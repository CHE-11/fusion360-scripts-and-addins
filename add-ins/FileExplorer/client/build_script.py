
"""
Build post-process step for Fusion 360 palette hosting.

What this script does (matches README intent):
- Generates a single `index.html` and `static/palette.js` for the Fusion palette.
- Copies them into the add-in folder:
    `/addin/commands/explorer/resources/html/`
- Copies (non-destructively) any assets from `client/src/assets/` into:
    `/addin/commands/explorer/resources/html/assets/`
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_ROOT = Path(__file__).resolve().parent
CLIENT_BUILD_DIR = CLIENT_ROOT / "build"
CLIENT_DIST_DIR = CLIENT_ROOT / "dist"

TARGET_HTML_DIR = (
  REPO_ROOT / "addin" / "commands" / "explorer" / "resources" / "html"
)
TARGET_STATIC_DIR = TARGET_HTML_DIR / "static"
TARGET_ASSETS_DIR = TARGET_HTML_DIR / "assets"

SOURCE_ASSETS_DIR = CLIENT_ROOT / "src" / "assets"


def _strip_web_path(p: str) -> str:
    # CRA manifest paths can be like "/static/js/main.hash.js" or "static/js/..."
    return p.lstrip("/").lstrip("./")


def _copy_tree_non_destructive(src: Path, dst: Path) -> None:
    """
    Copy contents of src into dst, overwriting same-named files, but not deleting
    existing dst files that don't exist in src.
    """
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _copy_tree_non_destructive(item, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def build_palette_bundle() -> tuple[Path, Path]:
    css_text = ""

    # Prefer Vite (dist/manifest.json). Fallback to CRA (build/asset-manifest.json).
    vite_manifest_path = CLIENT_DIST_DIR / "manifest.json"
    vite_manifest_path_alt = CLIENT_DIST_DIR / ".vite" / "manifest.json"
    cra_manifest_path = CLIENT_BUILD_DIR / "asset-manifest.json"

    main_js_path: Path | None = None

    def _looks_like_vite_manifest(m: object) -> bool:
        if not isinstance(m, dict):
            return False
        v = m.get("index.html")
        return isinstance(v, dict) and isinstance(v.get("file"), str)

    if vite_manifest_path.exists() or vite_manifest_path_alt.exists():
        # Vite writes build manifest to dist/.vite/manifest.json by default.
        # Some projects also have dist/manifest.json (web app manifest) which is NOT the Vite build manifest.
        manifest_path = (
            vite_manifest_path_alt
            if vite_manifest_path_alt.exists()
            else vite_manifest_path
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not _looks_like_vite_manifest(manifest) and vite_manifest_path_alt.exists() and manifest_path != vite_manifest_path_alt:
            # Fallback just in case: prefer the .vite manifest if root "manifest.json" wasn't the build manifest.
            manifest_path = vite_manifest_path_alt
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not _looks_like_vite_manifest(manifest):
            raise KeyError(f"Vite build manifest not found at: {vite_manifest_path_alt}")
        # Vite manifest is a dict of entry ids -> { file, css?, isEntry? ... }
        entry = None
        for k, v in manifest.items():
            # Vite commonly uses "index.html" as the entry key.
            # Some toolchains can serialize booleans oddly, so avoid `is True`.
            if isinstance(v, dict) and (v.get("isEntry") or k == "index.html"):
                entry = v
                break
        if not entry:
            raise KeyError("Vite manifest.json missing an entry with isEntry=true")

        main_js_rel = entry.get("file")
        if not main_js_rel:
            raise KeyError("Vite manifest entry missing 'file'")
        main_js_path = CLIENT_DIST_DIR / _strip_web_path(main_js_rel)
        if not main_js_path.exists():
            raise FileNotFoundError(f"Missing Vite entry JS at: {main_js_path}")

        css_files = entry.get("css") or []
        if isinstance(css_files, list) and css_files:
            css_text = "\n".join(
                (CLIENT_DIST_DIR / _strip_web_path(css_rel)).read_text(encoding="utf-8")
                for css_rel in css_files
                if (CLIENT_DIST_DIR / _strip_web_path(css_rel)).exists()
            )
        else:
            # If cssCodeSplit=false, Vite may put CSS in a separate manifest entry (e.g. "style.css").
            extra_css = []
            for _k, v in manifest.items():
                if isinstance(v, dict):
                    f = v.get("file")
                    if isinstance(f, str) and f.endswith(".css"):
                        p = CLIENT_DIST_DIR / _strip_web_path(f)
                        if p.exists():
                            extra_css.append(p.read_text(encoding="utf-8"))
            css_text = "\n".join(extra_css)
    elif cra_manifest_path.exists():
        manifest = json.loads(cra_manifest_path.read_text(encoding="utf-8"))
        files: dict[str, str] = manifest.get("files", {})
        main_js_rel = files.get("main.js")
        if not main_js_rel:
            raise KeyError("asset-manifest.json missing files['main.js']")

        main_css_rel = files.get("main.css")

        main_js_path = CLIENT_BUILD_DIR / _strip_web_path(main_js_rel)
        if not main_js_path.exists():
            raise FileNotFoundError(f"Missing CRA main.js at: {main_js_path}")

        if main_css_rel:
            main_css_path = CLIENT_BUILD_DIR / _strip_web_path(main_css_rel)
            if main_css_path.exists():
                css_text = main_css_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(
            f"Missing build outputs. Expected either:\n- {vite_manifest_path}\n- {vite_manifest_path_alt}\n- {cra_manifest_path}"
        )

    # Ensure target folders exist
    # See if html folder exists, if it does, delete it
    if TARGET_HTML_DIR.exists():
      shutil.rmtree(TARGET_HTML_DIR)
      
    TARGET_STATIC_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) palette.js
    palette_js_out = TARGET_STATIC_DIR / "palette.js"
    if not main_js_path:
        raise RuntimeError("Failed to resolve main JS path")
    shutil.copy2(main_js_path, palette_js_out)

    # 2) index.html (single script, CSS inlined)
    index_html_out = TARGET_HTML_DIR / "index.html"
    index_html_out.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8" />',
                '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
                "  <title>File Explorer</title>",
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

    # 3) Copy client/src/assets -> palette assets (non-destructive)
    _copy_tree_non_destructive(SOURCE_ASSETS_DIR, TARGET_ASSETS_DIR)

    return index_html_out, palette_js_out


if __name__ == "__main__":
    index_html_out, palette_js_out = build_palette_bundle()
    print(f"Wrote: {index_html_out}")
    print(f"Wrote: {palette_js_out}")
