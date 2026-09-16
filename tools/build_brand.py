#!/usr/bin/env python3
"""Build the integration's brand images from one drawing, and the README diagram in both themes.

Home Assistant serves `custom_components/<domain>/brand/icon.png`, `icon@2x.png`, `logo.png` and
`logo@2x.png` directly, so an integration can carry its own mark without waiting for the brands
repository. Everything here comes from the shapes below rather than from a binary someone has to
open in an editor, so a change is a diff.

    python tools/build_brand.py           # writes custom_components/lk_ihc/brand/ and docs/img/
    python tools/build_brand.py --check   # fails when the files on disk are out of date

Needs cairosvg to rasterise (`pip install cairosvg`); without it the SVGs are still written.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = ROOT / "custom_components" / "lk_ihc" / "brand"
DOCS_DIR = ROOT / "docs" / "img"

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

# The mark: a wall plate with two keys, the left one pressed, and the press leaving as a signal.
# It has to read at 48 pixels, so it is four shapes and nothing else.
BLUE = "#0b7ec4"
BLUE_DARK = "#075d92"
PLATE = "#f7fafc"
KEY = "#d9e3ea"
KEY_PRESSED = "#ffc65c"
SIGNAL = "#ffffff"


def mark(size: int, *, background: bool = True) -> str:
    """Return the icon as SVG at the given size. The drawing is laid out on a 512 grid."""
    bg = (
        f'<rect width="512" height="512" rx="112" fill="{BLUE}"/>'
        f'<rect y="256" width="512" height="256" rx="112" fill="{BLUE_DARK}" opacity="0.25"/>'
        if background
        else ""
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 512 512">
  {bg}
  <rect x="96" y="96" width="272" height="320" rx="40" fill="{PLATE}"/>
  <rect x="130" y="132" width="204" height="118" rx="20" fill="{KEY_PRESSED}"/>
  <rect x="130" y="262" width="204" height="118" rx="20" fill="{KEY}"/>
  <path d="M166 191 h60" stroke="{BLUE_DARK}" stroke-width="22" stroke-linecap="round" opacity="0.5"/>
  <path d="M238 321 h60" stroke="{BLUE}" stroke-width="22" stroke-linecap="round" opacity="0.3"/>
  <g fill="none" stroke="{SIGNAL}" stroke-width="20" stroke-linecap="round" opacity="0.95">
    <path d="M392 156 a64 64 0 0 1 0 92"/>
    <path d="M428 124 a112 112 0 0 1 0 156"/>
  </g>
</svg>
"""


def logo(width: int) -> str:
    """Return the wordmark: the icon next to the name, for places that show a wide logo."""
    height = round(width * 512 / 1400)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 1400 512">
  <rect width="1400" height="512" fill="none"/>
  <g>{mark(512).split(">", 1)[1].rsplit("</svg>", 1)[0]}</g>
  <text x="560" y="300" font-family="{FONT}" font-size="150" font-weight="700" fill="{BLUE}">LK IHC</text>
  <text x="562" y="372" font-family="{FONT}" font-size="66" font-weight="500" fill="#5b6b78">for Home Assistant</text>
