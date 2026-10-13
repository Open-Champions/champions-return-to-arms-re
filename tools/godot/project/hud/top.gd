extends Control
# top.gd - the upper part of the picture: the large bar of the boss and of the enemy the
# player's attack is aimed at, the radar (overhead) or the compass strip (close views) with
# the objective's direction, the game's own one-line message, the name of a level on entry,
# the level-up banner, and what the network has to say (stalls, a desync, chat).

const Style := preload("res://hud/style.gd")
const Hud := preload("res://hud/hud.gd")

const FOCUS_LINGER := 3.5
const RADAR_REACH := 900.0

var hud: Node
var focus_uid := 0                      # the enemy shown in the target frame
var focus_until := 0.0
var focus_name := ""
var focus := {"hp": 0.0, "max": 1.0, "shown": 1.0, "ghost": 1.0, "hit_at": -10.0, "alpha": 0.0, "mini": false}
var boss := {"uid": 0, "name": "", "hp": 0.0, "max": 1.0, "shown": 1.0, "ghost": 1.0, "hit_at": -10.0, "alpha": 0.0}
var message := ""
var message_alpha := 0.0
var level_seen := ""
var level_at := -100.0
var level_title := ""
var levelup_at := -100.0
var levelup_level := 0
var chat: Array = []
var test_notice := 0
var test_chat: Array = []


func test(w: Array) -> void:
	# pictures of states a run without a network cannot reach; what they show is marked as test data
	if w.size() >= 2 and str(w[0]) == "notice":
		test_notice = str(w[1]).to_int()
	elif w.size() >= 2 and str(w[0]) == "chat":
		test_chat.append([1, "TEST DATA 2: " + " ".join(PackedStringArray(w.slice(1)))])


func tick() -> void:
	var c: PackedFloat32Array = hud.creatures
	var n := c.size() / Hud.C_STRIDE
	var now: float = hud.now
	# which enemy the target frame is about: the one the local player's attack is aimed at, kept a while after
	var target_uid: int = hud.me.get("target_uid", 0)
	var boss_index := -1
	var focus_index := -1
	var boss_best := 1e30
	for k in range(n):
		var o := k * Hud.C_STRIDE
		var flags := int(c[o + Hud.C_FLAGS])
		var uid := int(c[o + Hud.C_UID])
		if (flags & Hud.CF_BOSS) != 0 and (flags & (Hud.CF_DEAD | Hud.CF_INERT)) == 0 and (flags & Hud.CF_HOSTILE) != 0:
			var d: float = c[o + Hud.C_SZ] if uid != int(hud.frame.get("boss_uid", 0)) else -1.0
			if d < boss_best:
				boss_best = d
				boss_index = k
		if uid == target_uid and target_uid != 0 and (flags & Hud.CF_HOSTILE) != 0:
			focus_uid = uid
			focus_until = now + FOCUS_LINGER
		if uid == focus_uid:
			focus_index = k
	if boss_index >= 0:
		var o := boss_index * Hud.C_STRIDE
		var uid := int(c[o + Hud.C_UID])
		if boss.uid != uid:
			boss.uid = uid
			boss.shown = clampf(c[o + Hud.C_HP] / maxf(c[o + Hud.C_MAX], 0.001), 0.0, 1.0)
			boss.ghost = boss.shown
		boss.name = Style.pretty(hud.creature_name(boss_index))
		boss.hp = c[o + Hud.C_HP]
		boss.max = c[o + Hud.C_MAX]
		_ease(boss, 1.0)
	else:
		_ease(boss, 0.0)
	if focus_index >= 0 and now < focus_until and focus_uid != boss.uid:
		var o := focus_index * Hud.C_STRIDE
		var flags := int(c[o + Hud.C_FLAGS])
		focus.hp = c[o + Hud.C_HP]
		focus.max = c[o + Hud.C_MAX]
		focus.mini = (flags & Hud.CF_MINIBOSS) != 0
		focus_name = Style.pretty(hud.creature_name(focus_index))
		if focus.alpha <= 0.0:
			focus.shown = clampf(focus.hp / maxf(focus.max, 0.001), 0.0, 1.0)
			focus.ghost = focus.shown
		if (flags & Hud.CF_DEAD) != 0:
			focus_until = minf(focus_until, now + 0.6)
		_ease(focus, 1.0)
	else:
		if focus_index < 0:
			focus.hp = 0.0 if focus.alpha > 0.0 and now < focus_until else focus.hp
		_ease(focus, 0.0)
		if focus.alpha <= 0.0:
			focus_uid = 0
	# the game's own message
	var text: String = hud.frame.get("message", "") if hud.ok else ""
	if text != "":
		message = text
		message_alpha = move_toward(message_alpha, 1.0, hud.dt / 0.15)
	else:
		message_alpha = move_toward(message_alpha, 0.0, hud.dt / 0.4)
	# a level's name when it is entered
	if hud.ok and (hud.phase & Hud.PH_LEVEL) != 0:
		var level: String = hud.frame.get("level", "")
		if level != level_seen and hud.show > 0.5:
			level_seen = level
			level_title = hud.frame.get("level_title", "")
			level_at = now
	for e in hud.events:
		if e.kind == 7 and hud.players[e.slot].get("local", false):
			levelup_at = now
			levelup_level = int(e.amount)
	chat = hud.frame.get("chat", []) if hud.ok else []
	if not test_chat.is_empty():
		chat = chat + test_chat
	queue_redraw()                      # the radar turns with the camera: this piece is drawn every frame


