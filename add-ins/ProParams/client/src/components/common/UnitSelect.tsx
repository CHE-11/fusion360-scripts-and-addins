import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';

import { IconCheck, IconChevronDown } from '@tabler/icons-react';

import { FUSION_UNITS, findUnit, resolveUnitQuery, searchUnits, type FusionUnit } from '../../data/fusionUnits';

type MenuBox = {
  top: number;
  left: number;
  width: number;
  maxHeight: number;
};

type Props = {
  id: string;
  value: string;
  disabled?: boolean;
  onChange: (unit: string) => void;
  onCommit?: () => void;
  onCancel?: () => void;
};

function optionDomId(id: string, symbol: string): string {
  const slug = symbol === '' ? 'unitless' : symbol.replace(/[^a-zA-Z0-9_-]/g, '_');
  return `${id}_opt_${slug}`;
}

function unitIndex(symbol: string): number {
  const index = FUSION_UNITS.findIndex((unit) => unit.symbol === symbol);
  return index >= 0 ? index : 0;
}

export function UnitSelect({ id, value, disabled = false, onChange, onCommit, onCancel }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [box, setBox] = useState<MenuBox | null>(null);

  const selected = findUnit(value);
  const results = useMemo(() => searchUnits(query ?? ''), [query]);
  const safeActive = results.length === 0 ? 0 : Math.min(active, results.length - 1);
  const grouped = query === null || query.trim() === '';

  const closeMenu = () => {
    setOpen(false);
    setQuery(null);
    setBox(null);
  };

  const choose = (symbol: string) => {
    onChange(symbol);
    closeMenu();
    inputRef.current?.focus();
  };

  useLayoutEffect(() => {
    if (!open) return;

    const place = () => {
      const input = inputRef.current;
      const menu = menuRef.current;
      if (!input || !menu) return;

      const rect = input.getBoundingClientRect();
      const margin = 4;
      const width = Math.max(rect.width, 280);
      const spaceBelow = window.innerHeight - rect.bottom - margin;
      const spaceAbove = rect.top - margin;
      const wanted = Math.min(menu.scrollHeight, 280);
      const openUp = spaceBelow < Math.min(wanted, 180) && spaceAbove > spaceBelow;
      const available = openUp ? spaceAbove : spaceBelow;
      const maxHeight = Math.min(280, Math.max(available, 0));
      const height = Math.min(menu.scrollHeight, maxHeight);
      let left = rect.left;
      if (left + width > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - width - 8);
      }
      const top = openUp ? rect.top - margin - height : rect.bottom + margin;
      setBox({ top, left, width, maxHeight });
    };

    place();
    const onScroll = (event: Event) => {
      const menu = menuRef.current;
      if (menu && event.target instanceof Node && (event.target === menu || menu.contains(event.target))) return;
      place();
    };
    window.addEventListener('resize', place);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [open, query, results.length]);

  useEffect(() => {
    if (!open || !box) return;
    const menu = menuRef.current;
    const option = results[safeActive];
    if (!menu || !option) return;
    const node = document.getElementById(optionDomId(id, option.symbol));
    if (!node) return;
    const menuRect = menu.getBoundingClientRect();
    const nodeRect = node.getBoundingClientRect();
    if (nodeRect.top < menuRect.top) {
      menu.scrollTop -= menuRect.top - nodeRect.top;
    } else if (nodeRect.bottom > menuRect.bottom) {
      menu.scrollTop += nodeRect.bottom - menuRect.bottom;
    }
  }, [open, safeActive, results, id, box]);

  useEffect(() => {
    if (!disabled) return;
    setOpen(false);
    setQuery(null);
    setBox(null);
  }, [disabled]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      closeMenu();
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const applyQuery = () => {
    if (query !== null) {
      const resolved = resolveUnitQuery(query);
      if (resolved !== undefined) onChange(resolved);
    }
    closeMenu();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        setActive(unitIndex(value));
        setOpen(true);
        return;
      }
      if (results.length === 0) return;
      setActive((index) => {
        const current = Math.min(index, results.length - 1);
        if (event.key === 'ArrowDown') return (current + 1) % results.length;
        return (current - 1 + results.length) % results.length;
      });
      return;
    }

    if (event.key === 'Enter') {
      event.preventDefault();
      if (open) {
        const next = results[safeActive];
        if (!next) return;
        if (query !== null || next.symbol !== value) {
          choose(next.symbol);
          return;
        }
        closeMenu();
      }
      onCommit?.();
      return;
    }

    if (event.key === 'Escape') {
      event.preventDefault();
      if (open) {
        closeMenu();
        return;
      }
      onCancel?.();
      return;
    }

    if (event.key === 'Home' && open) {
      event.preventDefault();
      setActive(0);
    }
    if (event.key === 'End' && open && results.length > 0) {
      event.preventDefault();
      setActive(results.length - 1);
    }
  };

  const inputValue = query ?? (selected?.symbol ?? value);

  const menu = open
    ? createPortal(
        <div
          id={`${id}_list`}
          ref={menuRef}
          className="pp_unitMenu"
          role="listbox"
          aria-label="Units"
          onMouseDown={(event) => event.preventDefault()}
          style={{
            top: box?.top ?? 0,
            left: box?.left ?? 0,
            width: box?.width ?? 280,
            maxHeight: box?.maxHeight ?? 280,
            visibility: box ? 'visible' : 'hidden',
          }}
        >
          {results.length === 0 ? (
            <div id={`${id}_empty`} className="pp_unitEmpty">
              No matching units
            </div>
          ) : (
            results.map((unit, index) => {
              const showHeader = grouped && (index === 0 || unit.category !== results[index - 1].category);
              return (
                <UnitOption
                  key={unit.symbol === '' ? 'unitless' : unit.symbol}
                  id={id}
                  unit={unit}
                  index={index}
                  active={index === safeActive}
                  current={unit.symbol === value}
                  showHeader={showHeader}
                  showCategory={!grouped}
                  onHover={setActive}
                  onChoose={choose}
                />
              );
            })
          )}
        </div>,
        document.body
      )
    : null;

  return (
    <div id={id} ref={rootRef} className={`pp_unitSelect${open ? ' pp_unitSelectOpen' : ''}`}>
      <input
        id={`${id}_input`}
        ref={inputRef}
        className="pp_input pp_inputInline pp_unitInput"
        size={1}
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}_list`}
        aria-autocomplete="list"
        aria-activedescendant={open && results[safeActive] ? optionDomId(id, results[safeActive].symbol) : undefined}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        placeholder={value ? 'Unit' : 'unitless'}
        title={selected?.label || value || 'Unitless'}
        value={inputValue}
        onFocus={(event) => event.currentTarget.select()}
        onClick={() => {
          if (!open) {
            setActive(unitIndex(value));
            setOpen(true);
          }
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onBlur={applyQuery}
        onKeyDown={onKeyDown}
      />
      <button
        id={`${id}_toggle`}
        type="button"
        className="pp_unitToggle"
        tabIndex={-1}
        disabled={disabled}
        aria-label="Show units"
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => {
          if (open) {
            applyQuery();
            return;
          }
          setActive(unitIndex(value));
          setOpen(true);
          inputRef.current?.focus();
        }}
      >
        <span id={`${id}_chevron`}>
          <IconChevronDown size={14} />
        </span>
      </button>
      {menu}
    </div>
  );
}

function UnitOption({
  id,
  unit,
  index,
  active,
  current,
  showHeader,
  showCategory,
  onHover,
  onChoose,
}: {
  id: string;
  unit: FusionUnit;
  index: number;
  active: boolean;
  current: boolean;
  showHeader: boolean;
  showCategory: boolean;
  onHover: (index: number) => void;
  onChoose: (symbol: string) => void;
}) {
  const headerSlug = unit.category.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  return (
    <>
      {showHeader && (
        <div id={`${id}_group_${headerSlug}`} className="pp_unitGroup">
          {unit.category}
        </div>
      )}
      <button
        id={optionDomId(id, unit.symbol)}
        type="button"
        role="option"
        aria-selected={current}
        className={`pp_unitOption${active ? ' pp_unitOptionActive' : ''}`}
        onMouseEnter={() => onHover(index)}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => onChoose(unit.symbol)}
      >
        <span id={`${id}_sym_${unit.symbol || 'unitless'}`} className="pp_unitSymbol">
          {unit.symbol || '—'}
        </span>
        <span id={`${id}_label_${unit.symbol || 'unitless'}`} className="pp_unitLabel">
          {unit.label}
          {showCategory && (
            <span id={`${id}_cat_${unit.symbol || 'unitless'}`} className="pp_unitCategory">
              {' '}
              · {unit.category}
            </span>
          )}
        </span>
        {current && (
          <span id={`${id}_check_${unit.symbol || 'unitless'}`} className="pp_unitCheck">
            <IconCheck size={14} />
          </span>
        )}
      </button>
    </>
  );
}
