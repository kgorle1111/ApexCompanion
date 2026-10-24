"""Draw a simple 1024px app icon PNG (build-time only). usage: python make_icon.py OUT.png"""

import sys

from PIL import Image, ImageDraw, ImageFont

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((80, 80, S - 80, S - 80), radius=190, fill=(18, 18, 22, 255))
d.ellipse((250, 250, S - 250, S - 250), outline=(232, 72, 48, 255), width=46)  # the "eye"
d.ellipse((430, 430, S - 430, S - 430), fill=(232, 72, 48, 255))
try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 120)
    d.text((S / 2, 860), "APEX", font=font, fill=(240, 240, 240, 255), anchor="mm")
except OSError:
    pass  # icon without the word is fine
img.save(sys.argv[1])
