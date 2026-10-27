"""Fusion hub, project, and folder browsing for the File Explorer palette.

Fusion's data API is main-thread only, and every folder listing is a network
call. Listings stay one folder deep. A background crawl reads one folder per
turn and stores names locally. Search filters that index instead of walking
the project again.
"""

import json
import os
import threading
import time
import traceback
from collections import deque

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil

app = adsk.core.Application.get()

SEARCH_EVENT_ID = 'CHE_FileExplorer_searchTick'
INDEX_FILE_CAP = 20000
INDEX_STALE_SECONDS = 15 * 60
_INVALID_NAME = set('<>:"/\\|?*')

_cache = {}
_indexes = {}
_active_crawl = ''
_tick_due = False
_pause_until = 0.0
_request_depth = 0
_search = None
_push = None
_local_handlers = []


def attach(push):
    """Register the index tick. `push(action, payload)` sends palette events."""
    global _push
    _push = push
    try:
        app.unregisterCustomEvent(SEARCH_EVENT_ID)
    except Exception:
        pass
    event = app.registerCustomEvent(SEARCH_EVENT_ID)
    futil.add_handler(event, _on_index_tick, local_handlers=_local_handlers)


def detach():
    global _search, _push, _active_crawl, _tick_due
    _search = None
    _active_crawl = ''
    _tick_due = False
    for state in list(_indexes.values()):
        _save_index_sync(state)
    _push = None
    try:
        app.unregisterCustomEvent(SEARCH_EVENT_ID)
    except Exception:
        pass
    _local_handlers.clear()


def enter_request():
    """Palette requests and index ticks share Fusion's main thread."""
    global _request_depth
    _request_depth += 1


def leave_request():
    global _request_depth
    _request_depth = max(0, _request_depth - 1)


def ready():
    data = app.data
    hubs = []
    for hub in _each(data.dataHubs):
        _remember(hub, 'hub')
        hubs.append(_hub_node(hub))
    hubs.sort(key=lambda node: node['name'].lower())

    active_hub = _safe(lambda: data.activeHub)
    active_file_id = _active_file_id()
    listing = None
    listing_error = ''
    try:
        if active_hub:
            _remember(active_hub, 'hub')
            folder = _safe(lambda: data.activeFolder)
            project = _safe(lambda: data.activeProject)
            if folder:
                listing = _list_folder_obj(folder)
            elif project:
                listing = _list_project(project)
            else:
                listing = _list_hub(active_hub)
        elif hubs:
            listing = _list_hub(_require(hubs[0]['id'], 'hub'))
    except ValueError as exc:
        listing_error = str(exc)
    except Exception as exc:
        listing_error = _short_error(exc, 'Could not open the current folder.')

    return {
        'hubs': hubs,
        'activeHubId': active_hub.id if active_hub else (hubs[0]['id'] if hubs else ''),
        'activeFileId': active_file_id,
        'listing': listing,
        'listingError': listing_error,
    }


def list_location(data):
    _pause_index()
    kind = data.get('kind') if isinstance(data, dict) else ''
    item_id = data.get('id') if isinstance(data, dict) else ''
    if kind == 'hub':
        return _list_hub(_require(item_id, 'hub'))
    if kind == 'project':
        return _list_project(_require(item_id, 'project'))
    if kind == 'folder':
        return _list_folder_obj(_require(item_id, 'folder'))
    raise ValueError('Choose a hub, project, or folder.')


def open_file(file_id):
    _pause_index()
    if not file_id:
        raise ValueError('Choose a file to open.')
    for document in _each(app.documents):
        data_file = _safe(lambda document=document: document.dataFile)
        if data_file and _safe(lambda data_file=data_file: data_file.id) == file_id:
            document.activate()
            return {'opened': True, 'activated': True}
    data_file = _require(file_id, 'file')
    app.documents.open(data_file, True)
    return {'opened': True, 'activated': False}


