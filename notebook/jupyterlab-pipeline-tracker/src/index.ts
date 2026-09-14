import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { DocumentRegistry } from '@jupyterlab/docregistry';
import { NotebookActions, NotebookPanel } from '@jupyterlab/notebook';
import { IDisposable, DisposableDelegate } from '@lumino/disposable';
import { BoxLayout, Widget } from '@lumino/widgets';

import '../style/index.css';

type StepStatus = 'pending' | 'running' | 'done' | 'error';
type StepSource = 'metadata' | 'cell-metadata' | 'marker' | 'heading' | 'explicit' | 'fallback';

interface PipelineStep {
  id: string;
  label: string;
  source: StepSource;
  cellIndices: number[];
  status: StepStatus;
  error?: string;
}

interface ParsedMetadataStep {
  label: string;
  cells?: number[];
  start?: number;
  end?: number;
}

interface NotebookViewSnapshot {
  activeCellIndex: number;
  scrollNode: HTMLElement | null;
  scrollTop: number;
}

const PLUGIN_ID = 'jupyterlab-pipeline-tracker:plugin';
const LOG_PREFIX = '[pipeline-tracker]';
const MIN_STRIP_HEIGHT = 56;
const STRIP_BOTTOM_GAP = 15;

function isDebugEnabled(): boolean {
  try {
    return window.localStorage.getItem('pipeline-tracker-debug') === '1';
  } catch {
    return false;
  }
}

function logInfo(message: string, details?: unknown): void {
  if (details === undefined) {
    console.info(`${LOG_PREFIX} ${message}`);
    return;
  }
  console.info(`${LOG_PREFIX} ${message}`, details);
}

function logDebug(message: string, details?: unknown): void {
  if (!isDebugEnabled()) {
    return;
  }
  if (details === undefined) {
    console.debug(`${LOG_PREFIX} ${message}`);
    return;
  }
  console.debug(`${LOG_PREFIX} ${message}`, details);
}

function logError(message: string, error: unknown): void {
  console.error(`${LOG_PREFIX} ${message}`, error);
}

