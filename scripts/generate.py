#!/usr/bin/env python3
"""
Generates the header/stack SVGs (dark + light), README.md and the stats workflow.

Usage (from the repo root):
    python3 scripts/generate.py --avatar avatar.png                # Night Owl colors
    python3 scripts/generate.py --avatar avatar.png --auto-color   # colors from the avatar
    python3 scripts/generate.py --avatar avatar.png --hue 170      # generated palette, hue 0-360

Content lives in CONFIG, colors in THEMES. Standard library only.
The stats cards are rendered daily by .github/workflows/stats.yml (also generated here).
"""
from __future__ import annotations

import argparse
import base64
import colorsys
import math
import mimetypes
from html import escape
from pathlib import Path

from icons import ICONS

# ─────────────────────────────────────────────────────────────────────────────
# COLORS: Material-You-style tonal schemes, all derived from ONE hue (0-360).
# Every surface is tinted with it, so the whole profile carries the color.
# ─────────────────────────────────────────────────────────────────────────────
SEED_HUE = 250        # only used with --hue / --auto-color instead of Night Owl
TERTIARY_SHIFT = 60   # hue offset for the second accent


def _c(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l, s)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def scheme(h: float) -> dict:
    t = h + TERTIARY_SHIFT
    return {
        "dark": {
            "card": _c(h, .28, .12), "surface": _c(h, .32, .20), "surface_hi": _c(h, .30, .26),
            "outline": _c(h, .18, .34), "text": _c(h, .45, .93), "muted": _c(h, .22, .80), "dim": _c(h, .14, .60),
            "primary": _c(h, .90, .78), "primary_c": _c(h, .55, .34), "on_primary_c": _c(h, .95, .91),
            "tertiary": _c(t, .75, .74), "tertiary_c": _c(t, .45, .30),
        },
        "light": {
            "card": _c(h, .50, .94), "surface": _c(h, .55, .88), "surface_hi": _c(h, .45, .84),
            "outline": _c(h, .20, .74), "text": _c(h, .35, .12), "muted": _c(h, .18, .30), "dim": _c(h, .12, .46),
            "primary": _c(h, .60, .40), "primary_c": _c(h, .90, .85), "on_primary_c": _c(h, .80, .16),
            "tertiary": _c(t, .55, .45), "tertiary_c": _c(t, .75, .84),
        },
    }


# Night Owl by Sarah Drasner (github.com/sdras/night-owl-vscode-theme).
# Values from the official theme files (dark: Night Owl, light: Night Owl Light);
# only muted/tertiary_c are blended in-between tones.
NIGHT_OWL = {
    "dark": {
        "card": "#011627", "surface": "#0b253a", "surface_hi": "#1d3b53", "outline": "#1d3b53",
        "text": "#d6deeb", "muted": "#a7b8cc", "dim": "#5f7e97",
        "primary": "#c792ea", "primary_c": "#7e57c2", "on_primary_c": "#ffffff",
        "tertiary": "#7fdbca", "tertiary_c": "#0f4c5c",
    },
    "light": {
        "card": "#f0f0f0", "surface": "#e0e0e0", "surface_hi": "#d9d9d9", "outline": "#d9d9d9",
        "text": "#403f53", "muted": "#5f7e97", "dim": "#697098",
        "primary": "#994cc3", "primary_c": "#994cc3", "on_primary_c": "#ffffff",
        "tertiary": "#0c969b", "tertiary_c": "#bfe5e4",
    },
}

THEMES = NIGHT_OWL  # alternative: scheme(SEED_HUE), or use --hue / --auto-color


def hue_from_image(path: Path) -> float | None:
    """Dominant hue of an image: colorful mid-tone pixels count most. Needs Pillow."""
    try:
        from PIL import Image
    except ImportError:
        print("⚠ Pillow fehlt (pip install pillow), Farbe wird nicht automatisch erkannt.")
        return None
    img = Image.open(path).convert("RGB").resize((64, 64))
    bins = [0.0] * 36
    data = img.tobytes()
    for i in range(0, len(data), 3):
        r, g, b = data[i], data[i + 1], data[i + 2]
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        weight = s * (1 - abs(l - 0.5) * 2)  # saturated, neither too dark nor too bright
        bins[int(h * 36) % 36] += weight
    if sum(bins) < 1:  # (almost) grayscale image
        return None
    best = max(range(36), key=lambda i: bins[i - 1] + 2 * bins[i] + bins[(i + 1) % 36])
    return best * 10 + 5

