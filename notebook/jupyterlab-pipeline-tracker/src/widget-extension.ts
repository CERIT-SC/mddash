import type { JupyterFrontEnd } from '@jupyterlab/application';
import { DocumentRegistry } from '@jupyterlab/docregistry';
import { NotebookPanel } from '@jupyterlab/notebook';
import { IDisposable, DisposableDelegate } from '@lumino/disposable';
import { Widget } from '@lumino/widgets';

import { PipelineSession } from './session';
import { logInfo } from './logging';

export class PipelineWidgetExtension implements DocumentRegistry.WidgetExtension {
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
