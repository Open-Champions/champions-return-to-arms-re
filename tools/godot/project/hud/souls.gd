extends Control
# souls.gd - Hardcore mode's part of the HUD (the internal name of the mode is "souls": tools/recomp/app/soulscombat.h,
# docs/issues/native-souls-combat.md): the stamina bar under the middle of the picture, a frame
# round it during a dodge's invulnerable ticks, red while the guard is broken, a gold line over it in
# the parry's window and a red one under it while a riposte or guard counter is open; the flasks
# (pips and a count) left of it; the lock-on marker on the locked creature with its health; a
# marker over this player's death drop when it is on this level; and the weapon card over the bar
# (the weapon, its upgrade, class, scaling grades, damage percent, two-handing, the equip load and
# its tier, the upgrade materials; near a save point the next upgrade's price).
#
# It reads the mode's block in the game's memory (0xE0800: "SOUL", then the numbers) through the
# machine's peek_u32 / peek_f32 - nothing else of the game or the library.  With a library that
# does not have the mode the block is not there and nothing is drawn.
#
# Hook (one line pair in hud.gd's _ready, after the pieces are set up):
#     var souls: Control = load("res://hud/souls.gd").new(); souls.set("hud", self); root.add_child(souls)

const Style := preload("res://hud/style.gd")
const Hud := preload("res://hud/hud.gd")

const BASE := 0xE0800
const MAGIC := 0x4c554f53
const FL_IFRAMES := 2
const FL_BROKEN := 32
const FL_EMPTY := 64
const FL_PARRY := 128
const FL_RIPOSTE := 256
const FL_COUNTER := 512
const FL_DRINK := 1024
const EXT := 0x200                  # the second per-player part (kept over a death): flasks, the death drop
const STAMINA_MAX := 10000.0        # soulscombat::Tuning::stamina_max
const WPN := 0x400                  # the weapons part (soulscombat.h, version 3): 0x60 a player
const CLASSES := ["unarmed", "dagger", "sword", "axe", "mace", "great weapon", "spear", "staff", "bow"]
const TIERS := ["LIGHT", "MEDIUM", "HEAVY", "OVERLOADED"]

var hud: Node
var on := false
var stamina := 1.0
var shown := 1.0
var flags := 0
var lock := false
var lock_at := Vector3.ZERO
var lock_hp := 0.0
var lock_max := 0.0
var flasks := 0
var flask_max := 4                  # soulscombat::Tuning::flask_count (the most seen: the count is full at a level's start)
var drop := false
var drop_at := Vector3.ZERO
# the weapon card: the weapon in hand, its upgrade, class, grades and damage, the equip load and its tier, the materials,
# and near a save point what the next upgrade costs (our own text)
var card := ""
var load_line := ""
var upgrade_line := ""
var tier := 0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)


func _peek(offset: int) -> int:
	var v: int = hud.machine.peek_u32(BASE + offset)
	return v - 0x100000000 if v >= 0x80000000 else v


