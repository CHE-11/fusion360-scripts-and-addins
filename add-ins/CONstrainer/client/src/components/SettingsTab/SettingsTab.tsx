type Props = {
  active: boolean;
};

export function SettingsTab({ active }: Props) {
  return (
    <section id="cs_settingsPanel" className="cs_tabPanel" hidden={!active} role="tabpanel" aria-labelledby="cs_tab_settings">
   
    </section>
  );
}
