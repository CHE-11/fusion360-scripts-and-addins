import { useEffect, useState } from 'react';

import { request } from '../../connector/fusionBridge';
import type { FeatureList, FeatureRow, ThreadFeature } from '../../types/types';
import { useToast } from '../common/Toast';

type Props = {
  revision: number;
  onChanged: () => void;
};

export function AdjustTab({ revision, onChanged }: Props) {
  const { showToast } = useToast();
  const [rows, setRows] = useState<FeatureRow[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void request<FeatureList>('thread:list')
      .then((data) => {
        if (!cancelled) setRows(data.features || []);
      })
      .catch((reason: unknown) => {
        if (!cancelled) showToast(reason instanceof Error ? reason.message : 'Could not list threads.', 'error');
      });
    return () => {
      cancelled = true;
    };
  }, [revision, showToast]);

  async function nudge(row: FeatureRow, direction: 'tight' | 'loose') {
    const action = row.kind === 'thread' ? 'thread:nudge' : 'insert:nudge';
    try {
      await request(action, { id: row.id, direction });
      showToast(direction === 'tight' ? 'Loosened the fit.' : 'Tightened the fit.', 'success');
      onChanged();
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : 'Could not update the fit.', 'error');
    }
  }

  async function remove(row: FeatureRow) {
    const action = row.kind === 'thread' ? 'thread:delete' : 'insert:delete';
    try {
      await request(action, { id: row.id });
      showToast(`Deleted ${row.label}.`, 'success');
      onChanged();
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : 'Could not delete it.', 'error');
    }
  }

  async function applyThread(row: ThreadFeature, draft: ThreadFeature) {
    try {
      await request('thread:update', draft);
      showToast(`Updated ${row.label}.`, 'success');
      onChanged();
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : 'Could not update the thread.', 'error');
    }
  }

  if (!rows.length) {
    return (
      <div id="th_adjustEmpty" className="th_body">
        <div id="th_adjustEmptyCard" className="th_empty">
          <h2 id="th_adjustEmptyTitle">Nothing to adjust yet</h2>
          <p id="th_adjustEmptyText">Create a thread or a heat-set pocket, print it, then come back if the fit is off.</p>
        </div>
      </div>
    );
  }

  return (
    <div id="th_adjustTab" className="th_body">
      <p id="th_adjustHint" className="th_hint">
        Too tight opens the fit (more clearance, or a larger insert hole). Too loose closes it. Threads rebuild. Insert holes update in place.
      </p>
      {rows.map((row) => (
        <article key={row.id} id={`th_row_${row.id}`} className="th_row">
          <h3 id={`th_rowTitle_${row.id}`}>{row.label}</h3>
          <p id={`th_rowMeta_${row.id}`} className="th_meta">
            {row.kind === 'thread'
              ? `${row.gender} ${row.build} · clearance ${row.clearanceMm ?? '—'} mm · pitch ${row.pitchMm ?? '—'} mm`
              : `Hole ${row.holeMm ?? '—'} mm · depth ${row.depthMm ?? '—'} mm`}
          </p>
          <div id={`th_rowActions_${row.id}`} className="th_rowActions">
            <button id={`th_tight_${row.id}`} className="th_btn" type="button" onClick={() => void nudge(row, 'tight')}>Too tight</button>
            <button id={`th_loose_${row.id}`} className="th_btn" type="button" onClick={() => void nudge(row, 'loose')}>Too loose</button>
            {row.kind === 'thread' ? (
              <button id={`th_edit_${row.id}`} className="th_btn" type="button" onClick={() => setOpenId(openId === row.id ? null : row.id)}>
                Edit
              </button>
            ) : null}
            <button id={`th_delete_${row.id}`} className="th_btn th_btnDanger" type="button" onClick={() => void remove(row)}>Delete</button>
          </div>
          {row.kind === 'thread' && openId === row.id ? (
            <ThreadEditor row={row} onApply={(draft) => void applyThread(row, draft)} />
          ) : null}
        </article>
      ))}
    </div>
  );
}

function ThreadEditor({ row, onApply }: { row: ThreadFeature; onApply: (draft: ThreadFeature) => void }) {
  const [draft, setDraft] = useState(row);
  useEffect(() => setDraft(row), [row]);
  const [text, setText] = useState<Record<string, string>>({});

  function shown(key: 'clearanceMm' | 'pitchMm' | 'lengthMm' | 'offsetMm' | 'flankDeg') {
    return text[key] ?? (draft[key] ?? '');
  }

  function field(key: 'clearanceMm' | 'pitchMm' | 'lengthMm' | 'offsetMm' | 'flankDeg', id: string, label: string) {
    return (
      <label id={`${id}_field`} className="th_field">
        <span id={`${id}_label`}>{label}</span>
        <input
          id={id}
          value={shown(key)}
          onChange={(event) => setText((current) => ({ ...current, [key]: event.target.value }))}
        />
      </label>
    );
  }

  function apply() {
    const next = { ...draft };
    (['clearanceMm', 'pitchMm', 'lengthMm', 'offsetMm', 'flankDeg'] as const).forEach((key) => {
      if (text[key] === undefined) return;
      next[key] = text[key] === '' ? null : Number(text[key]);
    });
    onApply(next);
  }

  return (
    <div id={`th_editor_${row.id}`} className="th_grid">
      {field('clearanceMm', `th_editClear_${row.id}`, 'Clearance')}
      {field('pitchMm', `th_editPitch_${row.id}`, 'Pitch')}
      {field('lengthMm', `th_editLength_${row.id}`, 'Length')}
      {field('offsetMm', `th_editOffset_${row.id}`, 'Offset')}
      {field('flankDeg', `th_editFlank_${row.id}`, 'Flank')}
      <button id={`th_apply_${row.id}`} className="th_btn th_btnPrimary" type="button" onClick={apply}>
        Apply
      </button>
    </div>
  );
}
