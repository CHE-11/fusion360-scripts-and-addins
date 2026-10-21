// ---------------------------------------------------------------------------
// Shared parameter types for the three ProParams scopes.
// ---------------------------------------------------------------------------

/** Which tab/scope a parameter belongs to. */
export type ParamScope = 'global' | 'project' | 'feature';

/**
 * Global parameters live in a cross-document JSON store and can be pushed into
 * any open design on demand. `category` is an optional grouping tag (migrated
 * from the legacy per-project CSV column).
 */
export type GlobalParam = {
  name: string;
  expression: string;
  unit?: string;
  comment?: string;
  category?: string;
};

/**
 * Project parameters mirror the active design's local parameters.
 * User parameters created in this design and driving model dimensions
 * (sketch and feature sizes) are editable. Parameters pushed from the global
 * store are omitted. Driven dimensions, which only report a measured value,
 * stay read-only (`isEditable=false`).
 */
export type ProjectParam = {
  name: string;
  expression: string;
  value: string;
  unit?: string;
  comment?: string;
  isUserParam: boolean;
  isDeletable: boolean;
  isEditable: boolean;
};

/**
 * Feature parameters are real user parameters associated with a selected
 * entity (face/edge/body/sketch) via a Fusion attribute, so they both drive
 * geometry and travel with that entity.
 */
export type FeatureParam = {
  name: string;
  expression: string;
  value?: string;
  unit?: string;
  comment?: string;
};

/** Description of the entity currently selected in the viewport. */
export type FeatureEntity = {
  label: string;
  entityType: string;
};

/** Result of reading the current viewport selection. */
export type FeatureSelection = {
  hasSelection: boolean;
  entity?: FeatureEntity;
  params: FeatureParam[];
};

/** Result of pushing global params into a design. */
export type PushResult = {
  created: number;
  updated: number;
  errors: string[];
};

/** Where the shared global-parameter JSON file is stored. */
export type ParamsLocation = {
  globalParamsPath: string;
  defaultPath: string;
  isCustom: boolean;
};

/** Folder picker result. `path` is the JSON file that would be used. */
export type BrowseParamsFileResult = {
  cancelled: boolean;
  path: string;
};

// ---------------------------------------------------------------------------
// Request payloads (JS -> Python)
// ---------------------------------------------------------------------------

export type AddParamPayload = {
  name: string;
  expression: string;
  unit?: string;
  comment?: string;
};

export type UpdateParamPayload = {
  originalName: string;
  name: string;
  expression: string;
  unit?: string;
  comment?: string;
};

export type DeleteParamPayload = {
  name: string;
};

// ---------------------------------------------------------------------------
// Tab identifiers
// ---------------------------------------------------------------------------

export type TabId = 'global' | 'project' | 'feature';