def insert_file(file_id):
    """Insert a Fusion design into the active component as a linked occurrence."""
    _pause_index()
    if not file_id:
        raise ValueError('Choose a design to insert.')
    data_file = _require(file_id, 'file')
    extension = ''
    try:
        extension = (data_file.fileExtension or '').lstrip('.').lower()
    except Exception:
        extension = ''
    if extension != 'f3d':
        raise ValueError('Only Fusion designs can be inserted into the open design.')

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise ValueError('Open a Fusion design before inserting a file.')
    target = _active_file()
    if not target:
        raise ValueError('Save the open design before inserting a file.')
    if _safe(lambda: target.id) == file_id:
        raise ValueError('A design cannot be inserted into itself.')

    source_project = _safe(lambda: data_file.parentProject)
    target_project = _safe(lambda: target.parentProject)
    source_project_id = _safe(lambda: source_project.id) if source_project else ''
    target_project_id = _safe(lambda: target_project.id) if target_project else ''
    if source_project_id and target_project_id and source_project_id != target_project_id:
        raise ValueError('Fusion can only link a design from the same project as the open design.')

    component = _safe(lambda: design.activeComponent) or design.rootComponent
    transform = adsk.core.Matrix3D.create()
    try:
        row = _configuration_row(data_file)
        if row:
            occurrence = component.occurrences.addFromConfiguration(row, transform)
        else:
            occurrence = component.occurrences.addByInsert(data_file, transform, True)
    except Exception as exc:
        raise ValueError(_short_error(exc, 'Fusion could not insert that design.')) from exc
    if not occurrence:
        raise ValueError('Fusion could not insert that design.')
    name = _safe(lambda: occurrence.name) or _safe(lambda: data_file.name) or 'design'
    return {'inserted': True, 'name': name}


def rename_item(data):
    _pause_index()
    kind = data.get('kind')
    item_id = data.get('id') or ''
    name = _clean_name(data.get('name'))
    if kind == 'file':
        item = _require(item_id, 'file')
    elif kind == 'folder':
        item = _require(item_id, 'folder')
        if _is_root(item):
            raise ValueError('The project root folder cannot be renamed here.')
    else:
        raise ValueError('Only files and folders can be renamed.')
    try:
        item.name = name
    except Exception as exc:
        raise ValueError(_short_error(exc, 'Fusion could not rename that.')) from exc
    _refresh_panel()
    if kind == 'file':
        node = _file_node(item)
    else:
        node = _folder_node(item)
    _upsert_indexed(node)
    return node


def delete_item(data):
    _pause_index()
    kind = data.get('kind')
    item_id = data.get('id') or ''
    if kind == 'file':
        _refuse_if_open(item_id)
        item = _require(item_id, 'file')
    elif kind == 'folder':
        item = _require(item_id, 'folder')
        if _is_root(item):
            raise ValueError('The project root folder cannot be deleted.')
    else:
        raise ValueError('Only files and folders can be deleted.')
    try:
        deleted = item.deleteMe()
    except Exception as exc:
        raise ValueError(_short_error(exc, 'Fusion could not delete that.')) from exc
    if deleted is False:
        raise ValueError('Fusion could not delete that. Close it if it is open, and folders must be empty.')
    _cache.pop(item_id, None)
    _forget_indexed(item_id)
    _refresh_panel()
    return {'deleted': True}


def create_folder(data):
    _pause_index()
    parent_kind = data.get('parentKind')
    parent_id = data.get('parentId') or ''
    name = _clean_name(data.get('name'))
    if parent_kind == 'project':
        parent = _require(parent_id, 'project').rootFolder
    elif parent_kind == 'folder':
        parent = _require(parent_id, 'folder')
    else:
        raise ValueError('Open a project folder before creating a folder.')
    _remember(parent, 'folder')
    try:
        created = parent.dataFolders.add(name)
    except Exception as exc:
        raise ValueError(_short_error(exc, 'Fusion could not create that folder.')) from exc
    _remember(created, 'folder')
    _refresh_panel()
    node = _folder_node(created)
    _upsert_indexed(node)
    return node


