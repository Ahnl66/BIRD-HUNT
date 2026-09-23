"""Create the deterministic 320x240 G7400 dawn title artwork."""
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/g7400"
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
BLUE = (0, 0, 255)
WHITE = (255, 255, 255)

FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "N": ("10001", "11001", "11001", "10101", "10011", "10011", "10001"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "'": ("00100", "00100", "01000", "00000", "00000", "00000", "00000"),
    "s": ("00000", "00000", "01110", "10000", "01110", "00001", "11110"),
    " ": ("00000",) * 7,
}


def draw_text(draw, text, y, cell_scale):
    """Draw one glyph per 8x10 cell (or four cells for the large title)."""
    cell_width, cell_height = 8 * cell_scale, 10 * cell_scale
    pixel_scale = cell_scale
    x = (320 - len(text) * cell_width) // 2
    for char in text:
        glyph_x = x + (cell_width - 5 * pixel_scale) // 2
        glyph_y = y + (cell_height - 7 * pixel_scale) // 2
        for row, bits in enumerate(FONT[char]):
            for col, bit in enumerate(bits):
                if bit == "1":
                    left = glyph_x + col * pixel_scale
                    top = glyph_y + row * pixel_scale
                    draw.rectangle((left, top, left + pixel_scale - 1,
                                    top + pixel_scale - 1), fill=WHITE)
        x += cell_width


def draw_bird(draw, x, y):
    """Draw a reusable two-cell bird silhouette, aligned to the character grid."""
    rows = ("1100000000000011", "0110000000000110", "0011000000001100",
            "0001100000011000", "0000110000110000", "0000011111100000",
            "0000001111000000", "0000000110000000")
    for row, bits in enumerate(rows):
        for col, bit in enumerate(bits):
            if bit == "1":
                draw.point((x + col, y + row), fill=BLACK)


def main():
    # Begin with the gameplay landscape so unchanged cells need no extra ROM data.
    palette = Image.new("P", (1, 1))
    colors = BLACK + GREEN + YELLOW + BLUE + WHITE
    palette.putpalette(list(colors) + [0] * (768 - len(colors)))
    image = Image.open(OUT / "concept.png").convert("RGB").resize(
        (320, 240), Image.Resampling.BOX).quantize(
            palette=palette, dither=Image.Dither.NONE).convert("RGB")
    draw = ImageDraw.Draw(image)

    # A low dawn sun stays in the sky above the existing shrub line.
    sun_rows = ((128, 148, 172), (132, 140, 180), (136, 136, 184),
                (140, 132, 188), (144, 132, 188), (148, 128, 192))
    for y, left, right in sun_rows:
        draw.rectangle((left, y, right, y + 3), fill=YELLOW)

    # Two identical, grid-aligned birds stay well above and right of the sun.
    draw_bird(draw, 224, 90)
    draw_bird(draw, 272, 110)

    draw_text(draw, "AHNL66's", 30, 1)
    draw_text(draw, "BIRD HUNT", 60, 2)
    draw_text(draw, "PRESS FIRE", 100, 1)

    image.save(OUT / "intro-source.png")


if __name__ == "__main__":
    main()
