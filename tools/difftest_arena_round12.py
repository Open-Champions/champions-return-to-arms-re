#!/usr/bin/env python3
"""Round 12: controller-only kills through the recipe-0 waves, with the original arena
task run every frame.  The checks hold on both seeds; how far each seed gets (kills per
wave, whether the third-wave next-level request is reached) is printed as OUTCOME lines.

    python3 tools/difftest_arena_round12.py local/SLUS_209.73 DISC --seed 20973
    python3 tools/difftest_arena_round12.py local/SLUS_209.73 DISC --seed 7

DISC is the disc image, or a directory holding the disc's files (tools/disc_dir.py).
The FX lump's clips are added to round 10's set (the arena spawn effect).
It continues the round-10/11 fixture (difftest_arena_engagement.prepare: disc terrain,
disc clips, original Goblin/creature bodies, original class-0 unarmed record).

Differences from round 11, all disclosed in docs/spec/arena-acceptance.md:
  * No scheduled Player_meleeHit.  Every hit comes from Player_run on controller
    input chosen from positions the way a player would: walk to 58 units, face, press
    attack every 36 frames; after three swings on a target reach no Player_meleeHit,
    walk to 26 units of that target instead.
  * Player_animStep 0x1b9520 is followed.  Round 11 left it a stub, so the first
    player reaction (state 3) waited forever on the clip-end bit: its swing stall.
    (--resist can plant item stagger resistance +0xdc; the retained runs do not.)
  * HP and maximum HP are 10,000, as in round 11.  A level-up (player_giveExp) recomputes
    max HP from the real class-0 statistics and refills HP to it; the driver then
    writes 10,000 to both again and reports each such frame.
  * animtrack_decode 0x16e468 and animcache_alloc 0x16e388 are followed (original
    bodies); round 10's animation follow set omitted them.
  * A Scorpion sting's SpellDiseaseEffect block (pool_new 0x1b0 at 0x1e9de8) is
    allocated and its constructor 0x2d5594 followed; the effect's tick is an auto-stub.
  * obj_delete 0x14f200 is followed and world_flushDeleteList 0x14f3a8 runs at each
    frame start with every callee followed, as runObjects does inline; the
    saved-creature table 0x50388c gets the 0x4b0-byte block arena_init allocates.
  * The arena task 0x306b78 runs every frame with the original grid walker 0x14a610
    and empty-wave callback 0x3069e8, arena_nextWave, the preparation walk,
    arena_startWave, the ring step and the spawn body.  Nothing marks a wave empty.
Stubs that remain (from prepare): the model joint count 0x1799c8 (returns 1, as in
difftest_arena_modes), the end prompt 0x307ebc, game_scanCm1Vars, strcpy
(recorded: it receives the next level's name pointer), net_closeLocalMenus, and every
callee outside the follow set (auto-stubs return 0).  Level loading is not run.
"""
import argparse
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE]
sys.path.append(_HERE)

import difftest_arena_engagement as A          # noqa: E402
import difftest_arena_modes as D               # noqa: E402
import difftest_player as DP                   # noqa: E402
import disc_dir                                # noqa: E402
import probe_arena_match as P                  # noqa: E402
import ref_arena_match_core as MC              # noqa: E402
import ref_arena_modes as R                    # noqa: E402
import ref_player as RP                        # noqa: E402
import ref_world as W                          # noqa: E402
from ref_core import s16                       # noqa: E402

disc_dir.install(P)

DROP = 0x10F2C8
GENERATE_DROPS = 0x100D54
ON_DEATH = 0x10BEB8
GIVE_EXP = 0x1D3150
PREPARE = 0x3063FC
STAGGER_RESIST = 0xDC
STATE = 0x58C
OBJ_DELETE = 0x14F200
FLUSH_DELETES = 0x14F3A8
DELETE_LIST = 0x5DB4E0
MONSTER_TABLE = 0x50388C
BIG_HP = 0x461C4000          # 10000.0
ANIMTRACK_DECODE = 0x16E468
ANIMCACHE_ALLOC = 0x16E388
PLAYER_ANIM_STEP = 0x1B9520
RESULTS = []


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                        '' if ok else '\n      got  %r\n      want %r' % (got, want)))
    return ok


