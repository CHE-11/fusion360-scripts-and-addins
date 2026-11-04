import { IconHelp } from '@tabler/icons-react';

import type { TabId } from '../../types/types';

type Props = {
  active: TabId;
  onChange: (tab: TabId) => void;
};

const TABS: { id: TabId; label: string }[] = [
  { id: 'thread', label: 'Thread' },
  { id: 'insert', label: 'Heat-set' },
  { id: 'adjust', label: 'Adjust' },
];

export function Tabs({ active, onChange }: Props) {
  return (
    <div id="th_tabs" className="th_tabs" role="tablist">
      {TABS.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            id={`th_tab_${tab.id}`}
            className={selected ? 'th_tab th_tabActive' : 'th_tab'}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        );
      })}
      <button
        id="th_tab_help"
        className={active === 'help' ? 'th_tab th_tabActive' : 'th_tab'}
        type="button"
        role="tab"
        aria-selected={active === 'help'}
        aria-label="Help"
        title="Help"
        onClick={() => onChange('help')}
      >
        <IconHelp id="th_tabHelpIcon" size={16} />
      </button>
    </div>
  );
}
