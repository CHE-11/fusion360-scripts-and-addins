export type ItemKind = 'component' | 'assembly' | 'body' | 'face';

export type ListMode = 'component' | 'body' | 'assembly' | 'face';

export type SortOrder = 'az' | 'browser';

export type Theme = 'dark' | 'light';

export type OpName = 'move' | 'mirror' | 'circPattern' | 'rectPattern';

export type ListItem = {
  /** Stable key for checkbox state; built from occurrence paths and names. */
  id: string;
  /** Fusion entity token used to find the entity again. */
  token: string;
  kind: ItemKind;
  name: string;
  context: string;
  depth: number;
  /** Position in Fusion's browser order. */
  order: number;
  dims: string;
  color: string;
  /** The item's own light bulb. */
  visible: boolean;
  /** Whether it is actually drawn (parents can hide it). */
  shown: boolean;
  linked: boolean;
  childCount: number;
  surface?: string;
};

export type FaceItem = ListItem & { kind: 'face'; surface: string };

export type ViewportSelection = {
  count: number;
  keys: string[];
};

export type LastOp = {
  op: OpName;
  label: string;
  count: number;
};

export type Listing = {
  mode: ListMode;
  items: ListItem[];
  warning: string;
};

export type ReadyPayload = Listing & {
  hasDocument: boolean;
  designName: string;
  theme: Theme | null;
  viewport: ViewportSelection;
  lastOp: LastOp | null;
  isolated: boolean;
};

export type SelectResult = {
  selected: number;
  missing: number;
};

export type VisibilityResult = {
  changed: number;
  missing: number;
  isolated: boolean;
};

export type RenameResult = {
  id: string;
  token: string;
  name: string;
};

export type OpResult = {
  op: OpName;
  label: string;
  count: number;
  missing: number;
  lastOp: LastOp | null;
};
