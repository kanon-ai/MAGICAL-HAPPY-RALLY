"""Read-only v0.2 preservation checks and actual native v0.3 car comparisons.

Only the contact-sheet labels/layout are generated on the PC. Scene pixels
come from openMSX screenshots; no host-side gameplay rendering is used.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from compare_scenery import CONDITIONS, c_function

ROOT = Path(__file__).resolve().parents[1]
OLD_ADVANCE = "advance=(u16)distance_fraction+speed;"
NEW_ADVANCE = "advance=(u16)distance_fraction+speed+(speed>>1);"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sprite_tables(source: str) -> dict[str, list[tuple[int, int, int, int]]]:
    return {name: [tuple(map(int, row)) for row in re.findall(r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}", body)]
            for name, body in re.findall(r"static const Sprite\s+(\w+)\[\d+\]\s*=\s*\{(.*?)\};", source, re.S)}


def indexed_sprite(atlas: bytes, rect: tuple[int, int, int, int]):
    sx, sy, width, height = rect
    for y in range(height):
        for x in range(width):
            value = atlas[(sy - 512 + y) * 128 + (sx + x) // 2]
            yield x, y, value & 15 if (sx + x) & 1 else value >> 4


def preservation_checks(baseline: Path, manifest: dict) -> list[dict]:
    hashes = json.loads((baseline / "SHA256.json").read_text())
    mismatches = [name for name, expected in hashes.items() if digest((baseline / name).read_bytes()) != expected]
    checks = [{"name": "v0.2-baseline-files-preserved", "passed": not mismatches, "files": len(hashes), "mismatches": mismatches}]
    with zipfile.ZipFile(baseline / "source-v0.2.zip") as archive:
        old_game = archive.read("src/game.c").decode("utf-8").replace("\r\n", "\n")
        game = (ROOT / "src/game.c").read_text(encoding="utf-8").replace("\r\n", "\n")
        expected_update = c_function(old_game, "update").replace(OLD_ADVANCE, NEW_ADVANCE)
        new_update = c_function(game, "update")
        checks.append({"name": "v0.2-handling-preserved-except-1.5x-distance-step", "passed": OLD_ADVANCE in old_game and new_update == expected_update, "allowed_change": NEW_ADVANCE, "includes": "Acceleration, braking, steering, offroad limits, pause logic and lap wrapping"})
        expected_game = old_game.replace("ALPINE DRIVE v0.2", "ALPINE DRIVE v0.3").replace('"ALPINE DRIVE  0.2"', '"ALPINE DRIVE  0.3"').replace(OLD_ADVANCE, NEW_ADVANCE).replace("s=&car[pose];", "s=&driving_car[pose];")
        # The implementation may explain the distance multiplier in a comment.
        without_comments = lambda text: re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
        checks.append({"name": "game-code-only-speed-car-and-version-changes", "passed": re.sub(r"\s+", "", without_comments(game)) == re.sub(r"\s+", "", without_comments(expected_game)), "allowed_changes": ["Distance-step multiplier", "driving_car sprite table", "Version string", "Comments"]})
        protected = ("src/hardware.c", "src/hardware.h", "src/boot.asm", "src/palette.h", "src/course.h", "src/scenery.h", "tools/generate_course.py", "assets/course.bin", "assets/scenery.bin")
        changed = [path for path in protected if archive.read(path) != (ROOT / path).read_bytes()]
        checks.append({"name": "v0.2-course-scenery-palette-input-sound-and-boot-unchanged", "passed": not changed, "files": len(protected), "changed": changed})
        old_header = archive.read("src/assets.h").decode("ascii")
        tables = sprite_tables((ROOT / "src/assets.h").read_text())
        old_tables = sprite_tables(old_header)
        old_atlas = archive.read("assets/vram.bin")
        atlas = (ROOT / "assets/vram.bin").read_bytes()
        cars = tables.get("driving_car", [])
        allowed_bytes = set()
        new_pixels = set()
        for sx, sy, width, height in cars:
            for y in range(sy - 512, sy - 512 + height):
                for x in range(sx, sx + width):
                    allowed_bytes.add(y * 128 + x // 2)
                    new_pixels.add((x, y + 512))
        overlap = []
        for name, rectangles in old_tables.items():
            for sx, sy, width, height in rectangles:
                if any((x, y) in new_pixels for y in range(sy, sy + height) for x in range(sx, sx + width)):
                    overlap.append(name)
        outside_changes = sum(old != new and index not in allowed_bytes for index, (old, new) in enumerate(zip(old_atlas, atlas)))
        checks.append({"name": "v0.2-background-font-and-original-sprite-atlas-preserved", "passed": len(atlas) == len(old_atlas) == 65536 and not outside_changes and not overlap and all(tables.get(name) == rects for name, rects in old_tables.items()), "changed_bytes_outside_new_car": outside_changes, "old_sprite_overlaps": overlap, "old_sprite_tables": len(old_tables)})
        checks.append({"name": "larger-car-three-poses-with-fixed-bottom-anchor", "passed": len(cars) == 3 and all(rect[2:] == (56, 38) for rect in cars) and "184-s->h,186" in game, "old_size": [44, 30], "new_size": [56, 38], "bottom_anchor": 184, "atlas_rectangles": cars})
    rom = (ROOT / "outputs" / manifest["file"]).read_bytes()
    for section, filename in (("vram", "assets/vram.bin"), ("course", "assets/course.bin"), ("scenery", "assets/scenery.bin")):
        data = (ROOT / filename).read_bytes()
        info = manifest[section]
        checks.append({"name": f"ROM-{section}-bank-payload-matches-assets", "passed": rom[info["rom_offset"]:info["rom_offset"] + info["bytes"]] == data and digest(data) == info["sha256"], "bytes": len(data), "rom_offset": info["rom_offset"], "sha256": digest(data)})
    return checks


def baseline_color_map(baseline: Path) -> dict[int, tuple[int, int, int]]:
    manifest = json.loads((baseline / "build-manifest.json").read_text())
    rom = (baseline / manifest["file"]).read_bytes()
    atlas = rom[manifest["vram"]["rom_offset"]:manifest["vram"]["rom_offset"] + 65536]
    with zipfile.ZipFile(baseline / "source-v0.2.zip") as archive:
        old_car = sprite_tables(archive.read("src/assets.h").decode("ascii"))["car"][1]
    colors = {}
    with Image.open(baseline / "landscape-000.png") as source:
        image = source.convert("RGB")
        box = image.getbbox()
        if box is None or (box[2] - box[0], box[3] - box[1]) != (256, 212):
            raise ValueError("Unexpected baseline native video viewport")
        for x, y, index in indexed_sprite(atlas, old_car):
            if index:
                actual = image.getpixel((box[0] + 106 + x, box[1] + 154 + y))
                if index in colors and colors[index] != actual:
                    raise ValueError("Baseline palette mapping is not uniform")
                colors[index] = actual
    return colors


def check_native_car(baseline: Path, screenshot: Path, pose: int, player_x: int) -> dict:
    atlas = (ROOT / "assets/vram.bin").read_bytes()
    rect = sprite_tables((ROOT / "src/assets.h").read_text())["driving_car"][pose]
    colors = baseline_color_map(baseline)
    checked = mismatches = 0
    with Image.open(screenshot) as source:
        image = source.convert("RGB")
        box = image.getbbox()
        if box is None or (box[2] - box[0], box[3] - box[1]) != (256, 212):
            return {"passed": False, "error": "Unexpected native viewport"}
        x0 = 128 + int(player_x / 4) - rect[2] // 2
        y0 = 184 - rect[3]
        for x, y, index in indexed_sprite(atlas, rect):
            if index:
                checked += 1
                mismatches += image.getpixel((box[0] + x0 + x, box[1] + y0 + y)) != colors.get(index)
    return {"passed": checked > 0 and mismatches == 0, "pose": pose, "player_x": player_x, "screen_rectangle": [x0, y0, rect[2], rect[3]], "opaque_pixels_checked": checked, "mismatched_pixels": mismatches}


def compare_speed_car(baseline: Path, current: dict, destination: Path) -> dict:
    original = json.loads((baseline / "verification-v0.2.json").read_text())
    old_scenes = {scene["requested_phase"]: scene for scene in original["seeded_landscapes"]}
    pairs, images = [], []
    # At speed zero and player_x zero the two car rectangles are nested:
    # old x106..149/y154..183; new x100..155/y146..183.
    excluded = (100, 146, 156, 184)
    for scene in current["seeded_landscapes"]:
        phase = scene["requested_phase"]
        old_scene = old_scenes[phase]
        old_path = baseline / Path(old_scene["file"]).name
        new_path = ROOT / scene["file"]
        differences = {key: {"v0.2": old_scene["state"][key], "current": scene["state"][key]} for key in CONDITIONS if old_scene["state"][key] != scene["state"][key]}
        with Image.open(old_path) as old, Image.open(new_path) as new:
            old, new = old.convert("RGB"), new.convert("RGB")
            box, new_box = old.getbbox(), new.getbbox()
            valid = old.size == new.size and box == new_box and box is not None and (box[2] - box[0], box[3] - box[1]) == (256, 212)
            outside = inside = 0
            if valid:
                for y in range(old.height):
                    for x in range(old.width):
                        if old.getpixel((x, y)) != new.getpixel((x, y)):
                            if excluded[0] <= x - box[0] < excluded[2] and excluded[1] <= y - box[1] < excluded[3]:
                                inside += 1
                            else:
                                outside += 1
            images.append((phase, old.copy(), new.copy()))
        car = check_native_car(baseline, new_path, 1, 0)
        pairs.append({"phase": phase, "conditions_match": not differences, "condition_differences": differences, "baseline_hash_matches": digest(old_path.read_bytes()) == old_scene["sha256"], "native_size_matches": valid, "changed_pixels_outside_car_union": outside, "changed_car_pixels": inside, "background_and_hud_preserved": valid and outside == 0, "new_native_car": car})
    width, height = images[0][1].size
    margin, gap, label, top = 12, 12, 24, 52
    rows = (len(images) + 1) // 2
    contact = Image.new("RGB", (margin * 2 + 4 * width + 3 * gap, top + rows * (height + label + gap) + margin), (18, 23, 27))
    draw = ImageDraw.Draw(contact)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 16)
        heading = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 20)
    except OSError:
        font = heading = ImageFont.load_default()
    draw.text((margin, 12), "ALPINE DRIVE | native openMSX | SAME DISTANCE / STOPPED | larger car", font=heading, fill=(235, 242, 245))
    for index, (phase, old, new) in enumerate(images):
        row, group = divmod(index, 2)
        for version_index, picture in enumerate((old, new)):
            x = margin + (group * 2 + version_index) * (width + gap)
            y = top + row * (height + label + gap)
            draw.text((x, y), f"PHASE {phase:04d} / {'v0.2' if version_index == 0 else 'v0.3'}", font=font, fill=(198, 218, 222))
            contact.paste(picture, (x, y + label))
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "car-comparison.png"
    contact.save(path)
    return {"all_conditions_match": all(pair["conditions_match"] for pair in pairs), "baseline_hashes_match": all(pair["baseline_hash_matches"] for pair in pairs), "native_sizes_match": all(pair["native_size_matches"] for pair in pairs), "background_and_hud_preserved": all(pair["background_and_hud_preserved"] for pair in pairs), "new_car_pixels_match": all(pair["new_native_car"]["passed"] for pair in pairs), "phases": [pair["phase"] for pair in pairs], "excluded_car_union": excluded, "contact_sheet": str(path.relative_to(ROOT)).replace("\\", "/"), "scene_pixels_modified": False, "pairs": pairs}
