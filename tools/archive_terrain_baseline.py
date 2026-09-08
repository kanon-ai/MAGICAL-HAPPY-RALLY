"""One-shot preservation of the approved, published v0.4 local checkout."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ROM = '89aea977464a8cd5f28d9ca1b83a7329d691b437f52444a06729d5588cda8291'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    rom = (source/'outputs/MAGICAL_HAPPY_RALLY-v0.4.rom').read_bytes()
    assert hashlib.sha256(rom).hexdigest() == EXPECTED_ROM
    destination = ROOT/'outputs/baseline-v0.4'
    assert not destination.exists(), 'Never replace a preserved baseline.'
    destination.mkdir()
    names = sorted([str(path.relative_to(source)).replace('\\', '/')
                    for folder in ('src', 'tools') for path in (source/folder).iterdir() if path.is_file()]
                   + ['assets/course.bin', 'assets/vram.bin', 'assets/scenery.bin'])
    with zipfile.ZipFile(destination/'source-v0.4.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            info = zipfile.ZipInfo(name, (2026, 9, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (source/name).read_bytes())
    (destination/'MAGICAL_HAPPY_RALLY-v0.4.rom').write_bytes(rom)
    for name in ('build-manifest.json', 'course-manifest.json'):
        (destination/name).write_bytes((source/'outputs'/name).read_bytes())
    # Retained palette reference: v0.4 preserves these v0.3 car/sky colors.
    (destination/'landscape-000.png').write_bytes((source/'outputs/baseline-v0.3/landscape-000.png').read_bytes())
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(destination.iterdir())}
    (destination/'SHA256.json').write_text(json.dumps(hashes, indent=2)+'\n')
    print(json.dumps({'source_files': len(names), 'preserved_files': hashes}, indent=2))

if __name__ == '__main__':
    main()
