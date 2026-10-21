/*
 * fusionBridge
 * -------------
 * A single, typed communication layer between the React palette and the
 * Fusion 360 Python add-in.
 *
 * Two directions:
 *  1. request(action, payload)  -> JS calls Python and awaits a JSON response.
 *     Fusion's `window.adsk.fusionSendData` returns the handler's `returnData`
 *     synchronously (or as a promise), so this maps cleanly to request/response.
 *  2. onEvent(action, cb)       -> Python pushes to JS via `sendInfoToHTML`.
 *     We install a single `window.fusionJavaScriptHandler` that fans out to
 *     registered listeners.
 *
 * When `window.adsk` is missing (e.g. `vite dev` in a normal browser) we fall
 * back to an in-memory mock so the UI stays fully interactive during dev.
 */

import type {
  BrowseParamsFileResult,
  FeatureSelection,
  GlobalParam,
  ParamsLocation,
  ProjectParam,
  PushResult,
} from '../types/types';
import { markSynced } from '../utils/lastSync';

// ---------------------------------------------------------------------------
// Response envelope
// ---------------------------------------------------------------------------

export type FusionResponse<T> = { ok: true; data: T } | { ok: false; error: string };

export class FusionError extends Error {}

// ---------------------------------------------------------------------------
// Inbound event dispatch (Python -> JS)
// ---------------------------------------------------------------------------

type EventListener = (data: string) => void;

const eventListeners = new Map<string, Set<EventListener>>();

function dispatchEvent(action: string, messageString: string): string {
  if (action === 'loadGlobal' || action === 'docActivated') {
    markSynced();
  }
  const listeners = eventListeners.get(action);
  if (listeners) {
    listeners.forEach((cb) => {
      try {
        cb(messageString);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error(`[ProParams] event listener for "${action}" threw`, e);
      }
    });
  }
  return 'OK';
}

/** Subscribe to a pushed event from the Python add-in. Returns an unsubscribe fn. */
export function onEvent(action: string, cb: EventListener): () => void {
  let set = eventListeners.get(action);
  if (!set) {
    set = new Set();
    eventListeners.set(action, set);
  }
  set.add(cb);
  return () => {
    set?.delete(cb);
  };
}

// Install the global handler Fusion calls for `sendInfoToHTML`.
function installHandler() {
  window.fusionJavaScriptHandler = {
    handle: (action: string, messageString: string) => {
      if (action === 'debugger') {
        // eslint-disable-next-line no-debugger
        debugger;
        return 'OK';
      }
      return dispatchEvent(action, messageString);
    },
  };
}

// ---------------------------------------------------------------------------
// adsk readiness
// ---------------------------------------------------------------------------

const MAX_WAIT_MS = 15000;

export function hasAdsk(): boolean {
  return !!(window.adsk && typeof window.adsk.fusionSendData === 'function');
}

let readyPromise: Promise<boolean> | null = null;

/** Resolves true once `window.adsk` is available, false after a timeout (dev). */
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
        // eslint-disable-next-line no-console
        console.log('[ProParams] adsk object not found; running in dev mock mode.');
        resolve(false);
      }
    }, 100);
  });
  return readyPromise;
}

// Install the handler eagerly too, so events can arrive before waitForAdsk resolves.
installHandler();

// ---------------------------------------------------------------------------
// Outbound request (JS -> Python)
// ---------------------------------------------------------------------------

/**
 * Send a request to the Python add-in and await its JSON response.
 * Throws FusionError when the backend responds with `{ ok: false }`.
 */
export async function request<T = unknown>(action: string, payload?: unknown): Promise<T> {
  if (!hasAdsk()) {
    const data = await mockRequest<T>(action, payload);
    markSynced();
    return data;
  }

  const raw = await Promise.resolve(
    window.adsk!.fusionSendData(action, JSON.stringify(payload ?? {}))
  );

  if (raw == null || raw === '') {
    throw new FusionError(`Empty response from Fusion for "${action}"`);
  }

  let parsed: FusionResponse<T>;
  try {
    parsed = JSON.parse(raw) as FusionResponse<T>;
  } catch {
    // Backend returned a bare string (e.g. legacy "OK"). Treat as success.
    markSynced();
    return raw as unknown as T;
  }

  if (parsed && typeof parsed === 'object' && 'ok' in parsed) {
    if (parsed.ok) {
      markSynced();
      return parsed.data;
    }
    throw new FusionError(parsed.error || `Request "${action}" failed`);
  }

  // Unknown shape; hand it back as-is.
  markSynced();
  return parsed as unknown as T;
}

