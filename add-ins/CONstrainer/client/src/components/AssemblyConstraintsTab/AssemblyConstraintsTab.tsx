import { IconRefresh, IconSearch, IconX } from '@tabler/icons-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { FusionError, request } from '../../connector/fusionBridge';
import type {
  AssemblyConstraintInfo,
  ConstraintList,
  ConstraintSelection,
  FocusKind,
  SelectionFocus,
} from '../../types/types';
import { EmptyState } from '../common/EmptyState';
import { useToast } from '../common/Toast';
import { ConstraintRow, constraintDomId } from './ConstraintRow';

type Props = {
  booted: boolean;
  active: boolean;
  revision: number;
  selection: ConstraintSelection;
};

type ConstraintGroup = {
  name: string;
  token: string;
  constraints: AssemblyConstraintInfo[];
};

type FocusView = {
  focus: SelectionFocus;
  direct: AssemblyConstraintInfo[];
  component: AssemblyConstraintInfo[];
};

const FOCUS_NOUNS: Record<FocusKind, string> = {
  planarFace: 'face',
  face: 'face',
  curve: 'edge',
  point: 'point',
  jointOrigin: 'joint origin',
  body: 'body',
  component: 'component',
};

// Selecting a constraint from the list replaces the canvas selection, so keep the focus view briefly.
const KEEP_FOCUS_MS = 1500;

function messageOf(error: unknown, fallback: string) {
  if (error instanceof FusionError || error instanceof Error) return error.message;
  return fallback;
}

function groupConstraints(constraints: AssemblyConstraintInfo[]): ConstraintGroup[] {
  const groups: ConstraintGroup[] = [];
  for (const constraint of constraints) {
    const token = constraint.componentToken || constraint.component || 'assembly';
    const existing = groups.find((group) => group.token === token);
    if (existing) existing.constraints.push(constraint);
    else groups.push({ name: constraint.component || 'Assembly', token, constraints: [constraint] });
  }
  return groups;
}

