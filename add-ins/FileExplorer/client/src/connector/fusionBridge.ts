/*
 * fusionBridge
 * -------------
 * Typed request/response between the React palette and the Fusion add-in.
 * Outside Fusion (vite dev), an in-memory hub keeps the explorer interactive.
 */

import type {
  ActiveFileLocation,
  ExplorerNode,
  Listing,
  ReadyPayload,
  ReferencesPayload,
} from '../types/types';
import { sortNodes } from '../utils/nodes';

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
        console.error(`[FileExplorer] event listener for "${action}" threw`, error);
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
        console.log('[FileExplorer] adsk object not found; running in dev mock mode.');
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
    console.log(`[FileExplorer:${level}]`, message, extra ?? '');
    return;
  }
  void request('jsLog', { level, message, extra }).catch(() => {
    // Logging must not throw into the palette.
  });
}

type MockFile = {
  id: string;
  name: string;
  extension: string;
  version: number;
  modifiedAt: number;
  parentRefs: string[];
  childRefs: string[];
};

type MockFolder = {
  id: string;
  name: string;
  folders: MockFolder[];
  files: MockFile[];
};

type MockProject = {
  id: string;
  name: string;
  hubId: string;
  root: MockFolder;
};

type MockHub = {
  id: string;
  name: string;
  projects: MockProject[];
};

type FoundFolder = {
  folder: MockFolder;
  parent: MockFolder | null;
  project: MockProject;
  hub: MockHub;
};

type FoundFile = {
  file: MockFile;
  folder: MockFolder;
  project: MockProject;
  hub: MockHub;
};

const now = Math.floor(Date.now() / 1000);
const hoursAgo = (hours: number) => now - Math.round(hours * 3600);

function file(
  id: string,
  name: string,
  extension: string,
  version: number,
  modifiedAt: number,
  parentRefs: string[] = [],
  childRefs: string[] = []
): MockFile {
  return { id, name, extension, version, modifiedAt, parentRefs, childRefs };
}

function folder(id: string, name: string, folders: MockFolder[], files: MockFile[]): MockFolder {
  return { id, name, folders, files };
}

const hubs: MockHub[] = [
  {
    id: 'hub-studio',
    name: 'Studio',
    projects: [
      {
        id: 'proj-arm',
        name: 'Robot Arm',
        hubId: 'hub-studio',
        root: folder('folder-arm-root', 'Robot Arm', [
          folder('folder-hardware', 'Hardware', [
            folder('folder-brackets', 'Brackets', [], [
              file('file-bracket', 'Bracket', 'f3d', 14, hoursAgo(2), ['file-bracket-dwg', 'file-assembly']),
              file('file-wrist', 'Wrist Link', 'f3d', 6, hoursAgo(5), ['file-assembly']),
              file('file-cover', 'Cover Plate', 'f3d', 3, hoursAgo(30), []),
              file('file-bracket-dwg', 'Bracket Drawing', 'f2d', 4, hoursAgo(26), [], ['file-bracket']),
            ]),
            folder('folder-fasteners', 'Fasteners', [], [
              file('file-screw', 'M5 Screw', 'f3d', 3, hoursAgo(10), ['file-assembly']),
              file('file-insert', 'Heat Set Insert', 'f3d', 2, hoursAgo(80), ['file-assembly']),
            ]),
          ], []),
          folder('folder-electronics', 'Electronics', [], [
            file('file-sch', 'Controller', 'fsch', 6, hoursAgo(8), []),
            file('file-brd', 'Controller Board', 'fbrd', 6, hoursAgo(8), ['file-assembly']),
            file('file-notes', 'Harness Notes', 'pdf', 1, hoursAgo(100), []),
          ]),
        ], [
          file('file-assembly', 'Arm Assembly', 'f3d', 30, hoursAgo(1), ['file-arm-dwg'], ['file-bracket', 'file-wrist', 'file-screw', 'file-insert', 'file-brd']),
          file('file-arm-dwg', 'Arm Drawing', 'f2d', 8, hoursAgo(4), [], ['file-assembly']),
        ]),
      },
      {
        id: 'proj-archive',
        name: 'Archive',
        hubId: 'hub-studio',
        root: folder('folder-archive-root', 'Archive', [], [
          file('file-plate', 'Old Plate', 'f3d', 1, hoursAgo(400), []),
        ]),
      },
    ],
  },
  {
    id: 'hub-personal',
    name: 'Personal',
    projects: [
      {
        id: 'proj-sandbox',
        name: 'Sandbox',
        hubId: 'hub-personal',
        root: folder('folder-sandbox-root', 'Sandbox', [], [
          file('file-sketch', 'Sketch Dump', 'f3d', 2, hoursAgo(12), ['file-test-dwg']),
          file('file-test-dwg', 'Test Drawing', 'f2d', 1, hoursAgo(15), [], ['file-sketch']),
        ]),
      },
    ],
  },
];

