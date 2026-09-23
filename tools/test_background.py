"""Format and round-trip checks; does not replace testing on a G7400."""
import unittest

import numpy as np
from PIL import Image

from convert_background import OUT, PALETTE, decode


class BackgroundTests(unittest.TestCase):
    def test_bit_order_and_attributes(self):
        patterns = bytearray(960)
        patterns[0] = 1
        patterns[9] = 128
        pixels = decode(patterns, bytes([0xca, 0xa0]) * 960)
        self.assertEqual(pixels[0, 0], 2)
        self.assertEqual(pixels[0, 7], 4)
        self.assertEqual(pixels[9, 7], 2)
        self.assertEqual(pixels[9, 0], 4)

    def test_files_and_preview(self):
        patterns = (OUT / "patterns.bin").read_bytes()
        screen = (OUT / "screen.bin").read_bytes()
        pixels = decode(patterns, screen)
        expected = PALETTE[pixels].astype(np.uint8)
        np.testing.assert_array_equal(np.array(Image.open(OUT / "preview-native.png")), expected)
        self.assertLessEqual(len(set(screen[1::2])), 96)
        self.assertEqual(set(np.unique(pixels)), {0, 2, 3, 4})

        intro = (OUT / "intro-screen.bin").read_bytes()
        intro_pixels = decode(patterns, intro)
        intro_expected = PALETTE[intro_pixels].astype(np.uint8)
        np.testing.assert_array_equal(
            np.array(Image.open(OUT / "intro-preview-native.png")), intro_expected)
        self.assertGreater(np.count_nonzero(intro_pixels == 7), 500)
        source = np.array(Image.open(OUT / "intro-source.png").convert("RGB"))
        np.testing.assert_array_equal(intro_pixels == 7, np.all(source == 255, axis=2))
        for x, y in ((224, 90), (272, 110)):
            np.testing.assert_array_equal(intro_expected[y:y + 10, x:x + 16],
                                          source[y:y + 10, x:x + 16])
        self.assertLessEqual((OUT / "intro-rle.bin").stat().st_size, 720)

    def test_intro_delta_round_trip(self):
        screen = bytearray((OUT / "screen.bin").read_bytes())
        encoded = iter((OUT / "intro-rle.bin").read_bytes())
        for row in encoded:
            if row == 0xff:
                break
            column, run_count = next(encoded), next(encoded)
            for _ in range(run_count):
                count, attr, code = next(encoded), next(encoded), next(encoded)
                for _ in range(count):
                    offset = (row * 40 + column) * 2
                    screen[offset:offset + 2] = bytes((attr, code))
                    column += 1
        self.assertEqual(bytes(screen), (OUT / "intro-screen.bin").read_bytes())

    def test_assembly_matches_binary(self):
        data = bytearray()
        for line in (OUT / "background.inc").read_text().splitlines():
            if line.startswith("\tdb "):
                data.extend(int(v[:-1], 16) for v in line[4:].split(","))
        self.assertEqual(data, (OUT / "patterns.bin").read_bytes() + (OUT / "screen.bin").read_bytes())


if __name__ == "__main__":
    unittest.main()
