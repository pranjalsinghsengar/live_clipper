"""Streamer-Enhanced High-CTR Thumbnail Designer for YouTube Shorts & Comparison Videos."""
from __future__ import annotations

import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

log = logging.getLogger("thumbnail_designer")

STREAMERS_DIR = Path(__file__).parent / "assets" / "streamers"

def _get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Find a bold system font on macOS."""
    font_paths = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def create_streamer_thumbnail(
    base_frame_path: Path,
    out_thumb_path: Path,
    streamer_name: str = "carryminati",
    headline: str = "GTA 5 VS GTA 6",
    subheadline: str = "REAL OR FAKE?! 😱",
    tag_color: tuple[int, int, int] = (255, 230, 0),  # Yellow
) -> Path:
    """Create a high-impact, viral thumbnail with GTA 6 streamer sticker,
    glowing border, and high-CTR typography."""
    out_thumb_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Load base frame (720x1280 or resize)
    base = Image.open(base_frame_path).convert("RGBA")
    if base.size != (720, 1280):
        base = base.resize((720, 1280), Image.Resampling.LANCZOS)

    # Slightly increase contrast and saturation for thumbnail pop
    from PIL import ImageEnhance
    base = ImageEnhance.Color(base).enhance(1.25)
    base = ImageEnhance.Contrast(base).enhance(1.15)

    draw = ImageDraw.Draw(base)

    # 2. Add Top Header Card
    font_head = _get_font(52, bold=True)
    font_sub = _get_font(34, bold=True)

    # Dark gradient overlay on top for text legibility
    top_overlay = Image.new("RGBA", (720, 260), (0, 0, 0, 180))
    base.paste(top_overlay, (0, 0), top_overlay)

    # Draw Red Accent Bar at very top
    draw.rectangle([0, 0, 720, 12], fill=(255, 30, 30, 255))

    # Headline text with thick black outline
    def draw_text_with_outline(text, x, y, font, fill_color, outline_color=(0, 0, 0), stroke_width=5):
        # Draw stroke
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx * dx + dy * dy <= stroke_width * stroke_width:
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
        draw.text((x, y), text, font=font, fill=fill_color)

    # Center headline
    head_bbox = draw.textbbox((0, 0), headline, font=font_head)
    head_w = head_bbox[2] - head_bbox[0]
    head_x = (720 - head_w) // 2
    draw_text_with_outline(headline, head_x, 40, font_head, (255, 255, 255), (0, 0, 0), stroke_width=6)

    # Subheadline with yellow badge
    sub_bbox = draw.textbbox((0, 0), subheadline, font=font_sub)
    sub_w = sub_bbox[2] - sub_bbox[0]
    sub_x = (720 - sub_w) // 2

    # Draw yellow pill badge background
    pad_x, pad_y = 20, 8
    badge_box = [sub_x - pad_x, 115 - pad_y, sub_x + sub_w + pad_x, 115 + (sub_bbox[3] - sub_bbox[1]) + pad_y]
    draw.rounded_rectangle(badge_box, radius=12, fill=(255, 220, 0, 240), outline=(0, 0, 0), width=3)
    draw.text((sub_x, 115), subheadline, font=font_sub, fill=(0, 0, 0))

    # 3. Add Streamer Circular Sticker with glowing border
    streamer_key = streamer_name.lower().replace(" ", "_")
    streamer_path = STREAMERS_DIR / f"{streamer_key}.jpg"
    if not streamer_path.exists():
        streamer_path = STREAMERS_DIR / "carryminati.jpg"

    if streamer_path.exists():
        st_img = Image.open(streamer_path).convert("RGBA")
        st_size = 220  # diameter
        st_img = ImageOps.fit(st_img, (st_size, st_size), centering=(0.5, 0.5))

        # Circular mask
        mask = Image.new("L", (st_size, st_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, st_size, st_size), fill=255)

        # Output circular image
        circular_st = Image.new("RGBA", (st_size, st_size), (0, 0, 0, 0))
        circular_st.paste(st_img, (0, 0), mask=mask)

        # Create glowing outer ring
        border_size = st_size + 24
        border_img = Image.new("RGBA", (border_size, border_size), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(border_img)
        # Drop shadow
        b_draw.ellipse((4, 4, border_size - 4, border_size - 4), fill=(0, 0, 0, 160))
        # Cyan / Neon outer ring
        b_draw.ellipse((2, 2, border_size - 2, border_size - 2), outline=(0, 255, 255, 255), width=8)

        # Paste streamer in center of ring
        border_img.paste(circular_st, (12, 12), mask=circular_st)

        # Paste into bottom right corner of thumbnail
        st_x = 720 - border_size - 25
        st_y = 1280 - border_size - 40
        base.paste(border_img, (st_x, st_y), mask=border_img)

        # Add streamer name pill below/on the sticker
        font_tag = _get_font(24, bold=True)
        display_name = streamer_name.upper()
        tag_bbox = draw.textbbox((0, 0), display_name, font=font_tag)
        tag_w = tag_bbox[2] - tag_bbox[0]
        tag_x = st_x + (border_size - tag_w) // 2
        tag_y = st_y + border_size - 14

        draw.rounded_rectangle([tag_x - 12, tag_y - 4, tag_x + tag_w + 12, tag_y + 28], radius=8, fill=(0, 0, 0, 230), outline=(0, 255, 255), width=2)
        draw.text((tag_x, tag_y), display_name, font=font_tag, fill=(255, 255, 255))

    # Convert to RGB and save as high-quality JPEG
    rgb_thumb = base.convert("RGB")
    rgb_thumb.save(out_thumb_path, "JPEG", quality=95)
    log.info("Generated high-CTR streamer thumbnail -> %s", out_thumb_path)
    return out_thumb_path
