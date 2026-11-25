import { IconEyeOff, IconLink } from '@tabler/icons-react';
import { memo, type MouseEvent } from 'react';

import type { ListItem } from '../types/types';
import { KIND_LABELS } from '../utils/items';

type ItemRowProps = {
  item: ListItem;
  index: number;
  top: number;
  checked: boolean;
  inViewport: boolean;
  indent: boolean;
  onToggle: (id: string, event: MouseEvent) => void;
  onActivate: (item: ListItem) => void;
};

function rowId(id: string) {
  return `sbl-row-${id.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
}

export const ItemRow = memo(function ItemRow({ item, index, top, checked, inViewport, indent, onToggle, onActivate }: ItemRowProps) {
  const domId = rowId(item.id);
  const classes = [
    'sbl-row',
    `sbl-row-${item.kind}`,
    checked ? 'sbl-rowChecked' : '',
    inViewport ? 'sbl-rowViewport' : '',
    item.shown ? '' : 'sbl-rowHidden',
  ]
    .filter(Boolean)
    .join(' ');
  const tooltip = [
    `${KIND_LABELS[item.kind]}: ${item.name}`,
    item.context ? `In: ${item.context}` : '',
    item.dims ? `Size: ${item.dims}` : '',
    item.shown ? '' : 'Hidden',
    'Double-click to select in the viewport',
  ]
    .filter(Boolean)
    .join('\n');

  return (
    <div
      id={domId}
      className={classes}
      style={{ top }}
      role="option"
      aria-selected={checked}
      data-index={index}
      title={tooltip}
      onClick={(event) => onToggle(item.id, event)}
      onDoubleClick={() => onActivate(item)}
    >
      <input
        id={`${domId}-check`}
        className="sbl-rowCheck"
        type="checkbox"
        checked={checked}
        readOnly
        tabIndex={-1}
      />
      <span
        id={`${domId}-swatch`}
        className={`sbl-swatch${item.color ? '' : ' sbl-swatchEmpty'}`}
        style={item.color ? { background: item.color } : undefined}
      />
      <span id={`${domId}-name`} className="sbl-rowName" style={indent ? { paddingLeft: item.depth * 12 } : undefined}>
        {item.name}
      </span>
      {item.linked && <IconLink id={`${domId}-linked`} className="sbl-rowFlag" size={12} />}
      {!item.visible && <IconEyeOff id={`${domId}-hidden`} className="sbl-rowFlag" size={12} />}
      <span id={`${domId}-dims`} className="sbl-rowDims">
        {item.dims}
      </span>
    </div>
  );
});
