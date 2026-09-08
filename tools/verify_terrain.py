"""Native v0.5 course-shape verification without changing any older verifier.

Inherited v0.4 assertions retain their original thresholds, including the
0.25-second lap-clock comparison. This adapter changes version/output/baseline
selection and uses one persistent HTTP connection to its dedicated emulator.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import zipfile
from pathlib import Path

from PIL import Image

from verify_encounters import EncounterChecks, TIMER_FIELDS, dense_scenery_phase
from compare_speed_car import sprite_tables, indexed_sprite
from check_terrain_scope import preservation_checks

ROOT = Path(__file__).resolve().parents[1]


def portable(value):
    if isinstance(value, dict):
        return {key: portable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [portable(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(ROOT), ".").replace(ROOT.as_posix(), ".")
    return value


class TerrainChecks(EncounterChecks):
    def __init__(self, port: int = 18798, frames: int = 170, input_lap: bool = True):
        # Deliberately do not call or weaken the parent's v0.4-only constructor.
        self.manifest = json.loads((ROOT / "outputs/build-manifest.json").read_text())
        if self.manifest["version"] != "0.5" or not self.manifest["file"].endswith("-v0.5.rom"):
            raise ValueError("This independent terrain verifier exclusively requires v0.5.")
        self.symbols = json.loads((ROOT / "work/build/symbols.json").read_text())
        self.url = f"http://127.0.0.1:{port}"
        self.connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        self.frames, self.input_lap, self.lap_finished = frames, input_lap, False
        self.release = "v0.5"
        self.output_root = ROOT / "outputs"
        self.out = self.output_root / self.release
        self.report_path = self.output_root / "verification-v0.5.json"
        self.baseline = self.output_root / "baseline-v0.4"
        self.shots = self.out / "screenshots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.results, self.breakpoint = [], None
        self.screenshot_evidence = []
        self.report = {
            "rom": self.manifest, "machine": "Panasonic_FS-A1ST", "extension": "gfx9000",
            "physical_hardware_tested": False, "browser_mock_used": False,
            "full_course_input_only_playthrough": False,
            "baseline": "outputs/baseline-v0.4",
            "transport": "One persistent HTTPConnection; each response body is consumed before the next request. No command retry after ambiguous failures.",
            "reused_assertions": "The unchanged v0.4 input, speed, transfer, traffic, UFO, clock, 12-scenario performance and keyboard-only lap assertions. The lap-clock tolerance remains 0.25 seconds.",
            "scenario_seeding": "Named scenario tests and GIF setup explicitly seed RAM. The final full lap starts from hardware reset and sends keyboard input only; its counters are never written by the test.",
            "precision_diagnostic": "An optional additional FPS probe reads emulated time and frame counter in one Tcl response. It does not replace or relax the inherited 12-scenario FPS assertion.",
            "scanout_timing": "Frame-hook RAM can lead the last native scanout by one frame. Only stabilized stills are claimed to depict a particular seeded state.",
            "results": self.results,
        }

    def cmd(self, script: str) -> str:
        script = script.replace("*ALPINE_DRIVE*", "*" + Path(self.manifest["file"]).stem + "*")
        self.connection.request("POST", "/", body=script.encode("utf-8"))
        response = self.connection.getresponse()
        result = response.read().decode("utf-8").strip()
        if response.status != 200:
            raise RuntimeError(result)
        return result

    def screenshot(self, name: str) -> Path:
        path = super().screenshot(name)
        with Image.open(path) as source:
            rgb = source.convert("RGB")
            size, viewport = rgb.size, rgb.getbbox()
        record = {"name": name, "file": path.relative_to(ROOT).as_posix(),
                  "size": list(size), "viewport": list(viewport) if viewport else None,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        self.screenshot_evidence.append(record)
        # A blank640x480 frame seen after an interrupted reset is not valid
        # evidence of this256x212 GFX9000 game. Stop that group explicitly.
        if size != (320, 240) or viewport != (31, 13, 287, 225):
            raise RuntimeError(f"Unexpected native screenshot size/viewport: {record}")
        return path

    def baseline_car_colors(self) -> dict:
        with zipfile.ZipFile(self.baseline / "source-v0.4.zip") as archive:
            atlas = archive.read("assets/vram.bin")
            rect = sprite_tables(archive.read("src/assets.h").decode("ascii"))["driving_car"][1]
        with Image.open(self.baseline / "landscape-000.png") as source:
            image = source.convert("RGB")
            box = image.getbbox()
            if image.size != (320, 240) or box != (31, 13, 287, 225):
                raise ValueError("Baseline car palette reference has an unexpected viewport")
            colors = {}
            for x, y, index in indexed_sprite(atlas, rect):
                if index:
                    color = image.getpixel((box[0]+100+x, box[1]+146+y))
                    if index in colors and colors[index] != color:
                        raise ValueError("Baseline car palette reference is not consistent")
                    colors[index] = color
        return colors

    def verify_car_retained(self) -> None:
        colors = self.baseline_car_colors()
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
                               "file": path.relative_to(ROOT).as_posix()})
            self.check("all-three-native-car-poses-retain-v0.4-pixels-and-size",
                       all(c["opaque_pixels"] > 0 and c["mismatches"] == 0 for c in checks),
                       poses=checks, size=[56, 38], seeded=True)
        finally:
            self.release_keys()
            self.end_frames()

    def verify_clock_cache_pixels(self) -> None:
        # Same cases and pixel criterion as v0.4, with its proper archive.
        colors = self.baseline_car_colors()
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
                          "file": path.relative_to(ROOT).as_posix()})
        self.check("clock-cache-native-digits-carry-and-long-value-clearing",
                   all(all(text == c["expected"] for text in c["strings"].values())
                       and not c["current_mismatched_pixels"] and not c["best_mismatched_pixels"] for c in cases),
                   cases=cases, pixels_checked_per_case=1440, seeded=True)

    def frame_snapshot(self) -> tuple[float, int]:
        raw = self.cmd("list [machine_info time] " + self.read_expr("frame_counter")).split()
        return float(raw[0]), int(raw[1])

    def terrain_traffic_state(self) -> dict:
        """Read the unchanged runtime's actual first-car projection fields."""
        values = {}
        for name, size, signed in (("traffic_gap", 2, False), ("traffic_screen_x", 2, True),
                                   ("traffic_screen_y", 2, True), ("traffic_size", 1, False),
                                   ("traffic_clip", 1, False), ("traffic_visible", 1, False)):
            raw = bytes.fromhex(self.cmd(f"binary encode hex [debug read_block memory {self.address(name)} {size}]"))
            values[name] = int.from_bytes(raw, "little", signed=signed)
        return values

    def verify_terrain_traffic_approach(self) -> None:
        """Native approach traces at the strongest static 230-unit hill masks.

        This is a seeded visibility regression, not a claim that the complete
        course has been exhaustively playtested for every possible actor path.
        """
        course = (ROOT / "assets/course.bin").read_bytes()
        rects = sprite_tables((ROOT / "src/assets.h").read_text())["traffic_car"]
        ranks = sorted(range(1024), key=lambda phase: course[phase*256+241]-course[phase*256+243], reverse=True)
        phases = []
        for phase in ranks:
            if all(min((phase-old)&1023, (old-phase)&1023) >= 64 for old in phases):
                phases.append(phase)
            if len(phases) == 3:
                break
        cases = []
        self.release_keys()
        self.begin_frames()
        try:
            for phase in phases:
                for lane in (-1, 1):
                    distance = phase*4
                    self.seed_quiet(distance=distance, traffic_z0=(distance+240)&4095,
                                    traffic_lane0=lane, player_x=-48*lane, ufo_lap=0)
                    self.key("space", True)
                    trace, first_drawn_gap = [], None
                    for frame in range(61):
                        self.next_frame()
                        state = self.state("distance", "speed", "player_x", "hits", "offroad")
                        native = self.terrain_traffic_state()
                        _, _, width, height = rects[native["traffic_size"]]
                        x, y, clip = native["traffic_screen_x"], native["traffic_screen_y"], native["traffic_clip"]
                        drawn_rows = max(0, min(y, clip, 186)-max(0, y-height))
                        drawn_columns = max(0, min(256, x-width//2+width)-max(0, x-width//2))
                        drawn = native["traffic_visible"] and drawn_rows >= 4 and drawn_columns >= 4
                        if drawn and first_drawn_gap is None:
                            first_drawn_gap = native["traffic_gap"]
                            self.screenshot(f"terrain-traffic-first-{phase}-{lane}")
                        trace.append({"frame": frame, **state, **native,
                                      "drawable_rows": drawn_rows, "drawable_columns": drawn_columns})
                        if native["traffic_gap"] <= 72:
                            self.screenshot(f"terrain-traffic-near-{phase}-{lane}")
                            break
                    self.release_keys()
                    near = [row for row in trace if row["traffic_gap"] <= 120]
                    cases.append({"start_phase": phase, "lane": lane, "first_drawable_gap": first_drawn_gap,
                                  "minimum_warning_frames_before_gap72": None if first_drawn_gap is None else (first_drawn_gap-72)//3,
                                  "passed": first_drawn_gap is not None and first_drawn_gap >= 120 and bool(near)
                                  and all(row["drawable_rows"] >= 4 and row["drawable_columns"] >= 4 for row in near)
                                  and all(row["speed"] == 128 and not row["hits"] and not row["offroad"] for row in trace),
                                  "trace": trace})
            self.check("terrain-crest-traffic-visible-before-contact-range-in-both-lanes",
                       all(row["passed"] for row in cases), cases=cases,
                       required_first_visible_gap=120, collision_maximum_gap=72,
                       phase_selection="Three separated strongest 230-unit hill masks from the current course.", seeded=True)
        finally:
            self.release_keys()
            self.end_frames()

    def verify_terrain_ufo_safety(self) -> None:
        """Exercise both actual active-beam lanes over every trigger-zone phase."""
        cases = []
        self.release_keys()
        self.begin_frames()
        try:
            for phase in range(1550//4, (1749//4)+1):
                for lane in (-1, 1):
                    self.seed_quiet(distance=max(1550, phase*4), speed=0, player_x=-48*lane,
                                    ufo_state=3, ufo_timer=60, ufo_lane=lane, ufo_lap=0)
                    self.next_frame()
                    safe = self.state("player_x", "ufo_catches", "lift_timer", "offroad", "mode")
                    profile = bytes.fromhex(self.cmd(f"binary encode hex [debug read_block memory {self.address('profile')} 128]"))
                    width, half = profile[121], profile[121] >> 1
                    center = 128 + int.from_bytes(profile[120:121], signed=True) - int(safe["player_x"]*half/64)
                    car_center = 128 + int(safe["player_x"]/4)
                    margin = abs(center+lane*half-car_center)-42
                    road_margin = min(car_center-28-(center-width), center+width-(car_center+28))
                    self.seed_quiet(distance=max(1550, phase*4), speed=0, player_x=48*lane,
                                    ufo_state=3, ufo_timer=60, ufo_lane=lane, ufo_lap=0)
                    self.next_frame()
                    hazard = self.state("ufo_catches", "lift_timer", "speed", "mode")
                    cases.append({"phase": phase, "beam_lane": lane, "safe_state": safe, "hazard_state": hazard,
                                  "safe_collision_margin_pixels": margin, "safe_car_road_margin_pixels": road_margin,
                                  "passed": safe["ufo_catches"] == safe["lift_timer"] == safe["offroad"] == 0
                                  and safe["mode"] == 1 and margin >= 0 and road_margin >= 0
                                  and hazard == {"ufo_catches": 1, "lift_timer": 30, "speed": 0, "mode": 1}})
            for lane in (-1, 1):
                worst = min((row for row in cases if row["beam_lane"] == lane), key=lambda row: row["safe_collision_margin_pixels"])
                self.seed_quiet(distance=max(1550, worst["phase"]*4), speed=0, player_x=-48*lane,
                                ufo_state=3, ufo_timer=60, ufo_lane=lane, ufo_lap=0)
                self.next_frame(3)
                self.screenshot(f"terrain-ufo-safe-{lane}")
            self.check("terrain-entire-ufo-trigger-zone-retains-both-alternating-safe-sides",
                       all(row["passed"] for row in cases), cases=cases, seeded=True,
                       covered_distance=[1550, 1749], safe_player_offset=48, beam_capture_threshold_pixels=42)
        finally:
            self.release_keys()
            self.end_frames()

    def verify_atomic_fps(self) -> None:
        """Additional precision evidence; the older FPS checks stay intact."""
        cases = [("section-6", 3072, -48),
                 ("dense-center", dense_scenery_phase(0)*4, 0)]
        if self.report.get("section_frame_rates"):
            slowest = min(self.report["section_frame_rates"], key=lambda row: row["fps"])
            cases.append(("slowest-inherited-probe", slowest["distance"], slowest["state"]["player_x"]))
        samples = []
        self.release_keys()
        try:
            for name, distance, player_x in cases:
                self.seed_quiet(distance=distance, player_x=player_x,
                                traffic_z0=(distance+110)&4095, traffic_z1=(distance+350)&4095,
                                traffic_z2=(distance+650)&4095)
                self.key("space", True)
                self.advance(0.12)
                t0, f0 = self.frame_snapshot()
                self.advance(2.0)
                t1, f1 = self.frame_snapshot()
                samples.append({"name": name, "distance": distance, "player_x": player_x,
                                "fps": round(((f1-f0)&65535)/(t1-t0), 3),
                                "emulated_seconds": round(t1-t0, 6), "completed_frames": (f1-f0)&65535})
                self.release_keys()
        finally:
            self.release_keys()
        self.report["atomic_frame_rate_diagnostics"] = samples
        self.check("additional-atomic-time-and-frame-counter-fps", all(row["fps"] >= 27 for row in samples),
                   samples=samples, replaces_inherited_measurement=False, seeded=True)

    def capture_crest_review(self) -> None:
        """Bounded art review capture, separate from the acceptance suite."""
        self.shots = ROOT / "work/crest-review"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.reset_title()
        self.begin_frames()
        states, pictures, timestamps, stills = [], [], [], []
        try:
            for phase in (0, 48, 96, 144, 224, 300):
                self.seed_quiet(distance=phase*4, speed=0, ufo_lap=0)
                self.next_frame(2)
                path = self.screenshot(f"phase-{phase:03d}")
                stills.append({"phase": phase, "state": self.state(), "file": path.relative_to(ROOT).as_posix()})
            self.seed_quiet(distance=334, speed=128, ufo_lap=0)
            self.key("space", True)
            # Let the native scanout replace the previous seeded still before
            # saving frame0. The frame hook's RAM can lead scanout by a frame.
            self.next_frame(2)
            for index in range(28):
                path = self.screenshot(f"crest-{index:03d}")
                with Image.open(path) as source:
                    pictures.append(source.convert("RGB"))
                timestamps.append(self.clock())
                states.append(self.state("distance", "course_phase", "speed", "player_x", "hill", "ufo_state"))
                self.next_frame()
        finally:
            self.release_keys()
            self.end_frames()
        durations, total = [], 0
        for index in range(len(pictures)):
            end = timestamps[index+1] if index+1 < len(pictures) else timestamps[index]+timestamps[index]-timestamps[index-1]
            rounded = round((end-timestamps[0])*100)*10
            durations.append(max(10, rounded-total))
            total = rounded
        gif = self.shots / "crest-native.gif"
        pictures[0].save(gif, save_all=True, append_images=pictures[1:], duration=durations, loop=0, optimize=False)
        with Image.open(gif) as decoded:
            exact = decoded.n_frames == len(pictures)
            if exact:
                for index, picture in enumerate(pictures):
                    decoded.seek(index)
                    exact = exact and decoded.convert("RGB").tobytes() == picture.tobytes() and decoded.info.get("duration") == durations[index]
        self.check("crest-review-native-gif-pixels-and-timing", exact, frames=len(pictures), duration_ms=total)
        capture = {"rom_sha256": self.manifest["sha256"], "seeded": True,
                   "setup": "Each still seeds its distance with speed0. The continuous run seeds distance334/speed128, then SPACE only.",
                   "scanout_note": "Two initial completed frames exclude the previous still. Recorded frame-hook RAM may lead native scanout by one frame.",
                   "still_scenarios": stills, "states": states, "timestamps": timestamps,
                   "gif": gif.relative_to(ROOT).as_posix(), "gif_sha256": hashlib.sha256(gif.read_bytes()).hexdigest(),
                   "frames": len(pictures), "native_pixels_and_timing_exact": exact,
                   "emulated_seconds": timestamps[-1]-timestamps[0], "gif_duration_ms": total,
                   "screenshots": self.screenshot_evidence, "physical_hardware_tested": False}
        (self.shots / "crest-review.json").write_text(json.dumps(portable(capture), indent=2)+"\n")
        self.report["crest_review"] = capture

    def capture_scenic_drive(self) -> None:
        """Seven native seconds before the first surprise, keyboard-driven."""
        self.reset_title()
        self.tap("space")
        self.begin_frames()
        pictures, timestamps, states = [], [], []
        active_steering = 0
        try:
            # Only these two initial RAM fields are written. Traffic, events,
            # counters and clock remain their normal reset-to-start values.
            self.seed(distance=0, speed=128)
            self.key("space", True)
            self.next_frame(3)
            for index in range(210):
                state = self.state()
                close = sorted(((state[f"traffic_z{i}"]-state["distance"])&4095, state[f"traffic_lane{i}"])
                               for i in range(3) if ((state[f"traffic_z{i}"]-state["distance"])&4095) < 340)
                target = -48*close[0][1] if close else 0
                steering = -1 if state["player_x"] > target+5 else (1 if state["player_x"] < target-5 else 0)
                if steering != active_steering:
                    if active_steering:
                        self.key("left" if active_steering < 0 else "right", False)
                    if steering:
                        self.key("left" if steering < 0 else "right", True)
                    active_steering = steering
                path = self.screenshot(f"scenic-{index:03d}")
                with Image.open(path) as source:
                    pictures.append(source.convert("RGB"))
                timestamps.append(self.clock())
                states.append({"steering_key": steering, "target_player_x": target, **state})
                self.next_frame()
        finally:
            self.release_keys()
            self.end_frames()
        durations, total = [], 0
        for index in range(len(pictures)):
            end = timestamps[index+1] if index+1 < len(pictures) else timestamps[index]+timestamps[index]-timestamps[index-1]
            rounded = round((end-timestamps[0])*100)*10
            durations.append(max(10, rounded-total))
            total = rounded
        gif = self.out / "scenic-drive.gif"
        pictures[0].save(gif, save_all=True, append_images=pictures[1:], duration=durations, loop=0, optimize=False)
        distinct = len({hashlib.sha256(picture.tobytes()).hexdigest() for picture in pictures})
        with Image.open(gif) as decoded:
            exact = decoded.n_frames == len(pictures)
            if exact:
                for index, picture in enumerate(pictures):
                    decoded.seek(index)
                    exact = exact and decoded.convert("RGB").tobytes() == picture.tobytes() and decoded.info.get("duration") == durations[index]
        elapsed = timestamps[-1]-timestamps[0]
        self.check("scenic-drive-native-gif-pixels-and-timing", exact, frames=len(pictures), duration_ms=total)
        self.check("scenic-drive-shows-moving-terrain-without-event-spoilers", distinct == len(pictures)
                   and all(state["ufo_state"] == 0 and state["distance"] < 1450 for state in states)
                   and max(state["hill"] for state in states)-min(state["hill"] for state in states) >= 10,
                   distinct_frames=distinct, distance_range=[states[0]["distance"], states[-1]["distance"]],
                   hill_range=[min(state["hill"] for state in states), max(state["hill"] for state in states)])
        self.check("scenic-drive-remains-fast-and-clear-with-keyboard-control", all(state["speed"] == 128
                   and not state["hits"] and not state["offroad"] for state in states)
                   and (len(pictures)-1)/elapsed >= 27,
                   fps=round((len(pictures)-1)/elapsed, 3), initial_seed_fields=["distance", "speed"], later_ram_writes=0)
        capture = {"rom_sha256": self.manifest["sha256"], "file": gif.relative_to(ROOT).as_posix(),
                   "gif_sha256": hashlib.sha256(gif.read_bytes()).hexdigest(),
                   "frames": len(pictures), "distinct_frames": distinct, "duration_ms": total,
                   "emulated_seconds": elapsed, "fps": (len(pictures)-1)/elapsed,
                   "native_pixels_and_timing_exact": exact, "timestamps": timestamps, "states": states,
                   "initial_ram_seed": {"distance": 0, "speed": 128}, "later_ram_writes": 0,
                   "initial_scanout_stabilization_frames": 3,
                   "controls": "SPACE and left/right steering; ordinary traffic retained. No event or clock fields changed.",
                   "scanout_note": "Recorded frame-hook RAM may lead native scanout by one frame.",
                   "physical_hardware_tested": False,
                   "screenshots": [row for row in self.screenshot_evidence if row["name"].startswith("scenic-")]}
        (self.out / "scenic-capture.json").write_text(json.dumps(portable(capture), indent=2)+"\n")
        self.report["scenic_capture"] = capture

    def run(self, only: str = "all") -> int:
        for result in preservation_checks(self.baseline, self.manifest):
            result = dict(result)
            self.check(result.pop("name"), result.pop("passed"), **result)
        groups = (self.verify_input, self.verify_motion, self.verify_course_transfer,
                  self.verify_car_retained, self.verify_traffic, self.verify_ufo,
                  self.verify_terrain_traffic_approach, self.verify_terrain_ufo_safety,
                  self.verify_lap_clock, self.verify_performance, self.verify_atomic_fps,
                  self.capture_encounters, self.verify_input_lap)
        selected = {
            "performance": (self.verify_performance, self.verify_atomic_fps),
            "events": (self.verify_motion, self.verify_traffic, self.verify_ufo, self.verify_lap_clock),
            "clock": (self.verify_lap_clock,), "transfer": (self.verify_course_transfer,),
            "terrain": (self.verify_terrain_traffic_approach, self.verify_terrain_ufo_safety),
            "crest": (self.capture_crest_review,),
            "scenic": (self.capture_scenic_drive,),
            "visuals": (self.verify_car_retained, self.verify_lap_clock),
        }
        groups = selected.get(only, groups)
        try:
            if only == "all":
                try:
                    self.reset_title()
                except Exception as error:
                    self.report.setdefault("errors", []).append({"group": "reset_title", "message": str(error)})
                    self.check("initial-title-reset-completed", False, error=str(error))
                    self.report["aborted_after_group"] = "reset_title"
                    groups = ()
            for group in groups:
                try:
                    group()
                except Exception as error:
                    self.report.setdefault("errors", []).append({"group": group.__name__, "message": str(error)})
                    self.check(group.__name__ + "-completed", False, error=str(error))
                    # Do not seed later scenarios into an interrupted/reset
                    # emulator and accidentally call those results valid.
                    self.report["aborted_after_group"] = group.__name__
                    break
        finally:
            try:
                self.end_frames()
                self.release_keys()
            except Exception as error:
                self.report["cleanup_error"] = str(error)
            self.connection.close()
            self.report["screenshot_evidence"] = self.screenshot_evidence
            self.report["passed"] = all(row["passed"] for row in self.results)
            self.report["checks_passed"] = sum(row["passed"] for row in self.results)
            self.report["checks_total"] = len(self.results)
            path = self.report_path if only == "all" else self.out / (only + "-verification.json")
            text = json.dumps(portable(self.report), indent=2) + "\n"
            path.write_text(text)
            # Preserve each run separately; no retry-until-pass loop is used.
            evidence = self.out / (only + "-" + self.manifest["sha256"][:12] + "-verification.json")
            if evidence.exists():
                suffix = 2
                while evidence.with_stem(evidence.stem + f"-attempt-{suffix}").exists():
                    suffix += 1
                evidence = evidence.with_stem(evidence.stem + f"-attempt-{suffix}")
            evidence.write_text(text)
        return 0 if self.report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18798)
    parser.add_argument("--capture-frames", type=int, default=170)
    parser.add_argument("--skip-input-lap", action="store_true")
    parser.add_argument("--only", choices=("all", "performance", "events", "clock", "visuals", "transfer", "terrain", "crest", "scenic"), default="all")
    args = parser.parse_args()
    raise SystemExit(TerrainChecks(args.port, args.capture_frames, not args.skip_input_lap).run(args.only))
