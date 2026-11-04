import { useEffect, useState } from 'react';

import { request } from '../../connector/fusionBridge';
import type { SelectionPayload, StandardsCatalog } from '../../types/types';
import { useToast } from '../common/Toast';

type Props = {
  catalog: StandardsCatalog;
  selection: SelectionPayload;
  onCreated: () => void;
};

export function InsertTab({ catalog, selection, onCreated }: Props) {
  const { showToast } = useToast();
  const [size, setSize] = useState('M3');
  const [custom, setCustom] = useState(false);
  const [hole, setHole] = useState('4');
  const [depth, setDepth] = useState('5.6');
  const [chamfer, setChamfer] = useState('0.5');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (custom) return;
    const preset = catalog.inserts.find((row) => row.size === size);
    if (!preset) return;
    setHole(String(preset.holeMm));
    setDepth(String(preset.depthMm));
    setChamfer(String(preset.chamferMm));
  }, [catalog, custom, size]);

  const faces = selection.inserts?.faceCount ?? 0;
  const points = selection.inserts?.pointCount ?? 0;
  const target = faces + points === 0
    ? 'Select flat faces or points.'
    : `${faces} face${faces === 1 ? '' : 's'}, ${points} point${points === 1 ? '' : 's'}`;

  async function create() {
    setBusy(true);
    try {
      const result = await request<{ warnings?: string[] }>('insert:create', {
        size: custom ? 'Custom' : size,
        holeMm: hole,
        depthMm: depth,
        chamferMm: chamfer,
      });
      const extra = result.warnings?.length ? ` ${result.warnings[0]}` : '';
      showToast(`Created the insert pocket.${extra}`, extra ? 'info' : 'success');
      onCreated();
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : 'Could not create the pocket.', 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div id="th_insertTab" className="th_body">
      <section id="th_insertTarget" className="th_card">
        <p id="th_insertTargetText" className="th_role">{target}</p>
        <p id="th_insertHint" className="th_hint">
          A face gets a pocket at its center. A point gets a pocket on that point. The hole size is a starting point for a short brass insert.
        </p>
      </section>
      <section id="th_insertForm" className="th_card">
        <label id="th_insertSizeField" className="th_field">
          <span id="th_insertSizeLabel">Insert</span>
          <select
            id="th_insertSize"
            value={custom ? 'Custom' : size}
            onChange={(event) => {
              if (event.target.value === 'Custom') {
                setCustom(true);
                return;
              }
              setCustom(false);
              setSize(event.target.value);
            }}
          >
            {catalog.inserts.map((row) => (
              <option key={row.size} id={`th_insert_${row.size}`} value={row.size}>{row.size}</option>
            ))}
            <option id="th_insert_custom" value="Custom">Custom</option>
          </select>
        </label>
        <div id="th_insertGrid" className="th_grid">
          <label id="th_holeField" className="th_field">
            <span id="th_holeLabel">Hole diameter (mm)</span>
            <input id="th_hole" value={hole} onChange={(event) => { setCustom(true); setHole(event.target.value); }} />
          </label>
          <label id="th_depthField" className="th_field">
            <span id="th_depthLabel">Depth (mm)</span>
            <input id="th_depth" value={depth} onChange={(event) => { setCustom(true); setDepth(event.target.value); }} />
          </label>
          <label id="th_chamferField" className="th_field">
            <span id="th_chamferLabel">Chamfer (mm)</span>
            <input id="th_chamfer" value={chamfer} onChange={(event) => { setCustom(true); setChamfer(event.target.value); }} />
          </label>
        </div>
        <button
          id="th_insertCreate"
          className="th_btn th_btnPrimary"
          type="button"
          disabled={busy || faces + points === 0}
          onClick={() => void create()}
        >
          {busy ? 'Creating…' : faces + points > 1 ? `Create ${faces + points} pockets` : 'Create pocket'}
        </button>
      </section>
    </div>
  );
}
