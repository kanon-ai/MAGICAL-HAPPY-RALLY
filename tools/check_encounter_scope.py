"""Audit v0.4 additions against the immutable v0.3 cartridge baseline.

This is a source/assets preservation check, not an emulator or hardware test.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

from compare_speed_car import sprite_tables

ROOT = Path(__file__).resolve().parents[1]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def c_function(source: str, name: str) -> str:
    match = re.search(r"\b" + re.escape(name) + r"\s*\(", source)
    if match is None:
        raise ValueError(f"Missing C function {name}")
    opening = source.index("{", match.end())
    level = 1
    for end in range(opening + 1, len(source)):
        level += (source[end] == "{") - (source[end] == "}")
        if not level:
            return source[match.start():end + 1]
    raise ValueError(f"Unclosed C function {name}")


def preservation_checks(baseline: Path, manifest: dict) -> list[dict]:
    hashes = json.loads((baseline / "SHA256.json").read_text())
    mismatches = [name for name, expected in hashes.items()
                  if digest((baseline / name).read_bytes()) != expected]
    checks = [{"name": "v0.3-baseline-files-preserved", "passed": not mismatches,
               "files": len(hashes), "mismatches": mismatches}]
    with zipfile.ZipFile(baseline / "source-v0.3.zip") as archive:
        old_game = archive.read("src/game.c").decode("utf-8").replace("\r\n", "\n")
        game = (ROOT / "src/game.c").read_text(encoding="utf-8").replace("\r\n", "\n")
        names = ("update", "camera_shift", "draw_sky", "draw_road", "frame_done")
        changed = [name for name in names if c_function(old_game, name) != c_function(game, name)]
        checks.append({"name": "base-driving-road-and-background-functions-preserved",
                       "passed": not changed, "functions": list(names), "changed": changed})
        # Explicitly approved follow-up: replace only the 256-byte RAM copy.
        # Reconstruct the former loop/declaration and require the rest of
        # load_course to match exactly, including mapper and phase selection.
        old_load, load = c_function(old_game, "load_course"), c_function(game, "load_course")
        call = "copy_course_profile(src);"
        former_loop = "for(i=0;i<256;++i)profile[i]=src[i];"
        restored = load.replace(call, former_loop).replace("    const u8 *src;", "    u16 i;\n    const u8 *src;")
        expected_helper = """copy_course_profile(const u8 *src) __naked{
    src;
    __asm
    ld de,#_profile
    ld bc,#256
    ldir
    ret
    __endasm;
}"""
        helper = c_function(game, "copy_course_profile")
        canonical = lambda source: re.sub(r"\s+", "", source)
        exact_helper = canonical(helper) == canonical(expected_helper)
        exact_declaration = "staticvoid" + canonical(expected_helper) in canonical(game)
        checks.append({"name": "approved-course-copy-is-exact-256-byte-LDIR-only",
                       "passed": load.count(call) == 1 and restored == old_load and exact_helper and exact_declaration,
                       "load_course_other_logic_preserved": restored == old_load,
                       "helper_exact": exact_helper and exact_declaration,
                       "approved_change": "SDCC call1 HL source; DE=_profile; BC=256; LDIR; RET. No source bytes, geometry, bank selection or input changes."})
        protected = ("src/hardware.c", "src/hardware.h", "src/boot.asm", "src/palette.h",
                     "src/scenery.h", "assets/scenery.bin", "tools/verify_drive.py", "tools/compare_speed_car.py")
        changed = [path for path in protected if archive.read(path) != (ROOT / path).read_bytes()]
        checks.append({"name": "v0.3-hardware-palette-near-scenery-and-verifiers-preserved",
                       "passed": not changed, "files": list(protected), "changed": changed})
        old_course, course = archive.read("assets/course.bin"), (ROOT / "assets/course.bin").read_bytes()
        changed_profiles = [i // 256 for i in range(0, len(course), 256)
                            if old_course[i:i + 192] != course[i:i + 192]]
        checks.append({"name": "all-1024-road-and-existing-scenery-profiles-preserved",
                       "passed": len(course) == len(old_course) == 262144 and not changed_profiles,
                       "profile_bytes_preserved": 192, "new_projection_bytes": 64,
                       "changed_profiles": changed_profiles})
        old_tables = sprite_tables(archive.read("src/assets.h").decode("ascii"))
        tables = sprite_tables((ROOT / "src/assets.h").read_text())
        old_atlas, atlas = archive.read("assets/vram.bin"), (ROOT / "assets/vram.bin").read_bytes()
        added = {name: rows for name, rows in tables.items() if name not in old_tables}
        allowed_pixels, allowed_bytes = set(), set()
        for rows in added.values():
            for sx, sy, width, height in rows:
                for y in range(sy, sy + height):
                    for x in range(sx, sx + width):
                        allowed_pixels.add((x, y))
                        allowed_bytes.add((y - 512) * 128 + x // 2)
        overlap = []
        for name, rows in old_tables.items():
            for sx, sy, width, height in rows:
                if any((x, y) in allowed_pixels for y in range(sy, sy + height)
                       for x in range(sx, sx + width)):
                    overlap.append(name)
        outside_changes = sum(old != new and i not in allowed_bytes
                              for i, (old, new) in enumerate(zip(old_atlas, atlas)))
        checks.append({"name": "v0.3-car-font-sky-and-existing-sprites-preserved",
                       "passed": len(atlas) == len(old_atlas) == 65536 and not outside_changes
                       and not overlap and all(tables.get(name) == rows for name, rows in old_tables.items()),
                       "added_tables": added, "changed_bytes_outside_new_sprites": outside_changes,
                       "old_sprite_overlaps": overlap})
        checks.append({"name": "enlarged-v0.3-car-size-retained",
                       "passed": tables.get("driving_car") == old_tables.get("driving_car")
                       and all(row[2:] == (56, 38) for row in tables.get("driving_car", [])),
                       "size": [56, 38], "poses": len(tables.get("driving_car", []))})
    raw = (ROOT / "outputs" / manifest["file"]).read_bytes()
    checks.append({"name": "512KiB-AB-cartridge-and-hash",
                   "passed": len(raw) == 524288 and raw[:2] == b"AB" and digest(raw) == manifest["sha256"],
                   "bytes": len(raw), "sha256": digest(raw)})
    for section in ("vram", "course", "scenery"):
        data = (ROOT / f"assets/{section}.bin").read_bytes()
        info = manifest[section]
        checks.append({"name": f"ROM-{section}-bank-payload-matches-assets",
                       "passed": raw[info["rom_offset"]:info["rom_offset"] + info["bytes"]] == data
                       and digest(data) == info["sha256"], "bytes": len(data),
                       "rom_offset": info["rom_offset"], "sha256": digest(data)})
    return checks


if __name__ == "__main__":
    manifest = json.loads((ROOT / "outputs/build-manifest.json").read_text())
    if manifest["version"] != "0.4":
        raise SystemExit("This audit is exclusively for v0.4; build the candidate first.")
    checks = preservation_checks(ROOT / "outputs/baseline-v0.3", manifest)
    report = {"scope": "Added traffic and UFO encounters; existing driving, road, scenery and sprites retained.",
              "physical_hardware_tested": False, "results": checks,
              "passed": all(check["passed"] for check in checks)}
    (ROOT / "outputs/encounter-scope-verification-v0.4.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
