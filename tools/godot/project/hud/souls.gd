extends Control
# souls.gd - the souls-style combat mode's part of the HUD (tools/recomp/app/soulscombat.h,
# docs/issues/native-souls-combat.md): the stamina bar under the middle of the picture, a frame
# round it during a dodge's invulnerable ticks, red while the guard is broken; and the lock-on
# marker on the locked creature with its health.
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
const STAMINA_MAX := 10000.0        # soulscombat::Tuning::stamina_max

var hud: Node
var on := false
var stamina := 1.0
var shown := 1.0
var flags := 0
var lock := false
var lock_at := Vector3.ZERO
var lock_hp := 0.0
var lock_max := 0.0


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
