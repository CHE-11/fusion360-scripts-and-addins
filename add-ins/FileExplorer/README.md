# File Explorer

File Explorer is a Fusion 360 add-in for browsing hub projects and files. It docks a palette on the right of the Design workspace so you can move through folders without relying on Fusion's data panel.

The palette shows the active hub, project, and folder. From a folder you can:

- Search this project with the Search button or Enter. The open folder is listed first, then the rest of the project
- Open a design or drawing, or switch to it if it is already open
- Insert a Fusion design into the open design as a linked component. It has to be in the same project, and it is placed at the origin of the component you are editing
- Rename a file or folder
- Create a folder
- Move a file to another folder in the same project
- Delete a file or an empty folder, with a warning when other designs use the file
- Show where a file is used, and which files it uses

Folders load one level at a time. Project search walks the project in small batches so Fusion stays responsive, and it stops after about 3000 files.

## Install

1. In Fusion, open **Utilities → Scripts and Add-Ins** (or press `Shift+S`).
2. On the **Add-Ins** tab, click the **+** next to **My Add-Ins**.
3. Select the `add-ins/FileExplorer/addin` folder.
4. Run **File Explorer**. It also starts with Fusion.

The command is on the Design workspace **Solid** tab in the **CHE** group, and on **Utilities → ADD-INS**. The palette docks on the right.

Set `REACT_DEV = True` in `addin/config.py` and run the Vite dev server when you want the palette to load `http://localhost:5176/` instead of the built page.

## Build

From `add-ins/FileExplorer/client`:

1. Build the React client (`client/`) for production.
2. Create/update the palette HTML folder at `addin/commands/explorer/resources/html/`.
3. Generate a single HTML (`index.html`) and JS bundle (`static/palette.js`) from the React build output.
4. Copy `index.html` to `addin/commands/explorer/resources/html/index.html`.
5. Create/update `addin/commands/explorer/resources/html/static/` and write `palette.js` there.
6. Create/update `addin/commands/explorer/resources/html/assets/`.
7. Copy assets from `client/src/assets/` into the palette `assets/` folder.

```powershell
pnpm build
```
