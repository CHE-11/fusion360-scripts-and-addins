# CONstrainer

CONstrainer is a Fusion 360 add-in that creates and manages sketch geometric constraints and assembly constraints.

The palette has three tabs:

- **Sketches** lists every sketch in the active design, grouped by component. Each sketch shows whether it is fully constrained and lists its geometric constraints. Select geometry in the canvas, click **Use selection**, and apply a constraint that fits that geometry. Click a constraint to select its geometry, or delete it when Fusion allows it.
- **Assembly constraints** is shown for assembly and hybrid designs. It lists the constraints made with **Assemble → Constrain Components** (Align, Angle, and so on). Rename, show or hide, suppress, or delete a constraint. Hover a constraint to highlight the faces and edges it uses in the canvas; the highlight goes away when the pointer leaves. The target button keeps that highlight on. Fusion does not let add-ins select an assembly constraint or its timeline entry, so the timeline is not highlighted. Offsets, angles, and flips are edited in Fusion. Select a face, edge, point, body, or component to list the constraints that use it. Fusion's add-in API for assembly constraints is still a preview, so new constraints are created in Fusion, not here.
- **Help** explains sketch constraints and assembly constraints, and when to use each one. It stays available in part designs.

Sketch dimensions stay in ProParams. Joints, rigid groups, and contact sets are not managed here.

## Install

1. In Fusion, open **Utilities → Scripts and Add-Ins** (or press `Shift+S`).
2. On the **Add-Ins** tab, click the **+** next to **My Add-Ins**.
3. Select the `add-ins/CONstrainer/addin` folder.
4. Run **CONstrainer**. It also starts with Fusion.

The command is on the Design workspace **Sketch** tab (while a sketch is open), the **Solid** tab, and **Utilities → ADD-INS**. The palette docks on the right.

Set `REACT_DEV = True` in `addin/config.py` and run the Vite dev server when you want the palette to load `http://localhost:5173/` instead of the built page.

## Build

From `add-ins/CONstrainer/client` (or the **CONstrainer - Build** task):

1. Build the React client (`client/`) for production.
2. Create/update the palette HTML folder at `addin/commands/constraints/resources/html/`.
3. Generate a single HTML (`index.html`) and JS bundle (`static/palette.js`) from the React build output.
4. Copy `index.html` to `addin/commands/constraints/resources/html/index.html`.
5. Create/update `addin/commands/constraints/resources/html/static/` and write `palette.js` there.
6. Create/update `addin/commands/constraints/resources/html/assets/`.
7. Copy assets from `client/src/assets/` into the palette `assets/` folder.
