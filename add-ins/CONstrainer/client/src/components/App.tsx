import { useCallback, useEffect, useState } from 'react';

import { onEvent, request, sendJsLog, sendReady, waitForAdsk } from '../connector/fusionBridge';
import {
  EMPTY_CONSTRAINT_SELECTION,
  EMPTY_JOINT_SELECTION,
  EMPTY_SKETCH_SELECTION,
  type ConstraintSelection,
  type DocumentContext,
  type JointSelection,
  type SelectionChangedPayload,
  type SketchSelection,
  type TabId,
} from '../types/types';
import { AssemblyConstraintsTab } from './AssemblyConstraintsTab/AssemblyConstraintsTab';
import { HelpTab } from './HelpTab/HelpTab';
import { JointTab } from './JointTab/JointTab';
import { SettingsTab } from './SettingsTab/SettingsTab';
import { SketchTab } from './SketchTab/SketchTab';
import { Tabs } from './Tabs/Tabs';
import { ToastProvider, useToast } from './common/Toast';

function leaveAssemblyTabs(current: TabId): TabId {
  return current === 'joints' || current === 'constraints' ? 'sketches' : current;
}

function AppShell() {
  const { showToast } = useToast();
  const [booted, setBooted] = useState(false);
  const [tab, setTab] = useState<TabId>('sketches');
  const [docName, setDocName] = useState('');
  const [jointsAllowed, setJointsAllowed] = useState(false);
  const [revision, setRevision] = useState(0);
  const [sketchSelection, setSketchSelection] = useState<SketchSelection>(EMPTY_SKETCH_SELECTION);
  const [jointSelection, setJointSelection] = useState<JointSelection>(EMPTY_JOINT_SELECTION);
  const [constraintSelection, setConstraintSelection] = useState<ConstraintSelection>(EMPTY_CONSTRAINT_SELECTION);
  const handleAvailability = useCallback((allowed: boolean) => {
    setJointsAllowed(allowed);
    if (!allowed) setTab(leaveAssemblyTabs);
  }, []);

  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      sendJsLog('error', event.message || 'window.error', {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack,
      });
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      sendJsLog('error', 'Unhandled promise rejection', {
        reason: String(reason),
        stack: reason instanceof Error ? reason.stack : undefined,
      });
    };
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);

    void waitForAdsk().then(() => setBooted(true));

    const applyDocument = (data: Partial<DocumentContext> & { name?: string }) => {
      setDocName(data.doc ?? data.name ?? '');
      if (typeof data.jointsAllowed === 'boolean') {
        setJointsAllowed(data.jointsAllowed);
        if (!data.jointsAllowed) setTab(leaveAssemblyTabs);
      }
    };

    void sendReady()
      .then((ready) => applyDocument(ready ?? {}))
      .catch((error) => {
        showToast(error instanceof Error ? error.message : 'Could not reach Fusion.', 'error');
      });

    const offDoc = onEvent('docActivated', (raw) => {
      try {
        applyDocument(JSON.parse(raw) as Partial<DocumentContext> & { name?: string });
      } catch {
        setDocName('');
        setJointsAllowed(false);
        setTab(leaveAssemblyTabs);
      }
      setRevision((value) => value + 1);
    });
    const offSelection = onEvent('selectionChanged', (raw) => {
      try {
        const data = JSON.parse(raw) as SelectionChangedPayload;
        if (data.sketch) setSketchSelection(data.sketch);
        if (data.joint) setJointSelection(data.joint);
        if (data.constraint) setConstraintSelection(data.constraint);
        if (data.document) applyDocument(data.document);
      } catch {
        // Ignore a malformed push from the add-in.
      }
    });

    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
      offDoc();
      offSelection();
    };
  }, [showToast]);

  useEffect(() => {
    if (!booted) return;
    let cancelled = false;
    void request<SketchSelection>('sketch:readSelection')
      .then((next) => {
        if (!cancelled) setSketchSelection(next);
      })
      .catch(() => {
        if (!cancelled) setSketchSelection(EMPTY_SKETCH_SELECTION);
      });
    if (jointsAllowed) {
      void request<JointSelection>('joint:readSelection')
        .then((next) => {
          if (!cancelled) setJointSelection(next);
        })
        .catch(() => {
          if (!cancelled) setJointSelection(EMPTY_JOINT_SELECTION);
        });
      void request<ConstraintSelection>('constraint:readSelection')
        .then((next) => {
          if (!cancelled) setConstraintSelection(next);
        })
        .catch(() => {
          if (!cancelled) setConstraintSelection(EMPTY_CONSTRAINT_SELECTION);
        });
    } else {
      setJointSelection(EMPTY_JOINT_SELECTION);
      setConstraintSelection(EMPTY_CONSTRAINT_SELECTION);
    }
    return () => {
      cancelled = true;
    };
  }, [booted, jointsAllowed]);

  return (
    <div id="cs_app" className="cs_app" data-doc={docName}>
      <Tabs active={tab} showJoints={jointsAllowed} onChange={setTab} />
      <main id="cs_main" className="cs_main">
        <SketchTab
          booted={booted}
          active={tab === 'sketches'}
          revision={revision}
          selection={sketchSelection}
          onSelection={setSketchSelection}
        />
        {jointsAllowed && (
          <JointTab
            booted={booted}
            active={tab === 'joints'}
            revision={revision}
            selection={jointSelection}
            onSelection={setJointSelection}
            onAvailability={handleAvailability}
          />
        )}
        {jointsAllowed && (
          <AssemblyConstraintsTab
            booted={booted}
            active={tab === 'constraints'}
            revision={revision}
            selection={constraintSelection}
          />
        )}
        <HelpTab active={tab === 'help'} />
        <SettingsTab active={tab === 'settings'} />
      </main>
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
