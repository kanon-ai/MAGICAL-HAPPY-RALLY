"""Exact host-side proof for the approved v0.5 render-only optimization.

The two reviewed C functions are hash-bound to these models. Every course
phase/player position is covered; identical horizontal span states share an
exact interval proof instead of allocating billions of individual pixels.
An untouched-background sentinel proves equivalence over any sky/ground.
This is not a substitute for native instruction, timing or VRAM validation.
"""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILES = ('src/game.c', 'src/hardware.c', 'src/course.h', 'src/palette.h',
                  'assets/course.bin', 'old-hardware.asm')
SCRATCH_DECLARATIONS = ('static s16 road_asm_c,road_asm_left,road_asm_right;\n'
                        'static u8 road_asm_i;\n\n')
FUNCTION_HASHES = {
    "old": {
        "camera_shift": "591aded929e1feee06ab9373a77103e1112bc79a11a109e446e1f237d6eb2019",
        "draw_road": "70bc0563759ea3a804d04b0b1af13aa5aff457a25a89c8792555df3c1b0b2912",
    },
    "new": {
        "camera_shift": "36329de146ec8923a8a44e97638110afcc5b9bd106670820abfa2bf20418d714",
        "draw_road": "d77ad019add442b25bc8031fddd2872e86ec0172be8ec2d35e5e7cc46e6baf05",
    },
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def baseline_integrity(baseline):
    try:
        manifest = json.loads((baseline/'SHA256.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return False, {'error': str(error)}
    expected = set(BASELINE_FILES)
    actual = {path.relative_to(baseline).as_posix() for path in baseline.rglob('*') if path.is_file()}
    missing = [name for name in BASELINE_FILES if not (baseline/name).is_file()]
    changed = [name for name in BASELINE_FILES if name not in missing
               and digest((baseline/name).read_bytes()) != manifest.get(name)]
    extra = sorted(actual - expected - {'SHA256.json'})
    return (set(manifest) == expected and not missing and not changed and not extra,
            {'payload_files': len(expected), 'manifest_entries': len(manifest),
             'missing': missing, 'changed': changed, 'extra': extra})


def function(source, name):
    match = re.search(r"^static (?:s16|void) " + name + r"\(.*?^}", source, re.M | re.S)
    if not match:
        raise ValueError(f"Missing modeled function: {name}")
    return match.group()


def array(source, name):
    match = re.search(r"\b" + name + r"\[41\]\s*=\s*\{([^}]+)\}", source)
    if not match:
        raise ValueError(f"Missing band array: {name}")
    return tuple(map(int, match.group(1).split(',')))


def original_shift(player, halfwidth):
    magnitude = (abs(player) * halfwidth) >> 6
    return -magnitude if player < 0 else magnitude


def optimized_shift(player, halfwidth):
    # MULUB -> ADD HL,HL -> ADD HL,HL -> LD L,H -> LD H,0 -> RL H.
    hl = abs(player) * halfwidth
    hl = (hl << 1) & 65535
    carry = (hl >> 15) & 1
    hl = (hl << 1) & 65535
    magnitude = (carry << 8) | (hl >> 8)
    return -magnitude if player < 0 else magnitude


def signed_word(value):
    value &= 65535
    return value if value < 32768 else value-65536


def assembly_center(offset, player, width):
    byte = offset & 255
    # LD L,A / RLCA / SBC A,A / LD H,A sign-extends the profile byte.
    hl = byte | (65280 if byte & 128 else 0)
    hl = (hl+128) & 65535
    # OR A clears carry before SBC HL,DE; DE is camera_shift's call1 result.
    return signed_word(hl-(optimized_shift(player, width >> 1) & 65535))


def rotate_right(byte, count):
    for _ in range(count):
        byte = (byte >> 1) | ((byte & 1) << 7)
    return byte


def assembly_spans(center, width, flag, tracks):
    """Independent 8/16-bit model of reviewed naked road-loop arithmetic."""
    left = (center-width) & 65535
    right = (left+width+width) & 65535
    d, e, h = left >> 8, left & 255, right >> 8
    # BIT 7,D; D|E; then BIT 7,H and H!=0 test the full-width condition.
    shoulders = (not d & 128 and bool(d | e)) or bool(h & 128) or not h
    result = []
    if shoulders:
        if flag & 1:
            c = (width << 1) & 255       # SLA C / RL B, initial B=0
            b = width >> 7
            twice_width = b*256+c
            result.append(clip_span(signed_word(left-twice_width),
                                    signed_word(right+twice_width), 7))
        edge = (rotate_right(width, 4) & 15)+1
        result.append(clip_span(signed_word(left-edge), signed_word(right+edge), 11))
    result.append(clip_span(signed_word(left), signed_word(right), 9+(flag & 1)))
    if tracks:
        quarter = rotate_right(width, 2) & 63
        # RLCA twice / AND 3 is the top two bits; INC A adds one pixel.
        stripe_width = (((width << 2) | (width >> 6)) & 3)+1
        for x in ((center-quarter) & 65535, (center+quarter) & 65535):
            low_sum = (x & 255)+stripe_width
            e = low_sum & 255
            d = ((x >> 8)+int(low_sum > 255)) & 255  # ADD A,E / JR NC / INC D
            result.append(clip_span(signed_word(x), signed_word(d*256+e), 9))
    return tuple(span for span in result if span is not None)


def normalize_asm(source):
    return '\n'.join(re.sub(r'\s+', '', line.split(';', 1)[0]).lower()
                     for line in source.splitlines() if line.split(';', 1)[0].strip()
                     and not line.strip().startswith('.globl'))


def emitted_array(source, name):
    block = source.split('_'+name+':', 1)[1]
    block = re.split(r'^[_A-Za-z][\w$]*:', block, maxsplit=1, flags=re.M)[0]
    return tuple(int(value, 16) for value in re.findall(r'\.db\s+#0x([0-9a-f]+)', block, re.I))


def compiled_road_checks(new_source, band_y, band_h):
    assembly = (ROOT/'work/build/game.asm').read_text(encoding='utf-8')
    listing = (ROOT/'work/build/game.lst').read_text(encoding='utf-8')
    source = function(new_source, 'draw_road').split('__asm', 1)[1].split('__endasm', 1)[0]
    for name, value in (('COL_GRASS_ALT', 7), ('COL_VERGE', 11), ('COL_ROAD', 9), ('COURSE_BANDS', 41)):
        source = source.replace(name, str(value))
    source = normalize_asm(source)
    compiled = normalize_asm(assembly.split('_draw_road:', 1)[1].split('_init_encounters:', 1)[0])
    addresses = {name: int(re.search(r'^\s*([0-9A-F]{8})\s+\d+ _'+name+':', listing, re.M).group(1), 16)
                 for name in ('band_y', 'band_h')}
    offset = addresses['band_h']-addresses['band_y']
    table_ok = (offset == 41 and emitted_array(assembly, 'band_y') == band_y
                and emitted_array(assembly, 'band_h') == band_h
                and bool(re.search(r'FD 7E 29.*ld a,_band_h-_band_y\(iy\)', listing))
                and bool(re.search(r'FE 29.*cp #41', listing)))
    scratch = {name: int(re.search(r'^_'+name+r':\s*\.ds (\d+)', assembly, re.M).group(1))
               for name in ('road_asm_c', 'road_asm_left', 'road_asm_right', 'road_asm_i')}
    lines = compiled.splitlines()
    calls = [i for i, line in enumerate(lines) if line == 'call_gfx_span']
    argument_sites = all(lines[i-2:i] == ['pushaf', 'incsp']
                         or lines[i-4:i] == ['pushaf', 'incsp', 'ldhl,(_road_asm_left)', 'ldde,(_road_asm_right)']
                         for i in calls)
    stack_ok = (lines[:2] == ['pushix', 'pushiy'] and lines[-3:] == ['popiy', 'popix', 'ret']
                and len(calls) == lines.count('pushaf') == lines.count('incsp') == 5
                and argument_sites and sum(scratch.values()) == 7)
    pointer_ok = ('road_asm_next:\nincix\nincix\nincix\ninciy\n' in compiled
                  and 'cp#41\njpc,road_asm_loop' in compiled)
    return [
        {'name': 'compiled-road-is-exact-reviewed-inline-ASM', 'passed': source == compiled,
         'source_instructions_sha256': digest(source.encode()), 'compiled_instructions_sha256': digest(compiled.encode())},
        {'name': 'compiled-41-band-tables-offset-and-seven-byte-scratch', 'passed': table_ok and pointer_ok,
         'indexed_table_offset': offset, 'band_count': 41, 'profile_bytes_advanced': 123,
         'scratch_bytes': scratch, 'table_source_and_emitted_bytes_identical': table_ok},
        {'name': 'naked-road-IX-IY-and-call1-stack-balanced', 'passed': stack_ok,
         'span_call_sites': len(calls), 'color_argument_bytes_each': 1,
         'argument_setup_sp_change': -1, 'callee_span_return_sp_change': 3,
         'call_instruction_sp_change': -2, 'entry_to_return_sp_change': 2,
         'ix_iy': 'PUSH IX/PUSH IY, POP IY/POP IX; camera_shift and gfx_span preserve these registers'},
    ]


def clip_span(left, right, color):
    left = max(0, left)
    right = min(256, right)
    return (left, right, color) if right > left else None


def spans(center, width, flag, tracks, optimized):
    """Ordered gfx_span calls, including clipping and zero-area rejection."""
    left, right = center - width, center + width
    result = []
    if not optimized or left > 0 or right < 256:
        if flag:
            result.append(clip_span(center - 3 * width, center + 3 * width, 7))
        edge = 1 + (width >> 4)
        result.append(clip_span(left - edge, right + edge, 11))
    result.append(clip_span(left, right, 10 if flag else 9))
    if tracks:
        for x in (center - (width >> 2), center + (width >> 2)):
            result.append(clip_span(x, x + 1 + (width >> 6), 9))
    return tuple(span for span in result if span is not None)


def final_color(ordered, x):
    for left, right, color in reversed(ordered):
        if left <= x < right:
            return color
    return -1  # Preserve the same arbitrary preexisting pixel.


@lru_cache(maxsize=None)
def compare_span_state(center, width, flag, tracks):
    before = spans(center, width, flag, tracks, False)
    after = assembly_spans(center, width, flag, tracks)
    expected_commands = spans(center, width, flag, tracks, True)
    if after != expected_commands:
        raise ValueError({'center': center, 'width': width, 'flag': flag, 'tracks': tracks,
                          'ASM_spans': after, 'expected_spans': expected_commands})
    # All integer pixels in [left,right) have the same final color. Taking
    # the union of both models' endpoints checks every pixel, not samples.
    boundaries = sorted({0, 256} | {x for row in before + after for x in row[:2]})
    for left, right in zip(boundaries, boundaries[1:]):
        if final_color(before, left) != final_color(after, left):
            raise ValueError({"center": center, "width": width, "flag": flag,
                              "tracks": tracks, "different_interval": [left, right],
                              "before": before, "after": after})
    return (len(before), len(after), sum(r - l for l, r, _ in before),
            sum(r - l for l, r, _ in after))


def verify(baseline):
    checks = []

    def check(name, passed, **evidence):
        checks.append({"name": name, "passed": bool(passed), **evidence})

    intact, evidence = baseline_integrity(baseline)
    check('persistent-candidate-A-fixture-hashes-valid', intact, **evidence)
    if not intact:
        return checks
    old_source = (baseline / 'src/game.c').read_text(encoding='utf-8')
    new_source = (ROOT / 'src/game.c').read_text(encoding='utf-8')
    actual_hashes = {}
    remainders = []
    for label, source in (("old", old_source), ("new", new_source)):
        actual_hashes[label] = {}
        remainder = source
        for name in FUNCTION_HASHES[label]:
            body = function(source, name)
            actual_hashes[label][name] = digest(body.encode('utf-8'))
            remainder = remainder.replace(body, f"MODELED_FUNCTION_{name}")
        if label == 'new':
            remainder = remainder.replace(SCRATCH_DECLARATIONS, '', 1)
        remainders.append(remainder)
    check('reviewed-C-functions-match-exact-models', actual_hashes == FUNCTION_HASHES,
          actual=actual_hashes, expected=FUNCTION_HASHES)
    check('all-other-game-functions-unchanged', remainders[0] == remainders[1]
          and new_source.count(SCRATCH_DECLARATIONS) == 1,
          allowed_functions=list(FUNCTION_HASHES['new']),
          allowed_global_declarations=SCRATCH_DECLARATIONS.splitlines(), scratch_bytes=7)
    preserved = ('assets/course.bin', 'src/course.h', 'src/palette.h')
    changed = [name for name in preserved if (baseline/name).read_bytes() != (ROOT/name).read_bytes()]
    check('candidate-A-course-bands-and-palette-unchanged', not changed, changed=changed,
          course_sha256=digest((ROOT/'assets/course.bin').read_bytes()))

    camera_errors = []
    for player in range(-144, 145):
        for halfwidth in range(128):
            old = original_shift(player, halfwidth)
            new = optimized_shift(player, halfwidth)
            # Integer absolute-value arithmetic preserves C truncation to 0.
            expected = abs(player * halfwidth) // 64 * (-1 if player < 0 else 1)
            if old != new or new != expected:
                camera_errors.append([player, halfwidth, old, new, expected])
    check('R800-five-instruction-quotient-all-valid-inputs', not camera_errors,
          cases=289*128, player_range=[-144, 144], halfwidth_range=[0, 127],
          maximum_product=144*127, errors=camera_errors[:10])

    course = (ROOT/'assets/course.bin').read_bytes()
    header = (ROOT/'src/course.h').read_text()
    band_y, band_h = array(header, 'band_y'), array(header, 'band_h')
    layout_ok = (len(course) == 1024*256 and len(band_y) == len(band_h) == 41
                 and all(h > 0 for h in band_h)
                 and all(band_y[i]+band_h[i] == band_y[i+1] for i in range(40))
                 and band_y[0] == 64 and band_y[-1]+band_h[-1] == 186)
    check('band-height-and-double-buffer-Y-equivalence', layout_ok,
          band_y=band_y, band_h=band_h, pages=[0, 1],
          explanation='Both models use page*256+band_y[i]; pointers advance even for hidden bands.')
    checks.extend(compiled_road_checks(new_source, band_y, band_h))
    # The naked loop initializes IX=profile, IY=band_y and index=0 each call.
    # Walk its actual increments even on hidden bands, including both pages.
    loop_errors = []
    tables = band_y+band_h
    for phase in range(1024):
        record = course[phase*256:(phase+1)*256]
        for page in (0, 1):
            ix = iy = index = 0
            visited = []
            while index < 41:
                if record[ix+1]:
                    visited.append((ix, (page << 8) | tables[iy], tables[iy+41]))
                ix += 3
                iy += 1
                index += 1
            expected = [(i*3, page*256+band_y[i], band_h[i]) for i in range(41) if record[i*3+1]]
            if visited != expected or (ix, iy, index) != (123, 41, 41):
                loop_errors.append([phase, page])
    check('instruction-loop-covers-all-41-bands-on-both-pages', not loop_errors,
          calls=2048, includes_hidden_band_pointer_advance=True, errors=loop_errors[:10])
    if not all(item['passed'] for item in checks):
        return checks

    scenarios = band_cases = hidden_bands = commands_before = commands_after = 0
    pixels_before = pixels_after = full_width_bands = 0
    failure = None
    compare_span_state.cache_clear()
    try:
        for phase in range(1024):
            record = course[phase*256:(phase+1)*256]
            bands = [(byte if byte < 128 else byte-256, record[i*3+1],
                      record[i*3+2] & 1, i > 36, band_h[i])
                     for i, byte in enumerate(record[:123:3])]
            for player in range(-144, 145):
                scenarios += 1
                for index, (offset, width, flag, near_tracks, height) in enumerate(bands):
                    band_cases += 1
                    if not width:
                        hidden_bands += 1
                        continue
                    old_center = 128 + offset - original_shift(player, width >> 1)
                    new_center = assembly_center(offset, player, width)
                    if old_center != new_center:
                        raise ValueError(f"Center mismatch at phase {phase}, player {player}")
                    if index == 40 and old_center-128 != signed_word((new_center & 65535)-128):
                        raise ValueError(f"road_center mismatch at phase {phase}, player {player}")
                    a, b, pa, pb = compare_span_state(old_center, width, flag, bool(flag and near_tracks))
                    commands_before += a
                    commands_after += b
                    pixels_before += pa * height
                    pixels_after += pb * height
                    full_width_bands += old_center-width <= 0 and old_center+width >= 256
    except ValueError as error:
        failure = str(error)
    expected_scenarios = 1024*289
    check('all-phases-all-player-positions-final-road-pixels-identical',
          failure is None and scenarios == expected_scenarios and band_cases == expected_scenarios*41,
          failure=failure, scenarios=scenarios, phases=1024, player_range=[-144, 144],
          band_cases=band_cases, hidden_band_cases=hidden_bands,
          unique_interval_proofs=compare_span_state.cache_info().currsize,
          scanline_pixels_represented=scenarios*256*sum(band_h),
          includes=['clipping', 'arbitrary background', 'band height', 'both stripe colors',
                    'grass shading', 'verge', 'near gravel tracks', 'signed camera shift'],
          full_width_band_cases=full_width_bands,
          span_commands_before=commands_before, span_commands_after=commands_after,
          filled_pixels_before=pixels_before, filled_pixels_after=pixels_after)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT/'outputs/baseline-v0.5-terrain')
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/render-equivalence-v0.5.json')
    args = parser.parse_args()
    checks = verify(args.baseline)
    report = {"method": "exact source-bound host interval and instruction arithmetic models",
              "native_validation": False, "physical_hardware_tested": False,
              "checks": checks, "passed": all(item['passed'] for item in checks)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({"passed": report['passed'], "checks_passed": sum(item['passed'] for item in checks),
                      "checks_total": len(checks), "report": str(args.output)}, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
