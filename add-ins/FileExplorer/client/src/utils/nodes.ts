import type { ExplorerNode } from '../types/types';

export function sortNodes(nodes: ExplorerNode[]): ExplorerNode[] {
  return [...nodes].sort((a, b) => {
    const rank = (node: ExplorerNode) => (node.kind === 'file' ? 1 : 0);
    const byKind = rank(a) - rank(b);
    if (byKind !== 0) return byKind;
    return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
  });
}

export function relativeTime(unix: number | null): string {
  if (!unix) return '';
  const delta = Date.now() / 1000 - unix;
  if (delta < 45) return 'just now';
  if (delta < 3600) return `${Math.max(1, Math.floor(delta / 60))}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  if (delta < 86400 * 14) return `${Math.floor(delta / 86400)}d ago`;
  return new Date(unix * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function displayName(node: ExplorerNode): string {
  return node.extension ? `${node.name}.${node.extension}` : node.name;
}

export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

export function newSearchId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `search-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
