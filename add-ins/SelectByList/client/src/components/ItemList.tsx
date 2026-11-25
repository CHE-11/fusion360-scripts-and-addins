import { useEffect, useRef, useState, type MouseEvent } from 'react';

import type { ListItem } from '../types/types';
import { ItemRow } from './ItemRow';

const ROW_HEIGHT = 30;
const OVERSCAN = 8;

type ItemListProps = {
  items: ListItem[];
  checked: Set<string>;
  viewportKeys: Set<string>;
  indent: boolean;
  emptyMessage: string;
  onToggle: (id: string, event: MouseEvent) => void;
  onActivate: (item: ListItem) => void;
};

export function ItemList({ items, checked, viewportKeys, indent, emptyMessage, onToggle, onActivate }: ItemListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(400);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    setHeight(element.clientHeight);
    const observer = new ResizeObserver(() => setHeight(element.clientHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = scrollRef.current;
    if (element && element.scrollTop > items.length * ROW_HEIGHT) {
      element.scrollTop = 0;
      setScrollTop(0);
    }
  }, [items.length]);

  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const end = Math.min(items.length, Math.ceil((scrollTop + height) / ROW_HEIGHT) + OVERSCAN);
  const visible = items.slice(start, end);

  return (
    <div
      id="sbl-item-list"
      ref={scrollRef}
      className="sbl-list"
      role="listbox"
      aria-multiselectable="true"
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
    >
      {items.length === 0 ? (
        <div id="sbl-list-empty" className="sbl-listEmpty">
          {emptyMessage}
        </div>
      ) : (
        <div id="sbl-list-spacer" className="sbl-listSpacer" style={{ height: items.length * ROW_HEIGHT }}>
          {visible.map((item, offset) => {
            const index = start + offset;
            return (
              <ItemRow
                key={item.id}
                item={item}
                index={index}
                top={index * ROW_HEIGHT}
                checked={checked.has(item.id)}
                inViewport={viewportKeys.has(item.id)}
                indent={indent}
                onToggle={onToggle}
                onActivate={onActivate}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