/** Fire-and-forget message (no response expected). */
export function send(action: string, payload?: unknown): void {
  try {
    if (hasAdsk()) {
      window.adsk!.fusionSendData(action, JSON.stringify(payload ?? {}));
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error(`[ProParams] send("${action}") failed`, e);
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

/** Perform the initial handshake so the backend can push data. */
export async function sendReady(): Promise<void> {
  const ready = await waitForAdsk();
  if (ready) send('ready', {});
}

// ---------------------------------------------------------------------------
// Dev mock (only used when window.adsk is absent)
// ---------------------------------------------------------------------------

const MOCK_DEFAULT_PARAMS_PATH = 'C:\\Users\\dev\\ProParams\\ProParams_global.json';
let mockParamsPath = MOCK_DEFAULT_PARAMS_PATH;

function mockParamsLocation(): ParamsLocation {
  return {
    globalParamsPath: mockParamsPath,
    defaultPath: MOCK_DEFAULT_PARAMS_PATH,
    isCustom: mockParamsPath !== MOCK_DEFAULT_PARAMS_PATH,
  };
}

let mockGlobal: GlobalParam[] = [
  { name: 'wall_thickness', expression: '3 mm', unit: 'mm', comment: 'Default wall', category: 'Defaults' },
  { name: 'tolerance', expression: '0.1 mm', unit: 'mm', comment: 'Fit tolerance', category: 'Defaults' },
  { name: 'bolt_count', expression: '4', unit: '', comment: '', category: 'Hardware' },
];

const mockProject: ProjectParam[] = [
  { name: 'length', expression: '120 mm', value: '120.0', unit: 'mm', comment: 'Overall length', isUserParam: true, isDeletable: true, isEditable: true },
  { name: 'width', expression: '80 mm', value: '80.0', unit: 'mm', comment: '', isUserParam: true, isDeletable: true, isEditable: true },
  { name: 'd12', expression: '5 mm', value: '5.0', unit: 'mm', comment: 'Fillet radius', isUserParam: false, isDeletable: false, isEditable: true },
  { name: 'd5', expression: '42 mm', value: '42.0', unit: 'mm', comment: 'Driven measurement', isUserParam: false, isDeletable: false, isEditable: false },
];

let mockFeature: FeatureSelection = {
  hasSelection: true,
  entity: { label: 'Face (sample)', entityType: 'BRepFace' },
  params: [
    { name: 'face_offset', expression: '2 mm', value: '2.0', unit: 'mm', comment: 'Machining offset' },
  ],
};

async function mockRequest<T>(action: string, payload?: unknown): Promise<T> {
  // Simulate a little latency so loading states are visible in dev.
  await new Promise((r) => setTimeout(r, 120));
  const body = (payload ?? {}) as Record<string, unknown>;

  switch (action) {
    case 'settings:get':
      return mockParamsLocation() as unknown as T;
    case 'settings:browse': {
      const requested = typeof body.globalParamsPath === 'string' ? body.globalParamsPath.trim() : '';
      const fileName = requested.split(/[\\/]/).pop() || 'ProParams_global.json';
      const result: BrowseParamsFileResult = {
        cancelled: false,
        path: `\\\\shared\\ProParams\\${fileName}`,
      };
      return result as unknown as T;
    }
    case 'settings:reveal':
      return { opened: true } as unknown as T;
    case 'settings:set': {
      const next = typeof body.globalParamsPath === 'string' ? body.globalParamsPath.trim() : '';
      mockParamsPath = next || MOCK_DEFAULT_PARAMS_PATH;
      return mockParamsLocation() as unknown as T;
    }
    case 'global:list':
      return mockGlobal.map((param) => ({ ...param })) as unknown as T;
    case 'global:save':
      mockGlobal = (body.params as GlobalParam[]) ?? mockGlobal;
      return undefined as unknown as T;
    case 'global:pushToDesign': {
      const incoming = (Array.isArray(body.params) ? body.params : mockGlobal) as GlobalParam[];
      let created = 0;
      let updated = 0;
      for (const globalParam of incoming) {
        const existing = mockProject.find((param) => param.name === globalParam.name && param.isUserParam);
        if (existing) {
          existing.expression = globalParam.expression;
          existing.value = globalParam.expression;
          existing.unit = globalParam.unit ?? '';
          existing.comment = globalParam.comment ?? '';
          updated += 1;
        } else {
          mockProject.push({
            name: globalParam.name,
            expression: globalParam.expression,
            value: globalParam.expression,
            unit: globalParam.unit ?? '',
            comment: globalParam.comment ?? '',
            isUserParam: true,
            isDeletable: true,
            isEditable: true,
          });
          created += 1;
        }
      }
      return { created, updated, errors: [] } as PushResult as unknown as T;
    }

    case 'project:list': {
      const globalNames = new Set(mockGlobal.map((param) => param.name));
      return mockProject
        .filter((param) => !param.isUserParam || !globalNames.has(param.name))
        .map((param) => ({ ...param })) as unknown as T;
    }
    case 'project:add': {
      const name = String(body.name);
      if (mockGlobal.some((param) => param.name === name)) {
        throw new FusionError(`Cannot create "${name}". That name matches a global parameter.`);
      }
      const p: ProjectParam = {
        name,
        expression: String(body.expression),
        value: '',
        unit: String(body.unit ?? ''),
        comment: String(body.comment ?? ''),
        isUserParam: true,
        isDeletable: true,
        isEditable: true,
      };
      mockProject.push(p);
      return p as unknown as T;
    }
    case 'project:update': {
      const nextName = String(body.name);
      if (nextName !== String(body.originalName) && mockGlobal.some((param) => param.name === nextName)) {
        throw new FusionError(
          `Cannot rename "${String(body.originalName)}" to "${nextName}". That name matches a global parameter.`
        );
      }
      const idx = mockProject.findIndex((p) => p.name === body.originalName);
      if (idx >= 0) {
        mockProject[idx] = {
          ...mockProject[idx],
          name: String(body.name),
          expression: String(body.expression),
          unit: String(body.unit ?? mockProject[idx].unit ?? ''),
          comment: String(body.comment ?? ''),
        };
        return mockProject[idx] as unknown as T;
      }
      throw new FusionError('Parameter not found');
    }
    case 'project:delete': {
      const i = mockProject.findIndex((p) => p.name === body.name);
      if (i >= 0) mockProject.splice(i, 1);
      return undefined as unknown as T;
    }

    case 'feature:readSelection':
      return mockFeature as unknown as T;
    case 'feature:add': {
      if (!mockFeature.hasSelection) throw new FusionError('Nothing selected');
      mockFeature = {
        ...mockFeature,
        params: [
          ...mockFeature.params,
          {
            name: String(body.name),
            expression: String(body.expression),
            value: '',
            unit: String(body.unit ?? ''),
            comment: String(body.comment ?? ''),
          },
        ],
      };
      return mockFeature as unknown as T;
    }
    case 'feature:update': {
      mockFeature = {
        ...mockFeature,
        params: mockFeature.params.map((p) =>
          p.name === body.originalName
            ? {
                ...p,
                name: String(body.name),
                expression: String(body.expression),
                unit: String(body.unit ?? p.unit ?? ''),
                comment: String(body.comment ?? ''),
              }
            : p
        ),
      };
      return mockFeature as unknown as T;
    }
    case 'feature:delete': {
      mockFeature = {
        ...mockFeature,
        params: mockFeature.params.filter((p) => p.name !== body.name),
      };
      return mockFeature as unknown as T;
    }
    case 'feature:listAll':
      return { entities: [] } as unknown as T;

    default:
      return undefined as unknown as T;
  }
}
