"""
Build post-process step for Fusion palette hosting.

- Reads the Vite build manifest in `dist/.vite/manifest.json`.
- Writes a single `index.html` (CSS inlined) and `static/palette.js` into
    `/addin/commands/selectByList/resources/html/`
- Copies any assets from `client/src/assets/` into `resources/html/assets/`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_ROOT = Path(__file__).resolve().parent
CLIENT_DIST_DIR = CLIENT_ROOT / "dist"
VITE_MANIFEST = CLIENT_DIST_DIR / ".vite" / "manifest.json"

TARGET_HTML_DIR = REPO_ROOT / "addin" / "commands" / "selectByList" / "resources" / "html"
TARGET_STATIC_DIR = TARGET_HTML_DIR / "static"
TARGET_ASSETS_DIR = TARGET_HTML_DIR / "assets"

SOURCE_ASSETS_DIR = CLIENT_ROOT / "src" / "assets"


def _strip_web_path(p: str) -> str:
    return p.lstrip("/").lstrip("./")


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _copy_tree(item, target)
        else:
            shutil.copy2(item, target)


def build_palette_bundle() -> tuple[Path, Path]:
    if not VITE_MANIFEST.exists():
        raise FileNotFoundError(f"Vite build manifest not found at: {VITE_MANIFEST}")
    manifest = json.loads(VITE_MANIFEST.read_text(encoding="utf-8"))

    entry = None
    for key, value in manifest.items():
        if isinstance(value, dict) and (value.get("isEntry") or key == "index.html"):
            entry = value
            break
    if not entry or not entry.get("file"):
        raise KeyError("Vite manifest is missing its entry chunk")

    main_js_path = CLIENT_DIST_DIR / _strip_web_path(entry["file"])
    if not main_js_path.exists():
        raise FileNotFoundError(f"Missing Vite entry JS at: {main_js_path}")

    css_paths = [CLIENT_DIST_DIR / _strip_web_path(rel) for rel in entry.get("css") or []]
    if not css_paths:
        # With cssCodeSplit=false, Vite puts the stylesheet in its own manifest entry.
        for value in manifest.values():
            file = value.get("file") if isinstance(value, dict) else None
            if isinstance(file, str) and file.endswith(".css"):
                css_paths.append(CLIENT_DIST_DIR / _strip_web_path(file))
    css_text = "\n".join(p.read_text(encoding="utf-8") for p in css_paths if p.exists())

    if TARGET_HTML_DIR.exists():
        shutil.rmtree(TARGET_HTML_DIR)
    TARGET_STATIC_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    palette_js_out = TARGET_STATIC_DIR / "palette.js"
    shutil.copy2(main_js_path, palette_js_out)

    index_html_out = TARGET_HTML_DIR / "index.html"
    index_html_out.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8" />',
                '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
                "  <title>Select By List</title>",
                f"  <style>{css_text}</style>" if css_text else "",
                "</head>",
                "<body>",
                '  <div id="root"></div>',
                '  <script src="static/palette.js"></script>',
                "</body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )

    _copy_tree(SOURCE_ASSETS_DIR, TARGET_ASSETS_DIR)
    return index_html_out, palette_js_out


if __name__ == "__main__":
    index_html_out, palette_js_out = build_palette_bundle()
    print(f"Wrote: {index_html_out}")
    print(f"Wrote: {palette_js_out}")
