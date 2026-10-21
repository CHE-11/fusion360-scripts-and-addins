import { useEffect, useState } from 'react';

import { IconExternalLink, IconFolder } from '@tabler/icons-react';

import { request } from '../../connector/fusionBridge';
import type { BrowseParamsFileResult, ParamsLocation } from '../../types/types';
import { loadGlobalParams } from '../../utils/globalParams';
import { useToast } from '../common/Toast';

type Props = {
  onClose: () => void;
};

export function SettingsDialog({ onClose }: Props) {
  const { showToast } = useToast();
  const [path, setPath] = useState('');
  const [defaultPath, setDefaultPath] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    void request<ParamsLocation>('settings:get')
      .then((location) => {
        if (cancelled) return;
        setPath(location.globalParamsPath);
        setDefaultPath(location.defaultPath);
      })
      .catch((loadError) => {
        if (!cancelled) setError(`Could not load settings: ${String(loadError)}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving && !browsing) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [browsing, onClose, saving]);

  const browse = async () => {
    setBrowsing(true);
    setError('');
    try {
      const result = await request<BrowseParamsFileResult>('settings:browse', {
        globalParamsPath: path,
      });
      if (!result.cancelled && result.path) setPath(result.path);
    } catch (browseError) {
      setError(String(browseError));
    } finally {
      setBrowsing(false);
    }
  };

  const reveal = async () => {
    setOpening(true);
    setError('');
    try {
      await request('settings:reveal', { globalParamsPath: path.trim() });
    } catch (revealError) {
      setError(String(revealError));
    } finally {
      setOpening(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const location = await request<ParamsLocation>('settings:set', {
        globalParamsPath: path.trim(),
      });
      setPath(location.globalParamsPath);
      await loadGlobalParams();
      showToast(
        location.isCustom
          ? 'Global parameters now load from the shared file.'
          : 'Global parameters now load from the default file.',
        'success'
      );
      onClose();
    } catch (saveError) {
      setError(String(saveError));
    } finally {
      setSaving(false);
    }
  };

  const busy = loading || saving || browsing;

  return (
    <div
      id="pp_settingsBackdrop"
      className="pp_modalBackdrop"
      onClick={() => {
        if (!busy) onClose();
      }}
    >
      <form
        id="pp_settingsDialog"
        className="pp_modal"
        role="dialog"
        aria-labelledby="pp_settingsTitle"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy) void save();
        }}
      >
        <header id="pp_settingsHeader" className="pp_modalHeader">
          <h2 id="pp_settingsTitle" className="pp_modalTitle">
            Settings
          </h2>
        </header>

        <div id="pp_settingsBody" className="pp_modalBody">
          <label id="pp_settingsPathLabel" className="pp_fieldLabel" htmlFor="pp_settingsPath">
            Parameters file
          </label>
          <div id="pp_settingsPathRow" className="pp_pathRow">
            <input
              id="pp_settingsPath"
              className="pp_input"
              type="text"
              value={path}
              spellCheck={false}
              autoComplete="off"
              disabled={busy}
              placeholder={defaultPath || 'Path to ProParams_global.json'}
              onChange={(event) => setPath(event.target.value)}
            />
            <button
              id="pp_settingsBrowse"
              className="pp_btn"
              type="button"
              title="Choose a folder"
              disabled={busy}
              onClick={() => void browse()}
            >
              <IconFolder size={14} />
              Browse
            </button>
            <button
              id="pp_settingsReveal"
              className="pp_btn pp_btnIcon"
              type="button"
              title="Show in File Explorer"
              aria-label="Show in File Explorer"
              disabled={busy || opening || !path.trim()}
              onClick={() => void reveal()}
            >
              <IconExternalLink size={14} />
            </button>
          </div>
          <p id="pp_settingsHelp" className="pp_help">
            Global parameters are saved in this JSON file. Point it at a shared drive to use the same
            parameters across machines and users. An existing file is loaded. A new file is created with
            your current parameters.
          </p>
          {defaultPath && (
            <button
              id="pp_settingsUseDefault"
              className="pp_linkBtn"
              type="button"
              disabled={busy || path === defaultPath}
              onClick={() => setPath(defaultPath)}
            >
              Use the default location
            </button>
          )}
          {error && (
            <p id="pp_settingsError" className="pp_formError">
              {error}
            </p>
          )}
        </div>

        <footer id="pp_settingsFooter" className="pp_modalFooter">
          <button id="pp_settingsCancel" className="pp_btn" type="button" disabled={saving} onClick={onClose}>
            Cancel
          </button>
          <button id="pp_settingsSave" className="pp_btn pp_btnPrimary" type="submit" disabled={busy || !path.trim()}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </footer>
      </form>
    </div>
  );
}
