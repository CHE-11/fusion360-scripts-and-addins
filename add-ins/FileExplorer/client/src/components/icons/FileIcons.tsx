import type { ExplorerNode } from '../../types/types';

export type IconKind = 'hub' | 'project' | 'folder' | 'design' | 'drawing' | 'electronics' | 'file';

type IconProps = {
  kind: IconKind;
  id?: string;
};

export function iconKind(node: Pick<ExplorerNode, 'kind' | 'extension'>): IconKind {
  if (node.kind === 'hub') return 'hub';
  if (node.kind === 'project') return 'project';
  if (node.kind === 'folder') return 'folder';
  if (node.extension === 'f3d') return 'design';
  if (node.extension === 'f2d') return 'drawing';
  if (node.extension === 'fsch' || node.extension === 'fbrd' || node.extension === 'fprj') return 'electronics';
  return 'file';
}

export function FileTypeIcon({ kind, id }: IconProps) {
  return (
    <span id={id} className={`fx-icon fx-icon-${kind}`} aria-hidden="true">
      <IconGlyph kind={kind} />
    </span>
  );
}

function IconGlyph({ kind }: { kind: IconKind }) {
  if (kind === 'hub') {
    return (
      <svg viewBox="0 0 20 20">
        <path d="M4.2 8.2 10 4.5l5.8 3.7v6.2c0 .7-.5 1.2-1.2 1.2H5.4c-.7 0-1.2-.5-1.2-1.2V8.2Z" />
        <path d="M8 15.6V11h4v4.6" />
      </svg>
    );
  }
  if (kind === 'project') {
    return (
      <svg viewBox="0 0 20 20">
        <path d="M3.5 6.5h4l1.2 1.5H16.5v7.2c0 .6-.5 1.1-1.1 1.1H4.6c-.6 0-1.1-.5-1.1-1.1V6.5Z" />
        <path d="M3.5 6.5V5.2c0-.5.4-.9.9-.9h3.2l1.1 1.2" />
      </svg>
    );
  }
  if (kind === 'folder') {
    return (
      <svg viewBox="0 0 20 20">
        <path d="M3.2 7.2c0-.7.6-1.3 1.3-1.3h3.1l1.3 1.4h6.6c.7 0 1.3.6 1.3 1.3v6c0 .7-.6 1.3-1.3 1.3H4.5c-.7 0-1.3-.6-1.3-1.3V7.2Z" />
      </svg>
    );
  }
  if (kind === 'design') {
    return (
      <svg viewBox="0 0 20 20">
        <path d="M10 3.2 16.2 6.8v6.4L10 16.8 3.8 13.2V6.8L10 3.2Z" />
        <path d="M10 10.1 16.2 6.8M10 10.1 3.8 6.8M10 10.1v6.7" />
      </svg>
    );
  }
  if (kind === 'drawing') {
    return (
      <svg viewBox="0 0 20 20">
        <path d="M5 3.5h7.2L15.5 7v9.5c0 .6-.4 1-1 1H5c-.6 0-1-.4-1-1v-12c0-.6.4-1 1-1Z" />
        <path d="M12 3.6V7h3.4M6.2 10.2h6.2M6.2 12.6h4.4" />
      </svg>
    );
  }
  if (kind === 'electronics') {
    return (
      <svg viewBox="0 0 20 20">
        <rect x="5" y="5" width="10" height="10" rx="2" />
        <path d="M8 5V3M12 5V3M8 17v-2M12 17v-2M5 8H3M5 12H3M17 8h-2M17 12h-2" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 20 20">
      <path d="M6 3.4h5.4L15 7.2v9.2c0 .6-.5 1.1-1.1 1.1H6c-.6 0-1.1-.5-1.1-1.1V4.5c0-.6.5-1.1 1.1-1.1Z" />
      <path d="M11.2 3.6V7.2H15" />
    </svg>
  );
}
