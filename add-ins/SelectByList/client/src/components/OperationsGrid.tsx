import { IconArrowsMove, IconCircleDashed, IconFlipVertical, IconGridDots } from '@tabler/icons-react';

import type { ListItem, OpName } from '../types/types';
import { OP_LABELS, opBlocker } from '../utils/items';

type OperationsGridProps = {
  checkedItems: ListItem[];
  busy: boolean;
  hasDocument: boolean;
  onRun: (op: OpName) => void;
};

const OPS: { op: OpName; Icon: typeof IconArrowsMove; hint: string }[] = [
  { op: 'move', Icon: IconArrowsMove, hint: 'Open Move with the checked items, gizmo centred on them' },
  { op: 'mirror', Icon: IconFlipVertical, hint: 'Open Mirror with the checked items' },
  { op: 'circPattern', Icon: IconCircleDashed, hint: 'Open Circular Pattern with the checked items' },
  { op: 'rectPattern', Icon: IconGridDots, hint: 'Open Rectangular Pattern with the checked items' },
];

export function OperationsGrid({ checkedItems, busy, hasDocument, onRun }: OperationsGridProps) {
  return (
    <section id="sbl-operations" className="sbl-operations">
      <div id="sbl-operations-label" className="sbl-sectionLabel">
        Operations
      </div>
      <div id="sbl-operations-grid" className="sbl-opsGrid">
        {OPS.map(({ op, Icon, hint }) => {
          const blocker = opBlocker(op, checkedItems);
          return (
            <button
              key={op}
              id={`sbl-op-${op}`}
              type="button"
              className="sbl-opButton"
              onClick={() => onRun(op)}
              disabled={busy || !hasDocument}
              aria-disabled={!!blocker}
              data-blocked={blocker ? 'true' : undefined}
              title={blocker || hint}
            >
              <Icon id={`sbl-op-icon-${op}`} size={18} className="sbl-opIcon" />
              <span id={`sbl-op-label-${op}`}>{OP_LABELS[op]}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
