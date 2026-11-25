/*
 * fusionBridge
 * -------------
 * Typed request/response between the React palette and the Fusion add-in.
 * Outside Fusion (vite dev), an in-memory design keeps the palette interactive.
 */

import type {
  LastOp,
  ListItem,
  Listing,
  ListMode,
  OpName,
  OpResult,
  ReadyPayload,
  RenameResult,
  SelectResult,
  ViewportSelection,
  VisibilityResult,
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
        console.error(`[SelectByList] event listener for "${action}" threw`, error);
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
        console.log('[SelectByList] adsk object not found; running in dev mock mode.');
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
    throw new FusionError(parsed.error || `Fusion rejected "${action}"`);
  }
  return parsed as T;
}

export function sendJsLog(level: string, message: string, extra?: unknown) {
  if (!hasAdsk()) {
    console.log(`[SelectByList:${level}]`, message, extra ?? '');
    return;
  }
  void request('jsLog', { level, message, extra }).catch(() => {
    // Logging must not throw into the palette.
  });
}

/* ------------------------------------------------------------------------ */
/* Dev mock                                                                  */
/* ------------------------------------------------------------------------ */

type MockOccurrence = {
  name: string;
  dims: string;
  color: string;
  visible: boolean;
  bodies: { name: string; dims: string; color: string; visible: boolean; faces: number }[];
  children: MockOccurrence[];
};

function part(name: string, dims: string, color: string, faces = 12): MockOccurrence {
  return {
    name,
    dims,
    color,
    visible: true,
    bodies: [{ name: 'Body1', dims, color, visible: true, faces }],
    children: [],
  };
}

const mockRoot: MockOccurrence[] = [
  part('Drawbar:1', '17x138x20mm', '#6b6f78', 18),
  part('HTD_5M_34T_17277434:1', '60x31x60mm', '#c9ccd2', 220),
  part('Belt:1', '95x30x162mm', '#2b2b2b', 64),
  {
    name: 'Spindle Assembly:1',
    dims: '120x240x120mm',
    color: '#9aa3b2',
    visible: true,
    bodies: [],
    children: [
      part('BF15_SYK:1', '70x20x48mm', '#4f7fd6', 40),
      part('BKBF_2005:1', '20x615x20mm', '#b8bcc4', 30),
      part('BSH_2005_Tuli:1', '38x75x38mm', '#d6a24f', 26),
    ],
  },
  part('Component48:2', '16x5x16mm', '#8a8f99', 10),
  part('Component10:1', '100x10x38mm', '#a3a7ad', 14),
  part('Component48:1', '16x5x16mm', '#8a8f99', 10),
  part('Hexagon Socket Head Cap Screw DIN EN ISO 4762 - M6 x 40:1', '10x46x10mm', '#3d3f44', 38),
  part('HTD_8M_22T_17477211:1', '60x38x60mm', '#c9ccd2', 180),
];

let mockViewport: string[] = [];
let mockLastOp: { op: OpName; tokens: string[] } | null = null;
let mockIsolation: Map<string, boolean> | null = null;
const OP_LABELS: Record<OpName, string> = {
  move: 'Move',
  mirror: 'Mirror',
  circPattern: 'Circular Pattern',
  rectPattern: 'Rectangular Pattern',
};

type Walked = { occ: MockOccurrence; path: string[]; depth: number; parent: MockOccurrence | null };

function walk(): Walked[] {
  const out: Walked[] = [];
  const step = (list: MockOccurrence[], path: string[], depth: number, parent: MockOccurrence | null) => {
    list.forEach((occ) => {
      const next = [...path, occ.name];
      out.push({ occ, path: next, depth, parent });
      step(occ.children, next, depth + 1, occ);
    });
  };
  step(mockRoot, [], 0, null);
  return out;
}

const occKey = (path: string[]) => `o:${path.join('+')}`;
const bodyKey = (path: string[], name: string) => `b:${path.join('+')}/${name}`;

function isShown(entry: Walked, all: Walked[]): boolean {
  if (!entry.occ.visible) return false;
  if (!entry.parent) return true;
  const parentEntry = all.find((item) => item.occ === entry.parent);
  return parentEntry ? isShown(parentEntry, all) : true;
}

function occurrenceItems(): ListItem[] {
  const all = walk();
  return all.map((entry, order) => ({
    id: occKey(entry.path),
    token: `tok:${occKey(entry.path)}`,
    kind: entry.occ.children.length ? 'assembly' : 'component',
    name: entry.occ.name,
    context: entry.path.slice(0, -1).join(' / '),
    depth: entry.depth,
    order,
    dims: entry.occ.dims,
    color: entry.occ.color,
    visible: entry.occ.visible,
    shown: isShown(entry, all),
    linked: false,
    childCount: entry.occ.children.length,
  }));
}