def move_file(data):
    _pause_index()
    file_id = data.get('id') or ''
    target_id = data.get('targetFolderId') or ''
    data_file = _require(file_id, 'file')
    target = _require(target_id, 'folder')
    parent = _safe(lambda: data_file.parentFolder)
    if parent and parent.id == target.id:
        raise ValueError('That file is already in this folder.')
    file_project = _safe(lambda: parent.parentProject) if parent else None
    target_project = _safe(lambda: target.parentProject)
    if file_project and target_project and file_project.id != target_project.id:
        raise ValueError('Files can only be moved inside the same project.')
    try:
        moved = data_file.move(target)
    except Exception as exc:
        raise ValueError(_short_error(exc, 'Fusion could not move that file.')) from exc
    if moved is False:
        raise ValueError('Fusion could not move that file.')
    _refresh_panel()
    node = _file_node(data_file, target.id)
    _upsert_indexed(node)
    return node


def references(file_id):
    _pause_index()
    data_file = _require(file_id, 'file')
    parents, parent_error = _collect_refs(data_file, 'parentReferences', 'designs that use this file')
    children, child_error = _collect_refs(data_file, 'childReferences', 'files this design uses')
    warning = ' '.join(part for part in (parent_error, child_error) if part)
    return {
        'file': _file_node(data_file),
        'parents': _sort_nodes(parents),
        'children': _sort_nodes(children),
        'warning': warning,
    }


def nav_active_file():
    _pause_index()
    data_file = _active_file()
    if not data_file:
        raise ValueError('The open design is not saved to a Fusion project.')
    _remember(data_file, 'file')
    parent = _safe(lambda: data_file.parentFolder)
    if not parent:
        raise ValueError('Could not find the folder for the open design.')
    return {'fileId': data_file.id, 'listing': _list_folder_obj(parent)}


def active_file_id():
    return _active_file_id()


def start_search(data):
    global _search
    search_id = str(data.get('searchId') or '').strip()
    query = str(data.get('query') or '').strip().lower()
    project_id = str(data.get('projectId') or '').strip()
    if not search_id or not query:
        raise ValueError('Enter something to search for.')
    project = _require(project_id, 'project')
    _remember(project, 'project')
    state = _note_project(project)
    _search = {
        'id': search_id,
        'query': query,
        'project_id': project.id,
        'sent': False,
    }
    if state['walking']:
        if _active_crawl != project.id:
            _kick_crawl(project.id)
    elif _walk_needed(state):
        state['wants_walk'] = True
        _kick_crawl(project.id)
    else:
        _kick_crawl(project.id)
    return {'searchId': search_id, 'started': True, 'indexed': bool(state['complete'])}


def cancel_search(data):
    """Stop delivering matches. The project crawl keeps running."""
    global _search
    search_id = data.get('searchId') if isinstance(data, dict) else ''
    if _search and _search['id'] == search_id:
        _search = None
    return {'cancelled': True}


def _on_index_tick(args: adsk.core.CustomEventArgs):
    global _tick_due
    _tick_due = False
    project_id = _active_crawl
    if not project_id:
        return
    # Never touch the data API, or push into the palette, while it is still
    # answering an HTML request. Fusion deadlocks if those overlap.
    if _request_depth:
        _schedule_index_tick(project_id)
        return

    _flush_search()
    if time.monotonic() < _pause_until:
        _schedule_index_tick(project_id)
        return

    state = _indexes.get(project_id)
    if state and state.get('wants_walk') and not state['walking'] and _walk_needed(state):
        state['wants_walk'] = False
        project = _cached_obj(project_id, 'project')
        if project is None:
            project = _safe(lambda: _require(project_id, 'project'))
        root = _safe(lambda: project.rootFolder) if project else None
        if root:
            _remember(root, 'folder')
            _arm_walk(state, root)
        else:
            state['retry_after'] = time.monotonic() + 60
    elif state:
        state['wants_walk'] = False

    if not state or not state['queue']:
        if state and state['walking']:
            _complete_walk(state)
        _resume_next()
        return

    fresh = _index_one_folder(state)
    _publish_fresh(state, fresh)
    if state['queue']:
        _schedule_index_tick(project_id)
        return
    _complete_walk(state)
    _resume_next()


def _pause_index(seconds=0.45):
    """Let a folder click finish before the next cloud listing."""
    global _pause_until
    _pause_until = max(_pause_until, time.monotonic() + seconds)


