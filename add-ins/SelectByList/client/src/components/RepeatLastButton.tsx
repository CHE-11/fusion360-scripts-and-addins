import { IconArrowBackUp } from '@tabler/icons-react';

import type { LastOp } from '../types/types';

type RepeatLastButtonProps = {
  lastOp: LastOp | null;
  busy: boolean;
  onRepeat: () => void;
};

export function RepeatLastButton({ lastOp, busy, onRepeat }: RepeatLastButtonProps) {
  return (
    <div id="sbl-repeat-wrap" className="sbl-repeatWrap">
      <button
        id="sbl-repeat-button"
        type="button"
        className="sbl-btn sbl-btnRepeat"
        onClick={onRepeat}
        disabled={!lastOp || busy}
        title={lastOp ? `Run ${lastOp.label} again on the same ${lastOp.count} item(s)` : 'Run Move, Mirror, or a pattern first'}
      >
        <IconArrowBackUp id="sbl-repeat-icon" size={15} />
        Repeat Last
        <span id="sbl-repeat-detail" className="sbl-repeatDetail">
          {lastOp ? `${lastOp.label.toLowerCase()} (${lastOp.count})` : 'nothing yet'}
        </span>
      </button>
    </div>
  );
}
