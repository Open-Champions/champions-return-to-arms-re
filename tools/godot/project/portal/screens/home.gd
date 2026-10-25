extends "res://portal/screen.gd"
# home.gd - the big, obvious choices, and the character played last.
#
#   Play alone          straight into the game with this character
#   Host a game         opens a room: its code is shown large enough to read out
#   Join with a code    type the five characters a friend reads out
#   Friends             who is on, what they play, one press to join or invite
#
# The character card shows the character played last - name, level and class as the game
# gave them.  Its picture is a drawn stand-in until the game scene can hand in a live view
# of one character (widgets.gd, Portrait.texture).

var card_rect := Rect2()


func hints() -> Array:
	return [hint_select(), hint_back("Quit")]


func build() -> void:
	var need_disc: bool = not portal.profile.game_ready() and not bool(portal.options.stub_game)
	var y0 := 0.0
	if need_disc:
		# the one sentence, with its one button
		var strip := Strip.new()
		put(strip, Rect2(0, 0, size.x, UI.px(72)))
		var b := W.Btn.new("Choose the disc image", "disc", "primary")
		b.height = 48.0
		b.font_size = 18.0
		b.key = "disc"
		strip.add_child(b)
		b.size = b.custom_minimum_size
		b.position = Vector2(size.x - b.size.x - UI.px(14), UI.px(12))
		b.activated.connect(func() -> void: portal.call("go", "disc"))
		strip.text_right = b.position.x - UI.px(16)
		y0 = UI.px(72 + 20)
	var kind := String(portal.call("edition"))
	if kind != "":
		# which game this is (the first screen's choice, edition.gd) and the way back to change it
		var label := say(Rect2(0, y0, size.x * 0.5, UI.px(52)), ("CLASSIC" if kind == "classic" else "REMASTERED"), 22, UI.GOLD_HI, UI.spaced(UI.serif_bold(), 5.0))
		label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		var change_game := W.Btn.new("Change game", "layers", "ghost")
		change_game.height = 52.0
		change_game.font_size = 18.0
		change_game.key = "edition"
		add_child(change_game)
		change_game.size = change_game.custom_minimum_size
		change_game.position = Vector2(roundf(UI.text_width(label.text, UI.spaced(UI.serif_bold(), 5.0), 22) + UI.px(24)), y0)
		change_game.activated.connect(func() -> void: portal.call("go", "modes"))
		y0 += UI.px(52 + 12)
	var avail := size.y - y0
	var gap := UI.px(44)
	var card_w := clampf(size.x * 0.33, UI.px(420), UI.px(560))
	var left_w := size.x - card_w - gap
	var tile_gap := UI.px(16)
	var tile_h := minf(UI.px(172), (avail - tile_gap * 3.0) / 4.0)
	var block_h := tile_h * 4.0 + tile_gap * 3.0
	var top := y0 + maxf(0.0, (avail - block_h) * 0.5)
	var me: Dictionary = portal.session.me()
	var online := 0
	var joinable := 0
	for f in portal.session.friends():
		if int(f.presence) > 0:
			online += 1
		if bool(f.joinable):
			joinable += 1
	var tiles := [
		["alone", "Play alone", "Straight into the game with your character.", "sword"],
		["host", "Host a game", "Open a room and read its code out to your friends.", "banner"],
		["join", "Join with a code", "A friend is hosting? Type the code they read out.", "key"],
		["friends", "Friends", "See who is on and what they are playing.", "people"],
	]
	for k in tiles.size():
		var t := W.Tile.new(tiles[k][1], tiles[k][2], tiles[k][3])
		t.key = tiles[k][0]
		put(t, Rect2(0, top + k * (tile_h + tile_gap), left_w, tile_h))
		match String(tiles[k][0]):
			"alone":
				t.activated.connect(func() -> void: portal.call("play_alone"))
			"host":
				t.activated.connect(func() -> void: portal.call("host_game"))
				if portal.session.in_room():
					t.title = "Back to your room"
					t.note = "Room " + String(portal.session.room().get("code", "")) + " is still open."
					t.tag = "open"
					t.tag_colour = UI.BLUE
			"join":
				t.activated.connect(func() -> void: portal.call("go", "join"))
				if joinable > 0:
					t.tag = "%d you can join" % joinable
					t.tag_colour = UI.BLUE
			"friends":
				t.activated.connect(func() -> void: portal.call("go", "friends"))
				if online > 0:
					t.tag = "%d online" % online
		if int(me.get("link", 0)) != 2 and (tiles[k][0] == "host" or tiles[k][0] == "join"):
			t.tag = "needs the connection"
			t.tag_colour = UI.FAINT
	# the character card
	card_rect = Rect2(left_w + gap, top, card_w, block_h)
	panel_at(card_rect, 18.0)
	var c: Dictionary = portal.profile.character()
	var has := String(c.get("name", "")) != ""
	var pad := UI.px(26)
	var inner := card_rect.grow(-pad)
	var buttons_h := UI.px(60)
	var text_h := UI.px(118)
	var cap := say(Rect2(inner.position.x, inner.position.y - UI.px(4), inner.size.x, UI.px(26)), "YOUR CHARACTER", 14, UI.GOLD, UI.spaced(UI.bold(), 2.5))
	cap.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	var portrait := W.Portrait.new()
	portrait.character = c
	portrait.live = has                 # the game's own picture of this character once it has one (portal.character_card)
	portrait.set_process(true)
	portrait.empty_text = ""
	var ph := inner.size.y - UI.px(34) - text_h - buttons_h - UI.px(14)
	put(portrait, Rect2(inner.position.x, inner.position.y + UI.px(34), inner.size.x, ph))
	var ty := inner.position.y + UI.px(34) + ph + UI.px(14)
	if has:
		say(Rect2(inner.position.x, ty, inner.size.x, UI.px(52)), String(c.name), 40, UI.TEXT, UI.serif_bold())
		say(Rect2(inner.position.x, ty + UI.px(52), inner.size.x, UI.px(30)), UI.class_line(c), 21, UI.DIM)
		say(Rect2(inner.position.x, ty + UI.px(82), inner.size.x, UI.px(24)), "The character you played last", 15, UI.FAINT)
	else:
		say(Rect2(inner.position.x, ty, inner.size.x, UI.px(52)), "No character yet", 36, UI.TEXT, UI.serif_bold())
		say(Rect2(inner.position.x, ty + UI.px(52), inner.size.x, UI.px(56)), "Make one in the game - it shows up here with its name, level and class.", 18, UI.DIM, null, HORIZONTAL_ALIGNMENT_LEFT, true)
	var by := inner.end.y - buttons_h
	var change := W.Btn.new("Change character" if has else "Choose or make a character", "person", "normal" if has else "primary")
	change.height = 60.0
	change.font_size = 20.0
	change.fixed = true
	change.key = "character"
	put(change, Rect2(inner.position.x, by, inner.size.x, buttons_h))
	change.activated.connect(func() -> void: portal.call("go", "characters"))
	if want_focus == "":
		want_focus = "alone"


func session_changed(what: String) -> void:
	if what == "friends" or what == "link" or what == "room" or what == "me":
		rebuild()


class Strip extends Control:
	var text_right := 0.0

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		draw_style_box(UI.box(UI.px(14), Color(0.20, 0.13, 0.05, 0.85), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.55), maxf(1.0, UI.px(1.5))), r)
		var isz := UI.px(28)
		UI.icon(self, "disc", Rect2(UI.px(22), (size.y - isz) * 0.5, isz, isz), UI.GOLD_HI)
		UI.text(self, Rect2(UI.px(64), 0, text_right - UI.px(64), size.y), "Your disc image of the game has not been found yet - choose it once and you can play.", UI.sans(), 20, UI.TEXT)