def _note_project(project):
    project_id = project.id
    state = _indexes.get(project_id)
    if state is None:
        state = _load_index(project_id) or _new_index(project_id)
        _indexes[project_id] = state
    return state


def _walk_needed(state):
    if state['walking']:
        return False
    if time.monotonic() < state.get('retry_after', 0):
        return False
    if not state['complete']:
        return True
    return time.time() - (state.get('updated') or 0) > INDEX_STALE_SECONDS


def _arm_walk(state, root):
    state['pending'] = {}
    state['queue'] = deque([root.id])
    state['seen'] = {root.id}
    state['scanned'] = 0
    state['truncated'] = False
    state['walking'] = True
    state['visited'] = 0
    state['folders_done'] = 0
    state['wants_walk'] = False


def _flush_search():
    search = _search
    if not search or search.get('sent'):
        return
    state = _indexes.get(search['project_id'])
    if not state:
        return
    search['sent'] = True
    _emit_search(
        search,
        state,
        _matching_nodes(state['nodes'], search['query']),
        done=bool(state['complete']),
        replace=True,
        cancelled=False,
    )


def _complete_walk(state):
    state['walking'] = False
    if state.get('visited'):
        state['nodes'] = state['pending']
        state['complete'] = True
        state['updated'] = time.time()
        state['retry_after'] = 0
    else:
        state['retry_after'] = time.monotonic() + 60
        if not state['nodes']:
            state['complete'] = False
    state['pending'] = {}
    state['queue'] = deque()
    _save_index_async(state, force=True)
    _publish_full(state)


def _resume_next():
    current = _indexes.get(_active_crawl)
    if current and current['queue']:
        current['walking'] = True
        _kick_crawl(_active_crawl)
        return
    for project_id, state in _indexes.items():
        if state['queue']:
            state['walking'] = True
            _kick_crawl(project_id)
            return


def _index_one_folder(state):
    folder_id = state['queue'].popleft()
    folder = _cached_obj(folder_id, 'folder')
    if folder is None:
        folder = _safe(lambda: app.data.findFolderById(folder_id))
        if folder:
            _remember(folder, 'folder')
    if folder is None:
        return []
    project_id = state['project_id']
    try:
        subfolders = list(_each(folder.dataFolders))
        files = list(_each(folder.dataFiles))
    except Exception:
        futil.log(f'Index skipped a folder: {traceback.format_exc()}')
        return []
    state['visited'] = state.get('visited', 0) + 1

    fresh = []
    for sub in subfolders:
        sub_id = _safe(lambda sub=sub: sub.id)
        if not sub_id or sub_id in state['seen']:
            continue
        state['seen'].add(sub_id)
        _remember(sub, 'folder')
        state['queue'].append(sub_id)
        if _is_root(sub):
            continue
        node = _indexed_folder_node(sub, folder_id, project_id)
        state['pending'][sub_id] = node
        fresh.append(node)
    for data_file in files:
        file_id = _safe(lambda data_file=data_file: data_file.id)
        if not file_id:
            continue
        node = _indexed_file_node(data_file, folder_id, project_id)
        state['pending'][file_id] = node
        fresh.append(node)
        state['scanned'] += 1
        if state['scanned'] >= INDEX_FILE_CAP:
            state['truncated'] = True
            state['queue'].clear()
            break
    if not state['complete']:
        for node in fresh:
            state['nodes'][node['id']] = node
    state['folders_done'] = state.get('folders_done', 0) + 1
    if state['folders_done'] % 25 == 0:
        _save_index_async(state)
    return fresh


def _publish_fresh(state, fresh):
    search = _search
    if not fresh or not search or search['project_id'] != state['project_id']:
        return
    if state['complete']:
        return
    matches = [node for node in fresh if search['query'] in (node.get('name') or '').lower()]
    if not matches:
        return
    _emit_search(search, state, matches, done=False, replace=False, cancelled=False)


def _publish_full(state):
    search = _search
    if not search or search['project_id'] != state['project_id']:
        return
    building = bool(state['walking'] and not state['complete'])
    _emit_search(
        search,
        state,
        _matching_nodes(state['nodes'], search['query']),
        done=not building,
        replace=True,
        cancelled=False,
    )


