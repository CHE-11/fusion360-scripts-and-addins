import type { ExplorerNode } from '../../types/types';

type Props = {
  crumbs: ExplorerNode[];
  onOpen: (node: ExplorerNode) => void;
};

export function Breadcrumb({ crumbs, onOpen }: Props) {
  if (!crumbs.length) return null;
  return (
    <nav id="fx-crumbs" aria-label="Folder path">
      {crumbs.map((crumb, index) => {
        const current = index === crumbs.length - 1;
        return (
          <span id={`fx-crumb-wrap-${crumb.id}`} key={crumb.id} className="fx-crumbWrap">
            {index > 0 && (
              <span id={`fx-crumb-sep-${crumb.id}`} className="fx-crumbSep" aria-hidden="true">
                /
              </span>
            )}
            <button
              id={`fx-crumb-${crumb.id}`}
              type="button"
              className={current ? 'fx-crumb fx-crumbCurrent' : 'fx-crumb'}
              onClick={() => onOpen(crumb)}
              title={crumb.name}
            >
              {crumb.name}
            </button>
          </span>
        );
      })}
    </nav>
  );
}
