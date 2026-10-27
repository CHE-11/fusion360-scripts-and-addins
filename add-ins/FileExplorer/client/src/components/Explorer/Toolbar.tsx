import type { ExplorerNode } from '../../types/types';

type Props = {
  hubs: ExplorerNode[];
  activeHubId: string;
  query: string;
  canCreate: boolean;
  onHub: (id: string) => void;
  onQuery: (value: string) => void;
  onCreate: () => void;
  onRefresh: () => void;
  onRevealActive: () => void;
};

export function Toolbar({
  hubs,
  activeHubId,
  query,
  canCreate,
  onHub,
  onQuery,
  onCreate,
  onRefresh,
  onRevealActive,
}: Props) {
  return (
    <div id="fx-toolbar">
      <div id="fx-toolbar-row" className="fx-toolbarRow">
        <label id="fx-hub-label" className="fx-hubLabel">
          <span id="fx-hub-caption" className="fx-hubCaption">
            Hub
          </span>
          <select
            id="fx-hub-select"
            className="fx-hubSelect"
            value={activeHubId}
            onChange={(event) => onHub(event.target.value)}
          >
            {hubs.map((hub) => (
              <option id={`fx-hub-option-${hub.id}`} key={hub.id} value={hub.id}>
                {hub.name}
              </option>
            ))}
          </select>
        </label>
        <div id="fx-toolbar-actions" className="fx-toolbarActions">
          <button id="fx-reveal-active" type="button" className="fx-tool" onClick={onRevealActive} title="Show the open design">
            Open design
          </button>
          <button
            id="fx-new-folder"
            type="button"
            className="fx-tool"
            onClick={onCreate}
            disabled={!canCreate}
            title="New folder"
          >
            New folder
          </button>
          <button id="fx-refresh" type="button" className="fx-iconButton" onClick={onRefresh} title="Refresh" aria-label="Refresh">
            <RefreshIcon />
          </button>
        </div>
      </div>
      <div id="fx-search-label" className="fx-search">
        <SearchIcon />
        <input
          id="fx-search"
          className="fx-searchInput"
          value={query}
          placeholder="Search this project"
          aria-label="Search this project"
          onChange={(event) => onQuery(event.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        {query && (
          <button id="fx-search-clear" type="button" className="fx-searchClear" onClick={() => onQuery('')} aria-label="Clear search">
            Clear
          </button>
        )}
      </div>
    </div>
  );
}

function SearchIcon() {
  return (
    <svg id="fx-search-icon" className="fx-searchIcon" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="8.5" cy="8.5" r="4.6" />
      <path d="M12.2 12.2 16.2 16.2" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg id="fx-refresh-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M15.6 10a5.6 5.6 0 1 1-1.5-3.8" />
      <path d="M14.2 3.6v3.2h-3.2" />
    </svg>
  );
}
