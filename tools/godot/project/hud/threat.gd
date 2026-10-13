extends Control
# threat.gd - who is attacking from where the player cannot see it.
#
# Overhead: enemies that are after the player and outside the picture get a red wedge on a
# ring round the character, pointing at them.  In the close views (third and first person)
# everything outside the cone of sight counts - an attacker beside or behind the player -
# and the wedges sit round the middle of the picture; "up" is ahead, "down" is behind.
# A wedge pulses while its enemy is in an attack.
#
# Until the controls side supplies "who is attacking from behind", this is derived from the
# creatures' own targets (their target handle is the player) and their positions.

const Style := preload("res://hud/style.gd")
const Hud := preload("res://hud/hud.gd")

var hud: Node
var wedges: Array = []                  # {angle (screen, radians, 0 = right, y down), attacking, near 0..1, alpha}
var by_uid := {}
var hits: Array = []                    # where the last hits came from: {angle, born, heavy}


func tick() -> void:
	wedges.clear()
	var me: Dictionary = hud.me
	if me.is_empty() or not me.get("alive", false):
		if not by_uid.is_empty() or not hits.is_empty():
			by_uid.clear()
			hits.clear()
			queue_redraw()
		return
	var view: Dictionary = hud.frame.get("view", {})
	var yaw: float = view.get("yaw", 0.0)
	var fx := cos(yaw)
	var fy := sin(yaw)
	var close: bool = hud.layout != Hud.LAYOUT_OVERHEAD
	# a hit taken: where it came from (the reader gives the attacker's place), shown for a moment in the close views
	for e in hud.events:
		if e.kind == 2 and e.slot == me.slot and close:
			var from: Vector3 = e.position
			var hx: float = from.x - me.position.x
			var hy: float = from.y - me.position.y
			if hx * hx + hy * hy > 4.0:
				hits.append({"angle": atan2(-(hx * fx + hy * fy), hx * fy - hy * fx), "born": hud.now, "heavy": e.heavy})
	while not hits.is_empty() and hud.now - hits[0].born > 0.7:
		hits.pop_front()
	var threats: Array = hud.controls.get("threats", []) if close else []
	if not threats.is_empty():
		# the controls side knows the attackers and their bearing from the look (degrees, right positive, beyond 90 behind)
		for t in threats:
			if t.get("targets_me", false) and not t.get("in_view", false):
				wedges.append({"angle": deg_to_rad(float(t.get("bearing", 0.0))) - PI * 0.5, "attacking": t.get("attacking", false),
					"near": clampf(1.0 - float(t.get("distance", 900.0)) / 900.0, 0.0, 1.0), "alpha": 1.0})
		queue_redraw()
		return
	var c: PackedFloat32Array = hud.creatures
	var origin: Vector3 = me.position
	var seen := {}
	for k in range(c.size() / Hud.C_STRIDE):
		var o := k * Hud.C_STRIDE
		var flags := int(c[o + Hud.C_FLAGS])
		if (flags & Hud.CF_AGGRO) == 0 or (flags & (Hud.CF_DEAD | Hud.CF_INERT)) != 0 or int(c[o + Hud.C_TARGET_SLOT]) != int(me.slot):
			continue
		var dx: float = c[o + Hud.C_WX] - origin.x
		var dy: float = c[o + Hud.C_WY] - origin.y
		var right: float = dx * fy - dy * fx
		var ahead: float = dx * fx + dy * fy
		var dist: float = sqrt(dx * dx + dy * dy)
		var hidden: bool
		if close:
			hidden = ahead < dist * 0.45         # outside a cone of about 63 degrees to either side
		else:
			hidden = (flags & Hud.CF_ONSCREEN) == 0
		var uid := int(c[o + Hud.C_UID])
		var alpha: float = by_uid.get(uid, 0.0)
		alpha = move_toward(alpha, 1.0 if hidden else 0.0, hud.dt / 0.15)
		if alpha > 0.0:
			seen[uid] = alpha
			wedges.append({"angle": atan2(-ahead, right), "attacking": (flags & Hud.CF_ATTACKING) != 0, "near": clampf(1.0 - dist / 900.0, 0.0, 1.0), "alpha": alpha})
	var had := not by_uid.is_empty()
	by_uid = seen
	if had or not wedges.is_empty() or not hits.is_empty():
		queue_redraw()


