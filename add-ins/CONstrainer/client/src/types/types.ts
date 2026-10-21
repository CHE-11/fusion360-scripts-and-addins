export type TabId = 'sketches' | 'joints' | 'constraints' | 'help' | 'settings';

export type DesignIntent = 'part' | 'assembly' | 'hybrid' | 'none';

export type DocumentContext = {
  doc: string;
  intent: DesignIntent;
  jointsAllowed: boolean;
};

export type SketchEntityRef = {
  role: string;
  kind: string;
  label: string;
  token: string;
};

export type SketchConstraint = {
  token: string;
  sketchToken: string;
  index: number;
  type: string;
  label: string;
  isDeletable: boolean;
  entities: SketchEntityRef[];
  // Set when Fusion drew a coincident glyph for curves that share a sketch point.
  // That case is not a CoincidentConstraint in geometricConstraints.
  sharedPointToken?: string;
};

export type SketchInfo = {
  name: string;
  token: string;
  isFullyConstrained: boolean;
  constraints: SketchConstraint[];
};

export type SketchComponentGroup = {
  name: string;
  token: string;
  sketches: SketchInfo[];
};

export type SketchList = {
  components: SketchComponentGroup[];
};

export type CompatibleConstraint = {
  type: string;
  label: string;
  entityTokens: string[];
};

export type SketchSelection = {
  sketchName: string;
  sketchToken: string;
  entities: SketchEntityRef[];
  compatible: CompatibleConstraint[];
  error: string | null;
};

export type JointMotion = 'rigid' | 'revolute' | 'slider' | 'cylindrical' | 'pinSlot' | 'planar' | 'ball';

export type ValueKind = 'none' | 'angle' | 'distance';

export type JointKind = 'joint' | 'asBuilt';

export type JointInfo = {
  token: string;
  name: string;
  kind: JointKind;
  warning: string;
  motion: string;
  motionLabel: string;
  sideOne: string;
  sideTwo: string;
  isAsBuilt: boolean;
  isSuppressed: boolean;
  isLightBulbOn: boolean;
  isVisible: boolean;
  valueLabel: string;
  component: string;
  componentToken: string;
};

export type JointList = {
  joints: JointInfo[];
  intent: DesignIntent;
  jointsAllowed: boolean;
};

export type JointGeometryRef = {
  label: string;
  token: string;
  kind: string;
  occurrenceToken: string;
  occurrenceName: string;
};

export type JointFocusKind = 'planarFace' | 'face' | 'curve' | 'point' | 'jointOrigin' | 'body' | 'component';

export type JointFocus = {
  label: string;
  kind: JointFocusKind;
  token: string;
  occurrenceName: string;
};

export type JointRelated = {
  direct: JointInfo[];
  component: JointInfo[];
};

export type JointOccurrenceRef = {
  name: string;
  token: string;
};

export type JointMotionOption = {
  type: JointMotion;
  label: string;
  valueKind: ValueKind;
};

export type JointSelection = {
  geometries: JointGeometryRef[];
  occurrences: JointOccurrenceRef[];
  focus: JointFocus | null;
  related: JointRelated;
  error: string | null;
};

export const JOINT_MOTIONS: JointMotionOption[] = [
  { type: 'rigid', label: 'Rigid', valueKind: 'none' },
  { type: 'revolute', label: 'Revolute', valueKind: 'angle' },
  { type: 'slider', label: 'Slider', valueKind: 'distance' },
  { type: 'cylindrical', label: 'Cylindrical', valueKind: 'angle' },
  { type: 'pinSlot', label: 'Pin-slot', valueKind: 'distance' },
  { type: 'planar', label: 'Planar', valueKind: 'angle' },
  { type: 'ball', label: 'Ball', valueKind: 'none' },
];

export type ConstraintRelationshipType = 'mate' | 'angle';

export type ConstraintRelationship = {
  index: number;
  name: string;
  type: ConstraintRelationshipType;
  isFlipped: boolean;
  isSuppressed: boolean;
  expression: string;
  parameterName: string;
  entityOne: string;
  entityTwo: string;
};

export type ConstraintHealth = 'ok' | 'warning' | 'error';

export type AssemblyConstraintInfo = {
  token: string;
  name: string;
  typeLabel: string;
  sideOne: string;
  sideTwo: string;
  isSuppressed: boolean;
  isLightBulbOn: boolean;
  isVisible: boolean;
  health: ConstraintHealth;
  message: string;
  relationships: ConstraintRelationship[];
  component: string;
  componentToken: string;
};

export type ConstraintList = {
  constraints: AssemblyConstraintInfo[];
  supported: boolean;
  allowed: boolean;
};

export type ConstraintSelection = {
  focus: JointFocus | null;
  direct: AssemblyConstraintInfo[];
  component: AssemblyConstraintInfo[];
};

export const EMPTY_CONSTRAINT_SELECTION: ConstraintSelection = {
  focus: null,
  direct: [],
  component: [],
};

export type ReadyPayload = DocumentContext;

export type SelectionChangedPayload = {
  sketch: SketchSelection;
  joint: JointSelection;
  constraint?: ConstraintSelection;
  document?: DocumentContext;
};

export const EMPTY_SKETCH_SELECTION: SketchSelection = {
  sketchName: '',
  sketchToken: '',
  entities: [],
  compatible: [],
  error: null,
};

export const EMPTY_JOINT_SELECTION: JointSelection = {
  geometries: [],
  occurrences: [],
  focus: null,
  related: { direct: [], component: [] },
  error: null,
};
