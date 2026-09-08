"""Preservation checks and a labelled contact sheet of native MSX screenshots.

Only annotations and layout are produced on the PC. Each scene is the unchanged
pixel image captured from its native ROM. Baseline files are always read-only.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ("mode", "distance", "speed", "player_x", "course_phase", "road_center", "hill", "offroad", "course_curve", "section")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def c_function(source: str, name: str) -> str:
    match = re.search(r"\b(?:static\s+)?void\s+" + re.escape(name) + r"\s*\(void\)\s*\{", source)
    if match is None:
        raise ValueError(f"Missing C function {name}")
    level = 1
    for end in range(match.end(), len(source)):
        level += (source[end] == "{") - (source[end] == "}")
        if level == 0:
            return source[match.start():end + 1].replace("\r\n", "\n")
    raise ValueError(f"Unclosed C function {name}")


def python_function(source: str, name: str) -> str:
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise ValueError(f"Missing Python function {name}")


def scenery_probe_phases(player_x: int = 0) -> list[dict]:
    """Select actual course states with the greatest visible object transfers.

    These calculations choose stress-test locations. Passing performance and
    appearance checks still requires screenshots and timings from the MSX ROM.
    """
    headers = (ROOT / "src/assets.h").read_text() + (ROOT / "src/scenery.h").read_text()
    dimensions = {}
    for kind, name in enumerate(("grand_pines", "rocks", "crags", "bushes")):
        match = re.search(r"static const Sprite\s+" + name + r"\[\d+\]\s*=\s*\{(.*?)\};", headers, re.S)
        if not match:
            raise ValueError(f"Missing scenery table {name}")
        dimensions[kind] = [(int(w), int(h)) for _, _, w, h in re.findall(r"\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}", match[1])]
    course = (ROOT / "assets/course.bin").read_bytes()
    phases = []
    for phase in range(len(course) // 256):
        total = occluded = tallest = 0
        visible = []
        for offset in range(phase * 256 + 128, phase * 256 + 256, 8):
            record = course[offset:offset + 8]
            if not record[7]:
                continue
            x = int.from_bytes(record[0:2], "little", signed=True)
            y = int.from_bytes(record[2:4], "little", signed=True)
            shift = (abs(player_x) * (record[7] >> 1)) // 64
            x -= -shift if player_x < 0 else shift
            width, height = dimensions[record[5]][record[4]]
            left = x - width // 2
            pixels = max(0, min(256, left + width) - max(0, left)) * max(0, min(186, y, record[6]) - max(0, y - height))
            if pixels:
                total += pixels
                tallest = max(tallest, height)
                if record[6] < 186 and record[6] < y:
                    occluded += pixels
                visible.append({"kind": record[5], "level": record[4], "x": x, "ground_y": y, "clip_bottom": record[6], "sprite_size": [width, height], "visible_bbox_pixels": pixels})
        phases.append({"phase": phase, "bbox_pixels": total, "occluded_bbox_pixels": occluded, "tallest_visible_sprite": tallest, "objects": visible})
    choices = (("dense", lambda item: item["bbox_pixels"]), ("near", lambda item: (item["tallest_visible_sprite"], item["bbox_pixels"])), ("crest-occlusion", lambda item: item["occluded_bbox_pixels"]))
    return [{"name": name, "player_x": player_x, **max(phases, key=key)} for name, key in choices]


def preservation_checks(baseline: Path, manifest: dict) -> list[dict]:
    recorded = json.loads((baseline / "SHA256.json").read_text())
    mismatches = [name for name, expected in recorded.items() if sha256((baseline / name).read_bytes()) != expected]
    checks = [{"name": "v0.1-baseline-files-preserved", "passed": not mismatches, "files": len(recorded), "mismatches": mismatches}]
    baseline_manifest = json.loads((baseline / "build-manifest.json").read_text())
    baseline_rom = (baseline / baseline_manifest["file"]).read_bytes()
    with zipfile.ZipFile(baseline / "source-v0.1.zip") as source:
        original_game = source.read("src/game.c").decode("utf-8")
        original_course = source.read("tools/generate_course.py").decode("utf-8")
    current_game = (ROOT / "src/game.c").read_text(encoding="utf-8")
    current_course_source = (ROOT / "tools/generate_course.py").read_text(encoding="utf-8")
    old_update, new_update = c_function(original_game, "update"), c_function(current_game, "update")
    checks.append({"name": "v0.1-driving-update-unchanged", "passed": old_update == new_update, "normalized_source_sha256": sha256(new_update.encode()), "comparison": "Exact update() text after CRLF normalization; rendering is outside this function."})
    checks.append({"name": "v0.1-course-height-and-center-unchanged", "passed": all(python_function(original_course, name) == python_function(current_course_source, name) for name in ("height", "center")), "comparison": "Python AST for height() and center()"})
    current_course = (ROOT / "assets/course.bin").read_bytes()
    old_offset = baseline_manifest["course"]["rom_offset"]
    old_course = baseline_rom[old_offset:old_offset + baseline_manifest["course"]["bytes"]]
    protected_old = b"".join(old_course[index:index + 128] for index in range(0, len(old_course), 256))
    protected_new = b"".join(current_course[index:index + 128] for index in range(0, len(current_course), 256))
    checks.append({"name": "v0.1-road-profiles-and-metadata-unchanged", "passed": len(current_course) == len(old_course) == 262144 and protected_new == protected_old, "phases": 1024, "protected_bytes_per_phase": 128, "protected_sha256": sha256(protected_new), "includes": "Road spans 0..122; horizon, curvature, grade, section, heading 123..127"})
    old_atlas_start = baseline_manifest["vram"]["rom_offset"]
    old_atlas = baseline_rom[old_atlas_start:old_atlas_start + baseline_manifest["vram"]["bytes"]]
    current_atlas = (ROOT / "assets/vram.bin").read_bytes()
    # The first 128 rows are the panorama being enhanced. Existing car, font,
    # rocks and bushes live below it and must keep their original pixels.
    checks.append({"name": "v0.1-car-font-and-legacy-sprites-preserved", "passed": len(old_atlas) == len(current_atlas) == 65536 and old_atlas[16384:] == current_atlas[16384:], "protected_bytes": len(current_atlas) - 16384, "panorama_bytes_excluded": 16384, "protected_sha256": sha256(current_atlas[16384:])})
    actual_rom = (ROOT / "outputs" / manifest["file"]).read_bytes()
    scenery = (ROOT / "assets/scenery.bin").read_bytes()
    checks.append({"name": "extra-scenery-packed-at-bank44", "passed": len(scenery) == 131072 and actual_rom[360448:491520] == scenery, "rom_offset": 360448, "first_bank": 44, "last_bank": 59, "bytes": len(scenery), "sha256": sha256(scenery)})
    return checks


def compare_scenery(baseline: Path, current: dict, destination: Path) -> dict:
    original = json.loads((baseline / "verification-v0.1.json").read_text())
    original_rom = (baseline / original["rom"]["file"]).read_bytes()
    atlas_offset = original["rom"]["vram"]["rom_offset"]
    old_atlas = original_rom[atlas_offset:atlas_offset + original["rom"]["vram"]["bytes"]]
    # The preserved v0.1 centered car: atlas (46, 130), 44x30, screen (106,154).
    # Ignore transparent pixels, which intentionally reveal the new scenery.
    car_mask = []
    for y in range(30):
        for x in range(44):
            value = old_atlas[(130 + y) * 128 + (46 + x) // 2]
            index = value & 15 if (46 + x) & 1 else value >> 4
            if index:
                car_mask.append((106 + x, 154 + y))
    old_scenes = {scene["requested_phase"]: scene for scene in original["seeded_landscapes"]}
    pairs, images = [], []
    for scene in current["seeded_landscapes"]:
        phase = scene["requested_phase"]
        old_scene = old_scenes[phase]
        old_path = baseline / Path(old_scene["file"]).name
        new_path = ROOT / scene["file"]
        differences = {key: {"v0.1": old_scene["state"][key], "current": scene["state"][key]} for key in CONDITIONS if old_scene["state"][key] != scene["state"][key]}
        with Image.open(old_path) as old, Image.open(new_path) as new:
            old, new = old.convert("RGB"), new.convert("RGB")
            same_size = old.size == new.size
            changed_pixels = sum(pixel != (0, 0, 0) for pixel in ImageChops.difference(old, new).getdata()) if same_size else None
            old_box, new_box = old.getbbox(), new.getbbox()
            valid_view = old_box is not None and new_box is not None and (old_box[2] - old_box[0], old_box[3] - old_box[1]) == (256, 212) and old_box == new_box
            car_same = valid_view and all(old.getpixel((old_box[0] + x, old_box[1] + y)) == new.getpixel((new_box[0] + x, new_box[1] + y)) for x, y in car_mask)
            hud_same = valid_view and old.crop((old_box[0], old_box[1] + 186, old_box[2], old_box[3])).tobytes() == new.crop((new_box[0], new_box[1] + 186, new_box[2], new_box[3])).tobytes()
            images.append((phase, old.copy(), new.copy()))
        pairs.append({"phase": phase, "conditions_match": not differences, "condition_differences": differences, "baseline_hash_matches": sha256(old_path.read_bytes()) == old_scene["sha256"], "native_size_matches": same_size, "native_size": list(old.size), "changed_pixels": changed_pixels, "opaque_car_pixels_match": car_same, "hud_pixels_match": hud_same, "baseline": str(old_path.relative_to(ROOT)).replace("\\", "/"), "current": scene["file"]})
    width, height = images[0][1].size
    margin, gap, label, top = 12, 12, 24, 52
    columns, rows = 4, (len(images) + 1) // 2
    contact = Image.new("RGB", (margin * 2 + columns * width + (columns - 1) * gap, top + rows * (height + label + gap) + margin), (18, 23, 27))
    draw = ImageDraw.Draw(contact)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 16)
        heading = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 20)
    except OSError:
        font = heading = ImageFont.load_default()
    release = "v" + str(current["rom"]["version"])
    draw.text((margin, 12), f"ALPINE DRIVE | native openMSX | same distance, stopped, steering centered | {release}", font=heading, fill=(235, 242, 245))
    for index, (phase, old, new) in enumerate(images):
        row, group = divmod(index, 2)
        for version_index, picture in enumerate((old, new)):
            column = group * 2 + version_index
            x = margin + column * (width + gap)
            y = top + row * (height + label + gap)
            draw.text((x, y), f"PHASE {phase:04d} / {'v0.1' if version_index == 0 else release}", font=font, fill=(198, 218, 222))
            contact.paste(picture, (x, y + label))
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "scenery-comparison.png"
    contact.save(path)
    return {"all_conditions_match": all(pair["conditions_match"] for pair in pairs), "baseline_hashes_match": all(pair["baseline_hash_matches"] for pair in pairs), "native_sizes_match": all(pair["native_size_matches"] for pair in pairs), "car_and_hud_preserved": all(pair["opaque_car_pixels_match"] and pair["hud_pixels_match"] for pair in pairs), "car_opaque_pixels_checked_per_scene": len(car_mask), "phases": [pair["phase"] for pair in pairs], "contact_sheet": str(path.relative_to(ROOT)).replace("\\", "/"), "scene_pixels_modified": False, "pairs": pairs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default="v0.2")
    args = parser.parse_args()
    if not re.fullmatch(r"v\d+\.\d+(?:\.\d+)?", args.release) or args.release == "v0.1":
        raise SystemExit("Choose v0.2 or newer; v0.1 remains preserved.")
    current = json.loads((ROOT / "outputs" / f"verification-{args.release}.json").read_text())
    result = compare_scenery(ROOT / "outputs/baseline-v0.1", current, ROOT / "outputs" / args.release)
    print(json.dumps(result, indent=2))
