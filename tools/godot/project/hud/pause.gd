extends Control
# pause.gd - while the game's pause menu is open the playing HUD steps aside and two calm
# bands frame the picture: "Paused" and the level's name above, the character in a line
# below.  The menu itself is the game's own and stays untouched in the middle.

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
	var h: float = 58.0 * s
	draw_rect(Rect2(pic.position, Vector2(pic.size.x, h)), Color(Style.INK, 0.86))
	draw_rect(Rect2(Vector2(pic.position.x, pic.end.y - h), Vector2(pic.size.x, h)), Color(Style.INK, 0.86))
	draw_rect(Rect2(Vector2(pic.position.x, pic.position.y + h), Vector2(pic.size.x, maxf(1.0, s))), Style.HAIRLINE)
	draw_rect(Rect2(Vector2(pic.position.x, pic.end.y - h - maxf(1.0, s)), Vector2(pic.size.x, maxf(1.0, s))), Style.HAIRLINE)
	Style.text(self, Vector2(area.position.x, pic.position.y + 38.0 * s), "Paused", 26.0 * s, Style.TEXT, 0, true)
	var title: String = hud.frame.get("level_title", "")
	if title == "":
		title = hud.frame.get("level", "")
	Style.text(self, Vector2(area.end.x, pic.position.y + 37.0 * s), title, 19.0 * s, Style.TEXT_DIM, 2)
	var me: Dictionary = hud.me
	if not me.is_empty():
		var y: float = pic.end.y - 21.0 * s
		var x: float = area.position.x
		x += Style.text(self, Vector2(x, y), me.name, 19.0 * s, Style.TEXT, 0, true) + 14.0 * s
		x += Style.text(self, Vector2(x, y), "Level %d  %s" % [me.level, me.class_name], 15.0 * s, Style.TEXT_DIM) + 26.0 * s
		var line := "%s / %s health    %s / %s mana    %s gold" % [Style.number(me.health), Style.number(me.health_max), Style.number(me.mana), Style.number(me.mana_max),
			Style.number(me.gold + me.gold_coming)]
		Style.text(self, Vector2(area.end.x, y), line, 15.0 * s, Style.TEXT_DIM, 2)
	hud.draw_end(t0)
