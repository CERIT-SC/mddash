import type { JupyterFrontEnd } from '@jupyterlab/application';
import { NotebookPanel } from '@jupyterlab/notebook';
import { BoxLayout, Widget } from '@lumino/widgets';

import { showCompletionDialog } from './completion-dialog';
import { discoverSteps } from './discovery';
import { isDebugEnabled, logDebug, logError, logInfo } from './logging';
import {
  currentStatus,
  currentText,
  escapeHtml,
  executionErrorMessage,
  percentComplete,
  progressBarHtml,
  renderStepRows,
  summaryText
} from './view';
import type { NotebookViewSnapshot, PipelineStep } from './types';

const MIN_STRIP_HEIGHT = 56;
const STRIP_BOTTOM_GAP = 15;

// Step ids embed cell indices, which shift on cell insert/remove — statuses
// carry over by source+label (positional among duplicates) instead.
function statusKey(step: PipelineStep): string {
  return `${step.source}:${step.label}`;
}

export class PipelineSession {
  readonly panel: NotebookPanel;

  private readonly app: JupyterFrontEnd;
  private readonly stripWidget: Widget;
  private readonly stripNode: HTMLDivElement;
  private readonly resizeHandler = (): void => {
    this.syncStripHeight();
  };
  private readonly onCellsChanged = (): void => {
    this.refreshStepsKeepingStatus();
    this.render();
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
    this.panel.content.model?.cells.changed.connect(this.onCellsChanged);
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
    this.panel.content.model?.cells.changed.disconnect(this.onCellsChanged);
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

    const wasComplete = this.steps.length > 0 && this.steps.every(step => step.status === 'done');

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
    const isComplete = this.steps.length > 0 && this.steps.every(step => step.status === 'done');
    if (this.running && isComplete) {
      this.running = false;
    }
    if (isComplete && !wasComplete) {
      showCompletionDialog();
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
    const previousByKey = new Map<string, PipelineStep[]>();
    for (const step of this.steps) {
      const bucket = previousByKey.get(statusKey(step)) ?? [];
      bucket.push(step);
      previousByKey.set(statusKey(step), bucket);
    }
    this.steps = discoverSteps(this.panel).map(step => {
      const previousStep = previousByKey.get(statusKey(step))?.shift();
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

  private render(): void {
    const disabled = this.running || this.steps.length === 0 ? 'disabled' : '';
    const percent = percentComplete(this.steps);
    const status = currentStatus(this.steps);
    const toggleLabel = this.collapsed ? 'Expand' : 'Collapse';
    const steps = this.steps.length > 0
      ? `<div class="jp-PipelineTracker-stripSteps">${renderStepRows(this.steps)}</div>`
      : '<div class="jp-PipelineTracker-empty">No pipeline steps discovered yet.</div>';
    const current = `
      <div class="jp-PipelineTracker-current" data-status="${status}">
        <span class="jp-PipelineTracker-currentLabel">Status</span>
        <span class="jp-PipelineTracker-currentText">${escapeHtml(currentText(this.steps))}</span>
      </div>`;
    const details = this.collapsed
      ? status === 'error' ? current : ''
      : `${progressBarHtml(percent)}${current}${steps}`;

    this.stripNode.dataset.status = status;
    this.stripNode.dataset.collapsed = this.collapsed ? 'true' : 'false';

    this.stripNode.innerHTML = `
      <div class="jp-PipelineTracker-stripInner">
        <div class="jp-PipelineTracker-stripMain">
          <div class="jp-PipelineTracker-stripCopy">
            <div class="jp-PipelineTracker-stripTitle">Pipeline</div>
            <div class="jp-PipelineTracker-summary">${escapeHtml(summaryText(this.steps))}</div>
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
    const measuredStripHeight = this.measureStripContentHeight() + STRIP_BOTTOM_GAP;
    // fit/update forces a lumino relayout — skip when the height didn't move.
    if (measuredStripHeight === this.stripHeight) return;

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
    logDebug('Synced strip height', {
      notebook: this.panel.title.label,
      measuredStripHeight,
      contentHeaderSizeBasis: BoxLayout.getSizeBasis(this.panel.contentHeader),
      stripSizeBasis: BoxLayout.getSizeBasis(this.stripWidget)
    });
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