function bodyItems(): ListItem[] {
  const all = walk();
  const items: ListItem[] = [];
  all.forEach((entry) => {
    entry.occ.bodies.forEach((body) => {
      const id = bodyKey(entry.path, body.name);
      items.push({
        id,
        token: `tok:${id}`,
        kind: 'body',
        name: body.name,
        context: entry.occ.name,
        depth: 0,
        order: items.length,
        dims: body.dims,
        color: body.color,
        visible: body.visible,
        shown: body.visible && isShown(entry, all),
        linked: false,
        childCount: body.faces,
      });
    });
  });
  return items;
}

const SURFACES = ['Planar', 'Cylindrical', 'Planar', 'Conical', 'Planar', 'Toroidal', 'Freeform'];

function faceItems(tokens: string[]): Listing {
  const bodies = bodyItems();
  const wanted = new Set(tokens.map((token) => token.replace(/^tok:/, '')));
  const targets = wanted.size
    ? bodies.filter((body) => {
        if (wanted.has(body.id)) return true;
        const path = body.id.slice(2, body.id.lastIndexOf('/'));
        return [...wanted].some((key) => key.startsWith('o:') && (path === key.slice(2) || path.startsWith(`${key.slice(2)}+`)));
      })
    : bodies.filter((body) => body.shown);
  const items: ListItem[] = [];
  let warning = '';
  for (const body of targets) {
    for (let index = 0; index < body.childCount; index += 1) {
      if (items.length >= 2000) {
        warning = 'Showing the first 2000 faces. Check fewer bodies to see the rest.';
        return { mode: 'face', items, warning };
      }
      const surface = SURFACES[index % SURFACES.length];
      const id = `${body.id}#${index + 1}`;
      items.push({
        id,
        token: `tok:${id}`,
        kind: 'face',
        name: `${body.name} / Face ${index + 1}`,
        context: `${body.name} (${body.context})`,
        surface,
        depth: 0,
        order: items.length,
        dims: `${surface} \u00b7 ${(((index * 37) % 900) + 12).toFixed(0)}mm\u00b2`,
        color: body.color,
        visible: body.visible,
        shown: body.shown,
        linked: false,
        childCount: 0,
      });
    }
  }
  return { mode: 'face', items, warning };
}

function listing(mode: ListMode, tokens: string[] = []): Listing {
  if (mode === 'body') return { mode, items: bodyItems(), warning: '' };
  if (mode === 'face') return faceItems(tokens);
  return { mode, items: occurrenceItems(), warning: '' };
}

function findOcc(key: string): Walked | undefined {
  return walk().find((entry) => occKey(entry.path) === key);
}

function findBody(key: string) {
  for (const entry of walk()) {
    for (const body of entry.occ.bodies) {
      if (bodyKey(entry.path, body.name) === key) return { entry, body };
    }
  }
  return undefined;
}

function keysOf(tokens: unknown): string[] {
  if (!Array.isArray(tokens)) return [];
  return tokens.filter((token): token is string => typeof token === 'string').map((token) => token.replace(/^tok:/, ''));
}

function mockViewportSelection(): ViewportSelection {
  return { count: mockViewport.length, keys: [...mockViewport] };
}

function mockLast(): LastOp | null {
  return mockLastOp ? { op: mockLastOp.op, label: OP_LABELS[mockLastOp.op], count: mockLastOp.tokens.length } : null;
}

function mockFail(message: string): never {
  throw new FusionError(message);
}

function delay<T>(value: T, ms = 60): Promise<T> {
  return new Promise((resolve) => {
    window.setTimeout(() => resolve(value), ms);
  });
}

function setVisibility(keys: string[], on: boolean): number {
  let changed = 0;
  keys.forEach((key) => {
    const occ = findOcc(key);
    if (occ) {
      occ.occ.visible = on;
      changed += 1;
      return;
    }
    const body = findBody(key.split('#')[0]);
    if (body) {
      body.body.visible = on;
      changed += 1;
    }
  });
  return changed;
}

function runMockOp(op: OpName, keys: string[]): OpResult {
  if (keys.some((key) => key.includes('#'))) {
    mockFail(`${OP_LABELS[op]} works on components and bodies, not faces. Switch the list back to Component or Body.`);
  }
  if (!keys.length) mockFail(`Check at least one component or body to ${OP_LABELS[op].toLowerCase()}.`);
  const hasOcc = keys.some((key) => key.startsWith('o:'));
  const hasBody = keys.some((key) => key.startsWith('b:'));
  if (op !== 'move' && hasOcc && hasBody) {
    mockFail(`${OP_LABELS[op]} needs all components or all bodies. Do not mix types in one operation.`);
  }
  mockLastOp = { op, tokens: keys.map((key) => `tok:${key}`) };
  mockViewport = [...keys];
  window.setTimeout(() => dispatchEvent('viewportSelectionChanged', JSON.stringify(mockViewportSelection())), 20);
  return { op, label: OP_LABELS[op], count: keys.length, missing: 0, lastOp: mockLast() };
}

