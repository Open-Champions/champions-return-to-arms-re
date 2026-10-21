#!/usr/bin/env python3
"""Classify how each generateMonster argument is produced on a disc. Counts only.

  python3 tools/generator_names_census.py --disc DIR [--elf SLUS_209.73] [--detail FILE]
  python3 tools/generator_names_census.py --scripts DIR [--elf SLUS_209.73] [--detail FILE]
  ... --elf SLUS_209.73 --difftest [--cases N] [--seed N]

generateMonster(generator, className) is native 'ss' (docs/script-items.md 5.1). The
script machine pushes the arguments last first, then the byte count, then SYSREQ.C, so
the cell pushed just before the count is the generator and the one before that the class
name. tools/items_census.py looks only at the cells right before the call. An argument
computed by an expression puts its instructions between the pushes, so that census can
label the wrong argument. This tool evaluates each argument symbolically instead.

Each statement that ends in the call is replayed from its start (the last LINE, or the
last instruction that ends a statement) with symbolic registers PRI and ALT and a stack of
pushed values. Argument shapes:

  literal      PUSH.C of a data address: a string in the image
  table row    the address of row i of a two-level array (`table[i]`, the compiler's
               indirection vector): base + 4i + cell(base + 4i). The rows are read from the
               image; i is the variable that indexes it, with the BOUNDS limit
  other        anything else (a variable that holds an address, a parameter, ...)

For a table row the tool also:

  * reads every row (BOUNDS + 1 of them) as a candidate string;
  * lists every other reference to an address inside the table (indirection vector and
    row bytes). A reference that is not the read pattern means the table may be written
    at run time; the candidates are then not a closed set;
  * follows the index variable one level: the instructions that store it, and when the
    stored value is itself `itable[j]` of a cell array, the functions that store into
    that cell array. Each function involved is marked when it calls getRand (one
    shared-seed draw each, docs/spec/script-builtins.md 87).

With --elf every literal and candidate class name is run through the original
world_objectFactory 0x159c94 in tools/ee_emu.py (items_census.factory_probe): a
constructor, the Skeleton constructor (ScriptGenerator_spawn sends exactly Skeleton to
AI state 0x17), or no object. Names of 24 bytes or more are counted (the intern table
0x5d32c8 has 24-byte entries and copies with strcpy).

Nothing is printed but numbers and the shape names. --detail FILE writes the strings and
offsets as well; FILE must be outside the tracked tree (it holds disc text).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_amx                                  # noqa: E402

OPN = {number: name for name, number in ref_amx.OP.items()}
SKELETON_CTOR = 0x2A5AF4        # Skeleton_ctor (tools/items_census.py)
INTERN_ENTRY = 24               # bytes per entry of the name table 0x5d32c8
COMMAND = 'generateMonster'
ARGS = ('generator', 'class')
# instructions after which a new statement starts (no value is carried across them)
BOUNDARY = {'LINE', 'STACK', 'PROC', 'RETN', 'RET', 'JUMP', 'JZER', 'JNZ', 'JEQ', 'JNEQ', 'JLESS',
            'JLEQ', 'JGRTR', 'JGEQ', 'JSLESS', 'JSLEQ', 'JSGRTR', 'JSGEQ', 'SWITCH', 'CASETBL',
            'STOR.pri', 'STOR.alt', 'STOR.S.pri', 'STOR.S.alt', 'STOR.I', 'SREF.pri', 'SREF.alt',
            'SREF.S.pri', 'SREF.S.alt', 'HALT'}
STORES = {'STOR.pri', 'STOR.alt', 'INC', 'DEC', 'ZERO'}
VALUE_CONSTANTS = {'EQ.C.pri', 'EQ.C.alt', 'ADD.C', 'SMUL.C', 'SHL.C.pri', 'SHL.C.alt', 'SHR.C.pri',
                   'SHR.C.alt', 'LODB.I', 'STRB.I', 'ALIGN.pri', 'ALIGN.alt', 'LCTRL', 'SCTRL', 'MOVS',
                   'CMPS', 'FILL'}
INDEX_TABLES = {}               # id(code) -> {(function index, table base, cells)} found by index_origin


# ---- symbolic replay ----------------------------------------------------------------------------

def _row(value):
    """('row', base, index, bound) when value is the address of row index of the two-level
    array at the constant base."""
    if value[0] != 'add':
        return None
    a, b = value[1], value[2]
    for load, idx in ((a, b), (b, a)):
        if load[0] == 'ld' and load[1] == idx and idx[0] == 'idx' and idx[1][0] == 'c':
            return ('row', idx[1][1], idx[2], idx[3])
    return None


def replay(code, start, stop):
    """Run code[start:stop] symbolically; returns the stack of pushed values."""
    pri = alt = ('?', 'entry')
    bound = None
    stack = []
    for _off, (op, arg, _end) in code[start:stop]:
        name = OPN.get(op, '?')
        if name == 'PUSH.C':
            stack.append(('c', arg))
        elif name == 'PUSH':
            stack.append(('g', arg))
        elif name == 'PUSH.S':
            stack.append(('s', arg))
        elif name == 'PUSH.pri':
            stack.append(pri)
        elif name == 'PUSH.alt':
            stack.append(alt)
        elif name in ('CONST.pri', 'CONST.alt', 'LOAD.pri', 'LOAD.alt', 'LOAD.S.pri', 'LOAD.S.alt',
                      'ADDR.pri', 'ADDR.alt', 'ZERO.pri', 'ZERO.alt'):
            kind = {'CONST': 'c', 'LOAD': 'g', 'ADDR': 'a', 'ZERO': 'c'}[name.split('.')[0]]
            if name.startswith('LOAD.S'):
                kind = 's'
            value = (kind, 0 if name.startswith('ZERO') else arg)
            if name.endswith('pri'):
                pri = value
            else:
                alt = value
        elif name == 'BOUNDS':
            bound = arg
        elif name == 'POP.alt':
            alt = stack.pop() if stack else ('?', 'pop')
        elif name == 'POP.pri':
            pri = stack.pop() if stack else ('?', 'pop')
        elif name == 'IDXADDR':
            pri = ('idx', alt, pri, bound)
            bound = None
        elif name == 'LOAD.I':
            pri = ('ld', pri)
        elif name == 'MOVE.alt':
            alt = pri
        elif name == 'MOVE.pri':
            pri = alt
        elif name == 'XCHG':
            pri, alt = alt, pri
        elif name == 'ADD':
            pri = ('add', pri, alt)
            pri = _row(pri) or pri
        elif name in ('LINE', 'SYMBOL', 'SRANGE', 'FILE', 'NONE'):
            pass
        else:
            pri = ('?', name)
    return stack


def statement_start(code, pos):
    """Index of the first instruction of the statement that ends at code[pos]."""
    k = pos - 1
    while k >= 0:
        name = OPN.get(code[k][1][0], '?')
        if name in BOUNDARY or (name in ('SYSREQ.C', 'SYSREQ.pri', 'CALL') and k < pos - 1):
            return k + 1
        k -= 1
    return 0


def call_arguments(code, pos, nargs):
    """The symbolic values of the arguments of the SYSREQ.C at code[pos] (argument 0 first),
    or None when the byte count is not a constant."""
    stack = replay(code, statement_start(code, pos), pos)
    if not stack or stack[-1][0] != 'c':
        return None
    count = stack[-1][1] // 4
    pushed = stack[:-1][-count:] if count else []
    args = list(reversed(pushed))
    while len(args) < nargs:
        args.append(('?', 'missing'))
    return args


def shape(value):
    if value[0] == 'c':
        return 'literal'
    if value[0] == 'row':
        return 'table row'
    return 'other'


# ---- reading tables and following the index -----------------------------------------------------

def table_rows(machine, base, bound):
    """[(row address, bytes or None)] for rows 0..bound of the two-level array at base."""
    out = []
    for i in range((bound or 0) + 1):
        try:
            address = base + 4 * i + machine.cell(base + 4 * i)
            out.append((address, machine.get_string(address)))
        except Exception:       # noqa: BLE001  outside the image
            out.append((None, None))
    return out


def read_pattern(code, k):
    """True when the reference to a table at code[k] is `PUSH.C base; <load index>; BOUNDS;
    POP.alt; IDXADDR; ...`: an element read (row address or cell value)."""
    names = [OPN.get(code[j][1][0], '?') for j in range(k + 1, min(k + 8, len(code)))
             if OPN.get(code[j][1][0], '?') not in ('LINE', 'SYMBOL')]
    if len(names) < 4 or OPN.get(code[k][1][0]) != 'PUSH.C':
        return False
    return (names[0] in ('LOAD.pri', 'LOAD.S.pri', 'CONST.pri') and names[1] == 'BOUNDS'
            and names[2] == 'POP.alt' and names[3] == 'IDXADDR'
            and (len(names) < 5 or names[4] in ('MOVE.alt', 'LOAD.I', 'PUSH.pri')))


def element_store(code, k):
    """True when the reference at code[k] starts `PUSH.C base; ...; IDXADDR; MOVE.alt; ...;
    STOR.I` or ends in STOR.I before the next statement: a store into the table."""
    for j in range(k + 1, min(k + 40, len(code))):
        name = OPN.get(code[j][1][0], '?')
        if name in ('STOR.I', 'STRB.I'):
            return True
        if name in ('LINE', 'STACK', 'SYSREQ.C', 'CALL', 'RETN') and j > k + 1:
            return False
    return False


def references(code, lo, hi):
    """[(index, name)] of instructions whose operand is an address in [lo, hi)."""
    out = []
    for k, (_off, (op, arg, _end)) in enumerate(code):
        name = OPN.get(op, '?')
        if name in ('LINE', 'SYMBOL', 'SRANGE', 'FILE', 'BOUNDS', 'STACK', 'HEAP') or not isinstance(arg, int):
            continue
        if name.startswith('J') or name in ('CALL', 'SWITCH', 'CASETBL', 'SYSREQ.C') or name in VALUE_CONSTANTS:
            continue                # code targets, native numbers and value constants
        if lo <= arg < hi:
            out.append((k, name))
    return out


def function_of(code, k):
    while k > 0 and OPN.get(code[k][1][0]) != 'PROC':
        k -= 1
    return k


def function_calls(code, start, natives, wanted):
    k = start + 1
    n = 0
    while k < len(code) and OPN.get(code[k][1][0]) != 'PROC':
        op, arg = code[k][1][0], code[k][1][1]
        if OPN.get(op) == 'SYSREQ.C' and isinstance(arg, int) and 0 <= arg < len(natives) \
                and natives[arg] == wanted:
            n += 1
        k += 1
    return n


def index_origin(code, natives, index):
    """How the index variable of a table row is produced: a list of (what, function start,
    getRand calls in that function)."""
    if index[0] != 'g':
        return [('index not a global', None, 0)]
    out = []
    for k, (_off, (op, arg, _end)) in enumerate(code):
        name = OPN.get(op, '?')
        if name not in STORES or arg != index[1]:
            continue
        func = function_of(code, k)
        if name != 'STOR.pri':
            out.append(('counter ' + name, func, function_calls(code, func, natives, 'getRand')))
            continue
        stack_value = replay(code, statement_start(code, k), k + 1)
        value = _pri_before(code, k)
        if value[0] == 'ld' and value[1][0] == 'idx' and value[1][1][0] == 'c':
            base = value[1][1][1]
            size = 4 * ((value[1][3] or 0) + 1)
            out.append(('element of an index table', func, function_calls(code, func, natives, 'getRand')))
            for j, _n in references(code, base, base + size):
                if element_store(code, j):
                    f2 = function_of(code, j)
                    out.append(('store into that index table', f2, function_calls(code, f2, natives, 'getRand')))
                    INDEX_TABLES.setdefault(id(code), set()).add((f2, base, size // 4))
        else:
            out.append(('stored ' + value[0], func, function_calls(code, func, natives, 'getRand')))
        del stack_value
    seen, unique = set(), []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _pri_before(code, k):
    """The symbolic PRI just before code[k]."""
    start = statement_start(code, k)
    pri = ('?', 'entry')
    stack = []
    alt = ('?', 'entry')
    bound = None
    for _off, (op, arg, _end) in code[start:k]:
        name = OPN.get(op, '?')
        if name == 'PUSH.C':
            stack.append(('c', arg))
        elif name == 'PUSH.pri':
            stack.append(pri)
        elif name in ('LOAD.pri', 'CONST.pri', 'LOAD.S.pri'):
            pri = ('g' if name == 'LOAD.pri' else 'c' if name == 'CONST.pri' else 's', arg)
        elif name in ('LOAD.alt', 'CONST.alt'):
            alt = ('g' if name == 'LOAD.alt' else 'c', arg)
        elif name == 'BOUNDS':
            bound = arg
        elif name == 'POP.alt':
            alt = stack.pop() if stack else ('?', 'pop')
        elif name == 'IDXADDR':
            pri, bound = ('idx', alt, pri, bound), None
        elif name == 'LOAD.I':
            pri = ('ld', pri)
        elif name == 'MOVE.alt':
            alt = pri
        elif name == 'MOVE.pri':
            pri = alt
        elif name in ('LINE', 'SYMBOL'):
            pass
        else:
            pri = ('?', name)
    return pri


# ---- the census ---------------------------------------------------------------------------------

def sites(machine):
    """[(code index, offset, [arg values])] of every generateMonster call."""
    natives = [machine.native_name(k).decode('latin-1', 'replace') for k in range(max(machine.num_natives, 0))]
    code = sorted(machine._decoded.items())
    out = []
    for pos, (off, (op, arg, _end)) in enumerate(code):
        if OPN.get(op) == 'SYSREQ.C' and isinstance(arg, int) and 0 <= arg < len(natives) \
                and natives[arg] == COMMAND:
            out.append((pos, off, call_arguments(code, pos, 2)))
    return natives, code, out


def string_bytes(machine, address, text):
    """Bytes the string at address takes, terminator included: packed (first cell above 0xff,
    four characters a cell) or unpacked (a cell a character), as ref_amx.get_string reads it."""
    n = len(text or b'')
    try:
        packed = machine.cell(address) >= 0x100
    except Exception:           # noqa: BLE001
        return 4
    return 4 * (n // 4 + 1) if packed else 4 * (n + 1)


def string_of(machine, address):
    try:
        return machine.get_string(address)
    except Exception:           # noqa: BLE001
        return None


def census(images, factory=None, detail=None):
    """factory(name) -> (size, constructor) or None to skip. detail: a list that receives
    human-readable lines with disc text (keep it out of tracked files)."""
    r = {'scripts': len(images), 'refused': 0, 'calls': 0, 'scripts_with_calls': 0,
         'shape': {}, 'class_literal_names': set(), 'class_candidates': set(),
         'tables': 0, 'indexes': 0, 'table_rows': 0, 'table_other_refs': 0, 'table_written': 0,
         'origin': {}, 'getrand_functions': set(), 'factory': {}, 'long': 0,
         'per_script_upper': 0, 'per_script_literal': 0}
    tables_seen = set()
    for si, image in enumerate(images):
        machine = ref_amx.Machine(image)
        if machine.load() != 0:
            r['refused'] += 1
            continue
        natives, code, found = sites(machine)
        if not found:
            continue
        r['scripts_with_calls'] += 1
        lits, upper = set(), set()
        for pos, off, args in found:
            r['calls'] += 1
            if args is None:
                r['shape'][('call', 'count not constant')] = r['shape'].get(('call', 'count not constant'), 0) + 1
                continue
            key = tuple(shape(a) for a in args[:2])
            r['shape'][key] = r['shape'].get(key, 0) + 1
            for which, value in zip(ARGS, args[:2]):
                if value[0] == 'c' and which == 'class':
                    text = string_of(machine, value[1])
                    if text is not None:
                        lits.add(text)
                        upper.add(text)
                        r['class_literal_names'].add(text)
                if value[0] != 'row':
                    continue
                _row_tag, base, index, bound = value
                rows = table_rows(machine, base, bound)
                tag = (si, base)
                if tag not in tables_seen:
                    tables_seen.add(tag)
                    r['tables'] += 1
                    r['table_rows'] += len(rows)
                    vector_end = base + 4 * len(rows)
                    row_end = max([a + string_bytes(machine, a, t) for a, t in rows if a is not None] + [vector_end])
                    others = [(k, n) for k, n in references(code, base, row_end) if not read_pattern(code, k)]
                    r['table_other_refs'] += len(others)
                    written = [k for k, _n in others if element_store(code, k)] + \
                        [k for k, n in others if n in STORES or n.startswith('STOR') or n.startswith('SREF')]
                    if written:
                        r['table_written'] += 1
                    if detail is not None:
                        detail.append('script %d table %#x (%s) rows %d other refs %r' % (
                            si, base, which, len(rows), [(code[k][0], n) for k, n in others]))
                        for _a, t in rows:
                            detail.append('    row %r' % (t,))
                if (si, base, which, index) not in tables_seen:      # each index variable once
                    tables_seen.add((si, base, which, index))
                    r['indexes'] += 1
                    for what, func, draws in index_origin(code, natives, index):
                        r['origin'][(which, what)] = r['origin'].get((which, what), 0) + 1
                        if draws:
                            r['getrand_functions'].add((si, func, draws))
                        if detail is not None:
                            detail.append('script %d index %r: %s in function %r, getRand sites %d' % (
                                si, index, what, code[func][0] if func is not None else None, draws))
                if which == 'class':
                    for _a, t in rows:
                        if t is not None:
                            r['class_candidates'].add(t)
                            upper.add(t)
            if detail is not None:
                detail.append('script %d call %#x args %r' % (si, off, args[:2]))
        r['per_script_upper'] = max(r['per_script_upper'], len(upper))
        r['per_script_literal'] = max(r['per_script_literal'], len(lits))
    r['detail'] = detail
    names = r['class_literal_names'] | r['class_candidates']
    r['long'] = sum(1 for n in names if len(n) >= INTERN_ENTRY)
    if factory is not None:
        for group, pool in (('literal', r['class_literal_names']), ('candidate', r['class_candidates'])):
            for name in sorted(pool):
                size, ctor = factory(name)
                if r.get('detail') is not None:
                    r['detail'].append('factory %s %r -> %r %r' % (group, name, size, ctor))
                label = 'no object' if size is None else ('stopped' if size == 'stopped' else 'constructor')
                if ctor == SKELETON_CTOR:
                    label = 'Skeleton constructor'
                r['factory'][(group, label)] = r['factory'].get((group, label), 0) + 1
    return r


def report(r):
    print('scripts %d' % r['scripts'])
    print('refused %d' % r['refused'])
    print('generateMonster calls %d in %d scripts' % (r['calls'], r['scripts_with_calls']))
    print('argument shapes (generator, class)')
    for key, n in sorted(r['shape'].items()):
        print('  %s %d' % (' / '.join(key), n))
    print('class names: literal distinct %d, table candidates distinct %d, both %d' % (
        len(r['class_literal_names']), len(r['class_candidates']),
        len(r['class_literal_names'] | r['class_candidates'])))
    print('candidates that are also literals elsewhere %d' % len(r['class_candidates'] & r['class_literal_names']))
    print('tables %d, rows %d, references other than an element read %d, tables stored into %d' % (
        r['tables'], r['table_rows'], r['table_other_refs'], r['table_written']))
    print('index variables %d; their origin (argument, what)' % r['indexes'])
    for key, n in sorted(r['origin'].items()):
        print('  %s %s %d' % (key[0], key[1], n))
    print('functions on an index path that call getRand %d (getRand sites in them: %s)' % (
        len(r['getrand_functions']), ','.join(str(d) for _s, _f, d in sorted(r['getrand_functions']))))
    print('names of %d bytes or more %d' % (INTERN_ENTRY, r['long']))
    print('most distinct class names in one script: literal %d, literal + candidates %d' % (
        r['per_script_literal'], r['per_script_upper']))
    for key, n in sorted(r['factory'].items()):
        print('factory %s %s %d' % (key[0], key[1], n))


def factory_probe(elf, name):
    """(pool size, constructor) that the original world_objectFactory 0x159c94 picks for name,
    or (None, None) when it makes no object. Like items_census.factory_probe, but after
    pool_new 0x14fdb8 every call is stubbed (returning its a0) and the constructor is the
    first call that receives the block in a0: the 'prefix Orc' row of docs/objects.md calls
    0x217edc before its constructor."""
    from ee_emu import EE
    emu = EE(elf)
    block = emu.alloc(0x1000)
    asked, state = [], {'after': False, 'ctor': None}
    emu.stub(0x14FDB8, function=lambda e: asked.append(e.r[4] & 0xFFFFFFFF) or block)
    original = emu._enter_call

    def enter(target):
        if state['after'] and target != 0x14FDB8:
            if state['ctor'] is None and emu.r[4] & 0xFFFFFFFF == block:
                state['ctor'] = target
            emu.stub(target, function=lambda e: e.r[4] & 0xFFFFFFFF)
        if target == 0x14FDB8:
            state['after'] = True
        return original(target)
    emu._enter_call = enter
    text = emu.alloc(len(name) + 1)
    emu.mem.write(text, name + b'\0')
    pos, props = emu.alloc(16), emu.alloc(16)
    emu.default_ret = 0
    try:
        emu.call(0x159C94, text, pos, 0, props, max_steps=3000000)
    except Exception:           # noqa: BLE001  stopped inside the factory
        return ('stopped', None)
    return (asked[0] if asked else None, state['ctor'])


class Lcg:
    """getRand 0x146570 (docs/spec/script-builtins.md 87): seed = seed * 0x19660d + 0x3c6ef35f,
    result seed >> 16. Stands in for the native results on both sides of the difftest."""

    def __init__(self, seed):
        self.seed = seed & 0xFFFFFFFF

    def next(self):
        self.seed = (self.seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        return self.seed >> 16


def difftest(images, elf, cases, seed, detail=None):
    """Runs every function that stores into a class-name index table (and calls getRand) on
    the original script machine in tools/ee_emu.py and on tools/ref_amx.py, as
    difftest_amx.ScriptPair does, with getRand answered by Lcg from a seeded start. Compares
    native trace, error, result, machine words and every data byte. Returns a dict with the
    case and mismatch counts, the getRand calls per run, and the index-table values seen."""
    import random
    import difftest_amx as A
    rng = random.Random(seed)
    orig = A.Original(elf)
    out = {'functions': 0, 'cases': 0, 'bad': 0, 'host': 0, 'endless': 0, 'draws': set(), 'reached': {},
           'rows_reached': 0, 'rows': 0, 'examples': []}
    for si, image in enumerate(images):
        machine = ref_amx.Machine(image)
        if machine.load() != 0:
            continue
        natives, code, found = sites(machine)
        tables = {}
        for _pos, _off, args in found or ():
            if args and args[1][0] == 'row':
                INDEX_TABLES.pop(id(code), None)
                origin = index_origin(code, natives, args[1][2])
                for func, base, cells in INDEX_TABLES.get(id(code), ()):
                    if any(f == func and d for _w, f, d in origin):
                        tables.setdefault((func, base, cells), set()).add((args[1][1], args[1][3]))
        if not tables:
            continue
        publics = {offset: k for k, (_name, offset) in enumerate(machine.publics())}
        pair = A.ScriptPair(orig, bytes(image) + bytes(256), 'script %d' % si)
        a, b = orig.load(), pair.model.load()
        if (a, b) != (0, 0):
            out['bad'] += 1
            continue
        pair.bind(rng)
        saved, saved_model = orig.save(len(image) + 256), pair.model.snapshot()
        for (func, base, cells), class_tables in sorted(tables.items()):
            index = publics.get(code[func][0])
            if index is None:
                out['examples'].append('script %d: the shuffle function is not an entry point' % si)
                continue
            out['functions'] += 1
            seen = set()
            tally = A.Tally()
            for _case in range(cases):
                orig.restore(saved)
                pair.model.restore(saved_model)
                start = rng.getrandbits(32)
                A.Returns = lambda _seed, start=start: Lcg(start)       # both sides, same sequence
                outcome = pair.run(index, 0, 0, 'script %d case' % si, tally,
                                   {'runs': 0, 'instructions': 0, 'calls': 0, 'strings': 0, 'nested': 0,
                                    'errors': {}, 'host': [], 'moved': {}})
                out['cases'] += 1
                if outcome != 'ok':
                    out[{'bad': 'bad', 'host': 'host', 'endless': 'endless'}[outcome]] += 1
                    continue
                out['draws'].add(len(pair.m.trace))
                seen.add(tuple(pair.model.cell(base + 4 * k) for k in range(cells)))
            out['examples'] += tally.examples
            values = {v for row in seen for v in row}
            for table, bound in class_tables:
                rows = table_rows(machine, table, bound)
                ok = sorted(v for v in values if 0 <= v <= bound)
                out['rows'] += len(rows)
                out['rows_reached'] += len(ok)
                out['reached'][(si, table)] = (len(ok), len(rows), len(seen), sorted(values - set(ok)))
                if detail is not None:
                    detail.append('difftest script %d table %#x: values %r -> rows %r' % (
                        si, table, sorted(values), [rows[v][1] for v in ok]))
    return out


def main(argv):
    import items_census as C
    elf = argv[argv.index('--elf') + 1] if '--elf' in argv else None
    if '--disc' in argv:
        images, refused = C.images_from_disc(argv[argv.index('--disc') + 1])
    elif '--scripts' in argv:
        images, refused = C.images_from_dir(argv[argv.index('--scripts') + 1])
    else:
        print(__doc__)
        return 2
    detail = [] if '--detail' in argv else None
    cache = {}

    def factory(name):
        if name not in cache:
            cache[name] = factory_probe(elf, name)
        return cache[name]
    r = census(images, factory if elf else None, detail)
    r['refused'] += refused
    report(r)
    if elf and '--difftest' in argv:
        cases = int(argv[argv.index('--cases') + 1]) if '--cases' in argv else 100
        seed = int(argv[argv.index('--seed') + 1]) if '--seed' in argv else 20973
        d = difftest(images, elf, cases, seed, detail)
        print('difftest (seed %d): %d shuffle functions, %d cases, %d differ, %d host faults, %d endless' % (
            seed, d['functions'], d['cases'], d['bad'], d['host'], d['endless']))
        print('getRand calls per run: %s' % ','.join(str(n) for n in sorted(d['draws'])))
        print('class-table rows reached %d of %d' % (d['rows_reached'], d['rows']))
        for (_si, _table), (ok, rows, perms, outside) in sorted(d['reached'].items()):
            print('  table: %d of %d rows reached, %d distinct index tables, values outside the rows %d' % (
                ok, rows, perms, len(outside)))
        for line in d['examples'][:5]:
            print('  ' + line)
    if detail is not None:
        with open(argv[argv.index('--detail') + 1], 'w') as out:
            out.write('\n'.join(detail) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
