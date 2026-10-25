extends Control
# world.gd - what belongs to places in the world: health bars above enemies' heads, name
# tags of the other players, and the numbers that float up where something was hit or healed.
#
# A bar appears for an enemy that is hurt, is after a player, or is the one a player's
# attack is aimed at; it fades out a few seconds after the creature calms down.  Bosses and
# the targeted enemy get the large bar at the top as well (top.gd).  Bars ease to their
# value and leave a pale trail of what was just lost.

const Style := preload("res://hud/style.gd")
const Hud := preload("res://hud/hud.gd")

const LINGER := 4.0                     # seconds a bar stays after the last reason to show it
const FLOAT_TIME := 1.05                # a floating number's life

var hud: Node
var bars := {}                          # uid -> {shown, ghost, hit_at, alpha, seen, keep_until}
var floats: Array = []                  # {world: Vector3, text, colour, size, born, dx, heavy}
var column := 0
var was_busy := false


func tick() -> void:
	var c: PackedFloat32Array = hud.creatures
	var now: float = hud.now
	var n := c.size() / Hud.C_STRIDE
	for k in range(n):
		var o := k * Hud.C_STRIDE
		var uid := int(c[o + Hud.C_UID])
		var flags := int(c[o + Hud.C_FLAGS])
		var b = bars.get(uid)
		var frac: float = clampf(c[o + Hud.C_HP] / maxf(c[o + Hud.C_MAX], 0.001), 0.0, 1.0)
		var wanted: bool = (flags & Hud.CF_HOSTILE) != 0 and (flags & (Hud.CF_DEAD | Hud.CF_INERT)) == 0 \
			and (frac < 0.999 or (flags & (Hud.CF_AGGRO | Hud.CF_TARGETED | Hud.CF_ATTACKING | Hud.CF_MINIBOSS)) != 0)
		if b == null:
			if not wanted:
				continue
			b = {"shown": frac, "ghost": frac, "hit_at": -10.0, "alpha": 0.0, "keep_until": 0.0, "seen": 0}
			bars[uid] = b
		b.seen = hud.cost_frames
		if wanted:
			b.keep_until = now + LINGER
		if frac < b.shown - 0.0005:
			b.hit_at = now
		b.shown = move_toward(b.shown, frac, maxf(absf(b.shown - frac) * 14.0, 0.25) * hud.dt)
		if now - b.hit_at > 0.35:
			b.ghost = move_toward(b.ghost, b.shown, 1.2 * hud.dt)
		b.ghost = maxf(b.ghost, b.shown)
		var dead: bool = (flags & Hud.CF_DEAD) != 0
		var target: float = 1.0 if (now < b.keep_until and not dead) else 0.0
		b.alpha = move_toward(b.alpha, target, hud.dt / (0.15 if target > 0.0 else (0.45 if dead else 0.6)))
	if bars.size() > 0:
		for uid in bars.keys():
			var b = bars[uid]
			if b.seen != hud.cost_frames:
				b.alpha = move_toward(b.alpha, 0.0, hud.dt / 0.25)       # out of reach or gone
				if b.alpha <= 0.0:
					bars.erase(uid)
	# events -> floating numbers
	if hud.setting.numbers:
		for e in hud.events:
			_event(e)
	var k := 0
	while k < floats.size():
		if now - floats[k].born > FLOAT_TIME:
			floats.remove_at(k)
		else:
			k += 1
	# drawn again only while there is something of the world to draw (or it has just gone)
	var others := false
	for pl in hud.players:
		if pl.get("present", false) and not pl.get("local", false):
			others = true
	var busy: bool = bars.size() > 0 or floats.size() > 0 or others or (hud.layout != Hud.LAYOUT_OVERHEAD and not hud.me.is_empty())
	if busy or was_busy:
		queue_redraw()
	was_busy = busy


func _event(e: Dictionary) -> void:
	var kind: int = e.kind
	var text := ""
	var colour := Style.DAMAGE_OUT
	var size := 22.0
	var where: Vector3 = e.position
	match kind:
		1:      # damage dealt
			if e.amount < 0.5:
				return
			text = Style.number(e.amount)
			if e.heavy:
				colour = Style.DAMAGE_BIG
				size = 30.0
		2:      # damage taken
			if e.amount < 0.5:
				return
			text = "-" + Style.number(e.amount)
			colour = Style.DAMAGE_IN
			size = 26.0 if e.heavy else 21.0
		3:      # heal
			if e.amount < 0.5:
				return
			text = "+" + Style.number(e.amount)
			colour = Style.HEAL
		4:
			text = "miss"
			colour = Style.TEXT_DIM
			size = 18.0
		5:
			text = "+%s XP" % Style.number(e.amount)
			colour = Style.XP_TEXT
			size = 19.0
		_:
			return
	column = (column + 1) % 5
	floats.append({"world": where, "text": text, "colour": colour, "size": size, "born": hud.now, "dx": (column - 2) * 13.0,
		"heavy": e.heavy, "rise": 1.0 if kind != 2 else 0.8})
	if floats.size() > 40:
		floats.pop_front()


