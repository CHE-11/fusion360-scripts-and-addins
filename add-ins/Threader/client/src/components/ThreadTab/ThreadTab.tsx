import { useEffect, useState } from 'react';

import { request } from '../../connector/fusionBridge';
import type {
  Build,
  CreateResult,
  CylinderSelection,
  Family,
  Gender,
  Mating,
  StandardsCatalog,
  ThreadPreview,
} from '../../types/types';
import { useToast } from '../common/Toast';

type Props = {
  catalog: StandardsCatalog;
  cylinder: CylinderSelection | null;
  onCreated: () => void;
};

type Form = {
  gender: Gender;
  build: Build;
  family: Family;
  size: string;
  mating: Mating;
  pitch: string;
  clearance: string;
  flank: string;
  length: string;
  offset: string;
  endOffset: string;
  nozzle: string;
  layer: string;
  lead: boolean;
  chamfer: boolean;
  chamferMm: string;
  rightHand: boolean;
  flip: boolean;
};

const NOZZLES = [0.2, 0.4, 0.6, 0.8];

// Bambu Studio system presets for each Bambu nozzle.
const LAYER_HEIGHTS: Record<number, number[]> = {
  0.2: [0.06, 0.08, 0.1, 0.12, 0.14],
  0.4: [0.08, 0.12, 0.16, 0.2, 0.24, 0.28],
  0.6: [0.18, 0.24, 0.3, 0.36, 0.42],
  0.8: [0.24, 0.32, 0.4, 0.48, 0.56],
};

function layersForNozzle(nozzle: number): number[] {
  const match = NOZZLES.find((size) => Math.abs(size - nozzle) < 0.011);
  return match ? LAYER_HEIGHTS[match] : LAYER_HEIGHTS[0.4];
}

function defaultLayer(nozzle: number): number {
  const layers = layersForNozzle(nozzle);
  const target = nozzle * 0.5;
  return layers.reduce((best, layer) =>
    Math.abs(layer - target) < Math.abs(best - target) ? layer : best
  );
}

type ThreadPreset = {
  id: string;
  name: string;
  detail: string;
  pitch: number;
  clearance: number;
  flank: number;
};

function snapUp(value: number, step: number): number {
  if (!(step > 0)) return Math.round(value * 100) / 100;
  const steps = Math.ceil((value - 1e-6) / step);
  return Math.round(Math.max(step, steps * step) * 100) / 100;
}

function pitchForTooth(nozzle: number, tooth: number, layer: number): number {
  // Symmetric 45° trapezoid: crest and valley are each one nozzle wide, so pitch = 2 (nozzle + tooth).
  const flankRad = (45 * Math.PI) / 180;
  const raw = 2 * (nozzle + tooth / Math.tan(flankRad));
  return snapUp(Math.max(raw, 2 * nozzle + layer), layer);
}

function printablePresets(nozzle: number, layer: number): ThreadPreset[] {
  if (!(nozzle > 0) || !(layer > 0)) return [];
  const fineTooth = Math.max(3 * layer, 1.5 * nozzle);
  const standardTooth = Math.max(5 * layer, 2.5 * nozzle);
  const coarseTooth = Math.max(8 * layer, 4 * nozzle);
  const standardPitch = pitchForTooth(nozzle, standardTooth, layer);
  return [
    {
      id: 'fine',
      name: 'Fine',
      detail: 'Small thread, still a full crest',
      pitch: pitchForTooth(nozzle, fineTooth, layer),
      clearance: 0.2,
      flank: 45,
    },
    {
      id: 'standard',
      name: 'Standard',
      detail: 'Everyday fit',
      pitch: standardPitch,
      clearance: 0.2,
      flank: 45,
    },
    {
      id: 'coarse',
      name: 'Coarse',
      detail: 'Stronger, easier to start',
      pitch: pitchForTooth(nozzle, coarseTooth, layer),
      clearance: 0.25,
      flank: 45,
    },
    {
      id: 'easy',
      name: 'Easy fit',
      detail: 'Standard tooth, extra clearance',
      pitch: standardPitch,
      clearance: 0.3,
      flank: 45,
    },
  ];
}

function initialForm(catalog: StandardsCatalog): Form {
  return {
    gender: 'male',
    build: 'outset',
    family: 'printable',
    size: 'M6',
    mating: 'plastic',
    pitch: '2',
    clearance: String(catalog.plasticClearanceMm),
    flank: String(catalog.defaultFlankDeg),
    length: '',
    offset: '0',
    endOffset: '0',
    nozzle: String(catalog.defaultNozzleMm),
    layer: String(catalog.defaultLayerMm),
    lead: true,
    chamfer: true,
    chamferMm: '1',
    rightHand: true,
    flip: false,
  };
}

