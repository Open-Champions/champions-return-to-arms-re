tools/recomp/app/vendor - single-file audio decoders for the player's own boss music
(app/bossmusic.cpp; docs/issues/native-hud.md, "Custom music in the native program").

Copied unchanged from their public repositories on 2026-10-20.  Each file states its own
licence at its end; both choices each file offers allow copying, changing and shipping it
in source or compiled form, with nothing asked in return under the public-domain choice.

  file           what it reads   version in the file      source (commit)                                         licence (the file's own text, at its end)
  stb_vorbis.c   Ogg Vorbis      v1.22                    github.com/nothings/stb  a7d4c2175630e1ea5b6f8dd00ab96fed0b97b96d   public domain (Unlicense) or MIT, either
  dr_mp3.h       MP3             v0.7.4 (master, "TBD")   github.com/mackron/dr_libs  d89ecf1d0fc68fbada3f7790618270c8c883e988   public domain (Unlicense) or MIT No Attribution, either
  dr_wav.h       WAV             v0.14.6 (master, "TBD")  github.com/mackron/dr_libs  d89ecf1d0fc68fbada3f7790618270c8c883e988   public domain (Unlicense) or MIT No Attribution, either

SHA-256 of the files as copied:
  4c7cb2ff1f7011e9d67950446b7eb9ca044f2e464d76bfbb0b84dd2e23e65636  stb_vorbis.c
  997b7ee18de6e6b81e2a83f1ea9fc62aef25c62b28d48db95635f49e65de0a2f  dr_mp3.h
  03e70c1a2d9787cd7ed3e966c075bea7bac6373f759db9cd7ca9ccdfc4ec4493  dr_wav.h

The implementations are compiled once, inside app/bossmusic.cpp.  No music is shipped:
the decoders only read files a player puts in <data>/music/boss/ himself.
