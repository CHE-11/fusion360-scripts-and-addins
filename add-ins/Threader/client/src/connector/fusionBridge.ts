/*
 * fusionBridge
 * -------------
 * Typed request/response between the React palette and the Fusion add-in.
 * Outside Fusion (vite dev), an in-memory mock keeps the palette interactive.
 */

import { DEV_CATALOG, FACE_ROLE } from '../data/catalog';
import type {
  CreateResult,
  FeatureList,
  FeatureRow,
  InsertFeature,
  ReadyPayload,
  SelectionPayload,
  ThreadFeature,
  ThreadPreview,
} from '../types/types';

export type FusionResponse<T> = { ok: true; data: T } | { ok: false; error: string };

export class FusionError extends Error {}

type EventListener = (data: string) => void;

const eventListeners = new Map<string, Set<EventListener>>();

function dispatchEvent(action: string, messageString: string): string {
  const listeners = eventListeners.get(action);
  if (listeners) {
    listeners.forEach((callback) => {
      try {
        callback(messageString);
      } catch (error) {
        console.error(`[Threader] event listener for "${action}" threw`, error);
      }
    });
  }
  return 'OK';
}

export function onEvent(action: string, callback: EventListener): () => void {
  let set = eventListeners.get(action);
  if (!set) {
    set = new Set();
    eventListeners.set(action, set);
  }
  set.add(callback);
  return () => {
    set?.delete(callback);
  };
}

function installHandler() {
  window.fusionJavaScriptHandler = {
    handle: (action: string, messageString: string) => {
      if (action === 'debugger') {
        debugger;
        return 'OK';
      }
      return dispatchEvent(action, messageString);
    },
  };
}

const MAX_WAIT_MS = 1000;

export function hasAdsk(): boolean {
  return !!(window.adsk && typeof window.adsk.fusionSendData === 'function');
}

let readyPromise: Promise<boolean> | null = null;

export function waitForAdsk(): Promise<boolean> {
  if (readyPromise) return readyPromise;
  readyPromise = new Promise<boolean>((resolve) => {
    if (hasAdsk()) {
      installHandler();
      resolve(true);
      return;
    }
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      if (hasAdsk()) {
        window.clearInterval(timer);
        installHandler();
        resolve(true);
      } else if (Date.now() - startedAt > MAX_WAIT_MS) {
        window.clearInterval(timer);
        console.log('[Threader] adsk object not found; running in dev mock mode.');
        resolve(false);
      }
    }, 100);
  });
  return readyPromise;
}

installHandler();

export async function request<T = unknown>(action: string, payload?: unknown): Promise<T> {
  if (!hasAdsk()) {
    return mockRequest<T>(action, payload);
  }

  const raw = await Promise.resolve(window.adsk!.fusionSendData(action, JSON.stringify(payload ?? {})));
  if (raw == null || raw === '') {
    throw new FusionError(`Empty response from Fusion for "${action}"`);
  }

  let parsed: FusionResponse<T>;
  try {
    parsed = JSON.parse(raw) as FusionResponse<T>;
  } catch {
    return raw as unknown as T;
  }

  if (parsed && typeof parsed === 'object' && 'ok' in parsed) {
    if (parsed.ok) return parsed.data;
    throw new FusionError(parsed.error || `Request "${action}" failed`);
  }

  return parsed as unknown as T;
}

export function send(action: string, payload?: unknown): void {
  try {
    if (hasAdsk()) {
      void window.adsk!.fusionSendData(action, JSON.stringify(payload ?? {}));
    }
  } catch (error) {
    console.error(`[Threader] send("${action}") failed`, error);
  }
}

export function sendJsLog(level: string, message: unknown, extra?: unknown): void {
  send('jsLog', {
    level: level || 'info',
    message: String(message ?? ''),
    extra: extra ?? null,
    ts: new Date().toISOString(),
  });
}

export async function sendReady(): Promise<ReadyPayload> {
  await waitForAdsk();
  return request<ReadyPayload>('ready');
}

// ---------------------------------------------------------------------------
// Dev mock
// ---------------------------------------------------------------------------

const mockSelection: SelectionPayload = {
  cylinder: {
    token: 'face-cylinder',
    radiusMm: 5,
    diameterMm: 10,
    lengthMm: 18,
    gender: 'male',
    axisVertical: true,
  },
  planar: { token: 'face-planar' },
  center: { token: 'edge-circle', kind: 'edge' },
  inserts: { faceCount: 1, pointCount: 2 },
};

let mockFeatures: FeatureRow[] = [
  {
    id: 't1',
    kind: 'thread',
    label: 'Ø10.0 male outset',
    gender: 'male',
    build: 'outset',
    family: 'printable',
    size: 'Custom',
    mating: 'plastic',
    rightHand: true,
    lead: true,
    clearanceMm: 0.2,
    pitchMm: 2,
    lengthMm: 16,
    offsetMm: 0,
    leadMm: 1.5,
    flankDeg: 45,
  },
];

function num(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' && value !== '' ? Number(value) : NaN;
  return Number.isFinite(parsed) ? parsed : fallback;
}

