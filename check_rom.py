"""Execute the real ROM/BIOS in libretro O2EM; no BIOS is bundled.

Usage: python3 check_rom.py CORE_DYLIB BIOS_DIRECTORY ROM [PAL|NTSC]
The optional artgame_test_* exports come from the instrumented test core.
"""
import ctypes as C
from pathlib import Path
import struct
import sys
import zlib

core = C.CDLL(sys.argv[1])
bios_dir = str(Path(sys.argv[2]).resolve()).encode()
rom_path = Path(sys.argv[3]).resolve()
mode = sys.argv[4] if len(sys.argv) > 4 else "PAL"
buttons = set()
video_frame = None
check_background = False
observed_horizons = set()


class Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


class Game(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p),
                ("size", C.c_size_t), ("meta", C.c_char_p)]


@C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
def environment(cmd, data):
    if cmd == 9:  # GET_SYSTEM_DIRECTORY
        C.cast(data, C.POINTER(C.c_char_p))[0] = bios_dir
        return True
    if cmd == 10:  # SET_PIXEL_FORMAT: RGB565
        return C.cast(data, C.POINTER(C.c_int))[0] == 2
    if cmd == 15:  # GET_VARIABLE
        var = C.cast(data, C.POINTER(Variable)).contents
        values = {b"o2em_region": b"PAL" if mode == "PAL" else b"NTSC",
                  b"o2em_bios": b"o2rom.bin"}
        if var.key in values:
            var.value = values[var.key]
            return True
    return False


@C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
def video(data, width, height, pitch):
    global video_frame
    if data:
        video_frame = (C.string_at(data, pitch * height), width, height, pitch)


@C.CFUNCTYPE(None, C.c_int16, C.c_int16)
def audio(left, right):
    pass


@C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
def audio_batch(data, frames):
    return frames


@C.CFUNCTYPE(None)
def input_poll():
    pass


@C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
def input_state(port, device, index, key):
    # Supply both physical joystick ports; the game's BIOS joystick number is 0.
    return int(device == 1 and key in buttons)


for name, callback in (("environment", environment), ("video_refresh", video),
                       ("audio_sample", audio), ("audio_sample_batch", audio_batch),
                       ("input_poll", input_poll), ("input_state", input_state)):
    getattr(core, "retro_set_" + name)(callback)
core.retro_init()
payload = C.create_string_buffer(rom_path.read_bytes())
game = Game(str(rom_path).encode(), C.cast(payload, C.c_void_p), len(payload) - 1, None)
core.retro_load_game.restype = C.c_bool
assert core.retro_load_game(C.byref(game)), "ROM/BIOS load failed"
ram = C.POINTER(C.c_uint8).in_dll(core, "intRAM")
vdc = (C.c_uint8 * 256).in_dll(core, "VDCwrite")
pc = C.c_uint16.in_dll(core, "pc")


def run(frames=1, held=()):
    global buttons
    buttons = set(held)
    for _ in range(frames):
        core.retro_run()
        if check_background:
            check_landscape()


def check_landscape():
    data, w, h, pitch = video_frame
    # Sample a sprite-free column of the actual RGB565 video output.
    column = [struct.unpack_from("<H", data, y * pitch + 4)[0] for y in range(h)]
    sky = column[10]
    grass = column[200]
    assert (sky & 31) > ((sky >> 5) & 63), "upper field is not blue"
    assert ((grass >> 5) & 63) > (grass & 31), "lower field is not green"
    transitions = [y for y in range(1, 240) if column[y] != column[y-1]]
    assert len(transitions) == 1, ("unexpected background bands", transitions)
    horizon = transitions[0]
    observed_horizons.add(horizon)
    assert horizon == round(h * 0.6), ("horizon is not at 60%", horizon, h)


def snapshot():
    return {"pc": hex(pc.value), "ram": list(ram[0x20:0x2e]),
            "sprites": list(vdc[:16]), "control": hex(vdc[0xa0])}


def screenshot(name):
    data, w, h, pitch = video_frame
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            p = struct.unpack_from("<H", data, y * pitch + x * 2)[0]
            rows.extend(((p >> 11) * 255 // 31, ((p >> 5) & 63) * 255 // 63,
                         (p & 31) * 255 // 31))

    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body)))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    (rom_path.parent / (name + "-" + mode.lower() + ".png")).write_bytes(png)


