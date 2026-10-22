import { useEffect, useState } from 'react';

import { IconPlus, IconTarget, IconX } from '@tabler/icons-react';

import { request } from '../../connector/fusionBridge';
import type { ProjectParam } from '../../types/types';
import { prepareVariationValue, variationEditorValue } from '../../utils/variations';
import { useToast } from '../common/Toast';

type Props = {
  param: ProjectParam;
  onClose: () => void;
  onSaved: () => void;
};

function initialValues(param: ProjectParam): string[] {
  const unit = param.unit ?? '';
  const stored = param.variations ?? [];
  if (stored.length === 0) return [variationEditorValue(param.expression, unit)];
  return stored.map((value) => variationEditorValue(value, unit));
}

/** True when a row is the parameter's current expression, ignoring spacing. */
function isCurrentValue(rowValue: string, expression: string, unit: string): boolean {
  const row = prepareVariationValue(rowValue, unit);
  const current = prepareVariationValue(variationEditorValue(expression, unit), unit);
  if (!row || !current) return false;
  if (row === current) return true;
  return row.replace(/\s+/g, '') === current.replace(/\s+/g, '');
}

export function VariationsDialog({ param, onClose, onSaved }: Props) {
  const { showToast } = useToast();
  const [values, setValues] = useState(() => initialValues(param));
  const [currentExpression, setCurrentExpression] = useState(param.expression);
  const [saving, setSaving] = useState(false);
  const [setting, setSetting] = useState(false);
  const [error, setError] = useState('');
  const unit = param.unit ?? '';
  const isText = unit === 'Text';
  const busy = saving || setting;

  useEffect(() => {
    setCurrentExpression(param.expression);
  }, [param.expression, param.name]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  const setMainValue = async (rowValue: string) => {
    const expression = prepareVariationValue(rowValue, unit);
    if (!expression) {
      setError('Enter a value before using it as the parameter value.');
      return;
    }
    if (isCurrentValue(rowValue, currentExpression, unit)) return;
    setSetting(true);
    setError('');
    try {
      const updated = await request<ProjectParam>('project:update', {
        originalName: param.name,
        name: param.name,
        expression,
        unit,
        comment: param.comment ?? '',
      });
      setCurrentExpression(updated.expression);
      showToast(`Set "${param.name}" to ${variationEditorValue(updated.expression, unit)}.`, 'success');
      onSaved();
    } catch (updateError) {
      setError(String(updateError));
    } finally {
      setSetting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError('');
    const prepared = values
      .map((value) => prepareVariationValue(value, unit))
      .filter((value) => value.length > 0);
    try {
      await request<ProjectParam>('project:setVariations', { name: param.name, values: prepared });
      showToast(
        prepared.length === 0
          ? `Removed variations from "${param.name}".`
          : `Saved ${prepared.length} variation${prepared.length === 1 ? '' : 's'} for "${param.name}".`,
        'success'
      );
      onSaved();
      onClose();
    } catch (saveError) {
      setError(String(saveError));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      id="pp_variationsBackdrop"
      className="pp_modalBackdrop"
      onClick={() => {
        if (!busy) onClose();
      }}
    >
      <form
        id="pp_variationsDialog"
        className="pp_modal"
        role="dialog"
        aria-labelledby="pp_variationsTitle"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy) void save();
        }}
      >
        <header id="pp_variationsHeader" className="pp_modalHeader">
          <h2 id="pp_variationsTitle" className="pp_modalTitle">
            Variations for {param.name}
          </h2>
        </header>

        <div id="pp_variationsBody" className="pp_modalBody">
          <p id="pp_variationsHelp" className="pp_help">
            {isText
              ? 'Each row is a text value. Export writes one file for every combination of the saved lists, then puts this parameter back.'
              : 'Each row is an expression. A bare number uses the parameter unit. Export writes one file for every combination, then restores the current value.'}
          </p>
          <div id="pp_variationsList" className="pp_variationList">
            {values.map((value, index) => {
              const isCurrent = isCurrentValue(value, currentExpression, unit);
              return (
                <div id={`pp_variationsRow_${index}`} key={index} className="pp_variationRow">
                  <input
                    id={`pp_variationsValue_${index}`}
                    className="pp_input"
                    type="text"
                    value={value}
                    disabled={busy}
                    spellCheck={false}
                    autoComplete="off"
                    placeholder={isText ? 'Text' : 'Expression'}
                    aria-label={`Variation ${index + 1}`}
                    onChange={(event) => {
                      const next = event.target.value;
                      setValues((current) => current.map((item, itemIndex) => (itemIndex === index ? next : item)));
                    }}
                  />
                  <button
                    id={`pp_variationsSet_${index}`}
                    className={isCurrent ? 'pp_iconBtn pp_iconBtnActive' : 'pp_iconBtn'}
                    type="button"
                    title={isCurrent ? 'Current parameter value' : 'Set as parameter value'}
                    aria-label={isCurrent ? 'Current parameter value' : 'Set as parameter value'}
                    aria-pressed={isCurrent}
                    disabled={busy}
                    onClick={() => {
                      void setMainValue(value);
                    }}
                  >
                    <IconTarget size={16} />
                  </button>
                  <button
                    id={`pp_variationsRemove_${index}`}
                    className="pp_iconBtn"
                    type="button"
                    title="Remove value"
                    aria-label="Remove value"
                    disabled={busy}
                    onClick={() => {
                      setValues((current) => {
                        const next = current.filter((_, itemIndex) => itemIndex !== index);
                        return next.length > 0 ? next : [''];
                      });
                    }}
                  >
                    <IconX size={16} />
                  </button>
                </div>
              );
            })}
          </div>
          <button
            id="pp_variationsAdd"
            className="pp_btn"
            type="button"
            disabled={busy}
            onClick={() => setValues((current) => [...current, ''])}
          >
            <IconPlus size={16} />
            Add value
          </button>
          {error && (
            <p id="pp_variationsError" className="pp_formError">
              {error}
            </p>
          )}
        </div>

        <footer id="pp_variationsFooter" className="pp_modalFooter">
          <button id="pp_variationsCancel" className="pp_btn" type="button" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button id="pp_variationsSave" className="pp_btn pp_btnPrimary" type="submit" disabled={busy}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </footer>
      </form>
    </div>
  );
}
