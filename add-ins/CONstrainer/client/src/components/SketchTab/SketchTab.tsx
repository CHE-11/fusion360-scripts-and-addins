import { IconChevronDown, IconChevronRight, IconCurrentLocation, IconRefresh, IconSearch, IconTrash, IconX } from '@tabler/icons-react';
import { useEffect, useMemo, useState } from 'react';

import { FusionError, request } from '../../connector/fusionBridge';
import type { CompatibleConstraint, SketchConstraint, SketchList, SketchSelection } from '../../types/types';
import { EmptyState } from '../common/EmptyState';
import { useToast } from '../common/Toast';

type Props = {
  booted: boolean;
  active: boolean;
  revision: number;
  selection: SketchSelection;
  onSelection: (selection: SketchSelection) => void;
};

function domId(prefix: string, token: string) {
  const safe = token.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 80);
  return `${prefix}_${safe || 'item'}`;
}

function messageOf(error: unknown, fallback: string) {
  if (error instanceof FusionError || error instanceof Error) return error.message;
  return fallback;
}

function constraintRequest(constraint: SketchConstraint) {
  return {
    token: constraint.token,
    sketchToken: constraint.sketchToken,
    index: constraint.index,
    type: constraint.type,
    entityTokens: constraint.entities.map((entity) => entity.token),
    sharedPointToken: constraint.sharedPointToken ?? '',
  };
}

