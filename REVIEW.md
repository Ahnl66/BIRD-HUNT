# BIRD HUNT Technical Review

## Current Status

BIRD HUNT is an 8 KB, four-bank cartridge for the Videopac G7000/Odyssey2 and
G7400. The current build assembles without errors or warnings and is exercised
by PAL, NTSC, and G7400 integration tests using the real O2EM CPU, VDC, BIOS,
sound, and Plus-video paths.

The game includes three birds per round, five bullets, miss flashes, falling
birds, random flight paths, score and ammunition displays, pause/resume, round
transitions, game over, consecutive perfect-round bonuses, a G7400 landscape,
and a dedicated G7400 dawn title screen.

## Corrected Core Problems

### Memory-bank state after calls

Early code entered MB1 to fetch graphics data but returned without restoring the
memory-bank latch. A later BIOS call then jumped into the wrong cartridge page.
Core code and BIOS calls now use explicit MB0/MB1 transitions. The assembler and
instrumented emulator both enforce the valid MB1 regions.

### Screen initialization and interrupt chaining

Sprites were previously positioned after video output had already been enabled,
and an incomplete VSYNC hook skipped parts of the BIOS frame handling. The
cartridge now uses the standard vectors at `0400h` through `040Ah`, initializes
all sprites, characters, quads, grid state, and RAM before display enable, and
chains through the complete BIOS VSYNC routine.

### Hit detection and coordinates

The crosshair originally used an inconsistent vertical center and mixed full
VDC pixels with the half-pixel position bit. Hit testing now uses the visual
center of the 8-row sprite, keeps X in whole VDC pixels, and ignores birds that
are already falling.

### Input latching

FIRE is edge-latched so holding the button cannot consume multiple bullets.
Leaving the title screen, crossing a round boundary, and resuming from pause all
consume the current press without firing. A held keyboard key cannot immediately
pause the game again after resume.

### Sound initialization

`tune_shoot` changes sound control but does not initialize the shift-register
waveform. The HUD initialization now seeds a nonzero waveform before the first
shot while keeping output muted. Tests verify audible first shots after cold
start and repeated resets.

## Video and Timing

Gameplay input and state updates occur before `waitvsync`. During VBlank the
game selects the VDC, disables foreground output, writes object positions,
colors, and bitmaps, then enables output again. Instrumented tests report no
object writes while foreground is active and no gameplay object writes outside
VBlank.

On G7000, a timer interrupt uses the VDC beam counter and T1 HBlank/VBlank input
to switch from blue sky to green grass at scanline 150. The interrupt preserves
A, P1, and BIOS sound registers. On G7400, this raster interrupt is skipped and
the EF9340/41 Plus layer supplies the landscape.

## G7400 Loader

The European G7400 BIOS is detected before any Plus-only call. Banks 0-2 share
the same loader code. Bank 2 stores 96 DRCS patterns; banks 1 and 0 store the
upper and lower screen halves. The title is a 256-byte row/column/run encoded
difference layer split across free page-7 storage.

Cold start uploads patterns and gameplay cells, then applies the dawn title.
The title includes `AHNL66's`, `BIRD HUNT`, `PRESS FIRE`, a sun, and two protected
bird silhouettes. FIRE hides the layer while the loader restores only the
gameplay cells. The return bridge selects either title initialization or game
initialization without re-entering the public cartridge reset vector.

The two public entry points, reset at `0400h` and menu launch at `0408h`, both
perform full initialization. Tests verify title graphics and sound after cold
start, menu start, game over, and three consecutive resets.

## Round and Score Logic

Each round contains three sequential birds and five bullets. A miss displays a
fixed white patch for eight frames. A nonzero LFSR selects starting side, height,
and vertical turns while keeping flying birds above the horizon.

Round scoring is applied once after the third bird:

- Zero hits halves the total, rounds down, and plays `tune_alarm` once.
- One hit adds 1 point.
- Two hits add 5 points.
- Three hits add 10 points plus 5 per remaining bullet.
- Three hits with two bullets remaining form a perfect round.

Consecutive perfect rounds award 20, 40, 80, 160 points, and so on. A
non-perfect round clears the streak. The total saturates at 65,535. If a
zero-hit halving reaches zero, the same single alarm leads into a two-second
game-over delay and a fresh title screen.

## Verification

`check_rom.py` runs the compiled cartridge through O2EM and verifies:

- PAL and NTSC title, gameplay, horizon, and game-over timing.
- G7400 DRCS bytes, title cells, gameplay cells, composite colors, and resets.
- Crosshair movement during round waits and correct FIRE consumption.
- Five-shot limits, held-trigger behavior, miss position and lifetime.
- Exactly three sequential birds, both starting sides, varied paths, and falls.
- Round sounds, start buzz, happy-sound repetition, and zero-hit alarms.
- Score halving, odd-value rounding, carry, saturation, visible digits, and
  perfect-round doubling/reset behavior.
- Keyboard pause/resume and frozen gameplay state.
- Safe VDC write windows, MB1 execution regions, and HBlank-only grass changes.

`tools/test_background.py` additionally verifies binary sizes, bit order,
attributes, decoded previews, exact white title pixels, exact bird silhouettes,
and reconstruction of `intro-screen.bin` from `screen.bin` plus `intro-rle.bin`.

The ROM has not yet been revalidated on physical G7400 hardware after the final
title-screen revision. Emulator output cannot fully model television overscan,
analog color levels, or every regional BIOS variant.

## References

- Soeren Gust, G7000 programming manual and BIOS definitions.
- [libretro O2EM](https://github.com/libretro/libretro-o2em), revision
  `679d6fec04963f6e70a7ec217e3d0ebb1fe472fc`.
- [MAME Odyssey2 driver](https://github.com/mamedev/mame/blob/master/src/mame/philips/odyssey2.cpp).
- [MAME Intel 8244/8245 implementation](https://github.com/mamedev/mame/blob/master/src/devices/video/i8244.cpp).
- [MAME EF9340/41 implementation](https://github.com/mamedev/mame/blob/master/src/devices/video/ef9340_1.cpp).
