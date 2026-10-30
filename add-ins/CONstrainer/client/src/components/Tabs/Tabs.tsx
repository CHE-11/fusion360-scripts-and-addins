import { IconHelp } from '@tabler/icons-react';

import type { TabId } from '../../types/types';

type Props = {
  active: TabId;
  showAssembly: boolean;
  onChange: (tab: TabId) => void;
};

const TABS: { id: TabId; label: string }[] = [
  { id: 'sketches', label: 'Sketches' },
  { id: 'constraints', label: 'Assembly constraints' },
];

export function Tabs({ active, showAssembly, onChange }: Props) {
  const tabs = TABS.filter((tab) => showAssembly || tab.id !== 'constraints');
  const helpSelected = active === 'help';

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
