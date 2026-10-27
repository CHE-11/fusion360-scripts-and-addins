import { useEffect } from 'react';

import type { ExplorerNode } from '../../types/types';
import { FileRow } from './FileRow';

export type FileSection = {
  id: string;
  title: string;
  rows: ExplorerNode[];
};

type Props = {
  sections: FileSection[];
  selectedId: string;
  activeFileId: string;
  renameId: string;
  creating: boolean;
  loading: boolean;
  emptyTitle: string;
  emptyMessage: string;
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
  onCreate: (name: string) => void;
  onCancelCreate: () => void;
};

export function FileList({
  sections,
  selectedId,
  activeFileId,
  renameId,
  creating,
  loading,
  emptyTitle,
  emptyMessage,
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
  onCreate,
  onCancelCreate,
}: Props) {
  const hasRows = sections.some((section) => section.rows.length > 0);
  return (
    <div id="fx-list-wrap" className={loading ? 'fx-listWrap fx-listBusy' : 'fx-listWrap'}>
      {loading && !hasRows && <Skeletons />}
      {creating && <CreateRow onCreate={onCreate} onCancel={onCancelCreate} />}
      {!hasRows && !loading && !creating && (
        <div id="fx-empty" className="fx-empty">
          <p id="fx-empty-title" className="fx-emptyTitle">
            {emptyTitle}
          </p>
          <p id="fx-empty-message" className="fx-emptyMessage">
            {emptyMessage}
          </p>
        </div>
      )}
      {hasRows && (
        <div id="fx-list" role="listbox" aria-label="Project files">
          {sections.map((section) =>
            section.rows.length ? (
              <section id={`fx-section-${section.id}`} key={section.id} className="fx-section">
                {section.title && (
                  <h2 id={`fx-section-title-${section.id}`} className="fx-sectionTitle">
                    {section.title}
                  </h2>
                )}
                <ul id={`fx-section-rows-${section.id}`} className="fx-rows">
                  {section.rows.map((node) => (
                    <FileRow
                      key={node.id}
                      node={node}
                      selected={node.id === selectedId}
                      active={node.kind === 'file' && node.id === activeFileId}
                      renaming={node.id === renameId}
                      onSelect={onSelect}
                      onOpen={onOpen}
                      onRenameStart={onRenameStart}
                      onRenameCommit={onRenameCommit}
                      onRenameCancel={onRenameCancel}
                      onWhereUsed={onWhereUsed}
                      onInsert={onInsert}
                      onMove={onMove}
                      onDelete={onDelete}
                      inserting={inserting}
                    />
                  ))}
                </ul>
              </section>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}

function CreateRow({ onCreate, onCancel }: { onCreate: (name: string) => void; onCancel: () => void }) {
  useEffect(() => {
    const input = document.getElementById('fx-create-input') as HTMLInputElement | null;
    input?.focus();
  }, []);

  return (
    <form
      id="fx-create-form"
      className="fx-createForm"
      onSubmit={(event) => {
        event.preventDefault();
        const input = document.getElementById('fx-create-input') as HTMLInputElement | null;
        onCreate(input?.value ?? '');
      }}
    >
      <span id="fx-create-icon" className="fx-icon fx-icon-folder" aria-hidden="true">
        <svg viewBox="0 0 20 20">
          <path d="M3.2 7.2c0-.7.6-1.3 1.3-1.3h3.1l1.3 1.4h6.6c.7 0 1.3.6 1.3 1.3v6c0 .7-.6 1.3-1.3 1.3H4.5c-.7 0-1.3-.6-1.3-1.3V7.2Z" />
        </svg>
      </span>
      <input
        id="fx-create-input"
        className="fx-renameInput"
        placeholder="Folder name"
        aria-label="New folder name"
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            onCancel();
          }
        }}
      />
      <button id="fx-create-save" type="submit" className="fx-textButton">
        Create
      </button>
      <button id="fx-create-cancel" type="button" className="fx-renameCancel" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}

function Skeletons() {
  return (
    <div id="fx-skeletons" className="fx-skeletons" aria-hidden="true">
      {Array.from({ length: 7 }, (_, index) => (
        <div id={`fx-skeleton-${index}`} key={index} className="fx-skeleton" />
      ))}
    </div>
  );
}