run(20)
print("Intro:", snapshot(), flush=True)
assert vdc[0xa3] == 0, "intro background is not black"
assert sum(vdc[i] != 248 for i in range(0x10, 0x40, 4)) == 9, "title must have nine slots"
screenshot("intro")
run(2, (0,))
run(7)
print("Started:", snapshot(), flush=True)
assert list(ram[0x20:0x22]) == [96, 96], "cursor initialization failed"
assert list(vdc[0x80:0x88]) == [24, 24, 0, 195, 195, 0, 24, 24], "corrupt cursor bitmap"
assert vdc[0xa3] == 8 and (vdc[0xa0] & 0x20), "blue foreground scene not enabled"
assert all(vdc[i] == 220 for i in range(0x10, 0x38, 4)), ("score label/digits missing", list(vdc[0x10:0x38]), list(ram[0x34:0x3c]))
assert all(vdc[i] == 248 for i in range(0x38, 0x80, 4)), "stray text/quad objects"
assert list(ram[0x37:0x3c]) == [0] * 5
try:
    C.c_uint.in_dll(core, "artgame_test_monitor").value = 1
except ValueError:
    pass
screenshot("flying")
check_landscape()
check_background = True
# A single flying bird uses slot 1, the miss flash slot 2, slot 3 stays hidden.
assert ram[0x23] == 5 and ram[0x2a] == 3
assert vdc[12] == 248 and vdc[8] == 248
assert ram[0x26] == 0
initial_y = ram[0x25]
run(10)
assert ram[0x25] != initial_y, "bird path stayed on one horizontal line"

# Aim in the grass, well below every flying trajectory.
run(44, (5,))
assert ram[0x21] == 184
shot_position = (ram[0x20], ram[0x21])
run(2, (0,))
assert ram[0x23] == 4 and ram[0x26] == 0
assert ram[0x2b] > 0
assert tuple(ram[0x31:0x33]) == shot_position
run(2, (0, 7))
assert ram[0x20] > shot_position[0], "cursor failed to move while holding fire"
assert tuple(ram[0x31:0x33]) == shot_position, "miss patch follows cursor"
assert (vdc[9], vdc[8]) == shot_position and vdc[10] == 56
screenshot("miss")
run(10, (0,))
assert ram[0x23] == 4, "holding fire consumed additional ammunition"
assert ram[0x2b] == 0 and vdc[8] == 248, "miss patch did not disappear"
run()
for expected in (3, 2, 1, 0):
    run(2, (0,))
    assert ram[0x23] == expected
    run()
run(10)
run(2, (0,))
assert ram[0x23] == 0 and ram[0x2b] == 0, "sixth shot was allowed"
run()

# Exactly three passages per round; empty ammo must not stop bird motion.
sequence = [ram[0x2a]]
for _ in range(600):
    before = ram[0x2a]
    run()
    if ram[0x2a] != before:
        sequence.append(ram[0x2a])
    if ram[0x2c]:
        break
else:
    raise AssertionError("round did not finish")
assert sequence == [3, 2, 1, 0], ("not three sequential birds", sequence)
assert ram[0x26] == 2 and ram[0x23] == 0
pause_left = ram[0x2c]
run(2)
assert vdc[4] == 248, "bird visible during round pause"
assert ram[0x3f] & 0x40, "round transition did not start the BIOS sound"
run(pause_left - 2)
assert ram[0x2a] == 3 and ram[0x23] == 5 and ram[0x26] == 0
assert ram[0x2c] == 0

# Chase each of the three birds with joystick input, then shoot and await its fall.
for expected_left in (3, 2, 1):
    assert ram[0x2a] == expected_left
    assert ram[0x34] == 0 and ram[0x35] == 0, "score updated before round completion"
    for _ in range(140):
        dx = ram[0x24] - ram[0x20]
        dy = ram[0x25] - ram[0x21]
        if 0 <= ram[0x20] + 4 - ram[0x24] < 8 and 0 <= ram[0x21] + 8 - ram[0x25] < 16:
            break
        keys = []
        if abs(dx) >= 2:
            keys.append(7 if dx > 0 else 6)
        if abs(dy) >= 2:
            keys.append(5 if dy > 0 else 4)
        run(1, keys)
        assert ram[0x2a] == expected_left, "bird escaped before the test could aim"
    else:
        raise AssertionError("could not aim")
    ammo_before = ram[0x23]
    x_before, y_before = ram[0x24], ram[0x25]
    run(2, (0,))
    assert ram[0x26] == 1 and ram[0x23] == ammo_before - 1
    assert ram[0x24] == x_before and ram[0x25] > y_before, "hit bird did not fall vertically"
    assert ram[0x2b] == 0 and vdc[6] == 8, "hit showed a miss flash or no red bird"
    run(3, (0,))  # Let the captured video frame catch up with the VDC register writes.
    screenshot("falling")
    for _ in range(60):
        run()
        if ram[0x2a] != expected_left:
            break
    assert ram[0x2a] == expected_left - 1, "bird counted more than once"
    assert ram[0x23] == ammo_before - 1, "ammo refilled before round ended"
