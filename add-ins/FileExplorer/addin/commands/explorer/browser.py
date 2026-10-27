"""Fusion hub, project, and folder browsing for the File Explorer palette.

Fusion's data API is main-thread only, and every folder listing is a network
call. Listings stay one folder deep. Project search walks folders in small
batches on a custom event so the Fusion UI can keep running.
"""

import threading
import time
import traceback

import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil

app = adsk.core.Application.get()

SEARCH_EVENT_ID = 'CHE_FileExplorer_searchTick'
SEARCH_LIMIT = 3000
BATCH_FOLDERS = 10
_INVALID_NAME = set('<>:"/\\|?*')

_cache = {}
_search = None
_push = None
_local_handlers = []


def attach(push):
    """Register the search tick. `push(action, payload)` sends palette events."""
    global _push
    _push = push
    try:
        app.unregisterCustomEvent(SEARCH_EVENT_ID)
    except Exception:
        pass
    event = app.registerCustomEvent(SEARCH_EVENT_ID)
    futil.add_handler(event, _on_search_tick, local_handlers=_local_handlers)


def detach():
    global _search, _push
    if _search:
        _search['cancel'] = True
        _search = None
    _push = None
    try:
        app.unregisterCustomEvent(SEARCH_EVENT_ID)
    except Exception:
        pass
    _local_handlers.clear()


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
        return _file_node(item)
    return _folder_node(item)


def delete_item(data):
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
    _refresh_panel()
    return {'deleted': True}


def create_folder(data):
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
    return _folder_node(created)


def move_file(data):
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
    return _file_node(data_file, target.id)


def references(file_id):
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
    root = project.rootFolder
    _remember(root, 'folder')
    _search = {
        'id': search_id,
        'query': query,
        'queue': [root],
        'seen': {root.id},
        'scanned': 0,
        'truncated': False,
        'cancel': False,
    }
    _schedule_search_tick(search_id)
    return {'searchId': search_id, 'started': True}


def cancel_search(data):
    global _search
    search_id = data.get('searchId') if isinstance(data, dict) else ''
    if _search and _search['id'] == search_id:
        _search['cancel'] = True
    return {'cancelled': True}


def _on_search_tick(args: adsk.core.CustomEventArgs):
    state = _search
    incoming = getattr(args, 'additionalInfo', '') or ''
    if not state or state['id'] != incoming:
        return
    if state['cancel']:
        _emit_search(state, [], done=True, cancelled=True)
        if _search is state:
            _clear_search(state)
        return

    new_matches = []
    batch = 0
    truncated = False
    while state['queue'] and batch < BATCH_FOLDERS:
        folder = state['queue'].pop(0)
        batch += 1
        try:
            project_id = _project_id_of_folder(folder)
            for sub in _each(folder.dataFolders):
                sub_id = sub.id
                if sub_id in state['seen']:
                    continue
                state['seen'].add(sub_id)
                _remember(sub, 'folder')
                state['queue'].append(sub)
                if state['query'] in (sub.name or '').lower():
                    new_matches.append(_folder_node(sub, project_id))
            if truncated:
                break
            for data_file in _each(folder.dataFiles):
                state['scanned'] += 1
                _remember(data_file, 'file')
                if state['query'] in (data_file.name or '').lower():
                    new_matches.append(_file_node(data_file, folder.id, project_id))
                if state['scanned'] >= SEARCH_LIMIT:
                    truncated = True
                    break
        except Exception:
            futil.log(f'Search skipped a folder: {traceback.format_exc()}')
        if truncated:
            break

    done = truncated or not state['queue']
    state['truncated'] = truncated or state['truncated']
    _emit_search(state, new_matches, done=done, cancelled=False)
    if done:
        _clear_search(state)
        return
    _schedule_search_tick(state['id'])


def _clear_search(state):
    global _search
    if _search is state:
        _search = None


def _emit_search(state, matches, done, cancelled):
    if not _push:
        return
    _push('searchProgress', {
        'searchId': state['id'],
        'matches': matches,
        'scanned': state['scanned'],
        'done': done,
        'truncated': bool(state['truncated']),
        'cancelled': cancelled,
    })


def _schedule_search_tick(search_id):
    """Hop off the main thread, then wake Fusion on the next custom event."""
    def _kick():
        time.sleep(0.03)
        try:
            app.fireCustomEvent(SEARCH_EVENT_ID, search_id)
        except Exception:
            futil.log(f'Could not continue search: {traceback.format_exc()}')

    threading.Thread(target=_kick, daemon=True).start()


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
    if found and found['kind'] == kind:
        return found['obj']
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
