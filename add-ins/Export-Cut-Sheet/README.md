# Export Cut Sheet

Export Cut Sheet adds an **Export Cut Sheet** button to the CHE panel on the Design workspace **Solid** tab. It exports the bodies in the current design in two forms:

- **CSV**: one row per body with `Body Name, Length, Width, Thickness, Units, Note`. Rectangular bodies have an empty note. Complex bodies list their overall outline size and the note `Complex Shape - see PDF drawing`, or `Complex Shape - see design file` when no PDF page was made for them. Open it in Excel or feed it to a panel optimizer.
- **PDF**: a model overview on the first page, then one page per part with a dimensioned three-view drawing (top, front, right in third-angle projection) and a title block. Rectangular and complex parts are both included.

## Install

1. In Fusion, open **Utilities → Scripts and Add-Ins** (or press `Shift+S`).
2. On the **Add-Ins** tab, click the **+** next to **My Add-Ins**.
3. Select the `add-ins/Export-Cut-Sheet/addin` folder.
4. Run **ExportCutSheet**. It also starts with Fusion.

## Use

Click **Export Cut Sheet** and pick:

- **Bodies**: *All visible bodies* (every visible solid body in the root and in every visible occurrence) or *Selected bodies*.
- **Units** and **Decimal places**: default to the design's length units.
- **Use fractions** and **Fraction precision** (inches and feet only): write lengths as fractions rounded to 1/2 through 1/64, for example `12 3/8`. Feet are written as feet and inches, for example `3' 4 1/2"`. This applies to both the CSV and the PDF. In the CSV, values under one inch are written as `0 3/4` so Excel reads them as numbers instead of dates. Excel displays them as `3/4`.
- **CSV** and **PDF**: choose either or both. The PDF includes every exported body.
- **Page size**: Letter, Tabloid, A4, or A3, landscape.

Click **OK**, then choose an output folder. The folder dialog opens in your Downloads folder. The files are named `<Document>_cut_sheet.csv` and `<Document>_drawings.pdf`. A summary lists what was written and any bodies that could not be measured or drawn.

## How parts are measured

Each body is measured in its own minimum oriented bounding box. Parts rotated in the model still report their true length, width, and thickness. Dimensions are always sorted so Length ≥ Width ≥ Thickness.

A body counts as a rectangle when it has exactly six planar faces whose normals form three perpendicular pairs, and its volume matches its bounding box. Everything else, such as notches, holes, chamfers, or curves, is noted as a complex shape in the CSV. Both kinds of body are drawn in the PDF.

Each placement of a component is a separate CSV row. In the PDF, repeated instances of the same body are drawn once, with the count in the **QTY** cell.

## Drawings

The first page shows every visible body in the design as one model, even when only selected bodies are exported. It has four views at one scale: **Home** and **Top** above **Front** and **Right**. The views follow the design's ViewCube, including a custom Home or Front view. The front and right views carry the overall width, depth, and height, and the title block lists the body count.

Each part page after that:

- Views are projected from the body's own frame. The top view looks down the thickness, which is the flat profile for sheet parts.
- Each view gets overall horizontal and vertical dimensions.
- Feature dimensions run as a chain inside the overall dimensions. They mark where notches, steps, and angled edges start and end, and where hole centers sit, along the length, width, and thickness. Each chain is drawn once, on the top view for length and width and on the front view for thickness. Positions closer together than about 10 points on paper are merged so the chain stays readable.
- Straight edges that are not horizontal or vertical get an angle dimension, measured from the nearest horizontal or vertical reference, for example `15.3°`.
- Circular edges seen face-on get center marks and a diameter callout. Equal diameters are grouped, for example `4X Ø 0.250`. Holes that Fusion stores as two half arcs are recognized as full circles.
- Fillets and rounded ends seen face-on get a radius callout, grouped the same way, for example `2X R 0.500`.
- The scale snaps to a standard ratio (such as 1:2 or 1:10) and is printed in the title block.
- The views are wireframe projections. Hidden edges are drawn as solid lines, not dashed.

The PDF is written by the add-in itself, because Fusion's API cannot create drawing views. Nothing extra needs installing.

## Tests

The pure-Python parts (classification math, CSV rows, layout, scale, and PDF structure) have tests that run without Fusion:

```
python -m unittest discover -s add-ins/Export-Cut-Sheet/tests
```