let activeFileId = 'file-bracket';
let activeSearchId = '';
const searchTimers: number[] = [];

function clearSearchTimers() {
  while (searchTimers.length) {
    const timer = searchTimers.pop();
    if (timer) window.clearTimeout(timer);
  }
}

function walkFolders(root: MockFolder, visit: (folder: MockFolder, parent: MockFolder | null) => void) {
  const step = (current: MockFolder, parent: MockFolder | null) => {
    visit(current, parent);
    current.folders.forEach((child) => step(child, current));
  };
  step(root, null);
}

function findProject(projectId: string): { project: MockProject; hub: MockHub } | null {
  for (const hub of hubs) {
    const project = hub.projects.find((item) => item.id === projectId);
    if (project) return { project, hub };
  }
  return null;
}

function findFolder(folderId: string): FoundFolder | null {
  for (const hub of hubs) {
    for (const project of hub.projects) {
      let found: FoundFolder | null = null;
      walkFolders(project.root, (folder, parent) => {
        if (folder.id === folderId) found = { folder, parent, project, hub };
      });
      if (found) return found;
    }
  }
  return null;
}

function findFile(fileId: string): FoundFile | null {
  for (const hub of hubs) {
    for (const project of hub.projects) {
      let found: FoundFile | null = null;
      walkFolders(project.root, (folder) => {
        const file = folder.files.find((item) => item.id === fileId);
        if (file) found = { file, folder, project, hub };
      });
      if (found) return found;
    }
  }
  return null;
}

function hubNode(hub: MockHub): ExplorerNode {
  return node(hub.id, 'hub', hub.name, { hasChildren: true });
}

function projectNode(project: MockProject): ExplorerNode {
  return node(project.id, 'project', project.name, {
    parentId: project.hubId,
    projectId: project.id,
    hasChildren: true,
  });
}

function folderNode(item: MockFolder, project: MockProject, parentId: string): ExplorerNode {
  return node(item.id, 'folder', item.name, {
    parentId,
    projectId: project.id,
    hasChildren: true,
  });
}

function fileNode(item: MockFile, project: MockProject, parentId: string): ExplorerNode {
  return node(item.id, 'file', item.name, {
    extension: item.extension,
    version: item.version,
    modifiedAt: item.modifiedAt,
    hasParents: item.parentRefs.length > 0,
    hasChildren: item.childRefs.length > 0,
    parentId,
    projectId: project.id,
  });
}

function node(
  id: string,
  kind: ExplorerNode['kind'],
  name: string,
  extra: Partial<ExplorerNode> = {}
): ExplorerNode {
  return {
    id,
    kind,
    name,
    extension: '',
    version: null,
    modifiedAt: null,
    hasParents: false,
    hasChildren: false,
    parentId: '',
    projectId: '',
    ...extra,
  };
}

function listingForFolder(found: FoundFolder): Listing {
  const { folder, project, hub } = found;
  const isRoot = folder.id === project.root.id;
  const children = sortNodes([
    ...folder.folders.map((child) => folderNode(child, project, folder.id)),
    ...folder.files.map((child) => fileNode(child, project, folder.id)),
  ]);
  return {
    location: isRoot ? projectNode(project) : folderNode(folder, project, found.parent?.id ?? ''),
    crumbs: crumbsFor(found),
    children,
    activeFileId,
    containerId: folder.id,
  };
}

function crumbsFor(found: FoundFolder): ExplorerNode[] {
  const chain: MockFolder[] = [];
  let current: FoundFolder | null = found;
  let guard = 0;
  while (current && current.folder.id !== current.project.root.id && guard < 40) {
    chain.push(current.folder);
    current = current.parent ? findFolder(current.parent.id) : null;
    guard += 1;
  }
  const crumbs = [hubNode(found.hub), projectNode(found.project)];
  chain.reverse().forEach((item) => {
    const parent = findFolder(item.id);
    crumbs.push(folderNode(item, found.project, parent?.parent?.id ?? found.project.root.id));
  });
  return crumbs;
}

function listingForHub(hub: MockHub): Listing {
  return {
    location: hubNode(hub),
    crumbs: [hubNode(hub)],
    children: sortNodes(hub.projects.map(projectNode)),
    activeFileId,
    containerId: hub.id,
  };
}

