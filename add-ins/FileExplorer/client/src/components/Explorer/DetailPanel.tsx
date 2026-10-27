import { FileTypeIcon, iconKind } from '../icons/FileIcons';
import type { ExplorerNode, ReferencesPayload } from '../../types/types';
import { relativeTime } from '../../utils/nodes';

type Props = {
  file: ExplorerNode;
  status: 'loading' | 'ready' | 'error';
  data: ReferencesPayload | null;
  message: string;
  onClose: () => void;
  onOpen: (node: ExplorerNode) => void;
  onReveal: (node: ExplorerNode) => void;
  onRetry: () => void;
};

export function DetailPanel({ file, status, data, message, onClose, onOpen, onReveal, onRetry }: Props) {
  const meta = [
    file.extension ? file.extension.toUpperCase() : 'File',
    file.version != null ? `v${file.version}` : '',
    relativeTime(file.modifiedAt),
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <aside id="fx-detail" aria-label="Where used">
      <header id="fx-detail-header" className="fx-detailHeader">
        <FileTypeIcon id="fx-detail-icon" kind={iconKind(file)} />
        <div id="fx-detail-titles" className="fx-detailTitles">
          <h2 id="fx-detail-name">{file.name}</h2>
          <p id="fx-detail-meta">{meta}</p>
        </div>
        <button id="fx-detail-close" type="button" className="fx-textButton" onClick={onClose}>
          Close
        </button>
      </header>
      {status === 'loading' && (
        <p id="fx-detail-loading" className="fx-detailNote">
          Looking up references…
        </p>
      )}
      {status === 'error' && (
        <div id="fx-detail-error" className="fx-detailNote">
          <p id="fx-detail-error-message">{message}</p>
          <button id="fx-detail-retry" type="button" className="fx-textButton" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
      {status === 'ready' && data && (
        <div id="fx-detail-body" className="fx-detailBody">
          {data.warning && (
            <p id="fx-detail-warning" className="fx-detailNote">
              {data.warning}
            </p>
          )}
          <RefList id="used-in" title="Used in" empty="Nothing references this file." rows={data.parents} onOpen={onOpen} onReveal={onReveal} />
          <RefList id="uses" title="Uses" empty="This file does not reference other files." rows={data.children} onOpen={onOpen} onReveal={onReveal} />
        </div>
      )}
    </aside>
  );
}

function RefList({
  id,
  title,
  empty,
  rows,
  onOpen,
  onReveal,
}: {
  id: string;
  title: string;
  empty: string;
  rows: ExplorerNode[];
  onOpen: (node: ExplorerNode) => void;
  onReveal: (node: ExplorerNode) => void;
}) {
  return (
    <section id={`fx-refs-${id}`} className="fx-refs">
      <h3 id={`fx-refs-title-${id}`}>
        {title}
        <span id={`fx-refs-count-${id}`} className="fx-refCount">
          {rows.length}
        </span>
      </h3>
      {!rows.length && (
        <p id={`fx-refs-empty-${id}`} className="fx-refEmpty">
          {empty}
        </p>
      )}
      {rows.length > 0 && (
        <ul id={`fx-refs-list-${id}`} className="fx-refList">
          {rows.map((node) => (
            <li id={`fx-ref-${id}-${node.id}`} key={node.id} className="fx-refItem">
              <button
                id={`fx-ref-reveal-${id}-${node.id}`}
                type="button"
                className="fx-refMain"
                onClick={() => onReveal(node)}
                title="Show in folder"
              >
                <FileTypeIcon id={`fx-ref-icon-${id}-${node.id}`} kind={iconKind(node)} />
                <span id={`fx-ref-name-${id}-${node.id}`} className="fx-refName">
                  {node.name}
                  {node.extension && <span className="fx-ext">.{node.extension}</span>}
                </span>
              </button>
              <button
                id={`fx-ref-open-${id}-${node.id}`}
                type="button"
                className="fx-textButton"
                onClick={() => onOpen(node)}
              >
                Open
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