func _ease(b: Dictionary, target_alpha: float) -> void:
	var frac: float = clampf(b.hp / maxf(b.max, 0.001), 0.0, 1.0)
	if frac < b.shown - 0.0005:
		b.hit_at = hud.now
	b.shown = move_toward(b.shown, frac, maxf(absf(b.shown - frac) * 12.0, 0.2) * hud.dt)
	if hud.now - b.hit_at > 0.4:
		b.ghost = move_toward(b.ghost, b.shown, 0.8 * hud.dt)
	b.ghost = maxf(b.ghost, b.shown)
	b.alpha = move_toward(b.alpha, target_alpha, hud.dt / (0.18 if target_alpha > 0.0 else 0.5))


func _draw() -> void:
	var t0: int = hud.draw_begin()
	var s: float = hud.s
	var area: Rect2 = hud.area
	var cx: float = area.get_center().x
	var y: float = area.position.y
	var strip: bool = hud.layout != Hud.LAYOUT_OVERHEAD
	if not hud.me.is_empty():
		if strip:
			_compass_strip(Vector2(cx, y + 14.0 * s), s)
			y += 44.0 * s
		elif hud.setting.radar:
			_radar(Vector2(area.end.x - 78.0 * s, area.position.y + 78.0 * s), 70.0 * s, s)
	# boss
	if boss.alpha > 0.01:
		var w: float = minf(600.0 * s, area.size.x * 0.56)
		var a: float = boss.alpha
		Style.text(self, Vector2(cx, y + 20.0 * s), boss.name, 22.0 * s, Color(Style.TEXT, a), 1, true)
		var rect := Rect2(Vector2(cx - w * 0.5, y + 30.0 * s).round(), Vector2(w, 18.0 * s).round())
		Style.bar(self, rect, boss.shown, boss.ghost, Style.BOSS_A, Style.BOSS_B, s, a)
		for side in [-1.0, 1.0]:
			var d := Vector2(cx + side * (w * 0.5 + 14.0 * s), rect.get_center().y)
			Style.glyph(self, 11, d, 9.0 * s, Color(Style.BOSS_B, a))
		Style.text(self, Vector2(cx, rect.position.y + 14.0 * s), "%s / %s" % [Style.number(boss.hp), Style.number(boss.max)], 13.0 * s, Color(Style.TEXT, a), 1, true)
		y += 62.0 * s
	# the targeted enemy
	if focus.alpha > 0.01:
		var w: float = minf(420.0 * s, area.size.x * 0.42)
		var a: float = focus.alpha
		Style.text(self, Vector2(cx, y + 18.0 * s), focus_name, 18.0 * s, Color(Style.TEXT, a), 1, true)
		var rect := Rect2(Vector2(cx - w * 0.5, y + 26.0 * s).round(), Vector2(w, 14.0 * s).round())
		Style.bar(self, rect, focus.shown, focus.ghost, Style.BOSS_A if focus.mini else Style.ENEMY_A, Style.BOSS_B if focus.mini else Style.ENEMY_B, s, a)
		Style.text(self, Vector2(cx, rect.position.y + 11.5 * s), "%s / %s" % [Style.number(focus.hp), Style.number(focus.max)], 12.0 * s, Color(Style.TEXT, a), 1, true)
		y += 52.0 * s
	# the game's own message
	if message_alpha > 0.01:
		var size: float = 19.0 * s
		var w: float = Style.text_width(message, size, true) + 36.0 * s
		var rect := Rect2(Vector2(cx - w * 0.5, y + 14.0 * s).round(), Vector2(w, 36.0 * s).round())
		Style.panel(self, rect, s, message_alpha, 18.0)
		Style.text(self, Vector2(cx, rect.position.y + 24.5 * s), message, size, Color(Style.TEXT, message_alpha), 1, true)
		y += 56.0 * s
	# entering a level: its name for a few seconds
	var age: float = hud.now - level_at
	if age < 4.5 and level_title != "":
		var a: float = clampf(age / 0.4, 0.0, 1.0) * clampf((4.5 - age) / 0.8, 0.0, 1.0)
		var at := Vector2(cx, area.position.y + area.size.y * 0.22)
		Style.text(self, at, level_title, 40.0 * s, Color(Style.TEXT, a), 1, true)
		var half: float = Style.text_width(level_title, 40.0 * s, true) * 0.5 * Style.ease_out(age / 0.8)
		draw_line(at + Vector2(-half, 14.0 * s), at + Vector2(half, 14.0 * s), Color(Style.XP_B, 0.8 * a), maxf(1.0, 2.0 * s), true)
	# level up
	age = hud.now - levelup_at
	if age < 3.2:
		var a: float = clampf(age / 0.2, 0.0, 1.0) * clampf((3.2 - age) / 0.7, 0.0, 1.0)
		var pop: float = 1.0 + 0.25 * maxf(0.0, 1.0 - age / 0.25)
		var at := Vector2(cx, area.position.y + area.size.y * 0.30)
		Style.text(self, at, "LEVEL %d" % levelup_level, 46.0 * s * pop, Color(Style.XP_B, a), 1, true)
		Style.text(self, at + Vector2(0, 30.0 * s), "Level up", 18.0 * s, Color(Style.TEXT, a), 1, true)
	_network(s)
	hud.draw_end(t0)


