import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';

import { onEvent, request, waitForAdsk } from '../connector/fusionBridge';
import type {
  LastOp,
  ListItem,
  ListMode,
  OpName,
  OpResult,
  ReadyPayload,
  RenameResult,
  SelectResult,
  SortOrder,
  Theme,
  ViewportSelection,
  VisibilityResult,
} from '../types/types';
import { errorMessage, filterItems, opBlocker, sortItems } from '../utils/items';
import { ActionBar } from './ActionBar';
import { FilterBar } from './FilterBar';
import { FooterBar } from './FooterBar';
import { HeaderBar } from './HeaderBar';
import { ItemList } from './ItemList';
import { OperationsGrid } from './OperationsGrid';
import { RenameDialog } from './RenameDialog';
import { RepeatLastButton } from './RepeatLastButton';
import { SelectionBar } from './SelectionBar';
import { StatusBar, type StatusTone } from './StatusBar';
import { useToast } from './common/Toast';

type FaceSource = {
  tokens: string[];
  label: string;
  returnMode: ListMode;
};

type Status = { message: string; tone: StatusTone };

type VisibilityAction = 'vis:show' | 'vis:hide' | 'vis:isolate' | 'vis:restoreAll';

const DESIGN_CHANGE_DEBOUNCE_MS = 350;
const NO_DOCUMENT_RETRY_MS = 2000;
const STATUS_HOLD_MS = 5000;

const isOccurrenceMode = (mode: ListMode) => mode === 'component' || mode === 'assembly';

