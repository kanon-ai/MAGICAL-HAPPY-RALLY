"""Verify the actual 512 KiB cartridge in native openMSX, through its Tcl bridge.

The first block uses only keyboard input. Distant visual and loop-boundary
scenarios explicitly seed game RAM; they are not a complete-course playthrough.
The final block resets the machine and drives one full lap with keyboard input.
Screenshots and GIF pixels are rendered by the MSX ROM, never recreated on PC.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image
from compare_scenery import scenery_probe_phases
from compare_speed_car import compare_speed_car, preservation_checks, check_native_car

ROOT = Path(__file__).resolve().parents[1]
SIZES = {
    "ready": 1, "mode": 1, "frame_counter": 2, "distance": 2,
    "speed": 2, "player_x": 2, "keys": 1, "course_phase": 2,
    "road_center": 2, "hill": 2, "offroad": 1, "laps": 2,
    "course_curve": 1, "section": 1, "distance_fraction": 1,
}
SIGNED = {"player_x", "road_center", "hill", "course_curve"}
KEYS = {
    "left": (8, 0x10), "right": (8, 0x80), "up": (8, 0x20),
    "down": (8, 0x40), "space": (8, 0x01), "x": (5, 0x20),
    "escape": (7, 0x04),
}


class NativeChecks:
    def __init__(self, port: int, frames: int, input_lap: bool = True):
        self.url = f"http://127.0.0.1:{port}"
        self.frames = frames
        self.input_lap = input_lap
        self.lap_finished = False
        self.symbols = json.loads((ROOT / "work/build/symbols.json").read_text())
        self.manifest = json.loads((ROOT / "outputs/build-manifest.json").read_text())
        version = str(self.manifest["version"])
        if version != "0.3":
            raise ValueError("This verifier requires v0.3; v0.1 and v0.2 verification artifacts are preserved.")
        self.release = "v" + version
        self.output_root = ROOT / "outputs"
        self.out = self.output_root / self.release
        self.report_path = self.output_root / f"verification-{self.release}.json"
        self.baseline = self.output_root / "baseline-v0.2"
        self.shots = self.out / "screenshots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.results: list[dict] = []
        self.report = {
            "rom": self.manifest,
            "machine": "Panasonic_FS-A1ST",
            "extension": "gfx9000",
            "physical_hardware_tested": False,
            "browser_mock_used": False,
            "full_course_input_only_playthrough": False,
            "input_only_checks": "Startup, start, acceleration, steering, braking, coasting, pause, recovery.",
            "scenario_seeding": "Landscape phases, near-loop endpoint, exact per-frame speed and car-pose scenarios, GIF start, and final return to title use RAM writes. The reset full lap uses no RAM writes.",
            "baseline": "outputs/baseline-v0.2",
            "results": self.results,
        }
        self.breakpoint: str | None = None

    def cmd(self, script: str) -> str:
        request = urllib.request.Request(self.url, data=script.encode(), method="POST")
        try:
            return urllib.request.urlopen(request, timeout=30).read().decode().strip()
        except urllib.error.HTTPError as error:
            raise RuntimeError(error.read().decode()) from error

    def address(self, name: str) -> int:
        return int(self.symbols["_" + name])

    def read_expr(self, name: str) -> str:
        address = self.address(name)
        expr = f"[debug read memory {address}]"
        if SIZES[name] == 2:
            expr += f"+256*[debug read memory {address + 1}]"
        return f"[expr {{{expr}}}]"

    def state(self, *names: str) -> dict[str, int]:
        if not names:
            names = tuple(name for name in SIZES if "_" + name in self.symbols)
        values = map(int, self.cmd("list " + " ".join(self.read_expr(n) for n in names)).split())
        state = dict(zip(names, values))
        for name in names:
            if name in SIGNED and state[name] >= 1 << (SIZES[name] * 8 - 1):
                state[name] -= 1 << (SIZES[name] * 8)
        return state

    def read(self, name: str) -> int:
        return self.state(name)[name]

    def logical_vram(self, address: int, size: int) -> bytes:
        """B1 logical bytes are interleaved between two physical VRAM planes.

        Each reply is at most 64 KiB of hex. The local XML bridge has a 1 MiB
        receive cap, so never request the entire 512 KiB VRAM as a hex string.
        """
        if address & 1 or size & 1 or not 0 <= address < address + size <= 524288:
            raise ValueError("Expected a nonempty even B1 VRAM range")
        data = bytearray(size)
        for offset in range(0, size // 2, 32768):
            count = min(32768, size // 2 - offset)
            even_address = address // 2 + offset
            odd_address = even_address + 262144
            even = bytes.fromhex(self.cmd(f"binary encode hex [debug read_block {{Sunrise GFX9000 VRAM}} {even_address} {count}]"))
            odd = bytes.fromhex(self.cmd(f"binary encode hex [debug read_block {{Sunrise GFX9000 VRAM}} {odd_address} {count}]"))
            data[2 * offset:2 * (offset + count):2] = even
            data[2 * offset + 1:2 * (offset + count):2] = odd
        return bytes(data)

    def seed(self, **values: int) -> None:
        commands = []
        for name, value in values.items():
            for i in range(SIZES[name]):
                commands.append(f"debug write memory {self.address(name) + i} {(value >> (8 * i)) & 255}")
        self.cmd("set pause on; " + "; ".join(commands) + "; set pause off")

    def clock(self) -> float:
        return float(self.cmd("machine_info time"))

    def until(self, predicate, seconds: float = 20) -> None:
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError("Waiting for native emulator state")
            time.sleep(0.012)

    def advance(self, seconds: float) -> None:
        target = self.clock() + seconds
        self.until(lambda: self.clock() >= target, max(30, seconds * 5))

    def key(self, name: str, down: bool) -> None:
        row, mask = KEYS[name]
        self.cmd(f"keymatrix{'down' if down else 'up'} {row} {mask}")

    def release_keys(self) -> None:
        self.cmd("; ".join(f"keymatrixup {row} {mask}" for row, mask in KEYS.values()))

    def tap(self, name: str) -> None:
        self.key(name, True)
        self.advance(0.18)
        self.key(name, False)
        self.advance(0.12)

    def check(self, name: str, passed: bool, **evidence) -> None:
        self.results.append({"name": name, "passed": bool(passed), **evidence})
        print(name, "PASS" if passed else "FAIL", json.dumps(evidence), flush=True)

    def screenshot(self, name: str) -> Path:
        path = self.shots / (name + ".png")
        self.cmd(f"openmsx::internal_screenshot -raw {{{path.as_posix()}}}")
        return path

    def stop(self) -> None:
        self.key("space", False)
        self.key("up", False)
        self.key("x", True)
        self.until(lambda: self.read("speed") == 0, 20)
        self.key("x", False)
        self.advance(0.10)

    def verify_input(self) -> None:
        self.cmd("set pause off; set speed 100; set videosource GFX9000")
        self.release_keys()
        self.until(lambda: self.read("ready") == 0xA5, 45)
        self.advance(0.15)
        self.report["emulator"] = self.cmd("openmsx_info version")
        self.report["rom_slot"] = self.cmd("set drive_check_slot {}; foreach drive_check_cart [info commands cart?] {if {[string match *ALPINE_DRIVE* [lindex [$drive_check_cart] 1]]} {set drive_check_slot [list $drive_check_cart [machine_info external_slot slot[string index $drive_check_cart end]]]}}; set drive_check_slot")
        identity = self.cmd("set drive_check_identity {}; foreach drive_check_device [machine_info device] {set drive_check_info [machine_info device $drive_check_device]; if {[dict exists $drive_check_info actualSHA1] && [dict exists $drive_check_info filename] && [string match *ALPINE_DRIVE* [dict get $drive_check_info filename]]} {set drive_check_identity [list [dict get $drive_check_info actualSHA1] [dict get $drive_check_info mappertype]]}}; set drive_check_identity").split()
        self.report["loaded_rom"] = {"sha1": identity[0], "mapper": identity[1]}
        local_sha1 = hashlib.sha1((self.output_root / self.manifest["file"]).read_bytes()).hexdigest()
        self.check("loaded-cartridge-identity-and-ASCII8-mapper", identity[0].lower() == local_sha1 and identity[1].lower() == "ascii8", emulator_sha1=identity[0], file_sha1=local_sha1, mapper=identity[1])
        self.check("target-machine", self.cmd("machine_info config_name") == "Panasonic_FS-A1ST")
        r6 = int(self.cmd("debug read {Sunrise GFX9000 regs} 6"))
        r13 = int(self.cmd("debug read {Sunrise GFX9000 regs} 13"))
        self.check("V9990-B1-4bpp", r6 == 0x81 and r13 == 0, register_6=r6, register_13=r13)
        cpu_mode = int(self.cmd("debug read {S1990 regs} 6"))
        self.check("R800-DRAM-active", cpu_mode & 0x60 == 0, register_6=cpu_mode)
        self.cmd("set pause on")
        try:
            atlas = (ROOT / "assets/vram.bin").read_bytes()
            native_atlas = self.logical_vram(0x10000, len(atlas))
            self.check("native-scenery-atlas-upload", native_atlas == atlas, bytes=len(atlas), sha256=hashlib.sha256(atlas).hexdigest())
            scenery = (ROOT / "assets/scenery.bin").read_bytes()
            self.check("native-extra-scenery-upload", len(scenery) == 131072 and self.logical_vram(0x30000, len(scenery)) == scenery, logical_vram_start="0x30000", bytes=len(scenery), chunk_bytes=32768, sha256=hashlib.sha256(scenery).hexdigest())
        finally:
            self.cmd("set pause off")
        self.check("startup-title", self.read("mode") == 0, state=self.state())
        self.screenshot("00-title")
        self.tap("space")
        self.check("space-starts-drive", self.read("mode") == 1, mode=self.read("mode"))
        before = self.state("speed", "distance")
        self.key("space", True)
        self.advance(1.5)
        after = self.state("speed", "distance")
        self.check("space-accelerates-and-travels", after["speed"] > before["speed"] and after["distance"] != before["distance"], before=before, after=after)
        self.screenshot("01-first-drive")
        x0 = self.read("player_x")
        self.key("left", True)
        self.advance(0.25)
        self.key("left", False)
        x1 = self.read("player_x")
        self.key("right", True)
        self.advance(0.25)
        self.key("right", False)
        x2 = self.read("player_x")
        self.check("left-right-steering", x1 < x0 and x2 > x1, start=x0, left=x1, right=x2)
        self.key("space", False)
        before = self.read("speed")
        self.advance(0.7)
        self.check("release-accelerator-coasts-down", self.read("speed") < before, before=before, after=self.read("speed"))
        self.stop()
        d0 = self.read("distance")
        self.advance(0.4)
        self.check("x-brakes-to-stable-stop", self.read("speed") == 0 and self.read("distance") == d0, state=self.state("speed", "distance"))
        self.key("up", True)
        self.advance(0.8)
        self.key("up", False)
        self.check("up-restarts-stopped-car", self.read("speed") > 0 and self.read("distance") != d0, state=self.state("speed", "distance"))
        self.key("space", True)
        self.advance(0.3)
        self.tap("escape")
        self.check("escape-pauses", self.read("mode") == 2)
        paused = self.state("distance", "distance_fraction", "speed", "player_x", "laps")
        self.key("left", True)
        self.advance(0.6)
        self.key("left", False)
        self.check("pause-freezes-travel-and-steering", self.state(*paused) == paused, before=paused, after=self.state(*paused))
        self.screenshot("02-paused")
        self.tap("escape")
        self.advance(0.2)
        self.check("escape-resumes-drive", self.read("mode") == 1 and self.read("distance") != paused["distance"])
        self.until(lambda: self.read("speed") >= 126, 20)
        paved_speed = self.read("speed")
        self.key("right", True)
        self.until(lambda: self.read("offroad") != 0, 15)
        self.key("right", False)
        self.advance(1.4)
        grass = self.state("speed", "offroad", "player_x")
        self.check("roadside-slows-car-without-failure", grass["offroad"] != 0 and grass["speed"] < paved_speed and self.read("mode") == 1, road_speed=paved_speed, grass=grass)
        self.screenshot("03-roadside")
        self.key("left", True)
        self.until(lambda: self.read("player_x") <= 0, 15)
        self.key("left", False)
        self.advance(1.5)
        recovered = self.state("speed", "offroad", "player_x", "mode")
        self.check("steer-back-and-recover-speed", recovered["offroad"] == 0 and recovered["speed"] > grass["speed"] and recovered["mode"] == 1, recovered=recovered)
        self.key("space", False)
        self.stop()
        self.key("up", True)
        self.advance(1.0)
        self.key("down", True)
        before = self.read("speed")
        self.advance(0.5)
        after = self.read("speed")
        self.key("down", False)
        self.key("up", False)
        self.check("down-brakes-with-accelerator-held", after < before, before=before, after=after)
        self.release_keys()

    def verify_scenarios(self) -> None:
        self.key("space", True)
        self.seed(mode=1, distance=4080, speed=128, player_x=0, laps=0)
        self.until(lambda: self.read("laps") > 0, 10)
        wrapped = self.state("laps", "distance", "course_phase", "speed", "mode")
        self.check("seeded-course-wrap-remains-drivable", wrapped["laps"] == 1 and wrapped["distance"] < 512 and wrapped["course_phase"] < 64 and wrapped["mode"] == 1, state=wrapped)
        self.release_keys()
        scenes = []
        phase_count = self.manifest["course"]["records"]
        phase_distance = 4096 // phase_count
        for phase in range(0, phase_count, phase_count // 8):
            self.seed(mode=1, distance=phase * phase_distance, speed=0, player_x=0)
            self.advance(0.22)
            state = self.state()
            path = self.screenshot(f"landscape-{phase:03d}")
            scenes.append({"requested_phase": phase, "state": state, "file": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        self.report["seeded_landscapes"] = scenes
        comparison = compare_speed_car(self.baseline, self.report, self.out)
        self.report["same_condition_comparison"] = comparison
        self.check("baseline-same-coordinate-landscape-comparison", comparison["all_conditions_match"] and comparison["baseline_hashes_match"] and comparison["native_sizes_match"], compared_phases=comparison["phases"], contact_sheet=comparison["contact_sheet"])
        self.check("baseline-native-background-and-hud-preserved-outside-car", comparison["background_and_hud_preserved"], scenes=len(comparison["phases"]), excluded_car_union=comparison["excluded_car_union"], changed_pixels=[pair["changed_pixels_outside_car_union"] for pair in comparison["pairs"]])
        self.check("larger-centered-native-car-matches-atlas", comparison["new_car_pixels_match"], scenes=len(comparison["phases"]), opaque_pixels_per_scene=[pair["new_native_car"]["opaque_pixels_checked"] for pair in comparison["pairs"]])
        self.check("seeded-landscapes-change", len({s["sha256"] for s in scenes}) == len(scenes), distinct=len({s["sha256"] for s in scenes}), captures=len(scenes))
        curves = [s["state"].get("course_curve", s["state"]["road_center"]) for s in scenes]
        hills = [s["state"]["hill"] for s in scenes]
        self.check("seeded-left-and-right-curves", min(curves) < 0 < max(curves), curve_values=curves)
        self.check("seeded-horizon-varies-for-hills", max(hills) - min(hills) >= 4, hill_values=hills)
        section_rates = []
        self.key("space", True)
        for scene in scenes:
            self.seed(mode=1, distance=scene["requested_phase"] * phase_distance, speed=128, player_x=0)
            self.advance(0.10)
            t0, f0 = self.clock(), self.read("frame_counter")
            self.advance(1.0)
            t1, f1 = self.clock(), self.read("frame_counter")
            section_rates.append({"starting_phase": scene["requested_phase"], "fps": round(((f1 - f0) & 65535) / (t1 - t0), 3)})
        self.report["section_frame_rates"] = section_rates
        self.check("all-eight-sections-near-30-fps", min(rate["fps"] for rate in section_rates) >= 27, sections=section_rates)
        self.seed(mode=1, distance=0, speed=128, player_x=0)
        self.key("space", True)
        self.advance(0.2)
        t0, f0 = self.clock(), self.read("frame_counter")
        self.advance(3.0)
        t1, f1 = self.clock(), self.read("frame_counter")
        fps = ((f1 - f0) & 65535) / (t1 - t0)
        self.report["native_frame_rate"] = {"fps": round(fps, 3), "emulated_seconds": round(t1 - t0, 5), "target_fps": 30, "definition": "Completed front-buffer flips, measured against emulated machine time."}
        self.check("native-frame-rate-near-30", fps >= 27, **self.report["native_frame_rate"])
        self.release_keys()

    def verify_speed_and_car(self) -> None:
        """Exact frame boundary checks; these are explicitly RAM-seeded tests."""
        self.release_keys()
        self.breakpoint = self.cmd(f"debug set_bp {self.address('frame_done')} {{}} {{debug break}}")
        self.until(lambda: self.cmd("debug breaked") == "1")
        def next_frame():
            self.cmd("debug cont")
            self.until(lambda: self.cmd("debug breaked") == "1")
        try:
            self.key("space", True)
            self.seed(mode=1, distance=0, distance_fraction=0, speed=128, player_x=0, laps=0)
            states = [self.state("distance", "distance_fraction", "speed", "offroad", "player_x")]
            for _ in range(32):
                next_frame()
                states.append(self.state("distance", "distance_fraction", "speed", "offroad", "player_x"))
            steps = [(after["distance"] - before["distance"]) % 4096 for before, after in zip(states, states[1:])]
            self.check("native-full-throttle-exactly-1.5x-distance-per-frame", steps == [6] * 32 and all(state["speed"] == 128 and not state["offroad"] for state in states), distance_steps=steps, baseline_step=4, new_step=6, speed_multiplier=1.5, seeded=True)
            self.report["exact_speed_scenario"] = {"states": states, "distance_steps": steps, "seeded": True}
            self.seed(mode=1, distance=4095, distance_fraction=31, speed=128, player_x=0, laps=0)
            next_frame()
            wrapped = self.state("distance", "distance_fraction", "laps", "speed")
            self.check("exact-six-unit-course-wrap", wrapped == {"distance": 5, "distance_fraction": 31, "laps": 1, "speed": 128}, state=wrapped, seeded=True)
            self.release_keys()
            stopped_cases = []
            for fraction in (0, 1, 15, 31):
                self.seed(mode=1, distance=1234, distance_fraction=fraction, speed=0, player_x=0)
                for _ in range(4):
                    next_frame()
                state = self.state("distance", "distance_fraction", "speed")
                stopped_cases.append(state)
            self.check("stopped-car-retains-all-fraction-boundaries", all(case == {"distance": 1234, "distance_fraction": fraction, "speed": 0} for case, fraction in zip(stopped_cases, (0, 1, 15, 31))), cases=stopped_cases)
            fractional_cases = []
            for post_update_speed in (0, 1, 2, 31, 32, 63, 64, 65, 126, 127):
                for fraction in (0, 1, 31):
                    self.seed(mode=1, distance=1234, distance_fraction=fraction, speed=post_update_speed + 1, player_x=0)
                    next_frame()
                    actual = self.state("distance", "distance_fraction", "speed")
                    advance = fraction + post_update_speed + post_update_speed // 2
                    expected = {"distance": 1234 + advance // 32, "distance_fraction": advance % 32, "speed": post_update_speed}
                    fractional_cases.append({"speed_after_coasting": post_update_speed, "initial_fraction": fraction, "actual": actual, "expected": expected, "passed": actual == expected})
            self.check("native-odd-even-low-speed-fractional-progress", all(case["passed"] for case in fractional_cases), cases=fractional_cases, seeded=True)
            poses = []
            for pose, steering in ((0, "left"), (1, None), (2, "right")):
                self.release_keys()
                self.key("space", True)
                if steering:
                    self.key(steering, True)
                # internal_screenshot returns the fully presented video frame,
                # which can lag the frame_done CPU hook by one presentation.
                # Pause gameplay at fixed coordinates and present the same
                # pose twice; input keys still select the intended car sprite.
                self.seed(mode=2, distance=0, distance_fraction=0, speed=128, player_x=0)
                next_frame()
                next_frame()
                state = self.state("mode", "player_x", "keys", "speed", "distance")
                path = self.screenshot(f"car-pose-{pose}")
                check = check_native_car(self.baseline, path, pose, state["player_x"])
                check["state"] = state
                check["file"] = str(path.relative_to(ROOT)).replace("\\", "/")
                check["capture_condition"] = "RAM-seeded paused gameplay, fixed player_x=0, speed=128 retained for steering-pose selection; two completed frames presented before screenshot."
                poses.append(check)
            self.report["native_car_poses"] = poses
            self.check("larger-native-car-all-three-steering-poses", all(pose["passed"] for pose in poses), poses=poses, seeded=True)
        finally:
            self.release_keys()
            self.cmd(f"debug remove_bp {self.breakpoint}; debug cont")
            self.breakpoint = None

    def verify_scenery_probes(self) -> None:
        probes = scenery_probe_phases()
        for label, player_x in (("left-side-load", -96), ("right-side-load", 96)):
            probe = scenery_probe_phases(player_x)[0]
            probe["name"] = label
            probes.append(probe)
        phase_distance = 4096 // self.manifest["course"]["records"]
        for probe in probes:
            self.seed(mode=1, distance=probe["phase"] * phase_distance, speed=0, player_x=probe["player_x"])
            self.advance(0.20)
            probe["native_state"] = self.state()
            path = self.screenshot(f"scenery-{probe['name']}-{probe['phase']:04d}")
            probe["file"] = str(path.relative_to(ROOT)).replace("\\", "/")
            self.key("space", True)
            self.seed(mode=1, distance=probe["phase"] * phase_distance, speed=128, player_x=probe["player_x"])
            self.advance(0.1)
            t0, f0 = self.clock(), self.read("frame_counter")
            self.advance(1.0)
            t1, f1 = self.clock(), self.read("frame_counter")
            probe["native_fps"] = round(((f1 - f0) & 65535) / (t1 - t0), 3)
            probe["after_motion_state"] = self.state()
            path = self.screenshot(f"scenery-{probe['name']}-after-motion")
            probe["after_motion_file"] = str(path.relative_to(ROOT)).replace("\\", "/")
            self.release_keys()
        self.report["scenery_probes"] = probes
        self.check("near-scenery-rendering-budget", min(probe["native_fps"] for probe in probes) >= 27, scenarios=[{"name": probe["name"], "phase": probe["phase"], "player_x": probe["player_x"], "fps": probe["native_fps"], "visible_bbox_pixels": probe["bbox_pixels"]} for probe in probes])

    def capture_scenery_transitions(self) -> None:
        # Dedicated adjacent-phase evidence for entry-pop locations found by
        # the static reviewer. This is a seeded visual check, not a playthrough.
        phase_distance = 4096 // self.manifest["course"]["records"]
        transitions = []
        self.release_keys()
        for phase in (184, 185, 186, 187, 188, 541, 542, 543, 544, 545):
            self.seed(mode=1, distance=phase * phase_distance, speed=0, player_x=0)
            self.advance(0.20)
            path = self.screenshot(f"scenery-transition-{phase:04d}")
            transitions.append({"phase": phase, "state": self.state(), "file": str(path.relative_to(ROOT)).replace("\\", "/")})
        self.report["scenery_transition_captures"] = transitions

    def append_scenery_transitions(self) -> None:
        """Add requested visual evidence to a completed report without rerunning input tests."""
        report = json.loads(self.report_path.read_text())
        if report["rom"]["sha256"] != self.manifest["sha256"]:
            raise ValueError("Existing verification describes a different ROM")
        expected_sha1 = hashlib.sha1((self.output_root / self.manifest["file"]).read_bytes()).hexdigest()
        loaded = self.cmd("set drive_check_sha {}; foreach drive_check_device [machine_info device] {set drive_check_info [machine_info device $drive_check_device]; if {[dict exists $drive_check_info actualSHA1] && [dict exists $drive_check_info filename] && [string match *ALPINE_DRIVE* [dict get $drive_check_info filename]]} {set drive_check_sha [dict get $drive_check_info actualSHA1]}}; set drive_check_sha")
        if loaded.lower() != expected_sha1:
            raise ValueError("Loaded emulator ROM differs from the verified ROM")
        saved = self.state("mode", "distance", "speed", "player_x", "laps")
        if saved["speed"] != 0:
            raise ValueError("Additional screenshots require the verifier's stopped-car handoff state")
        try:
            self.cmd("set videosource GFX9000")
            self.capture_scenery_transitions()
            report["scenery_transition_captures"] = self.report["scenery_transition_captures"]
            report["additional_visual_scenario_seeding"] = "After the full input-only lap, the listed adjacent phases were seeded in RAM for visual QA; the stopped-car state was then restored. This does not form part of the input-only lap."
        finally:
            self.release_keys()
            self.seed(**saved)
            self.advance(0.20)
        self.report_path.write_text(json.dumps(report, indent=2) + "\n")
        print("Adjacent-phase native evidence appended; stopped-car state restored", flush=True)

    def capture(self) -> None:
        if self.frames <= 0:
            return
        self.seed(mode=1, distance=0, speed=128, player_x=0)
        self.key("space", True)
        self.breakpoint = self.cmd(f"debug set_bp {self.address('frame_done')} {{}} {{debug break}}")
        self.until(lambda: self.cmd("debug breaked") == "1")
        pictures, timestamps, states = [], [], []
        for i in range(self.frames):
            path = self.screenshot(f"native-{i:03d}")
            with Image.open(path) as source:
                pictures.append(source.convert("RGB"))
            timestamps.append(self.clock())
            states.append(self.state("distance", "course_phase", "speed", "player_x"))
            self.cmd("debug cont")
            self.until(lambda: self.cmd("debug breaked") == "1")
        self.cmd(f"debug remove_bp {self.breakpoint}; debug cont")
        self.breakpoint = None
        self.release_keys()
        durations, accumulated = [], 0
        for i in range(len(pictures)):
            end = timestamps[i + 1] if i + 1 < len(pictures) else timestamps[i] + timestamps[i] - timestamps[i - 1]
            rounded = round((end - timestamps[0]) * 100) * 10
            durations.append(max(10, rounded - accumulated))
            accumulated = rounded
        gif = self.out / "drive-native.gif"
        pictures[0].save(gif, save_all=True, append_images=pictures[1:], duration=durations, loop=0, optimize=False)
        distinct = len({hashlib.sha256(p.tobytes()).hexdigest() for p in pictures})
        self.check("consecutive-native-frames-move", distinct >= int(self.frames * 0.8), distinct=distinct, total=self.frames)
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
            self.check("native-gif-pixels-and-timing-match-captures", exact, frames=result.n_frames, native_frames=len(pictures), identical_frames_combined=True)
        self.report["native_capture"] = {"frames": len(pictures), "emulated_seconds": round(timestamps[-1] - timestamps[0], 6), "fps": round((len(pictures) - 1) / (timestamps[-1] - timestamps[0]), 3), "timing": "Consecutive completed native frames, GIF times quantized to 10 ms.", "states": states}

    def verify_input_lap(self) -> None:
        if not self.input_lap:
            return
        if any(not result["passed"] and result["name"] in ("all-eight-sections-near-30-fps", "native-frame-rate-near-30", "near-scenery-rendering-budget") for result in self.results):
            self.report["input_lap_skipped_reason"] = "Frame-rate target not yet met; full input-only lap is reserved for the optimized candidate."
            print("input-only lap deferred until frame-rate target is met", flush=True)
            return
        # A real machine reset removes every earlier seeded test scenario.
        # From this reset until the car is stopped, only keymatrix input is sent.
        self.release_keys()
        self.cmd("reset; set pause off")
        self.advance(6.0)
        self.until(lambda: self.read("ready") == 0xA5 and self.read("mode") == 0, 45)
        self.cmd("set videosource GFX9000")
        initial = self.state("mode", "distance", "speed", "laps", "player_x")
        self.check("input-lap-starts-from-reset-title", initial == {"mode": 0, "distance": 0, "speed": 0, "laps": 0, "player_x": 0}, state=initial)
        if initial != {"mode": 0, "distance": 0, "speed": 0, "laps": 0, "player_x": 0}:
            return
        self.tap("space")
        self.key("space", True)
        started, first_frame = self.clock(), self.read("frame_counter")
        samples, sections, active_steering = [], set(), 0
        while self.read("laps") == 0:
            state = self.state("distance", "course_phase", "section", "speed", "player_x", "offroad", "mode", "laps")
            elapsed = self.clock() - started
            if elapsed > 120 or state["mode"] != 1:
                raise RuntimeError(f"Input-only lap did not complete: {state}")
            steering = -1 if state["player_x"] > 6 else (1 if state["player_x"] < -6 else 0)
            if steering != active_steering:
                if active_steering:
                    self.key("left" if active_steering < 0 else "right", False)
                if steering:
                    self.key("left" if steering < 0 else "right", True)
                active_steering = steering
            samples.append({"emulated_seconds": round(elapsed, 4), "steering_key": steering, **state})
            if state["section"] not in sections:
                sections.add(state["section"])
                print("input-only-lap section", state["section"], "at", round(elapsed, 2), "seconds", flush=True)
            self.advance(0.12)
        end, last_frame = self.clock(), self.read("frame_counter")
        self.release_keys()
        self.stop()
        final = self.state("mode", "laps", "distance", "speed", "player_x")
        completed = final["laps"] == 1 and final["mode"] == 1 and final["speed"] == 0 and sections == set(range(8))
        self.check("input-only-complete-course-and-brake-to-stop", completed, final=final, sections=sorted(sections), emulated_seconds=round(end - started, 3), average_fps=round(((last_frame - first_frame) & 65535) / (end - started), 3), maximum_abs_player_x=max(abs(sample["player_x"]) for sample in samples), offroad_samples=sum(sample["offroad"] != 0 for sample in samples), ram_writes=0)
        old_report = json.loads((self.baseline / "verification-v0.2.json").read_text())
        old_lap = next(result for result in old_report["results"] if result["name"] == "input-only-complete-course-and-brake-to-stop")
        elapsed = end - started
        fps = ((last_frame - first_frame) & 65535) / elapsed
        self.check("input-only-lap-faster-without-frame-rate-regression", completed and elapsed <= old_lap["emulated_seconds"] * 0.75 and fps >= 27 and not any(sample["offroad"] for sample in samples), baseline_seconds=old_lap["emulated_seconds"], current_seconds=round(elapsed, 3), elapsed_ratio=round(elapsed / old_lap["emulated_seconds"], 4), average_fps=round(fps, 3), ram_writes=0)
        self.report["full_course_input_only_playthrough"] = completed
        self.report["input_only_lap"] = {"reset_before_start": True, "ram_writes": 0, "controls": "SPACE, left/right keyboard correction, X stop", "samples": samples}
        self.screenshot("04-input-only-lap-finished")
        self.lap_finished = completed

    def run(self) -> int:
        rom = self.output_root / self.manifest["file"]
        raw = rom.read_bytes()
        self.check("512KiB-AB-cartridge-and-hash", len(raw) == 524288 and raw[:2] == b"AB" and hashlib.sha256(raw).hexdigest() == self.manifest["sha256"], bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        for result in preservation_checks(self.baseline, self.manifest):
            result = dict(result)
            self.check(result.pop("name"), result.pop("passed"), **result)
        try:
            for group in (self.verify_input, self.verify_speed_and_car, self.verify_scenarios, self.verify_scenery_probes, self.capture_scenery_transitions, self.capture, self.verify_input_lap):
                try:
                    group()
                except Exception as error:
                    self.report.setdefault("errors", []).append({"group": group.__name__, "message": str(error)})
                    self.check(group.__name__ + "-completed", False, error=str(error))
                    self.release_keys()
        finally:
            try:
                if self.breakpoint:
                    self.cmd(f"debug remove_bp {self.breakpoint}; debug cont")
                self.release_keys()
                if not self.lap_finished:
                    self.seed(mode=0, distance=0, speed=0, player_x=0, laps=0)
            except Exception as error:
                self.report["cleanup_error"] = str(error)
            self.report["passed"] = all(check["passed"] for check in self.results)
            self.report["checks_passed"] = sum(check["passed"] for check in self.results)
            self.report["checks_total"] = len(self.results)
            self.report_path.write_text(json.dumps(self.report, indent=2) + "\n")
        return 0 if self.report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18796)
    parser.add_argument("--capture-frames", type=int, default=96)
    parser.add_argument("--skip-input-lap", action="store_true", help="Skip the fresh-reset, keyboard-only full-course drive")
    parser.add_argument("--only-scenery-transitions", action="store_true", help="Append requested adjacent-phase screenshots to this ROM's completed verification")
    args = parser.parse_args()
    verification = NativeChecks(args.port, args.capture_frames, not args.skip_input_lap)
    if args.only_scenery_transitions:
        verification.append_scenery_transitions()
    else:
        raise SystemExit(verification.run())
