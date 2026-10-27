# Fusion Scripts and Add-Ins

Scripts and add-ins for [Autodesk Fusion](https://www.autodesk.com/products/fusion-360/overview). Scripts run once from the Scripts and Add-Ins dialog. Add-ins stay loaded and start with Fusion. Palette add-ins open from the Design workspace **Solid** scripts and add-ins panel.

| Name | Kind | Folder |
| --- | --- | --- |
| [ProParams](#proparams) | Add-in | `add-ins/ProParams/addin` |
| [CONstrainer](#constrainer) | Add-in | `add-ins/CONstrainer/addin` |
| [File Explorer](#file-explorer) | Add-in | `add-ins/FileExplorer/addin` |
| [Script Runner](#script-runner) | Add-in | `add-ins/ScriptRunner/addin` |
| [Restart Add-Ins](#restart-add-ins) | Add-in | `add-ins/RestartAddIns/addin` |
| [Step File Body Combiner](#step-file-body-combiner) | Script | `scripts/Step-File-Body-Combiner` |
| [Renamer](#renamer) | Script | `scripts/Renamer` |

## Install

Fusion looks for the folder that contains the `.py` entry file and the `.manifest`.

**Scripts**

1. In Fusion, open **Utilities → Scripts and Add-Ins** (or press `Shift+S`).
2. On the **Scripts** tab, click the **+** next to **My Scripts**.
3. Select the script folder from the table above.
4. Select the script and click **Run**.

The script stays in that list. Run it again from the same dialog whenever you need it.

**Add-ins**

1. Open **Utilities → Scripts and Add-Ins** (or press `Shift+S`).
2. On the **Add-Ins** tab, click the **+** next to **My Add-Ins**.
3. Select the add-in folder from the table above (`addin`, not the parent project folder).
4. Select the add-in and click **Run**.

The add-ins are set to run on startup. Palette HTML is already built into ProParams, CONstrainer, and File Explorer, so there is no build step for normal use. Rebuild only when you change a React client. Script Runner and Restart Add-Ins are Python only. See [Developing the add-ins](#developing-the-add-ins).

Palette commands are on the Design workspace **Sketch** tab (while a sketch is open), the **Solid** tab **CHE** group, and **Utilities → ADD-INS**. ProParams and CONstrainer are on the Sketch tab. The Solid tab **CHE** group holds ProParams, CONstrainer, File Explorer, Script Runner, and Restart Add-Ins.

**How to add commands to Panels**

Each add-in creates its command once, then places that same command on toolbar panels. The **Utilities → ADD-INS** button comes from `PANEL_ID` (`SolidScriptsAddinsPanel`) in the Design workspace (`FusionSolidEnvironment`). Further panels are the `RIBBON_TABS` list in the add-in's `config.py`. Each entry is the tab id, the shared panel id, and the existing panel to insert after:

```python
RIBBON_TABS = (
    ('SketchTab', 'CHE_SketchPanel', 'SketchConstraintsPanel'),
    ('SolidTab', 'CHE_SolidPanel', 'SolidAssemblePanel'),
)
```

`commands/.../entry.py` reads that list on start, creates the **CHE** panel if it is missing, and pins the command on it. ProParams and CONstrainer share `CHE_SketchPanel` and `CHE_SolidPanel`. File Explorer, Script Runner, and Restart Add-Ins use `CHE_SolidPanel` only. On stop, an add-in removes its own control and deletes the panel only when nothing else is left on it. Add another tab by adding a tuple. `SketchTab` only appears while a sketch is open.

To list the tab and panel ids in your Fusion build, set the Text Commands window to **Py** and run:

```python
ws = adsk.core.Application.get().userInterface.workspaces.itemById('FusionSolidEnvironment')
for tab in ws.toolbarTabs:
    print(f'TAB {tab.id} | {tab.name}')
    for panel in tab.toolbarPanels:
        print(f'  PANEL {panel.id} | {panel.name}')
```

Stop and run the add-in again after changing `RIBBON_TABS`.


---

## ProParams

Edits Fusion parameters from a palette docked at the top of the Design workspace. The toolbar command is **ProParams Manager**.

- **Project** lists user parameters and driving model dimensions in the active design. Add, rename, edit, or delete them. Driven dimensions stay read-only. Each editable parameter can store alternate expressions. **Export variations** writes one file per combination as STEP, STL, or 3MF.
- **Global** keeps a shared parameter list in a JSON file and pushes it into the active design. The default file is `ProParams/ProParams_global.json` in your user home folder. Settings can point that store at another path, such as a shared drive.
- Parameters whose names match a global parameter are hidden on the Project tab so the shared value stays the one that gets pushed.

---

## CONstrainer

Creates and manages sketch geometric constraints, assembly joints, and assembly constraints from a palette docked on the right. Sketch dimensions stay in ProParams. Rigid groups and contact sets are not managed here.

The palette has four tabs: **Sketches**, **Joints**, **Assembly constraints**, and **Help**. Joints and assembly constraints appear for assembly and hybrid designs. Fusion’s add-in API for assembly constraints is still a preview, so new assembly constraints are created in Fusion, not in this palette.

Full tab behavior, the dev-server switch, and the build steps are in [`add-ins/CONstrainer/README.md`](add-ins/CONstrainer/README.md).

---

## File Explorer

Browses the active hub’s projects and files from a palette docked on the right. Open, rename, move, and delete files and folders, and search the current project.

The command is on the Design workspace **Solid** tab in the **CHE** group, and on **Utilities → ADD-INS**.

Install, search limits, and the build steps are in [`add-ins/FileExplorer/README.md`](add-ins/FileExplorer/README.md).

---

## Script Runner

Adds a **Scripts** button to the Design workspace **Solid** tab **CHE** group and to **Utilities → ADD-INS**. Click it, choose a saved script, and click **Run**. The list is your scripts folder and any script linked with **+**. Sample scripts and add-ins are left out. Choose **Refresh** after you create or link a script.

There is no palette and no client build. Install and behavior are in [`add-ins/ScriptRunner/README.md`](add-ins/ScriptRunner/README.md).

---

## Restart Add-Ins

Stops and starts every running user add-in from a **Restart Add-Ins** button on the Solid tab and the Scripts and Add-Ins panel. Fusion's built-in add-ins and samples stay as they are. Add-ins that are already stopped stay stopped. This add-in stays loaded, so the button is still there after the restart.

Use it after editing another add-in when Fusion should load that new code without a full restart.

**Folder:** `add-ins/RestartAddIns/addin`

---

## Step File Body Combiner

Copies every solid and surface body in the active design into the root component, then removes the original subcomponents. Bodies keep their positions, names, materials, and appearances, and they stay separate solids. They belong to one component, so they move together when the design is inserted into another assembly.

Use this after importing a STEP file when the imported assembly should behave as a single rigid part. Mesh bodies are left untouched: if the design contains any, the script stops before changing anything. Move the timeline marker to the end before running it in a parametric design.

**Folder:** `scripts/Step-File-Body-Combiner`

---

## Renamer

Renames the selected bodies and sketches to `base_1`, `base_2`, and so on, in selection order. The script asks for the base name when it runs. Components in the selection are skipped.

This is for sets of bodies that only need a short, ordered name, such as letter bodies in a 3D print that you select again in a slicer to change color.

**Folder:** `scripts/Renamer`

---

## Developing the add-ins

ProParams, CONstrainer, and File Explorer are a Fusion Python package in `addin/` plus a React, TypeScript, and Vite client in `client/`. The client build writes a single `index.html` and `static/palette.js` into the add-in’s palette HTML folder, which is what Fusion loads. Script Runner and Restart Add-Ins are Python only and have no client build.

From the client folder (`add-ins/ProParams/client` or `add-ins/CONstrainer/client`):

```bash
pnpm install
pnpm build
```

The same commands are VS Code tasks: **ProParams - Deps**, **ProParams - Build**, **CONstrainer - Deps**, and **CONstrainer - Build**.

CONstrainer can load the Vite dev server instead of the built page. Set `REACT_DEV = True` in `add-ins/CONstrainer/addin/config.py`, then run `pnpm start` in `add-ins/CONstrainer/client` (or the **CONstrainer - Start** task). The palette uses `http://localhost:5173/`. Set `REACT_DEV` back to `False` before you rely on the built page.
