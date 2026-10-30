import { IconBan, IconCurrentLocation, IconEye, IconEyeOff, IconPencil, IconTrash } from '@tabler/icons-react';

import type { AssemblyConstraintInfo } from '../../types/types';

type Props = {
  constraint: AssemblyConstraintInfo;
  busy: boolean;
  editing: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onStartRename: () => void;
  onSaveName: () => void;
  onCancelRename: () => void;
  onSelect: () => void;
  onHighlight: () => void;
  onClearHighlight: () => void;
  onToggleVisible: () => void;
  onToggleSuppressed: () => void;
  onDelete: () => void;
};

export function constraintDomId(prefix: string, token: string) {
  const safe = token.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 80);
  return `${prefix}_${safe || 'item'}`;
}

// Fusion names these "Constraint 12", and copies "Constraint 12 (1)", shown as 12 and 12.1.
function shortName(name: string) {
  const short = name
    .trim()
    .replace(/^constraint\s*/i, '')
    .replace(/^(\d+)\s*\((\d+)\)/, '$1.$2');
  return short || name;
}

function visibilityTitle(constraint: AssemblyConstraintInfo) {
  if (!constraint.isLightBulbOn) return `Show ${constraint.name}`;
  if (!constraint.isVisible) return `${constraint.name} is hidden by a parent component or folder`;
  return `Hide ${constraint.name}`;
}

export function ConstraintRow({
  constraint,
  busy,
  editing,
  draft,
  onDraftChange,
  onStartRename,
  onSaveName,
  onCancelRename,
  onSelect,
  onHighlight,
  onClearHighlight,
  onToggleVisible,
  onToggleSuppressed,
  onDelete,
}: Props) {
  const id = (prefix: string) => constraintDomId(prefix, constraint.token);
  const rowClass = ['cs_constraintCard', constraint.isSuppressed ? 'cs_constraintSuppressed' : '', constraint.isLightBulbOn ? '' : 'cs_constraintHidden']
    .filter(Boolean)
    .join(' ');
  const geometries = Array.from(
    new Set(
      constraint.relationships
        .flatMap((item) => [item.entityOneGeometry, item.entityTwoGeometry])
        .filter((geometry) => geometry && geometry !== 'Geometry')
    )
  );

  return (
    <article
      id={id('cs_asmConstraint')}
      className={rowClass}
      onMouseEnter={onHighlight}
      onMouseLeave={onClearHighlight}
    >
      <div id={id('cs_asmConstraintHead')} className="cs_constraintHead">
        {editing ? (
          <input
            id={id('cs_asmConstraintNameInput')}
            className="cs_input cs_constraintNameInput"
            value={draft}
            aria-label={`Rename ${constraint.name}`}
            autoFocus
            onChange={(event) => onDraftChange(event.target.value)}
            onBlur={onSaveName}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                event.currentTarget.blur();
              } else if (event.key === 'Escape') {
                onCancelRename();
              }
            }}
          />
        ) : (
          <>
            <button id={id('cs_asmConstraintSelect')} className="cs_constraintName" type="button" title={constraint.name} onClick={onSelect}>
              {shortName(constraint.name)}
            </button>
            <div id={id('cs_asmConstraintSides')} className="cs_constraintSides" onClick={onSelect}>
              <span id={id('cs_asmConstraintSideOne')} className="cs_constraintSide" title={constraint.sideOne}>
                {constraint.sideOne}
              </span>
              <span id={id('cs_asmConstraintSideTwo')} className="cs_constraintSide" title={constraint.sideTwo}>
                {constraint.sideTwo}
              </span>
            </div>
          </>
        )}
        <div id={id('cs_asmConstraintBadges')} className="cs_constraintBadges">
          {constraint.relationships.length > 1 && (
            <span
              id={id('cs_asmConstraintCount')}
              className="cs_badge cs_badgeMuted"
              title={`${constraint.relationships.length} relationships`}
            >
              ×{constraint.relationships.length}
            </span>
          )}
          {constraint.isSuppressed && (
            <span id={id('cs_asmConstraintSuppressed')} className="cs_badge cs_badgeWarn">
              Suppressed
            </span>
          )}
          {constraint.health !== 'ok' && (
            <span
              id={id('cs_asmConstraintHealth')}
              className={constraint.health === 'error' ? 'cs_badge cs_badgeError' : 'cs_badge cs_badgeWarn'}
              title={constraint.message || undefined}
            >
              {constraint.health === 'error' ? 'Error' : 'Warning'}
            </span>
          )}
          {geometries.map((geometry, index) => (
            <span key={geometry} id={id(`cs_asmConstraintGeometry${index}`)} className="cs_badge cs_badgeMuted">
              {geometry}
            </span>
          ))}
          <span id={id('cs_asmConstraintType')} className="cs_badge">
            {constraint.typeLabel}
          </span>
        </div>
        <div id={id('cs_asmConstraintActions')} className="cs_rowActions cs_constraintActions">
          <button
            id={id('cs_asmConstraintRename')}
            className="cs_iconBtn"
            type="button"
            title="Rename"
            aria-label={`Rename ${constraint.name}`}
            onClick={onStartRename}
          >
            <IconPencil size={15} />
          </button>
          <button
            id={id('cs_asmConstraintVisible')}
            className="cs_iconBtn"
            type="button"
            title={visibilityTitle(constraint)}
            aria-label={visibilityTitle(constraint)}
            aria-pressed={constraint.isLightBulbOn}
            disabled={busy}
            onClick={onToggleVisible}
          >
            {constraint.isLightBulbOn ? <IconEye size={15} /> : <IconEyeOff size={15} />}
          </button>
          <button
            id={id('cs_asmConstraintSuppress')}
            className={constraint.isSuppressed ? 'cs_iconBtn cs_iconBtnActive' : 'cs_iconBtn'}
            type="button"
            title={constraint.isSuppressed ? 'Unsuppress' : 'Suppress'}
            aria-label={constraint.isSuppressed ? `Unsuppress ${constraint.name}` : `Suppress ${constraint.name}`}
            aria-pressed={constraint.isSuppressed}
            disabled={busy}
            onClick={onToggleSuppressed}
          >
            <IconBan size={15} />
          </button>
          <button
            id={id('cs_asmConstraintLocate')}
            className="cs_iconBtn"
            type="button"
            title="Highlight its geometry in the canvas"
            aria-label={`Highlight the geometry of ${constraint.name} in the canvas`}
            onClick={onSelect}
          >
            <IconCurrentLocation size={15} />
          </button>
          <button
            id={id('cs_asmConstraintDelete')}
            className="cs_iconBtn cs_iconBtnDanger"
            type="button"
            title="Delete constraint"
            aria-label={`Delete ${constraint.name}`}
            disabled={busy}
            onClick={onDelete}
          >
            <IconTrash size={15} />
          </button>
        </div>
      </div>
    </article>
  );
}