function delay<T>(value: T, ms = 90): Promise<T> {
  return new Promise((resolve) => {
    window.setTimeout(() => resolve(value), ms);
  });
}

function mockFail(message: string): never {
  throw new FusionError(message);
}

function cleanName(name: unknown): string {
  if (typeof name !== 'string' || !name.trim()) mockFail('Enter a name.');
  const cleaned = name.trim();
  if (/[<>:"/\\|?*]/.test(cleaned)) mockFail('Names cannot include <>:"/\\|?*');
  return cleaned;
}

function payloadOf(payload: unknown): Record<string, unknown> {
  return payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
}

function startMockSearch(searchId: string, projectId: string, query: string) {
  clearSearchTimers();
  activeSearchId = searchId;
  const found = findProject(projectId);
  if (!found) mockFail('That project is not loaded. Refresh and open it again.');
  const folders: MockFolder[] = [];
  walkFolders(found.project.root, (item) => folders.push(item));
  let index = 0;
  let scanned = 0;
  const needle = query.toLowerCase();

  const step = () => {
    if (activeSearchId !== searchId) return;
    const current = folders[index];
    index += 1;
    const matches: ExplorerNode[] = [];
    if (current && current !== found.project.root && current.name.toLowerCase().includes(needle)) {
      const parent = findFolder(current.id);
      matches.push(folderNode(current, found.project, parent?.parent?.id ?? ''));
    }
    if (current) {
      current.files.forEach((item) => {
        scanned += 1;
        if (item.name.toLowerCase().includes(needle)) {
          matches.push(fileNode(item, found.project, current.id));
        }
      });
    }
    const truncated = scanned >= 3000 && index < folders.length;
    const done = truncated || index >= folders.length;
    dispatchEvent(
      'searchProgress',
      JSON.stringify({
        searchId,
        matches,
        scanned,
        done,
        truncated,
        cancelled: false,
      })
    );
    if (!done) {
      searchTimers.push(window.setTimeout(step, 50));
    } else if (activeSearchId === searchId) {
      activeSearchId = '';
    }
  };

  searchTimers.push(window.setTimeout(step, 50));
}

async function mockRequest<T>(action: string, payload?: unknown): Promise<T> {
  const data = payloadOf(payload);

  if (action === 'ready') {
    const hub = hubs[0];
    const start = findFolder('folder-hardware');
    return delay<T>({
      hubs: hubs.map(hubNode),
      activeHubId: hub.id,
      activeFileId,
      listing: start ? listingForFolder(start) : listingForHub(hub),
      listingError: '',
    } as ReadyPayload as T);
  }

  if (action === 'folder:list') {
    const kind = String(data.kind || '');
    const id = String(data.id || '');
    if (kind === 'hub') {
      const hub = hubs.find((item) => item.id === id);
      if (!hub) mockFail('That hub is not loaded. Refresh and open it again.');
      return delay(listingForHub(hub) as T);
    }
    if (kind === 'project') {
      const found = findProject(id);
      if (!found) mockFail('That project is not loaded. Refresh and open it again.');
      return delay(listingForFolder({ folder: found.project.root, parent: null, project: found.project, hub: found.hub }) as T);
    }
    if (kind === 'folder') {
      const found = findFolder(id);
      if (!found) mockFail('That folder is not loaded. Refresh and open it again.');
      return delay(listingForFolder(found) as T);
    }
    mockFail('Choose a hub, project, or folder.');
  }

  if (action === 'file:open') {
    const found = findFile(String(data.id || ''));
    if (!found) mockFail('Choose a file to open.');
    activeFileId = found.file.id;
    dispatchEvent('activeFileChanged', JSON.stringify({ activeFileId }));
    return delay({ opened: true, activated: true } as T, 40);
  }

  if (action === 'item:rename') {
    const name = cleanName(data.name);
    const id = String(data.id || '');
    if (data.kind === 'file') {
      const found = findFile(id);
      if (!found) mockFail('That file is not loaded. Refresh and open it again.');
      found.file.name = name;
      return delay(fileNode(found.file, found.project, found.folder.id) as T, 40);
    }
    if (data.kind === 'folder') {
      const found = findFolder(id);
      if (!found) mockFail('That folder is not loaded. Refresh and open it again.');
      if (!found.parent) mockFail('The project root folder cannot be renamed here.');
      found.folder.name = name;
      return delay(folderNode(found.folder, found.project, found.parent.id) as T, 40);
    }
    mockFail('Only files and folders can be renamed.');
  }

  if (action === 'item:delete') {
    const id = String(data.id || '');
    if (data.kind === 'file') {
      const found = findFile(id);
      if (!found) mockFail('That file is not loaded. Refresh and open it again.');
      if (found.file.id === activeFileId) mockFail('Close that design before deleting it.');
      found.folder.files = found.folder.files.filter((item) => item.id !== id);
      hubs.forEach((hub) => {
        hub.projects.forEach((project) => {
          walkFolders(project.root, (item) => {
            item.files.forEach((entry) => {
              entry.parentRefs = entry.parentRefs.filter((ref) => ref !== id);
              entry.childRefs = entry.childRefs.filter((ref) => ref !== id);
            });
          });
        });
      });
      return delay({ deleted: true } as T, 40);
    }
    if (data.kind === 'folder') {
      const found = findFolder(id);
      if (!found || !found.parent) mockFail('That folder cannot be deleted.');
      if (found.folder.files.length || found.folder.folders.length) {
        mockFail('Fusion could not delete that. Folders must be empty.');
      }
      found.parent.folders = found.parent.folders.filter((item) => item.id !== id);
      return delay({ deleted: true } as T, 40);
    }
    mockFail('Only files and folders can be deleted.');
  }

  if (action === 'folder:create') {
    const name = cleanName(data.name);
    const parentKind = String(data.parentKind || '');
    const parentId = String(data.parentId || '');
    let parent: MockFolder | null = null;
    let project: MockProject | null = null;
    if (parentKind === 'project') {
      const found = findProject(parentId);
      if (!found) mockFail('Open a project folder before creating a folder.');
      parent = found.project.root;
      project = found.project;
    } else if (parentKind === 'folder') {
      const found = findFolder(parentId);
      if (!found) mockFail('Open a project folder before creating a folder.');
      parent = found.folder;
      project = found.project;
    }
    if (!parent || !project) mockFail('Open a project folder before creating a folder.');
    const created = folder(`folder-${Date.now()}`, name, [], []);
    parent.folders.push(created);
    return delay(folderNode(created, project, parent.id) as T, 40);
  }

  if (action === 'file:move') {
    const found = findFile(String(data.id || ''));
    const target = findFolder(String(data.targetFolderId || ''));
    if (!found || !target) mockFail('That item is not loaded. Refresh and open it again.');
    if (found.folder.id === target.folder.id) mockFail('That file is already in this folder.');
    if (found.project.id !== target.project.id) mockFail('Files can only be moved inside the same project.');
    found.folder.files = found.folder.files.filter((item) => item.id !== found.file.id);
    target.folder.files.push(found.file);
    return delay(fileNode(found.file, target.project, target.folder.id) as T, 40);
  }

  if (action === 'file:references') {
    const found = findFile(String(data.id || ''));
    if (!found) mockFail('That file is not loaded. Refresh and open it again.');
    const toNode = (id: string) => {
      const match = findFile(id);
      return match ? fileNode(match.file, match.project, match.folder.id) : null;
    };
    const refs: ReferencesPayload = {
      file: fileNode(found.file, found.project, found.folder.id),
      parents: sortNodes(found.file.parentRefs.map(toNode).filter((item): item is ExplorerNode => !!item)),
      children: sortNodes(found.file.childRefs.map(toNode).filter((item): item is ExplorerNode => !!item)),
      warning: '',
    };
    return delay(refs as T, 140);
  }

  if (action === 'nav:activeFile') {
    const found = findFile(activeFileId);
    if (!found) mockFail('The open design is not saved to a Fusion project.');
    const listing = listingForFolder({
      folder: found.folder,
      parent: findFolder(found.folder.id)?.parent ?? null,
      project: found.project,
      hub: found.hub,
    });
    return delay({ fileId: found.file.id, listing } as ActiveFileLocation as T);
  }

  if (action === 'search:start') {
    const searchId = String(data.searchId || '');
    const query = String(data.query || '').trim();
    const projectId = String(data.projectId || '');
    if (!searchId || !query) mockFail('Enter something to search for.');
    startMockSearch(searchId, projectId, query);
    return delay({ searchId, started: true } as T, 10);
  }

  if (action === 'search:cancel') {
    const searchId = String(data.searchId || '');
    if (activeSearchId === searchId) {
      activeSearchId = '';
      clearSearchTimers();
    }
    return { cancelled: true } as T;
  }

  if (action === 'jsLog' || action === 'clipboard:copy') {
    return { copied: true } as T;
  }

  mockFail(`Unknown action: ${action}`);
}
