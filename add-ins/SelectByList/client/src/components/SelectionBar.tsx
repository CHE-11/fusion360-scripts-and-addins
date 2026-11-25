import { IconArrowBackUp, IconPolygon } from '@tabler/icons-react';

type SelectionBarProps = {
  checkedCount: number;
  shownCount: number;
  totalCount: number;
  inFaceMode: boolean;
  faceSourceLabel: string;
  disabled: boolean;
  onInvert: () => void;
  onFaces: () => void;
};

export function SelectionBar({
  checkedCount,
  shownCount,
  totalCount,
  inFaceMode,
  faceSourceLabel,
  disabled,
  onInvert,
  onFaces,
}: SelectionBarProps) {
  return (
    <div id="sbl-selection-bar" className="sbl-selectionBar">
      <div id="sbl-selection-summary" className="sbl-selectionSummary">
        <span id="sbl-selection-count" className="sbl-selectionCount">
          {checkedCount} selected
        </span>
        <span id="sbl-selection-total" className="sbl-selectionTotal">
          {shownCount === totalCount ? `${totalCount} items` : `${shownCount} of ${totalCount}`}
          {inFaceMode && faceSourceLabel ? ` \u00b7 ${faceSourceLabel}` : ''}
        </span>
      </div>
      <div id="sbl-selection-actions" className="sbl-selectionActions">
        <button id="sbl-invert-button" type="button" className="sbl-btn sbl-btnTag" onClick={onInvert} disabled={disabled} title="Flip the checks on every listed item">
          Invert
        </button>
        <button
          id="sbl-faces-button"
          type="button"
          className={`sbl-btn sbl-btnTag sbl-btnFaces${inFaceMode ? ' sbl-btnFacesActive' : ''}`}
          onClick={onFaces}
          disabled={disabled}
          title={inFaceMode ? 'Back to the previous list' : 'List the faces of the checked bodies or components'}
        >
          {inFaceMode ? <IconArrowBackUp id="sbl-faces-back-icon" size={13} /> : <IconPolygon id="sbl-faces-icon" size={13} />}
          {inFaceMode ? 'Back' : 'Faces'}
        </button>
      </div>
    </div>
  );
}
