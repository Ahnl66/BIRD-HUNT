"""Execute the real ROM/BIOS in libretro O2EM; no BIOS is bundled.

Usage: python3 check_rom.py CORE_DYLIB BIOS_DIRECTORY ROM [PAL|NTSC] [G7400]
The optional birdhunt_test_* exports come from the instrumented test core.
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
plus = len(sys.argv) > 5 and sys.argv[5] == "G7400"
buttons = set()
keyboard_keys = set()
audio_samples = []
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
                  b"o2em_bios": b"g7400.bin" if plus else b"o2rom.bin"}
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
    audio_samples.extend((left, right))


@C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
def audio_batch(data, frames):
    audio_samples.extend(C.cast(data, C.POINTER(C.c_int16))[:frames * 2])
    return frames


@C.CFUNCTYPE(None)
def input_poll():
    pass


@C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
def input_state(port, device, index, key):
    # Supply both physical joystick ports; the game's BIOS joystick number is 0.
    return int((device == 1 and key in buttons) or (device == 3 and key in keyboard_keys))


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
if "MENU" in sys.argv[5:]:
    pc.value = 0x408  # Menu-style entry, deliberately bypassing cartridge RESET.


def run(frames=1, held=()):
    global buttons
    buttons = set(held)
    for _ in range(frames):
        core.retro_run()
        if check_background:
            check_landscape()


def await_title_start():
    for _ in range(400 if plus else 20):
        run()
        if ram[0x23] == 5 and ram[0x26] == 5:
            return
    raise AssertionError("title did not enter the first-round countdown")


def check_landscape():
    if plus:
        return  # Plus memory and composite pixels are checked separately below.
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


def await_round(held=()):
    buzz = C.c_uint.in_dll(core, "birdhunt_buzz")
    initial_buzz = buzz.value
    previous_state = ram[0x26]
    counted = previous_state == 5
    post_buzz_frames = 0
    for _ in range(400):
        run(1, held)
        if ram[0x26] == 5:
            if previous_state != 5:
                duration = 100 if mode == "PAL" else 120
                assert duration - 2 <= ram[0x2c] <= duration
            counted = True
            assert buzz.value == initial_buzz, "buzz played before countdown ended"
            assert not (ram[0x3f] & 0x40), "countdown overlaps the end-of-round tune"
        if ram[0x26] == 6:
            post_buzz_frames += 1
            if previous_state != 6:
                duration = 50 if mode == "PAL" else 60
                assert duration - 2 <= ram[0x2c] <= duration
        if ram[0x26] == 0 and ram[0x2c] == 0:
            run(2, held)
            if counted:
                assert buzz.value == initial_buzz + 1, "missing or duplicate start signal"
                assert post_buzz_frames >= (48 if mode == "PAL" else 58)
            return
        previous_state = ram[0x26]
    raise AssertionError("next round did not start")


def snapshot():
    return {"pc": hex(pc.value), "ram": list(ram[0x20:0x2e]),
            "sprites": list(vdc[:16]), "control": hex(vdc[0xa0])}


def check_plus_picture():
    data, w, h, pitch = video_frame
    green = yellow = blue = 0
    for y in range(h):
        for x in range(w):
            p = struct.unpack_from("<H", data, y * pitch + x * 2)[0]
            r, g, b = p >> 11, ((p >> 5) & 63) // 2, p & 31
            green += g > r + 3 and g > b + 3
            yellow += r > b + 3 and g > b + 3
            blue += b > r + 3 and b > g + 3
    assert green > 10000 and yellow > 100 and blue > 20000, (green, yellow, blue)
    core.read_PB.restype = C.c_uint8
    assert (core.read_PB(2) << 4 | core.read_PB(3)) == 0xeb


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
    (rom_path.parent / (name + ("-g7400" if plus else "") + "-" + mode.lower() + ".png")).write_bytes(png)


run(400 if plus else 20)
print("Intro:", snapshot(), flush=True)
assert ram[0x3c] == int(plus), "wrong console detection"
if plus:
    def check_plus_data(screen_name):
        patterns = (rom_path.parent / "assets/g7400/patterns.bin").read_bytes()
        chars = (C.c_uint8 * 1920).in_dll(core, "dchars")
        reverse = lambda b: int(f"{b:08b}"[::-1], 2)
        assert bytes(chars[960:]) == bytes(map(reverse, patterns)), ("DRCS upload mismatch", list(ram[0x18:0x20]), hex(C.c_uint8.in_dll(core, "p1").value), [(i, chars[960+i], reverse(b)) for i, b in enumerate(patterns) if chars[960+i] != reverse(b)][:12])
        screen = (rom_path.parent / "assets/g7400" / screen_name).read_bytes()
        cells = (C.c_uint8 * (40 * 32 * 4)).in_dll(core, "vpp_mem")
        for row in range(24):
            for col in range(40):
                i = (col * 32 + row) * 4
                j = (row * 40 + col) * 2
                assert (cells[i+1], cells[i]) == tuple(screen[j:j+2]), (
                    "cell", screen_name, row, col, (cells[i+1], cells[i]),
                    tuple(screen[j:j+2]))
    check_plus_data("intro-screen.bin")
    C.c_uint.in_dll(core, "birdhunt_test_mb1_instructions").value = 0
if plus:
    assert vdc[0xa3] == 8, "G7400 title does not expose the Plus graphic"
    assert all(vdc[i] == 248 for i in range(0x10, 0x40, 4)), \
        "ordinary Videopac title is visible over the G7400 graphic"
    check_plus_picture()
else:
    assert vdc[0xa3] == 0, "plain-console intro background is not black"
    assert sum(vdc[i] != 248 for i in range(0x10, 0x40, 4)) == 9, \
        "plain-console title must have nine slots"
    assert vdc[0x10] == 112, "plain-console title not moved down one row"
screenshot("intro")
run(2, (0,))
await_title_start()
assert ram[0x23] == 5 and ram[0x26] == 5, "first round bypassed countdown"
assert (100 if mode == "PAL" else 120) - 10 <= ram[0x2c] <= (100 if mode == "PAL" else 120)
buzz_before = C.c_uint.in_dll(core, "birdhunt_buzz").value
start_x = ram[0x20]
assert list(ram[0x20:0x22]) == [96, 96], "cursor initialization failed"
run(4, (7,))
assert ram[0x20] > start_x, "cursor cannot move during the pre-round wait"
run(4, (6,))
run(2)
ram[0x20] = start_x
await_round((0,))  # Keep fire held right through the start signal.
assert ram[0x23] == 5 and ram[0x2b] == 0, "title/countdown fire consumed a shot"
assert C.c_uint.in_dll(core, "birdhunt_buzz").value == buzz_before + 1
run(2)
print("Started:", snapshot(), flush=True)
assert list(vdc[0x80:0x88]) == [24, 24, 0, 195, 195, 0, 24, 24], "corrupt cursor bitmap"
assert vdc[0xa3] == 8 and (vdc[0xa0] & 0x20), "blue foreground scene not enabled"
assert all(vdc[i] == 220 for i in range(0x10, 0x38, 4)), ("score label/digits missing", list(vdc[0x10:0x38]), list(ram[0x34:0x3c]))
assert vdc[0x38] == 16 and vdc[0x39] == 152, "fifth ammo icon missing"
assert vdc[0x3c] == 248, "ammo cache character became visible"
assert all(vdc[i] == 16 for i in range(0x40, 0x50, 4)), "ammo quad missing"
assert all(vdc[i] == 248 for i in range(0x50, 0x80, 4)), "stray quad objects"
assert list(ram[0x37:0x3c]) == [0] * 5
assert vdc[0x10] == 220
ram[0x34] = 32  # Avoid game-over in the old empty-ammo/round-flow scenario.
try:
    C.c_uint.in_dll(core, "birdhunt_test_monitor").value = 1
except ValueError:
    pass
screenshot("flying")
def check_ammo_icons(expected):
    pointers = [vdc[i] for i in (0x42, 0x46, 0x4a, 0x4e, 0x3a)]
    assert pointers == [168] * expected + [88] * (5 - expected), (expected, pointers)
    assert vdc[0x3e] == expected

check_ammo_icons(5)
if plus:
    check_plus_data("screen.bin")
    check_plus_picture()
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
run(2)
assert 182 <= ram[0x21] <= 184  # Input polling can straddle retro_run's return.
shot_position = (ram[0x20], ram[0x21])
audio_samples.clear()
run(2, (0,))
assert ram[0x23] == 4 and ram[0x26] == 0
check_ammo_icons(4)
assert ram[0x2b] > 0
assert tuple(ram[0x31:0x33]) == shot_position
run(2, (0, 7))
assert ram[0x20] > shot_position[0], "cursor failed to move while holding fire"
assert tuple(ram[0x31:0x33]) == shot_position, "miss patch follows cursor"
assert (vdc[9], vdc[8]) == shot_position and vdc[10] == 56
screenshot("miss")
run(10, (0,))
assert audio_samples and max(audio_samples) - min(audio_samples) > 100, "first-round shot is silent"
assert ram[0x23] == 4, "holding fire consumed additional ammunition"
assert ram[0x2b] == 0 and vdc[8] == 248, "miss patch did not disappear"
run()
for expected in (3, 2, 1, 0):
    run(2, (0,))
    assert ram[0x23] == expected
    check_ammo_icons(expected)
    run()
run(10)
run(2, (0,))
assert ram[0x23] == 0 and ram[0x2b] == 0, "sixth shot was allowed"
check_ammo_icons(0)
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
assert ram[0x26] in (4, 5), "round melody did not lead into countdown"
await_round()
assert ram[0x2a] == 3 and ram[0x23] == 5 and ram[0x26] == 0
assert ram[0x2c] == 0
run(2)
check_ammo_icons(5)

# Chase each of the three birds with joystick input, then shoot and await its fall.
for expected_left in (3, 2, 1):
    run()  # Finish any spawn routine straddling an emulator frame boundary.
    assert ram[0x2a] == expected_left
    assert ram[0x34] == 16 and ram[0x35] == 0, "score updated before round completion"
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
    run(3, (0,))
    assert ram[0x26] == 1 and ram[0x23] == ammo_before - 1, snapshot()
    assert abs(ram[0x24] - x_before) <= 1 and ram[0x25] > y_before, "hit bird did not fall vertically"
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
assert ram[0x33] == 3 and ram[0x34] == 36 and ram[0x35] == 0

# A held trigger across the round boundary must not auto-fire after refill.
run(95, (0,))
await_round((0,))
assert ram[0x2a] == 3 and ram[0x23] == 5
run()
run(2, (0,))
assert ram[0x23] == 4, "release/repress did not fire in next round"
run()

# Long run: path diversity, one bird only, sky bounds and stable raster/interrupts.
starts = set()
ram[0x34], ram[0x35] = 0x60, 0xea  # 60000, enough for all idle-round penalties.
directions = set()
heights = set()
rounds = 0
previous = ram[0x2a]
for _ in range(3400):
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
await_round()
for total, hits, expected in ((32, 0, 16), (0, 1, 1), (1, 2, 6), (6, 3, 26),
                              (17, 0, 8), (255, 1, 256),
                              (10000, 3, 10020), (65530, 3, 65535),
                              (65535, 1, 65535), (65535, 0, 32767)):
    ram[0x34], ram[0x35] = total & 255, total >> 8
    ram[0x33] = hits
    ram[0x23] = 2
    ram[0x2c] = 0
    ram[0x2a] = 1
    ram[0x26] = 1
    ram[0x25] = 212
    alarms_before = C.c_uint.in_dll(core, "birdhunt_alarm").value
    run(4)
    actual = ram[0x34] + 256 * ram[0x35]
    assert actual == expected, (total, hits, expected, actual)
    alarms_after = C.c_uint.in_dll(core, "birdhunt_alarm").value
    assert alarms_after - alarms_before == int(hits == 0), \
        ("wrong zero-hit alarm count", total, hits, alarms_before, alarms_after)
    assert list(ram[0x37:0x3c]) == [int(d) for d in f"{expected:05d}"]
    run(6)
    assert ram[0x36] == 0, "score digits not fully refreshed"
    assert all(vdc[i] == 220 for i in range(0x10, 0x38, 4))
    for index, digit in enumerate(f"{expected:05d}"):
        slot = 0x24 + 4 * index
        pointer = vdc[slot + 2] + ((vdc[slot + 3] & 1) << 8)
        assert pointer == (8 * int(digit) - 220 // 2) % 512, "wrong visible digit"
    screenshot("score")
    run(100)
    await_round()
    assert ram[0x34] + 256 * ram[0x35] == expected, "new round reset total"
    assert ram[0x33] == 0, "new round did not clear hit count"
print("Score: all awards, floor halving, zero-hit alarm, carry, saturation and display refresh passed")

# Bonus and exact one/three happy tune dispatches, including the no-ammo case.
for bullets in (0, 1, 2):
    ram[0x34], ram[0x35], ram[0x33], ram[0x23] = 0, 0, 3, bullets
    ram[0x2c], ram[0x2a], ram[0x26], ram[0x25] = 0, 1, 1, 212
    before = C.c_uint.in_dll(core, "birdhunt_happy").value
    run(2)
    await_round()
    assert ram[0x34] == 10 + 5 * bullets and ram[0x35] == 0
    assert C.c_uint.in_dll(core, "birdhunt_happy").value - before == (3 if bullets == 2 else 1)

# Keyboard presses freeze all gameplay counters; fire resumes without a shot.
for key in (ord('a'), ord('5'), 13):
    keyboard_keys.add(key)
    run(3)
    frozen = bytes(ram[0x20:0x2e])
    run(20, (7,))
    assert bytes(ram[0x20:0x2e]) == frozen, "game moves while paused"
    ammo_before = ram[0x23]
    run(3, (0,))
    assert not (ram[0x2e] & 0x80) and ram[0x23] == ammo_before
    run(3, (0,))
    assert not (ram[0x2e] & 0x80), "held keyboard key pauses again after resume"
    keyboard_keys.clear()
    run(2)
print("Bonus, one/triple happy tune and keyboard pause/resume passed")

# Consecutive perfect rounds double only the perfect-round award. Any other
# round breaks the streak, after which the next perfect round is worth 20 again.
ram[0x34], ram[0x35] = 0, 0
ram[0x2e] &= 0xe1
perfect_total = 0
for streak, award in enumerate((20, 40, 80, 160, 320), 1):
    ram[0x33], ram[0x23] = 3, 2
    ram[0x2c], ram[0x2a], ram[0x26], ram[0x25] = 0, 1, 1, 212
    before = C.c_uint.in_dll(core, "birdhunt_happy").value
    run(2)
    perfect_total += award
    assert ram[0x34] + 256 * ram[0x35] == perfect_total, (streak, award, snapshot())
    assert (ram[0x2e] & 0x1e) == 2 * streak, "perfect streak was not retained"
    await_round()
    assert C.c_uint.in_dll(core, "birdhunt_happy").value - before == 3

ram[0x33], ram[0x23] = 2, 3
ram[0x2c], ram[0x2a], ram[0x26], ram[0x25] = 0, 1, 1, 212
run(2)
perfect_total += 5
assert ram[0x34] + 256 * ram[0x35] == perfect_total
assert (ram[0x2e] & 0x1e) == 0, "non-perfect round did not break the streak"
await_round()

ram[0x33], ram[0x23] = 3, 2
ram[0x2c], ram[0x2a], ram[0x26], ram[0x25] = 0, 1, 1, 212
run(2)
assert ram[0x34] + 256 * ram[0x35] == perfect_total + 20
assert (ram[0x2e] & 0x1e) == 2, "perfect streak did not restart at 20"
await_round()

# The twelfth perfect award is 40960; later values exceed 16 bits and saturate.
ram[0x34], ram[0x35], ram[0x2e] = 0, 0, (ram[0x2e] & 0xe1) | 22
ram[0x33], ram[0x23] = 3, 2
ram[0x2c], ram[0x2a], ram[0x26], ram[0x25] = 0, 1, 1, 212
run(2)
assert ram[0x34] + 256 * ram[0x35] == 40960
assert (ram[0x2e] & 0x1e) == 24
await_round()
ram[0x34], ram[0x35] = 0, 0
ram[0x33], ram[0x23] = 3, 2
ram[0x2c], ram[0x2a], ram[0x26], ram[0x25] = 0, 1, 1, 212
run(2)
assert ram[0x34] + 256 * ram[0x35] == 65535, ("13th perfect", ram[0x34] + 256 * ram[0x35], ram[0x2e], snapshot())
assert (ram[0x2e] & 0x1e) == 26, "perfect streak cap changed"
await_round()
print("Consecutive perfect-run doubling, streak reset and saturation passed")

try:
    counts = {name: C.c_uint.in_dll(core, "birdhunt_test_" + name).value for name in
              ("unsafe_writes", "active_writes", "mb1_instructions", "last_on_clock",
               "unblanked_color", "grass_writes")}
    print("Hardware checks:", counts)
    assert counts["unsafe_writes"] == 0, "VDC object writes with foreground enabled"
    assert counts["active_writes"] == 0, "game VDC writes outside vertical blank"
    assert counts["mb1_instructions"] > 0, "ammo HUD was not executed"
    assert C.c_uint.in_dll(core, "birdhunt_test_bad_mb1").value == 0, "execution escaped the HUD code in MB1"
    assert counts["unblanked_color"] == 0, "grass color changed outside HBlank"
    if plus:
        assert counts["grass_writes"] == 0, "G7400 unexpectedly uses horizon IRQ"
    else:
        assert counts["grass_writes"] > 1000, "raster interrupt did not keep running"
except ValueError:
    print("Timing instrumentation not available in this O2EM build")
print("PASS:", mode, "intro, miss flash, 5-shot limit, three birds per round, random paths, hits, round sound, refill, held fire")
print("Final:", snapshot())
if not plus:
    print("Landscape: 60% blue / 40% green; observed horizon rows:", sorted(observed_horizons))
check_background = False
C.c_uint.in_dll(core, "birdhunt_test_monitor").value = 0
# Both zero and one halve to zero. Wait must be 100 PAL / 120 NTSC frames.
for total in (0, 1):
    ram[0x34], ram[0x35], ram[0x33] = total, 0, 0
    ram[0x2c], ram[0x2a], ram[0x26], ram[0x25] = 0, 1, 1, 212
    alarms = C.c_uint.in_dll(core, "birdhunt_alarm").value
    for _ in range(5):
        run()
        if C.c_uint.in_dll(core, "birdhunt_alarm").value > alarms:
            break
    assert ram[0x26] == 3 and ram[0x34] == 0
    assert C.c_uint.in_dll(core, "birdhunt_alarm").value == alarms + 1
    delay = ram[0x2c]
    assert (100 if mode == "PAL" else 120) - 2 <= delay <= (100 if mode == "PAL" else 120), delay
    run(delay - 3)
    assert ram[0x26] == 3, "game over ended too early"
    run(400 if plus else 20)
    assert ram[0x2e] == 0, "game over did not return to title"
    if plus:
        assert vdc[0xa3] == 8 and vdc[0x10] == 248
        check_plus_data("intro-screen.bin")
    else:
        assert vdc[0x10] == 112
    run(2, (0,))
    await_title_start()
    await_round()
    assert ram[0x23] == 5 and ram[0x34] == 0 and ram[0x35] == 0
print("Game over: alarm, two-second delay, title and fresh restart passed")
if plus:
    C.c_uint.in_dll(core, "birdhunt_test_monitor").value = 0
    for _ in range(3):
        core.retro_reset()
        run(400)
        assert ram[0x3c] == 1 and ram[0x2e] == 0, "reset did not return to intro"
        check_plus_data("intro-screen.bin")
        run(2, (0,))
        await_title_start()
        await_round()
        check_plus_data("screen.bin")
        before = tuple(ram[0x24:0x26])
        run(20)
        assert tuple(ram[0x24:0x26]) != before, "frozen after reset"
        check_plus_picture()
        audio_samples.clear()
        run(12, (0,))
        assert max(audio_samples) - min(audio_samples) > 100, "first shot after reset is silent"
    print("G7400: pattern/screen byte checks and three reset/restart cycles passed")
core.retro_unload_game()
core.retro_deinit()
