import { useEffect } from 'react';

import type { ExplorerNode } from '../../types/types';

type Props = {
  node: ExplorerNode;
  usedByCount: number;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({ node, usedByCount, busy, onCancel, onConfirm }: Props) {
  useEffect(() => {
    document.getElementById('fx-confirm-cancel')?.focus();
  }, []);

  const title = node.kind === 'folder' ? `Delete folder “${node.name}”?` : `Delete “${node.name}”?`;
  let message = 'This removes it from the project. Fusion cannot undo the delete.';
  if (node.kind === 'folder') {
    message = 'Fusion only deletes empty folders. Files inside have to be moved or deleted first.';
  } else if (node.hasParents || usedByCount > 0) {
    message = 'Other designs use this file. Deleting it can break those references.';
  }

  return (
    <div id="fx-confirm-overlay" className="fx-overlay">
      <div id="fx-confirm" className="fx-dialog" role="dialog" aria-modal="true" aria-labelledby="fx-confirm-title">
        <h2 id="fx-confirm-title">{title}</h2>
        <p id="fx-confirm-message">{message}</p>
        <div id="fx-confirm-actions" className="fx-dialogActions">
          <button id="fx-confirm-cancel" type="button" className="fx-textButton" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button id="fx-confirm-delete" type="button" className="fx-dangerButton" onClick={onConfirm} disabled={busy}>
            {busy ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}
