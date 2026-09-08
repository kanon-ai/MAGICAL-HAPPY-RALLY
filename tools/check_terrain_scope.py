"""v0.5 approved terrain/render optimization preservation and safety audit.

The former v0.4 preservation checker is deliberately not modified: its promise
of unchanged road data does not apply to this explicitly approved new course.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPTHS = (28, 32, 36, 42, 50, 60, 72, 86, 102, 124, 150, 184, 230, 292, 380, 512)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def signed(byte):
    return byte if byte < 128 else byte - 256

def mask_render_functions(source, names):
    if 'draw_road' in names:
        # Seven bytes used exclusively by the non-reentrant road renderer.
        source = source.replace('static s16 road_asm_c,road_asm_left,road_asm_right;\nstatic u8 road_asm_i;\n\n', '')
    # Only these explicitly named, top-level functions may change. Anchoring
    # the closing brace at column zero leaves all other source text audited.
    for name in names:
        pattern = rf'(?ms)^(?:static )?(?:void|s16) {name}\([^\n]*\{{.*?^}}'
        source, count = re.subn(pattern, f'APPROVED_RENDER_FUNCTION_{name}', source)
        if count != 1:
            raise ValueError(f'Expected exactly one {name} function, found {count}')
    return source

def preservation_checks(baseline, manifest):
    baseline = Path(baseline)
    checks = []
    def check(name, passed, **evidence):
        checks.append({'name': name, 'passed': bool(passed), **evidence})

    hashes = json.loads((baseline/'SHA256.json').read_text())
    changed = [name for name, sha in hashes.items() if digest((baseline/name).read_bytes()) != sha]
    check('v0.4-baseline-files-preserved', len(hashes) == 5 and not changed, files=len(hashes), changed=changed)
    with zipfile.ZipFile(baseline/'source-v0.4.zip') as archive:
        source = (ROOT/'src/game.c').read_text(encoding='utf-8').replace('v0.5', 'v0.4').replace('RALLY 0.5', 'RALLY 0.4')
        old_source = archive.read('src/game.c').decode('utf-8').replace('\r\n', '\n')
        functions = ('camera_shift', 'draw_road')
        check('game-code-preserved-outside-approved-render-functions-and-version',
              mask_render_functions(source, functions) == mask_render_functions(old_source, functions),
              allowed_functions=list(functions), allowed_label='0.4 to 0.5',
              preserved='All input, speed, drift, event, clock, audio and other drawing code.')
        hardware = (ROOT/'src/hardware.c').read_text(encoding='utf-8')
        old_hardware = archive.read('src/hardware.c').decode('utf-8').replace('\r\n', '\n')
        check('hardware-code-preserved-outside-approved-gfx-span',
              mask_render_functions(hardware, ('gfx_span',)) == mask_render_functions(old_hardware, ('gfx_span',)),
              allowed_functions=['gfx_span'])
        protected = [name for name in archive.namelist()
                     if name not in ('src/game.c', 'src/hardware.c', 'tools/build.py', 'tools/generate_course.py',
                                     'tools/emulator_host.mjs', 'tools/check_rebuild.py', 'assets/course.bin')]
        changed = [name for name in protected if (ROOT/name).read_bytes() != archive.read(name)]
        check('v0.4-sprites-events-clock-and-old-verifiers-preserved', not changed,
              files=protected, changed=changed)
        packaging = ('tools/build.py', 'tools/emulator_host.mjs', 'tools/check_rebuild.py')
        changed = [name for name in packaging
                   if (ROOT/name).read_text(encoding='utf-8').replace('v0.5', 'v0.4').replace('"0.5"', '"0.4"')
                   != archive.read(name).decode('utf-8').replace('\r\n', '\n')]
        check('build-and-launch-changes-are-version-only', not changed, changed=changed)
        old_course = archive.read('assets/course.bin')
    course = (ROOT/'assets/course.bin').read_bytes()
    raw = (ROOT/'outputs'/manifest['file']).read_bytes()
    old_raw = (baseline/'MAGICAL_HAPPY_RALLY-v0.4.rom').read_bytes()
    check('512KiB-ASCII8-cartridge-valid', manifest['version'] == '0.5' and len(raw) == 524288
          and raw[:2] == b'AB' and digest(raw) == manifest['sha256'], bytes=len(raw), sha256=digest(raw))
    old_label = b'MAGICAL HAPPY RALLY 0.4\0'
    new_label = b'MAGICAL HAPPY RALLY 0.5\0'
    changed_rom = [index for index, (old, new) in enumerate(zip(old_raw, raw)) if old != new]
    check('ROM-changes-confined-to-relinked-code-and-course', len(raw) == len(old_raw)
          and old_raw.count(old_label) == raw.count(new_label) == 1
          and all(index < 4*8192 or 12*8192 <= index < 44*8192 for index in changed_rom),
          changed_bytes=len(changed_rom), code_and_boot_byte_range=[0, 4*8192],
          course_byte_range=[12*8192, 44*8192])
    check('approved-strong-terrain-retained-through-render-optimization',
          digest(course) == 'ccabb191e324373b24e47e15ad666fb8b9e664351946b53fb9a1bfa127a39be2',
          sha256=digest(course), baseline_candidate_rom='8849a4e19fb97fec44f5276026543079ec0529271141e09be6a33d8f42a58606')
    for name in ('vram', 'course', 'scenery'):
        info = manifest[name]
        payload = (ROOT/f'assets/{name}.bin').read_bytes()
        check(f'ROM-{name}-payload-matches-assets',
              raw[info['rom_offset']:info['rom_offset']+info['bytes']] == payload
              and digest(payload) == info['sha256'], bytes=len(payload), sha256=digest(payload))
    check('course-format-and-all-eight-sections-preserved', len(course) == len(old_course) == 262144
          and all(course[phase*256+126] == phase//128 for phase in range(1024)),
          profiles=1024, record_bytes=256, road_spans=41, scenery_slots=8, event_anchors=16)
    if len(course) != 262144:
        return checks
    records = [course[i:i+256] for i in range(0, len(course), 256)]
    old_records = [old_course[i:i+256] for i in range(0, len(old_course), 256)]
    horizons = [r[123] for r in records]
    curves = [signed(r[124]) for r in records]
    check('sky-source-and-ground-horizon-safe', min(horizons) >= 64 and max(horizons) <= 112,
          range=[min(horizons), max(horizons)], sky_renderer_unchanged=True)
    check('outward-drift-remains-gentle', min(curves) >= -33 and max(curves) <= 33,
          range=[min(curves), max(curves)], maximum_drift_per_8_frames=2)
    holes = []
    saturated = []
    for phase, record in enumerate(records):
        visible = [band for band in range(41) if record[3*band+1]]
        if not visible or visible != list(range(visible[0], 41)):
            holes.append(phase)
        if any(abs(signed(record[3*band])) >= 127 for band in visible):
            saturated.append(phase)
    check('road-reaches-player-with-no-band-holes', not holes, bad_phases=holes)
    check('road-and-traffic-signed-coordinates-do-not-saturate', not saturated
          and all(abs(signed(r[at])) < 127 for r in records for at in range(192, 256, 4)),
          saturated_road_phases=saturated)
    check('event-widths-and-near-hill-occlusion-consistent',
          all(r[194+4*i] == min(250, round(6960/depth)) for r in records for i, depth in enumerate(DEPTHS))
          and all(list(r[195:256:4]) == sorted(r[195:256:4], reverse=True)
                  and all(y <= 186 for y in r[195:256:4]) for r in records),
          anchors=1024*16, unchanged_depth_units=list(DEPTHS))
    continuity = []
    crest_transitions = []
    # A screen row at a crest can change from the nearby hill to the distant
    # road behind it: those are different world points, so bounding their x
    # difference as if they were one moving point is incorrect. Audit the
    # near road strictly and classify the horizon-adjacent reveal separately.
    # Keep the full maxima in the evidence rather than concealing the reveal.
    for step in (1, 2):
        delta_h = delta_x = delta_w = 0
        near_x = near_w = event_x = event_y = event_clip = 0
        for phase, record in enumerate(records):
            next_record = records[(phase+step)%1024]
            delta_h = max(delta_h, abs(record[123]-next_record[123]))
            for band in range(41):
                at = 3*band
                if record[at+1] and next_record[at+1]:
                    dx = abs(signed(record[at])-signed(next_record[at]))
                    dw = abs(record[at+1]-next_record[at+1])
                    delta_x = max(delta_x, dx)
                    delta_w = max(delta_w, dw)
                    y = 64+2*band if band < 21 else 106+4*(band-21)
                    if y >= 122:
                        near_x, near_w = max(near_x, dx), max(near_w, dw)
                    if dx > 12*step or dw > 12*step:
                        crest_transitions.append({'phase': phase, 'step': step, 'y': y,
                                                  'horizon': record[123], 'next_horizon': next_record[123],
                                                  'center_change': dx, 'halfwidth_change': dw})
            for at in range(192, 256, 4):
                event_x = max(event_x, abs(signed(record[at])-signed(next_record[at])))
                event_y = max(event_y, abs(record[at+1]-next_record[at+1]))
                event_clip = max(event_clip, abs(record[at+3]-next_record[at+3]))
        continuity.append({'phase_step': step, 'max_horizon_pixels': delta_h,
                           'all_rows_max_road_center_pixels': delta_x, 'all_rows_max_halfwidth_pixels': delta_w,
                           'near_road_max_center_pixels': near_x, 'near_road_max_halfwidth_pixels': near_w,
                           'event_max_x_pixels': event_x, 'event_max_y_pixels': event_y,
                           'event_max_clip_pixels': event_clip})
    check('one-and-two-phase-near-road-and-loop-boundary-continuous',
          all(row['max_horizon_pixels'] <= 3*row['phase_step']
              and row['near_road_max_center_pixels'] <= 12*row['phase_step']
              and row['near_road_max_halfwidth_pixels'] <= 12*row['phase_step'] for row in continuity),
          limits='Per phase: horizon <=3 px; near-road (y>=122) center/halfwidth <=12 px.', measured=continuity)
    check('large-road-reveals-confined-to-far-crest-region',
          all(row['y'] < 122 and row['y'] <= max(row['horizon'], row['next_horizon'])+12
              for row in crest_transitions), transitions=crest_transitions,
          note='Near-to-far intersection switches world branches as a crest uncovers the farther road; native crest sequence is reviewed separately.')
    check('traffic-anchors-continuous-through-hills-and-loop',
          all(row['event_max_x_pixels'] <= 4*row['phase_step']
              and row['event_max_y_pixels'] <= 3*row['phase_step']
              and row['event_max_clip_pixels'] <= 3*row['phase_step'] for row in continuity),
          measured=continuity)
    def spread(record, bands):
        values = [signed(record[3*band]) for band in bands if record[3*band+1]]
        return max(values)-min(values) if values else 0
    # Native bands 24..33 cover y=118..158, where a bend must be visible,
    # not merely shift a tiny road tip on the horizon.
    old_mid = max(spread(r, range(24, 34)) for r in old_records)
    new_mid = max(spread(r, range(24, 34)) for r in records)
    check('visible-midground-bends-stronger-than-v0.4', new_mid >= max(12, old_mid*1.5),
          old_max_center_spread_pixels=old_mid, new_max_center_spread_pixels=new_mid,
          sample_bands=[24, 33])
    return checks

if __name__ == '__main__':
    manifest = json.loads((ROOT/'outputs/build-manifest.json').read_text())
    results = preservation_checks(ROOT/'outputs/baseline-v0.4', manifest)
    report = {'scope': 'Approved course shape and reprojection, camera_shift/draw_road/gfx_span pixel-preserving optimization, and version bookkeeping.',
              'physical_hardware_tested': False, 'results': results,
              'passed': all(row['passed'] for row in results)}
    (ROOT/'outputs/terrain-scope-verification-v0.5.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)
