extends Control
# notice.gd - an invitation or a friend request from the portal while a game runs: one small
# card in the upper right corner, in the HUD's style.  It is not part of the playing HUD: it
# shows over the game's own screens too (hud.gd, "the portal's notices", says how it is answered).

const Top := preload("res://hud/top.gd")
const Hud := preload("res://hud/hud.gd")

var hud: Node


func tick() -> void:
	# not over the game's own full-screen screens (the bag, a shop, the pause and gate menus): the card waits, and its
	# clock with it (hud.gd _notices), until the screen is closed
	var covered: bool = hud.ok and (hud.phase & (Hud.PH_MENU | Hud.PH_PAUSE_MENU | Hud.PH_GATE_MENU)) != 0
	var want: bool = not hud.notices.is_empty() and not covered
	if want or visible:
		visible = want
		queue_redraw()


func _draw() -> void:
	var t0: int = hud.draw_begin()
	Top.draw_notice(self, hud)
	hud.draw_end(t0)