# test aid: "app hud test number TEXT" puts a number over the local player
func test(w: Array) -> void:
	if w.size() >= 2 and str(w[0]) == "number" and not hud.me.is_empty():
		floats.append({"world": hud.me.position + Vector3(0, 0, hud.me.height), "text": str(w[1]), "colour": Style.DAMAGE_BIG, "size": 30.0, "born": hud.now,
			"dx": 0.0, "heavy": true, "rise": 1.0})


func _draw() -> void:
	var t0: int = hud.draw_begin()
	var s: float = hud.s
	var c: PackedFloat32Array = hud.creatures
	var n := c.size() / Hud.C_STRIDE
	var first_person: bool = hud.layout == Hud.LAYOUT_FIRST
	for k in range(n):
		var o := k * Hud.C_STRIDE
		var b = bars.get(int(c[o + Hud.C_UID]))
		if b == null or b.alpha <= 0.01 or c[o + Hud.C_SZ] <= 1.0:
			continue
		var flags := int(c[o + Hud.C_FLAGS])
		if (flags & Hud.CF_BOSS) != 0:
			continue                    # the boss has the large bar
		var p: Vector2 = hud.to_window(c[o + Hud.C_SX], c[o + Hud.C_SY])
		if not hud.picture.grow(40.0).has_point(p):
			continue
		# nearer creatures get slightly larger bars in a close view; overhead they are all alike
		var near: float = clampf(380.0 / maxf(c[o + Hud.C_SZ], 60.0), 0.7, 1.5) if hud.layout != Hud.LAYOUT_OVERHEAD else 1.0
		var mini: bool = (flags & Hud.CF_MINIBOSS) != 0
		var targeted: bool = (flags & Hud.CF_TARGETED) != 0
		var w: float = (96.0 if mini else 68.0) * s * near
		var h: float = (9.0 if mini else 7.0) * s * near
		var rect := Rect2((p + Vector2(-w * 0.5, -h - 6.0 * s)).round(), Vector2(w, h).round())
		var a: float = b.alpha * _haze_left(c, o)
		if a <= 0.02:
			continue                    # lost in the haze or beyond the drawn distance: no body is seen, so no bar
		if targeted:
			draw_rect(rect.grow(3.0 * s), Color(1, 1, 1, 0.55 * a), false, maxf(1.0, 1.5 * s))
		Style.bar(self, rect, b.shown, b.ghost, Style.BOSS_A if mini else Style.ENEMY_A, Style.BOSS_B if mini else Style.ENEMY_B, s, a)
		if mini or targeted:
			Style.text(self, rect.position + Vector2(w * 0.5, -5.0 * s), Style.pretty(hud.creature_name(k)), 14.0 * s * near, Color(Style.TEXT, a), 1, true)
	# the other players: a name and a thin bar above their heads
	var count: int = hud.players.size()
	for slot in range(count):
		var pl: Dictionary = hud.players[slot]
		if not pl.get("present", false) or pl.get("local", false) or not pl.get("alive", false):
			continue
		var sc: Vector3 = pl.screen
		if sc.z <= 1.0:
			continue
		var p: Vector2 = hud.to_window(sc.x, sc.y)
		if not hud.picture.has_point(p):
			continue
		var w: float = 64.0 * s
		var rect := Rect2((p + Vector2(-w * 0.5, -5.0 * s - 6.0 * s)).round(), Vector2(w, 5.0 * s).round())
		Style.bar(self, rect, pl.health / maxf(pl.health_max, 0.001), 0.0, Style.PARTY.darkened(0.25), Style.PARTY, s, 0.95)
		Style.text(self, rect.position + Vector2(w * 0.5, -5.0 * s), pl.name, 14.0 * s, Style.TEXT, 1, true)
	# floating numbers: pop, rise, fade
	for f in floats:
		var age: float = (hud.now - f.born) / FLOAT_TIME
		var sc: Vector3 = hud.project(f.world)
		if sc.z <= 1.0:
			continue
		var p: Vector2 = hud.to_window(sc.x, sc.y)
		var pop: float = 1.0 + 0.45 * maxf(0.0, 1.0 - age / 0.14)
		var a: float = clampf((1.0 - age) / 0.32, 0.0, 1.0)
		p += Vector2(f.dx * s, (-18.0 - 58.0 * Style.ease_out(age) * f.rise) * s)
		var col: Color = f.colour
		col.a = a
		Style.text(self, p, f.text, f.size * s * pop, col, 1, true)
	if hud.layout != Hud.LAYOUT_OVERHEAD and not hud.me.is_empty():
		_aim(s, first_person)
	hud.draw_end(t0)