SANS = "'Google Sans','Product Sans','Segoe UI Variable Display','Segoe UI',Inter,Roboto,system-ui,-apple-system,sans-serif"

CONFIG = {
    "username": "AthanasiosG",
    "first_name": "Athanasios",
    "last_name": "Giotas",
    "chips": [("ms:person", "Developer"), ("ms:location_on", "Munich")],
    "main": [("python", "Python")],
    "also": [("openjdk", "Java"), ("rust", "Rust")],
}

W = 840  # content width of a GitHub README (scales down on mobile)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def text_width(text: str, size: float, bold: bool = False, tracking: float = 0) -> float:
    narrow, wide = set("il.,:;|!'·ftjrI ()"), set("mwMW@%")
    w = sum(0.30 if c in narrow else 0.85 if c in wide else 0.66 if (c.isupper() or c.isdigit()) else 0.54
            for c in text)
    return w * size * (1.06 if bold else 1.0) + tracking * len(text)


def icon(name: str, x: float, y: float, size: float, fill: str) -> str:
    ic = ICONS[name]
    s = size / ic["vb"]
    return (f'<path transform="translate({x:.1f} {y:.1f}) scale({s:.4f}) translate(0 {-ic["y0"]})" '
            f'fill="{fill}" d="{ic["d"]}"/>')


def radial_path(cx, cy, fn, steps=240) -> str:
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        r = fn(t)
        pts.append(f"{cx + r * math.cos(t):.1f},{cy + r * math.sin(t):.1f}")
    return "M" + " L".join(pts) + " Z"


def cookie(cx, cy, r, amp, lobes, rot=0.0) -> str:
    """Material-3 'cookie' shape (scalloped circle)."""
    return radial_path(cx, cy, lambda t: r + amp * math.cos(lobes * (t - rot)))


def blob(cx, cy, r, seed=0.0) -> str:
    return radial_path(cx, cy, lambda t: r * (1 + 0.13 * math.sin(3 * t + seed) + 0.06 * math.cos(5 * t + 2 * seed)))


def svg(w, h, body, style="") -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<style>
  text {{ font-family: {SANS}; }}
  {style}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
{body}
</svg>
'''


def chip(x, y, ic, label, T, filled=False, h=38) -> tuple[str, float]:
    w = 14 + 18 + 9 + text_width(label, 15) + 18
    if filled:
        bg = f'<rect x="{x}" y="{y}" width="{w:.0f}" height="{h}" rx="12" fill="{T["primary_c"]}"/>'
        fg, ic_col = T["on_primary_c"], T["on_primary_c"]
    else:
        bg = f'<rect x="{x}" y="{y}" width="{w:.0f}" height="{h}" rx="12" fill="{T["surface"]}"/>'
        fg, ic_col = T["text"], T["primary"]
    return (bg + icon(ic, x + 14, y + (h - 18) / 2, 18, ic_col)
            + f'<text x="{x + 41}" y="{y + h / 2 + 5.5}" font-size="15" font-weight="500" fill="{fg}">{escape(label)}</text>'), w


# ─────────────────────────────────────────────────────────────────────────────
# Cards
# ─────────────────────────────────────────────────────────────────────────────

def header(C, T, avatar_uri: str | None) -> str:
    H = 296
    ax, ay = 150, 148
    face = cookie(ax, ay, 96, 5, 12)

    if avatar_uri:
        avatar = (f'<image xlink:href="{avatar_uri}" x="{ax - 104}" y="{ay - 104}" width="208" height="208" '
                  f'preserveAspectRatio="xMidYMid slice" clip-path="url(#face)"/>')
    else:
        initials = C["first_name"][0] + C["last_name"][0]
        avatar = (f'<path d="{face}" fill="url(#ph)"/>'
                  f'<text x="{ax}" y="{ay + 16}" text-anchor="middle" font-size="46" font-weight="700" '
                  f'fill="{T["on_primary_c"]}">{escape(initials)}</text>')

    chips, cx = [], 304
    for ic, label in C["chips"]:
        s, w = chip(cx, 220, ic, label, T)
        chips.append(s)
        cx += w + 10

    body = f'''<defs>
  <clipPath id="card"><rect width="{W}" height="{H}" rx="32"/></clipPath>
  <clipPath id="face"><path d="{face}"/></clipPath>
  <linearGradient id="ph" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{T["primary_c"]}"/><stop offset="1" stop-color="{T["tertiary_c"]}"/>
  </linearGradient>
