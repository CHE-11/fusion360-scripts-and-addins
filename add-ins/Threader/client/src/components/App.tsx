import { useEffect, useState } from 'react';

import { DEV_CATALOG } from '../data/catalog';
import { onEvent, request, sendJsLog, sendReady, waitForAdsk } from '../connector/fusionBridge';
import {
  EMPTY_SELECTION,
  type ReadyPayload,
  type SelectionPayload,
  type StandardsCatalog,
  type TabId,
} from '../types/types';
import { AdjustTab } from './AdjustTab/AdjustTab';
import { HelpTab } from './HelpTab/HelpTab';
import { InsertTab } from './InsertTab/InsertTab';
import { Tabs } from './Tabs/Tabs';
import { ThreadTab } from './ThreadTab/ThreadTab';
import { ToastProvider, useToast } from './common/Toast';

function AppShell() {
  const { showToast } = useToast();
  const [tab, setTab] = useState<TabId>('thread');
  const [catalog, setCatalog] = useState<StandardsCatalog>(DEV_CATALOG);
  const [selection, setSelection] = useState<SelectionPayload>(EMPTY_SELECTION);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      sendJsLog('error', event.message || 'window.error', {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack,
      });
    };
    window.addEventListener('error', onError);
    void waitForAdsk();

    const applyDocument = (data: ReadyPayload) => {
      if (data.standards) setCatalog(data.standards);
    };

    void sendReady()
      .then((ready) => applyDocument(ready ?? {}))
      .catch((error) => {
        showToast(error instanceof Error ? error.message : 'Could not reach Fusion.', 'error');
      });

    void request<SelectionPayload>('face:readSelection')
      .then((next) => setSelection(next))
      .catch(() => setSelection(EMPTY_SELECTION));

    const offDoc = onEvent('docActivated', (raw) => {
      try {
        applyDocument(JSON.parse(raw) as ReadyPayload);
      } catch {
        setCatalog(DEV_CATALOG);
      }
      setSelection(EMPTY_SELECTION);
      setRevision((value) => value + 1);
    });
    const offSelection = onEvent('selectionChanged', (raw) => {
      try {
        const data = JSON.parse(raw) as SelectionPayload;
        setSelection((current) => ({
          cylinder: data.cylinder ?? current.cylinder,
          planar: data.planar ?? current.planar,
          center: data.center ?? current.center,
          inserts: data.inserts ?? current.inserts,
        }));
        if (data.document) applyDocument(data.document);
      } catch {
        // Ignore a malformed push from the add-in.
      }
    });

    return () => {
      window.removeEventListener('error', onError);
      offDoc();
      offSelection();
    };
  }, [showToast]);

  return (
    <div id="th_app" className="th_app">
      <Tabs active={tab} onChange={setTab} />
      {tab === 'thread' ? (
        <ThreadTab catalog={catalog} cylinder={selection.cylinder} onCreated={() => setRevision((value) => value + 1)} />
      ) : null}
      {tab === 'insert' ? (
        <InsertTab catalog={catalog} selection={selection} onCreated={() => setRevision((value) => value + 1)} />
      ) : null}
      {tab === 'adjust' ? <AdjustTab revision={revision} onChanged={() => setRevision((value) => value + 1)} /> : null}
      {tab === 'help' ? <HelpTab /> : null}
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AppShell />
    </ToastProvider>
  );
}
