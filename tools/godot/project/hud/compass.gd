extends Control
# compass.gd - where things are: the radar of the overhead layout (upper right: enemies,
# friends, the other players, the objective the game's own compass points at, the way the
# character faces) and the compass strip of the close views (upper middle: the cardinal
# points, the objective with its distance, enemies that are after the player).
# It turns with the camera, so it is drawn every frame; it is small.

const Style := preload("res://hud/style.gd")
const Hud := preload("res://hud/hud.gd")

const RADAR_REACH := 900.0

var hud: Node


func tick() -> void:
	if not hud.me.is_empty():
		queue_redraw()


func _draw() -> void:
	var t0: int = hud.draw_begin()
	if not hud.me.is_empty():
		var s: float = hud.s
		var area: Rect2 = hud.area
		if hud.layout != Hud.LAYOUT_OVERHEAD:
			_compass_strip(Vector2(area.get_center().x, area.position.y + 14.0 * s), s)
		elif hud.setting.radar:
			_radar(Vector2(area.end.x - 78.0 * s, area.position.y + 78.0 * s), 70.0 * s, s)
	hud.draw_end(t0)


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
