#!/usr/bin/env python3
"""Fail-closed no-stub check of the proposed full valor load (private inputs only).

This is a boundary test, not a combat reference model. The ELF boot and a direct
game_loadLevel call both stop before a level is loaded because EE has no kernel.
The direct call is deliberately labelled partial: it has no hub session state.
"""
import argparse
import hashlib
import mmap
from pathlib import Path

from dump_tables import iso_files
from ee_emu import CpuTrap, EE


FILES = ("SLUS_209.73", "HUB.GOB", "VALOR.GOB", "WARBOAR.LMP",
         "MINOTAUR.LMP", "HUD.LMP")
CONSTRUCTORS = {0x109D68, 0x14CB10, 0x2BA03C, 0x288FDC}


def verify_disc_inputs(iso_path, local_dir):
    """Check private inputs against the mounted disc index without exporting bytes."""
    with open(iso_path, "rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as disc:
            files = list(iso_files(disc))
            entries = {path.rsplit("/", 1)[-1].upper(): (offset, size)
                       for path, offset, size in files}
            for name in FILES:
                offset, size = entries[name]
                local = (local_dir / name).read_bytes() if (local_dir / name).exists() else None
                if local is not None:
                    assert len(local) == size
                    assert hashlib.sha256(local).digest() == hashlib.sha256(
                        disc[offset:offset + size]).digest(), name
    return len(files)


def stopped_at_kernel(exe_path, seed, entry, name, argument=None):
    emu = EE(exe_path)
    emu.mem.w32(0x404464, seed)
    args = ()
    if argument is not None:
        address = emu.alloc(len(argument) + 1)
        emu.mem.write(address, argument + b"\0")
        args = (address,)
    assert emu.follow is None and not emu.hooks and emu.syscall_handler is None
    try:
        emu.call(entry, *args, max_steps=10000000)
    except CpuTrap as error:
        result = str(error)
    else:
        raise AssertionError(f"{name}: unexpectedly returned")
    expected = ("SYSCALL at 0x0014fc48 (v1 = 60)" if name == "ELF boot"
                else "SYSCALL at 0x00352e14 (v1 = 124)")
    assert expected in result, (name, result)
    assert not any(call.stubbed for call in emu.calls)
    assert not any(call.target in CONSTRUCTORS for call in emu.calls)
    assert not any(call.target == 0x17365C for call in emu.calls)
    print(f"seed {seed}: {name}: {result}; {emu.steps} instructions, "
          f"{len(emu.calls)} calls, 0 resource lookups, 0 enemy constructors")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--local-dir", type=Path, default=Path("local"))
    parser.add_argument("--seed", type=int, action="append", required=True)
    args = parser.parse_args()
    count = verify_disc_inputs(args.iso, args.local_dir)
    print(f"disc index: {count} files; private inputs match where present")
    for seed in args.seed:
        stopped_at_kernel(args.exe, seed, 0x14FA88, "ELF boot")
        stopped_at_kernel(args.exe, seed, 0x1E55C0,
                          "direct game_loadLevel (no hub state)", b"valor")


if __name__ == "__main__":
    main()
