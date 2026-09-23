# BIRD HUNT

BIRD HUNT is a homebrew shooting game for the Philips Videopac G7000,
Magnavox Odyssey2, and Philips Videopac+ G7400. It is written in Intel 8048
assembly and distributed as a standard 8 KB cartridge image: `bird-hunt.bin`.

On a G7400, the title screen uses the Plus graphics layer to display a dawn
landscape with `AHNL66's`, `BIRD HUNT`, and `PRESS FIRE`. The game uses a
separate Plus landscape with a tree, shrubs, and grass. On a G7000 or an
unrecognized console, the original black Videopac title screen and raster-timed
blue-sky/green-grass playfield remain available.

## Gameplay

Move the crosshair with the joystick and press FIRE to shoot. Release FIRE
between shots. Each round contains three birds, shown one at a time on varying
flight paths, and five bullets. A hit makes the bird fall; a miss produces a
short white flash at the shot position. Five yellow bullet indicators appear in
the upper-right corner and disappear as ammunition is used.

Every round starts with a two-second pause, `tune_buzz`, and one additional
second of waiting. After later rounds, this sequence begins only after the round
sound has finished. The crosshair remains movable while waiting, but shooting
is disabled. FIRE used to leave the title screen or resume a paused game is
consumed as an input action and does not consume ammunition.

Pressing any console keyboard key pauses the game. FIRE resumes it without
firing a shot. Bird movement, round timers, and animation stop while paused.

## Scoring

The total score is updated after all three birds in a round have finished:

| Birds hit | Result |
| --- | --- |
| 0 | Halve the total, rounded down, and play `tune_alarm` |
| 1 | Add 1 point |
| 2 | Add 5 points |
| 3 | Add 10 points, plus 5 points for every remaining bullet |

A perfect round means three hits with two bullets remaining. The first perfect
round awards 20 points. Consecutive perfect rounds double that award: 40, 80,
160, 320, and so on. Any non-perfect round breaks the streak, so the next
perfect round starts again at 20 points. The 16-bit total saturates at 65,535.

Three hits play `tune_select`; a perfect round plays it three times. If a
zero-hit round halves the score to zero, the game ends after the alarm, waits
two seconds, and returns to the title screen.

## Building

Install the ASL Macro Assembler with 8048 support and its `p2bin` utility, then
run:

```sh
make rebuild
```

Explicit tool paths can be supplied when they are not on `PATH`:

```sh
make rebuild ASL=/path/to/asl P2BIN=/path/to/p2bin
```

`include/g7000.h` contains hardware and BIOS definitions by Soeren Gust. Its
original copyright and license text is preserved. This repository does not
include console BIOS images, commercial game ROMs, or assembler executables.

## Testing

The integration tests execute the compiled ROM in a libretro O2EM core with a
user-supplied legal BIOS. Apply `test-core.patch` to libretro-o2em revision
`679d6fec04963f6e70a7ec217e3d0ebb1fe472fc` to enable the additional
`birdhunt_test_*` timing counters:

```sh
git apply --ignore-whitespace /path/to/BIRD-HUNT/test-core.patch
```

The upstream emulator source uses CRLF line endings. Run the test matrix with:

```sh
python3 check_rom.py /path/to/o2em_libretro.dylib /path/to/bios bird-hunt.bin PAL
python3 check_rom.py /path/to/o2em_libretro.dylib /path/to/bios bird-hunt.bin NTSC
python3 check_rom.py /path/to/o2em_libretro.dylib /path/to/bios bird-hunt.bin PAL G7400
```

The G7000 tests cover initialization, aiming, shooting, miss flashes, falling
birds, random paths, ammunition, pause/resume, round timing, sound dispatch,
score arithmetic, perfect-round streaks, game over, PAL/NTSC timing, and VDC
write safety. The G7400 test additionally checks uploaded DRCS patterns, title
and gameplay screen memory, composed video output, first-start behavior, and
three reset/restart cycles. A user-supplied `g7400.bin` BIOS is required.

`tools/test_background.py` verifies the Plus asset format, shared pattern set,
title-delta round trip, and exact title/bird pixels. Physical G7400 validation is
still recommended because television overscan and analog color output are not
fully represented by the emulator.

## G7400 Architecture

The cartridge contains four 2 KB banks in file order 0, 1, 2, and 3. Bank 3
contains gameplay. Banks 0-2 contain identical loader code, 960 bytes of
background data each, and a 256-byte compressed title delta in their otherwise
free page-7 storage. Interrupts remain disabled while the loader changes banks.

G7400 detection checks two opcode signatures in the European G7400 BIOS at
`037Eh` and `0394h`. Unknown BIOS versions use the G7000-safe path. Jopac and
Odyssey3 BIOS variants have not been validated.

The loader uploads one shared set of 96 EF9340/41 DRCS patterns. It first loads
the gameplay screen and applies the compressed dawn-title differences. On FIRE,
it restores the gameplay screen without reloading the patterns. The ordinary
Videopac title characters are never created on the G7400 path. A bridge at
`07F8h` returns to either title setup or game setup after bank loading.

During gameplay, the Plus layer is exposed through the VDC blue and green
background colors. G7000 uses a timed horizon interrupt instead: scanlines
0-149 are blue and 150-249 are green in the 250-line O2EM frame.

The HUD uses quad 0 and character A for five bullet markers. Character B is
hidden and caches the last ammunition value. Extended game logic uses MB1 with
explicit MB0/MB1 transitions around BIOS and base-game calls. `game_active`
stores active state in bit 0, the perfect-round streak in bits 1-4, and keyboard
edge/pause state in bits 6-7.

## Rebuilding G7400 Assets

The approved concepts, deterministic source art, binary data, and previews are
stored in `assets/g7400`. Rebuild them with Pillow and NumPy:

```sh
python3 tools/create_intro.py
python3 tools/convert_background.py
python3 tools/test_background.py
make rebuild
```

See `assets/g7400/README.md` for the binary format and loader details, and
`REVIEW.md` for the technical review and historical corrections.
