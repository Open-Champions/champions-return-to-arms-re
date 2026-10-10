#!/usr/bin/env python3
"""flagxref.py ELF MASKHEX [FIELDOFF=c] [options] -- tests, sets, clears and toggles of flag
bits in a structure word. MASKHEX is the bit (or bits) asked about, numbered within the word
that starts at byte FIELDOFF (hex); the word may be 8 bytes wide (give a 64-bit mask).

  --stores                also list whole-word stores at the displacement whose value is not
                          the same word read back (constants, copies from elsewhere, values
                          the pass lost): each may set or clear the bit
  --class NAME[,NAME] / --func HEX[,HEX] / --range LO:HI / --this    as in fieldxref.py
  --static BASE[,STRIDE[,COUNT]]   the structure also exists at a fixed address
  --roots                 print where each hit's base pointer came from
  --certain               drop the possible ('?') hits
  --no-cache              do not read or write disasm/text.fx.pickle

How it works. It uses the data-flow pass of fieldxref.py (real control flow per Ghidra
function, no look-back window). A value loaded from memory is followed through moves, the
stack frame, shifts and masks until it is overwritten; every bit operation applied to it is
recorded with the mask translated back to bit numbers of the loaded bytes. A query then
keeps the operations whose load covers the asked bits: a word load at FIELDOFF, a byte or
halfword load inside the word (the mask is shifted accordingly), an 8-byte or unaligned load
that covers it, or a load through a pointer formed as object + K.

Output: one line per function, hits as ADDRESS:KIND[:MASK]. MASK is printed when the
instruction's mask is not exactly MASKHEX (a combined test, a multi-bit clear).
  test          and / andi with a mask that keeps the bit (mask in a register included)
  test(sign)    the bit was moved to the sign position (or is it) and branched on / slt 0
  test(shift)   the word was shifted so that only bits including this one remain, and the
                result is branched on, compared, stored or passed to a call
  set / toggle  or / xor with a mask that has the bit
  clear         and with a mask that drops the bit and keeps most of the others
  ...(var)?     the mask is 1 << n, or the word is shifted by n, with n not a constant: the
                instruction touches a bit chosen at run time (possible for every bit)
  ...(reg)?     the other operand is a run-time value (an argument, a loaded mask). When it
                is the function's own argument, call sites that pass a constant containing
                the bit are listed as  ADDRESS:set>FUNCTION  etc.
  store / store=CONST / copy<+OFF   (with --stores) a store over the word of an unknown
                value, a constant, or a value loaded from another place
  ?             possible: see fieldxref.py (base kept across a call, reloaded from the frame
                of a function that takes a local's address, code outside every function)

What it still cannot see
 1. Which structure: as for fieldxref.py, a displacement does not name a type. Every
    structure with a word at FIELDOFF is searched; narrow with --class, --this, --func,
    --range and read the function.
 2. A flag value that reaches the test through memory other than the stack frame, through a
    call (a getter that returns the word, a helper that takes the word by value), or that is
    merged from two different loads at a join.
 3. Masks that are neither constants in the function nor an argument passed as a constant
    one call up: masks read from a table, computed, or passed through two calls. They are
    listed as (reg)? at the instruction that applies them, for every bit.
 4. Accessors that take the bit number: listed as (var)? for every bit; which bit a caller
    passes is the reader's job.
 5. Tests of the whole word against zero or another value (no mask involved), and arithmetic
    on the word, are not listed.
 6. Block copies and fills of the object (clone, save, load): see fieldxref.py --blocks.
 7. The limits of the pass itself (fieldxref.py, "cannot see" 2, 5 and 7)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fieldxref as fx

VAR_KIND = {'and.varbit': 'test(var)', 'and.varclear': 'clear(var)', 'or.varbit': 'set(var)',
            'xor.varbit': 'toggle(var)', 'or.varclear': 'set(var)', 'xor.varclear': 'toggle(var)',
            'and.varshift': 'test(varshift)', 'or.varshift': 'set(varshift)',
            'xor.varshift': 'toggle(varshift)',
            'and.reg': 'test(reg)', 'or.reg': 'set(reg)', 'xor.reg': 'toggle(reg)',
            'nor.reg': 'test(reg)'}


def _index(db):
    idx = db.get('_acc_by_addr')
    if idx is None:
        idx = db['_acc_by_addr'] = {e[0]: e for e in db['acc']}
    return idx


def _positions(e, off, static):
    """Byte offsets, relative to the flag word, at which this access may start.
    Yields (offset - FIELDOFF, how, certain)."""
    a, fn, op, disp, root, delta, stp, ix, weak, sv = e[:10]
    s, w = fx.access_span(op, disp)
    yield s - off, 'raw', True
    if root[0] != 'A' and root != 'E$sp' and delta and not stp:
        yield delta + s - off, 'derived', not weak
    if root[0] == 'A' and static:
        base = static[0]; stride = static[1] if len(static) > 1 else 0
        count = static[2] if len(static) > 2 else 1
        ab = (delta + s) & 0xffffffff
        if base <= ab < base + (stride * count if stride else off + 16):
            yield ((ab - base) % stride if stride else ab - base) - off, 'abs', not weak and not ix


def _tr(m, shift):
    return (m << shift) if shift >= 0 else (m >> -shift)


def query_flag(db, mask, off=0xc, funcs=None, addr_range=None, static=None, stores=False,
               this=False, certain=False):
    """Returns (hits, number of whole-word stores not listed). A hit is a dict with addr,
    func, kind, mask (in bits of the word at off, or None), certain, root."""
    idx = _index(db); orph = db['orphans']
    hits = []; seen = set(); argmask = []

    def ok(a, fn):
        if addr_range and not (addr_range[0] <= a < addr_range[1]): return False
        return funcs is None or fn in funcs

    flg = []
    for ev in db['flg']:                 # one entry per load a value may have come from
        if ev[3].__class__ is tuple: flg.extend(ev[:3] + (d,) + ev[4:] for d in ev[3])
        else: flg.append(ev)
    for (a, fn, kind, da, m, aux, weak) in flg:
        if not ok(a, fn): continue
        la = idx.get(da)
        if la is None: continue
        if this and la[4] != 'E$4': continue
        w = fx.WIDTH[la[2]]
        for rel, how, sure in _positions(la, off, static):
            if not -16 < rel < 16: continue
            sh = 8 * rel
            if not _tr((1 << (8 * w)) - 1, sh) & mask: continue
            k = None; shown = None
            if m is None:
                k = VAR_KIND.get(kind); sure = False
                if kind.endswith('.reg') and aux.startswith('E$') and aux[1:] in fx.ARGNAME:
                    argmask.append((fn, aux[1:], kind.split('.')[0], a))
                    k = k.replace('reg', fx.ARGNAME[aux[1:]])
            elif kind == 'and':
                keep = _tr(m, sh); before = _tr(aux, sh); gone = before & ~keep
                nk = bin(keep).count('1'); ng = bin(gone).count('1')
                clearing = ng and nk >= 3 * ng
                if keep & mask:
                    if not clearing: k = 'test'; shown = keep
                elif (gone & mask) and clearing: k = 'clear'; shown = gone
            elif kind == 'or':
                if _tr(m, sh) & mask: k = 'set'; shown = _tr(m, sh)
            elif kind == 'xor':
                if _tr(m, sh) & mask: k = 'toggle'; shown = _tr(m, sh)
            elif kind == 'sign':
                if _tr(m, sh) & mask: k = 'test(sign)'; shown = _tr(m, sh)
            elif kind == 'zero':
                if _tr(m, sh) & mask: k = 'test(shift)'; shown = _tr(m, sh)
            if k is None: continue
            sure = sure and not weak and fn not in orph
            if (a, k) in seen: continue
            seen.add((a, k))
            if certain and not sure: continue
            hits.append(dict(addr=a, func=fn, kind=k, mask=shown, certain=sure, root=la[4],
                             load=da, how=how))
            break
    # a mask that is the function's own argument: look one call up for constant masks
    if argmask:
        want = {}
        for fn, reg, op, a in argmask: want.setdefault(fn, []).append((reg, op, a))
        for (a, fn, tgt, consts) in db.get('cargs', ()):
            if tgt not in want or not ok(a, fn): continue
            for reg, op, site in want[tgt]:
                for r, c in consts:
                    if r != reg: continue
                    c &= fx.MASK64
                    if op == 'and':
                        if c & mask: k = 'test'
                        elif bin(c & 0xffffffff).count('1') >= 24: k = 'clear'
                        else: continue
                    elif c & mask: k = 'set' if op == 'or' else 'toggle'
                    else: continue
                    if (a, k, tgt) in seen: continue
                    seen.add((a, k, tgt))
                    hits.append(dict(addr=a, func=fn, kind=k, mask=c if c != mask else None,
                                     certain=False, root='', load=None, how='call', via=tgt))
    hidden = 0
    for e in db['acc']:
        a, fn, op, disp, root, delta, stp, ix, weak, sv = e[:10]
        if op not in fx.STORE_W or not ok(a, fn): continue
        if this and root != 'E$4': continue
        w = fx.WIDTH[op]
        for rel, how, sure in _positions(e, off, static):
            if not -16 < rel < 16: continue
            sh = 8 * rel
            if not _tr((1 << (8 * w)) - 1, sh) & mask: continue
            if sv is None: k = 'store'; sure = False
            elif sv[0] == 'C':
                k = 'store=%x' % (_tr(sv[1] & ((1 << (8 * w)) - 1), sh)); sure = sure
            else:
                s, _ = fx.access_span(op, disp)
                k = None
                for d in (sv[1] if sv[1].__class__ is tuple else (sv[1],)):
                    la = idx.get(d)
                    if la is None: k = 'store'; continue
                    ls, lw = fx.access_span(la[2], la[3])
                    if not (la[4] == root and la[5] + ls == delta + s and sv[2] == 0
                            and root[0] not in 'JU'):
                        k = 'copy<%s' % fx._sx(la[5] + ls)
                if k is None: break                # the same word written back
            if stores:
                sure = sure and not weak and fn not in orph
                if not (certain and not sure):
                    hits.append(dict(addr=a, func=fn, kind=k, mask=None, certain=sure, root=root,
                                     load=None, how=how))
            else:
                hidden += 1
            break
    hits.sort(key=lambda h: h['addr'])
    return hits, hidden


def hit_text(h, mask, db=None, names=None, roots=False):
    s = '%x:%s' % (h['addr'], h['kind'])
    if h['mask'] is not None and h['mask'] != mask: s += ':%x' % h['mask']
    if h.get('via') is not None: s += '>' + ((names or {}).get(h['via']) or '%x' % h['via'])
    if h['how'] == 'derived': s += '{d}'
    if roots and h['root']: s += '/' + fx.root_label(h['root'], db, names)
    if not h['certain']: s += '?'
    return s


def format_hits(hits, mask, db, names, roots=False, width=24):
    by = {}
    for h in hits: by.setdefault(h['func'], []).append(h)
    out = []
    for f in sorted(by):
        nm = names.get(f, '')
        if f in db['orphans']: nm = nm or '(outside any function)'
        out.append('%s %-*s %s' % (hex(f), width, nm,
                                   ' '.join(hit_text(h, mask, db, names, roots) for h in by[f])))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pos, opts = fx.parse_common(argv)
    if len(pos) < 2 or '--help' in opts:
        print(__doc__); return 2
    from ps2elf import Elf
    import symtab
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    elf = Elf(pos[0])
    mask = int(pos[1], 16)
    off = int(pos[2], 16) if len(pos) > 2 else 0xc
    names = symtab.load(root)
    db = fx.load_db(root, elf, use_cache='--no-cache' not in opts)
    funcs, rng = fx.resolve_filters(opts, elf, names)
    hits, hidden = query_flag(
        db, mask, off, funcs=funcs, addr_range=rng,
        static=[int(x, 16) for x in opts['--static'].split(',')] if '--static' in opts else None,
        stores='--stores' in opts, this='--this' in opts, certain='--certain' in opts)
    for l in format_hits(hits, mask, db, names, roots='--roots' in opts): print(l)
    if hidden:
        print('# %d whole-word stores over +0x%x not listed (--stores; narrow with --class, '
              '--func or --range)' % (hidden, off), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
