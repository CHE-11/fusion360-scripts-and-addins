import { useCallback } from 'react';

import { request } from '../../connector/fusionBridge';
import type { GlobalParam } from '../../types/types';
import { useGlobalParams } from '../../utils/globalParams';
import { sanitizeName } from '../../utils/sanitizeName';
import { ParamTable, type DraftRow, type TableColumn, type TableRow } from '../ParamTable/ParamTable';
import { useToast } from '../common/Toast';

const COLUMNS: TableColumn[] = ['name', 'expression', 'unit', 'comment', 'category'];

function toRows(params: GlobalParam[]): TableRow[] {
  return params.map((p) => ({
    name: p.name,
    expression: p.expression,
    unit: p.unit ?? '',
    comment: p.comment ?? '',
    category: p.category ?? '',
    editable: true,
    deletable: true,
  }));
}

function draftToParam(draft: DraftRow): GlobalParam {
  return {
    name: draft.name.trim(),
    expression: draft.expression.trim(),
    unit: draft.unit.trim(),
    comment: draft.comment.trim(),
    category: draft.category.trim(),
  };
}

export function GlobalTab() {
  const { showToast } = useToast();
  const { params, setParams, busy, pushToDesign } = useGlobalParams();

  const persist = useCallback(
    async (next: GlobalParam[]) => {
      const saved = await request<GlobalParam[]>('global:save', { params: next });
      setParams(saved ?? next);
    },
    [setParams]
  );

  const onAdd = useCallback(
    async (draft: DraftRow) => {
      const p = draftToParam(draft);
      if (!p.name || !p.expression) {
        showToast('Name and expression are required.', 'error');
        throw new Error('validation');
      }
      if (params.some((x) => x.name === p.name)) {
        showToast(`A global parameter named "${p.name}" already exists.`, 'error');
        throw new Error('duplicate');
      }
      try {
        await persist([...params, p]);
        showToast(`Added "${p.name}".`, 'success');
        await pushToDesign();
      } catch (e) {
        showToast(`Save failed: ${String(e)}`, 'error');
        throw e;
      }
    },
    [params, persist, pushToDesign, showToast]
  );

  const onEdit = useCallback(
    async (originalName: string, draft: DraftRow) => {
      const p = draftToParam(draft);
      if (!p.name || !p.expression) {
        showToast('Name and expression are required.', 'error');
        throw new Error('validation');
      }
      if (p.name !== originalName && params.some((x) => x.name === p.name)) {
        showToast(`A global parameter named "${p.name}" already exists.`, 'error');
        throw new Error('duplicate');
      }
      try {
        await persist(params.map((x) => (x.name === originalName ? p : x)));
        showToast(`Updated "${p.name}".`, 'success');
      } catch (e) {
        showToast(`Save failed: ${String(e)}`, 'error');
        throw e;
      }
    },
    [params, persist, showToast]
  );

  const onDelete = useCallback(
    async (name: string) => {
      try {
        await persist(params.filter((x) => x.name !== name));
        showToast(`Deleted "${name}".`, 'success');
      } catch (e) {
        showToast(`Delete failed: ${String(e)}`, 'error');
      }
    },
    [params, persist, showToast]
  );



  return (
    <div id="pp_globalTab" className="pp_tabPanel">
      <ParamTable
        idPrefix="pp_global"
        rows={toRows(params)}
        columns={COLUMNS}
        editableFields={['name', 'expression', 'unit', 'comment', 'category']}
        canAdd
        onAdd={onAdd}
        onEdit={onEdit}
        onDelete={onDelete}
        refName={(name) => `{{${sanitizeName(name)}}}`}
        busy={busy}
        emptyTitle="No global parameters"
        emptyMessage="Add app-wide parameters here, then push them into any open design."
      />
    </div>
  );
}
