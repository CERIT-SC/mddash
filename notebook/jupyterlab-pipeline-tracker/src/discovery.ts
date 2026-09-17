import type { NotebookPanel } from '@jupyterlab/notebook';

import {
  cellMetadataStepLabels,
  cellSource,
  cellType,
  isRecord,
  metadataValue,
  numberFromMetadata
} from './notebook';
import type { ParsedMetadataStep, PipelineStep, StepSource } from './types';

function slug(text: string): string {
  const value = text.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return value || 'step';
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

export function discoverSteps(panel: NotebookPanel): PipelineStep[] {
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
