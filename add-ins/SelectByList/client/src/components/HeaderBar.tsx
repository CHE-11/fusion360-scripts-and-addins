import { IconListCheck, IconRefresh } from '@tabler/icons-react';

import type { SortOrder } from '../types/types';

type HeaderBarProps = {
  sort: SortOrder;
  loading: boolean;
  disabled: boolean;
  onRefresh: () => void;
  onCheckAll: () => void;
  onCheckNone: () => void;
  onToggleSort: () => void;
};

export function HeaderBar({ sort, loading, disabled, onRefresh, onCheckAll, onCheckNone, onToggleSort }: HeaderBarProps) {
  const nextSort = sort === 'az' ? 'Browser' : 'A-Z';
  return (
    <header id="sbl-header" className="sbl-header">
      <div id="sbl-header-title" className="sbl-headerTitle">
        <IconListCheck id="sbl-header-icon" size={16} stroke={2} />
        <span id="sbl-header-text">Select By List</span>
      </div>
      <div id="sbl-header-actions" className="sbl-headerActions">
        <button
          id="sbl-refresh-button"
          type="button"
          className={`sbl-btn sbl-btnGhost${loading ? ' sbl-spinning' : ''}`}
          onClick={onRefresh}
          title="Reload the list from the design"
        >
          <IconRefresh id="sbl-refresh-icon" size={13} />
          Refresh
        </button>
        <button id="sbl-check-all-button" type="button" className="sbl-btn sbl-btnGhost" onClick={onCheckAll} disabled={disabled} title="Check every item in the list">
          All
        </button>
        <button id="sbl-check-none-button" type="button" className="sbl-btn sbl-btnGhost" onClick={onCheckNone} disabled={disabled} title="Uncheck everything">
          None
        </button>
        <button
          id="sbl-sort-toggle"
          type="button"
          className="sbl-btn sbl-btnAccentOutline"
          onClick={onToggleSort}
          title={sort === 'az' ? 'Sorted A-Z. Click for Fusion browser order.' : 'In browser order. Click to sort A-Z.'}
        >
          {nextSort}
        </button>
      </div>
    </header>
  );
}
