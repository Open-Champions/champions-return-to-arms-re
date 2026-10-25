#!/usr/bin/env python3
"""Bounded inventory screen comparison with the original in ee_emu.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_inventory_screen.py [SLUS_209.73]

Runs constructed zero-world states for both seeds 20973 and 7. Callees outside
the named screen functions are stubbed; call submissions, writes and message
sender sites are compared, not pixels or live gameplay.
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != HERE] + [HERE]
from ee_emu import EE  # noqa: E402
import ref_inventory_screen as R  # noqa: E402

EXPECTED_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
HOME_ELF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SLUS_209.73')
DRAW, GRID, ROWS, INFO, INPUT = 0x1CD208, 0x1CC7E0, 0x1CC130, 0x1C8D38, 0x1CD988
BUILD, PICTURE = 0x1CBBE8, 0x108358
RES, RECT, CLIP, BEGIN, COLOR = 0x17365C, 0x17BD30, 0x17FB88, 0x1800B8, 0x1802E0
EQUIPPED, ALLOWED = 0x1C41D8, 0x1C4948
RECORD, PANEL = R.PLAYER_BASE, R.PANEL_BASE
SENDER = {0x1CE868: 'unequip', 0x1CE87C: 'equip', 0x1CEB1C: 'drop'}


def u(value):
    return value & 0xFFFFFFFF


def fixture(elf, seed, *, category=0, equip_result=0, allowed_result=0):
    e = EE(elf)
    e.mem.auto_map = True
    e.default_ret = 0
    e.mem.w32(0x404464, seed)
    e.mem.w32(0x86A6A4, seed)
    tex = e.alloc(64)
    e.mem.w16(tex, 32)
    e.mem.w16(tex + 2, 32)
    names = []

    def res(emu):
        try:
            name = emu.mem.cstr(u(emu.r[5]), 100)
        except Exception:
            name = ''
        names.append((emu._call_site, name))
        return tex

    def format_box(emu):
        fmt = emu.mem.cstr(u(emu.r[5]), 100)
        if fmt == 'inventrybox%d.tex':
            value = fmt % u(emu.r[6])
            emu.mem.write(u(emu.r[4]), value.encode() + b'\0')
            return len(value)
        return 0

    e.stub(RES, function=res)
    e.stub(0x3B7EF0, function=format_box)
    e.stub(0x173C84, ret=tex)
    e.stub(0x13E150, ret=1)
    e.stub(EQUIPPED, ret=equip_result)
    e.stub(ALLOWED, ret=allowed_result)
    e.mem.map(PANEL, 0x80)
    e.mem.w32(PANEL, 80)
    e.mem.w32(PANEL + 0x34, 0)
    e.mem.wf32(PANEL + 0x44, 112)
    e.mem.wf32(PANEL + 0x48, 132)
    e.mem.map(RECORD, 0x4C30)
    e.mem.w32(RECORD + 0x43D8, e.alloc(0x200))
    e.mem.w32(RECORD + 0x1330, 2)
    definition = e.alloc(0x40)
    e.mem.w8(definition + 0x1D, category)
    for off in (0x130, 0x178):
        e.mem.w32(RECORD + off, definition)
        e.mem.w16(RECORD + off + 4, 1)
    e.mem.w32(0x4F4228, RECORD + 0x130)
    e.mem.w32(0x4EBBB0, RECORD + 0x130)
    font = e.alloc(0x40)
    e.mem.w32(R.SMALL_FONT_WORD, font)
    e.mem.w32(0x4F7100, e.alloc(0x40))
    return e, names, tex, font, definition


def check_draw(elf, seed):
    e, names, tex, font, definition = fixture(elf, seed)
    e.follow = {GRID, ROWS, INFO}
    e.call(DRAW, 0, 2, 0, PANEL, max_steps=3_000_000)
    rects = [tuple(u(a) for a in c.args[:6]) for c in e.calls
             if c.site == 0x1CD728 and c.target == RECT]
    boxes = [name for site, name in names if site == 0x1CCB18]
    ends = [name for site, name in names if site == 0x1CCB68]
    variants = R.box_variants()
    grid_calls = [c for c in e.calls if c.target == GRID]
    small_font_sites = {0x1CC310, 0x1CC3F0, 0x1C911C, 0x1C92D0, 0x1CA2B4}
    begins = [c for c in e.calls if c.site in small_font_sites and c.target == BEGIN]
    selected = [c for c in e.calls if c.site == 0x1CC330 and c.target == COLOR]
    wrapped = [c for c in e.calls if c.site == 0x1CC380 and c.target == 0x181530]
    icons = [c for c in e.calls if c.site == 0x1CCEC0 and c.target == CLIP]
    box_sprites = [c for c in e.calls if c.site in (0x1CCB4C, 0x1CCBA0) and c.target == CLIP]
    underbar = [c for c in e.calls if c.site == 0x1CD774 and c.target == 0x17FB68]
    placements = [(u(c.args[1]), u(c.args[2]), 'end' if c.site == 0x1CCBA0 else 'numbered')
                  for c in box_sprites]
    checks = {
        'scrollbar': rects == R.strip_rects(80),
        'underbar': [(site, name) for site, name in names if site == 0x1CD754] ==
                    [(0x1CD754, 'inventoryunderbar.tex')] and len(underbar) == 1 and
                    u(underbar[0].args[3]) == 5,
        'box names': boxes == variants and ends == ['inventryboxend.tex'] * 5,
        'box positions': sorted(placements) == sorted(R.box_placements(80)),
        'box layer and tint': len(box_sprites) == 20 and all(
            u(c.args[3]) == 0 and u(c.args[4]) == 0x80808080 for c in box_sprites),
        'grid calls': len(grid_calls) == R.GRID_COLS * R.VISIBLE_ROWS,
        'small font': len(begins) == 5 and all(
            tuple(u(a) for a in c.args[:4]) == (font, 6, 0x80464646, 0xFFFFFFFF)
            for c in begins),
        'selected colour': len(selected) == 1 and u(selected[0].args[0]) == 0x805C2913,
        'selected wrap': len(wrapped) == 1 and tuple(u(a) for a in wrapped[0].args[:6]) ==
                         (244, 229, 0, 203, 0xFFFFFF9C, 580),
        'grid icons': len(icons) == 2 and all(u(c.args[3]) == R.GRID_LAYER for c in icons),
        'seed separation': e.mem.u32(0x404464) == seed and e.mem.u32(0x86A6A4) == R.BOX_ZERO_STATE_FINAL,
    }
    return checks, 'draw=%d grid=%d boxes=%d end=%d font=%d icons=%d' % (
        len(e.calls), len(grid_calls), len(boxes), len(ends), len(begins), len(icons))


def check_highlight(elf, seed):
    bad = []
    for equipped, blocked, flag41 in ((0, 0, 0), (1, 0, 0), (0, 1, 0),
                                      (0, 1, 1), (1, 1, 0)):
        e, _names, tex, font, definition = fixture(
            elf, seed, equip_result=equipped, allowed_result=blocked)
        e.follow = {GRID}
        if flag41:
            e.mem.w64(RECORD + 0x138, 1 << 41)
        e.call(DRAW, 0, 2, 0, PANEL, max_steps=3_000_000)
        fills = [u(c.args[5]) for c in e.calls
                 if c.site in (0x1CCE4C, 0x1CCE78, 0x1CCF04) and c.target == RECT]
        want = [R.grid_tint(equipped=bool(equipped), blocked=bool(blocked),
                            flag41=bool(flag41)),
                R.grid_tint(equipped=bool(equipped), blocked=bool(blocked))]
        if fills != want:
            bad.append((equipped, blocked, flag41, fills, [hex(v) for v in want]))
    return not bad, str(bad[:2]) if bad else '5 states, 2 cells each'


def check_info(elf, seed):
    bad = []
    for category in (0, 1, 2):
        e, names, tex, font, definition = fixture(elf, seed, category=category)
        e.follow = set()
        e.call(INFO, 0, 244, 230, RECORD + 0x130, 0, 0, 0, max_steps=1_000_000)
        called = {c.target for c in e.calls}
        expected = R.item_stat_kind(category)
        got = 'damage' if 0x104100 in called else 'armour' if 0x103EC8 in called else 'other'
        begins = [c for c in e.calls if c.target == BEGIN]
        frames = [c for c in e.calls if c.site == 0x1CB05C and c.target == 0x17C118]
        frame_ok = len(frames) == 1 and tuple(u(a) for a in frames[0].args[:6]) == R.item_info_frame(244, 230, category)
        if (got != expected or not begins or
                any(u(c.args[0]) != font or u(c.args[1]) != 6 for c in begins) or not frame_ok):
            bad.append((category, got, expected, len(begins), frame_ok))
    return not bad, str(bad[:2]) if bad else 'weapon, armour, other'


def check_input(elf, seed):
    cases = [(0x40, 0, 0), (0x40, 1, 0), (0x40, 0, 1),
             (0x10, 0, 0), (0x50, 0, 0), (0x80, 0, 0)]
    bad = []
    for edge, equipped, holdable in cases:
        e, names, tex, font, definition = fixture(elf, seed, equip_result=equipped)
        e.follow = set()
        e.mem.w32(0x41B960, 0x40)
        e.mem.w32(0x41B968, 0x10)
        e.mem.w32(0x41BFBC, 0x40)
        e.mem.map(0x4028D0, 0x80)
        for off in (8, 12, 16):
            e.mem.w32(0x4028D0 + off, edge)
        e.mem.wf32(PANEL + 0x44, 97)
        e.mem.wf32(PANEL + 0x48, 100)
        e.mem.w32(RECORD + 0x1330, 1)
        if holdable:
            e.mem.w64(RECORD + 0x138, 1 << 35)
        e.call(INPUT, 0, 2, 0, PANEL, max_steps=2_000_000)
        calls = [SENDER[c.site] for c in e.calls if c.site in SENDER]
        got = calls[0] if calls else 'drag' if e.mem.u32(PANEL + 0x58) == 1 else None
        want = R.action(edge, equipped=bool(equipped), holdable=bool(holdable))
        if got != want or e.mem.u32(0x404464) != seed:
            bad.append((hex(edge), equipped, holdable, got, want))
    return not bad, str(bad[:2]) if bad else '%d actions' % len(cases)


def check_pages(elf, seed):
    bad = []
    for page in range(6):
        e, names, tex, font, definition = fixture(elf, seed)
        e.follow = set()
        e.mem.w32(PANEL + 0x50, page)
        e.call(DRAW, 0, 2, 0, PANEL, max_steps=3_000_000)
        grid = sum(c.target == GRID for c in e.calls)
        stats = sum(c.target == 0x1D1DB8 for c in e.calls)
        if (grid, stats) != ((90, 0) if page < 3 else (0, 1)):
            bad.append((page, grid, stats))
    return not bad, str(bad[:2]) if bad else 'bags 0-2; stat pages 3-5'


def check_cursor(elf, seed):
    bad = []
    col, row = R.cursor_cell(80, 97, 100, 32)
    for page in (0, 1, 2):
        e, names, tex, font, definition = fixture(elf, seed)
        e.follow = set()
        e.mem.w32(PANEL + 0x50, page)
        e.mem.map(0x4028D0, 0x80)
        for off in (8, 12, 16):
            e.mem.w32(0x4028D0 + off, R.CROSS['equip'])
        e.mem.w32(0x41B960, R.CROSS['equip'])
        e.mem.w32(0x41B968, R.CROSS['drop'])
        e.mem.w32(0x41BFBC, R.CROSS['equip'])
        e.mem.wf32(PANEL + 0x44, 97)
        e.mem.wf32(PANEL + 0x48, 100)
        e.mem.w32(RECORD + 0x1330, 1)
        # Page-specific pointers in the display grid and source bags make a
        # missing page term observable, even when both records look populated.
        sentinels = [e.alloc(0x40) for _ in range(6)]
        for other in (0, 1, 2):
            e.mem.w32(R.grid_cell(RECORD + 0x130, col, row, other), sentinels[other])
            e.mem.w32(R.bag_page_base(RECORD + 0x130, other),
                      sentinels[other if other == 0 else 3 + other])
        e.call(INPUT, 0, 2, 0, PANEL, max_steps=2_000_000)
        expected = R.grid_cell(RECORD + 0x130, col, row, page)
        sends = [c for c in e.calls if c.site == 0x1CE87C and c.target == 0x1C5800]
        bag = R.bag_page_base(RECORD + 0x130, page)
        if (e.mem.u32(PANEL + 0x60) != expected or
                e.mem.u32(expected) != sentinels[page] or
                len(sends) != 1 or u(sends[0].args[1]) != bag or
                e.mem.u32(bag) != sentinels[page if page == 0 else 3 + page]):
            bad.append((page, hex(e.mem.u32(PANEL + 0x60)), hex(expected),
                        [hex(u(c.args[1])) for c in sends], hex(bag)))
    return not bad, str(bad[:2]) if bad else 'pages 0-2: hover and action targets'


def check_grid_builder(elf, seed):
    e, _names, _tex, _font, _definition = fixture(elf, seed)
    pointer = e.alloc(0x23988)
    e.mem.w32(0x4EBBB0, pointer)
    # Page 0 leaves one column; its last two-column item must start row 1.
    widths = ((0, 32, 0, 64, 0, 32),
              (32, 0, 32, 0, 0), (64, 0, 0, 32, 0))
    by_item = {}
    definitions = {}
    for page, sizes in enumerate(widths):
        base = R.bag_page_base(RECORD + 0x130, page)
        e.mem.w32(RECORD + 0x1330 + page * R.BAG_PAGE_STRIDE, len(sizes))
        stale = R.display_grid_base(pointer, 0, page) + 8 * R.GRID_COL_STRIDE + 74 * R.ITEM_SIZE
        e.mem.w32(stale, 0xDEADBEEF)
        e.mem.w16(stale + 0x22, 0xCAFE)
        for index, width in enumerate(sizes):
            item = base + index * R.ITEM_SIZE
            definition = e.alloc(0x40)
            e.mem.w32(item, definition)
            e.mem.w16(item + 4, index + 1)
            e.mem.w32(item + 0x20, 0xA100 + page * 16 + index)
            e.mem.w32(item + 0x28, 0xBEEF0000 + page * 16 + index)
            by_item[item] = width
            definitions[page, index] = definition

    def item_size(emu):
        emu.mem.w32(u(emu.r[6]), by_item[u(emu.r[5])])
        emu.mem.w32(u(emu.r[7]), 0)
        return 0

    # This isolates the placement loop. One-row height is the result of the
    # original float rounding chain for this bounded footprint fixture.
    e.stub(0x1083A4, function=item_size)
    e.stub(0x3AFAC0, ret=1)
    e.follow = set()
    e.call(BUILD, 0, 0, 0, max_steps=3_000_000)
    bad = []
    size_calls = [c for c in e.calls if c.site == 0x1CBD2C and c.target == 0x1083A4]
    if len(size_calls) != sum(map(len, widths)):
        bad.append(('size calls', len(size_calls)))
    for page, sizes in enumerate(widths):
        expected = R.bounded_grid_placement(sizes)
        if page == 0 and (any((col, 0) not in expected for col in range(8)) or
                          (8, 0) in expected or
                          (expected.get((0, 1)), expected.get((1, 1))) != (5, 5)):
            bad.append(('next-row fixture', expected.get((0, 1)), expected.get((1, 1))))
        for col in range(R.GRID_COLS):
            for row in range(R.GRID_ROWS):
                cell = R.display_grid_base(pointer, 0, page) + col * R.GRID_COL_STRIDE + row * R.ITEM_SIZE
                index = expected.get((col, row))
                want = (definitions[page, index], index) if index is not None else (0, 0)
                got = (e.mem.u32(cell), e.mem.u16(cell + 0x22))
                if got != want:
                    bad.append((page, col, row, got, want))
                if index is not None and (e.mem.u16(cell + 4) != index + 1 or
                        e.mem.u32(cell + 0x28) != 0xBEEF0000 + page * 16 + index):
                    bad.append((page, col, row, 'record copy'))
    return not bad, str(bad[:2]) if bad else 'three bags, mixed 1-3 column footprints, next-row copy/stamp, 2025 cells'


def check_grid_draw_source(elf, seed):
    bad = []
    for page in (0, 1, 2):
        e, _names, tex, _font, _definition = fixture(elf, seed)
        pointer = e.alloc(0x23988)
        e.mem.w32(0x4EBBB0, pointer)
        e.mem.w32(PANEL + 0x50, page)
        for other in (0, 1, 2):
            grid_item = R.display_grid_base(pointer, 0, other)
            bag_item = R.bag_page_base(RECORD + 0x130, other)
            e.mem.w32(grid_item, e.alloc(0x40))
            e.mem.w32(bag_item, e.alloc(0x40))
            e.mem.w16(grid_item + 4, 1)
            e.mem.w16(bag_item + 4, 1)
        e.stub(PICTURE, ret=tex)
        e.follow = {GRID}
        e.call(DRAW, 0, 2, 0, PANEL, max_steps=3_000_000)
        expected = R.display_grid_base(pointer, 0, page)
        grid_calls = [c for c in e.calls if c.site == 0x1CD914 and c.target == GRID]
        pictures = [c for c in e.calls if c.site == 0x1CC8EC and c.target == PICTURE]
        if (len(grid_calls) != 90 or u(grid_calls[0].args[2]) != expected or
                len(pictures) != 1 or u(pictures[0].args[1]) != expected or
                e.mem.u32(expected) == e.mem.u32(R.bag_page_base(RECORD + 0x130, page))):
            bad.append((page, len(grid_calls), len(pictures),
                        [hex(u(c.args[1])) for c in pictures[:2]], hex(expected)))
    return not bad, str(bad[:2]) if bad else 'pages 0-2 read display copies, distinct from bag records'


def check_held_picture(elf, seed):
    bad = []
    for dragging in (0, 1):
        e, _names, tex, _font, definition = fixture(elf, seed)
        held_picture = e.alloc(0x40)
        held = R.bag_page_base(RECORD + 0x130, 1)
        e.mem.w32(held, definition)
        e.mem.w16(held + 4, 1)
        e.mem.w32(RECORD + 0x54, 3)
        e.mem.w32(PANEL + 0x58, dragging)
        e.mem.w32(PANEL + 0x64, held)
        e.stub(PICTURE, ret=held_picture)
        e.follow = set()
        e.call(DRAW, 0, 2, 0, PANEL, max_steps=3_000_000)
        pictures = [c for c in e.calls if c.site == 0x1CD4B0 and c.target == PICTURE]
        sprites = [c for c in e.calls if c.site in (0x1CD4E8, 0x1CD520) and c.target == 0x17FB68]
        got = [(u(c.args[0]), u(c.args[1]), u(c.args[2]), u(c.args[3]), u(c.args[4]))
               for c in sprites]
        want = R.held_picture_sprites(held_picture, 112, 132) if dragging else []
        if (len(pictures) != dragging or
                (dragging and (u(pictures[0].args[0]) != 3 or u(pictures[0].args[1]) != held)) or
                got != want):
            bad.append((dragging, len(pictures), got, want))
    return not bad, str(bad[:2]) if bad else 'idle: none; drag: held pointer and two layer-7 sprites'


def main(argv):
    elf = argv[1] if len(argv) > 1 else HOME_ELF
    if not os.path.isfile(elf):
        print('SKIP: original executable absent: %s' % elf)
        return 0
    with open(elf, 'rb') as source:
        digest = hashlib.sha256(source.read()).hexdigest()
    if digest != EXPECTED_SHA:
        print('REFUSE: expected SLUS_209.73 v2.00 sha256 %s; got %s' % (EXPECTED_SHA, digest))
        return 2
    failed = []
    for seed in (20973, 7):
        checks, detail = check_draw(elf, seed)
        for name, good in checks.items():
            print('%s seed=%d %s %s' % ('PASS' if good else 'FAIL', seed, name, detail))
            if not good:
                failed.append((seed, name))
        for name, func in (('highlight', check_highlight), ('item stats', check_info),
                           ('equip/drop input', check_input), ('pages', check_pages),
                           ('cursor', check_cursor), ('grid builder', check_grid_builder),
                           ('grid draw source', check_grid_draw_source),
                           ('held picture', check_held_picture)):
            good, detail = func(elf, seed)
            print('%s seed=%d %s %s' % ('PASS' if good else 'FAIL', seed, name, detail))
            if not good:
                failed.append((seed, name))
    print('%d properties; %d failed' % (38, len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
