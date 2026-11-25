import { IconBox, IconCylinder, IconPolygon, IconStack2, IconX } from '@tabler/icons-react';
import { forwardRef } from 'react';

import type { ListMode } from '../types/types';

type FilterBarProps = {
  query: string;
  mode: ListMode;
  disabled: boolean;
  onQuery: (value: string) => void;
  onMode: (mode: ListMode) => void;
};

const CHIPS: { mode: ListMode; label: string; Icon: typeof IconBox }[] = [
  { mode: 'component', label: 'Component', Icon: IconBox },
  { mode: 'body', label: 'Body', Icon: IconCylinder },
  { mode: 'assembly', label: 'Assembly', Icon: IconStack2 },
  { mode: 'face', label: 'Faces', Icon: IconPolygon },
];

export const FilterBar = forwardRef<HTMLInputElement, FilterBarProps>(function FilterBar(
  { query, mode, disabled, onQuery, onMode },
  inputRef
) {
  return (
    <div id="sbl-filter-bar" className="sbl-filterBar">
      <div id="sbl-filter-input-wrap" className="sbl-filterInputWrap">
        <input
          id="sbl-filter-input"
          ref={inputRef}
          className="sbl-filterInput"
          type="text"
          placeholder="Filter by name..."
          value={query}
          disabled={disabled}
          onChange={(event) => onQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') onQuery('');
          }}
          spellCheck={false}
        />
        {query && (
          <button id="sbl-filter-clear" type="button" className="sbl-filterClear" onClick={() => onQuery('')} title="Clear filter">
            <IconX id="sbl-filter-clear-icon" size={12} />
          </button>
        )}
      </div>
      <div id="sbl-filter-chips" className="sbl-chips" role="tablist">
        {CHIPS.map(({ mode: chipMode, label, Icon }) => (
          <button
            key={chipMode}
            id={`sbl-chip-${chipMode}`}
            type="button"
            role="tab"
            aria-selected={mode === chipMode}
            className={`sbl-chip sbl-chip-${chipMode}${mode === chipMode ? ' sbl-chipActive' : ''}`}
            disabled={disabled}
            onClick={() => onMode(chipMode)}
            title={chipMode === 'face' ? 'Faces of the checked items, or of every visible body' : `Show ${label.toLowerCase()} items`}
          >
            <Icon id={`sbl-chip-icon-${chipMode}`} size={13} />
            {label}
          </button>
        ))}
      </div>
    </div>
  );
});
