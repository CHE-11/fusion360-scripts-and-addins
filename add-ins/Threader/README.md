# Threader

Threader is a Fusion 360 add-in that models threads and heat-set insert pockets for 3D printing. Clearance is part of the solid. After a test print, **Too tight** or **Too loose** updates that fit without remodeling the part by hand.

Based on ThreadFor3DPrinter by HookyMaster: https://github.com/HookyMaster/ThreadFor3DPrinter

The palette has three tabs:

- **Thread** reads the cylindrical face you select. Choose male or female, and outset (add material) or inset (cut material). Printable trapezoids are for plastic-on-plastic parts. ISO metric coarse (M1 through M24) and imperial UNC and UNF are for mating with metal fasteners.
- **Heat-set** cuts a pocket for a short knurled brass insert, M2 through M6, or a custom diameter and depth.
- **Adjust** lists every thread and pocket in the design. **Too tight** loosens the fit. **Too loose** tightens it.

## Fit

Plastic-on-plastic threads start at **0.20 mm** radial clearance, a 45° flank measured from the axis, and a pitch snapped to the layer height. The crest stays at least as wide as the nozzle.

Metal fasteners start at **0.15 mm** radial clearance. The pitch stays on the ISO, UNC, or UNF value so it still matches the screw. Crests finer than the nozzle are called out before you create the thread.

A nudge is **0.05 mm** radial on a thread and **0.10 mm** on an insert hole diameter. Loosening a male thread makes it smaller. Loosening a female thread makes it larger. Each feature keeps its own parameters (`t1_clear`, `i1_dia`, and so on). `thread_nozzle` and `thread_layer` are shared for the design.

Print threads with the axis vertical. Modeled threads smaller than M5 or #10 are a poor fit for a 0.4 mm nozzle. Use a heat-set insert or tap those.

Outset and inset use the selected face differently:

- Male outset: the face is the root, and teeth are added outside it.
- Male inset: the face is the major diameter, and grooves are cut into it.
- Female outset: the face is the major diameter of the hole, and teeth are added inside it.
- Female inset: the face is the minor diameter, and grooves are cut into the wall.

## Install

1. In Fusion, open **Utilities → Scripts and Add-Ins** (or press `Shift+S`).
2. On the **Add-Ins** tab, click the **+** next to **My Add-Ins**.
3. Select the `add-ins/Threader/addin` folder.
4. Run **Threader**. It also starts with Fusion.

The command is on the Design workspace **Solid** tab, in the **CHE** panel, and under **Utilities → ADD-INS**. The palette docks on the right.

The design has to be in **Parametric Modeling**. Direct modeling cannot keep the fit parameters.

Set `REACT_DEV = True` in `addin/config.py` and run the Vite dev server when you want the palette to load `http://localhost:5174/` instead of the built page.

## Build

From `add-ins/Threader/client` (or the **Threader - Build** task):

```powershell
pnpm install
pnpm build
```

That writes the palette to `addin/commands/threader/resources/html/` (`index.html` and `static/palette.js`).

`python -m unittest tests.test_profile` from `add-ins/Threader` checks the section math without opening Fusion.
