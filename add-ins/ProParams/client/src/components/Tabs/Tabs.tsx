import { useEffect, useState, type ReactNode } from 'react';

import { IconArrowsTransferUpDown, IconBox, IconFileSettings, IconSettings, IconWorld } from '@tabler/icons-react';

import type { TabId } from '../../types/types';
import { useGlobalParams } from '../../utils/globalParams';
import { getLastSyncAt, subscribeLastSync } from '../../utils/lastSync';

type TabDef = {
  id: TabId;
  label: string;
  icon: ReactNode;
  hint: string;
};

const TABS: TabDef[] = [
  { id: 'global', label: 'Global', icon: <IconWorld size={16} />, hint: 'App-wide saved parameters' },
  { id: 'project', label: 'Project', icon: <IconBox size={16} />, hint: 'Parameters in the active design' },
];

function formatSyncTime(at: number): string {
  const date = new Date(at);
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  const time = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (sameDay) return time;
  const day = date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  return `${day}, ${time}`;
}

type Props = {
  active: TabId;
  onChange: (tab: TabId) => void; 
  openSettings: () => void;
};

export function Tabs({ ...props }: Props) {
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(getLastSyncAt());
  const { params, busy, pushToDesign } = useGlobalParams();

  useEffect(() => subscribeLastSync(setLastSyncAt), []);

  const syncLabel = lastSyncAt == null ? '—' : formatSyncTime(lastSyncAt);
  const syncTitle =
    lastSyncAt == null
      ? 'Not synced yet'
      : `Last sync ${new Date(lastSyncAt).toLocaleString()}`;

  return (
    <div id="pp_tabs" className="pp_tabs">
      <div id="pp_tabList" className="pp_tabList" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            id={`pp_tab_${tab.id}`}
            className={`pp_tab ${props.active === tab.id ? 'pp_tabActive' : ''}`}
            role="tab"
            aria-selected={props.active === tab.id}
            title={tab.hint}
            onClick={() => props.onChange(tab.id)}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      <span id="pp_lastSync" className="pp_lastSync" title={syncTitle}>
        Last sync {syncLabel}
      </span>
      <button
        id="pp_global_pushBtn"
        className="pp_btn"
        title="Sync global parameters into the active design"
        onClick={() => void pushToDesign()}
        disabled={busy || params.length === 0}
      >
        <IconArrowsTransferUpDown size={14} />
      </button>
      <button
        id="pp_settingsBtn"
        className="pp_btn"
        title="Open settings"
        onClick={() => void props.openSettings()}
      >
        <IconSettings size={14} />
      </button>
    </div>
  );
}
