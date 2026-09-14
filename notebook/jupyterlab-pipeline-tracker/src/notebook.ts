import type { NotebookPanel } from '@jupyterlab/notebook';

export function isRecord(value: unknown): value is Record<string, any> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function numberFromMetadata(value: unknown): number | undefined {
  return Number.isInteger(value) && (value as number) >= 0 ? value as number : undefined;
}

export function cellSource(cellModel: any): string {
  if (cellModel?.sharedModel?.getSource) {
    return cellModel.sharedModel.getSource();
  }
  if (typeof cellModel?.value?.text === 'string') {
    return cellModel.value.text;
  }
  return '';
}

export function cellType(cellModel: any): string {
  return typeof cellModel?.type === 'string' ? cellModel.type : '';
}

export function metadataValue(panel: NotebookPanel, key: string): any {
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

export function cellMetadataValue(cellModel: any, key: string): any {
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

export function cellMetadataStepLabels(cellModel: any): string[] {
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
