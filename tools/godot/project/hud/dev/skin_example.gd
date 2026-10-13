extends RefCounted
# skin_example.gd - a small skin, to show (and test) that the HUD's look is a swap:
# a colder palette, square flat panels with a bright edge on the left, flat bars.
# Everything it does not name is drawn by style.gd as before.
#     --hud-theme res://hud/dev/skin_example.gd        or "theme" in user://hud.cfg


func setup(style: Script) -> void:
	style.HEALTH_A = Color(0.10, 0.62, 0.36)
	style.HEALTH_B = Color(0.30, 0.86, 0.52)
	style.MANA_A = Color(0.50, 0.30, 0.86)
	style.MANA_B = Color(0.72, 0.56, 0.98)
	style.XP_A = Color(0.85, 0.85, 0.85)
	style.XP_B = Color(1.0, 1.0, 1.0)
	style.GHOST = Color(1.0, 1.0, 1.0, 0.9)


func panel(ci: CanvasItem, rect: Rect2, s: float, alpha: float, _radius: float) -> bool:
	ci.draw_rect(rect, Color(0.02, 0.05, 0.10, 0.82 * alpha))
	ci.draw_rect(Rect2(rect.position, Vector2(maxf(2.0, 3.0 * s), rect.size.y)), Color(0.35, 0.80, 1.0, alpha))
	return true


func bar(ci: CanvasItem, rect: Rect2, value: float, ghost: float, a: Color, b: Color, _s: float, alpha: float, ahead: float, ahead_colour: Color) -> bool:
	ci.draw_rect(rect.grow(1.0), Color(0, 0, 0, 0.7 * alpha))
	if ahead > value:
		ci.draw_rect(Rect2(rect.position, Vector2(rect.size.x * clampf(ahead, 0.0, 1.0), rect.size.y)), Color(ahead_colour, 0.5 * alpha))
	if ghost > value:
		ci.draw_rect(Rect2(rect.position, Vector2(rect.size.x * clampf(ghost, 0.0, 1.0), rect.size.y)), Color(1, 1, 1, 0.85 * alpha))
	ci.draw_rect(Rect2(rect.position, Vector2(rect.size.x * clampf(value, 0.0, 1.0), rect.size.y)), Color(a.lerp(b, 0.5), alpha))
	return true
