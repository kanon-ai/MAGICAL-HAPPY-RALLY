"""Build the standalone 512 KiB ASCII8 MAGICAL HAPPY RALLY cartridge.

SDCC and Pasmo are used from existing installations; no BIOS is copied.
Override their locations with SDCC and PASMO if moving this project.
"""
from pathlib import Path
import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BANK_BYTES = 8192
ROM_BYTES = 524288
COURSE_OFFSET = 12 * BANK_BYTES
COURSE_RECORD_BYTES = 256


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-only", action="store_true", help="Reuse generated assets but always recompile C")
    parser.add_argument("--check-tools", action="store_true", help="Check local tool locations without building")
    args = parser.parse_args()
    sdcc = Path(os.environ.get("SDCC") or shutil.which("sdcc") or "sdcc")
    pasmo = Path(os.environ.get("PASMO") or shutil.which("pasmo") or "pasmo")
    for label, path in (("SDCC", sdcc), ("PASMO", pasmo)):
        if not path.is_file():
            raise SystemExit(f"{label} not found: {path}. Set the {label} environment variable.")
    if args.check_tools:
        print(json.dumps({"python": sys.executable, "sdcc": str(sdcc), "pasmo": str(pasmo)}, indent=2))
        return
    build = ROOT / "work/build"
    out = ROOT / "outputs"
    build.mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["PATH"] = str(sdcc.parent) + os.pathsep + env.get("PATH", "")

    def run(command):
        result = subprocess.run([str(item) for item in command], cwd=ROOT, env=env,
                                text=True, capture_output=True)
        for output in (result.stdout, result.stderr):
            if output.strip():
                print(output.strip())
        if result.returncode:
            raise SystemExit(result.returncode)

    if not args.pack_only:
        run([sys.executable, ROOT / "tools/generate_assets.py"])
        run([sys.executable, ROOT / "tools/generate_course.py"])
    vram = (ROOT / "assets/vram.bin").read_bytes()
    course = (ROOT / "assets/course.bin").read_bytes()
    scenery = (ROOT / "assets/scenery.bin").read_bytes()
    assert len(vram) == 65536, "VRAM image must occupy banks 4..11 (65536 bytes)"
    assert course and len(course) % COURSE_RECORD_BYTES == 0, "Course profiles must be exactly 256 bytes"
    assert len(course)==262144, "The existing 1024 road profiles are preserved"
    assert len(scenery)==131072, "Scenery atlas must occupy banks 44..59"
    assert COURSE_OFFSET+len(course)+len(scenery)<=ROM_BYTES, "Scenery exceeds 512 KiB"
    flags = ["-mz80", "--std-sdcc11", "--opt-code-speed", "--no-std-crt0",
             "--code-loc", "0x8000", "--data-loc", "0xE000"]
    objects = []
    for name in ("game", "hardware"):
        obj = build / f"{name}.rel"
        objects.append(obj)
        run([sdcc, *flags, "-I", "src", "-c", f"src/{name}.c", "-o", obj])
    # SDCC's 32-bit arithmetic helpers use _HOME. Without an explicit RAM
    # code address that area follows _DATA, outside the boot-copied runtime.
    # Reserve D000-DFFF for these helpers; the HEX overlap/range audit below
    # rejects either a growing _CODE collision or a helper overflow.
    run([sdcc, *flags, "-Wl-b_HOME=0xD000", "-o", build / "game.ihx", *objects])
    memory = {}
    for line in (build / "game.ihx").read_text().splitlines():
        if not line.startswith(":"):
            continue
        record = bytes.fromhex(line[1:])
        assert len(record) == record[0] + 5 and sum(record) % 256 == 0, "Invalid Intel HEX record"
        address = int.from_bytes(record[1:3], "big")
        kind = record[3]
        if kind == 0:
            for index, value in enumerate(record[4:-1]):
                target = address + index
                assert 0x8000 <= target < 0xE000, f"Runtime overflow at {target:04X}"
                assert target not in memory, f"Overlapping HEX data at {target:04X}"
                memory[target] = value
        elif kind not in (1,):
            raise AssertionError(f"Unsupported Intel HEX record type {kind}")
    map_text = (build / "game.map").read_text()
    symbols = {match[2]: int(match[1], 16) for match in
               re.finditer(r"^\s*([0-9A-F]{8})\s+(_[\w]+)\s", map_text, re.M)}
    areas = {match[1]: (int(match[2], 16), int(match[3], 16)) for match in
             re.finditer(r"^(_[\w]+)\s+([0-9A-F]{8})\s+([0-9A-F]{8})\s", map_text, re.M)}
    assert "_main" in symbols, "Missing C entry point"
    assert "_DATA" in areas, "Missing linker data area"
    for name in ("_DATA", "_INITIALIZED", "_BSEG", "_BSS"):
        address, size = areas.get(name, (0, 0))
        assert not size or 0xE000 <= address <= address + size <= 0xF000, f"{name} exceeds E000-EFFF"
    runtime = bytearray([0xFF] * 24576)
    for address, value in memory.items():
        runtime[address - 0x8000] = value
    initializer, initial_size = areas.get("_INITIALIZER", (0, 0))
    initialized, data_size = areas.get("_INITIALIZED", (0, 0))
    assert initial_size == data_size, "SDCC initialized-data sizes disagree"
    initialization = ""
    if initial_size:
        assert 0x8000 <= initializer < initializer + initial_size <= 0xE000
        initialization = f"    ld hl,{initializer}\n    ld de,{initialized}\n    ld bc,{initial_size}\n    ldir"
    boot_source = (ROOT / "src/boot.asm").read_text()
    boot_source = boot_source.replace("ENTRY_POINT", str(symbols["_main"]))
    boot_source = boot_source.replace("INITIALIZE_DATA", initialization)
    (build / "boot.asm").write_text(boot_source)
    run([pasmo, "--bin", build / "boot.asm", build / "boot.bin"])
    boot = (build / "boot.bin").read_bytes()
    assert len(boot) == BANK_BYTES and boot[:2] == b"AB", "Invalid MSX cartridge boot bank"
    rom = boot + runtime + vram + course + scenery
    used = len(rom)
    rom += bytes([0xFF]) * (ROM_BYTES - used)
    assert len(rom) == ROM_BYTES
    assert rom[COURSE_OFFSET:COURSE_OFFSET + len(course)] == course
    target = out / "MAGICAL_HAPPY_RALLY-v0.4.rom"
    try:
        target.write_bytes(rom)
    except OSError as error:
        if error.errno not in (errno.EACCES, errno.EPERM, errno.EINVAL):
            raise
        raise SystemExit(
            f"Cannot replace {target.name}; Windows may be locking the loaded cartridge.\n"
            "Close this project's emulator, run BUILD.cmd again, then restart it with PLAY.cmd.\n"
            "Eject alone may leave the ROM file locked on Windows."
        ) from None
    symbols_json = json.dumps(symbols, indent=2) + "\n"
    (build / "symbols.json").write_text(symbols_json)
    (out / "symbols.json").write_text(symbols_json)
    source_paths = sorted((ROOT / "src").glob("*")) + [
        ROOT / "tools/build.py", ROOT / "tools/generate_assets.py", ROOT / "tools/generate_course.py"]
    manifest = {
        "title": "MAGICAL HAPPY RALLY", "version": "0.4", "working_title": True,
        "file": target.name, "machine": "MSX turbo R + V9990", "mapper": "ASCII8",
        "rom_bytes": len(rom), "allocated_bytes": used, "free_bytes": ROM_BYTES - used,
        "runtime_bytes": max(memory) - 0x8000 + 1, "runtime_address": "8000-DFFF",
        "data_address": "E000-EFFF", "stack_top": "F300", "entry": hex(symbols["_main"]),
        "vram": {"bytes": len(vram), "rom_offset": 4 * BANK_BYTES,
                 "first_bank": 4, "last_bank": 11, "sha256": digest(vram)},
        "course": {"bytes": len(course), "rom_offset": COURSE_OFFSET,
                   "first_bank": 12, "record_bytes": COURSE_RECORD_BYTES,
                   "records": len(course) // COURSE_RECORD_BYTES,
                   "road_bytes": 128, "object_bytes": 64, "event_projection_bytes": 64,
                   "sha256": digest(course)},
        "scenery": {"bytes":len(scenery),"rom_offset":44*BANK_BYTES,"first_bank":44,"last_bank":59,"vram_byte_offset":0x30000,"sha256":digest(scenery)},
        "sha256": digest(rom),
        "sources": {str(path.relative_to(ROOT)).replace("\\", "/"): digest(path.read_bytes())
                    for path in source_paths if path.is_file()},
    }
    (out / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
