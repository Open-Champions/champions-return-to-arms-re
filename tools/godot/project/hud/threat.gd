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


func tick() -> void:
	wedges.clear()
	var me: Dictionary = hud.me
	if me.is_empty() or not me.get("alive", false):
		if not by_uid.is_empty():
			by_uid.clear()
			queue_redraw()
		return
	var view: Dictionary = hud.frame.get("view", {})
	var yaw: float = view.get("yaw", 0.0)
	var fx := cos(yaw)
	var fy := sin(yaw)
	var close: bool = hud.layout != Hud.LAYOUT_OVERHEAD
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
	if had or not wedges.is_empty():
		queue_redraw()


func _draw() -> void:
	var t0: int = hud.draw_begin()
	if not wedges.is_empty():
		var s: float = hud.s
		var close: bool = hud.layout != Hud.LAYOUT_OVERHEAD
		var centre: Vector2 = hud.picture.get_center()
		var radius: float = minf(hud.picture.size.x, hud.picture.size.y) * 0.30
		if not close:
			var sc: Vector3 = hud.me.screen
			if sc.z > 1.0:
				centre = hud.to_window(sc.x, sc.y) + Vector2(0, 50.0 * s)
			radius = minf(hud.picture.size.x, hud.picture.size.y) * 0.36
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
