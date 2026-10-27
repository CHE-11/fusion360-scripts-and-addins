import { useEffect } from 'react';

import { FileTypeIcon, iconKind } from '../icons/FileIcons';
import type { ExplorerNode } from '../../types/types';
import { relativeTime } from '../../utils/nodes';

type Props = {
  node: ExplorerNode;
  selected: boolean;
  active: boolean;
  renaming: boolean;
  onSelect: (node: ExplorerNode) => void;
  onOpen: (node: ExplorerNode) => void;
  onRenameStart: (node: ExplorerNode) => void;
  onRenameCommit: (node: ExplorerNode, name: string) => void;
  onRenameCancel: () => void;
  onWhereUsed: (node: ExplorerNode) => void;
  onInsert: (node: ExplorerNode) => void;
  onMove: (node: ExplorerNode) => void;
  onDelete: (node: ExplorerNode) => void;
  inserting: boolean;
};

export function FileRow({
  node,
  selected,
  active,
  renaming,
  onSelect,
  onOpen,
  onRenameStart,
  onRenameCommit,
  onRenameCancel,
  onWhereUsed,
  onInsert,
  onMove,
  onDelete,
  inserting,
}: Props) {
  const canEdit = node.kind === 'file' || node.kind === 'folder';
  return (
    <li
      id={`fx-row-${node.id}`}
      className={selected ? 'fx-row fx-rowSelected' : 'fx-row'}
      role="option"
      aria-selected={selected}
    >
      {renaming ? (
        <RenameField node={node} onCommit={onRenameCommit} onCancel={onRenameCancel} />
      ) : (
        <button
          id={`fx-open-${node.id}`}
          type="button"
          className="fx-rowMain"
          onClick={() => onSelect(node)}
          onDoubleClick={() => onOpen(node)}
          title={node.extension ? `${node.name}.${node.extension}` : node.name}
        >
          <FileTypeIcon id={`fx-icon-${node.id}`} kind={iconKind(node)} />
          <span id={`fx-name-${node.id}`} className="fx-name">
            {node.name}
            {node.extension && (
              <span id={`fx-ext-${node.id}`} className="fx-ext">
                .{node.extension}
              </span>
            )}
          </span>
          {active && (
            <span id={`fx-open-pill-${node.id}`} className="fx-pill">
              Open
            </span>
          )}
          {node.version != null && (
            <span id={`fx-version-${node.id}`} className="fx-version">
              v{node.version}
            </span>
          )}
          {node.modifiedAt != null && (
            <span id={`fx-time-${node.id}`} className="fx-time">
              {relativeTime(node.modifiedAt)}
            </span>
          )}
        </button>
      )}
      {canEdit && !renaming && (
        <div id={`fx-actions-${node.id}`} className="fx-actions">
          {node.kind === 'file' && node.extension === 'f3d' && !active && (
            <button
              id={`fx-insert-${node.id}`}
              type="button"
              className="fx-action"
              title="Insert into the open design"
              aria-label={`Insert ${node.name} into the open design`}
              onClick={() => onInsert(node)}
              disabled={inserting}
            >
              <InsertIcon />
            </button>
          )}
          {node.kind === 'file' && (
            <button
              id={`fx-where-${node.id}`}
              type="button"
              className="fx-action"
              title="Show where used"
              aria-label={`Show where ${node.name} is used`}
              onClick={() => onWhereUsed(node)}
            >
              <WhereIcon />
            </button>
          )}
          <button
            id={`fx-rename-${node.id}`}
            type="button"
            className="fx-action"
            title="Rename"
            aria-label={`Rename ${node.name}`}
            onClick={() => onRenameStart(node)}
          >
            <PencilIcon />
          </button>
          {node.kind === 'file' && (
            <button
              id={`fx-move-${node.id}`}
              type="button"
              className="fx-action"
              title="Move"
              aria-label={`Move ${node.name}`}
              onClick={() => onMove(node)}
            >
              <MoveIcon />
            </button>
          )}
          <button
            id={`fx-delete-${node.id}`}
            type="button"
            className="fx-action fx-actionDanger"
            title="Delete"
            aria-label={`Delete ${node.name}`}
            onClick={() => onDelete(node)}
          >
            <TrashIcon />
          </button>
        </div>
      )}
    </li>
  );
}

function RenameField({
  node,
  onCommit,
  onCancel,
}: {
  node: ExplorerNode;
  onCommit: (node: ExplorerNode, name: string) => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const input = document.getElementById(`fx-rename-input-${node.id}`) as HTMLInputElement | null;
    input?.focus();
    input?.select();
  }, [node.id]);

  return (
    <form
      id={`fx-rename-form-${node.id}`}
      className="fx-renameForm"
      onSubmit={(event) => {
        event.preventDefault();
        const input = document.getElementById(`fx-rename-input-${node.id}`) as HTMLInputElement | null;
        onCommit(node, input?.value ?? '');
      }}
    >
      <FileTypeIcon id={`fx-rename-icon-${node.id}`} kind={iconKind(node)} />
      <input
        id={`fx-rename-input-${node.id}`}
        className="fx-renameInput"
        defaultValue={node.name}
        aria-label={`Rename ${node.name}`}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            onCancel();
          }
        }}
        onBlur={(event) => {
          if (event.relatedTarget instanceof HTMLElement && event.relatedTarget.id === `fx-rename-cancel-${node.id}`) {
            return;
          }
          onCommit(node, event.currentTarget.value);
        }}
      />
      <button id={`fx-rename-cancel-${node.id}`} type="button" className="fx-renameCancel" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}

function InsertIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M10 3.4v4.2" />
      <path d="M8.1 5.6 10 7.6l1.9-2" />
      <path d="M5.2 8.4h9.6v7.4H5.2z" />
    </svg>
  );
}

function WhereIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="7" cy="10" r="2.2" />
      <circle cx="13.4" cy="6.2" r="2.2" />
      <circle cx="13.4" cy="13.8" r="2.2" />
      <path d="M9 9.2 11.4 7.2M9 10.8l2.4 2" />
    </svg>
  );
}

function PencilIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M11.2 4.8 15.2 8.8 7.6 16.4 3.6 16.6 3.8 12.6 11.2 4.8Z" />
      <path d="M10.2 5.8 14.2 9.8" />
    </svg>
  );
}

function MoveIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M4 7.2h7.2" />
      <path d="M8.6 4.6 11.4 7.2 8.6 9.8" />
      <path d="M4.6 5.2V4.4c0-.5.4-.9.9-.9h8.6c.5 0 .9.4.9.9v8.2c0 .5-.4.9-.9.9H8.2" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M5.2 6.4h9.6" />
      <path d="M8 6.2V4.8h4v1.4" />
      <path d="M6.4 6.4 7 15.2h6l.6-8.8" />
    </svg>
  );
}
