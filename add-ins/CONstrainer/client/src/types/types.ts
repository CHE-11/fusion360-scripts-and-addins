export type TabId = 'sketches' | 'constraints' | 'help';

export type DesignIntent = 'part' | 'assembly' | 'hybrid' | 'none';

export type DocumentContext = {
  doc: string;
  intent: DesignIntent;
  assemblyAllowed: boolean;
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

export type FocusKind = 'planarFace' | 'face' | 'curve' | 'point' | 'jointOrigin' | 'body' | 'component';

export type SelectionFocus = {
  label: string;
  kind: FocusKind;
  token: string;
  occurrenceName: string;
};

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
  entityOneGeometry: string;
  entityTwoGeometry: string;
  entityOneComponent: string;
  entityTwoComponent: string;
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
  focus: SelectionFocus | null;
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