def _emit_search(search, state, matches, done, replace, cancelled):
    if not _push or not search:
        return
    building = bool(state and state['walking'] and not state['complete'])
    _push('searchProgress', {
        'searchId': search['id'],
        'matches': matches,
        'scanned': state['scanned'] if state else 0,
        'done': done,
        'truncated': bool(state and state['truncated']),
        'cancelled': cancelled,
        'replace': replace,
        'indexing': bool(building and not done),
    })


def _schedule_index_tick(project_id):
    """Hop off the main thread, then read one folder on the next custom event."""
    global _tick_due
    if _tick_due or not project_id:
        return
    _tick_due = True

    def _kick():
        global _tick_due
        time.sleep(0.05)
        try:
            app.fireCustomEvent(SEARCH_EVENT_ID, project_id)
        except Exception:
            _tick_due = False
            futil.log(f'Could not continue indexing: {traceback.format_exc()}')

    threading.Thread(target=_kick, daemon=True).start()


def _kick_crawl(project_id):
    global _active_crawl
    _active_crawl = project_id
    _schedule_index_tick(project_id)


def _new_index(project_id):
    return {
        'project_id': project_id,
        'nodes': {},
        'pending': {},
        'queue': deque(),
        'seen': set(),
        'complete': False,
        'walking': False,
        'truncated': False,
        'scanned': 0,
        'updated': 0,
        'saved_at': 0,
        'retry_after': 0,
        'folders_done': 0,
        'wants_walk': False,
    }


def _index_dir():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'CHE', 'FileExplorer', 'index')


def _index_file(project_id):
    digest = 0
    for char in project_id:
        digest = (digest * 131 + ord(char)) & 0xFFFFFFFF
    slug = ''.join(char for char in project_id if char.isalnum())[:24] or 'project'
    return os.path.join(_index_dir(), f'{slug}-{digest:08x}.json')


def _load_index(project_id):
    path = _index_file(project_id)
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get('projectId') != project_id:
        return None
    state = _new_index(project_id)
    nodes = data.get('nodes')
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get('id'):
                state['nodes'][node['id']] = node
    state['complete'] = bool(data.get('complete'))
    state['truncated'] = bool(data.get('truncated'))
    try:
        state['updated'] = float(data.get('updated') or 0)
    except Exception:
        state['updated'] = 0
    try:
        state['scanned'] = int(data.get('scanned') or len(state['nodes']))
    except Exception:
        state['scanned'] = len(state['nodes'])
    return state


def _snapshot_index(state):
    return {
        'projectId': state['project_id'],
        'complete': bool(state['complete'] and not state['walking']),
        'truncated': bool(state['truncated']),
        'scanned': state['scanned'],
        'updated': state.get('updated') or 0,
        'nodes': list(state['nodes'].values()),
    }


def _save_index_async(state, force=False):
    now = time.monotonic()
    if not force and now - state.get('saved_at', 0) < 3:
        state['dirty'] = True
        return
    state['dirty'] = False
    state['saved_at'] = now
    snapshot = _snapshot_index(state)
    path = _index_file(state['project_id'])

    def _write():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            temporary = f'{path}.{threading.get_ident()}.tmp'
            with open(temporary, 'w', encoding='utf-8') as handle:
                json.dump(snapshot, handle, separators=(',', ':'))
            os.replace(temporary, path)
        except Exception:
            futil.log(f'Could not save the project index: {traceback.format_exc()}')

    threading.Thread(target=_write, daemon=True).start()


def _save_index_sync(state):
    if not state.get('nodes') and not state.get('complete'):
        return
    snapshot = _snapshot_index(state)
    path = _index_file(state['project_id'])
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = f'{path}.tmp'
        with open(temporary, 'w', encoding='utf-8') as handle:
            json.dump(snapshot, handle, separators=(',', ':'))
        os.replace(temporary, path)
        state['dirty'] = False
        state['saved_at'] = time.monotonic()
    except Exception:
        futil.log(f'Could not save the project index: {traceback.format_exc()}')


