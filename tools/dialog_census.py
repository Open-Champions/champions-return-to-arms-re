#!/usr/bin/env python3
"""Count NPC dialog files, nodes, choices and the script built-ins they reach. Counts only.

  python3 tools/dialog_census.py --disc DIR [--json]

DIR is any directory holding the disc's .GOB archives (searched recursively).  Nothing
is written.  No level name, entry-point name, text key or voice name is printed: only
totals, histograms and the names of script built-ins (which the game exports).

What is counted (docs/dialog.md section 9):
  * every `*.dbin` entry of every `.lmp`, split into NPC conversations (no `<name>.cut`
    beside it), cutscene line lists (a `<name>.cut` in the same lump) and NPC files that
    no `startDialog` call of the level script names;
  * nodes, choices, conditions, actions and jumps, with the graph reach from the start
    candidates `dialog_onMsg` case 0 can pick (node 0 and every node with a condition);
  * condition and action names that the level script does not export (script_runByName
    then returns -1, which a condition treats as true);
  * the built-ins those entries reach through `call` and `callScript`, and separately
    through `addDeferedCall` / `postAction` (those run after the choice);
  * the `startDialog` calls and their two integer arguments;
  * objects in `objects.ob` with the `dialogScript`, `shop`, `showName`, `talkCone` and
    `dialogOffset` properties, and what each `dialogScript` entry reaches (a dialog start,
    a forced mutex release, neither);
  * NPC voice names found as `<voice>.vag` / `<voice>.anm` in the level's stream
    directory (`ntsc_dialog.bin`).
"""
import argparse
import collections
import json
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
from gob import gob_entries, lmp_entries   # noqa: E402
from anim_audio_info import StreamDir      # noqa: E402
import ref_dialog as R                     # noqa: E402

BASE = 0x60
OP_PUSH_C = 0x27
OP_SYSREQ_C = 0x7B
OP_LINE = 0x7D
OP_CALL = 0x31
OP_RETURN = 0x30
STRING_ARG = {'callScript', 'addDeferedCall', 'postAction', 'startDialog', 'newWorldPost'}
FOLLOW_NOW = {'callScript'}
FOLLOW_LATER = {'addDeferedCall', 'postAction'}
OBJECT_KEYS = ('dialogscript', 'shop', 'showname', 'talkcone', 'dialogoffset')
ZERO_KEYS = ('npc_condition_names_unresolved', 'npc_action_names_unresolved', 'dialogscript_unresolved',
             'npc_actions_reaching_activateMissionMenu', 'dbin_refused', 'objects_refused',
             'startDialog_name_not_literal', 'npc_voices_missing_vag')

# Operand counts of the script machine (tools/scr.py OPS and NO_OPERAND).
_NO_OPERAND = {0x09, 0x17, 0x19, 0x1b, 0x21, 0x22, 0x23, 0x24, 0x25, 0x2a, 0x2b, 0x2e, 0x2f,
               0x30, 0x32, *range(0x41, 0x44), *range(0x48, 0x57), 0x59, 0x5a,
               *range(0x5d, 0x69), 0x6b, 0x6c, 0x6f, 0x70, 0x71, 0x74, 0x7a, 0x80}


