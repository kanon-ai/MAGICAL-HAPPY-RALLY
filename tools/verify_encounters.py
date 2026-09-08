"""Native v0.4 traffic/UFO verification, isolated from the preserved v0.3 tests.

Scenario tests explicitly seed RAM. The final reset-to-full-lap test uses only
keyboard input and reads state; native screenshots/GIF are never PC-rendered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path

from PIL import Image

from verify_drive import NativeChecks, SIZES, SIGNED
from check_encounter_scope import preservation_checks
from compare_speed_car import sprite_tables, indexed_sprite

ROOT = Path(__file__).resolve().parents[1]


def portable_report(value):
    """Keep native results intact without publishing a local checkout path."""
    if isinstance(value, dict):
        return {key: portable_report(item) for key, item in value.items()}
    if isinstance(value, list):
        return [portable_report(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(ROOT), ".").replace(ROOT.as_posix(), ".")
    return value

FIELDS = dict(SIZES, passes=2, hits=2, ufo_dodges=2, ufo_catches=2,
              ufo_state=1, ufo_timer=1, ufo_lane=1, ufo_lap=2,
              ufo_caught=1, recovery_timer=1, lift_timer=1, event_tick=2)
for _index in range(3):
    FIELDS[f"traffic_z{_index}"] = 2
    FIELDS[f"traffic_lane{_index}"] = 1
    FIELDS[f"traffic_tag{_index}"] = 1
SIGNED_FIELDS = SIGNED | {"ufo_lane", "traffic_lane0", "traffic_lane1", "traffic_lane2"}
EVENT_FIELDS = tuple(name for name in FIELDS if name not in SIZES)
TIMER_FIELDS = {"lap_current_tenths": 4, "lap_last_tenths": 4, "lap_best_tenths": 4,
                "lap_last_valid": 1, "lap_best_valid": 1}
FIELDS.update(TIMER_FIELDS)
TEST_ONLY_FIELDS = {"lap_tick_fraction": 4, "lap_previous_laps": 2, "lap_previous_mode": 1}


def dense_scenery_phase(player_x: int) -> int:
    """Read only the preserved eight scenery records, not the new projection tail."""
    tables = sprite_tables((ROOT / "src/assets.h").read_text() + (ROOT / "src/scenery.h").read_text())
    names = ("grand_pines", "rocks", "crags", "bushes")
    course = (ROOT / "assets/course.bin").read_bytes()
    costs = []
    for phase in range(1024):
        pixels = 0
        for offset in range(phase * 256 + 128, phase * 256 + 192, 8):
            p = course[offset:offset + 8]
            if not p[7]:
                continue
            x = int.from_bytes(p[:2], "little", signed=True)
            y = int.from_bytes(p[2:4], "little", signed=True)
            shift = abs(player_x) * (p[7] >> 1) // 64
            x -= -shift if player_x < 0 else shift
            _, _, w, h = tables[names[p[5]]][p[4]]
            left = x - w // 2
            pixels += max(0, min(256, left+w)-max(0, left)) * max(0, min(y, p[6], 186)-max(0, y-h))
        costs.append(pixels)
    return max(range(1024), key=costs.__getitem__)


class EncounterChecks(NativeChecks):
    def __init__(self, port: int, frames: int, input_lap: bool = True):
        # Do not weaken or monkey-patch the old verifier's v0.3-only guard.
        self.url = f"http://127.0.0.1:{port}"
        self.frames, self.input_lap, self.lap_finished = frames, input_lap, False
        self.symbols = json.loads((ROOT / "work/build/symbols.json").read_text())
        self.manifest = json.loads((ROOT / "outputs/build-manifest.json").read_text())
        if self.manifest["version"] != "0.4":
            raise ValueError("This verifier exclusively requires the v0.4 candidate.")
        self.release = "v0.4"
        self.output_root = ROOT / "outputs"
        self.out = self.output_root / self.release
        self.report_path = self.output_root / "verification-v0.4.json"
        self.baseline = self.output_root / "baseline-v0.3"
        self.shots = self.out / "screenshots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.results, self.breakpoint = [], None
        self.report = {
            "rom": self.manifest, "machine": "Panasonic_FS-A1ST", "extension": "gfx9000",
            "physical_hardware_tested": False, "browser_mock_used": False,
            "full_course_input_only_playthrough": False,
            "baseline": "outputs/baseline-v0.3",
            "scenario_seeding": "All explicitly named scenario/frame/visual tests seed game RAM. The final full lap starts from hardware reset and sends keyboard input only; event counters are never written during that lap.",
            "results": self.results,
        }

    def cmd(self, script: str) -> str:
        # Reuse the inherited machine/ROM checks without assuming the old title.
        script = script.replace("*ALPINE_DRIVE*", "*" + Path(self.manifest["file"]).stem + "*")
        return super().cmd(script)

    def address(self, name: str) -> int:
        for array, stride in (("traffic_z", 2), ("traffic_lane", 1), ("traffic_tag", 1)):
            if name.startswith(array) and name[-1:].isdigit():
                return int(self.symbols["_" + array]) + int(name[-1]) * stride
        return int(self.symbols["_" + name])

    def read_expr(self, name: str) -> str:
        address = self.address(name)
        size = FIELDS.get(name, TEST_ONLY_FIELDS.get(name))
        expr = "+".join(f"{256**i}*[debug read memory {address+i}]" for i in range(size))
        return f"[expr {{{expr}}}]"

    def state(self, *names: str) -> dict[str, int]:
        names = names or tuple(FIELDS)
        values = map(int, self.cmd("list " + " ".join(self.read_expr(n) for n in names)).split())
        state = dict(zip(names, values))
        for name in names:
            if name in SIGNED_FIELDS and state[name] >= 1 << (FIELDS[name] * 8 - 1):
                state[name] -= 1 << (FIELDS[name] * 8)
        return state

    def seed(self, **values: int) -> None:
        commands = []
        for name, value in values.items():
            for i in range(FIELDS.get(name, TEST_ONLY_FIELDS.get(name))):
                commands.append(f"debug write memory {self.address(name) + i} {(value >> (8 * i)) & 255}")
        self.cmd("set pause on; " + "; ".join(commands) + "; set pause off")

    def seed_quiet(self, **values: int) -> None:
        defaults = dict(mode=1, distance=0, distance_fraction=0, speed=128, player_x=0,
                        laps=0, recovery_timer=0, lift_timer=0, event_tick=0,
                        ufo_state=0, ufo_timer=0, ufo_lane=1, ufo_lap=65535, ufo_caught=0,
                        passes=0, hits=0, ufo_dodges=0, ufo_catches=0)
        for i in range(3):
            defaults.update({f"traffic_z{i}": 2500 + i * 400,
                             f"traffic_lane{i}": 1 if i != 1 else -1, f"traffic_tag{i}": 0})
        defaults.update(values)
        self.seed(**defaults)

    def begin_frames(self) -> None:
        if self.breakpoint:
            raise RuntimeError("Frame hook already active")
        self.breakpoint = self.cmd(f"debug set_bp {self.address('frame_done')} {{}} {{debug break}}")
        self.until(lambda: self.cmd("debug breaked") == "1")

    def next_frame(self, count: int = 1) -> None:
        for _ in range(count):
            self.cmd("debug cont")
            self.until(lambda: self.cmd("debug breaked") == "1")

    def end_frames(self) -> None:
        if self.breakpoint:
            self.cmd(f"debug remove_bp {self.breakpoint}; debug cont")
            self.breakpoint = None

    def reset_title(self) -> None:
        self.release_keys()
        self.end_frames()
        self.cmd("reset; set pause off; set speed 100")
        self.advance(6.0)
        self.until(lambda: self.read("ready") == 0xA5 and self.read("mode") == 0, 45)
        self.cmd("set videosource GFX9000")

    def verify_motion(self) -> None:
        self.release_keys()
        self.begin_frames()
        try:
            self.key("space", True)
            self.seed_quiet()
            states = [self.state("distance", "distance_fraction", "speed", "player_x", "offroad")]
            for _ in range(32):
                self.next_frame()
                states.append(self.state(*states[0]))
            steps = [(b["distance"] - a["distance"]) % 4096 for a, b in zip(states, states[1:])]
            self.check("v0.3-six-unit-top-speed-preserved", steps == [6] * 32
                       and all(s["speed"] == 128 and not s["offroad"] for s in states),
                       distance_steps=steps, seeded=True)
            self.seed_quiet(distance=4095, distance_fraction=31)
            self.next_frame()
            wrap = self.state("distance", "distance_fraction", "speed", "laps")
            self.check("exact-six-unit-course-wrap", wrap == {"distance": 5, "distance_fraction": 31, "speed": 128, "laps": 1}, state=wrap, seeded=True)
            self.release_keys()
            self.seed_quiet(speed=0, distance=1000, distance_fraction=31)
            self.next_frame(5)
            state = self.state("distance", "distance_fraction", "speed", "traffic_z0")
            self.check("stopped-player-stays-put-while-ordinary-traffic-moves",
                       state == {"distance": 1000, "distance_fraction": 31, "speed": 0, "traffic_z0": 2515}, state=state, seeded=True)
        finally:
            self.release_keys()
            self.end_frames()

    def verify_car_retained(self) -> None:
        with zipfile.ZipFile(self.baseline / "source-v0.3.zip") as archive:
            old_atlas = archive.read("assets/vram.bin")
            old_rect = sprite_tables(archive.read("src/assets.h").decode("ascii"))["driving_car"][1]
        with Image.open(self.baseline / "landscape-000.png") as source:
            baseline = source.convert("RGB")
            box = baseline.getbbox()
            colors = {}
            for x, y, index in indexed_sprite(old_atlas, old_rect):
                if index:
                    colors[index] = baseline.getpixel((box[0]+100+x, box[1]+146+y))
        atlas = (ROOT / "assets/vram.bin").read_bytes()
        rects = sprite_tables((ROOT / "src/assets.h").read_text())["driving_car"]
        self.release_keys()
        self.begin_frames()
        checks = []
        try:
            for pose, steering in ((0, "left"), (1, None), (2, "right")):
                self.release_keys()
                if steering:
                    self.key(steering, True)
                self.seed_quiet(mode=2, speed=128, player_x=0)
                self.next_frame(2)
                path = self.screenshot(f"retained-car-pose-{pose}")
                count = mismatches = 0
                with Image.open(path) as source:
                    native = source.convert("RGB")
                    box = native.getbbox()
                    for x, y, index in indexed_sprite(atlas, rects[pose]):
                        if index:
                            count += 1
                            mismatches += native.getpixel((box[0]+100+x, box[1]+146+y)) != colors.get(index)
                checks.append({"pose": pose, "opaque_pixels": count, "mismatches": mismatches,
                               "file": str(path.relative_to(ROOT)).replace("\\", "/")})
            self.check("all-three-native-car-poses-retain-v0.3-pixels-and-size",
                       all(c["opaque_pixels"] > 0 and c["mismatches"] == 0 for c in checks),
                       poses=checks, size=[56, 38], seeded=True)
        finally:
            self.release_keys()
            self.end_frames()

    def verify_course_transfer(self) -> None:
        course = (ROOT / "assets/course.bin").read_bytes()
        phases = [phase for bank in range(32) for phase in (bank*32, bank*32+31)] + [0]
        samples = []
        self.release_keys()
        self.begin_frames()
        try:
            self.seed_quiet(mode=2, speed=0)
            for phase in phases:
                self.seed(distance=phase*4)
                self.next_frame()
                native = bytes.fromhex(self.cmd(f"binary encode hex [debug read_block memory {self.address('profile')} 256]"))
                expected = course[phase*256:(phase+1)*256]
                samples.append({"phase": phase, "rom_bank": 12+(phase//32),
                                "matched": native == expected, "sha256": hashlib.sha256(native).hexdigest()})
            self.check("native-course-RAM-copy-all-32-bank-boundaries-and-wrap",
                       all(sample["matched"] for sample in samples), records=samples,
                       bytes_per_record=256, seeded=True)
        finally:
            self.release_keys()
            self.end_frames()

    def verify_traffic(self) -> None:
        self.release_keys()
        self.begin_frames()
        try:
            self.key("space", True)
            self.seed_quiet(traffic_z0=80, traffic_lane0=1, player_x=-48)
            self.next_frame(25)
            clear = self.state("passes", "hits", "speed", "mode", "traffic_z0", "traffic_tag0")
            self.check("clear-side-overtake-counts-once-without-slowdown", clear["passes"] == 1
                       and clear["hits"] == 0 and clear["speed"] == 128 and clear["mode"] == 1, state=clear, seeded=True)
            self.next_frame(15)
            self.check("passed-car-does-not-repeat-score-every-frame", self.read("passes") == 1,
                       state=self.state("passes", "hits", "traffic_z0"), seeded=True)
            self.seed_quiet(traffic_z0=40, traffic_lane0=1, player_x=48)
            contact = []
            for _ in range(8):
                self.next_frame()
                contact.append(self.state("speed", "hits", "passes", "recovery_timer", "traffic_tag0", "traffic_z0", "mode"))
            hit = [s for s in contact if s["hits"] == 1]
            self.check("ordinary-car-contact-is-short-slowdown-not-failure", bool(hit)
                       and min(s["speed"] for s in hit) >= 72 and min(s["speed"] for s in hit) < 128
                       and all(s["mode"] == 1 for s in contact) and max(s["hits"] for s in contact) == 1,
                       frames=contact, seeded=True)
            self.next_frame(60)
            restored = self.state("hits", "speed", "recovery_timer", "mode")
            self.check("collision-recovery-restores-control-and-speed-without-hit-spam",
                       restored == {"hits": 1, "speed": 128, "recovery_timer": 0, "mode": 1},
                       state=restored, seeded=True)
            self.seed_quiet(traffic_z0=40, traffic_lane0=-1, player_x=-48)
            self.next_frame(5)
            self.check("ordinary-traffic-contact-also-works-in-left-lane", self.read("hits") == 1,
                       state=self.state("hits", "speed", "traffic_lane0", "player_x"), seeded=True)
            self.release_keys()
            self.seed_quiet(traffic_z0=38, traffic_lane0=1, player_x=48, speed=30)
            self.next_frame()
            slow = self.state("hits", "speed")
            self.check("slow-speed-contact-never-accelerates-player", slow == {"hits": 1, "speed": 29},
                       state=slow, speed_before_coasting=30, seeded=True)
            self.seed_quiet(distance=1000, speed=0, traffic_z0=998, traffic_lane0=1, player_x=-48)
            self.next_frame()
            behind = self.state("passes", "hits", "speed", "traffic_z0")
            self.check("traffic-coming-from-behind-does-not-award-an-overtake",
                       behind["passes"] == 0 and behind["hits"] == 0 and behind["speed"] == 0,
                       state=behind, seeded=True)
        finally:
            self.release_keys()
            self.end_frames()

    def verify_ufo(self) -> None:
        self.release_keys()
        self.begin_frames()
        try:
            # Stop below the trigger, then cross it under native acceleration.
            self.seed_quiet(distance=1540, speed=0)
            self.next_frame(3)
            self.check("ufo-does-not-start-before-meadow-trigger", self.read("ufo_state") == 0,
                       state=self.state("distance", "ufo_state"), seeded=True)
            self.key("space", True)
            self.seed_quiet(distance=1550, player_x=48)
            self.next_frame()
            first = self.state("ufo_state", "ufo_timer", "ufo_lane", "ufo_lap", "laps")
            self.check("meadow-starts-announced-ufo-approach", first["ufo_state"] == 1
                       and first["ufo_lane"] == 1 and first["ufo_lap"] == 0,
                       state=first, seeded=True)
            transitions, states = [], [self.state("ufo_state", "ufo_timer", "ufo_catches", "speed", "lift_timer", "recovery_timer")]
            for i in range(180):
                self.next_frame()
                state = self.state(*states[0])
                states.append(state)
                if state["ufo_state"] != states[-2]["ufo_state"]:
                    transitions.append({"frame": i + 1, **state})
                    self.screenshot(f"ufo-transition-{state['ufo_state']}")
                if len(transitions) >= 4 and state["ufo_state"] == 0:
                    break
            transition_order = [row["ufo_state"] for row in transitions]
            harmless = [s for s in states if s["ufo_state"] in (1, 2)]
            caught = [s for s in states if s["ufo_catches"]]
            self.check("ufo-approach-warning-active-departure-order", transition_order == [2, 3, 4, 0], transitions=transitions, seeded=True)
            self.check("ufo-provides-full-30-frame-approach-and-45-frame-warning",
                       [row["frame"] for row in transitions] == [30, 75, 135, 165],
                       transition_frames=[row["frame"] for row in transitions], seeded=True)
            self.check("ufo-visible-approach-and-warning-are-nonharmful", bool(harmless)
                       and all(s["ufo_catches"] == 0 and s["speed"] == 128 and not s["lift_timer"] for s in harmless),
                       approach_frames=sum(s["ufo_state"] == 1 for s in states),
                       warning_frames=sum(s["ufo_state"] == 2 for s in states), seeded=True)
            self.check("active-beam-catches-once-and-lifts-without-hard-stop", bool(caught)
                       and max(s["ufo_catches"] for s in states) == 1 and any(s["lift_timer"] for s in caught)
                       and min(s["speed"] for s in caught) >= 56, catches=max(s["ufo_catches"] for s in states),
                       minimum_speed=min(s["speed"] for s in states), maximum_lift_timer=max(s["lift_timer"] for s in states), seeded=True)
            self.report["ufo_cycle_frame_states"] = states
            self.next_frame(60)
            recovery = self.state("ufo_catches", "speed", "lift_timer", "recovery_timer", "mode")
            self.check("ufo-capture-short-recovery-returns-to-full-drive",
                       recovery == {"ufo_catches": 1, "speed": 128, "lift_timer": 0, "recovery_timer": 0, "mode": 1},
                       state=recovery, seeded=True)
            self.seed(distance=1550, speed=128, ufo_state=0, ufo_timer=0)
            self.next_frame(5)
            self.check("ufo-does-not-retrigger-within-same-lap", self.read("ufo_state") == 0,
                       state=self.state("ufo_state", "ufo_lap", "laps", "ufo_catches"), seeded=True)
            self.seed_quiet(distance=1550, player_x=-48)
            self.next_frame(170)
            avoided = self.state("ufo_state", "ufo_catches", "ufo_dodges", "speed", "mode")
            self.check("opposite-half-road-remains-a-safe-ufo-escape", avoided == {
                       "ufo_state": 0, "ufo_catches": 0, "ufo_dodges": 1, "speed": 128, "mode": 1}, state=avoided, seeded=True)
            self.seed_quiet(distance=1550, laps=1, ufo_lap=0)
            self.next_frame()
            self.check("next-lap-ufo-uses-opposite-side", self.read("ufo_state") == 1
                       and self.read("ufo_lane") == -1 and self.read("ufo_lap") == 1,
                       state=self.state("ufo_state", "ufo_lane", "ufo_lap", "laps"), seeded=True)
            self.release_keys()
            self.seed_quiet(distance=1950, player_x=48, speed=30, ufo_state=3, ufo_timer=60)
            self.next_frame()
            slow = self.state("ufo_catches", "speed", "lift_timer")
            self.check("slow-speed-UFO-capture-never-accelerates-player",
                       slow == {"ufo_catches": 1, "speed": 29, "lift_timer": 30}, state=slow, seeded=True)
            self.seed_quiet(mode=2, ufo_state=2, ufo_timer=20, recovery_timer=12, lift_timer=15)
            before = self.state("distance", "speed", *EVENT_FIELDS)
            self.next_frame(20)
            after = self.state(*before)
            self.check("pause-freezes-traffic-ufo-lift-and-recovery-timers", before == after,
                       before=before, after=after, seeded=True)
        finally:
            self.release_keys()
            self.end_frames()

    def verify_lap_clock(self) -> None:
        self.reset_title()
        self.begin_frames()
        try:
            self.next_frame(20)
            title = self.state(*TIMER_FIELDS)
            self.check("title-does-not-start-time-attack-clock", all(value == 0 for value in title.values()), state=title)
            self.seed_quiet(speed=0)
            self.next_frame(2)
            before, t0 = self.read("lap_current_tenths"), self.clock()
            self.next_frame(90)
            after, t1 = self.read("lap_current_tenths"), self.clock()
            self.check("stopped-active-car-clock-measures-emulated-time-not-frame-assumptions",
                       self.read("distance") == 0 and self.read("speed") == 0
                       and abs((after-before)/10-(t1-t0)) <= 0.15,
                       elapsed_clock_seconds=(after-before)/10, emulated_seconds=round(t1-t0, 6), seeded=True)
            self.key("escape", True)
            self.next_frame()
            self.key("escape", False)
            self.next_frame(2)
            paused = self.state("mode", "lap_current_tenths")
            self.next_frame(60)
            after_pause = self.state(*paused)
            self.check("escape-pause-freezes-time-attack-clock", paused["mode"] == 2 and after_pause == paused,
                       before=paused, after=after_pause)
            self.key("escape", True)
            self.next_frame()
            self.key("escape", False)
            self.next_frame(2)
            resumed, t0 = self.read("lap_current_tenths"), self.clock()
            self.next_frame(30)
            after, t1 = self.read("lap_current_tenths"), self.clock()
            self.check("resume-clock-excludes-paused-interval", self.read("mode") == 1
                       and abs((after-resumed)/10-(t1-t0)) <= 0.15,
                       clock_seconds=(after-resumed)/10, emulated_seconds=round(t1-t0, 6))
            finishes = []
            self.key("space", True)
            for lap, elapsed in enumerate((500, 700, 300)):
                self.seed_quiet(distance=4090, laps=lap, lap_current_tenths=elapsed,
                                lap_previous_laps=lap, lap_previous_mode=1, lap_tick_fraction=0)
                if lap == 0:
                    self.seed(lap_last_valid=0, lap_best_valid=0, lap_last_tenths=0, lap_best_tenths=0)
                self.next_frame()
                finishes.append(self.state("laps", *TIMER_FIELDS))
            self.check("first-finish-records-last-and-best-time", finishes[0]["laps"] == 1
                       and finishes[0]["lap_last_valid"] == finishes[0]["lap_best_valid"] == 1
                       and 500 <= finishes[0]["lap_last_tenths"] <= 501
                       and finishes[0]["lap_best_tenths"] == finishes[0]["lap_last_tenths"]
                       and finishes[0]["lap_current_tenths"] == 0, state=finishes[0], seeded=True)
            self.check("slower-lap-keeps-best-and-faster-lap-replaces-it",
                       700 <= finishes[1]["lap_last_tenths"] <= 701
                       and finishes[1]["lap_best_tenths"] == finishes[0]["lap_best_tenths"]
                       and 300 <= finishes[2]["lap_last_tenths"] <= 301
                       and finishes[2]["lap_best_tenths"] == finishes[2]["lap_last_tenths"],
                       lap_results=finishes, seeded=True)
            self.release_keys()
            self.seed_quiet(speed=0, lap_current_tenths=100000, lap_previous_mode=1,
                            lap_previous_laps=0, lap_tick_fraction=0)
            self.next_frame(30)
            unlimited = self.state("mode", "speed", "lap_current_tenths")
            self.check("large-time-record-has-no-timeout-or-game-over", unlimited["mode"] == 1
                       and unlimited["speed"] == 0 and unlimited["lap_current_tenths"] > 100000,
                       state=unlimited, seeded=True, note="Large elapsed value seeded; not a 10000-second endurance run.")
            self.verify_clock_cache_pixels()
        finally:
            self.release_keys()
            self.end_frames()

    def verify_clock_cache_pixels(self) -> None:
        """Called at a stopped CPU frame hook; compare actual displayed pixels."""
        with zipfile.ZipFile(self.baseline / "source-v0.3.zip") as archive:
            old_atlas = archive.read("assets/vram.bin")
            old_car = sprite_tables(archive.read("src/assets.h").decode("ascii"))["driving_car"][1]
        with Image.open(self.baseline / "landscape-000.png") as source:
            native = source.convert("RGB")
            box = native.getbbox()
            colors = {index: native.getpixel((box[0]+100+x, box[1]+146+y))
                      for x, y, index in indexed_sprite(old_atlas, old_car) if index}
        atlas = (ROOT / "assets/vram.bin").read_bytes()
        font = sprite_tables((ROOT / "src/assets.h").read_text())["font"]
        cases = []
        for value, expected in ((599, "00:59.9"), (600, "01:00.0"),
                                (59999, "99:59.9"), (60000, "100:00.0"),
                                (4294967295, "7158278:49.5"), (0, "00:00.0")):
            self.seed_quiet(mode=2, speed=0, lap_current_tenths=value, lap_best_tenths=value,
                            lap_best_valid=1, lap_previous_mode=2, lap_tick_fraction=0)
            self.next_frame(2)
            texts = {}
            for name in ("lap_current_text", "lap_best_text"):
                raw = bytes.fromhex(self.cmd(f"binary encode hex [debug read_block memory {self.address(name)} 13]"))
                texts[name] = raw.split(b"\0", 1)[0].decode("ascii")
            target = [[12 for _ in range(90)] for _ in range(8)]
            for position, char in enumerate(expected):
                for x, y, index in indexed_sprite(atlas, font[ord(char)-32]):
                    if index:
                        target[y][position*6+x] = index
            path = self.screenshot(f"clock-digits-{value}")
            errors = []
            with Image.open(path) as source:
                image = source.convert("RGB")
                box = image.getbbox()
                for x0 in (38, 164):
                    errors.append(sum(image.getpixel((box[0]+x0+x, box[1]+202+y)) != colors.get(target[y][x])
                                      for y in range(8) for x in range(90)))
            cases.append({"tenths": value, "expected": expected, "strings": texts,
                          "current_mismatched_pixels": errors[0], "best_mismatched_pixels": errors[1],
                          "file": str(path.relative_to(ROOT)).replace("\\", "/")})
        self.check("clock-cache-native-digits-carry-and-long-value-clearing",
                   all(all(text == case["expected"] for text in case["strings"].values())
                       and not case["current_mismatched_pixels"] and not case["best_mismatched_pixels"] for case in cases),
                   cases=cases, pixels_checked_per_case=1440, seeded=True)

    def verify_performance(self) -> None:
        self.release_keys()
        self.seed(lap_current_tenths=0, lap_last_tenths=0, lap_best_tenths=0,
                  lap_last_valid=0, lap_best_valid=0, lap_tick_fraction=0, lap_previous_laps=0)
        rates = []
        cases = [(f"section-{i}", i * 512, 0, -48) for i in range(8)] + [("active-UFO", 1920, 3, -48)]
        cases += [(f"dense-scenery-{x}", dense_scenery_phase(x)*4, 0, x) for x in (-96, 0, 96)]
        for name, distance, ufo, player_x in cases:
            self.seed_quiet(distance=distance, player_x=player_x, ufo_state=ufo, ufo_timer=60,
                            traffic_z0=(distance+110)&4095, traffic_z1=(distance+350)&4095,
                            traffic_z2=(distance+650)&4095)
            self.key("space", True)
            self.advance(0.12)
            t0, f0 = self.clock(), self.read("frame_counter")
            self.advance(1.0)
            t1, f1 = self.clock(), self.read("frame_counter")
            fps = ((f1 - f0) & 65535) / (t1 - t0)
            rates.append({"name": name, "distance": distance, "fps": round(fps, 3), "state": self.state()})
            self.screenshot("performance-" + name)
            self.release_keys()
        self.report["section_frame_rates"] = rates
        self.check("traffic-and-UFO-all-eight-sections-near-30-fps",
                   min(row["fps"] for row in rates) >= 27, sections=rates, seeded=True)

    def capture_encounters(self) -> None:
        if self.frames <= 0:
            return
        self.release_keys()
        self.begin_frames()
        self.seed_quiet(distance=1550, player_x=24, traffic_z0=1760, traffic_lane0=-1,
                        traffic_z1=2200, traffic_z2=2650, lap_current_tenths=0,
                        lap_last_tenths=0, lap_best_tenths=0, lap_last_valid=0,
                        lap_best_valid=0, lap_tick_fraction=0, lap_previous_laps=0)
        self.key("space", True)
        pictures, timestamps, states = [], [], []
        try:
            self.next_frame(2)
            for i in range(self.frames):
                path = self.screenshot(f"native-{i:03d}")
                with Image.open(path) as source:
                    pictures.append(source.convert("RGB"))
                timestamps.append(self.clock())
                states.append(self.state("distance", "speed", "player_x", "passes", "hits", "ufo_state", "ufo_timer", "ufo_dodges", "ufo_catches"))
                self.next_frame()
        finally:
            self.release_keys()
            self.end_frames()
        durations, accumulated = [], 0
        for i in range(len(pictures)):
            end = timestamps[i + 1] if i + 1 < len(pictures) else timestamps[i] + timestamps[i] - timestamps[i - 1]
            rounded = round((end - timestamps[0]) * 100) * 10
            durations.append(max(10, rounded - accumulated))
            accumulated = rounded
        gif = self.out / "drive-native.gif"
        pictures[0].save(gif, save_all=True, append_images=pictures[1:], duration=durations, loop=0, optimize=False)
        distinct = len({hashlib.sha256(p.tobytes()).hexdigest() for p in pictures})
        self.check("consecutive-native-encounter-frames-move", distinct >= int(self.frames * 0.8), distinct=distinct, total=self.frames)
        runs = []
        for picture, duration in zip(pictures, durations):
            pixels = picture.tobytes()
            if runs and runs[-1][0] == pixels:
                runs[-1][1] += duration
            else:
                runs.append([pixels, duration])
        with Image.open(gif) as result:
            exact = result.n_frames == len(runs)
            if exact:
                for i, (pixels, duration) in enumerate(runs):
                    result.seek(i)
                    exact = exact and result.convert("RGB").tobytes() == pixels and result.info.get("duration") == duration
            self.check("native-gif-pixels-and-timing-match-captures", exact, frames=result.n_frames, native_frames=len(pictures))
        self.report["native_capture"] = {"frames": len(pictures), "file": str(gif.relative_to(ROOT)).replace("\\", "/"),
                                         "emulated_seconds": round(timestamps[-1] - timestamps[0], 6),
                                         "fps": round((len(pictures) - 1) / (timestamps[-1] - timestamps[0]), 3),
                                         "seeded": True, "states": states}

    def verify_input_lap(self) -> None:
        if not self.input_lap:
            return
        if any(not r["passed"] and r["name"] == "traffic-and-UFO-all-eight-sections-near-30-fps" for r in self.results):
            self.report["input_lap_skipped_reason"] = "Frame-rate target not met; optimize before the final lap."
            return
        self.reset_title()
        initial = self.state("mode", "distance", "speed", "laps", "player_x", "passes", "hits", "ufo_dodges", "ufo_catches")
        expected = {name: 0 for name in initial}
        self.check("input-lap-starts-from-reset-title-with-zero-counters", initial == expected, state=initial)
        if initial != expected:
            return
        started, first_frame = self.clock(), self.read("frame_counter")
        self.tap("space")
        self.key("space", True)
        samples, sections, seen_ufo, active_steering = [], set(), set(), 0
        while self.read("laps") == 0:
            state = self.state()
            elapsed = self.clock() - started
            if elapsed > 120 or state["mode"] != 1:
                raise RuntimeError(f"Input-only lap did not complete: {state}")
            # Read-only driving policy: choose the opposite half from the nearest
            # slower car ahead (all traffic travels in our direction), except
            # during the announced UFO encounter when its fixed beam takes priority.
            target = 0
            close = sorted(((state[f"traffic_z{i}"]-state["distance"])&4095, state[f"traffic_lane{i}"])
                           for i in range(3) if ((state[f"traffic_z{i}"]-state["distance"])&4095) < 340)
            if close:
                target = -48 * close[0][1]
            if state["ufo_state"] in (1, 2, 3):
                target = -48 * state["ufo_lane"]
            steering = -1 if state["player_x"] > target + 5 else (1 if state["player_x"] < target - 5 else 0)
            if steering != active_steering:
                if active_steering:
                    self.key("left" if active_steering < 0 else "right", False)
                if steering:
                    self.key("left" if steering < 0 else "right", True)
                active_steering = steering
            samples.append({"emulated_seconds": round(elapsed, 4), "steering_key": steering, "target_player_x": target, **state})
            if state["section"] not in sections:
                sections.add(state["section"])
                print("input-only-lap section", state["section"], "at", round(elapsed, 2), "seconds", flush=True)
            if state["ufo_state"] not in seen_ufo:
                seen_ufo.add(state["ufo_state"])
                self.screenshot(f"input-lap-ufo-state-{state['ufo_state']}")
            self.advance(0.08)
        end, last_frame = self.clock(), self.read("frame_counter")
        self.release_keys()
        self.stop()
        final = self.state("mode", "laps", "distance", "speed", "player_x", "passes", "hits", "ufo_dodges", "ufo_catches", *TIMER_FIELDS)
        completed = final["laps"] == 1 and final["mode"] == 1 and final["speed"] == 0 and sections == set(range(8))
        fps = ((last_frame - first_frame) & 65535) / (end - started)
        self.check("input-only-complete-course-and-brake-to-stop", completed, final=final,
                   sections=sorted(sections), emulated_seconds=round(end - started, 3), average_fps=round(fps, 3),
                   maximum_abs_player_x=max(abs(s["player_x"]) for s in samples), offroad_samples=sum(bool(s["offroad"]) for s in samples), ram_writes=0)
        self.check("input-only-lap-overtakes-ordinary-traffic-and-avoids-UFO", completed
                   and final["passes"] >= 3 and final["hits"] == 0 and final["ufo_dodges"] == 1
                   and final["ufo_catches"] == 0 and {1, 2, 3, 4}.issubset(seen_ufo),
                   passes=final["passes"], collisions=final["hits"], ufo_dodges=final["ufo_dodges"],
                   ufo_catches=final["ufo_catches"], observed_ufo_states=sorted(seen_ufo), ram_writes=0)
        self.check("input-only-encounter-lap-near-30-fps", completed and fps >= 27, average_fps=round(fps, 3), ram_writes=0)
        self.check("input-only-lap-last-and-best-match-native-elapsed-time",
                   completed and final["lap_last_valid"] == final["lap_best_valid"] == 1
                   and final["lap_last_tenths"] == final["lap_best_tenths"]
                   and abs(final["lap_last_tenths"]/10-(end-started)) <= 0.25,
                   recorded_seconds=final["lap_last_tenths"]/10, measured_seconds=round(end-started, 4), ram_writes=0)
        self.report["full_course_input_only_playthrough"] = completed
        self.report["input_only_lap"] = {"reset_before_start": True, "ram_writes": 0,
                                         "controls": "SPACE accelerator, left/right avoidance and X brake", "samples": samples}
        self.screenshot("04-input-only-lap-finished")
        self.lap_finished = completed

    def run(self, only: str = "all") -> int:
        for result in preservation_checks(self.baseline, self.manifest):
            result = dict(result)
            self.check(result.pop("name"), result.pop("passed"), **result)
        groups = (self.verify_input, self.verify_motion, self.verify_course_transfer, self.verify_car_retained, self.verify_traffic, self.verify_ufo, self.verify_lap_clock,
                  self.verify_performance, self.capture_encounters, self.verify_input_lap)
        if only == "performance":
            groups = (self.verify_performance,)
        elif only == "events":
            groups = (self.verify_motion, self.verify_traffic, self.verify_ufo, self.verify_lap_clock)
        elif only == "clock":
            groups = (self.verify_lap_clock,)
        elif only == "visuals":
            groups = (self.verify_car_retained, self.verify_lap_clock)
        elif only == "transfer":
            groups = (self.verify_course_transfer,)
        try:
            if only == "all":
                self.reset_title()
            for group in groups:
                try:
                    group()
                except Exception as error:
                    self.report.setdefault("errors", []).append({"group": group.__name__, "message": str(error)})
                    self.check(group.__name__ + "-completed", False, error=str(error))
                    self.release_keys()
                    self.end_frames()
        finally:
            try:
                self.end_frames()
                self.release_keys()
            except Exception as error:
                self.report["cleanup_error"] = str(error)
            self.report["passed"] = all(row["passed"] for row in self.results)
            self.report["checks_passed"] = sum(row["passed"] for row in self.results)
            self.report["checks_total"] = len(self.results)
            path = self.report_path if only == "all" else self.out / (only + "-verification.json")
            path.write_text(json.dumps(portable_report(self.report), indent=2) + "\n")
        return 0 if self.report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18796)
    parser.add_argument("--capture-frames", type=int, default=170)
    parser.add_argument("--skip-input-lap", action="store_true")
    parser.add_argument("--only", choices=("all", "performance", "events", "clock", "visuals", "transfer"), default="all")
    args = parser.parse_args()
    raise SystemExit(EncounterChecks(args.port, args.capture_frames, not args.skip_input_lap).run(args.only))
