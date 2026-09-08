"""Exact native A/B pixels for a rendering-only optimization.

Capture each ROM separately on the already-running dedicated emulator, using
its own build directory. Never launches, replaces or rebuilds a cartridge.
The comparison is offline and never weakens an older gameplay verifier.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
from pathlib import Path

from PIL import Image, ImageChops

from verify_encounters import EncounterChecks, FIELDS, TEST_ONLY_FIELDS

ROOT = Path(__file__).resolve().parents[1]
A_SHA = "8849a4e19fb97fec44f5276026543079ec0529271141e09be6a33d8f42a58606"
EXTRA_FIELDS = {"notice": 1, "notice_timer": 1, "cached_passes": 2, "old_keys": 1}
DEPTHS = (28, 32, 36, 42, 50, 60, 72, 86, 102, 124, 150, 184, 230, 292, 380, 512)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def portable(value):
    if isinstance(value, dict):
        return {key: portable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [portable(item) for item in value]
    if isinstance(value, str):
        return value.replace(str(ROOT), ".").replace(ROOT.as_posix(), ".")
    return value


def scenarios():
    cases = [{"name": "startup-title", "phase": 0, "x": 0, "display_mode": 0, "speed": 0}]
    phases = (0, 48, 85, 95, 96, 104, 105, 114, 115, 127, 144, 224, 256,
              300, 384, 437, 446, 456, 512, 640, 752, 778, 787, 797, 1023)
    for phase in phases:
        for x in (-144, -105, -48, 0, 48, 105, 144):
            cases.append({"name": f"road-{phase:04d}-{x:+04d}", "phase": phase, "x": x})
    for phase in (0, 96, 640):
        for x in (-104, -96, -1, 1, 96, 104):
            cases.append({"name": f"boundary-{phase:04d}-{x:+04d}", "phase": phase, "x": x})
    for phase, speed in ((96, 128), (640, 64)):
        for pose in ("left", "straight", "right"):
            cases.append({"name": f"car-{phase}-{pose}", "phase": phase, "x": 0,
                          "speed": speed, "pose": pose})
    for tenths in (0, 599, 600, 59999, 60000, 4294967295):
        cases.append({"name": f"HUD-{tenths}", "phase": 224, "x": -48,
                      "time": tenths, "passes": 999, "best_valid": 1})
    for phase in (96, 640):
        for index, depth in enumerate(DEPTHS):
            cases.append({"name": f"traffic-{phase}-{depth}", "phase": phase, "x": -48 if index&1 else 48,
                          "traffic": depth, "traffic_lane": 1 if index&1 else -1})
    for index, (state, timer) in enumerate(((1,30), (1,15), (2,45), (2,36), (2,20), (3,60), (3,29), (4,30), (4,10))):
        for lane in (-1, 1):
            cases.append({"name": f"UFO-{state}-{timer}-{lane}", "phase": (387,437,500,640)[index%4],
                          "x": lane*48, "ufo_state": state, "ufo_timer": timer, "ufo_lane": lane,
                          "traffic": 124, "traffic_lane": -lane})
    for lift in (30, 25, 15, 5):
        cases.append({"name": f"capture-lift-{lift}", "phase": 500, "x": 24,
                      "ufo_state": 3, "ufo_timer": 29, "ufo_lane": 1, "lift": lift, "caught": 1})
    for phase in (0, 96, 640):
        cases.append({"name": f"pause-{phase}", "phase": phase, "x": 0, "display_mode": 2})
    return cases


class RenderCapture(EncounterChecks):
    def __init__(self, source_root: Path, port: int):
        # Own initialization: neither older constructor nor its version guard
        # is edited or monkey-patched. source_root is an actual build root.
        self.source_root = source_root.resolve()
        self.manifest = json.loads((self.source_root / "outputs/build-manifest.json").read_text())
        if self.manifest["version"] != "0.5":
            raise ValueError("Render equivalence requires the independently built v0.5 ROM.")
        self.rom_path = self.source_root / "outputs" / self.manifest["file"]
        self.rom = self.rom_path.read_bytes()
        if len(self.rom) != 524288 or sha(self.rom) != self.manifest["sha256"]:
            raise ValueError("ROM and build manifest differ")
        self.symbols = json.loads((self.source_root / "work/build/symbols.json").read_text())
        self.listing = (self.source_root / "work/build/game.lst").read_text()
        local = {name: int(address, 16) for address, name in
                 re.findall(r"^\s*([0-9A-Fa-f]{8})\s+\d+\s+(_\w+)::?\s*$", self.listing, re.M)}
        code_base = self.symbols["_frame_done"] - local["_frame_done"]
        self.draw_symbols = {name: code_base+local["_"+name]
                             for name in ("draw_sky", "draw_road", "draw_objects", "draw_encounter_world", "draw_ui")}
        self.draw_symbols.update(gfx_flip=self.symbols["_gfx_flip"], frame_done=self.symbols["_frame_done"])
        self.connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        self.url = f"http://127.0.0.1:{port}"
        self.breakpoint = None
        self.hooks = []
        self.results = []

    def cmd(self, script):
        self.connection.request("POST", "/", body=script.encode("utf-8"))
        response = self.connection.getresponse()
        result = response.read().decode("utf-8").strip()
        if response.status != 200:
            raise RuntimeError(result)
        return result

    def seed(self, **values):
        commands = []
        for name, value in values.items():
            width = FIELDS.get(name, TEST_ONLY_FIELDS.get(name, EXTRA_FIELDS.get(name)))
            if width is None:
                raise KeyError(name)
            for index in range(width):
                commands.append(f"debug write memory {self.address(name)+index} {(value >> (8*index)) & 255}")
        # Every write is made while debug-breaked, never during a live frame.
        if self.cmd("debug breaked") != "1":
            raise RuntimeError("Deterministic seed requires a stopped frame hook")
        self.cmd("; ".join(commands))

    def identity(self):
        expected = hashlib.sha1(self.rom).hexdigest()
        found = self.cmd("set render_rom_ids {}; foreach render_device [machine_info device] {set render_info [machine_info device $render_device]; if {[dict exists $render_info actualSHA1]} {lappend render_rom_ids [dict get $render_info actualSHA1]}}; set render_rom_ids").lower().split()
        if expected not in found:
            raise RuntimeError(f"Wrong loaded ROM; expected SHA1 {expected}; native reports {found}")
        if self.cmd("machine_info config_name") != "Panasonic_FS-A1ST":
            raise RuntimeError("Wrong target machine")
        for name, address in self.draw_symbols.items():
            actual = bytes.fromhex(self.cmd(f"binary encode hex [debug read_block memory {address} 12]"))
            offset = 8192+address-0x8000
            if actual != self.rom[offset:offset+12]:
                raise RuntimeError(f"Untrusted symbol/ROM mapping for {name} at {address:04x}")
        return {"sha1": expected, "sha256": self.manifest["sha256"],
                "emulator": self.cmd("openmsx_info version"), "machine": "Panasonic_FS-A1ST",
                "draw_symbols": self.draw_symbols, "listing_sha256": sha(self.listing.encode())}

    def set_hooks(self, names):
        for name in names:
            address = self.draw_symbols[name]
            self.hooks.append(self.cmd(f"debug set_bp {address} {{}} {{set render_probe_stage {name}; debug break}}"))

    def resume_to_hook(self):
        self.cmd("debug cont")
        self.until(lambda: self.cmd("debug breaked") == "1")
        raw = self.cmd("list $render_probe_stage [machine_info time]").split()
        return raw[0], float(raw[1])

    def start(self, stages=("draw_sky", "frame_done")):
        self.reset_title()
        identity = self.identity()
        self.set_hooks(("frame_done",))
        self.until(lambda: self.cmd("debug breaked") == "1")
        self.set_hooks(tuple(name for name in stages if name != "frame_done"))
        return identity

    def cleanup(self):
        try:
            self.release_keys()
            for hook in self.hooks:
                self.cmd(f"debug remove_bp {hook}")
            self.hooks.clear()
            self.cmd("debug cont")
        finally:
            self.connection.close()

    def freeze_case(self, case):
        self.release_keys()
        pose = case.get("pose", "straight")
        if pose != "straight":
            self.key(pose, True)
        distance = case["phase"]*4
        self.seed_quiet(mode=2, distance=distance, speed=case.get("speed", 128), player_x=case["x"],
                        frame_counter=1, offroad=int(abs(case["x"]) > 104), old_keys=0,
                        traffic_z0=(distance+case.get("traffic", 2300))&4095,
                        traffic_z1=(distance+380)&4095, traffic_z2=(distance+150)&4095,
                        traffic_lane0=case.get("traffic_lane", 1), traffic_lane1=-1, traffic_lane2=1,
                        ufo_state=case.get("ufo_state", 0), ufo_timer=case.get("ufo_timer", 0),
                        ufo_lane=case.get("ufo_lane", 1), ufo_caught=case.get("caught", 0),
                        lift_timer=case.get("lift", 0), event_tick=32,
                        notice=0, notice_timer=0, passes=case.get("passes", 123), cached_passes=65535,
                        lap_current_tenths=case.get("time", 1234), lap_best_tenths=case.get("time", 987),
                        lap_last_tenths=0, lap_last_valid=0, lap_best_valid=case.get("best_valid", 1),
                        lap_previous_mode=2, lap_previous_laps=0, lap_tick_fraction=0)

    def frozen_frame(self, display_mode=1, profile=False):
        self.seed(mode=2, lap_previous_mode=2)
        marks = []
        while True:
            stage, now = self.resume_to_hook()
            marks.append((stage, now))
            if stage == "draw_sky":
                self.seed(mode=display_mode)
            elif stage == "frame_done":
                break
        return marks

    def native_image(self, path):
        self.cmd(f"openmsx::internal_screenshot -raw {{{path.as_posix()}}}")
        with Image.open(path) as source:
            result = source.convert("RGB")
        if result.size != (320, 240) or result.getbbox() != (31, 13, 287, 225):
            raise RuntimeError("Invalid native size/viewport; black or non-GFX9000 capture")
        return result

    def capture(self, out: Path, limit=0):
        out.mkdir(parents=True, exist_ok=True)
        if (out / "capture.json").exists():
            raise ValueError("Capture already exists; choose a new directory to preserve it")
        report = {"protocol": "mode2 simulation freeze; mode changes only to requested display mode at draw_sky entry, after update/events/clock. Three settled complete frames precede capture; fourth frame must be pixel-identical.",
                  "physical_hardware_tested": False, "seeded": True, "samples": [], "passed": False}
        try:
            report["identity"] = self.start()
            cases = scenarios()
            if limit:
                cases = cases[:limit]
            report["scenario_digest"] = sha(json.dumps(cases, sort_keys=True).encode())
            for case in cases:
                self.freeze_case(case)
                for _ in range(3):
                    self.frozen_frame(case.get("display_mode", 1))
                first_path = out / (case["name"]+".png")
                first = self.native_image(first_path)
                state = self.state()
                self.frozen_frame(case.get("display_mode", 1))
                stable_path = out / (case["name"]+"-stable.png")
                stable = self.native_image(stable_path)
                exact = first.tobytes() == stable.tobytes()
                report["samples"].append({"name": case["name"], "case": case, "state": state,
                                          "file": first_path.name, "stable_file": stable_path.name,
                                          "png_sha256": sha(first_path.read_bytes()), "rgb_sha256": sha(first.tobytes()),
                                          "size": list(first.size), "stable_after_three_frames": exact})
                print(case["name"], "STABLE" if exact else "UNSTABLE", flush=True)
                if not exact:
                    raise RuntimeError("Native scanout did not settle for " + case["name"])
            report["passed"] = True
        except Exception as error:
            report["error"] = str(error)
            raise
        finally:
            self.cleanup()
            (out / "capture.json").write_text(json.dumps(portable(report), indent=2)+"\n")
        return report

    def profile(self, out: Path, frames=10):
        order = ("draw_sky", "draw_road", "draw_objects", "draw_encounter_world", "draw_ui", "gfx_flip", "frame_done")
        report = {"seeded": True, "phase": 670, "player_x": -48, "frames": [], "timing": "Emulated time between existing function-entry breakpoints. Includes pending GPU command waits; not a pure CPU instruction profile."}
        try:
            report["identity"] = self.start(order)
            self.freeze_case({"phase": 670, "x": -48, "traffic": 110, "ufo_state": 0})
            for index in range(frames+3):
                marks = self.frozen_frame()
                if index < 3:
                    continue
                if [name for name, _ in marks] != list(order):
                    raise RuntimeError("Unexpected profile sequence: " + str(marks))
                report["frames"].append({marks[i][0]: (marks[i+1][1]-marks[i][1])*1000 for i in range(len(marks)-1)})
            report["mean_ms"] = {name: sum(row[name] for row in report["frames"])/frames for name in order[:-1]}
            print(json.dumps(report["mean_ms"], indent=2), flush=True)
        finally:
            self.cleanup()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(portable(report), indent=2)+"\n")
        return report

    def profile_wait(self, out: Path, frames=10):
        """Time one entry/exit per busy-wait, never stop on each IN iteration."""
        listing = (self.source_root / "work/build/hardware.lst").read_text()
        local_span = int(re.search(r"^\s*([0-9A-Fa-f]{8})\s+\d+\s+_gfx_span::", listing, re.M)[1], 16)
        local_wait = int(re.search(r"^\s*([0-9A-Fa-f]{8})\s+\d+\s+span_wait:", listing, re.M)[1], 16)
        base = self.symbols["_gfx_span"]-local_span
        wait = base+local_wait
        # This diagnostic intentionally recognizes the current six-byte
        # IN/AND/JR loop instead of guessing an address after a code change.
        offset = 8192+wait-0x8000
        if self.rom[offset:offset+8] != bytes.fromhex("db65e60120fa3e24"):
            raise ValueError("Unsupported span wait loop; inspect its new assembly first")
        report = {"phase": 670, "player_x": -48, "frames": [],
                  "timing": "Emulated duration of each gfx_span IN/AND/JR status wait, first entry to first instruction after the loop. Conditional breakpoint actions only record emulated timestamps, without stopping every iteration."}
        try:
            report["identity"] = self.start()
            self.freeze_case({"phase": 670, "x": -48, "traffic": 110, "ufo_state": 0})
            self.cmd("set render_waiting 0; set render_wait_times {}")
            self.hooks.append(self.cmd(f"debug set_bp {wait} {{$render_waiting == 0}} {{set render_waiting 1; set render_wait_start [machine_info time]}}"))
            self.hooks.append(self.cmd(f"debug set_bp {wait+6} {{}} {{lappend render_wait_times [expr {{1000*([machine_info time]-$render_wait_start)}}]; set render_waiting 0}}"))
            for index in range(frames+3):
                self.cmd("set render_wait_times {}")
                self.frozen_frame()
                if index >= 3:
                    times = [float(value) for value in self.cmd("set render_wait_times").split()]
                    report["frames"].append({"wait_count": len(times), "total_wait_ms": sum(times),
                                              "max_wait_ms": max(times, default=0), "waits_ms": times})
            report["mean_wait_ms"] = sum(row["total_wait_ms"] for row in report["frames"])/frames
            print(json.dumps({"mean_wait_ms": report["mean_wait_ms"], "counts": [row["wait_count"] for row in report["frames"]]}), flush=True)
        finally:
            self.cleanup()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(portable(report), indent=2)+"\n")
        return report


def compare(reference: Path, candidate: Path, out: Path):
    old = json.loads((reference / "capture.json").read_text())
    new = json.loads((candidate / "capture.json").read_text())
    if old["identity"]["sha256"] != A_SHA:
        raise ValueError("Reference must be preserved candidate A, not another optimized ROM")
    if not old["passed"] or not new["passed"] or old["scenario_digest"] != new["scenario_digest"]:
        raise ValueError("Incomplete or different capture protocols")
    rows = []
    out.parent.mkdir(parents=True, exist_ok=True)
    for a, b in zip(old["samples"], new["samples"]):
        with Image.open(reference/a["file"]) as image:
            left = image.convert("RGB")
        with Image.open(candidate/b["file"]) as image:
            right = image.convert("RGB")
        mismatch = sum(x != y for x, y in zip(left.getdata(), right.getdata()))
        difference = ImageChops.difference(left, right).getbbox()
        # Hardware timer internals are not included in state(). Frame counts
        # are reproducibly seeded; every visible gameplay field must match.
        state_equal = a["state"] == b["state"]
        rows.append({"name": a["name"], "pixels": left.width*left.height,
                     "mismatched_pixels": mismatch, "difference_bbox": difference,
                     "native_state_equal": state_equal, "passed": not mismatch and state_equal,
                     "reference_rgb_sha256": a["rgb_sha256"], "candidate_rgb_sha256": b["rgb_sha256"]})
    report = {"reference_sha256": old["identity"]["sha256"], "candidate_sha256": new["identity"]["sha256"],
              "scenario_digest": old["scenario_digest"], "protocol": old["protocol"],
              "physical_hardware_tested": False, "results": rows, "checks_total": len(rows),
              "checks_passed": sum(row["passed"] for row in rows), "passed": all(row["passed"] for row in rows),
              "total_native_pixels_compared": sum(row["pixels"] for row in rows)}
    out.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    capture_parser = sub.add_parser("capture")
    capture_parser.add_argument("--source-root", type=Path, default=ROOT)
    capture_parser.add_argument("--port", type=int, default=18798)
    capture_parser.add_argument("--out", type=Path, required=True)
    capture_parser.add_argument("--limit", type=int, default=0, help="Smoke test only; full comparison uses every scenario.")
    profile_parser = sub.add_parser("profile")
    profile_parser.add_argument("--source-root", type=Path, default=ROOT)
    profile_parser.add_argument("--port", type=int, default=18798)
    profile_parser.add_argument("--out", type=Path, required=True)
    wait_parser = sub.add_parser("profile-wait")
    wait_parser.add_argument("--source-root", type=Path, default=ROOT)
    wait_parser.add_argument("--port", type=int, default=18798)
    wait_parser.add_argument("--out", type=Path, required=True)
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("--reference", type=Path, required=True)
    compare_parser.add_argument("--candidate", type=Path, required=True)
    compare_parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "compare":
        raise SystemExit(compare(args.reference.resolve(), args.candidate.resolve(), args.out.resolve()))
    instance = RenderCapture(args.source_root, args.port)
    if args.action == "profile":
        instance.profile(args.out.resolve())
    elif args.action == "profile-wait":
        instance.profile_wait(args.out.resolve())
    else:
        instance.capture(args.out.resolve(), args.limit)
