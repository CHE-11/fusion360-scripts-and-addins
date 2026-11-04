export function HelpTab() {
  return (
    <div id="th_helpTab" className="th_body th_help">
      <p id="th_helpLead">
        Threader builds a thread you can change after a test print. Clearance is modeled in, not left as a note.
      </p>
      <h2 id="th_helpModesTitle">Male, female, inset, outset</h2>
      <ul id="th_helpModes">
        <li id="th_helpMaleOut">Male outset adds teeth outside the face. The face is the root.</li>
        <li id="th_helpMaleIn">Male inset cuts grooves into the face. The face stays the major diameter.</li>
        <li id="th_helpFemaleOut">Female outset adds teeth inside a hole. The face is the major diameter.</li>
        <li id="th_helpFemaleIn">Female inset cuts grooves into the wall. The face is the minor diameter.</li>
      </ul>
      <h2 id="th_helpFitTitle">Fit</h2>
      <ul id="th_helpFit">
        <li id="th_helpPlastic">Plastic on plastic starts at 0.20 mm radial clearance and a 45° trapezoid. Pitch snaps to the layer height.</li>
        <li id="th_helpMetal">Metal fasteners use ISO metric, UNC, or UNF with 0.15 mm radial clearance. Pitch is not snapped, so it still matches the screw.</li>
        <li id="th_helpNudge">After printing, open Adjust. Too tight adds 0.05 mm of clearance. Too loose removes it. A male thread gets smaller. A female thread gets larger.</li>
      </ul>
      <h2 id="th_helpPrintTitle">Print it</h2>
      <ul id="th_helpPrint">
        <li id="th_helpAxis">Stand the thread axis up on the printer. Sideways threads are weaker and need more clearance.</li>
        <li id="th_helpNozzle">Crests on the printable profile stay at least as wide as the nozzle. Sharp metric tips below that will not form fully.</li>
        <li id="th_helpSmall">Below M5 or #10, use a heat-set insert or tap the hole instead of modeling the thread.</li>
        <li id="th_helpInsert">Insert holes are typical starting sizes. Too tight opens the hole by 0.10 mm. Press the insert in with heat, not cold.</li>
      </ul>
    </div>
  );
}