def _remember_listing(project, folder, children):
    if not project:
        return
    _pause_index()
    _remember(project, 'project')
    state = _note_project(project)
    _absorb_children(state, folder.id, children)
    if _walk_needed(state):
        state['wants_walk'] = True
        _kick_crawl(project.id)


def _absorb_children(state, parent_id, children):
    if not parent_id:
        return
    trees = [state['nodes']]
    pending = state.get('pending')
    if state.get('walking') and isinstance(pending, dict):
        trees.append(pending)
    for tree in trees:
        _replace_children(tree, parent_id, children)
    _save_index_async(state)


def _replace_children(tree, parent_id, children):
    fresh = {}
    for node in children:
        node_id = node.get('id')
        if node_id:
            fresh[node_id] = node
    stale = [
        node_id for node_id, node in tree.items()
        if node.get('parentId') == parent_id and node_id not in fresh
    ]
    for node_id in stale:
        _drop_node(tree, node_id)
    for node_id, node in fresh.items():
        tree[node_id] = node


def _upsert_indexed(node):
    if not isinstance(node, dict):
        return
    project_id = node.get('projectId') or ''
    node_id = node.get('id') or ''
    if not project_id or not node_id:
        return
    state = _indexes.get(project_id)
    if not state:
        return
    state['nodes'][node_id] = node
    pending = state.get('pending')
    if state.get('walking') and isinstance(pending, dict):
        pending[node_id] = node
    state['updated'] = time.time()
    _save_index_async(state)


def _forget_indexed(item_id):
    if not item_id:
        return
    for state in _indexes.values():
        changed = False
        trees = [state['nodes']]
        pending = state.get('pending')
        if state.get('walking') and isinstance(pending, dict):
            trees.append(pending)
        for tree in trees:
            if item_id in tree:
                _drop_node(tree, item_id)
                changed = True
        if changed:
            _save_index_async(state)


def _drop_node(tree, node_id):
    node = tree.pop(node_id, None)
    if not node or node.get('kind') != 'folder':
        return
    child_ids = [item_id for item_id, child in list(tree.items()) if child.get('parentId') == node_id]
    for child_id in child_ids:
        _drop_node(tree, child_id)


def _matching_nodes(nodes, query):
    if not query:
        return []
    return [node for node in nodes.values() if query in (node.get('name') or '').lower()]


def _indexed_folder_node(folder, parent_id, project_id):
    return _node(
        folder.id,
        'folder',
        _safe(lambda: folder.name) or '',
        parent_id=parent_id,
        project_id=project_id,
        has_children=True,
    )


def _indexed_file_node(data_file, parent_id, project_id):
    extension = ''
    try:
        extension = (data_file.fileExtension or '').lstrip('.').lower()
    except Exception:
        extension = ''
    return _node(
        data_file.id,
        'file',
        _safe(lambda: data_file.name) or '',
        extension=extension,
        version=_version(data_file),
        modified_at=_unix(_safe(lambda: data_file.dateModified)),
        parent_id=parent_id,
        project_id=project_id,
    )


def _cached_obj(item_id, kind):
    found = _cache.get(item_id)
    if found and found['kind'] == kind and _still_valid(found['obj']):
        return found['obj']
    return None


def _still_valid(obj):
    try:
        return bool(obj.isValid)
    except AttributeError:
        return True
    except Exception:
        return False


def _list_hub(hub):
    _remember(hub, 'hub')
    projects = []
    try:
        collection = hub.dataProjects
    except Exception as exc:
        raise ValueError(_short_error(exc, 'Could not load projects for that hub.')) from exc
    for project in _each(collection):
        _remember(project, 'project')
        root = _safe(lambda project=project: project.rootFolder)
        if root:
            _remember(root, 'folder')
        projects.append(_project_node(project, hub.id))
    return {
        'location': _hub_node(hub),
        'crumbs': [_hub_node(hub)],
        'children': _sort_nodes(projects),
        'activeFileId': _active_file_id(),
        'containerId': hub.id,
    }


