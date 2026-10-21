# Arena index 0: Scorpion

US `SLUS_209.73` v2.00. The arena table entry `0x5037f0` is the plain
`scorpion` type. Its complete reference contract is already in
`docs/spec/monsters-1.md` §6 and `tools/ref_monsters_1.py`, so no second
model was authored for this round. That contract gives its fields, calls,
draws, clip constants, addressed constructor `0x2a4d68`, run
`0x2a5068`, set-state `0x2a55ec`, class definition `0x502238`, and
virtual table `0x50fe88`. Slot 2 uses the independently modelled
`Creature_takeDamage` `0x116638`; death state 0x14 is included in the
Scorpion set-state/run model. Its slot-1 destructor is `0x3c46a8`
(Observed, not executed by the new arena probe).

**Executed** again on 2026-10-21 with
`tools/difftest_monsters_1.py local/SLUS_209.73 --seed 20973 -k scorpion`
and `--seed 7 -k scorpion`: 3,888 and 3,868 comparisons respectively,
zero mismatches. The original constructor reached 178/178 instructions;
run 346/353, set-state 257/257, sever-part 64/65. The run branches not
entered in that suite include the documented dead search for a second
descriptor slot. The tests exercise deaths in many states and compare
callouts, stored bytes, seed and result. This is function-level execution
in `tools/ee_emu.py`, not a live arena match.
