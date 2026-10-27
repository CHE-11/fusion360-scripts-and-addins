import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { onEvent, request, sendJsLog, waitForAdsk } from '../../connector/fusionBridge';
import type {
  ActiveFileLocation,
  ActiveFilePayload,
  ExplorerNode,
  Listing,
  LocationTarget,
  ReadyPayload,
  ReferencesPayload,
  SearchProgress,
  SearchStartPayload,
} from '../../types/types';
import { errorMessage, newSearchId, sortNodes } from '../../utils/nodes';
import { useToast } from '../common/Toast';
import { Breadcrumb } from './Breadcrumb';
import { ConfirmDialog } from './ConfirmDialog';
import { DetailPanel } from './DetailPanel';
import { FileList, type FileSection } from './FileList';
import { MoveDialog } from './MoveDialog';
import { Toolbar } from './Toolbar';

const READY_TIMEOUT_MS = 30000;

type DetailState = {
  fileId: string;
  status: 'loading' | 'ready' | 'error';
  data: ReferencesPayload | null;
  message: string;
};

export function Explorer() {
  const { showToast } = useToast();
  const [hubs, setHubs] = useState<ExplorerNode[]>([]);
  const [activeHubId, setActiveHubId] = useState('');
  const [activeFileId, setActiveFileId] = useState('');
  const [location, setLocation] = useState<ExplorerNode | null>(null);
  const [crumbs, setCrumbs] = useState<ExplorerNode[]>([]);
  const [children, setChildren] = useState<ExplorerNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [activeQuery, setActiveQuery] = useState('');
  const [projectMatches, setProjectMatches] = useState<ExplorerNode[]>([]);
  const [searching, setSearching] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [searchTruncated, setSearchTruncated] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const [renameId, setRenameId] = useState('');
  const [creating, setCreating] = useState(false);
  const [confirmNode, setConfirmNode] = useState<ExplorerNode | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [moveNode, setMoveNode] = useState<ExplorerNode | null>(null);
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [detailNonce, setDetailNonce] = useState(0);
  const [searchEpoch, setSearchEpoch] = useState(0);
  const [inserting, setInserting] = useState(false);

  const loadSeq = useRef(0);
  const searchRef = useRef('');
  const locationRef = useRef<ExplorerNode | null>(null);
  const crumbsRef = useRef<ExplorerNode[]>([]);
  const rowsRef = useRef<ExplorerNode[]>([]);
  const selectedRef = useRef('');
  const queryRef = useRef('');
  const activeQueryRef = useRef('');
  const skipRenameCommit = useRef(false);
  const refCache = useRef(new Map<string, ReferencesPayload>());
  const openNodeRef = useRef<(node: ExplorerNode) => void>(() => {});

  locationRef.current = location;
  crumbsRef.current = crumbs;
  selectedRef.current = selectedId;
  queryRef.current = query;
  activeQueryRef.current = activeQuery;

  const applyListing = useCallback((listing: Listing) => {
    setLocation(listing.location);
    setCrumbs(listing.crumbs);
    setChildren(listing.children);
    if (listing.activeFileId) setActiveFileId(listing.activeFileId);
    if (listing.location.kind === 'hub') setActiveHubId(listing.location.id);
    const hubCrumb = listing.crumbs.find((crumb) => crumb.kind === 'hub');
    if (hubCrumb) setActiveHubId(hubCrumb.id);
  }, []);

  const applySearchProgress = useCallback((data: SearchProgress) => {
    if (data.searchId !== searchRef.current) return;
    setProjectMatches((current) => sortNodes(dedupe(data.replace ? data.matches : [...current, ...data.matches])));
    setSearchTruncated(data.truncated);
    setIndexing(Boolean(data.indexing) && !data.done);
    if (data.done) {
      setSearching(false);
      setIndexing(false);
    }
  }, []);

  const load = useCallback(
    async (target: LocationTarget, options?: { selectId?: string; keepQuery?: boolean; refresh?: boolean }) => {
      const seq = ++loadSeq.current;
      setLoading(true);
      setError('');
      if (!options?.keepQuery) {
        setQuery('');
        setActiveQuery('');
      }
      try {
        const listing = await request<Listing>('folder:list', { ...target, refresh: options?.refresh });
        if (seq !== loadSeq.current) return;
        applyListing(listing);
        setSelectedId(options?.selectId ?? '');
        setRenameId('');
        setCreating(false);
      } catch (err) {
        if (seq !== loadSeq.current) return;
        const message = errorMessage(err, 'Could not open that folder.');
        if (locationRef.current) showToast(message, 'error');
        else setError(message);
      } finally {
        if (seq === loadSeq.current) setLoading(false);
      }
    },
    [applyListing, showToast]
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await waitForAdsk();
      try {
        const ready = await Promise.race([
          request<ReadyPayload>('ready'),
          new Promise<never>((_, reject) => {
            window.setTimeout(
              () => reject(new Error('Fusion did not answer. Check the Text Commands window, then retry.')),
              READY_TIMEOUT_MS
            );
          }),
        ]);
        if (cancelled) return;
        setHubs(ready.hubs);
        setActiveHubId(ready.activeHubId);
        setActiveFileId(ready.activeFileId);
        if (ready.listing) {
          applyListing(ready.listing);
          if (ready.listingError) showToast(ready.listingError, 'error');
        } else {
          setError(ready.listingError || 'No Fusion hub is available.');
        }
      } catch (err) {
        sendJsLog('error', 'Palette ready failed', { message: errorMessage(err, 'unknown') });
        if (!cancelled) setError(errorMessage(err, 'Could not reach Fusion.'));
      } finally {
        if (!cancelled) {
          setLoading(false);
          window.setTimeout(() => document.getElementById('fx-search')?.focus(), 0);
        }
      }
    })();

    const offActive = onEvent('activeFileChanged', (raw) => {
      try {
        const data = JSON.parse(raw) as ActiveFilePayload;
        setActiveFileId(data.activeFileId || '');
      } catch {
        // Ignore a malformed push from the add-in.
      }
    });
    const offSearch = onEvent('searchProgress', (raw) => {
      try {
        applySearchProgress(JSON.parse(raw) as SearchProgress);
      } catch {
        // Ignore a malformed push from the add-in.
      }
    });

    return () => {
      cancelled = true;
      offActive();
      offSearch();
    };
  }, [applyListing, applySearchProgress, showToast]);

  const projectId = crumbs.find((crumb) => crumb.kind === 'project')?.id ?? '';

  useEffect(() => {
    const previous = searchRef.current;
    searchRef.current = '';
    if (previous) {
      void request('search:cancel', { searchId: previous }).catch(() => {
        // The walk may already have finished.
      });
    }
    setProjectMatches([]);
    setSearchTruncated(false);
    setIndexing(false);
    const needle = activeQuery.trim();
    if (!needle || !projectId) {
      setSearching(false);
      return;
    }
    setSearching(true);
    const searchId = newSearchId();
    searchRef.current = searchId;
    void request<SearchStartPayload>('search:start', { searchId, query: needle, projectId })
      .then((result) => {
        if (result?.progress) applySearchProgress(result.progress);
      })
      .catch((err) => {
        if (searchRef.current !== searchId) return;
        setSearching(false);
        showToast(errorMessage(err, 'Search failed.'), 'error');
      });
  }, [projectId, activeQuery, searchEpoch, applySearchProgress, showToast]);

  const needle = activeQuery.trim().toLowerCase();
  const localRows = needle ? children.filter((node) => node.name.toLowerCase().includes(needle)) : children;
  const childIds = useMemo(() => new Set(children.map((node) => node.id)), [children]);
  const otherRows = needle
    ? sortNodes(projectMatches.filter((node) => !childIds.has(node.id) && node.name.toLowerCase().includes(needle)))
    : [];
  const sections: FileSection[] = needle
    ? [
        { id: 'here', title: 'In this folder', rows: localRows },
        {
          id: 'project',
          title: indexing ? 'In this project, indexing' : searching ? 'In this project' : searchTruncated ? 'In this project, partial' : 'In this project',
          rows: otherRows,
        },
      ]
    : [{ id: 'all', title: '', rows: children }];
  const visibleRows = sections.flatMap((section) => section.rows);
  rowsRef.current = visibleRows;

  const selected = useMemo(
    () => visibleRows.find((node) => node.id === selectedId) ?? children.find((node) => node.id === selectedId) ?? null,
    [children, selectedId, visibleRows]
  );
  const detailFile = selected?.kind === 'file' ? selected : null;

  useEffect(() => {
    if (!detailFile) {
      setDetail(null);
      return;
    }
    const cached = refCache.current.get(detailFile.id);
    if (cached) {
      setDetail({ fileId: detailFile.id, status: 'ready', data: cached, message: '' });
      return;
    }
    let cancelled = false;
    setDetail({ fileId: detailFile.id, status: 'loading', data: null, message: '' });
    const timer = window.setTimeout(() => {
      void request<ReferencesPayload>('file:references', { id: detailFile.id })
        .then((data) => {
          if (cancelled) return;
          refCache.current.set(detailFile.id, data);
          setDetail({ fileId: detailFile.id, status: 'ready', data, message: '' });
        })
        .catch((err) => {
          if (cancelled) return;
          setDetail({
            fileId: detailFile.id,
            status: 'error',
            data: null,
            message: errorMessage(err, 'Could not load references.'),
          });
        });
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [detailFile, detailNonce]);

  useEffect(() => {
    if (!selectedId) return;
    document.getElementById(`fx-row-${selectedId}`)?.scrollIntoView({ block: 'nearest' });
  }, [selectedId, children, projectMatches]);

  const openNode = useCallback(
    (node: ExplorerNode) => {
      if (node.kind === 'file') {
        setSelectedId(node.id);
        void request('file:open', { id: node.id })
          .then(() => setActiveFileId(node.id))
          .catch((err) => showToast(errorMessage(err, 'Could not open that file.'), 'error'));
        return;
      }
      if (node.kind === 'hub') setActiveHubId(node.id);
      void load(node);
    },
    [load, showToast]
  );
  openNodeRef.current = openNode;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null;
      const typing = !!target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT');
      const searchFocused = target?.id === 'fx-search';

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'f') {
        event.preventDefault();
        document.getElementById('fx-search')?.focus();
        return;
      }

      if (event.key === 'Escape' && (confirmNode || moveNode)) {
        event.preventDefault();
        setConfirmNode(null);
        setMoveNode(null);
        return;
      }
      if (confirmNode || moveNode) return;

      if (event.key === 'Escape') {
        if (typing && !searchFocused) return;
        if (selectedRef.current) {
          event.preventDefault();
          setSelectedId('');
          return;
        }
        if (queryRef.current || activeQueryRef.current) {
          event.preventDefault();
          setQuery('');
          setActiveQuery('');
        }
        return;
      }

      if (typing && !searchFocused) return;

      const rows = rowsRef.current;
      const index = rows.findIndex((row) => row.id === selectedRef.current);

      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        if (!rows.length) return;
        event.preventDefault();
        const nextIndex =
          event.key === 'ArrowDown'
            ? Math.min(rows.length - 1, index < 0 ? 0 : index + 1)
            : Math.max(0, index < 0 ? 0 : index - 1);
        setSelectedId(rows[nextIndex].id);
        return;
      }

      if (event.key === 'Enter' && index >= 0) {
        event.preventDefault();
        openNodeRef.current(rows[index]);
        return;
      }

      if (event.key === 'F2' && index >= 0) {
        const node = rows[index];
        if (node.kind === 'file' || node.kind === 'folder') {
          event.preventDefault();
          skipRenameCommit.current = false;
          setCreating(false);
          setRenameId(node.id);
          setSelectedId(node.id);
        }
        return;
      }

      if (event.key === 'Delete' && index >= 0) {
        const node = rows[index];
        if (node.kind === 'file' || node.kind === 'folder') {
          event.preventDefault();
          setConfirmNode(node);
        }
        return;
      }

      if (event.key === 'Backspace' && (!searchFocused || !queryRef.current)) {
        const trail = crumbsRef.current;
        if (trail.length > 1) {
          event.preventDefault();
          openNodeRef.current(trail[trail.length - 2]);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [confirmNode, moveNode]);

  async function commitRename(node: ExplorerNode, name: string) {
    if (skipRenameCommit.current) {
      skipRenameCommit.current = false;
      return;
    }
    const trimmed = name.trim();
    setRenameId('');
    if (!trimmed || trimmed === node.name) return;
    try {
      await request('item:rename', { id: node.id, kind: node.kind, name: trimmed });
      refCache.current.delete(node.id);
      showToast(`Renamed to ${trimmed}`, 'success');
      setSearchEpoch((value) => value + 1);
      if (locationRef.current) await load(locationRef.current, { selectId: node.id, keepQuery: true });
    } catch (err) {
      showToast(errorMessage(err, 'Fusion could not rename that.'), 'error');
    }
  }

  async function commitCreate(name: string) {
    const parent = locationRef.current;
    const trimmed = name.trim();
    if (!parent || !trimmed) {
      setCreating(false);
      return;
    }
    try {
      const created = await request<ExplorerNode>('folder:create', {
        parentId: parent.id,
        parentKind: parent.kind,
        name: trimmed,
      });
      setCreating(false);
      showToast(`Created ${created.name}`, 'success');
      setSearchEpoch((value) => value + 1);
      await load(parent, { selectId: created.id, keepQuery: true });
    } catch (err) {
      showToast(errorMessage(err, 'Fusion could not create that folder.'), 'error');
    }
  }

  async function confirmDelete() {
    const node = confirmNode;
    const parent = locationRef.current;
    if (!node || !parent) return;
    setConfirmBusy(true);
    try {
      await request('item:delete', { id: node.id, kind: node.kind });
      refCache.current.delete(node.id);
      if (selectedRef.current === node.id) setSelectedId('');
      setConfirmNode(null);
      showToast(`Deleted ${node.name}`, 'success');
      setSearchEpoch((value) => value + 1);
      await load(parent, { keepQuery: true });
    } catch (err) {
      setConfirmNode(null);
      showToast(errorMessage(err, 'Fusion could not delete that.'), 'error');
    } finally {
      setConfirmBusy(false);
    }
  }

  async function insertNode(node: ExplorerNode) {
    if (inserting) return;
    if (node.extension !== 'f3d') {
      showToast('Only Fusion designs can be inserted.', 'error');
      return;
    }
    if (node.id === activeFileId) {
      showToast('A design cannot be inserted into itself.', 'error');
      return;
    }
    setInserting(true);
    try {
      const result = await request<{ inserted: boolean; name: string }>('file:insert', { id: node.id });
      showToast(`Inserted ${result.name || node.name}`, 'success');
    } catch (err) {
      showToast(errorMessage(err, 'Fusion could not insert that design.'), 'error');
    } finally {
      setInserting(false);
    }
  }

  async function revealActive() {
    try {
      const result = await request<ActiveFileLocation>('nav:activeFile');
      loadSeq.current += 1;
      applyListing(result.listing);
      setQuery('');
      setActiveQuery('');
      setSelectedId(result.fileId);
      setActiveFileId(result.fileId);
      setRenameId('');
      setCreating(false);
      setLoading(false);
    } catch (err) {
      showToast(errorMessage(err, 'The open design is not in a project yet.'), 'error');
    }
  }

  function retryReferences() {
    if (!detailFile) return;
    refCache.current.delete(detailFile.id);
    setDetailNonce((value) => value + 1);
  }

  const canCreate = location?.kind === 'project' || location?.kind === 'folder';
  const title = location?.name || 'File Explorer';
  let emptyTitle = 'Empty folder';
  let emptyMessage = 'This folder does not have any files yet.';
  if (needle && indexing) {
    emptyTitle = 'Indexing';
    emptyMessage = 'Reading this project in the background. Matches show up as each folder is indexed.';
  } else if (needle && searching) {
    emptyTitle = 'Searching';
    emptyMessage = 'Looking through the project index.';
  } else if (needle) {
    emptyTitle = 'No matches';
    emptyMessage = `Nothing in this project is named “${activeQuery.trim()}”.`;
  } else if (location?.kind === 'hub') {
    emptyTitle = 'No projects';
    emptyMessage = 'This hub does not have any projects yet.';
  }

  return (
    <div id="fx-app">
      {loading && <div id="fx-progress" className="fx-progress" />}
      <Toolbar
        hubs={hubs}
        activeHubId={activeHubId}
        query={query}
        canCreate={canCreate}
        onHub={(id) => {
          setActiveHubId(id);
          const hub = hubs.find((item) => item.id === id);
          if (hub) void load(hub);
        }}
        onQuery={setQuery}
        onSearch={() => {
          const next = query.trim();
          setQuery(next);
          setActiveQuery(next);
          setSearchEpoch((value) => value + 1);
        }}
        onClear={() => {
          setQuery('');
          setActiveQuery('');
        }}
        onCreate={() => {
          setRenameId('');
          setCreating(true);
        }}
        onRefresh={() => {
          if (location) void load(location, { selectId: selectedId, keepQuery: true, refresh: true });
        }}
        onRevealActive={() => void revealActive()}
      />
      {location && <Breadcrumb crumbs={crumbs} onOpen={openNode} />}
      {!location && error && (
        <div id="fx-boot-error" className="fx-empty">
          <p id="fx-boot-error-title" className="fx-emptyTitle">
            Could not open the hub
          </p>
          <p id="fx-boot-error-message" className="fx-emptyMessage">
            {error}
          </p>
          <button id="fx-boot-retry" type="button" className="fx-primaryButton" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      )}
      {location && (
        <FileList
          sections={sections}
          selectedId={selectedId}
          activeFileId={activeFileId}
          renameId={renameId}
          creating={creating}
          loading={loading}
          emptyTitle={emptyTitle}
          emptyMessage={emptyMessage}
          onSelect={(node) => {
            setSelectedId(node.id);
            setRenameId('');
          }}
          onOpen={openNode}
          onRenameStart={(node) => {
            skipRenameCommit.current = false;
            setCreating(false);
            setSelectedId(node.id);
            setRenameId(node.id);
          }}
          onRenameCommit={(node, name) => void commitRename(node, name)}
          onRenameCancel={() => {
            skipRenameCommit.current = true;
            setRenameId('');
          }}
          onWhereUsed={(node) => setSelectedId(node.id)}
          onInsert={(node) => void insertNode(node)}
          inserting={inserting}
          onMove={(node) => {
            setSelectedId(node.id);
            setMoveNode(node);
          }}
          onDelete={(node) => {
            setSelectedId(node.id);
            setConfirmNode(node);
          }}
          onCreate={(name) => void commitCreate(name)}
          onCancelCreate={() => setCreating(false)}
        />
      )}
      {!location && loading && (
        <div id="fx-boot-skeletons" className="fx-skeletons" aria-hidden="true">
          {Array.from({ length: 7 }, (_, index) => (
            <div id={`fx-boot-skeleton-${index}`} key={index} className="fx-skeleton" />
          ))}
        </div>
      )}
      {detailFile && (
        <DetailPanel
          file={detailFile}
          status={detail && detail.fileId === detailFile.id ? detail.status : 'loading'}
          data={detail && detail.fileId === detailFile.id ? detail.data : null}
          message={detail && detail.fileId === detailFile.id ? detail.message : ''}
          onClose={() => setSelectedId('')}
          onOpen={openNode}
          onInsert={(node) => void insertNode(node)}
          canInsert={detailFile.extension === 'f3d' && detailFile.id !== activeFileId}
          inserting={inserting}
          activeFileId={activeFileId}
          onReveal={(node) => {
            if (!node.parentId) {
              showToast('That file does not have a folder to show.', 'error');
              return;
            }
            void load({ id: node.parentId, kind: 'folder' }, { selectId: node.id });
          }}
          onRetry={retryReferences}
        />
      )}
      {!detailFile && location && (
        <footer id="fx-hints">
          <span id="fx-hint-keys">Enter open · F2 rename · Del delete · Backspace up</span>
          {indexing && <span id="fx-hint-search">Indexing project…</span>}
          {searching && !indexing && <span id="fx-hint-search">Searching…</span>}
          {searchTruncated && !indexing && <span id="fx-hint-truncated">Index is partial</span>}
        </footer>
      )}
      {confirmNode && (
        <ConfirmDialog
          node={confirmNode}
          usedByCount={refCache.current.get(confirmNode.id)?.parents.length ?? 0}
          busy={confirmBusy}
          onCancel={() => setConfirmNode(null)}
          onConfirm={() => void confirmDelete()}
        />
      )}
      {moveNode && (
        <MoveDialog
          file={moveNode}
          projectId={moveNode.projectId || projectId}
          onClose={() => setMoveNode(null)}
          onMoved={() => {
            const parent = locationRef.current;
            showToast(`Moved ${moveNode.name}`, 'success');
            refCache.current.delete(moveNode.id);
            setSearchEpoch((value) => value + 1);
            setMoveNode(null);
            if (parent) void load(parent, { selectId: moveNode.id, keepQuery: true });
          }}
        />
      )}
    </div>
  );
}

function dedupe(nodes: ExplorerNode[]): ExplorerNode[] {
  const byId = new Map<string, ExplorerNode>();
  nodes.forEach((node) => byId.set(node.id, node));
  return Array.from(byId.values());
}
