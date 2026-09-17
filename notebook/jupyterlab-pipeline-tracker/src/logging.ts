const LOG_PREFIX = '[pipeline-tracker]';

export function isDebugEnabled(): boolean {
  try {
    return window.localStorage.getItem('pipeline-tracker-debug') === '1';
  } catch {
    return false;
  }
}

export function logInfo(message: string, details?: unknown): void {
  if (details === undefined) {
    console.info(`${LOG_PREFIX} ${message}`);
    return;
  }
  console.info(`${LOG_PREFIX} ${message}`, details);
}

export function logDebug(message: string, details?: unknown): void {
  if (!isDebugEnabled()) {
    return;
  }
  if (details === undefined) {
    console.debug(`${LOG_PREFIX} ${message}`);
    return;
  }
  console.debug(`${LOG_PREFIX} ${message}`, details);
}

export function logError(message: string, error: unknown): void {
  console.error(`${LOG_PREFIX} ${message}`, error);
}