run(2)  # Decimal conversion may straddle the emulator's frame-return boundary.
assert ram[0x2c] > 0 and ram[0x23] == 2, snapshot()
assert ram[0x33] == 3 and ram[0x34] == 10 and ram[0x35] == 0

# A held trigger across the round boundary must not auto-fire after refill.
run(35, (0,))
assert ram[0x2a] == 3 and ram[0x23] == 5
run()
run(2, (0,))
assert ram[0x23] == 4, "release/repress did not fire in next round"
run()

# Long run: path diversity, one bird only, sky bounds and stable raster/interrupts.
starts = set()
directions = set()
heights = set()
rounds = 0
previous = ram[0x2a]
for _ in range(2400):
    run()
    current = ram[0x2a]
    assert vdc[12] == 248, "unexpected additional bird"
    if current != previous and current:
        starts.add((ram[0x24], ram[0x25], ram[0x27]))
        directions.add(ram[0x27])
        if current == 3:
            rounds += 1
            assert ram[0x23] == 5
    if ram[0x26] == 0:
        assert 32 <= ram[0x25] <= 128, "flying bird left the sky"
        assert 7 <= ram[0x24] <= 153, snapshot()  # Includes the exit step before respawn.
        heights.add(ram[0x25])
    previous = current
assert rounds >= 4 and len(starts) >= 6 and len(heights) > 20
assert directions == {1, 255}, "birds do not start from both sides"
print("Rounds:", rounds, "distinct starts:", len(starts), "flight heights:", len(heights))

# Boundary fixtures drive the actual ROM round-completion code, not a Python model.
for total, hits, expected in ((0, 0, 0), (0, 1, 1), (1, 2, 6), (6, 3, 16),
                              (17, 0, 8), (1, 0, 0), (255, 1, 256),
                              (10000, 3, 10010), (65530, 3, 65535),
                              (65535, 1, 65535), (65535, 0, 32767)):
    ram[0x34], ram[0x35] = total & 255, total >> 8
    ram[0x33] = hits
    ram[0x2c] = 0
    ram[0x2a] = 1
    ram[0x26] = 1
    ram[0x25] = 212
    run(2)
    actual = ram[0x34] + 256 * ram[0x35]
    assert actual == expected, (total, hits, expected, actual)
    assert list(ram[0x37:0x3c]) == [int(d) for d in f"{expected:05d}"]
    run(6)
    assert ram[0x36] == 0, "score digits not fully refreshed"
    assert all(vdc[i] == 220 for i in range(0x10, 0x38, 4))
    for index, digit in enumerate(f"{expected:05d}"):
        slot = 0x24 + 4 * index
        pointer = vdc[slot + 2] + ((vdc[slot + 3] & 1) << 8)
        assert pointer == (8 * int(digit) - 220 // 2) % 512, "wrong visible digit"
    screenshot("score")
    run(35)
    assert ram[0x34] + 256 * ram[0x35] == expected, "new round reset total"
    assert ram[0x33] == 0, "new round did not clear hit count"
print("Score: all awards, floor halving, carry, saturation and display refresh passed")

try:
    counts = {name: C.c_uint.in_dll(core, "artgame_test_" + name).value for name in
              ("unsafe_writes", "active_writes", "mb1_instructions", "last_on_clock",
               "unblanked_color", "grass_writes")}
    print("Hardware checks:", counts)
    assert counts["unsafe_writes"] == 0, "VDC object writes with foreground enabled"
    assert counts["active_writes"] == 0, "game VDC writes outside vertical blank"
    assert counts["mb1_instructions"] == 0, "execution escaped MB0"
    assert counts["unblanked_color"] == 0, "grass color changed outside HBlank"
    assert counts["grass_writes"] > 1000, "raster interrupt did not keep running"
except ValueError:
    print("Timing instrumentation not available in this O2EM build")
print("PASS:", mode, "intro, miss flash, 5-shot limit, three birds per round, random paths, hits, round sound, refill, held fire")
print("Final:", snapshot())
print("Landscape: 60% blue / 40% green; observed horizon rows:", sorted(observed_horizons))
core.retro_unload_game()
core.retro_deinit()
