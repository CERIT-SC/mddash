import type { PipelineStep, StepStatus } from './types';

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function executionErrorMessage(args: any): string {
  const error = args?.error;
  const name = typeof error?.ename === 'string' ? error.ename : '';
  const value = typeof error?.evalue === 'string' ? error.evalue : '';

  if (name && value) {
    return `${name}: ${value}`;
  }
  return name || value || 'Cell execution failed';
}

function doneCount(steps: PipelineStep[]): number {
  return steps.filter(step => step.status === 'done').length;
}

export function percentComplete(steps: PipelineStep[]): number {
  return steps.length > 0 ? Math.round((doneCount(steps) / steps.length) * 100) : 0;
}

export function summaryText(steps: PipelineStep[]): string {
  if (steps.length === 0) {
    return 'No pipeline steps discovered.';
  }
  return `${doneCount(steps)} / ${steps.length} steps complete`;
}

export function currentText(steps: PipelineStep[]): string {
  const errorIndex = steps.findIndex(step => step.status === 'error');
  if (errorIndex >= 0) {
    const errorStep = steps[errorIndex];
    return `Failed at Step ${errorIndex + 1}: ${errorStep.label} - ${errorStep.error ?? 'Cell execution failed'}`;
  }
  const runningStep = steps.find(step => step.status === 'running');
  if (runningStep) {
    return `Running: ${runningStep.label}`;
  }
  if (steps.length > 0 && steps.every(step => step.status === 'done')) {
    return 'Pipeline complete';
  }
  return steps.length > 0 ? `Ready: ${steps[0].label}` : 'Open a pipeline notebook';
}

export function currentStatus(steps: PipelineStep[]): StepStatus | 'ready' | 'complete' | 'empty' {
  if (steps.some(step => step.status === 'error')) {
    return 'error';
  }
  if (steps.some(step => step.status === 'running')) {
    return 'running';
  }
  if (steps.length > 0 && steps.every(step => step.status === 'done')) {
    return 'complete';
  }
  return steps.length > 0 ? 'ready' : 'empty';
}

function statusMark(status: StepStatus, index?: number): string {
  if (status === 'done') {
    return '&#10003;';
  }
  if (status === 'error') {
    return '!';
  }
  return index !== undefined ? String(index + 1) : '';
}

export function progressBarHtml(percent: number): string {
  return `
      <div class="jp-PipelineTracker-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}">
        <div class="jp-PipelineTracker-fill" style="width: ${percent}%"></div>
      </div>`;
}

export function renderStepRows(steps: PipelineStep[]): string {
  return steps.map((step, index) => {
    const mark = statusMark(step.status, index);
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