func _network(s: float) -> void:
	var area: Rect2 = hud.area
	var notice: int = hud.frame.get("net_notice", 0) if hud.ok else 0
	var made_up := false
	if test_notice > 0:
		notice = test_notice
		made_up = true
	if notice > 0:
		var who := ""
		var slot: int = hud.frame.get("net_notice_slot", -1)
		if slot >= 0 and slot < hud.players.size() and hud.players[slot].get("present", false):
			who = hud.players[slot].name
		var text := ""
		var colour := Style.WARN
		match notice:
			1: text = "Waiting for the other players"
			2:
				text = ("%s is out of sync" % who) if who != "" else "A player is out of sync"
				colour = Style.DANGER
			3:
				text = "The characters no longer match (checksum)"
				colour = Style.DANGER
			4: text = "Leaving the game"
			5:
				text = "Connection lost"
				colour = Style.DANGER
		if made_up:
			text += "   (TEST DATA)"
		var size: float = 17.0 * s
		var w: float = Style.text_width(text, size, true) + 52.0 * s
		var rect := Rect2(Vector2(area.get_center().x - w * 0.5, area.position.y + area.size.y * 0.16).round(), Vector2(w, 34.0 * s).round())
		Style.rounded(self, rect, 17.0 * s, Color(0.05, 0.05, 0.07, 0.86), Color(colour, 0.9), maxi(1, int(round(1.5 * s))))
		var pulse: float = 0.6 + 0.4 * sin(hud.now * 6.0)
		draw_circle(rect.position + Vector2(18.0, 17.0) * s, 5.0 * s, Color(colour, pulse))
		Style.text(self, rect.position + Vector2(32.0 * s, 23.0 * s), text, size, Style.TEXT, 0, true)
	# chat: the newest lines, above the player's frame on the left
	if not chat.is_empty():
		var x: float = area.position.x
		var y: float = area.end.y - (104.0 + 62.0 + 3.0 * 58.0 + 14.0) * s
		var first: int = maxi(0, chat.size() - 5)
		for k in range(chat.size() - 1, first - 1, -1):
			var line: Array = chat[k]
			var text: String = line[1]
			var w: float = Style.text_width(text, 15.0 * s) + 20.0 * s
			Style.rounded(self, Rect2(Vector2(x, y - 20.0 * s), Vector2(w, 26.0 * s)), 6.0 * s, Color(0.04, 0.05, 0.07, 0.66))
			draw_rect(Rect2(Vector2(x, y - 16.0 * s), Vector2(3.0 * s, 18.0 * s)), Style.PARTY)
			Style.text(self, Vector2(x + 10.0 * s, y - 1.0 * s), text, 15.0 * s, Style.TEXT)
			y -= 30.0 * s


