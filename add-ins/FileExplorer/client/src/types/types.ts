export type NodeKind = 'hub' | 'project' | 'folder' | 'file';

export type ExplorerNode = {
  id: string;
  kind: NodeKind;
  name: string;
  extension: string;
  version: number | null;
  modifiedAt: number | null;
  hasParents: boolean;
  hasChildren: boolean;
  parentId: string;
  projectId: string;
};

export type Listing = {
  location: ExplorerNode;
  crumbs: ExplorerNode[];
  children: ExplorerNode[];
  activeFileId: string;
  containerId: string;
};

export type ReadyPayload = {
  hubs: ExplorerNode[];
  activeHubId: string;
  activeFileId: string;
  listing: Listing | null;
  listingError: string;
};

export type ReferencesPayload = {
  file: ExplorerNode;
  parents: ExplorerNode[];
  children: ExplorerNode[];
  warning: string;
};

export type SearchProgress = {
  searchId: string;
  matches: ExplorerNode[];
  scanned: number;
  done: boolean;
  truncated: boolean;
  cancelled: boolean;
  replace?: boolean;
  indexing?: boolean;
};

export type SearchStartPayload = {
  searchId: string;
  started: boolean;
  indexed?: boolean;
  progress?: SearchProgress;
};

export type IndexStepPayload = {
  progress: SearchProgress | null;
};

export type ActiveFilePayload = {
  activeFileId: string;
};

export type ActiveFileLocation = {
  fileId: string;
  listing: Listing;
};

export type LocationTarget = {
  id: string;
  kind: NodeKind;
};