func _process(_delta: float) -> void:
	var was := on
	on = false
	if hud == null or hud.machine == null or not hud.ok or not hud.machine.has_method("peek_u32"):
		if was:
			queue_redraw()
		return
	if _peek(0) != MAGIC or _peek(8) != 1 or hud.me.is_empty():
		if was:
			queue_redraw()
		return
	var slot: int = int(hud.me.get("slot", 0))
	if slot < 0 or slot > 3:
		return
	on = true
	stamina = clampf(float(_peek(0x40 + slot * 0x40)) / STAMINA_MAX, 0.0, 1.0)
	flags = _peek(0x40 + slot * 0x40 + 8)
	shown = lerpf(shown, stamina, 0.35)
	flasks = _peek(EXT + slot * 0x40)
	flask_max = maxi(flask_max, flasks)
	drop = _peek(0x19c) != 0
	if drop:
		var e := BASE + EXT + slot * 0x40
		drop_at = Vector3(hud.machine.peek_f32(e + 0x18), hud.machine.peek_f32(e + 0x1c), hud.machine.peek_f32(e + 0x20) + 20.0)
	var w := WPN + slot * 0x60
	var cls: int = clampi(_peek(w), 0, CLASSES.size() - 1)
	var level: int = _peek(w + 0x10)
	var grades: int = _peek(w + 0x14)
	var two: bool = _peek(w + 0x1c) != 0 and cls != 0 and cls != 8
	var name := ""
	for k in range(8):
		var v: int = hud.machine.peek_u32(BASE + 0x1a0 + k * 4)
		for b in range(4):
			var ch: int = (v >> (8 * b)) & 0xff
			if ch == 0:
				break
			name += char(ch)
		if name.length() < (k + 1) * 4:
			break
	var g := func(shift: int) -> String:
		var ch: int = (grades >> shift) & 0xff
		return char(ch) if ch != 0 else "-"
	card = "%s +%d  %s  STR %s DEX %s%s  %d%%%s" % [name if name != "" else "-", level, CLASSES[cls], g.call(0), g.call(8),
		("  INT " + g.call(16)) if cls == 7 else "", _peek(w + 0x48), "  2H" if two else ""]
	tier = clampi(_peek(w + 0xc), 0, 3)
	load_line = "LOAD %.1f/%.1f %s  WHETSTONES %d%s" % [_peek(w + 4) / 100.0, maxi(1, _peek(w + 8)) / 100.0, TIERS[tier], _peek(w + 0x28),
		"  ART ..." if _peek(w + 0x40) > 0 else ""]
	upgrade_line = ""
	if _peek(w + 0x2c) != 0:
		var gold: int = _peek(w + 0x4c)
		var mats: int = _peek(w + 0x50)
		upgrade_line = ("UPGRADE TO +%d: %d GOLD, %d WHETSTONE%s  (HOLD L3 + USE)" % [level + 1, gold, mats, "" if mats == 1 else "S"]) if gold > 0 else "FULLY UPGRADED"
	lock = _peek(0x180) != 0
	if lock:
		lock_at = Vector3(hud.machine.peek_f32(BASE + 0x188), hud.machine.peek_f32(BASE + 0x18c), hud.machine.peek_f32(BASE + 0x190))
		lock_hp = hud.machine.peek_f32(BASE + 0x194)
		lock_max = hud.machine.peek_f32(BASE + 0x198)
	queue_redraw()