# ---- where things are ---------------------------------------------------------------------------
# The ground plane as the camera sees it: +y of the result is "up the screen" (ahead of the camera).
func _ground(d: Vector3) -> Vector2:
	var view: Dictionary = hud.frame.get("view", {})
	var yaw: float = view.get("yaw", 0.0)
	var fx := cos(yaw)
	var fy := sin(yaw)
	return Vector2(d.x * fy - d.y * fx, d.x * fx + d.y * fy)       # (to the right, ahead)


func _radar(c: Vector2, r: float, s: float) -> void:
	draw_circle(c, r + 3.0 * s, Color(0, 0, 0, 0.45))
	draw_circle(c, r, Color(Style.INK, 0.72))
	draw_arc(c, r, 0, TAU, 64, Style.HAIRLINE, maxf(1.0, s), true)
	draw_arc(c, r * 0.5, 0, TAU, 48, Color(1, 1, 1, 0.06), maxf(1.0, s), true)
	var me: Dictionary = hud.me
	var origin: Vector3 = me.position
	# north (the world's +y) on the rim
	var north := _ground(Vector3(0, 1, 0))
	var np := c + Vector2(north.x, -north.y) * (r - 9.0 * s)
	Style.text(self, np + Vector2(0, 4.5 * s), "N", 12.0 * s, Style.TEXT_DIM, 1, true)
	var cr: PackedFloat32Array = hud.creatures
	for k in range(cr.size() / Hud.C_STRIDE):
		var o := k * Hud.C_STRIDE
		var flags := int(cr[o + Hud.C_FLAGS])
		if (flags & (Hud.CF_DEAD | Hud.CF_INERT)) != 0:
			continue
		var g := _ground(Vector3(cr[o + Hud.C_WX], cr[o + Hud.C_WY], 0) - Vector3(origin.x, origin.y, 0)) / RADAR_REACH
		var marked := (flags & 2048) != 0
		if g.length() > 1.0:
			if not marked:
				continue
			g = g.normalized()
		var p := c + Vector2(g.x, -g.y) * (r - 4.0 * s)
		if marked:
			Style.glyph(self, 11, p, 5.0 * s, Style.GOLD)
		elif (flags & Hud.CF_HOSTILE) != 0:
			var big := (flags & (Hud.CF_BOSS | Hud.CF_MINIBOSS)) != 0
			draw_circle(p, (4.2 if big else 2.8) * s, Style.ENEMY_B if (flags & Hud.CF_AGGRO) != 0 else Color(Style.ENEMY_B, 0.6))
		elif (flags & (Hud.CF_FRIENDLY | Hud.CF_NAMED)) != 0:
			draw_circle(p, 2.8 * s, Style.FRIEND)
	for pl in hud.players:
		if not pl.get("present", false) or pl.get("local", false) or not pl.get("alive", false):
			continue
		var g := _ground(pl.position - origin) / RADAR_REACH
		if g.length() > 1.0:
			g = g.normalized()
		draw_circle(c + Vector2(g.x, -g.y) * (r - 4.0 * s), 3.4 * s, Style.PARTY)
	# the objective the game's own compass points at
	if hud.frame.get("compass_on", false):
		var target: Vector3 = hud.frame.compass_target
		var g := _ground(target - origin)
		var far: float = g.length()
		var dir := Vector2(g.x, -g.y).normalized() if far > 1.0 else Vector2.UP
		var p := c + dir * minf(far / RADAR_REACH, 1.0) * (r - 4.0 * s)
		if far > RADAR_REACH:
			var tip := c + dir * (r + 9.0 * s)
			var side := Vector2(-dir.y, dir.x) * 6.0 * s
			draw_colored_polygon(PackedVector2Array([tip, c + dir * (r - 3.0 * s) + side, c + dir * (r - 3.0 * s) - side]), Style.GOLD)
		else:
			Style.glyph(self, 11, p, 6.0 * s, Style.GOLD)
	# the player: an arrow the way the character faces
	var face: float = me.facing
	var fg := _ground(Vector3(cos(face), sin(face), 0))
	var f := Vector2(fg.x, -fg.y).normalized()
	var side := Vector2(-f.y, f.x)
	draw_colored_polygon(PackedVector2Array([c + f * 7.0 * s, c - f * 5.0 * s + side * 4.5 * s, c - f * 2.5 * s, c - f * 5.0 * s - side * 4.5 * s]), Style.TEXT)