# The close views: which enemy a swing or a shot would take, and a dot where the view looks.
# The controls side knows it by the simulation's own rules (fpcontrols::Hud: locked, shot, melee, reticle); without
# that data the creature the simulation holds now is marked (the player's own target), else the nearest enemy close
# to the middle of the view.
func _aim(s: float, first_person: bool) -> void:
	var c: PackedFloat32Array = hud.creatures
	var mark := Vector3.ZERO
	var have := false
	var locked := false
	var reticle := first_person
	var ctl: Dictionary = hud.controls
	if not ctl.is_empty():
		reticle = ctl.get("reticle", false)
		for key in ["locked", "shot", "melee"]:
			var m: Dictionary = ctl.get(key, {})
			if key == "shot" and not ctl.get("ranged", false):
				continue
			if m.get("valid", false):
				mark = hud.project(Vector3(m.x, m.y, m.z))
				have = mark.z > 1.0
				locked = key == "locked"
				break
	else:
		var best := 1e9
		for k in range(c.size() / Hud.C_STRIDE):
			var o := k * Hud.C_STRIDE
			var flags := int(c[o + Hud.C_FLAGS])
			if (flags & Hud.CF_HOSTILE) == 0 or (flags & (Hud.CF_DEAD | Hud.CF_INERT)) != 0 or c[o + Hud.C_SZ] <= 1.0:
				continue
			var is_locked := (flags & Hud.CF_TARGETED) != 0
			var off: float = Vector2(c[o + Hud.C_SX] - 0.5, (c[o + Hud.C_SY] - 0.5) * 0.6).length()
			if not is_locked and (off > 0.16 or c[o + Hud.C_SZ] > 420.0 or not first_person):
				continue
			var score: float = -1.0 if is_locked else off
			if score < best:
				best = score
				mark = hud.project(Vector3(c[o + Hud.C_WX], c[o + Hud.C_WY], c[o + Hud.C_WZ] + c[o + Hud.C_HEIGHT] * 0.45))
				have = mark.z > 1.0
				locked = is_locked
	if have:
		# four corners round the enemy's middle; bright while the simulation holds it, pale while it is only what would be taken
		var p: Vector2 = hud.to_window(mark.x, mark.y)
		var half: float = clampf(9000.0 / maxf(mark.z, 40.0), 14.0, 90.0) * s
		var arm: float = half * 0.38
		var col := Color(1.0, 0.92, 0.55, 0.95) if locked else Color(1, 1, 1, 0.55)
		var w: float = maxf(1.5, 2.2 * s)
		for sx in [-1.0, 1.0]:
			for sy in [-1.0, 1.0]:
				var corner := p + Vector2(sx, sy) * half
				draw_line(corner, corner - Vector2(sx * arm, 0), col, w, true)
				draw_line(corner, corner - Vector2(0, sy * arm), col, w, true)
	if reticle:
		# a small dot where the view looks: enough to aim a bow by
		var centre: Vector2 = hud.picture.get_center()
		draw_circle(centre, 3.2 * s, Color(0, 0, 0, 0.55))
		draw_circle(centre, 1.9 * s, Color(1, 1, 1, 0.9))


# how much of a creature the haze leaves visible (scene_view.gd _haze hands its range over as Engine meta "rta_haze":
# [start, end, amount, eye, far]); 1 when there is no such scene (the plain picture of the game)
func _haze_left(c: PackedFloat32Array, o: int) -> float:
	if not Engine.has_meta("rta_haze"):
		return 1.0
	var hz: Array = Engine.get_meta("rta_haze")
	var eye: Vector3 = hz[3]
	var d := eye.distance_to(Vector3(c[o + Hud.C_WX], c[o + Hud.C_WY], c[o + Hud.C_WZ]))
	if d > float(hz[4]) * 0.92:
		return 0.0
	var fog: float = float(hz[2]) * smoothstep(float(hz[0]), float(hz[1]), d)
	return clampf((1.0 - fog - 0.25) / 0.55, 0.0, 1.0)     # gone a little before the body is (the haze is full at 1)