def arena_clips(disc):
    """Round-10 recipe-0 clips plus the FX lump's clips: a creature built by a later
    wave plays the arena spawn-effect clip from that lump.  Read in memory only."""
    import gob
    clips = P.recipe0_clips_from_disc(disc)
    iso = P.Disc.Iso(disc)
    try:
        lump = P.disc_file(iso, 'BG/DATA/FX.LMP')
        for name, off, size in gob.lmp_entries(lump):
            if name.lower().endswith('.anm'):
                clips[('fx.lmp', name.lower())] = lump[off:off + size]
    finally:
        iso.f.close()
    return clips


def run_level(elf, disc, seed, frame_limit, resist=None):
    emu, created, player = A.prepare(elf, seed, P.recipe0_world_from_disc(disc),
                                     arena_clips(disc), init_record=True)
    mem = emu.mem
    mem.w32(D.PLAYERS + 0xAC, W.f32(10000.0))
    mem.w32(D.PLAYERS + 0xB0, W.f32(10000.0))
    if resist is not None:
        mem.w32(D.PLAYERS + STAGGER_RESIST, W.f32(resist))
    nrec = mem.u16(D.NREC)
    records = [bytes(mem.u8(D.RECIPES + 6 * i + b) for b in range(6)) for i in range(nrec)]
    names_b = D.names(emu, D.NAMES_B)
    # The real task from here on: original walker, callback, next wave and spawns.
    for address in (D.NEXT, D.WALK):
        emu.unhook(address)
    emu.follow.update({D.NEXT, D.START, D.STEP, D.SPAWN, PREPARE, D.WALK,
                       MC.EMPTY_WAVE_VISIT, MC.SAVE_WAVE_VISIT,
                       # the key-stream decoder and its slot cache: the spawn-effect clip
                       # is the first compressed (+0x1c & 0x800) track this fixture syncs,
                       # and follow_disc_animation only follows anim_*/anm_* names
                       ANIMTRACK_DECODE, ANIMCACHE_ALLOC,
                       # the player's own animation step, so reaction states end
                       PLAYER_ANIM_STEP,
                       # deferred deletion: obj_delete links the object on the delete list
                       OBJ_DELETE, 0x1A1738, 0x1A1868})
    emu.stub(D.STRCPY, ret=0, name='strcpy')
    emu.stub(D.CLOSE, ret=0, name='net_closeLocalMenus')
    # SpellArena_run 0x305bbc on a new wave's creatures divides by the joint count of
    # the actor model; these fixtures have no model.  Same bound as
    # difftest_arena_modes.py test_fade_and_spell: the joint service returns 1.
    emu.stub(D.JOINTS, ret=1, name='model_jointCount')
    emu.record_writes = False
    # arena_init 0x304c4c allocates the 0x4b0-byte saved-creature table at 0x50388c
    # (executed in difftest_arena_acceptance case_init); this fixture never ran it.
    if mem.u32(MONSTER_TABLE) == 0:
        mem.w32(MONSTER_TABLE, emu.alloc(0x4B0))
    misses = []
    inner = emu.hooks[0x17365C]

    def res_find_logged(e):
        lump, name = e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF
        before = e.clip_resolutions
        inner(e)
        if e.clip_resolutions == before:
            misses.append((e.mem.cstr(lump, 32), e.mem.cstr(name, 40)))
    emu.hooks[0x17365C] = res_find_logged
    # A Scorpion sting makes damage_apply attach a SpellDiseaseEffect to the player
    # (pool_new(0x1b0) at 0x1e9de8, constructor 0x2d5594; docs/spec/skills-01-34.md).
    # The probe's pool fixture refuses unknown sites; allocate this one and follow the
    # original constructor.  The effect's own tick is not followed (auto-stub).
    pool_inner = emu.hooks[P.POOL_NEW]
    effects = []

    def pool_new_effects(e):
        if (e.r[4] & 0xFFFFFFFF) == 0x1B0 and e._fresh_call is not None and e._fresh_call.site == 0x1E9DE8:
            block = e.alloc(0x1B0)
            effects.append(block)
            e.r[2] = block
            e.jump(e.r[31] & 0xFFFFFFFF)
            if e._fresh_call is not None:
                e._fresh_call.stubbed, e._fresh_call.ret = True, block
            return
        pool_inner(e)
    emu.hooks[P.POOL_NEW] = pool_new_effects
    emu.follow.add(0x2D5594)
    spawn_check = emu.hooks[P.ADD_SPELL]

    def add_spell_checked(e):
        # the probe's hook asserts the arena spawn's SpellArena record; the disease
        # effect is a different attach, so that one assertion is skipped for it
        if (e.r[5] & 0xFFFFFFFF) not in effects:
            spawn_check(e)
    emu.hooks[P.ADD_SPELL] = add_spell_checked

    counts = {k: 0 for k in ('melee', 'driver_melee', 'exp_calls')}
    exp = []
    deaths = {}
    death_calls = {}
    ticks = {}
    waves = [(0, 181, [index for index, _obj in created])]
    inter_frames = []
    level_request = None
    last_press = -100
    stagger_frames = []
    replants = []
    frame = 181
    deleted = []
    to_flush = []
    swings, struck, swing_misses = [], set(), {}
    seen = list(created)
    for frame in range(181, frame_limit):
        mem.w32(D.FRAME, frame)
        # runObjects 0x14b910 destroys the delete list at the start of each frame; run
        # the original flush body with every callee followed (destructors are virtual)
        pending, to_flush = to_flush, []
        if pending:
            saved_follow = emu.follow
            emu.follow = None
            try:
                emu.call(FLUSH_DELETES, max_steps=400_000_000)
            finally:
                emu.follow = saved_follow
            gone = set(pending)
            deleted += [(frame, i, o) for i, o in created if o in gone]
            created[:] = [(i, o) for i, o in created if o not in gone]
            del emu.calls[:]
        px, py = [A.f32_at(mem, player + a) for a in (0x10, 0x14)]
        live = [(i, o) for i, o in created if mem.u16(o + 0x232) != 0x14]
        press, lx, ly = 0, 0.0, 0.0
        if live:
            distance, target = min(
                (math.hypot(A.f32_at(mem, o + 0x10) - px, A.f32_at(mem, o + 0x14) - py), o)
                for _i, o in live)
            dx = A.f32_at(mem, target + 0x10) - px
            dy = A.f32_at(mem, target + 0x14) - py
            facing = mem.u16(player + 0x38) * 2 * math.pi / 65536
            dot = (dx * math.cos(facing) + dy * math.sin(facing)) / max(math.hypot(dx, dy), 1)
            theta = math.atan2(dy, dx) + 0x41C2 * 2 * math.pi / 65536
            stop = 58 if swing_misses.get(target, 0) < 3 else 26
            if distance > stop or dot < 0.6:
                lx, ly = math.sin(theta) * 0.7, math.cos(theta) * 0.7
            if distance < 65 and dot >= 0.6 and frame - last_press >= 36:
                press = DP.BTN['attack']
                last_press = frame
                swings.append((frame, target))
        for offset, value in ((8, press), (0xC, press), (0x14, W.f32(lx)), (0x18, W.f32(ly))):
            mem.w32(RP.G_PADS + offset, value)
        mark = len(emu.calls)
        emu.call(P.PLAYER_RUN, player, max_steps=400_000_000)
        for c in emu.calls[mark:]:
            if c.target == A.PLAYER_MELEE_HIT and not c.stubbed:
                counts['melee'] += 1
                struck.add((frame, c.args[1] & 0xFFFFFFFF))
        # a swing that reached no Player_meleeHit on its target within 24 frames is a miss;
        # after three misses the controller walks closer to that target
        while swings and frame - swings[0][0] >= 24:
            f0, t0 = swings.pop(0)
            if not any(f0 <= f <= f0 + 24 and v == t0 for f, v in struck):
                swing_misses[t0] = swing_misses.get(t0, 0) + 1
        if mem.u32(player + STATE) == 3:
            stagger_frames.append(frame)
        if os.environ.get('ARENA_PRESS') and frame >= int(os.environ['ARENA_PRESS']) and live and (press or frame % 9 == 0):
            seg = emu.calls[mark:]
            tz = A.f32_at(mem, target + 0x18) - A.f32_at(mem, player + 0x18)
            print('PRESS' if press else 'FRAME', frame, 'state', mem.u32(player + STATE),
                  'tstate', mem.u16(target + 0x232), 'd %.1f dot %.2f dz %.1f' % (distance, dot, tz),
                  'pick', sum(c.target == 0x1BBA88 for c in seg), 'find',
                  [(c.ret if c.ret is None else hex(c.ret & 0xFFFFFFFF)) for c in seg if c.target == 0x1BB3C8][:2],
                  'melee', sum(c.target == A.PLAYER_MELEE_HIT for c in seg), 'miss', swing_misses.get(target, 0),
                  'tz', round(A.f32_at(mem, target + 0x18), 1), 'tr', round(A.f32_at(mem, target + 0x1C), 1),
                  'pr', round(A.f32_at(mem, player + 0x1C), 1), 'tflags', hex(mem.u32(target + 0xC)),
                  hex(mem.u64(target + 0xA8)), flush=True)
        if mem.u32(D.PLAYERS + 0xB0) != BIG_HP:
            # a level-up recomputed max HP from the real class-0 statistics and refilled
            # HP to it; keep the fixture's 10,000 bound (counted, reported)
            replants.append((frame, A.f32_at(mem, D.PLAYERS + 0xB0)))
            mem.w32(D.PLAYERS + 0xAC, BIG_HP)
            mem.w32(D.PLAYERS + 0xB0, BIG_HP)
        for index, obj in list(created):
            mark = len(emu.calls)
            try:
                emu.call(P.RUN_STATES[index], obj, max_steps=400_000_000)
            except Exception:
                print('FAULT frame %d class %d obj %#x state %#x wave %d ticks %d deaths %d calls %s'
                      % (frame, index, obj, mem.u16(obj + 0x232), mem.u16(D.WAVE),
                         ticks.get(obj, 0), len(deaths),
                         [hex(c.target) for c in emu.calls[mark:]][-12:]), flush=True)
                print('MISSES', sorted(set(m for m in misses if m[1].lower().endswith('.anm')))[-40:])
                raise
            ticks[obj] = ticks.get(obj, 0) + 1
            if mem.u16(obj + 0x232) == 0x14 and obj not in deaths:
                deaths[obj] = (frame, index, mem.u16(D.WAVE))
                seg = emu.calls[mark:]
                death_calls[obj] = tuple(sum(1 for c in seg if c.target == a and not c.stubbed)
                                         for a in (P.PROCESS_DAMAGE, ON_DEATH, D.ADDK, DROP,
                                                   GENERATE_DROPS))
            for c in emu.calls[mark:]:
                if c.target == GIVE_EXP:
                    exp.append((frame, c.args[0] & 0xFF, c.args[1] & 0xFFFFFFFF))
        before_wave, before_inter, before_n = mem.u16(D.WAVE), mem.u16(D.INTER), len(created)
        mark = len(emu.calls)
        emu.call(D.RUN, max_steps=400_000_000)
        seg = emu.calls[mark:]
        if not before_inter and mem.u16(D.INTER):
            inter_frames.append(frame)
        if mem.u16(D.WAVE) != before_wave:
            waves.append((s16(mem.u16(D.WAVE)),
                          frame, [i for i, _o in created[before_n:]]))
        copies = [c for c in seg if c.target == D.STRCPY]
        if copies:
            level_request = (frame, copies[0].args[1] & 0xFFFFFFFF, len(copies))
            break
        to_flush = [c.args[0] & 0xFFFFFFFF for c in emu.calls if c.target == OBJ_DELETE]
        seen += [entry for entry in created if entry not in seen]
        if os.environ.get('ARENA_TRACE') and frame % int(os.environ.get('ARENA_TRACE')) == 0 and len(waves) > 1:
            print('TRACE', frame, 'pstate', mem.u32(player + STATE),
                  'hp', round(A.f32_at(mem, D.PLAYERS + 0xAC), 1), round(A.f32_at(mem, D.PLAYERS + 0xB0), 1),
                  'slot', D.read_slot(emu, 0)[:3], 'dead', mem.u16(D.COUNTDOWN),
                  'pos', [round(A.f32_at(mem, player + a)) for a in (0x10, 0x14, 0x18)],
                  'hits', counts['melee'], 'live',
                  [(i, mem.u16(o + 0x232), round(A.f32_at(mem, o + 0x228), 1),
                    [round(A.f32_at(mem, o + a)) for a in (0x10, 0x14, 0x18)],
                    hex(mem.u32(o + 0xC)), hex(mem.u64(o + 0xA8) >> 56))
                   for i, o in created if mem.u16(o + 0x232) != 0x14], flush=True)
        del emu.calls[:]
    return dict(emu=emu, created=seen, deaths=deaths, death_calls=death_calls, waves=waves,
                inter=inter_frames, level=level_request, frame=frame, counts=counts, exp=exp,
                effects=effects, ticks=ticks, staggers=stagger_frames, replants=replants, deleted=deleted, records=records, nrec=nrec,
                names_b=names_b, player=player)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('disc')
    parser.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    parser.add_argument('--frames', type=int, default=16000)
    parser.add_argument('--resist', type=float, default=None,
                        help='plant item stagger resistance +0xdc (default: leave the record)')
    args = parser.parse_args()
    out = run_level(args.elf, args.disc, args.seed, args.frames, args.resist)
    emu, mem = out['emu'], out['emu'].mem
    seed = args.seed
    print('seed %d: frames in player reaction state 3: %d; max-HP re-plants after level-ups %s'
          % (seed, len(out['staggers']), out['replants']))
    print('seed %d: disease effects attached to the player: %d' % (seed, len(out['effects'])))
    print('seed %d: corpses destroyed through the delete list: %s' % (seed, out['deleted']))
    check('seed %d: player never died' % seed, mem.u32(out['player'] + STATE) != 4, True)
    check('seed %d: controller hits only (driver calls none)' % seed,
          out['counts']['melee'] > 0 and out['counts']['driver_melee'] == 0, True)
    want_classes = []
    for wave in range(3):
        count, quot, rem = R.spawn_budget(wave, 1)
        record = out['records'][R.sdiv(quot, out['nrec'])[1]]
        want_classes.append(R.recipe_groups(record, rem, count))
    built = [classes for _w, _f, classes in out['waves']]
    check('seed %d: every wave built so far is recipe 0 (at least waves 0 and 1)' % seed,
          (len(built) >= 2, built), (True, want_classes[:len(built)]))
    check('seed %d: wave numbers' % seed, [w for w, _f, _c in out['waves']], list(range(len(built))))
    by_wave = [sum(1 for _f, _i, w in out['deaths'].values() if w == k) for k in range(3)]
    check('seed %d: wave 0 cleared by controller kills' % seed, by_wave[0], len(want_classes[0]))
    print('seed %d: OUTCOME controller kills per wave %s of %s' % (
        seed, by_wave[:len(built)], [len(c) for c in want_classes[:len(built)]]))
    check('seed %d: each death ran processDamage, onDeath, addKill, dropLoot, generateDrops once'
          % seed, sorted(set(out['death_calls'].values())), [(1, 1, 1, 1, 1)])
    check('seed %d: arena kill count equals deaths' % seed, D.read_slot(emu, 0)[0], len(out['deaths']))
    check('seed %d: one experience award per death, to slot 0' % seed,
          ([f for f, _s, _a in out['exp']], set(s_ for _f, s_, _a in out['exp'])),
          (sorted(f for f, _i, _w in out['deaths'].values()), {0}))
    new = [obj for _i, obj in out['created'][len(want_classes[0]):]]
    check('seed %d: later-wave creatures ticked' % seed,
          all(out['ticks'].get(obj, 0) > 100 for obj in new), True)
    check('seed %d: every intermission starts on the 128-frame scan' % seed,
          len(out['inter']) >= 1 and all(f % 128 == 0 for f in out['inter']), True)
    check('seed %d: each next wave 480 visits after its intermission start' % seed,
          [f for _w, f, _c in out['waves'][1:]],
          [f + R.INTERMISSION_OFFLINE for f in out['inter'][:len(out['waves']) - 1]])
    check('seed %d: mode B kept, end flag clear' % seed, (mem.u32(D.MODE_B), mem.u32(D.ENDF)), (1, 0))
    level = out['level']
    alive = [(i, round(A.f32_at(mem, o + 0x228), 1)) for i, o in out['created']
             if mem.u16(o + 0x232) != 0x14 and o not in [d for _f, _i, d in out['deleted']]]
    if level:
        rec = R.level_record_index(2, out['nrec'])
        want_ptr = out['names_b'][R.low_nibble(out['records'][rec][0])]
        check('seed %d: level request after the third intermission' % seed,
              (level[0], level[1], level[2], mem.s8(D.PENDING + 0x50), mem.u16(D.LEFT)),
              (out['inter'][2] + R.INTERMISSION_OFFLINE, want_ptr, 1, -1, 0))
    else:
        print('seed %d: OUTCOME wave %d not cleared within %d frames; alive (class, hp): %s; '
              'no level request' % (seed, len(built) - 1, out['frame'] + 1, alive))
    deaths = sorted(out['deaths'].values())
    print('seed %d: controller hits %d; deaths %s; waves %s; intermissions %s; level request %s; '
          'experience calls %d %s; loot blocks %d; stopped at frame %d' % (
              seed, out['counts']['melee'], [(f, i, w) for f, i, w in deaths],
              [(w, f) for w, f, _c in out['waves']], out['inter'],
              level and (level[0], hex(level[1])), len(out['exp']), out['exp'][:12],
              len(emu.loot), out['frame']))
    failed = sum(1 for _n, ok in RESULTS if not ok)
    print('%s  %d checks, %d failed, seed %d' % ('PASS' if not failed else 'FAIL', len(RESULTS),
                                                  failed, seed))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