# overhead: an arrow at the edge of the picture where the attacker is beyond it
func _edges(s: float) -> void:
	var from: Vector2 = hud.picture.get_center()
	var sc: Vector3 = hud.me.screen
	if sc.z > 1.0:
		from = hud.to_window(sc.x, sc.y) + Vector2(0, 50.0 * s)
	var box: Rect2 = hud.picture.grow_individual(-64.0 * s, -150.0 * s, -64.0 * s, -150.0 * s)     # clear of the bars at the top and the frames at the bottom
	if hud.slots_top > 0.0 and hud.slots_top - 24.0 * s < box.end.y:
		box.size.y = maxf(40.0, hud.slots_top - 24.0 * s - box.position.y)
	from = from.clamp(box.position + Vector2(8, 8), box.end - Vector2(8, 8))
	for w in wedges:
		var dir := Vector2(cos(w.angle), sin(w.angle))
		# where the ray from the character leaves the box
		var t := 1e9
		if dir.x > 0.0001: t = minf(t, (box.end.x - from.x) / dir.x)
		if dir.x < -0.0001: t = minf(t, (box.position.x - from.x) / dir.x)
		if dir.y > 0.0001: t = minf(t, (box.end.y - from.y) / dir.y)
		if dir.y < -0.0001: t = minf(t, (box.position.y - from.y) / dir.y)
		var p := from + dir * t
		var a: float = w.alpha * (0.6 + 0.4 * w.near)
		if w.attacking:
			a *= 0.7 + 0.3 * sin(hud.now * 14.0)
		var side := Vector2(-dir.y, dir.x)
		var size: float = (15.0 + 7.0 * w.near) * s
		draw_circle(p - dir * size * 0.2, size * 1.25, Color(0, 0, 0, 0.42 * a))
		draw_arc(p - dir * size * 0.2, size * 1.25, 0, TAU, 28, Color(Style.DANGER, 0.75 * a), maxf(1.0, 1.5 * s), true)
		draw_colored_polygon(PackedVector2Array([p + dir * size * 0.75, p - dir * size * 0.75 + side * size * 0.7, p - dir * size * 0.35, p - dir * size * 0.75 - side * size * 0.7]),
			Color(Style.DANGER, a))


func _draw() -> void:
	var t0: int = hud.draw_begin()
	if not hits.is_empty():
		# a hit: a bright flare on the ring, the way it came from
		var centre: Vector2 = hud.picture.get_center()
		var radius: float = minf(hud.picture.size.x, hud.picture.size.y) * 0.30
		for h in hits:
			var age: float = (hud.now - h.born) / 0.7
			var a: float = (1.0 - age) * (1.0 - age)
			var spread: float = 0.38 if h.heavy else 0.26
			draw_arc(centre, radius - 10.0 * hud.s * age, h.angle - spread, h.angle + spread, 16, Color(1.0, 0.85, 0.80, 0.9 * a), (12.0 if h.heavy else 8.0) * hud.s, true)
	if not wedges.is_empty():
		var s: float = hud.s
		var close: bool = hud.layout != Hud.LAYOUT_OVERHEAD
		var centre: Vector2 = hud.picture.get_center()
		var radius: float = minf(hud.picture.size.x, hud.picture.size.y) * 0.30
		if not close:
			_edges(s)
			hud.draw_end(t0)
			return
		for w in wedges:
			var a: float = w.alpha * (0.55 + 0.45 * w.near)
			if w.attacking:
				a *= 0.7 + 0.3 * sin(hud.now * 14.0)
			var dir := Vector2(cos(w.angle), sin(w.angle))
			var side := Vector2(-dir.y, dir.x)
			# an arc of the ring and a solid arrow head on it, pointing outward at the attacker
			var spread: float = 0.16 + 0.10 * w.near
			draw_arc(centre, radius, w.angle - spread, w.angle + spread, 12, Color(0, 0, 0, 0.5 * a), 9.0 * s, true)
			draw_arc(centre, radius, w.angle - spread, w.angle + spread, 12, Color(Style.DANGER, 0.9 * a), 5.0 * s, true)
			var tip := centre + dir * (radius + 22.0 * s)
			var base := centre + dir * (radius + 5.0 * s)
			var half: float = 11.0 * s
			draw_colored_polygon(PackedVector2Array([tip + dir * 2.0 * s, base + side * (half + 2.0 * s), base - side * (half + 2.0 * s)]), Color(0, 0, 0, 0.5 * a))
			draw_colored_polygon(PackedVector2Array([tip, base + side * half, base - side * half]), Color(Style.DANGER, 0.95 * a))
	hud.draw_end(t0)