def _list_project(project):
    _remember(project, 'project')
    try:
        root = project.rootFolder
    except Exception as exc:
        raise ValueError(_short_error(exc, 'Could not open that project.')) from exc
    return _list_folder_obj(root)


def _list_folder_obj(folder):
    _remember(folder, 'folder')
    project = _safe(lambda: folder.parentProject)
    hub = _safe(lambda: project.parentHub) if project else None
    if project:
        _remember(project, 'project')
    if hub:
        _remember(hub, 'hub')

    project_id = project.id if project else ''
    children = []
    try:
        folders = list(_each(folder.dataFolders))
        files = list(_each(folder.dataFiles))
    except Exception as exc:
        raise ValueError(_short_error(exc, 'Could not open that folder.')) from exc
    for sub in folders:
        _remember(sub, 'folder')
        children.append(_folder_node(sub, project_id))
    for data_file in files:
        _remember(data_file, 'file')
        children.append(_file_node(data_file, folder.id, project_id))

    if project and _is_root(folder):
        location = _project_node(project, hub.id if hub else '')
    else:
        location = _folder_node(folder, project_id)
    _remember_listing(project, folder, children)

    return {
        'location': location,
        'crumbs': _crumbs(folder, project, hub),
        'children': _sort_nodes(children),
        'activeFileId': _active_file_id(),
        'containerId': folder.id,
    }


def _crumbs(folder, project, hub):
    crumbs = []
    if hub:
        crumbs.append(_hub_node(hub))
    if project:
        crumbs.append(_project_node(project, hub.id if hub else ''))
    chain = []
    current = folder
    guard = 0
    while current is not None and guard < 40:
        if _is_root(current):
            break
        chain.append(current)
        current = _safe(lambda current=current: current.parentFolder)
        guard += 1
    for item in reversed(chain):
        _remember(item, 'folder')
        crumbs.append(_folder_node(item, project.id if project else ''))
    return crumbs


def _collect_refs(data_file, attribute, label):
    nodes = []
    try:
        collection = getattr(data_file, attribute)
        for item in _each(collection):
            _remember(item, 'file')
            nodes.append(_file_node(item))
    except Exception:
        futil.log(f'Could not read {attribute}: {traceback.format_exc()}')
        return [], f'Could not load {label}.'
    return nodes, ''


def _hub_node(hub):
    return _node(hub.id, 'hub', hub.name, parent_id='', project_id='')


def _project_node(project, hub_id=''):
    return _node(project.id, 'project', project.name, parent_id=hub_id, project_id=project.id)


def _folder_node(folder, project_id=''):
    parent_id = ''
    if not _is_root(folder):
        parent = _safe(lambda: folder.parentFolder)
        if parent:
            parent_id = parent.id
    if not project_id:
        project_id = _project_id_of_folder(folder)
    return _node(folder.id, 'folder', folder.name, parent_id=parent_id, project_id=project_id, has_children=True)


def _file_node(data_file, parent_id='', project_id=''):
    if not parent_id:
        parent = _safe(lambda: data_file.parentFolder)
        if parent:
            _remember(parent, 'folder')
            parent_id = parent.id
            if not project_id:
                project_id = _project_id_of_folder(parent)
    extension = ''
    try:
        extension = (data_file.fileExtension or '').lstrip('.').lower()
    except Exception:
        extension = ''
    has_parents = _safe_bool(lambda: data_file.hasParentReferences)
    has_children = _safe_bool(lambda: data_file.hasChildReferences)
    return _node(
        data_file.id,
        'file',
        data_file.name,
        extension=extension,
        version=_version(data_file),
        modified_at=_unix(_safe(lambda: data_file.dateModified)),
        has_parents=has_parents,
        has_children=has_children,
        parent_id=parent_id,
        project_id=project_id,
    )


def _node(item_id, kind, name, extension='', version=None, modified_at=None,
          has_parents=False, has_children=False, parent_id='', project_id=''):
    return {
        'id': item_id or '',
        'kind': kind,
        'name': name or '',
        'extension': extension or '',
        'version': version,
        'modifiedAt': modified_at,
        'hasParents': bool(has_parents),
        'hasChildren': bool(has_children),
        'parentId': parent_id or '',
        'projectId': project_id or '',
    }