func _draw() -> void:
	if not on or hud.show <= 0.01:
		return
	var s: float = hud.s
	var a: float = hud.show
	var pic: Rect2 = hud.picture
	var area: Rect2 = hud.area
	# where the bar sits, by layout (hud.gd): it is the third of the player's bars and keeps clear of the others -
	#   first person: under the two slim bars in the middle (status.gd _minimal), as long as they are
	#   overhead, third person: on the player's frame lower left (status.gd _frame), in the gap between it and the party's
	#   frames, as long as the frame's bars - nothing of the middle of the picture (markers, prompts, slots) is covered
	var w: float
	var h: float
	var x: float
	var y: float
	if int(hud.layout) == Hud.LAYOUT_FIRST:
		w = 300.0 * s
		h = maxf(4.0, 6.0 * s)
		x = area.get_center().x - w * 0.5
		y = area.end.y - 96.0 * s + 30.0 * s
	else:
		var k: float = 0.9 if int(hud.layout) == Hud.LAYOUT_THIRD else 1.0
		w = 280.0 * s * k
		h = maxf(5.0, 7.0 * s * k)
		x = area.position.x + 100.0 * s * k
		y = area.end.y - 104.0 * s * k - 16.0 * s * k - h
	var rect := Rect2(Vector2(x, y).round(), Vector2(w, h).round())
	var broken := (flags & FL_BROKEN) != 0
	var empty := (flags & FL_EMPTY) != 0
	# the theme's own bar (style.gd, or a skin's), as the health and mana bars are drawn: the same frame and ghost of
	# what was just spent; green, orange-red while the guard is broken
	var fill_a := Color(0.85, 0.36, 0.2) if broken else Color(0.42, 0.82, 0.36)
	var fill_b := Color(0.55, 0.18, 0.1) if broken else Color(0.2, 0.5, 0.18)
	Style.bar(self, rect, stamina, maxf(shown, stamina), fill_a, fill_b, s, a)
	if empty:
		draw_rect(rect, Color(0.9, 0.12, 0.12, 0.35 * a))
	if (flags & FL_IFRAMES) != 0:
		draw_rect(rect.grow(4.0 * s), Color(1, 1, 1, 0.8 * a), false, maxf(1.5, 2.0 * s))
	if (flags & FL_PARRY) != 0:
		draw_rect(Rect2(rect.position + Vector2(0, -5.0 * s), Vector2(rect.size.x, 2.0 * s)), Color(0.95, 0.9, 0.5, 0.9 * a))
	if (flags & (FL_RIPOSTE | FL_COUNTER)) != 0:
		draw_rect(Rect2(rect.position + Vector2(0, rect.size.y + 3.0 * s), Vector2(rect.size.x, 2.0 * s)), Color(0.95, 0.38, 0.25, 0.9 * a))
	# the flasks: amber pips left of the bar, spent ones dark, and the count
	var pw := maxf(3.0, 5.0 * s)
	var ph := maxf(8.0, 14.0 * s)
	for k in range(flask_max):
		var px := rect.position.x - 10.0 * s - float(flask_max - k) * (pw + 3.0 * s)
		var pip := Rect2(Vector2(px, rect.end.y - ph).round(), Vector2(pw, ph).round())
		var full := k < flasks
		var fade := 0.45 if (flags & FL_DRINK) != 0 and k == flasks else 1.0
		draw_rect(pip.grow(1.0), Color(0, 0, 0, 0.5 * a))
		draw_rect(pip, (Color(0.92, 0.55, 0.16, a * fade) if full else Color(0.22, 0.2, 0.2, 0.8 * a)))
	var font := ThemeDB.fallback_font
	var fs := int(maxf(9.0, 11.0 * s))
	var label := "%d" % flasks
	var lx := rect.position.x - 10.0 * s - float(flask_max) * (pw + 3.0 * s) - font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x - 4.0 * s
	draw_string(font, Vector2(lx, rect.end.y), label, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(1, 0.85, 0.6, a))
	# the weapon card over the bar (and the upgrade's price near a save point)
	var cs := int(maxf(9.0, 10.0 * s))
	var line_h := float(cs) + 3.0 * s
	var ty := rect.position.y - 6.0 * s - line_h
	var tier_colour := Color(0.95, 0.35, 0.3, a) if tier == 3 else (Color(0.95, 0.72, 0.3, a) if tier == 2 else Color(0.8, 0.88, 0.8, a))
	draw_string(font, Vector2(rect.position.x, ty), load_line, HORIZONTAL_ALIGNMENT_LEFT, -1, cs, tier_colour)
	draw_string(font, Vector2(rect.position.x, ty - line_h), card, HORIZONTAL_ALIGNMENT_LEFT, -1, cs, Color(0.95, 0.92, 0.82, a))
	if upgrade_line != "":
		draw_string(font, Vector2(rect.position.x, ty - 2.0 * line_h), upgrade_line, HORIZONTAL_ALIGNMENT_LEFT, -1, cs, Color(0.63, 0.9, 1.0, a))
	# the death drop: a pale green upright diamond over the spot
	if drop and hud.gs != null:
		var dc: Vector3 = hud.gs.project(drop_at)
		if dc.z > 1.0:
			var q: Vector2 = hud.to_window(dc.x, dc.y)
			if pic.grow(20.0).has_point(q):
				var r := 9.0 * s
				draw_colored_polygon(PackedVector2Array([q + Vector2(0, -1.6 * r), q + Vector2(0.6 * r, 0), q + Vector2(0, 1.6 * r), q + Vector2(-0.6 * r, 0)]), Color(0.56, 0.94, 0.69, 0.85 * a))
	if lock and hud.gs != null:
		var sc: Vector3 = hud.gs.project(lock_at)
		if sc.z > 1.0:
			var p: Vector2 = hud.to_window(sc.x, sc.y)
			if pic.grow(20.0).has_point(p):
				var r := 11.0 * s
				var outer := PackedVector2Array([p + Vector2(0, -r), p + Vector2(r, 0), p + Vector2(0, r), p + Vector2(-r, 0)])
				draw_colored_polygon(outer, Color(0.95, 0.88, 0.56, 0.85 * a))
				var k := r * 0.45
				draw_colored_polygon(PackedVector2Array([p + Vector2(0, -k), p + Vector2(k, 0), p + Vector2(0, k), p + Vector2(-k, 0)]), Color(0.05, 0.05, 0.05, 0.8 * a))
				if lock_max > 0.0:
					var bw := 64.0 * s
					var bar := Rect2((p + Vector2(-bw * 0.5, r + 6.0 * s)).round(), Vector2(bw, 5.0 * s).round())
					Style.bar(self, bar, clampf(lock_hp / lock_max, 0.0, 1.0), 0.0, Style.ENEMY_A, Style.ENEMY_B, s, a)
