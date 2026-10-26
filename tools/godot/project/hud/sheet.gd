extends Control
# sheet.gd - Hardcore mode's character sheet (tools/recomp/app/soulscombat.h, docs/issues/native-souls-combat.md 2.9): the seven
# attributes (Vigor, Mind, Endurance, Strength, Dexterity, Intelligence, Faith), what they make (hit points, mana, the stamina
# bar, the equip load, the weapon's and the spells' scaling grades) and the spellbook (the spell slots with each spell's rank
# and mana cost, the attuned ones marked).  Shown while the mode's character screen is open at a save point (the game's
# simulation: L3 held + L2), and on this machine with P (or "app souls sheet"); the selected row of the open screen is marked.
#
# Like souls.gd it reads only the mode's block in the game's memory (0xE0800) through the machine's peek_u32 / peek_f32; with
# a library that does not have the mode nothing is drawn.  souls.gd adds it (no line in hud.gd).

const BASE := 0xE0800
const MAGIC := 0x4c554f53
const STATS := 0x600                # the attributes part: 0x80 a player
const COSTS := 0xa00                # u16[15] mana costs (tenths), u8[15] ranks: 0x40 a player
const NAMES := 0xb00                # the local player's ability records' names: 24 bytes each
const WPN := 0x400
const CLASS_WORDS := ["BARBARIAN", "CLERIC", "SHADOW KNIGHT", "RANGER", "WIZARD", "BERSERKER", "SHAMAN"]
const ATTRS := ["VIGOR", "MIND", "ENDURANCE", "STRENGTH", "DEXTERITY", "INTELLIGENCE", "FAITH"]
const TIERS := ["LIGHT", "MEDIUM", "HEAVY", "OVERLOADED"]

var hud: Node
var asked := false                  # P on this machine (presentation only)
var lines: Array = []               # [text, row] of the sheet; row >= 0 is a row of the open screen
var open := false
var row := 0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_P:
		asked = not asked
		queue_redraw()


func _peek(offset: int) -> int:
	var v: int = hud.machine.peek_u32(BASE + offset)
	return v - 0x100000000 if v >= 0x80000000 else v


func _text(offset: int, most: int) -> String:
	var out := ""
	for k in range(0, most, 4):
		var v: int = hud.machine.peek_u32(BASE + offset + k)
		for b in range(4):
			var ch: int = (v >> (8 * b)) & 0xff
			if ch == 0:
				return out
			out += char(ch)
	return out


func _grade(word: int, shift: int) -> String:
	var ch: int = (word >> shift) & 0xff
	return char(ch) if ch != 0 else "-"


