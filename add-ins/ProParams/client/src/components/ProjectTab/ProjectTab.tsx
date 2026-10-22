import { useCallback, useEffect, useMemo, useState } from 'react';

import { IconFileExport } from '@tabler/icons-react';

import { onEvent, request } from '../../connector/fusionBridge';
import type { ProjectParam } from '../../types/types';
import { subscribeProjectReload, useGlobalParams } from '../../utils/globalParams';
import { sanitizeName } from '../../utils/sanitizeName';
import { variationFileCount } from '../../utils/variations';
import { ExportVariationsDialog } from '../ExportVariationsDialog/ExportVariationsDialog';
import { ParamTable, type DraftRow, type TableColumn, type TableRow } from '../ParamTable/ParamTable';
import { VariationsDialog } from '../VariationsDialog/VariationsDialog';
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
    variationCount: p.isEditable ? (p.variations?.length ?? 0) : 0,
  }));
}

export function ProjectTab() {
  const { showToast } = useToast();
  const { params: globalParams } = useGlobalParams();
  const [params, setParams] = useState<ProjectParam[]>([]);
  const [docName, setDocName] = useState('');
  const [variationName, setVariationName] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);

  const localParams = useMemo(() => {
    const globalNames = new Set(globalParams.map((param) => sanitizeName(param.name)));
    return params.filter((param) => !param.isUserParam || !globalNames.has(sanitizeName(param.name)));
  }, [globalParams, params]);

  const rows = useMemo(() => toRows(localParams), [localParams]);

  const exportCount = useMemo(
    () => variationFileCount(localParams.filter((param) => param.isEditable).map((param) => param.variations?.length ?? 0)),
    [localParams]
  );

  const variationParam = variationName
    ? localParams.find((param) => param.name === variationName && param.isEditable) ?? null
    : null;

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
        onVariations={setVariationName}
        toolbarExtra={
          <button
            id="pp_project_exportBtn"
            className="pp_btn"
            type="button"
            disabled={exportCount === 0}
            title={
              exportCount === 0
                ? 'Add variations on a parameter to export them.'
                : `Export ${exportCount} file${exportCount === 1 ? '' : 's'}`
            }
            onClick={() => setExportOpen(true)}
          >
            <IconFileExport size={16} />
            {exportCount > 0 ? `Export variations (${exportCount})` : 'Export variations'}
          </button>
        }
        refName={(name) => `{{${sanitizeName(name)}}}`}
        dimensionToggle
        emptyTitle="No parameters in this design"
        emptyMessage="User parameters and model dimensions from the active design show up here. Edit a dimension's expression to change its size."
      />
      {variationParam && (
        <VariationsDialog
          param={variationParam}
          onClose={() => setVariationName(null)}
          onSaved={() => void load()}
        />
      )}
      {exportOpen && (
        <ExportVariationsDialog fileCount={exportCount} onClose={() => setExportOpen(false)} />
      )}
    </div>
  );
}
