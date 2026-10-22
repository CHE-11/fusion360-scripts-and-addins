# Fusion Scripts and Add-Ins

Scripts and add-ins for [Autodesk Fusion](https://www.autodesk.com/products/fusion-360/overview). Scripts run once from the Scripts and Add-Ins dialog. Add-ins stay loaded, start with Fusion, and open a palette from the Design workspace **Solid** scripts and add-ins panel.

| Name | Kind | Folder |
| --- | --- | --- |
| [ProParams](#proparams) | Add-in | `add-ins/ProParams/addin` |
| [CONstrainer](#constrainer) | Add-in | `add-ins/CONstrainer/addin` |
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

Both add-ins are set to run on startup. The palette HTML is already built into each add-in, so there is no build step for normal use. Rebuild only when you change the React client. See [Developing the add-ins](#developing-the-add-ins).

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

Each add-in is a Fusion Python package in `addin/` plus a React, TypeScript, and Vite client in `client/`. The client build writes a single `index.html` and `static/palette.js` into the add-in’s palette HTML folder, which is what Fusion loads.

From the client folder (`add-ins/ProParams/client` or `add-ins/CONstrainer/client`):

```bash
pnpm install
pnpm build
```

The same commands are VS Code tasks: **ProParams - Deps**, **ProParams - Build**, **CONstrainer - Deps**, and **CONstrainer - Build**.

CONstrainer can load the Vite dev server instead of the built page. Set `REACT_DEV = True` in `add-ins/CONstrainer/addin/config.py`, then run `pnpm start` in `add-ins/CONstrainer/client` (or the **CONstrainer - Start** task). The palette uses `http://localhost:5173/`. Set `REACT_DEV` back to `False` before you rely on the built page.
