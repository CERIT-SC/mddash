import { logDebug } from './logging';

const DIALOG_TITLE = 'Workflow complete';
const DIALOG_BODY = 'You can head back to MDDash or keep working in this notebook.';
const DIALOG_ACTION = 'Continue in notebook';

export function showCompletionDialog(): void {
  const previouslyFocused = document.activeElement instanceof HTMLElement
    ? document.activeElement
    : null;

  const overlay = document.createElement('div');
  overlay.className = 'jp-PipelineTracker-dialogOverlay';

  const dialog = document.createElement('div');
  dialog.className = 'jp-PipelineTracker-dialog';
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-label', DIALOG_TITLE);

  const icon = document.createElement('span');
  icon.className = 'jp-PipelineTracker-dialogIcon';
  icon.setAttribute('aria-hidden', 'true');

  const title = document.createElement('h2');
  title.className = 'jp-PipelineTracker-dialogTitle';
  title.textContent = DIALOG_TITLE;

  const body = document.createElement('p');
  body.className = 'jp-PipelineTracker-dialogBody';
  body.textContent = DIALOG_BODY;

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'jp-PipelineTracker-dialogButton';
  button.textContent = DIALOG_ACTION;

  dialog.append(icon, title, body, button);
  overlay.append(dialog);

  const close = (): void => {
    document.removeEventListener('keydown', onKeyDown);
    overlay.remove();
    previouslyFocused?.focus();
  };

  const onKeyDown = (event: KeyboardEvent): void => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      close();
    }
  };

  overlay.addEventListener('click', (event: MouseEvent) => {
    if (event.target === overlay) {
      close();
    }
  });
  button.addEventListener('click', close);
  document.addEventListener('keydown', onKeyDown);

  document.body.append(overlay);
  button.focus();
  logDebug('Completion dialog shown');
}