async function mockRequest<T>(action: string, payload?: unknown): Promise<T> {
  const data = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  const mode = (String(data.mode || 'component') as ListMode) || 'component';

  if (action === 'ready') {
    const prefersLight = window.matchMedia?.('(prefers-color-scheme: light)').matches;
    const ready: ReadyPayload = {
      hasDocument: true,
      designName: 'Linear Axis v12',
      theme: prefersLight ? 'light' : 'dark',
      viewport: mockViewportSelection(),
      lastOp: mockLast(),
      isolated: mockIsolation !== null,
      ...listing(mode, keysOf(data.tokens).map((key) => `tok:${key}`)),
    };
    return delay(ready as T);
  }

  if (action === 'items:list') {
    return delay(listing(mode, Array.isArray(data.tokens) ? (data.tokens as string[]) : []) as T);
  }

  if (action === 'faces:list') {
    return delay(listing('face', Array.isArray(data.tokens) ? (data.tokens as string[]) : []) as T);
  }

  if (action === 'select:viewport') {
    const keys = keysOf(data.tokens);
    mockViewport = keys;
    window.setTimeout(() => dispatchEvent('viewportSelectionChanged', JSON.stringify(mockViewportSelection())), 20);
    return delay({ selected: keys.length, missing: 0 } as SelectResult as T, 30);
  }

  if (action === 'selection:get') {
    return delay(mockViewportSelection() as T, 10);
  }

  if (action === 'vis:show' || action === 'vis:hide') {
    const keys = keysOf(data.tokens);
    if (!keys.length) mockFail(`Check at least one component or body to ${action === 'vis:show' ? 'show' : 'hide'}.`);
    const changed = setVisibility(keys, action === 'vis:show');
    return delay({ changed, missing: 0, isolated: mockIsolation !== null } as VisibilityResult as T, 40);
  }

  if (action === 'vis:isolate') {
    const keys = keysOf(data.tokens);
    if (!keys.length) mockFail('Check at least one component or body to isolate.');
    if (!mockIsolation) {
      mockIsolation = new Map();
      walk().forEach((entry) => mockIsolation!.set(occKey(entry.path), entry.occ.visible));
    }
    const keep = new Set(keys);
    let hidden = 0;
    walk().forEach((entry) => {
      const key = occKey(entry.path);
      const isKept = keep.has(key) || [...keep].some((k) => k.startsWith(`${key}+`) || k.startsWith(`b:${key.slice(2)}/`) || k.startsWith(`b:${key.slice(2)}+`));
      const insideKept = [...keep].some((k) => key.startsWith(`${k}+`));
      if (!isKept && !insideKept && entry.occ.visible) {
        entry.occ.visible = false;
        hidden += 1;
      } else if (isKept) {
        entry.occ.visible = true;
      }
    });
    return delay({ changed: hidden, missing: 0, isolated: true } as VisibilityResult as T, 40);
  }

  if (action === 'vis:restoreAll') {
    let changed = 0;
    walk().forEach((entry) => {
      const target = mockIsolation ? mockIsolation.get(occKey(entry.path)) ?? true : true;
      if (entry.occ.visible !== target) changed += 1;
      entry.occ.visible = target;
      if (!mockIsolation) entry.occ.bodies.forEach((body) => (body.visible = true));
    });
    mockIsolation = null;
    return delay({ changed, missing: 0, isolated: false } as VisibilityResult as T, 40);
  }

  if (action === 'item:rename') {
    const name = typeof data.name === 'string' ? data.name.trim() : '';
    if (!name) mockFail('Enter a name.');
    const key = String(data.token || '').replace(/^tok:/, '');
    const occ = findOcc(key);
    if (occ) {
      const suffix = occ.occ.name.match(/:\d+$/)?.[0] ?? ':1';
      occ.occ.name = `${name}${suffix}`;
      const id = occKey([...occ.path.slice(0, -1), occ.occ.name]);
      return delay({ id, token: `tok:${id}`, name: occ.occ.name } as RenameResult as T, 40);
    }
    const body = findBody(key);
    if (body) {
      body.body.name = name;
      const id = bodyKey(body.entry.path, name);
      return delay({ id, token: `tok:${id}`, name } as RenameResult as T, 40);
    }
    mockFail('Only components and bodies can be renamed.');
  }

  if (action === 'op:run') {
    return delay(runMockOp(String(data.op) as OpName, keysOf(data.tokens)) as T, 40);
  }

  if (action === 'op:repeat') {
    if (!mockLastOp) mockFail('Run Move, Mirror, or a pattern first.');
    return delay(runMockOp(mockLastOp.op, keysOf(mockLastOp.tokens)) as T, 40);
  }

  if (action === 'palette:close' || action === 'jsLog') {
    return { closed: true } as T;
  }

  mockFail(`Unknown action: ${action}`);
}
