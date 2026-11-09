#!/bin/sh
# Final arrival runs for round 9: r9, r8, r7, r6, r5 and the unit tests, one process at a
# time. Run from anywhere inside the worktree, after the last commit. Inputs are the
# untracked local/SLUS_209.73 and local/arrival-route-r4.json. Each log is written under
# local/ and is headed by the commit, the sha256 of this script, tools/ee_emu.py and the
# test file, and the UTC start time. It ends with the exit status and the finish time.
set -u
cd "$(dirname "$0")/.." || exit 1
H=$(git rev-parse HEAD)
sum() { echo "sha256 $(shasum -a 256 "$1" | cut -c1-64) $1"; }
head_lines() {
  echo "commit $H"
  sum tools/run_arrival_stage_r9.sh
  sum tools/ee_emu.py
  for f in "$@"; do case $f in tools/*.py) sum "$f";; esac; done
  echo "started $(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
run() {
  log=$1; shift
  head_lines "$@" > "$log"
  PYTHONDONTWRITEBYTECODE=1 python3 -u "$@" >> "$log" 2>&1
  echo "exit $? finished $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$log"
}
IN="local/SLUS_209.73 local/arrival-route-r4.json"
run local/arrival-stage-r9.log tools/difftest_arrival_stage_r9.py $IN
run local/arrival-stage-r8-r9.log tools/difftest_arrival_stage_r8.py $IN
run local/arrival-stage-r7-r9.log tools/difftest_arrival_stage_r7.py $IN
run local/arrival-stage-r6-r9.log tools/difftest_arrival_stage_r6.py $IN
run local/arrival-stage-r5-r9.log tools/difftest_arrival_stage_r5.py $IN
head_lines > local/unittest-r9.log
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p "test_*.py" >> local/unittest-r9.log 2>&1
echo "exit $? finished $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> local/unittest-r9.log
