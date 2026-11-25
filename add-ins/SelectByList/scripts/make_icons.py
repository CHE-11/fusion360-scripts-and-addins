"""Draw the Select By List toolbar icons.

Writes every size Fusion looks for (16, 32, 64 and their @2x) in the plain,
-normal, -dark_blue and -light_gray variants, plus the add-in manager icon.
Run with: python scripts/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / 'addin' / 'commands' / 'selectByList' / 'resources'
ADDIN_ICON = ROOT / 'addin' / 'AddInIcon.png'

# Drawn on a 64-unit grid, supersampled, then reduced.
GRID = 64
SUPERSAMPLE = 8

ACCENT = (139, 92, 246, 255)
CHECK = (255, 255, 255, 255)
CURSOR_FILL = (255, 255, 255, 255)
CURSOR_LINE = (24, 26, 32, 255)

# Fusion swaps these in by UI theme. Dark themes want light strokes.
THEMES = {
    '': (88, 94, 106, 255),
    '-normal': (88, 94, 106, 255),
    '-light_gray': (52, 56, 64, 255),
    '-dark_blue': (214, 220, 230, 255),
}

SIZES = {
    '16x16': 16,
    '16x16@2x': 32,
    '32x32': 32,
    '32x32@2x': 64,
    '64x64': 64,
    '64x64@2x': 128,
}


def draw_icon(px: int, ink: tuple[int, int, int, int]) -> Image.Image:
    scale = px * SUPERSAMPLE / GRID
    canvas = px * SUPERSAMPLE
    img = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def s(v: float) -> float:
        return v * scale

    def box(x0, y0, x1, y1):
        return [s(x0), s(y0), s(x1), s(y1)]

    stroke = max(1, round(s(4.5)))
    rows = (8, 26, 44)
    for index, top in enumerate(rows):
        square = box(4, top, 16, top + 12)
        if index == 1:
            d.rounded_rectangle(square, radius=s(3), fill=ACCENT)
            d.line(
                [(s(6.8), s(top + 6.4)), (s(9.4), s(top + 9)), (s(13.6), s(top + 3.6))],
                fill=CHECK,
                width=max(1, round(s(2.6))),
                joint='curve',
            )
        else:
            d.rounded_rectangle(square, radius=s(3), outline=ink, width=max(1, round(s(2.6))))
        line_end = 35 if index == 2 else 58
        bar = box(22, top + 6 - 2.25, line_end, top + 6 + 2.25)
        d.rounded_rectangle(bar, radius=stroke / 2, fill=ACCENT if index == 1 else ink)

    cursor = [(40, 34), (40, 62), (46.5, 55.5), (51, 63.5), (55.5, 61.3), (51, 53.5), (60, 53.5)]
    d.polygon([(s(x), s(y)) for x, y in cursor], fill=CURSOR_FILL, outline=CURSOR_LINE, width=max(1, round(s(2.4))))

    return img.resize((px, px), Image.LANCZOS)


def main() -> None:
    RESOURCES.mkdir(parents=True, exist_ok=True)
    for name, px in SIZES.items():
        for suffix, ink in THEMES.items():
            out = RESOURCES / f'{name}{suffix}.png'
            draw_icon(px, ink).save(out)
            print(f'Wrote {out.relative_to(ROOT)}')
    draw_icon(64, THEMES['']).save(ADDIN_ICON)
    print(f'Wrote {ADDIN_ICON.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
