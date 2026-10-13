extends Control
# pause.gd - while the game's pause menu is open the playing HUD steps aside and one calm
# band lies across the top of the picture: "Paused", the level's name, the character in a
# line.  The menu itself is the game's own and stays untouched in the middle; so does the
# foot of the picture, where the game puts its button hints.

const Style := preload("res://hud/style.gd")
const Hud := preload("res://hud/hud.gd")

var hud: Node
var last := ""


func tick() -> void:
	if hud.pause_show <= 0.0:
		return
	var sig := "%s|%.2f|%s" % [str(hud.picture), hud.pause_show, hud.frame.get("level_title", "")]
	if sig != last:
		last = sig
		queue_redraw()


func _draw() -> void:
	var t0: int = hud.draw_begin()
	var s: float = hud.s
	var pic: Rect2 = hud.picture
	var area: Rect2 = hud.area
	# one band across the top; the foot of the picture stays free: the game's menu puts its button hints there
	var h: float = 76.0 * s
	draw_rect(Rect2(pic.position, Vector2(pic.size.x, h)), Color(Style.INK, 0.88))
	draw_rect(Rect2(Vector2(pic.position.x, pic.position.y + h), Vector2(pic.size.x, maxf(1.0, s))), Style.HAIRLINE)
	Style.text(self, Vector2(area.position.x, pic.position.y + 36.0 * s), "Paused", 27.0 * s, Style.TEXT, 0, true)
	var title: String = hud.frame.get("level_title", "")
	if title == "":
		title = hud.frame.get("level", "")
	Style.text(self, Vector2(area.end.x, pic.position.y + 35.0 * s), title, 20.0 * s, Style.TEXT, 2, true)
	var me: Dictionary = hud.me
	if not me.is_empty():
		var y: float = pic.position.y + 61.0 * s
		Style.text(self, Vector2(area.position.x, y), "%s    Level %d  %s" % [me.name, me.level, me.class_name], 15.0 * s, Style.TEXT_DIM)
		var line := "%s / %s health    %s / %s mana    %s gold" % [Style.number(me.health), Style.number(me.health_max), Style.number(me.mana), Style.number(me.mana_max),
			Style.number(me.gold + me.gold_coming)]
		Style.text(self, Vector2(area.end.x, y), line, 15.0 * s, Style.TEXT_DIM, 2)
	hud.draw_end(t0)
