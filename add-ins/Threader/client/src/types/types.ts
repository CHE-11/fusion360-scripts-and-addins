export type TabId = 'thread' | 'insert' | 'adjust' | 'help';

export type Gender = 'male' | 'female';
export type Build = 'inset' | 'outset';
export type Family = 'printable' | 'iso' | 'unc';
export type Mating = 'plastic' | 'metal';

export type SizeRow = {
  size: string;
  majorMm: number;
  pitchMm: number;
};

export type InsertRow = {
  size: string;
  holeMm: number;
  depthMm: number;
  chamferMm: number;
};

export type StandardsCatalog = {
  iso: SizeRow[];
  unc: SizeRow[];
  inserts: InsertRow[];
  plasticClearanceMm: number;
  metalClearanceMm: number;
  threadNudgeMm: number;
  insertNudgeMm: number;
  defaultNozzleMm: number;
  defaultLayerMm: number;
  defaultFlankDeg: number;
};

export type ReadyPayload = {
  doc?: string;
  standards?: StandardsCatalog;
};

export type CylinderSelection = {
  token: string;
  bodyToken?: string;
  radiusMm: number;
  diameterMm: number;
  lengthMm: number;
  gender: Gender;
  axisVertical: boolean;
};

export type PlanarSelection = { token: string };
export type CenterSelection = { token: string; kind: 'edge' | 'point' };

export type InsertSelection = {
  faceCount: number;
  pointCount: number;
};

export type SelectionPayload = {
  cylinder: CylinderSelection | null;
  planar: PlanarSelection | null;
  center: CenterSelection | null;
  inserts: InsertSelection;
  document?: ReadyPayload;
};

export type ThreadPreview = {
  gender: Gender;
  build: Build;
  family: Family;
  size: string;
  mating: Mating;
  pitchMm: number;
  flankDeg: number;
  clearanceMm: number;
  toothMm: number;
  crestMm: number;
  majorMm: number;
  minorMm: number;
  turns: number;
  lengthMm: number;
  offsetMm: number;
  chamferMm: number;
  leadMm: number;
  rightHand: boolean;
  faceRole: string;
  label: string;
  warnings: string[];
  notes: string[];
  operation: 'join' | 'cut';
};

export type ThreadFeature = {
  id: string;
  kind: 'thread';
  label: string;
  gender: Gender;
  build: Build;
  family: Family;
  size: string;
  mating: Mating;
  rightHand: boolean;
  lead: boolean;
  chamfer?: boolean;
  clearanceMm: number | null;
  pitchMm: number | null;
  lengthMm: number | null;
  offsetMm: number | null;
  leadMm: number | null;
  chamferMm?: number | null;
  flankDeg: number | null;
};

export type InsertFeature = {
  id: string;
  kind: 'insert';
  label: string;
  size: string;
  holeMm: number | null;
  depthMm: number | null;
  chamferMm: number | null;
};

export type FeatureRow = ThreadFeature | InsertFeature;

export type FeatureList = {
  features: FeatureRow[];
};

export type CreateResult = {
  feature: FeatureRow | null;
  preview?: ThreadPreview;
  warnings: string[];
};

export const EMPTY_SELECTION: SelectionPayload = {
  cylinder: null,
  planar: null,
  center: null,
  inserts: { faceCount: 0, pointCount: 0 },
};
