"""Convert the gameplay and dawn title art to one shared EF9340/41 DRCS set.

Requires Pillow and numpy. Run from any directory; output is deterministic.
This produces assets, not a ROM loader or a hardware/emulator test.
"""
from collections import Counter
from pathlib import Path
import json

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "assets/g7400"
# EF9340 color bits: R=1, G=2, B=4. Use four flat colors from the concept.
PALETTE = np.array([[0, 0, 0], [255, 0, 0], [0, 255, 0], [255, 255, 0],
                    [0, 0, 255], [255, 0, 255], [0, 255, 255], [255, 255, 255]])
COLORS = np.array([0, 2, 3, 4, 7])


def decode(patterns, screen):
    """Decode exported bytes, including LSB-left rows and parallel attributes."""
    assert len(patterns) == 960 and len(screen) == 1920
    pixels = np.zeros((240, 320), dtype=np.uint8)
    for cell in range(960):
        attr, code = screen[cell * 2:cell * 2 + 2]
        assert attr & 0x88 == 0x88 and 0xa0 <= code <= 0xff
        fg, bg = attr & 7, (attr >> 4) & 7
        x, y = cell % 40 * 8, cell // 40 * 10
        for row, bits in enumerate(patterns[(code - 0xa0)*10:(code - 0xa0 + 1)*10]):
            for col in range(8):
                pixels[y + row, x + col] = fg if bits & (1 << col) else bg
    return pixels


def make_tiles(path):
    source = Image.open(path).convert("RGB")
    source = np.array(source.resize((320, 240), Image.Resampling.BOX), dtype=np.int32)
    distances = ((source[:, :, None, :] - PALETTE[COLORS]) ** 2).sum(axis=3)
    indexed = COLORS[distances.argmin(axis=2)]
    tiles, pairs = [], []
    target = np.zeros_like(indexed)
    for y in range(0, 240, 10):
        for x in range(0, 320, 8):
            tile = indexed[y:y+10, x:x+8]
            # Choose the pair minimizing error after global palette quantization.
            best = None
            for i, bg in enumerate(COLORS):
                for fg in COLORS[i:]:
                    errors = ((PALETTE[tile, None] - PALETTE[[bg, fg]]) ** 2).sum(axis=3)
                    mask = errors[:, :, 1] < errors[:, :, 0]
                    error = np.minimum(errors[:, :, 0], errors[:, :, 1]).sum()
                    if best is None or error < best[0]:
                        best = error, mask, int(bg), int(fg)
            _, mask, bg, fg = best
            packed = np.packbits(mask, axis=1, bitorder="little").tobytes()
            inverted = bytes(v ^ 255 for v in packed)
            if inverted < packed:
                packed, bg, fg = inverted, fg, bg
            tiles.append(packed)
            pairs.append((bg, fg))
            target[y:y+10, x:x+8] = np.where(mask, best[3], best[2])

    return tiles, pairs, target


def encode(tiles, pairs, dictionary):
    dictionary_masks = np.unpackbits(np.array([list(t) for t in dictionary], dtype=np.uint8),
                                     axis=1, bitorder="little")
    screen = bytearray()
    for tile, (bg, fg) in zip(tiles, pairs):
        mask = np.unpackbits(np.frombuffer(tile, dtype=np.uint8), bitorder="little")
        raw = np.count_nonzero(mask != dictionary_masks, axis=1)
        slot = int(np.minimum(raw, 80 - raw).argmin())
        if raw[slot] > 40:
            bg, fg = fg, bg
        screen.extend((0x88 | bg << 4 | fg, 0xa0 + slot))
    return bytes(screen)


def compress_delta(game_screen, intro_screen):
    """Encode changed row spans as row/column/run-count plus pair RLE."""
    output = bytearray()
    for row in range(24):
        game = [game_screen[(row * 40 + col) * 2:(row * 40 + col + 1) * 2]
                for col in range(40)]
        cells = [intro_screen[(row * 40 + col) * 2:(row * 40 + col + 1) * 2]
                 for col in range(40)]
        changed = [col for col in range(40) if cells[col] != game[col]]
        spans = []
        for col in changed:
            if spans and col - spans[-1][1] <= 3:
                spans[-1][1] = col
            else:
                spans.append([col, col])
        for first, last in spans:
            runs = []
            for cell in cells[first:last + 1]:
                if runs and runs[-1][1] == cell:
                    runs[-1][0] += 1
                else:
                    runs.append([1, cell])
            output.extend((row, first, len(runs)))
            for count, cell in runs:
                output.extend((count, cell[0], cell[1]))
    output.append(0xff)
    return bytes(output)


