import { IconHelp, IconSettings } from '@tabler/icons-react';

import type { TabId } from '../../types/types';

type Props = {
  active: TabId;
  showJoints: boolean;
  onChange: (tab: TabId) => void;
};

const TABS: { id: TabId; label: string }[] = [
  { id: 'sketches', label: 'Sketches' },
  { id: 'joints', label: 'Joints' },
  { id: 'constraints', label: 'Assembly constraints' },
];

const ASSEMBLY_TABS: TabId[] = ['joints', 'constraints'];

export function Tabs({ active, showJoints, onChange }: Props) {
  const tabs = TABS.filter((tab) => showJoints || !ASSEMBLY_TABS.includes(tab.id));
  const helpSelected = active === 'help';
  const settingsSelected = active === 'settings';

  return (
    <div id="cs_tabs" className="cs_tabs" role="tablist">
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            id={`cs_tab_${tab.id}`}
            className={selected ? 'cs_tab cs_tabActive' : 'cs_tab'}
            type="button"
            role="tab"
            aria-selected={selected}
            title={tab.label}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        );
      })}

      <div id="cs_tabsRight" className="cs_tabsRight">
        <button
          id="cs_tab_settings"
          className={settingsSelected ? 'cs_tab cs_tabSettings cs_tabActive' : 'cs_tab cs_tabSettings'}
          type="button"
          role="tab"
          aria-selected={settingsSelected}
          aria-label="Settings"
          title="Settings"
          onClick={() => onChange('settings')}
        >
          <IconSettings id="cs_tabSettingsIcon" size={16} />
        </button>

        <button
          id="cs_tab_help"
          className={helpSelected ? 'cs_tab cs_tabHelp cs_tabActive' : 'cs_tab cs_tabHelp'}
          type="button"
          role="tab"
          aria-selected={helpSelected}
          aria-label="Help"
          title="Help"
          onClick={() => onChange('help')}
        >
          <IconHelp id="cs_tabHelpIcon" size={16} />
        </button>
      </div>

    </div>
  );
}
