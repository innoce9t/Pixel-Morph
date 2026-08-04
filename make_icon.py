"""Generates the PixelMorph app icon (neomorphic style) as pixelmorph.ico."""

from PIL import Image, ImageDraw, ImageFilter

BG = (230, 233, 239, 255)
DARK = (168, 178, 196, 255)
LIGHT = (255, 255, 255, 255)
ACCENT = (108, 99, 255, 255)
ACCENT_LIGHT = (150, 143, 255, 255)


def rounded(size, radius, fill):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=fill)
    return img


def build(size):
    scale = 4
    s = size * scale
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    pad = s // 10
    radius = s // 4

    # soft dark shadow (bottom-right)
    shadow = rounded(s, radius, DARK)
    shadow = shadow.filter(ImageFilter.GaussianBlur(s // 18))
    canvas.alpha_composite(shadow, (pad // 2, pad // 2))

    # soft light highlight (top-left)
    highlight = rounded(s, radius, LIGHT)
    highlight = highlight.filter(ImageFilter.GaussianBlur(s // 18))
    canvas.alpha_composite(highlight, (-pad // 3, -pad // 3))

    # base rounded square
    base = rounded(s, radius, BG)
    canvas.alpha_composite(base)

    # inner accent "photo/image" glyph: rounded square with mountain + sun
    inner_margin = s // 5
    glyph = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glyph)
    gx0, gy0, gx1, gy1 = inner_margin, inner_margin, s - inner_margin, s - inner_margin
    gd.rounded_rectangle([gx0, gy0, gx1, gy1], radius=s // 12, fill=ACCENT)

    sun_r = (gx1 - gx0) // 8
    sun_cx, sun_cy = gx0 + (gx1 - gx0) * 0.28, gy0 + (gy1 - gy0) * 0.32
    gd.ellipse([sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r], fill=ACCENT_LIGHT)

    mtn_h = (gy1 - gy0) * 0.42
    gd.polygon(
        [
            (gx0 + (gx1 - gx0) * 0.10, gy1 - (gy1 - gy0) * 0.12),
            (gx0 + (gx1 - gx0) * 0.42, gy1 - mtn_h),
            (gx0 + (gx1 - gx0) * 0.62, gy1 - (gy1 - gy0) * 0.28),
            (gx0 + (gx1 - gx0) * 0.78, gy1 - mtn_h * 0.85),
            (gx0 + (gx1 - gx0) * 0.92, gy1 - (gy1 - gy0) * 0.12),
        ],
        fill=ACCENT_LIGHT,
    )

    canvas.alpha_composite(glyph)

    return canvas.resize((size, size), Image.LANCZOS)


sizes = [16, 24, 32, 48, 64, 128, 256]
images = [build(s) for s in sizes]
images[-1].save(
    "pixelmorph.ico",
    format="ICO",
    sizes=[(s, s) for s in sizes],
)
print("Saved pixelmorph.ico")
