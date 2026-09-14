export type StepStatus = 'pending' | 'running' | 'done' | 'error';
export type StepSource = 'metadata' | 'cell-metadata' | 'marker' | 'heading' | 'explicit' | 'fallback';

export interface PipelineStep {
  id: string;
  label: string;
  source: StepSource;
  cellIndices: number[];
  status: StepStatus;
  error?: string;
}

export interface ParsedMetadataStep {
  label: string;
  cells?: number[];
  start?: number;
  end?: number;
}

export interface NotebookViewSnapshot {
  activeCellIndex: number;
  scrollNode: HTMLElement | null;
  scrollTop: number;
}
