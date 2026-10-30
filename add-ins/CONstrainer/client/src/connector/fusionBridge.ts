/*
 * fusionBridge
 * -------------
 * Typed request/response between the React palette and the Fusion add-in.
 * Outside Fusion (vite dev), an in-memory mock keeps the palette interactive.
 */

import type {
  AssemblyConstraintInfo,
  ConstraintList,
  ConstraintSelection,
  DesignIntent,
  ReadyPayload,
  SketchConstraint,
  SketchList,
  SketchSelection,
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
        console.error(`[CONstrainer] event listener for "${action}" threw`, error);
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
        console.log('[CONstrainer] adsk object not found; running in dev mock mode.');
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
    console.error(`[CONstrainer] send("${action}") failed`, error);
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

const LINE_A = 'ent-line-a';
const LINE_B = 'ent-line-b';

let mockSketches: SketchList = {
  components: [
    {
      name: 'Root',
      token: 'comp-root',
      sketches: [
        {
          name: 'Profile',
          token: 'sk-profile',
          isFullyConstrained: true,
          constraints: [
            {
              token: 'c-coincident',
              sketchToken: 'sk-profile',
              index: 0,
              type: 'coincident',
              label: 'Coincident',
              isDeletable: true,
              entities: [
                { role: 'point', kind: 'point', label: 'Point', token: 'ent-pt-1' },
                { role: 'entity', kind: 'line', label: 'Line', token: 'ent-line-c' },
              ],
            },
            {
              token: 'c-horizontal',
              sketchToken: 'sk-profile',
              index: 1,
              type: 'horizontal',
              label: 'Horizontal',
              isDeletable: true,
              entities: [{ role: 'line', kind: 'line', label: 'Line', token: 'ent-line-c' }],
            },
          ],
        },
        {
          name: 'Slot',
          token: 'sk-slot',
          isFullyConstrained: false,
          constraints: [
            {
              token: 'c-parallel',
              sketchToken: 'sk-slot',
              index: 0,
              type: 'parallel',
              label: 'Parallel',
              isDeletable: false,
              entities: [
                { role: 'lineOne', kind: 'line', label: 'Line', token: LINE_A },
                { role: 'lineTwo', kind: 'line', label: 'Line', token: LINE_B },
              ],
            },
            {
              token: 'c-vertical',
              sketchToken: 'sk-slot',
              index: 1,
              type: 'vertical',
              label: 'Vertical',
              isDeletable: true,
              entities: [{ role: 'line', kind: 'line', label: 'Line', token: LINE_A }],
            },
          ],
        },
      ],
    },
    {
      name: 'Bracket',
      token: 'comp-bracket',
      sketches: [
        {
          name: 'Holes',
          token: 'sk-holes',
          isFullyConstrained: false,
          constraints: [
            {
              token: 'c-concentric',
              sketchToken: 'sk-holes',
              index: 0,
              type: 'concentric',
              label: 'Concentric',
              isDeletable: true,
              entities: [
                { role: 'entityOne', kind: 'circle', label: 'Circle', token: 'ent-circ-1' },
                { role: 'entityTwo', kind: 'circle', label: 'Circle', token: 'ent-circ-2' },
              ],
            },
          ],
        },
      ],
    },
  ],
};

let mockConstraints: AssemblyConstraintInfo[] = [
  {
    token: 'ac-lid',
    name: 'Align1',
    typeLabel: 'Mate',
    sideOne: 'Bracket:1',
    sideTwo: 'Base:1',
    isSuppressed: false,
    isLightBulbOn: true,
    isVisible: true,
    health: 'ok',
    message: '',
    relationships: [
      {
        index: 0,
        name: 'Mate1',
        type: 'mate',
        isFlipped: false,
        isSuppressed: false,
        expression: '0 mm',
        parameterName: 'd12',
        entityOne: 'Planar face · Bracket:1',
        entityTwo: 'Planar face · Base:1',
        entityOneGeometry: 'Planar face',
        entityTwoGeometry: 'Planar face',
        entityOneComponent: 'Bracket:1',
        entityTwoComponent: 'Base:1',
      },
      {
        index: 1,
        name: 'Mate2',
        type: 'mate',
        isFlipped: true,
        isSuppressed: false,
        expression: '2 mm',
        parameterName: 'd13',
        entityOne: 'Edge · Bracket:1',
        entityTwo: 'Edge · Base:1',
        entityOneGeometry: 'Edge',
        entityTwoGeometry: 'Edge',
        entityOneComponent: 'Bracket:1',
        entityTwoComponent: 'Base:1',
      },
    ],
    component: 'Root',
    componentToken: 'comp-root',
  },
  {
    token: 'ac-angle',
    name: 'Angle1',
    typeLabel: 'Angle',
    sideOne: 'Lid:1',
    sideTwo: 'Enclosure:1',
    isSuppressed: false,
    isLightBulbOn: true,
    isVisible: true,
    health: 'warning',
    message: 'The constraint is over-defined.',
    relationships: [
      {
        index: 0,
        name: 'Angle1',
        type: 'angle',
        isFlipped: false,
        isSuppressed: false,
        expression: '90 deg',
        parameterName: 'd14',
        entityOne: 'Planar face · Lid:1',
        entityTwo: 'Planar face · Enclosure:1',
        entityOneGeometry: 'Planar face',
        entityTwoGeometry: 'Planar face',
        entityOneComponent: 'Lid:1',
        entityTwoComponent: 'Enclosure:1',
      },
    ],
    component: 'Root',
    componentToken: 'comp-root',
  },
];

function findMockConstraint(token: unknown) {
  const constraint = mockConstraints.find((item) => item.token === String(token ?? ''));
  if (!constraint) throw new FusionError('That assembly constraint is no longer in the design.');
  return constraint;
}

const mockSketchSelection: SketchSelection = {
  sketchName: 'Slot',
  sketchToken: 'sk-slot',
  entities: [
    { role: '', kind: 'line', label: 'Line', token: LINE_A },
    { role: '', kind: 'line', label: 'Line', token: LINE_B },
  ],
  compatible: [
    { type: 'collinear', label: 'Collinear', entityTokens: [LINE_A, LINE_B] },
    { type: 'parallel', label: 'Parallel', entityTokens: [LINE_A, LINE_B] },
    { type: 'perpendicular', label: 'Perpendicular', entityTokens: [LINE_A, LINE_B] },
    { type: 'equal', label: 'Equal', entityTokens: [LINE_A, LINE_B] },
  ],
  error: null,
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function mockIntent(): DesignIntent {
  const value = new URLSearchParams(window.location.search).get('intent');
  if (value === 'part' || value === 'assembly' || value === 'hybrid') return value;
  return 'hybrid';
}

function mockDocument() {
  const intent = mockIntent();
  return {
    doc: intent === 'part' ? 'Sample Part' : 'Sample Assembly',
    intent,
    assemblyAllowed: intent === 'assembly' || intent === 'hybrid',
  };
}

async function mockRequest<T>(action: string, payload?: unknown): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, 80));
  const body = (payload ?? {}) as Record<string, unknown>;

  switch (action) {
    case 'ready':
      return mockDocument() as ReadyPayload as T;
    case 'palette:minimize':
      return { minimized: true, dev: true } as T;
    case 'jsLog':
      return undefined as T;
    case 'sketch:list':
      return clone(mockSketches) as T;
    case 'sketch:readSelection':
      return clone(mockSketchSelection) as T;
    case 'sketch:select':
      return { selected: 1, highlighted: 1 } as T;
    case 'sketch:highlight':
      return { highlighted: 1 } as T;
    case 'sketch:clearHighlight':
      return { cleared: true } as T;
    case 'sketch:delete': {
      const token = String(body.token ?? '');
      let removed: SketchConstraint | undefined;
      for (const group of mockSketches.components) {
        for (const sketch of group.sketches) {
          const index = sketch.constraints.findIndex((item) => item.token === token);
          if (index >= 0) {
            removed = sketch.constraints[index];
            if (!removed.isDeletable) throw new FusionError('This constraint cannot be deleted.');
            sketch.constraints.splice(index, 1);
          }
        }
      }
      if (!removed) throw new FusionError('That constraint is no longer in the design.');
      return { sketchToken: '', label: removed.label } as T;
    }
    case 'sketch:add': {
      const type = String(body.type ?? '');
      const tokens = (body.entityTokens as string[]) ?? [];
      if (type === 'parallel' && tokens.includes(LINE_A) && tokens.includes(LINE_B)) {
        const slot = mockSketches.components[0].sketches[1];
        if (slot.constraints.some((item) => item.type === 'parallel')) {
          throw new FusionError('A parallel constraint already exists between these lines.');
        }
      }
      const option = mockSketchSelection.compatible.find((item) => item.type === type);
      const sketch = mockSketches.components
        .flatMap((group) => group.sketches)
        .find((item) => item.token === mockSketchSelection.sketchToken);
      if (!sketch || !option) throw new FusionError('That constraint cannot be added to this selection.');
      const created: SketchConstraint = {
        token: `c-${Date.now()}`,
        sketchToken: sketch.token,
        index: sketch.constraints.length,
        type,
        label: option.label,
        isDeletable: true,
        entities: mockSketchSelection.entities.map((entity, index) => ({
          ...entity,
          role: `entity${index + 1}`,
        })),
      };
      sketch.constraints.push(created);
      return { sketchToken: sketch.token, constraint: created } as T;
    }
    case 'constraint:list': {
      const document = mockDocument();
      const data: ConstraintList = {
        constraints: document.assemblyAllowed ? clone(mockConstraints) : [],
        supported: true,
        allowed: document.assemblyAllowed,
      };
      return data as T;
    }
    case 'constraint:readSelection': {
      const data: ConstraintSelection = {
        focus: { label: 'Planar face', kind: 'planarFace', token: 'geo-face-1', occurrenceName: 'Bracket:1' },
        direct: clone(mockConstraints.filter((item) => item.token === 'ac-lid')),
        component: [],
      };
      return data as T;
    }
    case 'constraint:highlight':
      findMockConstraint(body.token);
      return { highlighted: 1, selected: true, geometry: 2 } as T;
    case 'constraint:clearHighlight':
      return { cleared: true } as T;
    case 'constraint:select':
      findMockConstraint(body.token);
      return { selected: 1, geometry: 2 } as T;
    case 'constraint:rename': {
      const constraint = findMockConstraint(body.token);
      const name = String(body.name ?? '').trim();
      if (!name) throw new FusionError('Name is required.');
      constraint.name = name;
      return clone(constraint) as T;
    }
    case 'constraint:setSuppressed': {
      const constraint = findMockConstraint(body.token);
      constraint.isSuppressed = Boolean(body.suppressed);
      return clone(constraint) as T;
    }
    case 'constraint:setVisible': {
      const constraint = findMockConstraint(body.token);
      constraint.isLightBulbOn = Boolean(body.visible);
      constraint.isVisible = constraint.isLightBulbOn;
      return clone(constraint) as T;
    }
    case 'constraint:delete': {
      const constraint = findMockConstraint(body.token);
      mockConstraints = mockConstraints.filter((item) => item.token !== constraint.token);
      return { name: constraint.name } as T;
    }
    default:
      throw new FusionError(`Unknown action: ${action}`);
  }
}