</defs>
<g clip-path="url(#card)">
  <rect width="{W}" height="{H}" fill="{T["card"]}"/>
  <path class="drift" d="{blob(815, 22, 118, 0.5)}" fill="{T["primary_c"]}"/>
  <path class="spin" d="{cookie(800, 282, 58, 6, 9)}" fill="{T["tertiary_c"]}"/>
  <path class="drift" d="{blob(640, 330, 62, 2.2)}" fill="{T["surface"]}"/>
</g>
<path class="spin slow" d="{cookie(ax, ay, 112, 9, 9)}" fill="{T["primary"]}" opacity="0.9"/>
<path d="{cookie(ax, ay, 102, 5, 12)}" fill="{T["card"]}"/>
{avatar}
<text x="300" y="118" font-size="60" font-weight="700" letter-spacing="-1.8" fill="{T["text"]}">{escape(C["first_name"])}</text>
<text x="300" y="182" font-size="60" font-weight="700" letter-spacing="-1.8" fill="{T["primary"]}">{escape(C["last_name"])}</text>
{"".join(chips)}'''

    style = '''
  .spin  { transform-box: fill-box; transform-origin: center; animation: spin 50s linear infinite; }
  .slow  { animation-duration: 80s; }
  .drift { transform-box: fill-box; transform-origin: center; animation: drift 10s ease-in-out infinite alternate; }
  @keyframes spin  { to { transform: rotate(360deg); } }
  @keyframes drift { to { transform: translate(-6px, 5px) rotate(6deg); } }'''
    return svg(W, H, body, style)


def stack(C, T) -> str:
    H = 176
    parts = [f'<rect width="{W}" height="{H}" rx="32" fill="{T["card"]}"/>',
             f'<path d="{cookie(52, 50, 21, 2.6, 8)}" fill="{T["primary_c"]}"/>',
             icon("ms:code", 41, 39, 22, T["on_primary_c"]),
             f'<text x="88" y="59" font-size="24" font-weight="600" fill="{T["text"]}">Tech stack</text>']
    x = 28
    for label, items, filled in (("Main", C["main"], True), ("Also", C["also"], False)):
        parts.append(f'<text x="{x + 2}" y="110" font-size="12" font-weight="700" letter-spacing="1.6" '
                     f'fill="{T["dim"]}">{label.upper()}</text>')
        cx = x
        for ic, name in items:
            s, w = chip(cx, 122, ic, name, T, filled=filled)
            parts.append(s)
            cx += w + 10
        x = max(cx, x + 120) + 30
    return svg(W, H, "\n".join(parts))


# ─────────────────────────────────────────────────────────────────────────────
# README + workflow
# ─────────────────────────────────────────────────────────────────────────────

def picture(name: str, alt: str, attrs: str = 'width="100%"') -> str:
    return f'''<picture>
  <source media="(prefers-color-scheme: dark)" srcset="{name}-dark.svg">
  <img src="{name}-light.svg" {attrs} alt="{escape(alt)}">
</picture>'''


def readme(C) -> str:
    name = f'{C["first_name"]} {C["last_name"]}'
    stack_alt = "Tech stack: " + ", ".join(n for _, n in C["main"] + C["also"])
    return f'''<!-- Generated by scripts/generate.py. Avatar + stats are refreshed daily by .github/workflows/stats.yml -->
