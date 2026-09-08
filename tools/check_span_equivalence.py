"""Source-bound instruction-arithmetic proof for the naked gfx_span fast path.

Checks signed clipping, all color bytes, ordered V9990 writes and SDCC call1
stack cleanup against candidate A. It also checks that the current compiler
emitted exactly the reviewed inline instructions. Native execution/timing
validation remains separate; this script never starts an emulator.

The compact tracked candidate-A fixture includes the old compiler ABI
evidence. Build the current ROM first to generate work/build/hardware.asm;
no old working directory or additional old-source compilation is required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILES = ('src/game.c', 'src/hardware.c', 'src/course.h', 'src/palette.h',
                  'assets/course.bin', 'old-hardware.asm')
OLD_FUNCTION_SHA = 'd53af6753da2aa5b84d538e5361d3cc0dac8d6e6aa8e0cbcf266e800cec03e7e'
NEW_FUNCTION_SHA = '25f619e80eeee53e187aeacf0b818e595c24cfae9f4f37a1fe51ae2b42a05f79'
BOUNDARIES = (-32768, -32767, -512, -257, -256, -255, -2, -1,
              0, 1, 2, 127, 128, 254, 255, 256, 257, 511, 512, 32766, 32767)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def baseline_integrity(baseline):
    try:
        manifest = json.loads((baseline/'SHA256.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return False, {'error': str(error)}
    expected = set(BASELINE_FILES)
    actual = {path.relative_to(baseline).as_posix() for path in baseline.rglob('*') if path.is_file()}
    missing = [name for name in BASELINE_FILES if not (baseline/name).is_file()]
    changed = [name for name in BASELINE_FILES if name not in missing
               and hashlib.sha256((baseline/name).read_bytes()).hexdigest() != manifest.get(name)]
    extra = sorted(actual - expected - {'SHA256.json'})
    return (set(manifest) == expected and not missing and not changed and not extra,
            {'payload_files': len(expected), 'manifest_entries': len(manifest),
             'missing': missing, 'changed': changed, 'extra': extra})


def function(source):
    match = re.search(r'^void gfx_span\(.*?^}', source, re.M | re.S)
    if not match:
        raise ValueError('gfx_span function missing')
    return match.group()


def normalize_asm(source):
    return '\n'.join(re.sub(r'\s+', '', line.split(';', 1)[0]).lower()
                     for line in source.splitlines() if line.split(';', 1)[0].strip())


def compiled_span(path):
    source = path.read_text(encoding='utf-8')
    return normalize_asm(source.split('_gfx_span::', 1)[1].split('_gfx_flip::', 1)[0])


def original_clip(left, right):
    if left < 0:
        left = 0
    if right > 256:
        right = 256
    if right <= left:
        return None
    return left, right-left


def instruction_clip(left, right):
    """The reviewed ASM prefix, including each 8-bit SUB/SBC carry."""
    hl, de = left & 65535, right & 65535
    if (hl >> 8) & 128:                  # BIT 7,H / JR Z / LD HL,0
        hl = 0
    if (de >> 8) & 128:                  # BIT 7,D / JR NZ,return
        return None
    if de >> 8:                         # LD A,D / OR A / JR Z / LD DE,256
        de = 256
    if hl >> 8:                         # LD A,H / OR A / JR NZ,return
        return None
    difference = (de & 255) - (hl & 255) # LD A,E / SUB L
    c = difference & 255                # LD C,A
    carry = int(difference < 0)
    difference = (de >> 8) - carry       # LD A,D / SBC A,0
    if difference < 0:                  # JR C,return
        return None
    b = difference & 255                # LD B,A
    if not b | c:                       # OR C / JR Z,return
        return None
    return hl, (b << 8) | c


def instruction_color(color):
    a = color
    e = a
    for _ in range(4):                  # ADD A,A, four times (8-bit result)
        a = (a+a) & 255
    return a | e                       # OR E


def original_io(left, right, color, y, height):
    clipped = original_clip(left, right)
    if clipped is None:
        return ()
    x, width = clipped
    color = (color | (color << 4)) & 255
    return ((0x64, 36), (0x63, x & 255), (0x63, x >> 8),
            (0x63, y & 255), (0x63, y >> 8),
            (0x63, width & 255), (0x63, width >> 8),
            (0x63, height), (0x63, 0), (0x64, 48),
            (0x63, color), (0x63, color), (0x64, 52), (0x63, 0x20))


def instruction_io(left, right, color, y, height, busy_reads=0):
    # Initial ABI stack is return-low, return-high, color, live canaries.
    initial_sp = 0xeef0
    stack = [0x34, 0x12, color, 0x78, 0x56, 0x9a]
    ix, iy = 0x2468, 0x1357
    clipped = instruction_clip(left, right)
    writes = []
    polls = 0
    if clipped is not None:
        # IN A,status / AND 1 / JR NZ: no writes while busy.
        while polls <= busy_reads:
            status = 1 if polls < busy_reads else 0
            polls += 1
            if not status & 1:
                break
        hl, bc = clipped
        # Every OUT is listed in reviewed source order, not register-state
        # equivalence alone: register select auto-increment is significant.
        writes.append((0x64, 36))
        writes.append((0x63, hl & 255))
        writes.append((0x63, 0))
        writes.append((0x63, y & 255))
        writes.append((0x63, y >> 8))
        writes.append((0x63, bc & 255))
        writes.append((0x63, bc >> 8))
        writes.append((0x63, height))
        writes.append((0x63, 0))
        address = initial_sp + 2        # LD HL,2 / ADD HL,SP
        packed = instruction_color(stack[address-initial_sp])
        writes.append((0x64, 48))
        writes.extend(((0x63, packed), (0x63, packed)))
        writes.extend(((0x64, 52), (0x63, 0x20)))
    return_pc = stack[0] | (stack[1] << 8)  # POP HL
    sp = initial_sp + 2
    sp += 1                               # INC SP / JP (HL)
    return (tuple(writes), polls, return_pc, sp-initial_sp,
            ix, iy, tuple(stack[3:]))


def verify(baseline, current_asm, old_asm):
    checks = []

    def check(name, passed, **evidence):
        checks.append({'name': name, 'passed': bool(passed), **evidence})

    intact, evidence = baseline_integrity(baseline)
    check('persistent-candidate-A-fixture-hashes-valid', intact, **evidence)
    if not intact:
        return checks
    old_source = (baseline/'src/hardware.c').read_text(encoding='utf-8')
    new_source = (ROOT/'src/hardware.c').read_text(encoding='utf-8')
    old_function, new_function = function(old_source), function(new_source)
    old_hash, new_hash = digest(old_function), digest(new_function)
    check('reviewed-old-and-new-span-functions-match-models',
          old_hash == OLD_FUNCTION_SHA and new_hash == NEW_FUNCTION_SHA,
          old_sha256=old_hash, new_sha256=new_hash)
    check('other-hardware-functions-unchanged',
          old_source.replace(old_function, 'MODELED_SPAN') == new_source.replace(new_function, 'MODELED_SPAN'))
    inline = normalize_asm(new_function.split('__asm', 1)[1].split('__endasm', 1)[0])
    compiled = compiled_span(current_asm)
    check('compiled-span-is-exact-reviewed-inline-ASM', compiled == inline,
          source_instructions_sha256=digest(inline), compiled_instructions_sha256=digest(compiled))
    old_compiled = compiled_span(old_asm) if old_asm.is_file() else ''
    abi = ('lda,4(ix)' in old_compiled and 'ora,4(ix)' in old_compiled
           and old_compiled.endswith('popix\npophl\nincsp\njp(hl)')
           and compiled.endswith('span_return:\npophl\nincsp\njp(hl)')
           and not re.search(r'\b(?:ix|iy)\b', new_function.split('__asm', 1)[1]))
    check('old-SDCC-call1-ABI-and-new-cleanup-match', abi,
          old_compiler_evidence_present=bool(old_compiled), arguments='HL left, DE right, one color byte on stack',
          old_color='4(IX) after PUSH IX', new_color='SP+2 without a prologue',
          return_stack_advance=3, ix_iy='untouched by naked function')
    if not all(row['passed'] for row in checks):
        return checks

    count = 0
    errors = []

    def compare(left, right):
        nonlocal count
        count += 1
        old, new = original_clip(left, right), instruction_clip(left, right)
        if old != new and len(errors) < 10:
            errors.append({'left': left, 'right': right, 'old': old, 'new': new})

    for left in range(-32768, 32768):
        for right in BOUNDARIES:
            compare(left, right)
        for right in (left-1, left, left+1):
            if -32768 <= right <= 32767:
                compare(left, right)
    for right in range(-32768, 32768):
        for left in BOUNDARIES:
            compare(left, right)
    # This additionally exhausts every possible post-clipping coordinate
    # combination, including rejection and 256-wide spans.
    for left in range(257):
        for right in range(257):
            compare(left, right)
    check('signed16-clipping-instruction-carry-and-boundaries', not errors,
          cases=count, all_left_values=65536, all_right_values=65536,
          opposite_coordinate_boundaries=BOUNDARIES, left_relative_right_offsets=[-1, 0, 1],
          post_clipping_pairs=257*257, exhaustive_32bit_pair_space=False, errors=errors)

    errors = [(color, instruction_color(color), (color | color << 4) & 255)
              for color in range(256) if instruction_color(color) != (color | color << 4) & 255]
    check('all-256-color-bytes-identical', not errors, cases=256, errors=errors)

    geometries = ((-32768, 32767), (-1, 256), (0, 256), (255, 256),
                  (256, 32767), (32767, 0), (-1, 0), (0, 0), (1, 0),
                  (0, 1), (254, 255), (1, 32767), (32767, 32767),
                  (-32768, -1), (0, -32768))
    positions = ((0, 2), (511, 4), (65535, 255), (112, 0))
    trace_cases = 0
    errors = []
    for left, right in geometries:
        for color in range(256):
            for y, height in positions:
                trace_cases += 1
                result = instruction_io(left, right, color, y, height, busy_reads=2)
                expected = original_io(left, right, color, y, height)
                polls = 3 if expected else 0
                if (result[0] != expected or result[1:] != (polls, 0x1234, 3, 0x2468, 0x1357, (0x78, 0x56, 0x9a))):
                    errors.append([left, right, color, y, height])
    check('ordered-V9990-byte-trace-wait-and-call-stack-equivalence', not errors,
          cases=trace_cases, io_writes_per_nonempty_span=14, errors=errors[:10],
          includes=['rejected span has no reads/writes', 'busy wait precedes writes',
                    'DX/DY/NX/NY byte order', 'color duplication', 'command 0x20',
                    'return PC', 'one-byte argument removal', 'IX/IY', 'live stack canaries'],
          zero_height='Modeled as original; callers must supply valid band heights, currently 2 or 4.')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT/'outputs/baseline-v0.5-terrain')
    parser.add_argument('--current-asm', type=Path, default=ROOT/'work/build/hardware.asm')
    parser.add_argument('--old-asm', type=Path, help='Override the tracked old-hardware.asm fixture')
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/span-equivalence-v0.5.json')
    args = parser.parse_args()
    checks = verify(args.baseline, args.current_asm, args.old_asm or args.baseline/'old-hardware.asm')
    report = {'method': 'source-bound instruction arithmetic and ordered I/O/stack model',
              'native_execution_test': False, 'physical_hardware_tested': False,
              'checks': checks, 'passed': all(row['passed'] for row in checks)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks_passed': sum(row['passed'] for row in checks),
                      'checks_total': len(checks), 'report': str(args.output)}, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