function slug(text: string): string {
  const value = text.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return value || 'step';
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function extractHeading(markdown: string): string | null {
  let lastHeading: string | null = null;
  for (const line of markdown.split(/\r?\n/)) {
    const match = line.trim().match(/^#+\s*(.+)$/);
    if (match) {
      lastHeading = match[1].trim();
    }
  }
  return lastHeading;
}

function findPipelineMarkers(source: string): string[] {
  const labels: string[] = [];
  for (const line of source.split(/\r?\n/)) {
    const match = line.match(/^(?:\s*(?:#|\/\/)\s*)?(?:<!--\s*)?pipeline[-_\s]?step\s*:\s*(.+?)(?:\s*-->)?\s*$/i);
    if (match) {
      const label = match[1].trim();
      if (label) {
        labels.push(label);
      }
    }
  }
  return labels;
}

function findExplicitSteps(source: string): string[] {
  const labels: string[] = [];
  const pattern = /tracker\s*\.\s*step\s*\(\s*['"]([^'"]+)['"]/g;
  let match = pattern.exec(source);
  while (match) {
    labels.push(match[1]);
    match = pattern.exec(source);
  }
  return labels;
}

function isTrackerBootstrap(source: string): boolean {
  return source.includes('from pipeline_tracker') && source.includes('PipelineTracker');
}

function cellSource(cellModel: any): string {
  if (cellModel?.sharedModel?.getSource) {
    return cellModel.sharedModel.getSource();
  }
  if (typeof cellModel?.value?.text === 'string') {
    return cellModel.value.text;
  }
  return '';
}

function cellType(cellModel: any): string {
  return typeof cellModel?.type === 'string' ? cellModel.type : '';
}

function executionErrorMessage(args: any): string {
  const error = args?.error;
  const name = typeof error?.ename === 'string' ? error.ename : '';
  const value = typeof error?.evalue === 'string' ? error.evalue : '';

  if (name && value) {
    return `${name}: ${value}`;
  }
  return name || value || 'Cell execution failed';
}

function isRecord(value: unknown): value is Record<string, any> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function numberFromMetadata(value: unknown): number | undefined {
  return Number.isInteger(value) && (value as number) >= 0 ? value as number : undefined;
}

function metadataValue(panel: NotebookPanel, key: string): any {
  const model = panel.content.model as any;
  if (!model) {
    return undefined;
  }
  if (typeof model.getMetadata === 'function') {
    const value = model.getMetadata(key);
    if (value !== undefined) {
      return value;
    }
  }
  if (typeof model.sharedModel?.getMetadata === 'function') {
    const value = model.sharedModel.getMetadata(key);
    if (value !== undefined) {
      return value;
    }
  }
  return model.metadata?.[key];
}

function cellMetadataValue(cellModel: any, key: string): any {
  if (typeof cellModel?.getMetadata === 'function') {
    const value = cellModel.getMetadata(key);
    if (value !== undefined) {
      return value;
    }
  }
  if (typeof cellModel?.sharedModel?.getMetadata === 'function') {
    const value = cellModel.sharedModel.getMetadata(key);
    if (value !== undefined) {
      return value;
    }
  }
  return cellModel?.metadata?.[key] ?? cellModel?.sharedModel?.metadata?.[key];
}

function cellMetadataStepLabels(cellModel: any): string[] {
  const raw = cellMetadataValue(cellModel, 'pipeline_step')
    ?? cellMetadataValue(cellModel, 'pipelineTrackerStep')
    ?? cellMetadataValue(cellModel, 'pipeline_tracker_step');

  if (typeof raw === 'string' && raw.trim()) {
    return [raw.trim()];
  }
  if (Array.isArray(raw)) {
    return raw.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
      .map(value => value.trim());
  }
  if (isRecord(raw)) {
    const label = raw.label ?? raw.title ?? raw.name;
    return typeof label === 'string' && label.trim() ? [label.trim()] : [];
  }
  return [];
}

function parseMetadataStep(raw: unknown, fallbackStart?: number): ParsedMetadataStep | null {
  if (typeof raw === 'string') {
    const label = raw.trim();
    return label ? { label, start: fallbackStart } : null;
  }
  if (!isRecord(raw)) {
    return null;
  }

  const label = raw.label ?? raw.title ?? raw.name;
  if (typeof label !== 'string' || !label.trim()) {
    return null;
  }

  const cells = Array.isArray(raw.cells)
    ? raw.cells.filter((value: unknown): value is number => typeof value === 'number' && Number.isInteger(value) && value >= 0)
    : undefined;
  const start = numberFromMetadata(raw.start_cell)
    ?? numberFromMetadata(raw.startCell)
    ?? numberFromMetadata(raw.start)
    ?? numberFromMetadata(raw.cell)
    ?? numberFromMetadata(raw.cell_index)
    ?? numberFromMetadata(raw.cellIndex)
    ?? fallbackStart;
  const end = numberFromMetadata(raw.end_cell)
    ?? numberFromMetadata(raw.endCell)
    ?? numberFromMetadata(raw.end);

  return { label: label.trim(), cells, start, end };
}

function nonEmptyCodeCellIndices(cells: any): number[] {
  const indices: number[] = [];
  for (let index = 0; index < cells.length; index++) {
    const cellModel = cells.get(index);
    if (cellType(cellModel) === 'code') {
      const source = cellSource(cellModel);
      if (source.trim() && !isTrackerBootstrap(source)) {
        indices.push(index);
      }
    }
  }
  return indices;
}

function codeCellsInRange(cells: any, start: number, end: number): number[] {
  const indices: number[] = [];
  for (let index = start; index <= end && index < cells.length; index++) {
    const cellModel = cells.get(index);
    if (cellType(cellModel) !== 'code') {
      continue;
    }
    const source = cellSource(cellModel);
    if (source.trim() && !isTrackerBootstrap(source)) {
      indices.push(index);
    }
  }
  return indices;
}

function createStep(label: string, source: StepSource, cellIndices: number[], index: number): PipelineStep {
  return {
    id: `${source}-${slug(label)}-${index}-${cellIndices.join('-')}`,
    label,
    source,
    cellIndices,
    status: 'pending'
  };
}

function discoverMetadataSteps(panel: NotebookPanel, cells: any): PipelineStep[] {
  const raw = metadataValue(panel, 'pipeline_tracker') ?? metadataValue(panel, 'pipelineTracker');
  const rawSteps = Array.isArray(raw) ? raw : isRecord(raw) && Array.isArray(raw.steps) ? raw.steps : null;
  if (!rawSteps) {
    return [];
  }

  const codeCells = nonEmptyCodeCellIndices(cells);
  const parsedSteps = rawSteps
    .map((step, index) => parseMetadataStep(step, codeCells[index]))
    .filter((step): step is ParsedMetadataStep => Boolean(step));
  if (parsedSteps.length === 0) {
    return [];
  }

  const steps: PipelineStep[] = [];
  for (let index = 0; index < parsedSteps.length; index++) {
    const parsed = parsedSteps[index];
    const explicitCells = parsed.cells?.filter(cellIndex => codeCells.includes(cellIndex));
    const nextStart = parsedSteps.slice(index + 1).find(step => step.start !== undefined)?.start;
    const end = parsed.end ?? (nextStart !== undefined ? nextStart - 1 : cells.length - 1);
    const cellIndices = explicitCells && explicitCells.length > 0
      ? explicitCells
      : parsed.start !== undefined
        ? codeCellsInRange(cells, parsed.start, end)
        : [];

    const safeCellIndices = cellIndices.length > 0
      ? cellIndices
      : parsed.start !== undefined && codeCells.includes(parsed.start)
        ? [parsed.start]
        : [];
    if (safeCellIndices.length > 0) {
      steps.push(createStep(parsed.label, 'metadata', safeCellIndices, index));
    }
  }

  return steps;
}

function fallbackStepLabel(source: string, index: number): string {
  const firstLine = source.split(/\r?\n/).map(line => line.trim()).find(Boolean);
  if (!firstLine) {
    return `Code cell ${index + 1}`;
  }
  const withoutComment = firstLine.replace(/^#\s*/, '').trim();
  const shortened = withoutComment.length > 48 ? `${withoutComment.slice(0, 45)}...` : withoutComment;
  return `Code cell ${index + 1}: ${shortened}`;
}

function discoverSteps(panel: NotebookPanel): PipelineStep[] {
  const cells = panel.content.model?.cells as any;
  const steps: PipelineStep[] = [];
  let currentHeading: string | null = null;
  let currentSource: StepSource = 'heading';
  let headingStep: PipelineStep | null = null;

  if (!cells) {
    return steps;
  }

  const metadataSteps = discoverMetadataSteps(panel, cells);
  if (metadataSteps.length > 0) {
    return metadataSteps;
  }

  for (let index = 0; index < cells.length; index++) {
    const cellModel = cells.get(index);
    const type = cellType(cellModel);
    const source = cellSource(cellModel);

    if (type === 'markdown') {
      const marker = findPipelineMarkers(source).at(-1);
      if (marker) {
        currentHeading = marker;
        currentSource = 'marker';
        headingStep = null;
        continue;
      }
      const heading = extractHeading(source);
      if (heading) {
        currentHeading = heading;
        currentSource = 'heading';
        headingStep = null;
      }
      continue;
    }

    if (type !== 'code') {
      continue;
    }
    if (!source.trim() || isTrackerBootstrap(source)) {
      continue;
    }

    const cellMetadataLabels = cellMetadataStepLabels(cellModel);
    const markerLabels = findPipelineMarkers(source);
    const explicitLabels = [...cellMetadataLabels, ...markerLabels, ...findExplicitSteps(source)];
    if (explicitLabels.length > 0) {
      for (const label of explicitLabels) {
        const sourceKind: StepSource = cellMetadataLabels.includes(label)
          ? 'cell-metadata'
          : markerLabels.includes(label)
            ? 'marker'
            : 'explicit';
        steps.push(createStep(label, sourceKind, [index], steps.length));
      }
      headingStep = null;
      continue;
    }

    if (!currentHeading) {
      continue;
    }

    const label = currentHeading;
    if (!headingStep) {
      headingStep = createStep(label, currentSource, [index], steps.length);
      steps.push(headingStep);
    } else {
      headingStep.cellIndices.push(index);
    }
  }

  if (steps.length > 0) {
    return steps;
  }

  return nonEmptyCodeCellIndices(cells).map((index, stepIndex) => {
    const cellModel = cells.get(index);
    return createStep(fallbackStepLabel(cellSource(cellModel), index), 'fallback', [index], stepIndex);
  });
}

class PipelineSession {
  readonly panel: NotebookPanel;

  private readonly app: JupyterFrontEnd;
  private readonly stripWidget: Widget;
  private readonly stripNode: HTMLDivElement;
  private readonly resizeHandler = (): void => {
    this.syncStripHeight();
  };
  private stripHeight = 0;
  private steps: PipelineStep[] = [];
  private cellToSteps = new Map<number, PipelineStep[]>();
  private collapsed = false;
  private running = false;

  constructor(app: JupyterFrontEnd, panel: NotebookPanel) {
    this.app = app;
    this.panel = panel;
    this.stripNode = document.createElement('div');
    this.stripWidget = new Widget({ node: this.stripNode });
    this.stripWidget.addClass('jp-PipelineTracker-strip');
    this.stripNode.style.minHeight = `${MIN_STRIP_HEIGHT}px`;
    this.stripNode.style.width = '100%';
    this.stripNode.style.overflow = 'visible';
    BoxLayout.setStretch(this.stripWidget, 0);
    BoxLayout.setSizeBasis(this.stripWidget, MIN_STRIP_HEIGHT);
    window.addEventListener('resize', this.resizeHandler);
    this.insertStrip();
    this.refreshSteps();
    this.render();
    logDebug('Session created', { notebook: this.panel.title.label, id: this.panel.id });

    void panel.context.ready.then(() => {
      this.refreshStepsKeepingStatus();
      this.render();
      logDebug('Context ready', { notebook: this.panel.title.label, steps: this.steps.length });
    }).catch((error: unknown) => {
      logError('context.ready failed', error);
    });

    void panel.revealed.then(() => {
      this.stripWidget.show();
      this.panel.contentHeader.show();
      this.panel.contentHeader.update();
      this.panel.update();
      this.render();
      this.logLayout('revealed');
    }).catch((error: unknown) => {
      logError('revealed failed', error);
    });
  }

  matchesExecution(args: any): boolean {
    return args.notebook === this.panel.content;
  }

  dispose(): void {
    window.removeEventListener('resize', this.resizeHandler);
    this.stripWidget.dispose();
    logDebug('Session disposed', { notebook: this.panel.title.label, id: this.panel.id });
  }

  refreshLayout(reason = 'manual'): void {
    this.stripWidget.show();
    this.panel.contentHeader.show();
    this.panel.contentHeader.update();
    this.panel.update();
    this.syncStripHeight();
    logDebug('Refreshed session layout', {
      notebook: this.panel.title.label,
      id: this.panel.id,
      reason
    });
  }

  refreshSteps(): void {
    this.steps = discoverSteps(this.panel);
    this.rebuildCellMap();
  }

  async runAll(): Promise<void> {
    this.refreshSteps();
    for (const step of this.steps) {
      step.status = 'pending';
      step.error = undefined;
    }

    const firstStep = this.steps[0];
    if (firstStep) {
      firstStep.status = 'running';
    }

    this.running = true;
    this.render();
    logDebug('Run requested', { notebook: this.panel.title.label, steps: this.steps.length });
    const viewSnapshot = this.captureNotebookView();
    this.app.shell.activateById(this.panel.id);
    this.panel.activate();

    try {
      const runPromise = this.app.commands.execute('notebook:run-all-cells');
      this.restoreNotebookView(viewSnapshot);
      await runPromise;
    } catch (error) {
      this.running = false;
      if (firstStep) {
        firstStep.status = 'error';
        firstStep.error = error instanceof Error ? error.message : String(error);
      }
      this.render();
      logError('run-all-cells failed', error);
    }
  }

  handleExecution(args: any): void {
    if (!this.matchesExecution(args)) {
      return;
    }

    const cellIndex = this.panel.content.widgets.indexOf(args.cell);
    if (cellIndex < 0) {
      return;
    }

    const affectedSteps = this.cellToSteps.get(cellIndex) ?? [];
    if (affectedSteps.length === 0) {
      return;
    }

    const success = args.success !== false;
    for (const step of affectedSteps) {
      if (step.status === 'pending') {
        step.status = 'running';
      }

      if (!success) {
        step.status = 'error';
        step.error = executionErrorMessage(args);
        this.running = false;
        logDebug('Execution error in step', { notebook: this.panel.title.label, step: step.label });
        continue;
      }

      const lastCell = Math.max(...step.cellIndices);
      if (cellIndex === lastCell) {
        step.status = 'done';
      }
    }

    this.markNextPendingStepRunning();
    if (this.steps.length > 0 && this.steps.every(step => step.status === 'done')) {
      this.running = false;
    }
    this.render();
  }

  private insertStrip(): void {
    this.panel.contentHeader.node.style.overflow = 'visible';
    this.panel.contentHeader.insertWidget(0, this.stripWidget);
    this.stripWidget.show();
    this.panel.contentHeader.show();
    this.stripWidget.fit();
    this.panel.contentHeader.fit();
    this.panel.contentHeader.update();
    this.panel.fit();
    this.panel.update();
    logInfo('Inserted strip via notebook contentHeader', {
      notebook: this.panel.title.label,
      id: this.panel.id,
      headerClass: this.panel.contentHeader.node.className
    });
    this.logLayout('insert');
  }

  private refreshStepsKeepingStatus(): void {
    const previousSteps = new Map(this.steps.map(step => [step.id, step]));
    this.steps = discoverSteps(this.panel).map(step => {
      const previousStep = previousSteps.get(step.id);
      return previousStep ? { ...step, status: previousStep.status, error: previousStep.error } : step;
    });
    this.rebuildCellMap();
  }

  private rebuildCellMap(): void {
    this.cellToSteps = new Map<number, PipelineStep[]>();
    for (const step of this.steps) {
      for (const cellIndex of step.cellIndices) {
        const existing = this.cellToSteps.get(cellIndex) ?? [];
        existing.push(step);
        this.cellToSteps.set(cellIndex, existing);
      }
    }
  }

  private markNextPendingStepRunning(): void {
    if (!this.running) {
      return;
    }
    if (this.steps.some(step => step.status === 'running')) {
      return;
    }
    const next = this.steps.find(step => step.status === 'pending');
    if (next) {
      next.status = 'running';
    }
  }

  private captureNotebookView(): NotebookViewSnapshot {
    const scrollNode = this.findNotebookScrollNode();
    return {
      activeCellIndex: this.panel.content.activeCellIndex,
      scrollNode,
      scrollTop: scrollNode?.scrollTop ?? 0
    };
  }

  private restoreNotebookView(snapshot: NotebookViewSnapshot): void {
    const restore = (): void => {
      if (!this.panel.isDisposed && snapshot.activeCellIndex >= 0) {
        this.panel.content.activeCellIndex = snapshot.activeCellIndex;
      }
      if (snapshot.scrollNode?.isConnected) {
        snapshot.scrollNode.scrollTop = snapshot.scrollTop;
      }
    };

    restore();
    window.requestAnimationFrame(restore);
    window.setTimeout(restore, 100);
    window.setTimeout(restore, 300);
  }

  private findNotebookScrollNode(): HTMLElement | null {
    return this.panel.content.node.querySelector<HTMLElement>('.jp-WindowedPanel-outer')
      ?? this.panel.content.node.querySelector<HTMLElement>('.jp-Notebook-viewport')
      ?? this.panel.content.node;
  }

  private doneCount(): number {
    return this.steps.filter(step => step.status === 'done').length;
  }

  private percentComplete(): number {
    return this.steps.length > 0 ? Math.round((this.doneCount() / this.steps.length) * 100) : 0;
  }

  private summaryText(): string {
    if (this.steps.length === 0) {
      return 'No pipeline steps discovered.';
    }
    return `${this.doneCount()} / ${this.steps.length} steps complete`;
  }

  private currentText(): string {
    const errorIndex = this.steps.findIndex(step => step.status === 'error');
    if (errorIndex >= 0) {
      const errorStep = this.steps[errorIndex];
      return `Failed at Step ${errorIndex + 1}: ${errorStep.label} - ${errorStep.error ?? 'Cell execution failed'}`;
    }
    const runningStep = this.steps.find(step => step.status === 'running');
    if (runningStep) {
      return `Running: ${runningStep.label}`;
    }
    if (this.steps.length > 0 && this.steps.every(step => step.status === 'done')) {
      return 'Pipeline complete';
    }
    return this.steps.length > 0 ? `Ready: ${this.steps[0].label}` : 'Open a pipeline notebook';
  }

  private currentStatus(): StepStatus | 'ready' | 'complete' | 'empty' {
    if (this.steps.some(step => step.status === 'error')) {
      return 'error';
    }
    if (this.steps.some(step => step.status === 'running')) {
      return 'running';
    }
    if (this.steps.length > 0 && this.steps.every(step => step.status === 'done')) {
      return 'complete';
    }
    return this.steps.length > 0 ? 'ready' : 'empty';
  }

  private progressBarHtml(): string {
    return `
      <div class="jp-PipelineTracker-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${this.percentComplete()}">
        <div class="jp-PipelineTracker-fill" style="width: ${this.percentComplete()}%"></div>
      </div>`;
  }

  private renderStepRows(): string {
    return this.steps.map((step, index) => {
      const mark = this.statusMark(step.status, index);
      const label = step.error ? `${step.label} - ${step.error}` : step.label;
      return `
        <div class="jp-PipelineTracker-step" data-status="${step.status}" title="${escapeHtml(label)}">
          <span class="jp-PipelineTracker-dot">${mark}</span>
          <span class="jp-PipelineTracker-stepBody">
            <span class="jp-PipelineTracker-stepNumber">Step ${index + 1}</span>
            <span class="jp-PipelineTracker-label">${escapeHtml(label)}</span>
          </span>
        </div>`;
    }).join('');
  }

  private statusMark(status: StepStatus, index?: number): string {
    if (status === 'done') {
      return '&#10003;';
    }
    if (status === 'error') {
      return '!';
    }
    return index !== undefined ? String(index + 1) : '';
  }

  private render(): void {
    const disabled = this.running || this.steps.length === 0 ? 'disabled' : '';
    const percent = this.percentComplete();
    const status = this.currentStatus();
    const toggleLabel = this.collapsed ? 'Expand' : 'Collapse';
    const steps = this.steps.length > 0
      ? `<div class="jp-PipelineTracker-stripSteps">${this.renderStepRows()}</div>`
      : '<div class="jp-PipelineTracker-empty">No pipeline steps discovered yet.</div>';
    const current = `
      <div class="jp-PipelineTracker-current" data-status="${status}">
        <span class="jp-PipelineTracker-currentLabel">Status</span>
        <span class="jp-PipelineTracker-currentText">${escapeHtml(this.currentText())}</span>
      </div>`;
    const details = this.collapsed
      ? status === 'error' ? current : ''
      : `${this.progressBarHtml()}${current}${steps}`;

    this.stripNode.dataset.status = status;
    this.stripNode.dataset.collapsed = this.collapsed ? 'true' : 'false';

    this.stripNode.innerHTML = `
      <div class="jp-PipelineTracker-stripInner">
        <div class="jp-PipelineTracker-stripMain">
          <div class="jp-PipelineTracker-stripCopy">
            <div class="jp-PipelineTracker-stripTitle">Pipeline</div>
            <div class="jp-PipelineTracker-summary">${escapeHtml(this.summaryText())}</div>
          </div>
          <div class="jp-PipelineTracker-stripActions">
            <span class="jp-PipelineTracker-percent">${percent}%</span>
            <button class="jp-PipelineTracker-primaryButton" data-action="run-all" ${disabled}>
              <span class="jp-PipelineTracker-playIcon" aria-hidden="true"></span>
              <span>Run Pipeline</span>
            </button>
            <button class="jp-PipelineTracker-toggleButton" data-action="toggle-collapse" aria-expanded="${this.collapsed ? 'false' : 'true'}">
              <span class="jp-PipelineTracker-toggleIcon" aria-hidden="true"></span>
              <span>${toggleLabel}</span>
            </button>
          </div>
        </div>
        ${details}
      </div>
    `;

    const runButton = this.stripNode.querySelector<HTMLButtonElement>('[data-action="run-all"]');
    if (runButton) {
      runButton.addEventListener('click', () => {
        void this.runAll();
      });
    }

    const toggleButton = this.stripNode.querySelector<HTMLButtonElement>('[data-action="toggle-collapse"]');
    if (toggleButton) {
      toggleButton.addEventListener('click', () => {
        this.collapsed = !this.collapsed;
        this.render();
      });
    }

    this.syncStripHeight();

    if (isDebugEnabled()) {
      window.requestAnimationFrame(() => {
        this.logLayout('render');
      });
    }
  }

  private syncStripHeight(): void {
    this.applyStripHeight();
    window.requestAnimationFrame(() => {
      this.applyStripHeight();
    });
    window.setTimeout(() => this.applyStripHeight(), 120);
  }

  private applyStripHeight(): void {
    const headerNode = this.panel.contentHeader.node;

    this.stripNode.style.minHeight = `${MIN_STRIP_HEIGHT}px`;

    const measuredStripHeight = this.measureStripContentHeight() + STRIP_BOTTOM_GAP;
    const heightChanged = measuredStripHeight !== this.stripHeight;

    this.stripHeight = measuredStripHeight;
    this.stripNode.style.minHeight = `${measuredStripHeight}px`;
    this.stripNode.style.height = 'auto';
    headerNode.style.minHeight = `${measuredStripHeight}px`;
    headerNode.style.height = 'auto';
    BoxLayout.setSizeBasis(this.panel.contentHeader, measuredStripHeight);
    BoxLayout.setSizeBasis(this.stripWidget, measuredStripHeight);
    this.stripWidget.fit();
    this.panel.contentHeader.fit();
    this.panel.contentHeader.update();
    this.panel.fit();
    this.panel.update();
    if (heightChanged) {
      logDebug('Synced strip height', {
        notebook: this.panel.title.label,
        measuredStripHeight,
        contentHeaderSizeBasis: BoxLayout.getSizeBasis(this.panel.contentHeader),
        stripSizeBasis: BoxLayout.getSizeBasis(this.stripWidget)
      });
    }
  }

  private measureStripContentHeight(): number {
    const contentNode = this.stripNode.querySelector<HTMLElement>('.jp-PipelineTracker-stripInner');
    if (!contentNode) {
      return MIN_STRIP_HEIGHT;
    }

    const rectHeight = Math.ceil(contentNode.getBoundingClientRect().height);
    const scrollHeight = Math.ceil(contentNode.scrollHeight);
    return Math.max(MIN_STRIP_HEIGHT, rectHeight, scrollHeight);
  }

  private logLayout(reason: string): void {
    if (!isDebugEnabled()) {
      return;
    }

    const stripStyle = window.getComputedStyle(this.stripNode);
    const contentNode = this.stripNode.querySelector<HTMLElement>('.jp-PipelineTracker-stripInner');
    const contentRect = contentNode?.getBoundingClientRect();
    const headerNode = this.panel.contentHeader.node;
    const headerStyle = window.getComputedStyle(headerNode);
    const stripRect = this.stripNode.getBoundingClientRect();
    const headerRect = headerNode.getBoundingClientRect();

    logDebug(`Strip layout (${reason})`, {
      notebook: this.panel.title.label,
      stripWidth: this.stripNode.offsetWidth,
      stripHeight: this.stripNode.offsetHeight,
      stripDisplay: stripStyle.display,
      stripVisibility: stripStyle.visibility,
      stripMinHeight: stripStyle.minHeight,
      stripContentHeight: contentNode ? Math.ceil(Math.max(
        contentNode.scrollHeight,
        contentRect?.height ?? 0
      )) : null,
      stripRect: {
        top: stripRect.top,
        left: stripRect.left,
        width: stripRect.width,
        height: stripRect.height
      },
      headerDisplay: headerStyle.display,
      headerVisibility: headerStyle.visibility,
      headerMinHeight: headerStyle.minHeight,
      headerRect: {
        top: headerRect.top,
        left: headerRect.left,
        width: headerRect.width,
        height: headerRect.height
      },
      headerChildren: headerNode.childElementCount,
      stripHtmlLength: this.stripNode.innerHTML.length,
      contentHeaderSizeBasis: BoxLayout.getSizeBasis(this.panel.contentHeader),
      stripSizeBasis: BoxLayout.getSizeBasis(this.stripWidget)
    });
  }
}

class PipelineWidgetExtension implements DocumentRegistry.WidgetExtension {
  constructor(
    private readonly app: JupyterFrontEnd,
    private readonly sessions: Map<NotebookPanel, PipelineSession>
  ) {}

  createNew(widget: Widget): IDisposable {
    if (!(widget instanceof NotebookPanel)) {
      return new DisposableDelegate(() => {
        // This extension is registered for notebooks, but keep the guard cheap.
      });
    }

    const panel = widget;
    const existing = this.sessions.get(panel);
    if (existing) {
      return new DisposableDelegate(() => {
        // The original session owns the widget and will be disposed with it.
      });
    }

    const session = new PipelineSession(this.app, panel);
    this.sessions.set(panel, session);
    logInfo('Session registered by widget extension', {
      notebook: panel.title.label,
      id: panel.id
    });

    return new DisposableDelegate(() => {
      session.dispose();
      this.sessions.delete(panel);
      logInfo('Session removed by widget extension', {
        notebook: panel.title.label,
        id: panel.id
      });
    });
  }
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: PLUGIN_ID,
  autoStart: true,
  activate: (app: JupyterFrontEnd): void => {
    logInfo('Plugin activate', {
      id: PLUGIN_ID,
      appVersion: (app as any).version ?? 'unknown'
    });

    const sessions = new Map<NotebookPanel, PipelineSession>();
    app.docRegistry.addWidgetExtension(
      'Notebook',
      new PipelineWidgetExtension(app, sessions)
    );
    logInfo('Notebook widget extension registered');

    NotebookActions.executed.connect((_: unknown, args: unknown) => {
      for (const session of sessions.values()) {
        try {
          session.handleExecution(args as any);
        } catch (error) {
          logError('handleExecution failed', error);
        }
      }
    });

    app.shell.currentChanged?.connect((_: unknown, args: any) => {
      const widget = args.newValue;
      if (widget instanceof NotebookPanel) {
        const session = sessions.get(widget);
        session?.refreshLayout('current-changed');
      }
    });
  }
};

export default plugin;