func _compass_strip(c: Vector2, s: float) -> void:
	var w: float = minf(460.0 * s, hud.area.size.x * 0.5)
	var half_span := PI * 0.5                   # the strip shows a half turn
	var rect := Rect2(c + Vector2(-w * 0.5, -11.0 * s), Vector2(w, 22.0 * s))
	Style.rounded(self, rect, 11.0 * s, Color(Style.INK, 0.6), Style.HAIRLINE, 1)
	var view: Dictionary = hud.frame.get("view", {})
	var yaw: float = view.get("yaw", 0.0)
	var names := {0: "E", 90: "N", 180: "W", 270: "S"}
	for deg in range(0, 360, 15):
		var off: float = wrapf(yaw - deg_to_rad(deg), -PI, PI)
		if absf(off) > half_span * 0.94:
			continue
		var x: float = c.x + off / half_span * w * 0.5
		var a: float = 1.0 - pow(absf(off) / half_span, 3.0)
		if names.has(deg):
			Style.text(self, Vector2(x, c.y + 5.5 * s), names[deg], 15.0 * s, Color(Style.TEXT, a), 1, true)
		else:
			draw_line(Vector2(x, c.y - (5.0 if deg % 45 == 0 else 3.0) * s), Vector2(x, c.y + (5.0 if deg % 45 == 0 else 3.0) * s), Color(1, 1, 1, 0.45 * a), maxf(1.0, s))
	draw_colored_polygon(PackedVector2Array([c + Vector2(-5.0, -15.0) * s, c + Vector2(5.0, -15.0) * s, c + Vector2(0, -9.0) * s]), Style.TEXT)
	var me: Dictionary = hud.me
	var origin: Vector3 = me.position
	var cr: PackedFloat32Array = hud.creatures
	for k in range(cr.size() / Hud.C_STRIDE):
		var o := k * Hud.C_STRIDE
		var flags := int(cr[o + Hud.C_FLAGS])
		if (flags & Hud.CF_HOSTILE) == 0 or (flags & (Hud.CF_DEAD | Hud.CF_INERT)) != 0 or (flags & (Hud.CF_AGGRO | 2048)) == 0:
			continue
		var bearing: float = atan2(cr[o + Hud.C_WY] - origin.y, cr[o + Hud.C_WX] - origin.x)
		var off: float = clampf(wrapf(yaw - bearing, -PI, PI), -half_span * 0.97, half_span * 0.97)
		draw_circle(Vector2(c.x + off / half_span * w * 0.5, c.y + 15.0 * s), 3.0 * s, Style.ENEMY_B)
	if hud.frame.get("compass_on", false):
		var target: Vector3 = hud.frame.compass_target
		var bearing: float = atan2(target.y - origin.y, target.x - origin.x)
		var off: float = clampf(wrapf(yaw - bearing, -PI, PI), -half_span * 0.97, half_span * 0.97)
		var p := Vector2(c.x + off / half_span * w * 0.5, c.y)
		Style.glyph(self, 11, p, 8.0 * s, Style.GOLD)
		var far: float = Vector2(target.x - origin.x, target.y - origin.y).length()
		Style.text(self, p + Vector2(0, 27.0 * s), "%d m" % int(far / 30.0), 12.0 * s, Style.GOLD, 1, true)
