import type { ItemKind, ListItem, ListMode, OpName, SortOrder } from '../types/types';

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

export function sortItems(items: ListItem[], sort: SortOrder): ListItem[] {
  const copy = [...items];
  if (sort === 'browser') return copy.sort((a, b) => a.order - b.order);
  return copy.sort((a, b) => collator.compare(a.name, b.name) || collator.compare(a.context, b.context) || a.order - b.order);
}

export function filterItems(items: ListItem[], mode: ListMode, query: string): ListItem[] {
  const needle = query.trim().toLowerCase();
  return items.filter((item) => {
    if (mode === 'assembly' && item.kind !== 'assembly') return false;
    if (!needle) return true;
    return item.name.toLowerCase().includes(needle) || item.context.toLowerCase().includes(needle);
  });
}

export const KIND_LABELS: Record<ItemKind, string> = {
  component: 'Component',
  assembly: 'Assembly',
  body: 'Body',
  face: 'Face',
};

export const OP_LABELS: Record<OpName, string> = {
  move: 'Move',
  mirror: 'Mirror',
  circPattern: 'Circ Pat',
  rectPattern: 'Rect Pat',
};

/** Why an operation cannot run on these items, or '' when it can. */
export function opBlocker(op: OpName, items: ListItem[]): string {
  if (!items.length) return 'Check at least one component or body first.';
  if (items.some((item) => item.kind === 'face')) return 'Operations work on components and bodies, not faces.';
  if (op === 'move') return '';
  const hasOcc = items.some((item) => item.kind === 'component' || item.kind === 'assembly');
  const hasBody = items.some((item) => item.kind === 'body');
  if (hasOcc && hasBody) return 'Mirror and patterns need all components or all bodies.';
  return '';
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
