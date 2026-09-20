#!/usr/bin/env python3
"""Generate on-brand placeholder card images for the portfolio site.

The portfolio (github.com/ndeogobernard/ndeogo) uses real map screenshots as
card thumbnails at `assets/<slug>.jpg`, 16:10, on a strictly monochrome dark
palette. Until this project has real figures to export, these stand in: dark
abstract analytical tiles in the site's own greys, so nothing on the live site
renders as a broken or jarringly blank tile.

Each is replaced by a real export as the project produces one - see
docs/PORTFOLIO_UPDATES.md for the checklist.

Usage:
    python tools/make_portfolio_placeholders.py [--out ../ndeogo/assets]
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle

# Site palette (assets/css/site.css, dark theme)
BG = "#141517"
G2 = "#191b1e"
G3 = "#212629"
G4 = "#293034"
G5 = "#333b3e"
G6 = "#3b4345"
G8 = "#52595b"
G9 = "#6e7679"
G10 = "#878d8f"

W, H, DPI = 16.0, 10.0, 100          # -> 1600 x 1000 px


def _canvas():
    fig, ax = plt.subplots(figsize=(W, H), dpi=DPI)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 160)
    ax.set_ylim(0, 100)
    ax.set_axis_off()
    ax.set_position([0, 0, 1, 1])
    return fig, ax


def _graticule(ax, step=10, color=G3, lw=0.6):
    for x in range(0, 161, step):
        ax.plot([x, x], [0, 100], color=color, lw=lw, zorder=0)
    for y in range(0, 101, step):
        ax.plot([0, 160], [y, y], color=color, lw=lw, zorder=0)


def _save(fig, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=BG, dpi=DPI, pil_kwargs={"quality": 88, "optimize": True})
    plt.close(fig)
    print(f"  {out.name:34} {out.stat().st_size / 1024:6.0f} KB")


def _blob(rng, cx, cy, r, n=9, jitter=0.42):
    """Irregular polygon standing in for a parcel or service area."""
    import math
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * (1 + rng.uniform(-jitter, jitter))
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a) * 0.72))
    return pts


# ---------------------------------------------------------------- flagship
def analysis(out: Path):
    """Scored candidate parcels over a road graticule."""
    rng = random.Random(11)
    fig, ax = _canvas()
    _graticule(ax, 8)

    # arterial corridors
    for y in (28, 62):
        ax.plot([0, 160], [y - 4, y + 4], color=G5, lw=2.4, zorder=1)
    for x in (44, 104):
        ax.plot([x - 3, x + 3], [0, 100], color=G5, lw=2.4, zorder=1)

    # candidate parcels, shaded by "score"
    shades = [G4, G5, G6, G8, G9, G10]
    spots = [(30, 70, 11), (62, 44, 14), (96, 72, 10), (124, 38, 12),
             (48, 22, 9), (136, 76, 8), (82, 82, 7), (18, 42, 8)]
    for i, (cx, cy, r) in enumerate(spots):
        fc = shades[min(i, len(shades) - 1)]
        ax.add_patch(Polygon(_blob(rng, cx, cy, r), closed=True,
                             facecolor=fc, edgecolor=G9, lw=1.0, alpha=0.92, zorder=2))

    # recommended site marker - dashed outline, as on the results maps
    ax.add_patch(Polygon(_blob(rng, 62, 44, 17), closed=True, facecolor="none",
                         edgecolor=G10, lw=1.8, ls=(0, (5, 4)), zorder=3))
    _save(fig, out)


# ---------------------------------------------------------------- toolbox
def toolbox(out: Path):
    """Pipeline of tools feeding one another."""
    fig, ax = _canvas()
    _graticule(ax, 16, color=G2)

    rows = [(24, [18, 52, 86, 120]), (50, [18, 52, 86, 120]), (76, [18, 52, 86])]
    boxes = []
    for y, xs in rows:
        for x in xs:
            boxes.append((x, y))
            ax.add_patch(FancyBboxPatch((x, y), 26, 13,
                                        boxstyle="round,pad=0,rounding_size=2",
                                        facecolor=G3, edgecolor=G6, lw=1.2, zorder=2))
            ax.plot([x + 4, x + 12], [y + 8.5, y + 8.5], color=G9, lw=1.6, zorder=3)
            ax.plot([x + 4, x + 9], [y + 4.5, y + 4.5], color=G5, lw=1.6, zorder=3)

    for y, xs in rows:
        for x in xs[:-1]:
            ax.annotate("", xy=(x + 34, y + 6.5), xytext=(x + 26, y + 6.5),
                        arrowprops=dict(arrowstyle="-|>", color=G8, lw=1.3), zorder=1)
    for x in (18, 52, 86):
        ax.annotate("", xy=(x + 13, 50), xytext=(x + 13, 37),
                    arrowprops=dict(arrowstyle="-|>", color=G5, lw=1.1), zorder=1)
        ax.annotate("", xy=(x + 13, 76), xytext=(x + 13, 63),
                    arrowprops=dict(arrowstyle="-|>", color=G5, lw=1.1), zorder=1)
    _save(fig, out)


# ------------------------------------------------------------ geodatabase
def geodatabase(out: Path):
    """ERD - entity boxes joined by relationship lines."""
    fig, ax = _canvas()
    _graticule(ax, 16, color=G2)

    ents = [(14, 58, 34, 30), (63, 66, 34, 24), (112, 54, 34, 34), (40, 12, 34, 28), (92, 14, 34, 24)]
    for x, y, w, h in ents:
        ax.add_patch(Rectangle((x, y), w, h, facecolor=G3, edgecolor=G6, lw=1.2, zorder=2))
        ax.add_patch(Rectangle((x, y + h - 6), w, 6, facecolor=G5, edgecolor=G6, lw=1.2, zorder=3))
        rows = int((h - 8) // 5)
        for r in range(rows):
            yy = y + h - 11 - r * 5
            ax.plot([x + 3, x + w - 6], [yy, yy], color=G8 if r == 0 else G4,
                    lw=1.4 if r == 0 else 1.1, zorder=3)

    links = [((48, 70), (63, 76)), ((97, 76), (112, 74)), ((57, 58), (57, 40)),
             ((74, 26), (92, 26)), ((112, 62), (109, 38))]
    for (x1, y1), (x2, y2) in links:
        ax.plot([x1, x2], [y1, y2], color=G8, lw=1.3, zorder=1)
        for cx, cy in ((x1, y1), (x2, y2)):
            ax.add_patch(Circle((cx, cy), 1.5, facecolor=G9, edgecolor="none", zorder=4))
    _save(fig, out)


# -------------------------------------------------------------- dashboard
def dashboard(out: Path):
    """Dashboard frame - map panel, indicators, ranked list, bar chart."""
    rng = random.Random(5)
    fig, ax = _canvas()

    ax.add_patch(Rectangle((0, 88), 160, 12, facecolor=G2, edgecolor="none", zorder=1))
    for i in range(4):
        ax.add_patch(FancyBboxPatch((6 + i * 26, 91), 20, 6,
                                    boxstyle="round,pad=0,rounding_size=1.5",
                                    facecolor=G4, edgecolor="none", zorder=2))

    ax.add_patch(Rectangle((6, 30), 84, 54, facecolor=G2, edgecolor=G4, lw=1.1, zorder=1))
    for x in range(10, 90, 8):
        ax.plot([x, x], [30, 84], color=G3, lw=0.6, zorder=2)
    for y in range(34, 85, 8):
        ax.plot([6, 90], [y, y], color=G3, lw=0.6, zorder=2)
    for cx, cy, r, fc in [(28, 62, 7, G6), (54, 48, 9, G9), (72, 70, 6, G5), (40, 38, 5, G4)]:
        ax.add_patch(Polygon(_blob(rng, cx, cy, r), closed=True, facecolor=fc,
                             edgecolor=G9, lw=0.9, zorder=3))

    for i in range(4):
        ax.add_patch(Rectangle((96, 66 - i * 14), 26, 11, facecolor=G2, edgecolor=G4, lw=1.1, zorder=1))
        ax.plot([99, 108], [73 - i * 14, 73 - i * 14], color=G5, lw=1.3, zorder=2)
        ax.plot([99, 115], [69 - i * 14, 69 - i * 14], color=G10, lw=2.4, zorder=2)

    ax.add_patch(Rectangle((128, 10), 26, 74, facecolor=G2, edgecolor=G4, lw=1.1, zorder=1))
    for i in range(9):
        ax.plot([131, 131 + rng.uniform(7, 20)], [78 - i * 8, 78 - i * 8],
                color=G8 if i < 3 else G5, lw=3.2, zorder=2)

    for i in range(7):
        h = rng.uniform(6, 20)
        ax.add_patch(Rectangle((10 + i * 11, 6), 7, h, facecolor=G6 if i < 3 else G4,
                               edgecolor="none", zorder=2))
    _save(fig, out)


# ------------------------------------------------------------- map series
def mapseries(out: Path):
    """Contact sheet of map pages."""
    rng = random.Random(23)
    fig, ax = _canvas()

    for r in range(2):
        for c in range(4):
            x, y = 8 + c * 37, 52 - r * 42
            ax.add_patch(Rectangle((x, y), 30, 34, facecolor=G2, edgecolor=G5, lw=1.2, zorder=1))
            ax.add_patch(Rectangle((x, y + 29), 30, 5, facecolor=G4, edgecolor="none", zorder=2))
            ax.plot([x + 2, x + 16], [y + 31.5, y + 31.5], color=G9, lw=1.4, zorder=3)
            for gx in range(int(x) + 4, int(x) + 30, 6):
                ax.plot([gx, gx], [y + 3, y + 28], color=G3, lw=0.5, zorder=2)
            n = rng.randint(2, 4)
            for _ in range(n):
                cx = rng.uniform(x + 7, x + 24)
                cy = rng.uniform(y + 8, y + 24)
                ax.add_patch(Polygon(_blob(rng, cx, cy, rng.uniform(2.5, 5)), closed=True,
                                     facecolor=rng.choice([G4, G5, G6, G8]),
                                     edgecolor=G9, lw=0.7, zorder=3))
            ax.plot([x + 3, x + 10], [y + 3, y + 3], color=G6, lw=1.6, zorder=3)
    _save(fig, out)


BUILDERS = {
    "dsg-dfw-analysis": analysis,
    "dsg-dfw-toolbox": toolbox,
    "dsg-dfw-geodatabase": geodatabase,
    "dsg-dfw-dashboard": dashboard,
    "dsg-dfw-mapseries": mapseries,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../ndeogo/assets",
                    help="portfolio assets directory (default: ../ndeogo/assets)")
    args = ap.parse_args()
    out_dir = Path(args.out).resolve()
    print(f"Writing placeholder card images to {out_dir}")
    for slug, fn in BUILDERS.items():
        fn(out_dir / f"{slug}.jpg")


if __name__ == "__main__":
    main()
