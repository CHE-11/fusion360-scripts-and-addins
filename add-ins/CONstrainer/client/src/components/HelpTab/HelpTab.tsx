type GuideItem = {
  id: string;
  title: string;
  body: string;
};

const CHOICES: GuideItem[] = [
  {
    id: 'sketch',
    title: 'A line, point, or arc inside a sketch',
    body: 'Use a sketch constraint. Horizontal, coincident, tangent, and the rest only exist inside that sketch.',
  },
  {
    id: 'align',
    title: 'Two faces flush, a gap, or a set angle',
    body: 'Use an assembly constraint from Assemble → Constrain Components. Align for a mate and offset, Angle for an angle such as 90 deg.',
  },
];

const SKETCH_TYPES =
  'Coincident, collinear, concentric, equal, horizontal, horizontal points, midpoint, parallel, perpendicular, smooth, symmetry, tangent, vertical, vertical points, and offset.';

type Props = {
  active: boolean;
};

function showTopic(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export function HelpTab({ active }: Props) {
  return (
    <section id="cs_helpPanel" className="cs_tabPanel" hidden={!active} role="tabpanel" aria-labelledby="cs_tab_help">
      <div id="cs_helpScroll" className="cs_help">
        <header id="cs_helpIntro" className="cs_helpIntro">
          <h2 id="cs_helpTitle" className="cs_helpTitle">
            Two different relationships
          </h2>
          <p id="cs_helpLead" className="cs_helpLead">
            Fusion solves sketch geometry and component alignment separately. CONstrainer keeps each one on its own tab.
          </p>
        </header>

        <div id="cs_helpCards" className="cs_helpCards">
          <button id="cs_helpCard_sketches" className="cs_helpCard" type="button" onClick={() => showTopic('cs_helpTopic_sketches')}>
            <span id="cs_helpCardKicker_sketches" className="cs_helpKicker">
              Any design
            </span>
            <span id="cs_helpCardTitle_sketches" className="cs_helpCardTitle">
              Sketch constraints
            </span>
            <span id="cs_helpCardBody_sketches" className="cs_helpCardBody">
              How lines, points, and curves sit inside one sketch.
            </span>
          </button>
          <button id="cs_helpCard_constraints" className="cs_helpCard" type="button" onClick={() => showTopic('cs_helpTopic_constraints')}>
            <span id="cs_helpCardKicker_constraints" className="cs_helpKicker">
              Assembly and hybrid
            </span>
            <span id="cs_helpCardTitle_constraints" className="cs_helpCardTitle">
              Assembly constraints
            </span>
            <span id="cs_helpCardBody_constraints" className="cs_helpCardBody">
              Faces, edges, or points that stay aligned or at an angle.
            </span>
          </button>
        </div>

        <section id="cs_helpChoose" className="cs_helpSection">
          <h2 id="cs_helpChooseTitle" className="cs_helpSectionTitle">
            Which one to use
          </h2>
          <ul id="cs_helpChooseList" className="cs_helpList">
            {CHOICES.map((item) => (
              <li id={`cs_helpChoice_${item.id}`} key={item.id} className="cs_helpItem">
                <p id={`cs_helpChoiceTitle_${item.id}`} className="cs_helpItemTitle">
                  {item.title}
                </p>
                <p id={`cs_helpChoiceBody_${item.id}`} className="cs_helpItemBody">
                  {item.body}
                </p>
              </li>
            ))}
          </ul>
        </section>

        <section id="cs_helpTopic_sketches" className="cs_helpSection">
          <p id="cs_helpTopicKicker_sketches" className="cs_helpKicker">
            Sketches tab
          </p>
          <h2 id="cs_helpTopicTitle_sketches" className="cs_helpSectionTitle">
            Sketch constraints
          </h2>
          <p id="cs_helpTopicLead_sketches" className="cs_helpText">
            A sketch constraint relates geometry inside a single sketch. The sketch solver keeps those lines, points, arcs, and circles in the relationship you set. Dragging the sketch respects that relationship.
          </p>
          <p id="cs_helpTopicTypes_sketches" className="cs_helpText">
            {SKETCH_TYPES}
          </p>
          <p id="cs_helpTopicScope_sketches" className="cs_helpText">
            These never move a component in an assembly. A fully constrained sketch has no free geometry left to drag. Dimensions are edited in ProParams.
          </p>
          <p id="cs_helpTopicHere_sketches" className="cs_helpText">
            In this palette, select sketch geometry and apply a constraint that fits it. Click a constraint to select its geometry, or delete it when Fusion allows the delete.
          </p>
        </section>

        <section id="cs_helpTopic_constraints" className="cs_helpSection">
          <p id="cs_helpTopicKicker_constraints" className="cs_helpKicker">
            Assembly constraints tab · assembly and hybrid
          </p>
          <h2 id="cs_helpTopicTitle_constraints" className="cs_helpSectionTitle">
            Assembly constraints
          </h2>
          <p id="cs_helpTopicLead_constraints" className="cs_helpText">
            An assembly constraint is a geometric relationship from Assemble → Constrain Components. You describe how two faces, edges, or points relate. Fusion works out the motion from those relationships, so you do not pick a motion type.
          </p>
          <ul id="cs_helpRelationships" className="cs_helpList">
            <li id="cs_helpRel_mate" className="cs_helpItem">
              <p id="cs_helpRelTitle_mate" className="cs_helpItemTitle">
                Mate
              </p>
              <p id="cs_helpRelBody_mate" className="cs_helpItemBody">
                Two faces, edges, or points line up. The value is an offset, such as 0 mm for flush or 2 mm for a gap. Align creates mates.
              </p>
            </li>
            <li id="cs_helpRel_angle" className="cs_helpItem">
              <p id="cs_helpRelTitle_angle" className="cs_helpItemTitle">
                Angle
              </p>
              <p id="cs_helpRelBody_angle" className="cs_helpItemBody">
                Two pieces of geometry stay at an angle, such as 90 deg.
              </p>
            </li>
          </ul>
          <p id="cs_helpTopicStack_constraints" className="cs_helpText">
            One constraint can hold several relationships; the card shows a count when it does. A warning or error on the card is Fusion's health message for that constraint, and hovering it shows the message.
          </p>
          <p id="cs_helpTopicStore_constraints" className="cs_helpText">
            This is the same idea as a mate in SolidWorks or Inventor.
          </p>
          <p id="cs_helpTopicHere_constraints" className="cs_helpText">
            In this palette, hover a row to highlight the faces and edges that constraint uses in the canvas. The target button keeps the highlight on. Rename, show, hide, suppress, or delete the whole constraint. Select a face, edge, point, body, or component to list the constraints that use it. Create new ones in Fusion with Constrain Components.
          </p>
        </section>

        <section id="cs_helpLimits" className="cs_helpSection">
          <h2 id="cs_helpLimitsTitle" className="cs_helpSectionTitle">
            Left in Fusion
          </h2>
          <ul id="cs_helpLimitsList" className="cs_helpList">
            <li id="cs_helpLimit_dimensions" className="cs_helpItem">
              <p id="cs_helpLimitTitle_dimensions" className="cs_helpItemTitle">
                Sketch dimensions
              </p>
              <p id="cs_helpLimitBody_dimensions" className="cs_helpItemBody">
                Lengths and angles on sketch geometry stay in ProParams.
              </p>
            </li>
            <li id="cs_helpLimit_joints" className="cs_helpItem">
              <p id="cs_helpLimitTitle_joints" className="cs_helpItemTitle">
                Joints and as-built joints
              </p>
              <p id="cs_helpLimitBody_joints" className="cs_helpItemBody">
                Create and edit joints with Fusion's Joint and As-built Joint commands.
              </p>
            </li>
            <li id="cs_helpLimit_groups" className="cs_helpItem">
              <p id="cs_helpLimitTitle_groups" className="cs_helpItemTitle">
                Rigid groups, contact sets, and motion links
              </p>
              <p id="cs_helpLimitBody_groups" className="cs_helpItemBody">
                These assembly tools are unchanged by this add-in.
              </p>
            </li>
            <li id="cs_helpLimit_create" className="cs_helpItem">
              <p id="cs_helpLimitTitle_create" className="cs_helpItemTitle">
                New assembly constraints
              </p>
              <p id="cs_helpLimitBody_create" className="cs_helpItemBody">
                Fusion's add-in support for creating them is still a preview, so this tab edits constraints that already exist.
              </p>
            </li>
          </ul>
        </section>
      </div>
    </section>
  );
}
