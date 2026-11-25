"""Draw the app icon: a flat orange rounded square with "API" in white.

The letters are plain geometric shapes (no font file), so the same drawing becomes the SVG favicon, the PNGs, the
Windows .ico and the macOS .icns. Run it from the repository root after changing the design:

    python scripts/make_icons.py

It needs Pillow, which only this script uses; the app itself has no dependencies.
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "src" / "api_credit_code" / "static"
ORANGE = (234, 88, 12)  # #EA580C
WHITE = (255, 255, 255)
SS = 4  # supersampling factor for smooth edges


def shapes(size, inset=0.0, block=0.74):
    """The icon as a list of (kind, fill, geometry) in a size x size box.

    inset: transparent margin on each side, as a fraction of size (macOS icons sit inside a margin).
    block: how much of the square's width the word takes (small icons use more, so the letters stay readable).
    """
    s = size * (1 - 2 * inset)
    o = size * inset
    out = [("rrect", ORANGE, (o, o, o + s, o + s, s * 0.225))]
    # The word in design units: cap height 380, stems 88, letter widths A 320 / P 255 / I 88, gaps 44.
    H, W, wa, wp, wi, gap = 380.0, 88.0, 320.0, 255.0, 88.0, 44.0
    total = wa + gap + wp + gap + wi
    k = s * block / total
    x0 = o + (s - total * k) / 2
    top = o + (s - H * k) / 2
    base = top + H * k
    W, H, wa, wp, wi, gap = W * k, H * k, wa * k, wp * k, wi * k, gap * k

    # A: a flat-topped triangle, minus the counter above the crossbar and the gap below it.
    cx = x0 + wa / 2
    a = W * 0.55
    wl = W * 1.12  # a slanted stroke needs more width across to look as heavy as a straight one
    out.append(("poly", WHITE, [(cx - a, top), (cx + a, top), (x0 + wa, base), (x0, base)]))
    run = cx - a - x0  # how far the outer left edge leans over the full height

    def left_inner(y):
        return x0 + wl + (base - y) * run / H

    apex = base - (cx - x0 - wl) * H / run
    bar_bottom = base - H * 0.23
    bar_top = bar_bottom - W * 0.76
    if apex < bar_top:
        out.append(("poly", ORANGE, [(cx, apex), (left_inner(bar_top), bar_top), (2 * cx - left_inner(bar_top), bar_top)]))
    out.append(("poly", ORANGE, [(left_inner(bar_bottom), bar_bottom), (2 * cx - left_inner(bar_bottom), bar_bottom),
                                 (x0 + wa - wl, base), (x0 + wl, base)]))

    # P: a stem and a D-shaped bowl.
    px = x0 + wa + gap
    hb = H * 0.58
    r = hb / 2
    t = W * 0.86
    out.append(("rect", WHITE, (px, top, px + W, base)))
    out.append(("rect", WHITE, (px, top, px + wp - r, top + hb)))
    out.append(("circle", WHITE, (px + wp - r, top + r, r)))
    out.append(("rect", ORANGE, (px + W, top + t, px + wp - r, top + hb - t)))
    out.append(("circle", ORANGE, (px + wp - r, top + r, r - t)))

    # I
    ix = px + wp + gap
    out.append(("rect", WHITE, (ix, top, ix + wi, base)))
    return out


def render(size, **kw):
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for kind, fill, g in shapes(big, **kw):
        if kind == "rrect":
            x1, y1, x2, y2, rad = g
            d.rounded_rectangle((x1, y1, x2, y2), radius=rad, fill=fill)
        elif kind == "rect":
            d.rectangle(g, fill=fill)
        elif kind == "circle":
            cx, cy, rad = g
            d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=fill)
        else:
            d.polygon(g, fill=fill)
    return img.resize((size, size), Image.LANCZOS)


def svg(size=512):
    hexc = lambda c: "#%02X%02X%02X" % c
    parts = []
    for kind, fill, g in shapes(size):
        f = hexc(fill)
        if kind == "rrect":
            x1, y1, x2, y2, rad = g
            parts.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2 - x1:.1f}" height="{y2 - y1:.1f}" rx="{rad:.1f}" fill="{f}"/>')
        elif kind == "rect":
            x1, y1, x2, y2 = g
            parts.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2 - x1:.1f}" height="{y2 - y1:.1f}" fill="{f}"/>')
        elif kind == "circle":
            cx, cy, rad = g
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rad:.1f}" fill="{f}"/>')
        else:
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in g)
            parts.append(f'<polygon points="{pts}" fill="{f}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">' + "".join(parts) + "</svg>\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "icon.svg").write_text(svg(), encoding="utf-8")
    for n in (180, 192, 512):
        render(n).save(OUT / f"icon-{n}.png", optimize=True)
    render(64, block=0.8).save(OUT / "icon-64.png", optimize=True)
    # Windows: one picture per size, the small ones with bigger letters
    ico = [render(n, block=0.86 if n <= 32 else 0.8 if n <= 64 else 0.74) for n in (16, 24, 32, 48, 64, 128, 256)]
    ico[-1].save(OUT / "icon.ico", format="ICO", sizes=[im.size for im in ico], append_images=ico[:-1])
    # macOS: the shape sits inside the standard margin of the 1024 px canvas
    mac = [render(n, inset=0.1) for n in (16, 32, 64, 128, 256, 512, 1024)]
    mac[-1].save(OUT / "AppIcon.icns", format="ICNS", append_images=mac[:-1])
    for p in sorted(OUT.glob("icon*")) + [OUT / "AppIcon.icns"]:
        print(f"{p.name:16} {p.stat().st_size:>8} bytes")


if __name__ == "__main__":
    main()
