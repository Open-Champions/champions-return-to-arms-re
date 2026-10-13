extends "res://portal/screen.gd"
# disc.gd - the disc image has not been found: one plain sentence and one button.
# (The game is not in this program: it plays from the player's own disc image, chosen once.
# The path is kept where the game scene reads it: user://settings.cfg, [game] disc.)


func chrome() -> bool:
	return false


func hints() -> Array:
	return [hint_select("Choose"), hint_back("Not now")]


func build() -> void:
	var cw := minf(size.x, UI.px(980))
	var x := (size.x - cw) * 0.5
	var total := UI.px(120 + 36 + 120 + 44 + 68)
	var y := maxf(0.0, (size.y - total) * 0.42)
	var medal := Medal.new()
	put(medal, Rect2((size.x - UI.px(120)) * 0.5, y, UI.px(120), UI.px(120)))
	y += UI.px(120 + 36)
	var missing := String(portal.profile.disc_path())
	var sentence := "To play, choose your disc image of Champions: Return to Arms (version 2.00) - once; it is remembered."
	if missing != "":
		sentence = "Your disc image is no longer where it was - choose it again; it is remembered."
	say(Rect2(x, y, cw, UI.px(120)), sentence, 34, UI.TEXT, UI.serif(), HORIZONTAL_ALIGNMENT_CENTER, true)
	y += UI.px(120 + 44)
	var b := W.Btn.new("Choose the disc image", "disc", "primary")
	b.height = 68.0
	b.font_size = 24.0
	b.key = "choose"
	add_child(b)
	b.size = b.custom_minimum_size
	b.position = Vector2(roundf((size.x - b.size.x) * 0.5), y)
	b.activated.connect(func() -> void: portal.call("choose_disc", _chosen))


func _chosen() -> void:
	portal.call("toast", "Disc image found", "good")
	portal.call("back")


class Medal extends Control:
	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		draw_style_box(UI.box(size.x * 0.5, Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.10), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.7), maxf(1.5, UI.px(2))), r)
		UI.icon(self, "disc", r.grow(-size.x * 0.22), UI.GOLD_HI)
