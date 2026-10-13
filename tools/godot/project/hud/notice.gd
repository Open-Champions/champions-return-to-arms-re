extends Control
# notice.gd - an invitation or a friend request from the portal while a game runs: one small
# card in the upper right corner, in the HUD's style.  It is not part of the playing HUD: it
# shows over the game's own screens too (hud.gd, "the portal's notices", says how it is answered).

const Top := preload("res://hud/top.gd")

var hud: Node


func tick() -> void:
	if not hud.notices.is_empty() or visible:
		visible = not hud.notices.is_empty()
		queue_redraw()


func _draw() -> void:
	var t0: int = hud.draw_begin()
	Top.draw_notice(self, hud)
	hud.draw_end(t0)