def main():
    game_tiles, game_pairs, target = make_tiles(OUT / "concept.png")
    intro_tiles, intro_pairs, intro_target = make_tiles(OUT / "intro-source.png")
    counts = Counter(game_tiles)
    counts.update(intro_tiles)
    unique = sorted(counts)
    masks = np.unpackbits(np.array([list(t) for t in unique], dtype=np.uint8),
                          axis=1, bitorder="little")
    # Hamming distance is color-independent; complement permits swapping FG/BG.
    raw = np.count_nonzero(masks[:, None] != masks[None, :], axis=2)
    distance = np.minimum(raw, 80 - raw)
    weights = np.array([counts[t] for t in unique])
    # Preserve every tile touching the three text bands so lettering is exact.
    title_patterns = {bytes(10)}
    title_patterns.update(tile for tile, pair in zip(intro_tiles, intro_pairs) if 7 in pair)
    protected = set(title_patterns)
    for row, first_col in ((9, 28), (11, 34)):
        protected.update(intro_tiles[row * 40 + first_col:row * 40 + first_col + 2])
    chosen = [unique.index(tile) for tile in sorted(protected) if tile in counts]
    assert len(chosen) <= 96, f"title needs {len(chosen)} protected patterns"
    nearest = distance[:, chosen].min(axis=1)
    while len(chosen) < min(96, len(unique)):
        improvement = (np.maximum(nearest[:, None] - distance, 0) * weights[:, None]).sum(axis=0)
        improvement[chosen] = -1
        pick = int(improvement.argmax())
        chosen.append(pick)
        nearest = np.minimum(nearest, distance[:, pick])
    dictionary = [unique[i] for i in chosen]
    screen = encode(game_tiles, game_pairs, dictionary)
    intro_screen = encode(intro_tiles, intro_pairs, dictionary)
    patterns = b"".join(dictionary).ljust(960, b"\0")
    (OUT / "patterns.bin").write_bytes(patterns)
    (OUT / "screen.bin").write_bytes(screen)
    (OUT / "intro-screen.bin").write_bytes(intro_screen)
    intro_rle = compress_delta(screen, intro_screen)
    assert len(intro_rle) <= 720, f"intro RLE is {len(intro_rle)} bytes"
    (OUT / "intro-rle.bin").write_bytes(intro_rle)
    # Round-trip from disk, not from the input image or pre-encoding masks.
    decoded = decode((OUT / "patterns.bin").read_bytes(), (OUT / "screen.bin").read_bytes())
    preview = Image.fromarray(PALETTE[decoded].astype(np.uint8))
    preview.save(OUT / "preview-native.png")
    preview.resize((1280, 960), Image.Resampling.NEAREST).save(OUT / "preview.png")
    intro_decoded = decode(patterns, intro_screen)
    intro_preview = Image.fromarray(PALETTE[intro_decoded].astype(np.uint8))
    intro_preview.save(OUT / "intro-preview-native.png")
    intro_preview.resize((1280, 960), Image.Resampling.NEAREST).save(
        OUT / "intro-preview.png")
    lines = ["; Generated by tools/convert_background.py. Data only, no loader.",
             "; Place in cartridge data banks, NOT in existing MB0 game code."]
    for label, data in (("plus_patterns", patterns), ("plus_screen", screen)):
        lines.append(label)
        for offset in range(0, len(data), 10 if label == "plus_patterns" else 16):
            size = 10 if label == "plus_patterns" else 16
            lines.append("\tdb " + ",".join(f"0{b:02x}h" for b in data[offset:offset+size]))
    (OUT / "background.inc").write_text("\n".join(lines) + "\n")
    report = {"width": 320, "height": 240, "columns": 40, "rows": 24,
              "tile_width": 8, "tile_height": 10, "unique_input_patterns": len(unique),
              "stored_patterns": len(dictionary), "pattern_bytes": len(patterns),
              "screen_bytes": len(screen), "service_row": "disabled; not included",
              "cell_order": "row-major: attribute (R6/TA), character (R7/TB)",
              "row_bits": "bit 0 is leftmost", "codes": "A0-FF, block DRCS set",
              "palette_rgb": PALETTE.tolist(),
              "intro_screen_bytes": len(intro_screen), "intro_rle_bytes": len(intro_rle),
              "protected_title_patterns": len(title_patterns),
              "protected_patterns_total": len(protected),
              "pixels_changed_by_pattern_budget": int(np.count_nonzero(decoded != target)),
              "intro_pixels_changed_by_pattern_budget":
                  int(np.count_nonzero(intro_decoded != intro_target)),
              "hardware_tested": False}
    (OUT / "conversion.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