export function AssemblyConstraintsTab({ booted, active, revision, selection }: Props) {
  const { showToast } = useToast();
  const [constraints, setConstraints] = useState<AssemblyConstraintInfo[]>([]);
  const [supported, setSupported] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState('');
  const [focusView, setFocusView] = useState<FocusView | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const savingName = useRef(false);
  const cancelRename = useRef(false);
  const keepFocusUntil = useRef(0);

  useEffect(() => {
    if (!booted) return;
    let cancelled = false;
    setLoading(true);
    request<ConstraintList>('constraint:list')
      .then((data) => {
        if (cancelled) return;
        setConstraints(data.constraints);
        setSupported(data.supported);
        setLoadError(null);
      })
      .catch((error) => {
        if (!cancelled) setLoadError(messageOf(error, 'Could not load assembly constraints.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [booted, revision, tick]);

  useEffect(() => {
    setFocusView(null);
  }, [revision]);

  useEffect(() => {
    if (selection.focus) {
      setFocusView({ focus: selection.focus, direct: selection.direct, component: selection.component });
    } else if (Date.now() > keepFocusUntil.current) {
      setFocusView(null);
    }
  }, [selection]);

  const focusToken = focusView?.focus.token ?? '';
  useEffect(() => {
    setShowAll(false);
  }, [focusToken]);

  const byToken = useMemo(() => new Map(constraints.map((item) => [item.token, item])), [constraints]);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (constraint: AssemblyConstraintInfo) =>
      !needle ||
      [
        constraint.name,
        constraint.typeLabel,
        constraint.sideOne,
        constraint.sideTwo,
        constraint.component,
        constraint.isSuppressed ? 'suppressed' : '',
        constraint.isLightBulbOn ? '' : 'hidden',
        constraint.health === 'ok' ? '' : constraint.health,
        ...constraint.relationships.flatMap((item) => [item.name, item.entityOne, item.entityTwo, item.expression]),
      ]
        .join(' ')
        .toLowerCase()
        .includes(needle);
  }, [query]);

  const filtered = useMemo(() => constraints.filter(matches), [constraints, matches]);
  const groups = useMemo(() => groupConstraints(filtered), [filtered]);

  const related = useMemo(() => {
    const fresh = (items: AssemblyConstraintInfo[]) => items.map((item) => byToken.get(item.token) ?? item).filter(matches);
    return {
      direct: fresh(focusView?.direct ?? []),
      component: fresh(focusView?.component ?? []),
    };
  }, [focusView, byToken, matches]);

  const problemCount = constraints.filter((item) => item.health !== 'ok').length;

  const reload = () => setTick((value) => value + 1);

  const replaceConstraint = (updated: AssemblyConstraintInfo) => {
    setConstraints((current) => current.map((item) => (item.token === updated.token ? updated : item)));
  };

  const dropFromFocus = (token: string) => {
    setFocusView(
      (current) =>
        current && {
          ...current,
          direct: current.direct.filter((item) => item.token !== token),
          component: current.component.filter((item) => item.token !== token),
        }
    );
  };

  const run = async (token: string, action: string, payload: Record<string, unknown>, failure: string) => {
    setBusy(token);
    try {
      const updated = await request<AssemblyConstraintInfo>(action, { token, ...payload });
      if (updated?.token) replaceConstraint(updated);
      reload();
    } catch (error) {
      showToast(messageOf(error, failure), 'error');
      reload();
    } finally {
      setBusy('');
    }
  };

  const selectConstraint = async (token: string) => {
    keepFocusUntil.current = Date.now() + KEEP_FOCUS_MS;
    try {
      await request('constraint:select', { token });
    } catch (error) {
      showToast(messageOf(error, 'Could not highlight that constraint.'), 'error');
    }
  };

  const highlightConstraint = (token: string) => {
    void request('constraint:highlight', { token }).catch(() => {
      // Hover stays quiet when Fusion cannot highlight the constraint.
    });
  };

  const clearHighlight = (token: string) => {
    void request('constraint:clearHighlight', { token }).catch(() => {
      // The highlight is already gone if Fusion closed the palette.
    });
  };

  useEffect(() => {
    if (active) return;
    void request('constraint:clearHighlight', {}).catch(() => {
      // Leaving the tab drops a hover highlight. A pinned highlight stays.
    });
  }, [active]);

  const removeConstraint = async (constraint: AssemblyConstraintInfo) => {
    setBusy(constraint.token);
    try {
      await request('constraint:delete', { token: constraint.token });
      showToast(`Deleted ${constraint.name}.`, 'success');
      dropFromFocus(constraint.token);
      reload();
    } catch (error) {
      showToast(messageOf(error, 'Could not delete that constraint.'), 'error');
    } finally {
      setBusy('');
    }
  };

  const saveName = async (constraint: AssemblyConstraintInfo) => {
    if (cancelRename.current) {
      cancelRename.current = false;
      return;
    }
    if (savingName.current) return;
    const name = draft.trim();
    setEditing(null);
    if (!name) {
      showToast('Name is required.', 'error');
      return;
    }
    if (name === constraint.name) return;
    savingName.current = true;
    try {
      await run(constraint.token, 'constraint:rename', { name }, 'Could not rename that constraint.');
    } finally {
      savingName.current = false;
    }
  };

  const renderRow = (constraint: AssemblyConstraintInfo) => (
    <ConstraintRow
      key={constraint.token}
      constraint={constraint}
      busy={busy === constraint.token}
      editing={editing === constraint.token}
      draft={draft}
      onDraftChange={setDraft}
      onStartRename={() => {
        setEditing(constraint.token);
        setDraft(constraint.name);
      }}
      onSaveName={() => void saveName(constraint)}
      onCancelRename={() => {
        cancelRename.current = true;
        setEditing(null);
      }}
      onSelect={() => void selectConstraint(constraint.token)}
      onHighlight={() => highlightConstraint(constraint.token)}
      onClearHighlight={() => clearHighlight(constraint.token)}
      onToggleVisible={() =>
        void run(constraint.token, 'constraint:setVisible', { visible: !constraint.isLightBulbOn }, 'Could not change visibility.')
      }
      onToggleSuppressed={() =>
        void run(constraint.token, 'constraint:setSuppressed', { suppressed: !constraint.isSuppressed }, 'Could not change suppression.')
      }
      onDelete={() => void removeConstraint(constraint)}
    />
  );

  const focus = focusView?.focus ?? null;
  const focusNoun = focus ? FOCUS_NOUNS[focus.kind] ?? 'item' : '';
  const showFocus = !!focus && !showAll;

  return (
    <section
      id="cs_constraintPanel"
      className="cs_tabPanel"
      hidden={!active}
      role="tabpanel"
      aria-labelledby="cs_tab_constraints"
    >
      <div id="cs_constraintToolbar" className="cs_toolbar">
        <div id="cs_constraintSearch" className="cs_search">
          <IconSearch size={14} className="cs_searchIcon" />
          <input
            id="cs_constraintSearchInput"
            className="cs_input cs_searchInput"
            type="search"
            placeholder="Search assembly constraints"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query && (
            <button
              id="cs_constraintSearchClear"
              className="cs_iconBtn cs_searchClear"
              type="button"
              aria-label="Clear search"
              onClick={() => setQuery('')}
            >
              <IconX size={14} />
            </button>
          )}
        </div>
        <span id="cs_constraintCount" className="cs_count">
          {loading ? 'Loading…' : problemCount > 0
              ? `${problemCount} need attention · ${constraints.length}`
              : `${constraints.length} constraint${constraints.length === 1 ? '' : 's'}`}
        </span>
        <button
          id="cs_constraintRefresh"
          className="cs_iconBtn"
          type="button"
          title="Refresh"
          aria-label="Refresh assembly constraints"
          onClick={reload}
        >
          <IconRefresh size={16} />
        </button>
      </div>

      <div id="cs_constraintList" className="cs_list">
        {focus && supported && (
          <div id="cs_constraintFocus" className="cs_focus">
            <div id="cs_constraintFocusText" className="cs_focusText">
              <span id="cs_constraintFocusLabel" className="cs_focusTitle">
                {focus.label}
              </span>
              {focus.occurrenceName && focus.kind !== 'component' && (
                <span id="cs_constraintFocusOccurrence" className="cs_muted">
                  {focus.occurrenceName}
                </span>
              )}
            </div>
            <button id="cs_constraintFocusToggle" className="cs_btn" type="button" onClick={() => setShowAll((value) => !value)}>
              {showAll ? 'Show selected' : 'Show all'}
            </button>
            <button
              id="cs_constraintFocusClear"
              className="cs_iconBtn"
              type="button"
              aria-label="Clear selected item"
              onClick={() => setFocusView(null)}
            >
              <IconX size={14} />
            </button>
          </div>
        )}

        {loadError && <EmptyState id="cs_constraintLoadError" title="Could not load assembly constraints" message={loadError} />}

        {!loadError && !supported && (
          <EmptyState
            id="cs_constraintUnsupported"
            title="Not available in this Fusion"
            message="Update Fusion to view and edit assembly constraints from this add-in."
          />
        )}

        {!loadError && supported && showFocus && (
          <>
            <section id="cs_constraintDirect" className="cs_group">
              <h2 id="cs_constraintDirectTitle" className="cs_groupTitle">
                On this {focusNoun} · {related.direct.length}
              </h2>
              {related.direct.length === 0 && (
                <p id="cs_constraintDirectEmpty" className="cs_hint cs_groupEmpty">
                  No assembly constraints use this {focusNoun}.
                </p>
              )}
              {related.direct.map(renderRow)}
            </section>
            {focus.kind !== 'component' && focus.occurrenceName && (
              <section id="cs_constraintComponent" className="cs_group">
                <h2 id="cs_constraintComponentTitle" className="cs_groupTitle">
                  Other constraints on {focus.occurrenceName} · {related.component.length}
                </h2>
                {related.component.length === 0 && (
                  <p id="cs_constraintComponentEmpty" className="cs_hint cs_groupEmpty">
                    No other assembly constraints on this component.
                  </p>
                )}
                {related.component.map(renderRow)}
              </section>
            )}
          </>
        )}

        {!loadError && supported && !showFocus && (
          <>
            {!loading && constraints.length === 0 && (
              <EmptyState
                id="cs_constraintEmpty"
                title="No assembly constraints"
                message="Use Assemble › Constrain Components in Fusion to add one. It will show up here."
              />
            )}
            {!loading && constraints.length > 0 && filtered.length === 0 && (
              <EmptyState id="cs_constraintNoMatches" title="No matches" message="Try a different name, component, or geometry." />
            )}
            {groups.map((group) => (
              <section key={group.token} id={constraintDomId('cs_constraintGroup', group.token)} className="cs_group">
                <h2 id={constraintDomId('cs_constraintGroupName', group.token)} className="cs_groupTitle">
                  {group.name}
                </h2>
                {group.constraints.map(renderRow)}
              </section>
            ))}
          </>
        )}
      </div>
    </section>
  );
}