function mockPreview(payload: Record<string, unknown>): ThreadPreview {
  const gender = payload.gender === 'female' ? 'female' : 'male';
  const build = payload.build === 'inset' ? 'inset' : 'outset';
  const family = payload.family === 'iso' || payload.family === 'unc' ? payload.family : 'printable';
  const radius = num(payload.faceRadiusMm, 5);
  const clearance = num(payload.clearanceMm, family === 'printable' ? 0.2 : 0.15);
  const pitch = num(payload.pitchMm, 2);
  const warnings: string[] = [];
  const notes = ['Browser mock. Fusion computes the real tooth and sweep.'];
  if (payload.axisVertical === false) {
    warnings.push('Print this with the thread axis vertical. A sideways thread is weaker and less accurate.');
  }
  if (family !== 'printable' && num(payload.faceRadiusMm, 0) > 0 && radius * 2 < 4.8) {
    warnings.push('Modeled threads smaller than M5 or #10 rarely print cleanly.');
  }
  const major = gender === 'male' ? radius * 2 - clearance * 2 + 1 : radius * 2 + clearance * 2;
  const minor = major - 1;
  return {
    gender,
    build,
    family,
    size: String(payload.size || 'Custom'),
    mating: payload.mating === 'metal' ? 'metal' : 'plastic',
    pitchMm: pitch,
    flankDeg: num(payload.flankDeg, family === 'printable' ? 45 : 60),
    clearanceMm: clearance,
    toothMm: 0.5,
    crestMm: 0.45,
    majorMm: Math.round(major * 100) / 100,
    minorMm: Math.round(minor * 100) / 100,
    turns: Math.max(1, Math.floor(num(payload.faceLengthMm, 18) / pitch)),
    lengthMm: Math.max(1, Math.floor(num(payload.faceLengthMm, 18) / pitch)) * pitch,
    offsetMm: num(payload.offsetMm, 0),
    chamferMm: payload.chamfer ? num(payload.chamferMm, 1) : 0,
    leadMm: 0.75 * pitch,
    rightHand: payload.rightHand !== false,
    faceRole: FACE_ROLE[`${gender}|${build}`] || '',
    label: `${payload.size || 'Custom'} ${gender} ${build}`,
    warnings,
    notes,
    operation: build === 'inset' ? 'cut' : 'join',
  };
}

function mockRequest<T>(action: string, payload?: unknown): T {
  const data = (payload ?? {}) as Record<string, unknown>;
  if (action === 'ready' || action === 'standards:list') {
    return { doc: 'Mock design', standards: DEV_CATALOG } as T;
  }
  if (action === 'palette:minimize' || action === 'jsLog' || action === 'clipboard:copy') {
    return { minimized: true, copied: true } as T;
  }
  if (action === 'face:readSelection') {
    return mockSelection as T;
  }
  if (action === 'thread:preview') {
    if (!data.faceRadiusMm) throw new FusionError('Select a cylindrical face.');
    return mockPreview(data) as T;
  }
  if (action === 'thread:create') {
    const preview = mockPreview(data);
    const feature: ThreadFeature = {
      id: `t${mockFeatures.length + 1}`,
      kind: 'thread',
      label: preview.label,
      gender: preview.gender,
      build: preview.build,
      family: preview.family,
      size: preview.size,
      mating: preview.mating,
      rightHand: preview.rightHand,
      lead: true,
      clearanceMm: preview.clearanceMm,
      pitchMm: preview.pitchMm,
      lengthMm: preview.lengthMm,
      offsetMm: preview.offsetMm,
      leadMm: preview.leadMm,
      flankDeg: preview.flankDeg,
    };
    mockFeatures = [...mockFeatures, feature];
    return { feature, preview, warnings: preview.warnings } as T;
  }
  if (action === 'thread:list' || action === 'insert:list') {
    return { features: mockFeatures } as FeatureList as T;
  }
  if (action === 'thread:nudge' || action === 'insert:nudge') {
    const id = String(data.id || '');
    const direction = data.direction === 'loose' ? -1 : 1;
    mockFeatures = mockFeatures.map((row) => {
      if (row.id !== id) return row;
      if (row.kind === 'thread') {
        return { ...row, clearanceMm: Math.max(0, (row.clearanceMm ?? 0) + direction * 0.05) };
      }
      return { ...row, holeMm: Math.max(0.5, (row.holeMm ?? 0) + direction * 0.1) };
    });
    const feature = mockFeatures.find((row) => row.id === id) ?? null;
    return { feature, warnings: [] } as CreateResult as T;
  }
  if (action === 'thread:update' || action === 'insert:update') {
    const id = String(data.id || '');
    mockFeatures = mockFeatures.map((row) => (row.id === id ? ({ ...row, ...data, id, kind: row.kind } as FeatureRow) : row));
    const feature = mockFeatures.find((row) => row.id === id) ?? null;
    return { feature, warnings: [] } as T;
  }
  if (action === 'thread:delete' || action === 'insert:delete') {
    mockFeatures = mockFeatures.filter((row) => row.id !== data.id);
    return { deleted: data.id } as T;
  }
  if (action === 'insert:preview') {
    const preset = DEV_CATALOG.inserts.find((row) => row.size === data.size) ?? DEV_CATALOG.inserts[2];
    return {
      size: preset.size,
      holeMm: num(data.holeMm, preset.holeMm),
      depthMm: num(data.depthMm, preset.depthMm),
      chamferMm: num(data.chamferMm, preset.chamferMm),
      notes: ['A tight insert means the hole was small. Too tight opens it by 0.10 mm.'],
      warnings: [],
    } as T;
  }
  if (action === 'insert:create') {
    const feature: InsertFeature = {
      id: `i${mockFeatures.length + 1}`,
      kind: 'insert',
      label: `${data.size || 'M3'} heat-set`,
      size: String(data.size || 'M3'),
      holeMm: num(data.holeMm, 4),
      depthMm: num(data.depthMm, 5.6),
      chamferMm: num(data.chamferMm, 0.5),
    };
    mockFeatures = [...mockFeatures, feature];
    return { feature, warnings: [] } as T;
  }
  throw new FusionError(`Unknown action: ${action}`);
}
