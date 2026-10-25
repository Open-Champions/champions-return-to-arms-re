# Model form 0x46: external row-register boundary

2026-10-17, SLUS-20973 v2.00. **Partial**, not a clearance of the native
model-coverage refusal. No reference implementation with invented row
registers is supplied.

**Observed:** [model-texture](../formats/model-texture.md), packet layout,
describes form 0x46's `STMOD 1` before position unpack, then `STMOD 0`.
It has no weight block. The per-packet data therefore does not by itself
determine positions: VIF row state belongs to the surrounding command stream.
Assuming all row registers zero is not an established original-model contract.

**Observed:** [render-pipeline](render-pipeline.md) 4.6 addresses
`world_drawChunk` at `0x1887b8`, which supplies `STROW tx,ty,tz,0` before
its level packet. Its level equation is
`p=(stored_position+row_xyz)/16`, then its supplied setup matrix and world
projection. Its chunk rotation and translation conventions are documented
there. Those are **level-drawer** inputs; transplanting them to a standalone
model requires proving the model's actual caller/setup.

**Observed:** setup helper `0x175950` emits the level-form setup entries
0x16 and 0x34 (`0x175a94,0x175a9c`), as the earlier render-pipeline audit
notes. That audit found no caller and leaves the sky-dome path unresolved.
The current pass re-read the helper's setup head, but did not establish a
reachable caller that writes the required row state for the model. An
uncalled candidate helper is not dispatch evidence.

**Unknown:** the exact original command-stream predecessor and surviving
row values for the exceptional model draw. To settle: instrument VIF
`STROW/STMOD` and the relevant REF/MSCAL chain for that specific original
draw, retaining which producer last wrote all four row registers; validate
the reconstructed positions against the original VU input. Keep game-derived
traces under `local/`. This branch did not run a game process, alter the live
research build or contact the public service.

**Inferred host design:** a packet decoder can expose an explicit required
external VIF state and decode when the caller supplies addressed provenance.
That is different from accepting a context-free .vif using guessed zero
rows. Until that producer is established, keep the native refusal in
`worktrees/model-coverage/docs/MODEL_FORMS.md` and report this target unknown.
