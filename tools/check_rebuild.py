"""Check a complete regenerated build against the current cartridge.

Run with the emulator closed on Windows so the mapped ROM is not locked.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
rom = ROOT/'outputs/MAGICAL_HAPPY_RALLY-v0.4.rom'
before = rom.read_bytes()
subprocess.run([sys.executable, str(ROOT/'tools/build.py')], cwd=ROOT, check=True)
after = rom.read_bytes()
manifest = json.loads((ROOT/'outputs/build-manifest.json').read_text())
sha = hashlib.sha256(after).hexdigest()
checks = {
    'full_regenerated_build_identical': before == after,
    'cartridge_exactly_512kib': len(after) == 524288,
    'msx_header': after[:2] == b'AB',
    'manifest_hash_matches': sha == manifest['sha256'],
    'course_has_1024_profiles': manifest['course']['records'] == 1024,
    'remaining_rom_padding_ff': set(after[manifest['allocated_bytes']:]) == {255},
}
report = {'sha256': sha, 'rom_bytes': len(after), 'checks': checks,
          'native_runtime_test': False}
(ROOT/'outputs/rebuild-verification-v0.4.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
assert all(checks.values()), 'Rebuild verification failed'