func _process(_delta: float) -> void:
	var was := not lines.is_empty()
	lines = []
	if hud == null or hud.machine == null or not hud.ok or not hud.machine.has_method("peek_u32") or hud.me.is_empty():
		if was:
			queue_redraw()
		return
	if _peek(0) != MAGIC or _peek(8) != 1 or _peek(4) < 4:
		if was:
			queue_redraw()
		return
	var slot: int = int(hud.me.get("slot", 0))
	if slot < 0 or slot > 3:
		return
	var a := STATS + slot * 0x80
	open = _peek(a + 0x24) != 0
	if not (open or asked or _peek(0x1c0) != 0):
		if was:
			queue_redraw()
		return
	row = _peek(a + 0x28)
	var v: Array = []
	for k in range(7):
		v.append(_peek(a + 4 * k))
	var level: int = _peek(a + 0x68)
	var unspent: int = _peek(a + 0x1c)
	var slots: int = clampi(_peek(a + 0x2c), 0, 9)
	var cls: int = clampi(_peek(a + 0x70), 0, 6)
	var w := WPN + slot * 0x60
	lines.append(["%s  LEVEL %d  POINTS %d" % [CLASS_WORDS[cls], level, unspent], -1])
	lines.append(["%-13s %3d   HP %.0f/%.0f" % [ATTRS[0], v[0], hud.machine.peek_f32(BASE + 0x1d0), hud.machine.peek_f32(BASE + 0x1d4)], -1])
	lines.append(["%-13s %3d   MANA %.0f/%.0f" % [ATTRS[1], v[1], hud.machine.peek_f32(BASE + 0x1d8), hud.machine.peek_f32(BASE + 0x1dc)], 0])
	lines.append(["%-13s %3d   STAMINA %.0f  LOAD %.1f/%.1f %s" % [ATTRS[2], v[2], _peek(a + 0x38) / 100.0, _peek(w + 4) / 100.0,
		maxi(1, _peek(w + 8)) / 100.0, TIERS[clampi(_peek(w + 0xc), 0, 3)]], 1])
	for k in range(3, 6):
		lines.append(["%-13s %3d" % [ATTRS[k], v[k]], -1])
	lines.append(["%-13s %3d" % [ATTRS[6], v[6]], 2])
	var grades: int = _peek(w + 0x14)
	var weapon := _text(0x1a0, 32)
	lines.append(["WEAPON  %s +%d  STR %s DEX %s INT %s  %d%%" % [weapon if weapon != "" else "-", _peek(w + 0x10), _grade(grades, 0), _grade(grades, 8),
		_grade(grades, 16), _peek(w + 0x48)], -1])
	var sg: int = _peek(a + 0x4c)
	lines.append(["SPELLS  INT %s  FTH %s  %d%%   SLOTS %d OF %d (*)" % [_grade(sg, 0), _grade(sg, 8), _peek(a + 0x48), _peek(a + 0x74), slots], -1])
	var c := COSTS + slot * 0x40
	var attuned: int = _peek(a + 0x34)
	var n := 0
	for j in range(15):
		var k: int = (hud.machine.peek_u32(BASE + 0x1e0 + (j & ~3)) >> (8 * (j & 3))) & 0xff
		if k >= 15:
			break
		var cost: int = (hud.machine.peek_u32(BASE + c + 2 * (k & ~1)) >> (16 * (k & 1))) & 0xffff
		var rank: int = (hud.machine.peek_u32(BASE + c + 0x20 + (k & ~3)) >> (8 * (k & 3))) & 0xff
		var star := "*" if (attuned >> k) & 1 else " "
		lines.append(["%s %-22s RANK %d  %.1f MANA" % [star, _text(NAMES + 24 * k, 24), rank, cost / 10.0], 3 + j])
		n += 1
	if n == 0:
		lines.append(["  (NO SPELLS)", -1])
	if open:
		lines.append(["UP/DOWN CHOOSE  RIGHT SPEND / INTO A SLOT  LEFT OUT OF ITS SLOT  BLOCK CLOSES", -1])
	elif unspent > 0:
		lines.append(["SPEND THE POINTS AT A SAVE POINT: HOLD L3 + L2", -1])
	queue_redraw()


func _draw() -> void:
	if lines.is_empty() or hud == null or hud.show <= 0.01:
		return
	var s: float = hud.s
	var a: float = hud.show
	var area: Rect2 = hud.area
	var font := ThemeDB.fallback_font
	var fs := int(maxf(10.0, 15.0 * s))
	var lh := float(fs) + 5.0 * s
	var widest := 0.0
	for l in lines:
		widest = maxf(widest, font.get_string_size(l[0], HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x)
	var x := area.position.x + 40.0 * s
	var y := area.position.y + area.size.y * 0.14
	var pad := 12.0 * s
	var box := Rect2(Vector2(x - pad, y - pad), Vector2(widest + 2.0 * pad + 18.0 * s, lh * lines.size() + 2.0 * pad))
	draw_rect(box, Color(0.04, 0.04, 0.06, 0.78 * a))
	draw_rect(Rect2(box.position, Vector2(box.size.x, maxf(1.0, 2.0 * s))), Color(0.94, 0.85, 0.5, 0.9 * a))
	for k in range(lines.size()):
		var chosen: bool = open and int(lines[k][1]) >= 0 and int(lines[k][1]) == row
		var colour := Color(1.0, 0.85, 0.44, a) if chosen else Color(0.91, 0.89, 0.85, a)
		var at := Vector2(x + 18.0 * s, y + lh * (k + 1) - 5.0 * s)
		if chosen:
			draw_string(font, Vector2(x, at.y), ">", HORIZONTAL_ALIGNMENT_LEFT, -1, fs, colour)
		draw_string(font, at, String(lines[k][0]), HORIZONTAL_ALIGNMENT_LEFT, -1, fs, colour)
