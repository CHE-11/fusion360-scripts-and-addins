# Select By List

Select By List is a Fusion add-in that finds, sorts, selects, and operates on components, bodies, and faces by name. It docks a palette on the right of the Design workspace, so you can work from a searchable list instead of hunting through the viewport or browser.

The Fusion browser can't sort components alphabetically. This palette sorts the whole design A-Z, and one click switches back to Fusion's browser order.

## What the palette does

**Selection and search**

- Lists every component, body, or face in the active design. Type in the filter box to narrow the list by name or by parent path.
- **A-Z** sorts naturally, so `Component10` comes after `Component9`. **Browser** keeps Fusion's order and indents nested components.
- The filter buttons are **Component**, **Body**, **Assembly** (components that contain other components), and **Faces**.
- Names are colour coded like Fusion's browser: purple for components, blue for bodies, orange for assemblies, and pink for faces. Each row shows the item's appearance colour and its size in the design's length units.
- Click a row to check it. Shift-click checks a range. **All**, **None**, and **Invert** act on the rows currently listed.
- **Select in Viewport** sends the checked items to Fusion's selection, ready for any Fusion command. Double-clicking a row selects just that item.
- Items selected in the viewport are underlined in the list. The status bar shows how many items are selected.

**Operations**

- **Move**, **Mirror**, **Circ Pat** (Circular Pattern), and **Rect Pat** (Rectangular Pattern) open Fusion's own command with the checked items preselected. Move preselects only the components or bodies, so Fusion centres the gizmo on them.
- **Repeat Last** runs the last operation again on the same items.
- Mirror and the patterns need all components or all bodies. Don't mix the two in one operation. Faces can't be used for operations.

**Visibility**

- **Show** and **Hide** turn the checked items on or off. Show also turns on any hidden parent components, so the item really appears.
- **Isolate** hides everything except the checked items and the components that contain them.
- **All** puts visibility back the way it was before the first Isolate. Without an Isolate, it turns every component and body back on.

**Rename**

- Check one component or body and press **Rename**. Renaming a component renames its definition, so every copy of it updates. That is normal Fusion behaviour. Linked components have to be renamed in their own design.

**Faces**

- Check bodies or components and press **Faces** to list their individual faces, with surface type and area. **Back** returns to the previous list. The **Faces** filter button does the same, and lists the faces of every visible body when nothing is checked.
- Select faces in the viewport to apply appearances, split faces, or run other face operations. The list stops at 2000 faces.

**Other**

- The list refreshes on its own when a design opens or becomes active, and after model-changing commands finish. If no design is open, the palette says so and checks again every 2 seconds.
- The palette follows Fusion's light and dark themes. The toolbar icon has light and dark variants too.
- Keyboard shortcuts: `Ctrl+F` focuses the filter, `Ctrl+A` checks everything listed, and `Esc` clears the checks (or clears the filter while typing in it).

## Install

1. In Fusion, open **Utilities → Scripts and Add-Ins** (or press `Shift+S`).
2. On the **Add-Ins** tab, click the **+** next to **My Add-Ins**.
3. Select the `add-ins/SelectByList/addin` folder.
4. Run **SelectByList**. It also starts with Fusion.

The **Select By List** command is on the Design workspace **Solid** tab in the **CHE** group, and on **Utilities → ADD-INS**. The palette docks on the right.

## Develop

From `add-ins/SelectByList/client`:

```powershell
pnpm install
pnpm build
```

`pnpm build` runs the Vite build, then `build_script.py` writes `index.html` and `static/palette.js` into `addin/commands/selectByList/resources/html/`.

`pnpm dev` serves the palette on `http://localhost:5178/` with a mock design, so the UI works in a normal browser. To load the dev server inside Fusion, set `REACT_DEV = True` in `addin/config.py`, then set it back to `False` before you rely on the built page.

The toolbar icons are drawn by `scripts/make_icons.py` (needs Pillow). Run `python scripts/make_icons.py` from `add-ins/SelectByList` to regenerate every size and theme variant, plus `addin/AddInIcon.png`.

## Known limits

- Fusion places the Move gizmo itself. It usually centres on the preselected items, but not always. The items stay selected either way.
- Listing faces is slow on bodies with very many faces.
- Components that share a definition all show a rename.