<p align="center">
{picture("assets/header", f'{name}. ' + " · ".join(l for _, l in C["chips"]))}
</p>

<p align="center">
{picture("assets/stack", stack_alt)}
</p>

<p align="center">
{picture("profile/stats", "GitHub stats", 'width="49%" align="top"')}
{picture("profile/top-langs", "Top languages", 'width="49%" align="top"')}
</p>
'''


def workflow(C) -> str:
    """Daily job that renders the stats cards (dark + light) in the theme colors and commits them."""
    steps = []
    for mode, T in THEMES.items():
        hx = {k: v.lstrip("#") for k, v in T.items()}
        common = (f"hide_border=true&border_radius=32&bg_color={hx['card']}"
                  f"&title_color={hx['primary']}&text_color={hx['text']}")
        cards = {
            "stats": f"username={C['username']}&show_icons=true&card_width=420&{common}"
                     f"&icon_color={hx['tertiary']}&ring_color={hx['primary']}",
            "top-langs": f"username={C['username']}&layout=compact&langs_count=6&card_width=420&{common}",
        }
        for card, opts in cards.items():
            steps.append(f"""
      - name: {card} ({mode})
        uses: readme-tools/github-readme-stats-action@v1
        with:
          card: {card}
          options: {opts}
          path: profile/{card}-{mode}.svg
          token: ${{{{ secrets.GITHUB_TOKEN }}}}
          fail_on_error: true
""")
    return f"""# Generated by scripts/generate.py. Daily: embeds the current avatar and renders the stats cards.
name: Update profile cards

on:
  schedule:
    - cron: "17 3 * * *"   # daily 03:17 UTC
  workflow_dispatch:        # manual start: Actions tab -> "Run workflow"
  push:                     # also runs right after you change the generator
    branches: [main]
    paths: ["scripts/**"]

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Header with current avatar
        run: |
          curl -fsSL "https://github.com/${{{{ github.repository_owner }}}}.png?size=256" -o avatar.png
          python3 scripts/generate.py --avatar avatar.png
          rm avatar.png
{"".join(steps)}
      - name: Commit cards
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add README.md assets profile
          git commit -m "chore(readme): update avatar and stats cards" || exit 0
          git push
"""


def sniff_mime(raw: bytes) -> str | None:
    """Real image type from the file header (GitHub serves avatars as PNG or JPEG regardless of the URL)."""
    if raw.startswith(b"\x89PNG"):
        return "image/png"
    if raw.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if raw[:4] == b"GIF8":
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--avatar", type=Path, help="Path to your avatar (png/jpg), gets embedded into the header")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--hue", type=float, help="Use a generated palette with this hue (0-360) instead of Night Owl")
    ap.add_argument("--auto-color", action="store_true", help="Use a generated palette based on the avatar's colors")
    args = ap.parse_args()
    global THEMES
    hue = args.hue
    if hue is None and args.auto_color and args.avatar:
        hue = hue_from_image(args.avatar)
        if hue is not None:
            print(f"🎨 Farbe aus dem Profilbild: Hue {hue:.0f}")
    if hue is not None:
        THEMES = scheme(hue)

    assets = args.out / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    avatar_uri = None
    if args.avatar:
        raw = args.avatar.read_bytes()
        mime = sniff_mime(raw) or mimetypes.guess_type(args.avatar.name)[0] or "image/png"
        avatar_uri = f"data:{mime};base64," + base64.b64encode(raw).decode()
    else:
        print("⚠ Kein --avatar angegeben, im Header stehen die Initialen.")

    for mode, T in THEMES.items():
        (assets / f"header-{mode}.svg").write_text(header(CONFIG, T, avatar_uri), encoding="utf-8")
        (assets / f"stack-{mode}.svg").write_text(stack(CONFIG, T), encoding="utf-8")
    (args.out / "README.md").write_text(readme(CONFIG), encoding="utf-8")
    wf = args.out / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "stats.yml").write_text(workflow(CONFIG), encoding="utf-8")
    print(f"✔ README.md + {len(list(assets.glob('*.svg')))} SVGs + workflow in {args.out}")


if __name__ == "__main__":
    main()
