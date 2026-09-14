import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { NotebookActions, NotebookPanel } from '@jupyterlab/notebook';

import { logError, logInfo } from './logging';
import type { PipelineSession } from './session';
import { PipelineWidgetExtension } from './widget-extension';

import '../style/index.css';

const PLUGIN_ID = 'jupyterlab-pipeline-tracker:plugin';

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