export function ThreadTab({ catalog, cylinder, onCreated }: Props) {
  const { showToast } = useToast();
  const [form, setForm] = useState<Form>(() => initialForm(catalog));
  const [preview, setPreview] = useState<ThreadPreview | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [lastThreadId, setLastThreadId] = useState<string | null>(null);

  useEffect(() => {
    if (!cylinder) return;
    setForm((current) => ({ ...current, gender: cylinder.gender }));
  }, [cylinder?.token]);

  useEffect(() => {
    if (!cylinder) {
      setPreview(null);
      setError('Select a cylindrical face.');
      return;
    }
    const handle = window.setTimeout(() => {
      const payload = {
        gender: form.gender,
        build: form.build,
        family: form.family,
        size: form.size,
        mating: form.mating,
        pitchMm: form.pitch,
        clearanceMm: form.clearance,
        flankDeg: form.flank,
        lengthMm: form.length,
        offsetMm: form.offset,
        endOffsetMm: form.endOffset,
        nozzleMm: form.nozzle,
        layerMm: form.layer,
        lead: form.lead,
        chamfer: form.chamfer,
        chamferMm: form.chamferMm,
        rightHand: form.rightHand,
        flip: form.flip,
        faceRadiusMm: cylinder.radiusMm,
        faceLengthMm: cylinder.lengthMm,
        axisVertical: cylinder.axisVertical,
        faceToken: cylinder.token,
      };
      void request<ThreadPreview>('thread:preview', payload)
        .then((next) => {
          setPreview(next);
          setError('');
        })
        .catch((reason: unknown) => {
          setPreview(null);
          setError(reason instanceof Error ? reason.message : 'Could not preview the thread.');
        });
    }, 150);
    return () => window.clearTimeout(handle);
  }, [form, cylinder]);

  function patch(partial: Partial<Form>) {
    setForm((current) => ({ ...current, ...partial }));
  }

  function setFamily(family: Family) {
    if (family === 'printable') {
      patch({
        family,
        mating: 'plastic',
        clearance: String(catalog.plasticClearanceMm),
        flank: String(catalog.defaultFlankDeg),
      });
      return;
    }
    const sizes = family === 'iso' ? catalog.iso : catalog.unc;
    patch({
      family,
      mating: 'metal',
      clearance: String(catalog.metalClearanceMm),
      size: sizes.some((row) => row.size === form.size) ? form.size : sizes[0]?.size || 'M6',
    });
  }

  async function create() {
    if (!cylinder || !preview) return;
    setBusy(true);
    try {
      const result = await request<CreateResult>('thread:create', {
        gender: form.gender,
        build: form.build,
        family: form.family,
        size: form.size,
        mating: form.mating,
        pitchMm: form.pitch,
        clearanceMm: form.clearance,
        flankDeg: form.flank,
        lengthMm: form.length,
        offsetMm: form.offset,
        endOffsetMm: form.endOffset,
        nozzleMm: form.nozzle,
        layerMm: form.layer,
        lead: form.lead,
        chamfer: form.chamfer,
        chamferMm: form.chamferMm,
        rightHand: form.rightHand,
        flip: form.flip,
        faceToken: cylinder.token,
      });
      setLastThreadId(result.feature?.kind === 'thread' ? result.feature.id : null);
      const extra = result.warnings?.length ? ` ${result.warnings[0]}` : '';
      showToast(`Created ${preview.label}.${extra}`, extra ? 'info' : 'success');
      onCreated();
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : 'Could not create the thread.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    if (!lastThreadId) return;
    setUndoing(true);
    try {
      await request('thread:delete', { id: lastThreadId });
      setLastThreadId(null);
      showToast('Removed the last thread.', 'success');
      onCreated();
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : 'Could not undo the thread.', 'error');
    } finally {
      setUndoing(false);
    }
  }

  const sizes = form.family === 'unc' ? catalog.unc : catalog.iso;
  const standard = form.family !== 'printable';
  const presets = printablePresets(Number(form.nozzle), Number(form.layer));
  const activePreset = presets.find(
    (preset) =>
      Math.abs(Number(form.pitch) - preset.pitch) < 0.011 &&
      Math.abs(Number(form.clearance) - preset.clearance) < 0.011 &&
      Math.abs(Number(form.flank) - preset.flank) < 0.1
  );

  return (
    <div id="th_threadTab" className="th_body">
      <section id="th_faceCard" className="th_card">
        {cylinder ? (
          <div id="th_faceSummary" className="th_face">
            <span id="th_faceSize">Ø{cylinder.diameterMm.toFixed(2)} mm</span>
            <span id="th_faceLength">{cylinder.lengthMm.toFixed(1)} mm long</span>
          </div>
        ) : (
          <p id="th_faceEmpty" className="th_hint">Select one cylindrical face in the canvas.</p>
        )}
        <p id="th_faceRole" className="th_role">{preview?.faceRole || 'Choose male or female, then inset or outset.'}</p>
      </section>

      <section id="th_modeCard" className="th_card">
        <div id="th_genderSeg" className="th_seg" role="group" aria-label="Gender">
          {(['male', 'female'] as Gender[]).map((gender) => (
            <button
              key={gender}
              id={`th_gender_${gender}`}
              type="button"
              className={form.gender === gender ? 'th_segOn' : ''}
              onClick={() => patch({ gender })}
            >
              {gender === 'male' ? 'Male' : 'Female'}
            </button>
          ))}
        </div>
        <div id="th_buildSeg" className="th_seg" role="group" aria-label="Build">
          {(['outset', 'inset'] as Build[]).map((build) => (
            <button
              key={build}
              id={`th_build_${build}`}
              type="button"
              className={form.build === build ? 'th_segOn' : ''}
              onClick={() => patch({ build })}
            >
              {build === 'outset' ? 'Outset (add)' : 'Inset (cut)'}
            </button>
          ))}
        </div>
        <label id="th_familyField" className="th_field">
          <span id="th_familyLabel">Profile</span>
          <select
            id="th_family"
            value={form.family}
            onChange={(event) => setFamily(event.target.value as Family)}
          >
            <option id="th_family_printable" value="printable">Printable trapezoid (plastic)</option>
            <option id="th_family_iso" value="iso">ISO metric coarse (metal)</option>
            <option id="th_family_unc" value="unc">Imperial UNC and UNF (metal)</option>
          </select>
        </label>
        {standard ? (
          <label id="th_sizeField" className="th_field">
            <span id="th_sizeLabel">Size</span>
            <select id="th_size" value={form.size} onChange={(event) => patch({ size: event.target.value })}>
              {sizes.map((row) => (
                <option key={row.size} id={`th_size_${row.size}`} value={row.size}>
                  {row.size}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </section>

      <section id="th_sizeCard" className="th_card">
        <div id="th_nozzleField" className="th_presetBlock">
          <span id="th_nozzleLabel" className="th_hint">Nozzle (mm)</span>
          <div id="th_nozzles" className="th_seg" role="group" aria-label="Nozzle">
            {NOZZLES.map((nozzle) => (
              <button
                key={nozzle}
                id={`th_nozzle_${String(nozzle).replace('.', '_')}`}
                type="button"
                className={Math.abs(Number(form.nozzle) - nozzle) < 0.011 ? 'th_segOn' : ''}
                onClick={() => {
                  const current = Number(form.layer);
                  const layers = layersForNozzle(nozzle);
                  const kept = layers.some((layer) => Math.abs(layer - current) < 0.011);
                  patch({
                    nozzle: nozzle.toFixed(1),
                    layer: (kept ? current : defaultLayer(nozzle)).toFixed(2),
                  });
                }}
              >
                {nozzle.toFixed(1)}
              </button>
            ))}
          </div>
        </div>
        <div id="th_layerField" className="th_presetBlock">
          <span id="th_layerLabel" className="th_hint">Layer height (mm)</span>
          <div id="th_layers" className="th_seg th_layerSeg" role="group" aria-label="Layer height">
            {layersForNozzle(Number(form.nozzle)).map((layer) => (
              <button
                key={layer}
                id={`th_layer_${String(layer).replace('.', '_')}`}
                type="button"
                className={Math.abs(Number(form.layer) - layer) < 0.011 ? 'th_segOn' : ''}
                onClick={() => patch({ layer: layer.toFixed(2) })}
              >
                {layer.toFixed(2)}
              </button>
            ))}
          </div>
        </div>
        {standard ? null : (
          <div id="th_presetBlock" className="th_presetBlock">
            <span id="th_presetLabel" className="th_hint">Presets for this nozzle and layer height</span>
            <div id="th_presets" className="th_presets" role="group" aria-label="Thread presets">
              {presets.map((preset) => (
                <button
                  key={preset.id}
                  id={`th_preset_${preset.id}`}
                  type="button"
                  className={activePreset?.id === preset.id ? 'th_segOn' : ''}
                  title={preset.detail}
                  onClick={() =>
                    patch({
                      pitch: preset.pitch.toFixed(2),
                      clearance: preset.clearance.toFixed(2),
                      flank: String(preset.flank),
                      mating: 'plastic',
                    })
                  }
                >
                  <span id={`th_presetName_${preset.id}`}>{preset.name}</span>
                  <span id={`th_presetPitch_${preset.id}`} className="th_presetPitch">
                    {preset.pitch.toFixed(2)} mm · {preset.clearance.toFixed(2)} mm
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        <div id="th_sizeGrid" className="th_grid">
          <label id="th_clearanceField" className="th_field">
            <span id="th_clearanceLabel">Clearance (mm, radial)</span>
            <input id="th_clearance" value={form.clearance} onChange={(event) => patch({ clearance: event.target.value })} />
          </label>
          <label id="th_pitchField" className="th_field">
            <span id="th_pitchLabel">Pitch (mm)</span>
            <input id="th_pitch" value={standard ? String(preview?.pitchMm ?? '') : form.pitch} disabled={standard} onChange={(event) => patch({ pitch: event.target.value })} />
          </label>
          <label id="th_lengthField" className="th_field">
            <span id="th_lengthLabel">Length (mm, blank = full)</span>
            <input id="th_length" value={form.length} placeholder="Full face" onChange={(event) => patch({ length: event.target.value })} />
          </label>
          <label id="th_offsetField" className="th_field">
            <span id="th_offsetLabel">Start offset (mm)</span>
            <input id="th_offset" value={form.offset} onChange={(event) => patch({ offset: event.target.value })} />
          </label>
          <label id="th_endOffsetField" className="th_field">
            <span id="th_endOffsetLabel">End offset (mm)</span>
            <input id="th_endOffset" value={form.endOffset} onChange={(event) => patch({ endOffset: event.target.value })} />
          </label>
          <label id="th_flankField" className="th_field">
            <span id="th_flankLabel">Flank from axis (°)</span>
            <input id="th_flank" value={standard ? '60' : form.flank} disabled={standard} onChange={(event) => patch({ flank: event.target.value })} />
          </label>
        </div>
        <div id="th_checks" className="th_checks">
          <label id="th_leadCheck" className="th_check">
            <input id="th_lead" type="checkbox" checked={form.lead} onChange={(event) => patch({ lead: event.target.checked })} />
            Lead-in
          </label>
          <label id="th_chamferCheck" className="th_check">
            <input id="th_chamferOn" type="checkbox" checked={form.chamfer} onChange={(event) => patch({ chamfer: event.target.checked })} />
            Chamfer ends
          </label>
          <label id="th_chamferSize" className="th_field th_chamferSize">
            <span id="th_chamferSizeLabel">mm</span>
            <input id="th_chamfer" value={form.chamferMm} disabled={!form.chamfer} onChange={(event) => patch({ chamferMm: event.target.value })} />
          </label>
          <label id="th_handCheck" className="th_check">
            <input id="th_hand" type="checkbox" checked={form.rightHand} onChange={(event) => patch({ rightHand: event.target.checked })} />
            Right-hand
          </label>
        </div>
      </section>

      <section id="th_previewCard" className="th_preview">
        {error ? <p id="th_previewError" className="th_error">{error}</p> : null}
        {preview ? (
          <>
            <dl id="th_previewStats" className="th_stats">
              <div id="th_stat_major"><dt>Major</dt><dd>{preview.majorMm.toFixed(2)} mm</dd></div>
              <div id="th_stat_minor"><dt>Minor</dt><dd>{preview.minorMm.toFixed(2)} mm</dd></div>
              <div id="th_stat_pitch"><dt>Pitch</dt><dd>{preview.pitchMm.toFixed(2)} mm</dd></div>
              <div id="th_stat_turns"><dt>Turns</dt><dd>{preview.turns}</dd></div>
              <div id="th_stat_crest"><dt>Crest</dt><dd>{preview.crestMm.toFixed(2)} mm</dd></div>
              <div id="th_stat_tooth"><dt>Tooth</dt><dd>{preview.toothMm.toFixed(2)} mm</dd></div>
            </dl>
            {preview.warnings.map((warning, index) => (
              <p key={warning} id={`th_warning_${index}`} className="th_warn">{warning}</p>
            ))}
            {preview.notes.map((note, index) => (
              <p key={note} id={`th_note_${index}`} className="th_note">{note}</p>
            ))}
          </>
        ) : null}
        <div id="th_actionButtons" className="th_actions">
          <button id="th_create" className="th_btn th_btnPrimary" type="button" disabled={!preview || busy || undoing} onClick={() => void create()}>
            {busy ? 'Creating…' : 'Create thread'}
          </button>
        </div>
      </section>
    </div>
  );
}
