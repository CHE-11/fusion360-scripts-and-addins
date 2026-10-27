import { useCallback, useEffect, useState } from 'react';

import { request } from '../../connector/fusionBridge';
import type { ExplorerNode, Listing } from '../../types/types';
import { errorMessage } from '../../utils/nodes';
import { FileTypeIcon } from '../icons/FileIcons';

type Props = {
  file: ExplorerNode;
  projectId: string;
  onClose: () => void;
  onMoved: () => void;
};

export function MoveDialog({ file, projectId, onClose, onMoved }: Props) {
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (target: { id: string; kind: ExplorerNode['kind'] }) => {
    setLoading(true);
    setError('');
    try {
      const next = await request<Listing>('folder:list', target);
      setListing(next);
    } catch (err) {
      setError(errorMessage(err, 'Could not open that folder.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load({ id: projectId, kind: 'project' });
  }, [load, projectId]);

  const folders = (listing?.children ?? []).filter((node) => node.kind === 'folder');
  const hereDisabled = busy || !listing || listing.containerId === file.parentId || listing.location.kind === 'hub';

  async function moveHere() {
    if (!listing || hereDisabled) return;
    setBusy(true);
    try {
      await request('file:move', { id: file.id, targetFolderId: listing.containerId });
      onMoved();
    } catch (err) {
      setError(errorMessage(err, 'Fusion could not move that file.'));
      setBusy(false);
    }
  }

  const crumbs = (listing?.crumbs ?? []).filter((crumb) => crumb.kind !== 'hub');

  return (
    <div id="fx-move-overlay" className="fx-overlay">
      <div id="fx-move" className="fx-dialog fx-moveDialog" role="dialog" aria-modal="true" aria-labelledby="fx-move-title">
        <h2 id="fx-move-title">Move “{file.name}”</h2>
        <p id="fx-move-hint" className="fx-dialogHint">
          Choose a folder in this project.
        </p>
        <nav id="fx-move-crumbs" className="fx-moveCrumbs" aria-label="Move destination">
          {crumbs.map((crumb, index) => (
            <span id={`fx-move-crumb-wrap-${crumb.id}`} key={crumb.id}>
              {index > 0 && <span className="fx-crumbSep">/</span>}
              <button id={`fx-move-crumb-${crumb.id}`} type="button" className="fx-crumb" onClick={() => void load(crumb)}>
                {crumb.name}
              </button>
            </span>
          ))}
        </nav>
        <div id="fx-move-list" className="fx-moveList">
          {loading && <p id="fx-move-loading" className="fx-detailNote">Loading folders…</p>}
          {!loading && error && <p id="fx-move-error" className="fx-detailNote">{error}</p>}
          {!loading && !error && !folders.length && (
            <p id="fx-move-empty" className="fx-detailNote">
              No folders here.
            </p>
          )}
          {!loading &&
            folders.map((folder) => (
              <button
                id={`fx-move-folder-${folder.id}`}
                key={folder.id}
                type="button"
                className="fx-moveFolder"
                onClick={() => void load(folder)}
              >
                <FileTypeIcon id={`fx-move-icon-${folder.id}`} kind="folder" />
                <span id={`fx-move-name-${folder.id}`}>{folder.name}</span>
              </button>
            ))}
        </div>
        <div id="fx-move-actions" className="fx-dialogActions">
          <button id="fx-move-cancel" type="button" className="fx-textButton" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button id="fx-move-here" type="button" className="fx-primaryButton" onClick={() => void moveHere()} disabled={hereDisabled}>
            {busy ? 'Moving…' : 'Move here'}
          </button>
        </div>
      </div>
    </div>
  );
}
