import { useEffect, useRef, useState, type FormEvent } from 'react';

import type { ListItem } from '../types/types';
import { KIND_LABELS } from '../utils/items';

type RenameDialogProps = {
  item: ListItem;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (name: string) => void;
};

function editableName(item: ListItem) {
  if (item.kind === 'component' || item.kind === 'assembly') return item.name.replace(/:\d+$/, '');
  return item.name;
}

export function RenameDialog({ item, busy, onCancel, onSubmit }: RenameDialogProps) {
  const [value, setValue] = useState(() => editableName(item));
  const inputRef = useRef<HTMLInputElement>(null);
  const isOccurrence = item.kind === 'component' || item.kind === 'assembly';

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const name = value.trim();
    if (!name || busy) return;
    onSubmit(name);
  };

  return (
    <div id="sbl-rename-overlay" className="sbl-overlay" onMouseDown={onCancel}>
      <form id="sbl-rename-dialog" className="sbl-dialog" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <div id="sbl-rename-title" className="sbl-dialogTitle">
          Rename {KIND_LABELS[item.kind].toLowerCase()}
        </div>
        <div id="sbl-rename-current" className="sbl-dialogHint">
          {item.name}
        </div>
        <input
          id="sbl-rename-input"
          ref={inputRef}
          className="sbl-filterInput sbl-dialogInput"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') onCancel();
          }}
          spellCheck={false}
        />
        {isOccurrence && (
          <div id="sbl-rename-note" className="sbl-dialogHint">
            Renames the component, so every copy of it updates.
          </div>
        )}
        <div id="sbl-rename-actions" className="sbl-dialogActions">
          <button id="sbl-rename-cancel" type="button" className="sbl-btn sbl-btnGhost" onClick={onCancel}>
            Cancel
          </button>
          <button id="sbl-rename-submit" type="submit" className="sbl-btn sbl-btnPrimary sbl-btnCompact" disabled={busy || !value.trim()}>
            Rename
          </button>
        </div>
      </form>
    </div>
  );
}
