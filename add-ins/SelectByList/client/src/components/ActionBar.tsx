import { IconCursorText, IconEye, IconEyeClosed, IconFocusCentered, IconPencil, IconPlayerPlayFilled, IconRestore } from '@tabler/icons-react';

type ActionBarProps = {
  checkedCount: number;
  canRename: boolean;
  isolated: boolean;
  busy: boolean;
  hasDocument: boolean;
  onSelectViewport: () => void;
  onShow: () => void;
  onHide: () => void;
  onIsolate: () => void;
  onRestoreAll: () => void;
  onRename: () => void;
};

export function ActionBar({
  checkedCount,
  canRename,
  isolated,
  busy,
  hasDocument,
  onSelectViewport,
  onShow,
  onHide,
  onIsolate,
  onRestoreAll,
  onRename,
}: ActionBarProps) {
  const none = checkedCount === 0 || busy || !hasDocument;
  return (
    <div id="sbl-action-bar" className="sbl-actionBar">
      <button
        id="sbl-select-viewport-button"
        type="button"
        className="sbl-btn sbl-btnPrimary"
        onClick={onSelectViewport}
        disabled={none}
        title="Select the checked items in the Fusion viewport"
      >
        <IconPlayerPlayFilled id="sbl-select-viewport-icon" size={13} />
        Select in Viewport
      </button>
      <div id="sbl-visibility-row" className="sbl-visibilityRow">
        <button id="sbl-show-button" type="button" className="sbl-btn sbl-btnTool" onClick={onShow} disabled={none} title="Turn on the checked items">
          <IconEye id="sbl-show-icon" size={13} />
          Show
        </button>
        <button id="sbl-hide-button" type="button" className="sbl-btn sbl-btnTool" onClick={onHide} disabled={none} title="Turn off the checked items">
          <IconEyeClosed id="sbl-hide-icon" size={13} />
          Hide
        </button>
        <button id="sbl-isolate-button" type="button" className="sbl-btn sbl-btnTool" onClick={onIsolate} disabled={none} title="Hide everything except the checked items">
          <IconFocusCentered id="sbl-isolate-icon" size={13} />
          Isolate
        </button>
        <button
          id="sbl-restore-all-button"
          type="button"
          className={`sbl-btn sbl-btnTool${isolated ? ' sbl-btnToolActive' : ''}`}
          onClick={onRestoreAll}
          disabled={busy || !hasDocument}
          title={isolated ? 'End isolate and restore the earlier visibility' : 'Turn every component and body back on'}
        >
          <IconRestore id="sbl-restore-all-icon" size={13} />
          All
        </button>
        <button
          id="sbl-rename-button"
          type="button"
          className="sbl-btn sbl-btnTool"
          onClick={onRename}
          disabled={!canRename || busy || !hasDocument}
          title={canRename ? 'Rename the checked component or body' : 'Check exactly one component or body to rename'}
        >
          {canRename ? <IconPencil id="sbl-rename-icon" size={13} /> : <IconCursorText id="sbl-rename-icon-off" size={13} />}
          Rename
        </button>
      </div>
    </div>
  );
}
