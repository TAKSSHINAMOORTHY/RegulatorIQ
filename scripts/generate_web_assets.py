"""Generate visual assets for RegulatorIQ frontend (Ledger Aurora).

Outputs:
- docs/design/screenshots/light.png, dark.png, theme_switch.gif
- web/public/favicon.ico, favicon.svg, apple-touch-icon.png, og-light.png, og-dark.png, manifest.json, robots.txt
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DOCS_DESIGN = ROOT / "docs" / "design"
SCREENSHOTS_DIR = DOCS_DESIGN / "screenshots"
PUBLIC_DIR = ROOT / "web" / "public"

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)


def create_screenshot(theme: str, path: Path):
    bg_color = (250, 246, 238) if theme == "light" else (10, 15, 30)
    card_color = (255, 255, 255) if theme == "light" else (18, 26, 46)
    ink_color = (27, 26, 23) if theme == "light" else (237, 239, 245)
    accent_color = (194, 97, 0) if theme == "light" else (245, 177, 76)
    line_color = (231, 223, 207) if theme == "light" else (36, 48, 73)

    img = Image.new("RGB", (1280, 800), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Header bar
    draw.rectangle([0, 0, 1280, 56], fill=card_color, outline=line_color, width=1)
    draw.text((32, 18), "RegulatorIQ", fill=accent_color)
    draw.text((140, 20), f"[ {theme.upper()} MODE ]", fill=ink_color)

    # Ledger lines background motif
    for y in range(80, 780, 24):
        draw.line([(60, y), (1220, y)], fill=line_color, width=1)

    # Main Chat Card
    draw.rounded_rectangle(
        [260, 100, 1020, 680], radius=16, fill=card_color, outline=line_color, width=1
    )
    draw.text((290, 130), "Regulatory Intelligence Engine", fill=accent_color)
    draw.text(
        (290, 170),
        "Q: What is the capital adequacy ratio requirement for commercial banks?",
        fill=ink_color,
    )

    # Answer text block
    draw.text((290, 230), "Official Synthesis (Verified Grounding):", fill=accent_color)
    draw.text(
        (290, 260),
        "Under RBI Master Circular DOR.CAP.REC.4/21.06.001/2023-24 on Basel III,\n"
        "commercial banks must maintain a minimum Total Capital Adequacy Ratio (CAR)\n"
        "of 9.0% on an ongoing basis. Common Equity Tier 1 (CET1) must be at least 5.5%,\n"
        "and Tier 1 capital must be at least 7.0%. Additionally, a Capital Conservation\n"
        "Buffer (CCB) of 2.5% applies.",
        fill=ink_color,
    )

    # Source cards block
    draw.rounded_rectangle(
        [290, 380, 990, 480], radius=8, fill=bg_color, outline=accent_color, width=1
    )
    draw.text((310, 395), "[1] Master Circular - Basel III Capital Regulations", fill=ink_color)
    draw.text(
        (310, 420),
        "RBI/2023-24/04 | DOR.CAP.REC.4/21.06.001/2023-24 | STATUS: CURRENT",
        fill=accent_color,
    )

    # Composer box at bottom of card
    draw.rounded_rectangle(
        [290, 600, 990, 650], radius=12, fill=bg_color, outline=line_color, width=1
    )
    draw.text(
        (310, 618), "Ask a regulatory compliance question... (Press / to focus)", fill=line_color
    )

    img.save(path)
    print(f"Generated screenshot: {path}")


def create_favicon():
    # ICO 32x32
    ico = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(ico)
    d.rounded_rectangle([2, 2, 30, 30], radius=6, fill=(194, 97, 0))
    # Stacked ledger lines
    d.line([(8, 10), (24, 10)], fill=(255, 255, 255), width=2)
    d.line([(10, 16), (24, 16)], fill=(255, 255, 255), width=2)
    d.line([(13, 22), (24, 22)], fill=(255, 255, 255), width=2)
    ico.save(PUBLIC_DIR / "favicon.ico")

    # Apple touch icon 180x180
    apple = Image.new("RGBA", (180, 180), (10, 15, 30))
    da = ImageDraw.Draw(apple)
    da.rounded_rectangle([15, 15, 165, 165], radius=32, fill=(194, 97, 0))
    da.line([(45, 60), (135, 60)], fill=(255, 255, 255), width=10)
    da.line([(55, 90), (135, 90)], fill=(255, 255, 255), width=10)
    da.line([(70, 120), (135, 120)], fill=(255, 255, 255), width=10)
    apple.save(PUBLIC_DIR / "apple-touch-icon.png")

    # SVG favicon
    svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="8" fill="#C26100"/>
  <rect x="6" y="8" width="20" height="3" rx="1.5" fill="#FFFFFF"/>
  <rect x="9" y="14" width="17" height="3" rx="1.5" fill="#FFFFFF"/>
  <rect x="13" y="20" width="13" height="3" rx="1.5" fill="#FFFFFF"/>
</svg>"""
    (PUBLIC_DIR / "favicon.svg").write_text(svg_content)


def create_manifest():
    manifest = {
        "name": "RegulatorIQ",
        "short_name": "RegulatorIQ",
        "description": "Verifiable RBI banking compliance and regulatory intelligence.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#FAF6EE",
        "theme_color": "#C26100",
        "icons": [
            {"src": "/favicon.ico", "sizes": "32x32", "type": "image/x-icon"},
            {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
        ],
    }
    (PUBLIC_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))


def create_robots_txt():
    robots = """User-agent: *
Allow: /
Allow: /about
Allow: /privacy
Disallow: /status
Disallow: /api/
"""
    (PUBLIC_DIR / "robots.txt").write_text(robots)


def create_animated_preview():
    # Animated gif of theme switch
    img_light = Image.open(SCREENSHOTS_DIR / "light.png").resize((640, 400))
    img_dark = Image.open(SCREENSHOTS_DIR / "dark.png").resize((640, 400))

    img_light.save(
        SCREENSHOTS_DIR / "theme_switch.gif",
        save_all=True,
        append_images=[img_dark],
        duration=1200,
        loop=0,
    )
    print("Generated animated preview: theme_switch.gif")


def main():
    print("Generating RegulatorIQ web visual assets...")
    create_screenshot("light", SCREENSHOTS_DIR / "light.png")
    create_screenshot("dark", SCREENSHOTS_DIR / "dark.png")
    create_screenshot("light", PUBLIC_DIR / "og-light.png")
    create_screenshot("dark", PUBLIC_DIR / "og-dark.png")
    create_favicon()
    create_manifest()
    create_robots_txt()
    create_animated_preview()
    print("All assets successfully created!")


if __name__ == "__main__":
    main()
