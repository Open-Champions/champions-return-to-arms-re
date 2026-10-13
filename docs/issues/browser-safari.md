# Browser build in Safari's engine: the stall on arriving in a level — working notes

Status: **in progress** (started 2026-10-13 08:00). This file is kept current while the
work goes on; the summary is filled in when there are figures. If the work was cut off,
the last section ("Log") says where.

Question: the page plays at 60 frames a second in Chrome and in Safari's engine, but in
Safari's engine arriving in a level gives up to five seconds without a frame
(`docs/issues/browser-build.md`, "What Safari's engine does differently"). Where does that
time go, and what removes it without changing what the emulated machine computes?

## Summary

(not yet)

## Where things are

| What | Where |
|---|---|
| the change, as a patch for the next release (applied after `play-net.patch`, `play-web.patch`, `perf.patch`) | `tools/play-web/safari.patch` (not written yet) |
| an untouched Play! tree at the commit `build.sh` names (copied from `local/rel.nosync/play-pristine`) | `local/play-web-safari/pristine` |
| the tree as `tools/play-web/build.sh` builds it today (made by running that script with `RTA_PLAY_SOURCE`, `RTA_WEB_SOURCE`, `RTA_WEB_BUILD`, `RTA_WEB_SITE` pointing here), and its build | `local/play-web-safari/base-src`, `base-build` |
| harness, helpers, results | `local/play-web-safari/out` |

Nothing of the released page is touched: not `tools/play-web/build.sh`, `play-web.patch`,
`perf.patch`, `src/`, `web/`, not `local/play-web-src`, `-build*`, `-site`.

## Log

1. 2026-10-12 22:45: started, stopped a minute later by the coordinator (the usage window
   was kept for the release). Nothing had been built.
2. 2026-10-13 08:00: started again on the released tree. Untouched tree copied; the
   released build made in my own directories with `build.sh` (422 steps).
