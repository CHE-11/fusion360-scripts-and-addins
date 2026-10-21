import { useCallback, useEffect, useMemo, useState } from 'react';

import { onEvent, request } from '../../connector/fusionBridge';
import type { ProjectParam } from '../../types/types';
import { subscribeProjectReload, useGlobalParams } from '../../utils/globalParams';
import { sanitizeName } from '../../utils/sanitizeName';
import { ParamTable, type DraftRow, type TableColumn, type TableRow } from '../ParamTable/ParamTable';
import { useToast } from '../common/Toast';

const COLUMNS: TableColumn[] = ['name', 'expression', 'value', 'unit', 'comment'];

function matchingGlobalName(name: string, globalNames: { name: string }[]): string | undefined {
  const key = sanitizeName(name.trim());
  if (!key) return undefined;
  return globalNames.find((param) => sanitizeName(param.name) === key)?.name;
}

function toRows(params: ProjectParam[]): TableRow[] {
  return params.map((p) => ({
    name: p.name,
    expression: p.expression,
    value: p.value,
    unit: p.unit ?? '',
    comment: p.comment ?? '',
    editable: p.isEditable,
    deletable: p.isDeletable,
    // A model dimension's unit comes from the sketch or feature, so only the
    // expression, name, and comment can change.
    editableFields: p.isUserParam ? undefined : ['name', 'expression', 'comment'],
  }));
}

export function ProjectTab() {
  const { showToast } = useToast();
  const { params: globalParams } = useGlobalParams();
  const [params, setParams] = useState<ProjectParam[]>([]);
  const [docName, setDocName] = useState('');

  const rows = useMemo(() => {
    const globalNames = new Set(globalParams.map((param) => sanitizeName(param.name)));
    const local = params.filter(
      (param) => !param.isUserParam || !globalNames.has(sanitizeName(param.name))
    );
    return toRows(local);
  }, [globalParams, params]);

  const load = useCallback(async () => {
    try {
      const data = await request<ProjectParam[]>('project:list');
      setParams(data ?? []);
    } catch (e) {
      showToast(`Failed to load project parameters: ${String(e)}`, 'error');
    }
  }, [showToast]);

  useEffect(() => {
    void load();
    // Reload when the active document changes.
    const off = onEvent('docActivated', (raw) => {
      try {
        const info = JSON.parse(raw) as { name?: string };
        setDocName(info.name ?? '');
      } catch {
        /* ignore */
      }
      void load();
    });
    return off;
  }, [load]);

  useEffect(() => subscribeProjectReload(() => void load()), [load]);

  const onAdd = useCallback(
    async (draft: DraftRow) => {
      const name = draft.name.trim();
      const globalMatch = matchingGlobalName(name, globalParams);
      if (globalMatch) {
        showToast(
          `Cannot create "${name}". That name matches the global parameter "${globalMatch}".`,
          'error'
        );
        throw new Error('global-name');
      }
      try {
        await request<ProjectParam>('project:add', {
          name,
          expression: draft.expression.trim(),
          unit: draft.unit.trim(),
          comment: draft.comment.trim(),
        });
        await load();
        showToast(`Added "${name}".`, 'success');
      } catch (e) {
        showToast(String(e), 'error');
        throw e;
      }
    },
    [globalParams, load, showToast]
  );

  const onEdit = useCallback(
    async (originalName: string, draft: DraftRow) => {
      const name = draft.name.trim();
      const globalMatch = matchingGlobalName(name, globalParams);
      if (globalMatch && sanitizeName(name) !== sanitizeName(originalName)) {
        showToast(
          `Cannot rename "${originalName}" to "${name}". That name matches the global parameter "${globalMatch}".`,
          'error'
        );
        throw new Error('global-name');
      }
      try {
        await request<ProjectParam>('project:update', {
          originalName,
          name,
          expression: draft.expression.trim(),
          unit: draft.unit.trim(),
          comment: draft.comment.trim(),
        });
        await load();
        showToast(`Updated "${name}".`, 'success');
      } catch (e) {
        showToast(String(e), 'error');
        throw e;
      }
    },
    [globalParams, load, showToast]
  );

  const onDelete = useCallback(
    async (name: string) => {
      try {
        await request('project:delete', { name });
        await load();
        showToast(`Deleted "${name}".`, 'success');
      } catch (e) {
        showToast(String(e), 'error');
      }
    },
    [load, showToast]
  );

  return (
    <div id="pp_projectTab" className="pp_tabPanel">
      {docName && (
        <div className="pp_scopeBar" id="pp_project_scope">
          <span className="pp_muted">Active design</span>
          <span className="pp_scopeName">{docName}</span>
        </div>
      )}
      <ParamTable
        idPrefix="pp_project"
        rows={rows}
        columns={COLUMNS}
        editableFields={['name', 'expression', 'unit', 'comment']}
        canAdd
        onAdd={onAdd}
        onEdit={onEdit}
        onDelete={onDelete}
        refName={(name) => `{{${sanitizeName(name)}}}`}
        dimensionToggle
        emptyTitle="No parameters in this design"
        emptyMessage="User parameters and model dimensions from the active design show up here. Edit a dimension's expression to change its size."

      />
    </div>
  );
}