export function SketchTab({ booted, active, revision, selection, onSelection }: Props) {
  const { showToast } = useToast();
  const [list, setList] = useState<SketchList>({ components: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [tick, setTick] = useState(0);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState('');

  useEffect(() => {
    if (!booted) return;
    let cancelled = false;
    setLoading(true);
    request<SketchList>('sketch:list')
      .then((data) => {
        if (cancelled) return;
        setList(data);
        setLoadError(null);
        setOpen((current) => {
          const next = { ...current };
          for (const group of data.components) {
            for (const sketch of group.sketches) {
              if (!(sketch.token in next)) next[sketch.token] = !sketch.isFullyConstrained;
            }
          }
          return next;
        });
      })
      .catch((error) => {
        if (!cancelled) setLoadError(messageOf(error, 'Could not load sketches.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [booted, revision, tick]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return list.components;
    return list.components
      .map((group) => ({
        ...group,
        sketches: group.sketches.filter((sketch) => {
          const haystack = [
            group.name,
            sketch.name,
            ...sketch.constraints.flatMap((constraint) => [constraint.label, ...constraint.entities.map((entity) => entity.label)]),
          ]
            .join(' ')
            .toLowerCase();
          return haystack.includes(needle);
        }),
      }))
      .filter((group) => group.sketches.length > 0);
  }, [list, query]);

  const sketchCount = list.components.reduce((sum, group) => sum + group.sketches.length, 0);
  const openCount = list.components.reduce(
    (sum, group) => sum + group.sketches.filter((sketch) => !sketch.isFullyConstrained).length,
    0
  );

  const addConstraint = async (option: CompatibleConstraint) => {
    setBusy(option.type);
    try {
      const result = await request<{ sketchToken: string; constraint: { label: string } }>('sketch:add', {
        type: option.type,
        entityTokens: option.entityTokens,
      });
      showToast(`Added ${result.constraint?.label ?? option.label}.`, 'success');
      if (result.sketchToken) setOpen((current) => ({ ...current, [result.sketchToken]: true }));
      setTick((value) => value + 1);
    } catch (error) {
      showToast(messageOf(error, 'Could not add that constraint.'), 'error');
    } finally {
      setBusy('');
    }
  };

  const deleteConstraint = async (constraint: SketchConstraint) => {
    setBusy(constraint.token);
    try {
      await request('sketch:delete', constraintRequest(constraint));
      showToast(`Deleted ${constraint.label}.`, 'success');
      setTick((value) => value + 1);
    } catch (error) {
      showToast(messageOf(error, 'Could not delete that constraint.'), 'error');
    } finally {
      setBusy('');
    }
  };

  const selectToken = async (token: string) => {
    try {
      await request('sketch:select', { token });
    } catch (error) {
      showToast(messageOf(error, 'Could not select that item.'), 'error');
    }
  };

  const selectConstraint = async (constraint: SketchConstraint) => {
    try {
      await request('sketch:select', constraintRequest(constraint));
    } catch (error) {
      showToast(messageOf(error, 'Could not select that item.'), 'error');
    }
  };

  const highlightConstraint = (constraint: SketchConstraint) => {
    void request('sketch:highlight', constraintRequest(constraint)).catch(() => {
      // Hover stays quiet when Fusion cannot draw the highlight.
    });
  };

  const clearConstraintHighlight = () => {
    void request('sketch:clearHighlight').catch(() => {
      // The highlight is already gone if Fusion closed the palette.
    });
  };

  return (
    <section id="cs_sketchPanel" className="cs_tabPanel" hidden={!active} role="tabpanel" aria-labelledby="cs_tab_sketches">
      {(selection.entities.length > 0 || selection.compatible.length > 0) && (
        <div id="cs_sketchCreate" className="cs_create">
          {selection.entities.length > 0 && (
            <p id="cs_sketchSelectionSummary" className="cs_selectionSummary">
              {selection.sketchName ? `${selection.sketchName}: ` : ''}
              {selection.entities.map((entity) => entity.label).join(' · ')}
            </p>
          )}
          {selection.compatible.length > 0 && (
            <div id="cs_sketchCompatible" className="cs_chipRow">
              {selection.compatible.map((option) => (
                <button
                  key={option.type}
                  id={`cs_add_${option.type}`}
                  className="cs_btn"
                  type="button"
                  disabled={busy === option.type}
                  onClick={() => void addConstraint(option)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
          {selection.error && (
            <p id="cs_sketchSelectionError" className="cs_inlineError">
              {selection.error}
            </p>
          )}
        </div>
      )}

      <div id="cs_sketchToolbar" className="cs_toolbar">
        <div id="cs_sketchSearch" className="cs_search">
          <IconSearch size={14} className="cs_searchIcon" />
          <input
            id="cs_sketchSearchInput"
            className="cs_input cs_searchInput"
            type="search"
            placeholder="Search sketches"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query && (
            <button id="cs_sketchSearchClear" className="cs_iconBtn cs_searchClear" type="button" aria-label="Clear search" onClick={() => setQuery('')}>
              <IconX size={14} />
            </button>
          )}
        </div>
        <span id="cs_sketchCount" className="cs_count">
          {loading ? 'Loading…' : `${openCount} open · ${sketchCount} sketches`}
        </span>
        <button id="cs_sketchRefresh" className="cs_iconBtn" type="button" title="Refresh" aria-label="Refresh sketches" onClick={() => setTick((value) => value + 1)}>
          <IconRefresh size={16} />
        </button>
      </div>

      <div id="cs_sketchList" className="cs_list">
        {loadError && <EmptyState id="cs_sketchLoadError" title="Could not load sketches" message={loadError} />}
        {!loadError && !loading && sketchCount === 0 && (
          <EmptyState id="cs_sketchEmpty" title="No sketches" message="This design does not have any sketches yet." />
        )}
        {!loadError && !loading && sketchCount > 0 && filtered.length === 0 && (
          <EmptyState id="cs_sketchNoMatches" title="No matches" message="Try a different sketch, component, or constraint name." />
        )}
        {!loadError &&
          filtered.map((group) => (
            <section key={group.token || group.name} id={domId('cs_component', group.token || group.name)} className="cs_group">
              <h2 id={domId('cs_componentName', group.token || group.name)} className="cs_groupTitle">
                {group.name}
              </h2>
              {group.sketches.map((sketch) => {
                const expanded = query.trim() ? true : !!open[sketch.token];
                return (
                  <article key={sketch.token} id={domId('cs_sketch', sketch.token)} className="cs_sketch">
                    <div id={domId('cs_sketchHead', sketch.token)} className="cs_sketchHead">
                      <button
                        id={domId('cs_sketchToggle', sketch.token)}
                        className="cs_sketchToggle"
                        type="button"
                        aria-expanded={expanded}
                        onClick={() => setOpen((current) => ({ ...current, [sketch.token]: !expanded }))}
                      >
                        {expanded ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />}
                        <span id={domId('cs_sketchName', sketch.token)} className="cs_sketchName">
                          {sketch.name}
                        </span>
                        <span
                          id={domId('cs_sketchBadge', sketch.token)}
                          className={sketch.isFullyConstrained ? 'cs_badge cs_badgeOk' : 'cs_badge cs_badgeWarn'}
                        >
                          {sketch.isFullyConstrained ? 'Constrained' : 'Open'}
                        </span>
                        <span id={domId('cs_sketchConstraintCount', sketch.token)} className="cs_muted">
                          {sketch.constraints.length}
                        </span>
                      </button>
                      <button
                        id={domId('cs_sketchSelect', sketch.token)}
                        className="cs_iconBtn"
                        type="button"
                        title="Select sketch"
                        aria-label={`Select ${sketch.name}`}
                        onClick={() => void selectToken(sketch.token)}
                      >
                        <IconCurrentLocation size={15} />
                      </button>
                    </div>
                    {expanded && (
                      <ul id={domId('cs_constraints', sketch.token)} className="cs_constraints">
                        {sketch.constraints.length === 0 && (
                          <li id={domId('cs_sketchNoConstraints', sketch.token)} className="cs_muted cs_constraintEmpty">
                            {sketch.isFullyConstrained
                              ? 'No geometric constraints. Dimensions fully constrain this sketch.'
                              : 'No geometric constraints'}
                          </li>
                        )}
                        {sketch.constraints.map((constraint) => (
                          <li
                            key={`${constraint.sketchToken}:${constraint.index}:${constraint.type}`}
                            id={domId('cs_constraint', constraint.token)}
                            className="cs_constraint"
                            onMouseEnter={() => highlightConstraint(constraint)}
                            onMouseLeave={clearConstraintHighlight}
                          >
                            <button
                              id={domId('cs_constraintSelect', constraint.token)}
                              className="cs_constraintMain"
                              type="button"
                              onClick={() => void selectConstraint(constraint)}
                            >
                              <span id={domId('cs_constraintLabel', constraint.token)} className="cs_constraintLabel">
                                {constraint.label}
                              </span>
                              <span id={domId('cs_constraintEntities', constraint.token)} className="cs_muted">
                                {constraint.entities.map((entity) => entity.label).join(' · ') || 'Geometry'}
                              </span>
                            </button>
                            <button
                              id={domId('cs_constraintDelete', constraint.token)}
                              className="cs_iconBtn cs_iconBtnDanger"
                              type="button"
                              title={constraint.isDeletable ? 'Delete constraint' : 'This constraint cannot be deleted'}
                              aria-label={`Delete ${constraint.label}`}
                              disabled={!constraint.isDeletable || busy === constraint.token}
                              onClick={() => void deleteConstraint(constraint)}
                            >
                              <IconTrash size={15} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </article>
                );
              })}
            </section>
          ))}
      </div>
    </section>
  );
}