export function SelectByList({ onTheme }: { onTheme: (theme: Theme | null) => void }) {
  const { showToast } = useToast();

  const [loading, setLoading] = useState(true);
  const [hasDocument, setHasDocument] = useState(true);
  const [designName, setDesignName] = useState('');
  const [mode, setMode] = useState<ListMode>('component');
  const [sort, setSort] = useState<SortOrder>('az');
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<ListItem[]>([]);
  const [warning, setWarning] = useState('');
  const [checked, setChecked] = useState<Set<string>>(() => new Set());
  const [viewport, setViewport] = useState<ViewportSelection>({ count: 0, keys: [] });
  const [lastOp, setLastOp] = useState<LastOp | null>(null);
  const [isolated, setIsolated] = useState(false);
  const [faceSource, setFaceSource] = useState<FaceSource | null>(null);
  const [renameTarget, setRenameTarget] = useState<ListItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  const anchorRef = useRef<string | null>(null);
  const filterRef = useRef<HTMLInputElement>(null);
  const loadSeq = useRef(0);
  const modeRef = useRef(mode);
  const faceSourceRef = useRef(faceSource);
  const shownIdsRef = useRef<string[]>([]);
  modeRef.current = mode;
  faceSourceRef.current = faceSource;

  const load = useCallback(
    async (nextMode: ListMode, tokens: string[] = [], quiet = false) => {
      const seq = ++loadSeq.current;
      if (!quiet) setLoading(true);
      try {
        const data = await request<ReadyPayload>('ready', { mode: nextMode, tokens });
        if (seq !== loadSeq.current) return;
        onTheme(data.theme);
        setHasDocument(data.hasDocument);
        setDesignName(data.designName);
        setItems(data.items);
        setWarning(data.warning);
        setViewport(data.viewport);
        setLastOp(data.lastOp);
        setIsolated(data.isolated);
        setChecked((prev) => {
          const ids = new Set(data.items.map((item) => item.id));
          const next = new Set([...prev].filter((id) => ids.has(id)));
          return next.size === prev.size ? prev : next;
        });
      } catch (error) {
        if (seq !== loadSeq.current) return;
        showToast(errorMessage(error), 'error');
      } finally {
        if (seq === loadSeq.current) setLoading(false);
      }
    },
    [onTheme, showToast]
  );

  const reload = useCallback(
    (quiet = false) => {
      const currentMode = modeRef.current;
      const tokens = currentMode === 'face' ? faceSourceRef.current?.tokens ?? [] : [];
      return load(currentMode, tokens, quiet);
    },
    [load]
  );

  const leaveFaceModeForNewDocument = useCallback(() => {
    const source = faceSourceRef.current;
    if (modeRef.current !== 'face') return false;
    const back = source?.returnMode ?? 'component';
    setFaceSource(null);
    setMode(back);
    setChecked(new Set());
    anchorRef.current = null;
    void load(back, [], true);
    return true;
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    void waitForAdsk().then(() => {
      if (!cancelled) void load('component');
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  useEffect(() => {
    let timer: number | null = null;
    const offDesign = onEvent('designChanged', (raw) => {
      let reason = '';
      try {
        reason = (JSON.parse(raw) as { reason?: string }).reason ?? '';
      } catch {
        // Treat malformed pushes as a plain refresh.
      }
      if (timer !== null) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        timer = null;
        if (reason === 'document' && leaveFaceModeForNewDocument()) return;
        void reload(true);
      }, DESIGN_CHANGE_DEBOUNCE_MS);
    });
    const offNoDocument = onEvent('noDocument', () => {
      setHasDocument(false);
      setItems([]);
      setDesignName('');
      setChecked(new Set());
      setViewport({ count: 0, keys: [] });
      setLoading(false);
    });
    const offViewport = onEvent('viewportSelectionChanged', (raw) => {
      try {
        setViewport(JSON.parse(raw) as ViewportSelection);
      } catch {
        // Ignore malformed pushes.
      }
    });
    return () => {
      if (timer !== null) window.clearTimeout(timer);
      offDesign();
      offNoDocument();
      offViewport();
    };
  }, [reload, leaveFaceModeForNewDocument]);

  useEffect(() => {
    if (hasDocument || loading) return;
    const timer = window.setInterval(() => void reload(true), NO_DOCUMENT_RETRY_MS);
    return () => window.clearInterval(timer);
  }, [hasDocument, loading, reload]);

  useEffect(() => {
    if (!status) return;
    const timer = window.setTimeout(() => setStatus(null), STATUS_HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [status]);

  const shownItems = useMemo(() => sortItems(filterItems(items, mode, query), sort), [items, mode, query, sort]);
  shownIdsRef.current = useMemo(() => shownItems.map((item) => item.id), [shownItems]);
  const itemsById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const checkedItems = useMemo(
    () => [...checked].map((id) => itemsById.get(id)).filter((item): item is ListItem => !!item),
    [checked, itemsById]
  );
  const viewportKeys = useMemo(() => new Set(viewport.keys), [viewport]);

  const onToggle = useCallback((id: string, event: MouseEvent) => {
    const shift = event.shiftKey;
    setChecked((prev) => {
      const next = new Set(prev);
      const anchor = anchorRef.current;
      if (shift && anchor && anchor !== id) {
        const ids = shownIdsRef.current;
        const from = ids.indexOf(anchor);
        const to = ids.indexOf(id);
        if (from >= 0 && to >= 0) {
          const on = prev.has(anchor);
          const [low, high] = from < to ? [from, to] : [to, from];
          for (let index = low; index <= high; index += 1) {
            if (on) next.add(ids[index]);
            else next.delete(ids[index]);
          }
          return next;
        }
      }
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    if (!shift) anchorRef.current = id;
  }, []);

  const checkAll = useCallback(() => {
    setChecked((prev) => new Set([...prev, ...shownIdsRef.current]));
  }, []);

  const checkNone = useCallback(() => {
    setChecked(new Set());
    anchorRef.current = null;
  }, []);

  const invert = useCallback(() => {
    setChecked((prev) => {
      const next = new Set(prev);
      shownIdsRef.current.forEach((id) => {
        if (next.has(id)) next.delete(id);
        else next.add(id);
      });
      return next;
    });
  }, []);

  async function run<T>(task: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    try {
      return await task();
    } catch (error) {
      const message = errorMessage(error);
      showToast(message, 'error');
      setStatus({ message, tone: 'error' });
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  const selectInViewport = async (targets: ListItem[]) => {
    if (!targets.length) return;
    const result = await run(() => request<SelectResult>('select:viewport', { tokens: targets.map((item) => item.token) }));
    if (!result) return;
    const missingNote = result.missing ? `, ${result.missing} no longer exist` : '';
    setStatus({ message: `${result.selected} item(s) selected in viewport${missingNote}`, tone: result.missing ? 'warn' : 'ok' });
  };

  const selectRef = useRef(selectInViewport);
  selectRef.current = selectInViewport;
  const onActivate = useCallback((item: ListItem) => {
    void selectRef.current([item]);
  }, []);

  const changeVisibility = async (action: VisibilityAction) => {
    const tokens = checkedItems.map((item) => item.token);
    const result = await run(() => request<VisibilityResult>(action, { tokens }));
    if (!result) return;
    setIsolated(result.isolated);
    const messages: Record<VisibilityAction, string> = {
      'vis:show': `Showing ${result.changed} item(s)`,
      'vis:hide': `Hid ${result.changed} item(s)`,
      'vis:isolate': `Isolated ${checkedItems.length} item(s), hid ${result.changed} other(s)`,
      'vis:restoreAll': result.changed ? `Visibility restored on ${result.changed} item(s)` : 'Everything is already visible',
    };
    setStatus({ message: messages[action], tone: 'ok' });
    await reload(true);
  };

  const exitFaceMode = () => {
    const back = faceSource?.returnMode ?? 'component';
    setFaceSource(null);
    setMode(back);
    setChecked(new Set());
    setItems([]);
    anchorRef.current = null;
    void load(back);
  };

  const enterFaceMode = (requireSelection: boolean) => {
    const sources = checkedItems.filter((item) => item.kind !== 'face');
    if (requireSelection && !sources.length) {
      showToast('Check a body or component first, then press Faces.', 'info');
      return;
    }
    const tokens = sources.map((item) => item.token);
    const label = sources.length ? `faces of ${sources.length} item(s)` : 'faces of visible bodies';
    setFaceSource({ tokens, label, returnMode: mode === 'face' ? faceSource?.returnMode ?? 'component' : mode });
    setMode('face');
    setChecked(new Set());
    setItems([]);
    anchorRef.current = null;
    void load('face', tokens);
  };

  const changeMode = (next: ListMode) => {
    if (next === mode) return;
    if (next === 'face') {
      enterFaceMode(false);
      return;
    }
    const sameData = isOccurrenceMode(next) && isOccurrenceMode(mode);
    setFaceSource(null);
    setMode(next);
    anchorRef.current = null;
    if (!sameData) {
      setChecked(new Set());
      setItems([]);
      void load(next);
    }
  };

  const submitRename = async (name: string) => {
    const target = renameTarget;
    if (!target) return;
    const result = await run(() => request<RenameResult>('item:rename', { token: target.token, name }));
    if (!result) return;
    setRenameTarget(null);
    setChecked((prev) => {
      const next = new Set(prev);
      next.delete(target.id);
      next.add(result.id);
      return next;
    });
    setStatus({ message: `Renamed to ${result.name}`, tone: 'ok' });
    await reload(true);
  };

  const runOp = async (op: OpName) => {
    const blocker = opBlocker(op, checkedItems);
    if (blocker) {
      showToast(blocker, 'info');
      return;
    }
    const result = await run(() => request<OpResult>('op:run', { op, tokens: checkedItems.map((item) => item.token) }));
    if (!result) return;
    setLastOp(result.lastOp);
    setStatus({ message: `${result.label} opened with ${result.count} item(s)`, tone: 'ok' });
    if (op === 'move' && result.count > 1) {
      showToast('Move is centred on the selection. If Fusion puts the gizmo elsewhere, the items are still selected.', 'info');
    }
  };

  const repeatLast = async () => {
    const result = await run(() => request<OpResult>('op:repeat'));
    if (!result) return;
    setLastOp(result.lastOp);
    const missingNote = result.missing ? ` (${result.missing} no longer exist)` : '';
    setStatus({ message: `${result.label} again on ${result.count} item(s)${missingNote}`, tone: result.missing ? 'warn' : 'ok' });
  };

  const closePalette = () => {
    void request('palette:close').catch((error) => showToast(errorMessage(error), 'error'));
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (renameTarget) return;
      const target = event.target as HTMLElement | null;
      const typing = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA';
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
        event.preventDefault();
        filterRef.current?.focus();
        filterRef.current?.select();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a' && !typing) {
        event.preventDefault();
        checkAll();
      } else if (event.key === 'Escape' && !typing) {
        checkNone();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [renameTarget, checkAll, checkNone]);

  const canRename =
    checkedItems.length === 1 && checkedItems[0].kind !== 'face' && !checkedItems[0].linked;

  let emptyMessage = '';
  if (!hasDocument) emptyMessage = 'No document open. Waiting for a design\u2026';
  else if (loading) emptyMessage = 'Loading\u2026';
  else if (items.length && query) emptyMessage = `Nothing matches "${query}".`;
  else if (mode === 'face') emptyMessage = 'No faces found. Check a body or component, then press Faces.';
  else if (mode === 'body') emptyMessage = 'This design has no bodies.';
  else if (mode === 'assembly') emptyMessage = 'No sub-assemblies in this design.';
  else emptyMessage = 'This design has no components. Root bodies are listed under Body.';

  const statusView: Status = status ??
    (hasDocument
      ? { message: `${viewport.count} item(s) selected in viewport`, tone: viewport.count ? 'ok' : 'dim' }
      : { message: 'No document open. Retrying every 2 seconds.', tone: 'warn' });

  return (
    <div id="sbl-app" className="sbl-app">
      <HeaderBar
        sort={sort}
        loading={loading}
        disabled={!hasDocument || !shownItems.length}
        onRefresh={() => void reload()}
        onCheckAll={checkAll}
        onCheckNone={checkNone}
        onToggleSort={() => setSort((current) => (current === 'az' ? 'browser' : 'az'))}
      />
      <FilterBar ref={filterRef} query={query} mode={mode} disabled={!hasDocument} onQuery={setQuery} onMode={changeMode} />
      {warning && (
        <div id="sbl-warning" className="sbl-warning">
          {warning}
        </div>
      )}
      <ItemList
        items={hasDocument ? shownItems : []}
        checked={checked}
        viewportKeys={viewportKeys}
        indent={sort === 'browser' && isOccurrenceMode(mode)}
        emptyMessage={emptyMessage}
        onToggle={onToggle}
        onActivate={onActivate}
      />
      <SelectionBar
        checkedCount={checkedItems.length}
        shownCount={shownItems.length}
        totalCount={mode === 'assembly' ? items.filter((item) => item.kind === 'assembly').length : items.length}
        inFaceMode={mode === 'face'}
        faceSourceLabel={faceSource?.label ?? ''}
        disabled={!hasDocument || busy}
        onInvert={invert}
        onFaces={() => (mode === 'face' ? exitFaceMode() : enterFaceMode(true))}
      />
      <ActionBar
        checkedCount={checkedItems.length}
        canRename={canRename}
        isolated={isolated}
        busy={busy}
        hasDocument={hasDocument}
        onSelectViewport={() => void selectInViewport(checkedItems)}
        onShow={() => void changeVisibility('vis:show')}
        onHide={() => void changeVisibility('vis:hide')}
        onIsolate={() => void changeVisibility('vis:isolate')}
        onRestoreAll={() => void changeVisibility('vis:restoreAll')}
        onRename={() => canRename && setRenameTarget(checkedItems[0])}
      />
      <OperationsGrid checkedItems={checkedItems} busy={busy} hasDocument={hasDocument} onRun={(op) => void runOp(op)} />
      <RepeatLastButton lastOp={lastOp} busy={busy || !hasDocument} onRepeat={() => void repeatLast()} />
      <StatusBar message={statusView.message} tone={statusView.tone} />
      <FooterBar designName={designName} onClose={closePalette} />
      {renameTarget && (
        <RenameDialog item={renameTarget} busy={busy} onCancel={() => setRenameTarget(null)} onSubmit={(name) => void submitRename(name)} />
      )}
    </div>
  );
}