</svg>
"""


@dataclass(frozen=True)
class Palette:
    """Colors for one theme of the diagram."""

    name: str
    bg: str
    card: str
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str
    chip: str
    chip_text: str
    line: str


LIGHT = Palette(
    "light",
    "#ffffff",
    "#f6f8fa",
    "#d0d7de",
    "#1f2328",
    "#59636e",
    "#0b7ec4",
    "#ffffff",
    "#ddf4ff",
    "#0a3069",
    "#8c959f",
)
DARK = Palette(
    "dark", "#0d1117", "#161b22", "#30363d", "#e6edf3", "#9198a1", "#4bb3ee", "#0d1117", "#122b3d", "#7cc4ff", "#6e7681"
)


def diagram(p: Palette) -> str:
    """Return the README diagram: what the integration makes out of one IHC installation."""
    w, h = 1000, 470
    parts: list[str] = []

    def text(x, y, value, *, size=13, color=None, weight="400", anchor="start"):
        parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color or p.text}" text-anchor="{anchor}">{value}</text>'
        )

    def box(x, y, bw, bh, *, fill=None, stroke=None, dash=None, radius=12):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="{radius}" fill="{fill or p.card}" '
            f'stroke="{stroke or p.border}" stroke-width="1.5"{dash_attr}/>'
        )

    def chip(x, y, label):
        cw = 14 + 7.1 * len(label)
        parts.append(f'<rect x="{x}" y="{y}" width="{cw:.0f}" height="26" rx="13" fill="{p.chip}"/>')
        text(x + cw / 2, y + 17.5, label, size=12, color=p.chip_text, weight="600", anchor="middle")
        return cw

    def arrow(path, *, color=None, dash=None):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<path d="{path}" fill="none" stroke="{color or p.line}" stroke-width="2" '
            f'stroke-linecap="round" marker-end="url(#a-{p.name})"{dash_attr}/>'
        )

    text(40, 46, "One controller, read once, turned into devices you can use", size=21, weight="700")
    subtitle = (
        "The project file already knows what every product is and where it sits. Nothing has to be listed by hand."
    )
    text(40, 70, subtitle, size=13, color=p.muted)

    # The controller
    box(40, 104, 232, 150)
    text(62, 136, "IHC controller", size=15, weight="600")
    for i, line in enumerate(["Signed in from the", "user interface.", "Sends its project", "and every change."]):
        text(62, 162 + i * 19, line, size=12.5, color=p.muted)

    # The project
    box(320, 104, 232, 150)
    text(342, 136, "The project", size=15, weight="600")
    for i, line in enumerate(["Groups become areas.", "Products become devices.", "Resources become", "entities."]):
        text(342, 162 + i * 19, line, size=12.5, color=p.muted)
    arrow("M278 179 L314 179")

    # What comes out
    box(600, 104, 360, 300)
    text(622, 136, "In Home Assistant", size=15, weight="600")
    rows = [
        ("Lights", "lamp outlets and dimmers"),
        ("Switches", "relays and plug outlets"),
        ("Binary sensors", "movement, door, smoke, water"),
        ("Sensors", "temperature"),
        ("Events", "every key on every wall switch"),
    ]
    y = 166
    for label, detail in rows:
        cw = chip(622, y - 14, label)
        text(622 + cw + 12, y + 4, detail, size=12.5, color=p.muted)
        y += 44
    arrow("M558 179 L594 179")

    # The point: a key press becomes a trigger
    box(40, 300, 512, 104, dash="6 5", stroke=p.accent)
    text(62, 332, "The part that was missing", size=14, weight="600", color=p.accent)
    text(62, 356, "A key press fires an event entity, so any key in the house can start an", size=12.5, color=p.muted)
    text(
        62, 375, "automation. The key keeps doing what the installation already uses it for.", size=12.5, color=p.muted
    )
    # Straight at the Events row, which is the row it is talking about.
    arrow("M556 346 L594 346", color=p.accent, dash="5 4")

    text(
        40,
        440,
        "Read-only until you say otherwise: everything is shown, nothing is switched.",
        size=12.5,
        color=p.muted,
    )

    marker = (
        f'<marker id="a-{p.name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
        f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{p.line}"/></marker>'
    )
    body = "\n  ".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">\n'
        f"  <defs>{marker}</defs>\n"
        f'  <rect width="{w}" height="{h}" fill="{p.bg}"/>\n  {body}\n</svg>\n'
    )


def build() -> dict[Path, str]:
    """Return every generated file and its SVG content."""
    return {
        BRAND_DIR / "icon.svg": mark(512),
        BRAND_DIR / "logo.svg": logo(1400),
        DOCS_DIR / "overview-light.svg": diagram(LIGHT),
        DOCS_DIR / "overview-dark.svg": diagram(DARK),
    }


def rasterise() -> list[str]:
    """Write the PNG sizes Home Assistant serves. Returns what was written."""
    try:
        import cairosvg
    except ImportError:
        print("cairosvg is not installed, so only the SVG files were written")
        return []
    written = []
    for name, source, size in (
        ("icon.png", mark(256), 256),
        ("icon@2x.png", mark(512), 512),
        ("logo.png", logo(700), None),
        ("logo@2x.png", logo(1400), None),
    ):
        target = BRAND_DIR / name
        options = {"output_width": size} if size else {}
        cairosvg.svg2png(bytestring=source.encode(), write_to=str(target), **options)
        written.append(name)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only report whether the SVG files are up to date")
    args = parser.parse_args()

    files = build()
    if args.check:
        stale = [path for path, content in files.items() if not path.exists() or path.read_text() != content]
        for path in stale:
            print(f"out of date: {path.relative_to(ROOT)}")
        return 1 if stale else 0

    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in files.items():
        path.write_text(content)
        print(f"wrote {path.relative_to(ROOT)}")
    for name in rasterise():
        print(f"wrote {(BRAND_DIR / name).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