class Script:
    """The parts of a level script.scr the census needs: entries, imports, strings and the
    call sites of each function body.  Layout as tools/scr.py (header at +0x60)."""

    def __init__(self, data):
        code_off, str_off, end_off = struct.unpack_from('<III', data, BASE + 0x0C)
        n_int, int_off, n_ext, ext_off = struct.unpack_from('<IIII', data, BASE + 0x20)
        self.entries = {}
        for i in range(n_int):
            o = BASE + int_off + i * 24
            value, = struct.unpack_from('<I', data, o)
            self.entries[data[o + 4:o + 24].split(b'\0')[0].decode('latin1')] = value
        self.imports = []
        for i in range(n_ext):
            o = BASE + ext_off + i * 24
            self.imports.append(data[o + 4:o + 24].split(b'\0')[0].decode('latin1'))
        raw = bytearray()
        start, end = BASE + str_off, min(BASE + end_off, len(data))
        for i in range(start, end - 3, 4):
            raw += data[i:i + 4][::-1]
        self.pool = raw
        cs, ce = BASE + code_off, BASE + str_off
        self.words = struct.unpack_from('<%dI' % ((ce - cs) // 4), data, cs)
        self.calls = []              # (offset, builtin, [args])
        self.internal = []           # (offset, target)
        self._scan()
        starts = set(self.entries.values()) | {t for _, t in self.internal}
        self.starts = sorted(starts)

    def string(self, offset):
        if not 0 <= offset < len(self.pool):
            return None
        end = self.pool.find(b'\0', offset)
        if end < 0:
            return None
        return self.pool[offset:end].decode('latin1')

    def _scan(self):
        words, i, pending = self.words, 0, []
        while i < len(words):
            op = words[i]
            if op == OP_LINE:
                i += 3
                continue
            if op == OP_SYSREQ_C:
                n = words[i + 1]
                name = self.imports[n] if n < len(self.imports) else '?'
                self.calls.append((i * 4, name, pending[:-1][::-1]))
                pending = []
                i += 2
                continue
            if op == OP_PUSH_C:
                pending.append(words[i + 1])
                i += 2
                continue
            if op == 0x2C:
                pending = []
                i += 2
                continue
            if op == OP_CALL:
                self.internal.append((i * 4, words[i + 1]))
            pending = [] if op not in (0x28,) else pending + [None]
            i += 1 + (0 if op in _NO_OPERAND else 1)

    def body(self, start):
        """[start, next function start) in code bytes."""
        later = [s for s in self.starts if s > start]
        return start, (later[0] if later else len(self.words) * 4)

    def reach(self, name):
        """Built-ins reached from entry `name`: (now, later).  `now` follows internal calls
        and callScript of a literal name; `later` is what addDeferedCall / postAction of a
        literal name reach.  Unresolved names reach nothing."""
        now, later = collections.Counter(), collections.Counter()
        seen = set()

        def walk(start, into):
            if start in seen:
                return
            seen.add(start)
            lo, hi = self.body(start)
            for off, builtin, args in self.calls:
                if lo <= off < hi:
                    into[builtin] += 1
                    if builtin in FOLLOW_NOW | FOLLOW_LATER and args and args[0] is not None:
                        target = self.string(args[0])
                        if target in self.entries:
                            walk(self.entries[target], into if builtin in FOLLOW_NOW else later)
            for off, target in self.internal:
                if lo <= off < hi:
                    walk(target, into)

        if name in self.entries:
            walk(self.entries[name], now)
        return now, later


def object_props(blob):
    """objects.ob (docs/objects.md, level records): yield (className, {key: value})."""
    count, _flags, strings = struct.unpack_from('<hHi', blob, 0)

    def text(off):
        p = strings + off
        return blob[p:blob.index(b'\0', p)].decode('latin1')

    p = 8
    for _ in range(count):
        cls, size, _angle = struct.unpack_from('<ihh', blob, p)
        q, props = p + 20, {}
        while True:
            v, = struct.unpack_from('<i', blob, q)
            q += 4
            if v == 0:
                break
            key, _, value = text(v).partition('=')
            props.setdefault(key.lower(), value)
        yield text(cls), props
        if size <= 0:
            raise ValueError('record size %d' % size)
        p += size


def census(root):
    c = collections.Counter({k: 0 for k in ZERO_KEYS})
    hist_nodes, hist_choices = collections.Counter(), collections.Counter()
    action_now, action_later = collections.Counter(), collections.Counter()
    cond_now = collections.Counter()
    start_args = collections.Counter()
    obj_classes = collections.Counter()
    gobs = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.upper().endswith('.GOB'):
                gobs.append(os.path.join(dirpath, f))
    for path in sorted(gobs):
        c['gob'] += 1
        data = open(path, 'rb').read()
        for lname, loff, lsize in gob_entries(data):
            if not lname.lower().endswith('.lmp'):
                continue
            lump = data[loff:loff + lsize]
            try:
                ents = lmp_entries(lump)
            except (ValueError, IndexError, struct.error):
                c['lmp_refused'] += 1
                continue
            names = {e[0].lower(): (e[1], e[2]) for e in ents}
            script = None
            if 'script.scr' in names:
                o, s = names['script.scr']
                script = Script(lump[o:o + s])
                c['level_scripts'] += 1
            started = set()
            if script is not None:
                for _off, builtin, args in script.calls:
                    if builtin != 'startDialog':
                        continue
                    c['startDialog_calls'] += 1
                    name = script.string(args[0]) if args and args[0] is not None else None
                    if name is None:
                        c['startDialog_name_not_literal'] += 1
                    else:
                        started.add(name.lower())
                        if name.lower() + '.dbin' in names:
                            c['startDialog_names_a_dbin_here'] += 1
                    ints = tuple(args[1:3]) if len(args) >= 3 else None
                    start_args[ints] += 1
            if 'objects.ob' in names:
                o, s = names['objects.ob']
                try:
                    for cls, props in object_props(lump[o:o + s]):
                        c['objects'] += 1
                        for key in OBJECT_KEYS:
                            if key in props:
                                c['objects_with_' + key] += 1
                        if 'showname' in props and 'dialogscript' not in props:
                            c['objects_showname_without_dialogscript'] += 1
                            if 'shop' not in props:
                                c['objects_showname_without_dialogscript_or_shop'] += 1
                        if 'dialogscript' in props:
                            obj_classes[cls] += 1
                            if script is not None and props['dialogscript'] in script.entries:
                                c['dialogscript_resolves'] += 1
                                now, later = script.reach(props['dialogscript'])
                                if now['startDialog']:
                                    c['dialogscript_reaches_startDialog'] += 1
                                if now['forceMutexRelease']:
                                    c['dialogscript_reaches_forceMutexRelease'] += 1
                                if not now['startDialog'] and not now['forceMutexRelease']:
                                    c['dialogscript_reaches_neither'] += 1
                                if now['activateStore']:
                                    c['dialogscript_reaches_activateStore'] += 1
                            else:
                                c['dialogscript_unresolved'] += 1
                except (ValueError, IndexError, struct.error):
                    c['objects_refused'] += 1
            stream = None
            for dname in ('ntsc_dialog.bin', 'dialog.bin'):
                if dname in names:
                    o, s = names[dname]
                    try:
                        stream = {e['name'].lower() for e in StreamDir(lump[o:o + s]).entries}
                    except Exception:            # a directory the parser refuses
                        c['stream_dir_refused'] += 1
                    break
            if script is not None:
                for _off, builtin, _args in script.calls:
                    if builtin == 'activateMissionMenu':
                        c['activateMissionMenu_sites'] += 1
            for ename, (o, s) in sorted(names.items()):
                if not ename.endswith('.dbin'):
                    continue
                base = ename[:-5]
                try:
                    nodes = R.parse_dbin(lump[o:o + s])
                except ValueError:
                    c['dbin_refused'] += 1
                    continue
                c['dbin_files'] += 1
                c['dbin_bytes'] += s
                c['dbin_nodes'] += len(nodes)
                if base + '.cut' in names:
                    c['dbin_cutscene_files'] += 1
                    c['dbin_cutscene_nodes'] += len(nodes)
                    continue
                c['dbin_npc_files'] += 1
                c['dbin_npc_nodes'] += len(nodes)
                if base not in started:
                    c['dbin_npc_files_not_started_here'] += 1
                hist_nodes[len(nodes)] += 1
                reach = R.reachable_nodes(nodes)
                c['npc_nodes_unreachable'] += len(nodes) - len(reach)
                cond_names, act_names = set(), set()
                for node in nodes:
                    hist_choices[len(node.choices)] += 1
                    voice = node.voice.lower()
                    if stream is None:
                        c['npc_voices_no_stream_dir'] += 1
                    elif voice + '.vag' not in stream:
                        c['npc_voices_missing_vag'] += 1
                    else:
                        c['npc_voices_with_vag'] += 1
                        if voice + '.anm' in stream:
                            c['npc_voices_with_lipsync_anm'] += 1
                    if node.condition:
                        c['npc_nodes_with_condition'] += 1
                        cond_names.add(node.condition)
                    if node.speaker:
                        c['npc_nodes_with_speaker'] += 1
                    if not node.choices:
                        c['npc_nodes_without_choices'] += 1
                    for ch in node.choices:
                        c['npc_choices'] += 1
                        if ch.condition:
                            c['npc_choices_with_condition'] += 1
                            cond_names.add(ch.condition)
                        if ch.action:
                            c['npc_choices_with_action'] += 1
                            act_names.add(ch.action)
                        if ch.next == -1:
                            c['npc_choices_end'] += 1
                        else:
                            c['npc_choices_jump'] += 1
                        if ch.action and ch.next != -1:
                            c['npc_choices_action_and_jump'] += 1
                for nm in cond_names:
                    c['npc_condition_names'] += 1
                    if script is None or nm not in script.entries:
                        c['npc_condition_names_unresolved'] += 1
                        if script is not None and nm.lower() in {k.lower() for k in script.entries}:
                            c['npc_condition_names_case_only'] += 1
                        continue
                    now, _later = script.reach(nm)
                    for b in now:
                        cond_now[b] += 1
                for nm in act_names:
                    c['npc_action_names'] += 1
                    if script is None or nm not in script.entries:
                        c['npc_action_names_unresolved'] += 1
                        continue
                    now, later = script.reach(nm)
                    if now['activateMissionMenu'] or later['activateMissionMenu']:
                        c['npc_actions_reaching_activateMissionMenu'] += 1
                    for b in now:
                        action_now[b] += 1
                    for b in later:
                        action_later[b] += 1
    return dict(totals=dict(sorted(c.items())),
                npc_nodes_per_file=dict(sorted(hist_nodes.items())),
                npc_choices_per_node=dict(sorted(hist_choices.items())),
                startDialog_int_args={str(k): v for k, v in sorted(start_args.items(), key=str)},
                dialogscript_object_classes=dict(sorted(obj_classes.items())),
                condition_entries_reach=dict(sorted(cond_now.items())),
                action_entries_reach=dict(sorted(action_now.items())),
                action_entries_reach_later=dict(sorted(action_later.items())))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--disc', required=True, help='directory with the .GOB archives')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    if not os.path.isdir(a.disc):
        print('dialog_census: %s is not a directory' % a.disc)
        return 2
    out = census(a.disc)
    if a.json:
        print(json.dumps(out, indent=1, sort_keys=True))
        return 0
    for section, values in out.items():
        print('%s:' % section)
        for k, v in values.items():
            print('  %-40s %s' % (k, v))
    return 0


if __name__ == '__main__':
    sys.exit(main())