def _sort_nodes(nodes):
    def key(node):
        rank = 0 if node['kind'] != 'file' else 1
        return (rank, (node.get('name') or '').lower())

    return sorted(nodes, key=key)


def _remember(obj, kind):
    if obj is None:
        return
    try:
        item_id = obj.id
    except Exception:
        return
    if item_id:
        _cache[item_id] = {'kind': kind, 'obj': obj}


def _require(item_id, kind):
    if not item_id:
        raise ValueError('That item is missing an id.')
    found = _cache.get(item_id)
    if found and found['kind'] == kind and _still_valid(found['obj']):
        return found['obj']
    _cache.pop(item_id, None)
    if kind == 'file':
        data_file = _safe(lambda: app.data.findFileById(item_id))
        if data_file:
            _remember(data_file, 'file')
            return data_file
    if kind == 'folder':
        folder = _safe(lambda: app.data.findFolderById(item_id))
        if folder:
            _remember(folder, 'folder')
            return folder
    if kind == 'hub':
        for hub in _each(app.data.dataHubs):
            _remember(hub, 'hub')
            if hub.id == item_id:
                return hub
    if kind == 'project':
        for hub in _each(app.data.dataHubs):
            _remember(hub, 'hub')
            try:
                projects = hub.dataProjects
            except Exception:
                continue
            for project in _each(projects):
                _remember(project, 'project')
                if project.id == item_id:
                    return project
    raise ValueError('That item is not loaded. Refresh and open it again.')


def _each(collection):
    if collection is None:
        return
    count = getattr(collection, 'count', None)
    if isinstance(count, int):
        for index in range(count):
            yield collection.item(index)
        return
    for item in collection:
        yield item


def _active_file():
    document = _safe(lambda: app.activeDocument)
    if not document:
        return None
    return _safe(lambda: document.dataFile)


def _active_file_id():
    data_file = _active_file()
    if not data_file:
        return ''
    return _safe(lambda: data_file.id) or ''


def _configuration_row(data_file):
    """First real configuration row, when this file is a configured design."""
    if not _safe_bool(lambda: data_file.isConfiguredDesign):
        return None
    table = _safe(lambda: data_file.configurationTable)
    rows = _safe(lambda: table.rows) if table else None
    count = _safe(lambda: rows.count) if rows else 0
    if not count:
        return None
    for index in range(count):
        row = _safe(lambda index=index: rows.item(index))
        if row and not _safe_bool(lambda row=row: row.isTestRow):
            return row
    return None


def _refuse_if_open(file_id):
    for document in _each(app.documents):
        data_file = _safe(lambda document=document: document.dataFile)
        if data_file and _safe(lambda data_file=data_file: data_file.id) == file_id:
            raise ValueError('Close that design before deleting it.')


def _project_id_of_folder(folder):
    project = _safe(lambda: folder.parentProject)
    if not project:
        return ''
    return _safe(lambda: project.id) or ''


def _is_root(folder):
    return _safe_bool(lambda: folder.isRoot)


def _version(data_file):
    for attribute in ('latestVersionNumber', 'versionNumber'):
        try:
            value = getattr(data_file, attribute)
        except Exception:
            continue
        try:
            number = int(value)
        except Exception:
            continue
        if number:
            return number
    return None


def _unix(value):
    if value is None:
        return None
    try:
        number = int(value)
    except Exception:
        return None
    if number > 10_000_000_000:
        number = number // 1000
    if number <= 0:
        return None
    return number


def _clean_name(name):
    if not isinstance(name, str):
        raise ValueError('Enter a name.')
    cleaned = name.strip()
    if not cleaned:
        raise ValueError('Enter a name.')
    if any(char in cleaned for char in _INVALID_NAME):
        raise ValueError('Names cannot include <>:"/\\|?*')
    return cleaned


def _refresh_panel():
    _safe(lambda: app.data.refreshDataPanel())


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def _safe_bool(fn):
    try:
        return bool(fn())
    except Exception:
        return False


def _short_error(exc, fallback):
    message = str(exc).strip()
    if not message or message.startswith('Traceback'):
        return fallback
    return message
