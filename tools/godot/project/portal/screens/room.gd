extends "res://portal/screen.gd"
# room.gd - the room: who is in it (name and the character they play), the code large
# enough to read out, chat, ready marks, what the host may choose, and the start.
#
#   host    chooses (as far as the session's options go: difficulty, who may walk in) and
#           presses Start - when everybody else has the ready mark
#   guest   presses Ready; sees the host's choices
#   A warning appears ONLY when something is wrong: a copy of the game that would fall out
#   of step ("Sam's game is a different version - they need to update").
# After the game the same room is back, with "Play again".

const Session := preload("res://portal/session.gd")

var chat_typed := ""
var played := false
var room := {}
var leaving := false
var auto_key := ""


func hints() -> Array:
	return [hint_select(), hint_back("Leave room")]


func build() -> void:
	played = played or bool(args.get("played", false))
	room = portal.session.room()
	var state := int(room.get("state", 0))
	if state <= Session.ROOM_JOINING:
		say(Rect2(0, size.y * 0.36, size.x, UI.px(60)), "Opening the room...", 40, UI.TEXT, UI.serif_bold(), HORIZONTAL_ALIGNMENT_CENTER)
		say(Rect2(0, size.y * 0.36 + UI.px(64), size.x, UI.px(34)), "One moment.", 21, UI.DIM, null, HORIZONTAL_ALIGNMENT_CENTER)
		return
	var members: Array = room.get("members", [])
	var mine: Dictionary = {}
	var host_member: Dictionary = {}
	for m in members:
		if bool(m.me):
			mine = m
		if bool(m.host):
			host_member = m
	var i_host := bool(mine.get("host", false))
	var gap := UI.px(36)
	var right_w := clampf(size.x * 0.33, UI.px(420), UI.px(560))
	var left_w := size.x - right_w - gap
	var y := 0.0
	var title := "Your room" if i_host else "%s's room" % String(host_member.get("name", "The host"))
	say(Rect2(0, 0, left_w, UI.px(60)), title, 44, UI.TEXT, UI.serif_bold())
	y += UI.px(70)
	# ---- only when something is wrong ----
	_find_odd(members, host_member)
	var wrong := _mismatch_text(members, mine, host_member)
	if wrong != "":
		var banner := Banner.new()
		banner.text = wrong
		banner.detail = String(room.get("warning", ""))
		put(banner, Rect2(0, y, left_w, UI.px(72)))
		y += UI.px(72 + 14)
	# ---- the bottom of the left column: choices, then the buttons ----
	var actions_h := UI.px(76)
	var note_h := UI.px(30)
	var choices_h := UI.px(82 if int(portal.gameflow.call("unlocked")) < 4 else 64)
	var bottom := size.y
	var actions_y := bottom - actions_h
	var note_y := actions_y - note_h - UI.px(4)
	var choices_y := note_y - choices_h - UI.px(10)
	# ---- the seats ----
	var seats_h := choices_y - UI.px(18) - y
	var seat_gap := UI.px(14)
	var seat_w := (left_w - seat_gap * 3.0) / 4.0
	for k in 4:
		var seat := Seat.new()
		seat.key = "seat%d" % k
		seat.starting = state >= Session.ROOM_STARTING
		var member := {}
		for m in members:
			if int(m.slot) == k:
				member = m
		if member.is_empty() and k < members.size() and not _slot_taken(members, k):
			member = {}
		seat.member = member
		seat.odd = not member.is_empty() and _is_odd(member, host_member)
		put(seat, Rect2(k * (seat_w + seat_gap), y, seat_w, seats_h))
		seat.build()
		if member.is_empty():
			if state != Session.ROOM_OPEN:
				seat.focus_mode = Control.FOCUS_NONE
			seat.activated.connect(func() -> void: portal.call("go", "friends"))
		else:
			var m := member
			var acts := _member_actions(m, i_host, state)
			if acts.is_empty():
				seat.focus_mode = Control.FOCUS_NONE
			else:
				seat.activated.connect(func() -> void: portal.call("menu", String(m.name), acts + [{"text": "Cancel", "kind": "ghost"}], UI.character_line(m.get("character", {}))))
	# ---- what the host may choose ----
	var options: Dictionary = room.get("options", {})
	var can_choose := i_host and state == Session.ROOM_OPEN
	var cw := (left_w - UI.px(14)) * 0.5
	# the game's own four (net2_options.difficulty 1..4; 0 means the first). Only missions are
	# wired into the launch today: the arena modes are not offered until they are.
	# ... and only those the game's own menu would offer this host (net2_game_status().difficulty_unlocked: 1 on a new card)
	var names := PackedStringArray(["Easy", "Normal", "Hard", "Harder"]).slice(0, int(portal.gameflow.call("unlocked")))
	var difficulty := W.Choice.new("Difficulty", names, clampi(int(options.get("difficulty", 1)) - 1, 0, names.size() - 1),
		"" if names.size() == 4 else "More as your game unlocks them")
	difficulty.key = "difficulty"
	difficulty.locked = not can_choose
	put(difficulty, Rect2(0, choices_y, cw, choices_h))
	difficulty.changed.connect(func(index: int) -> void: _set_option("difficulty", index + 1))
	var open_to := W.Choice.new("Who can join", PackedStringArray(["Code only", "Friends too"]), clampi(int(options.get("open_to", 0)), 0, 1))
	open_to.key = "open_to"
	open_to.locked = not can_choose
	put(open_to, Rect2(cw + UI.px(14), choices_y, cw, choices_h))
	open_to.changed.connect(func(index: int) -> void: _set_option("open_to", index))
	# ---- start / ready ----
	var waiting := []
	for m in members:
		if not bool(m.ready) and not bool(m.host):
			waiting.append(String(m.name))
	var note := ""
	var main := W.Btn.new("", "", "primary")
	main.height = 76.0
	main.font_size = 26.0
	main.fixed = true
	main.key = "main"
	if state >= Session.ROOM_STARTING:
		main.text = "Starting..."
		main.disabled = true
		note = _routes_text(members)
	elif gameflow_active() and not portal.gameflow.call("has_character"):
		# the game's side: a character for this game first, on the game's own screens
		main.icon = "person"
		main.text = ("Play again - choose your character" if played else "Choose your character")
		if not portal.gameflow.call("game_ready"):
			main.disabled = true
			if int(portal.gameflow.games) > 0:
				main.text = "Back to the title screen..."
				note = "Your game is on its way back from the last one."
			else:
				main.text = "Your game is getting ready..."
				note = "The game is starting behind the portal; it takes a few seconds."
		else:
			note = "The game's own screens: make a character or bring one you have. Then you are back here."
		main.activated.connect(func() -> void: portal.gameflow.call("choose"))
	elif i_host:
		main.text = "Play again" if played else "Start the game"
		main.icon = "sword"
		if wrong != "":
			main.disabled = true
			note = "The game cannot start until the versions match."
		elif not waiting.is_empty():
			main.disabled = true
			note = "Waiting for %s to be ready." % _names(waiting)
		elif gameflow_active() and not _all_back(members):
			main.disabled = true
			note = "Waiting for everybody to be back from the last game."
		elif members.size() == 1:
			note = "You can start alone - friends can still come in by the code."
		else:
			note = "Everybody is ready."
		main.activated.connect(func() -> void: portal.session.start())
	else:
		var ready := bool(mine.get("ready", false))
		main.text = "Not ready after all" if ready else ("Ready - play again" if played else "I am ready")
		main.icon = "" if ready else "check"
		main.kind = "normal" if ready else "primary"
		note = ("%s starts the game when everybody is ready." % String(host_member.get("name", "The host"))) if ready else "Press when you are ready to play."
		main.activated.connect(func() -> void: portal.session.ready(not ready))
	var main_w := left_w * 0.46
	put(main, Rect2(0, actions_y, main_w, actions_h))
	say(Rect2(0, note_y, left_w, note_h), note, 18, UI.DIM)
	var invite := W.Btn.new("Invite friends", "people", "normal")
	invite.height = 76.0
	invite.font_size = 21.0
	invite.fixed = true
	invite.key = "invite"
	invite.disabled = state != Session.ROOM_OPEN or members.size() >= 4
	var side_w := (left_w - main_w - UI.px(14) * 2.0) * 0.5
	put(invite, Rect2(main_w + UI.px(14), actions_y, side_w, actions_h))
	invite.activated.connect(func() -> void: portal.call("go", "friends"))
	var leave := W.Btn.new("Leave", "door", "ghost")
	leave.height = 76.0
	leave.font_size = 21.0
	leave.fixed = true
	leave.key = "leave"
	put(leave, Rect2(main_w + side_w + UI.px(28), actions_y, side_w, actions_h))
	leave.activated.connect(_ask_leave)
	# ---- the right column: the code, the chat ----
	var rx := left_w + gap
	var code_h := UI.px(232)
	panel_at(Rect2(rx, 0, right_w, code_h), 18.0)
	var code := CodeView.new()
	code.code = String(room.get("code", ""))
	put(code, Rect2(rx, 0, right_w, code_h - UI.px(70)))
	var copy := W.Btn.new("Copy the code", "copy", "ghost")
	copy.height = 48.0
	copy.font_size = 18.0
	copy.key = "copy"
	add_child(copy)
	copy.size = copy.custom_minimum_size
	copy.position = Vector2(roundf(rx + (right_w - copy.size.x) * 0.5), code_h - UI.px(64))
	copy.activated.connect(func() -> void: portal.call("copy_text", String(room.get("code", "")), "Room code"))
	var chat_y := code_h + UI.px(16)
	panel_at(Rect2(rx, chat_y, right_w, size.y - chat_y), 18.0)
	var field_h := UI.px(56)
	var lines := ChatView.new()
	lines.lines = room.get("chat", [])
	lines.my_name = String(mine.get("name", ""))
	put(lines, Rect2(rx + UI.px(20), chat_y + UI.px(14), right_w - UI.px(40), size.y - chat_y - field_h - UI.px(40)))
	var field := W.Field.new("Say something...", 120)
	field.key = "chat"
	field.height = 56.0
	field.text = chat_typed
	put(field, Rect2(rx + UI.px(14), size.y - field_h - UI.px(14), right_w - UI.px(28), field_h))
	field.edited.connect(func(t: String) -> void: chat_typed = t)
	field.submitted.connect(func(_t: String) -> void: _say())
	field.wants_keys.connect(func() -> void:
		ask_text({"title": "Say something", "mode": "chat", "text": chat_typed, "max": 120, "placeholder": "", "done_text": "Send",
			"done": func(t: String) -> void:
				chat_typed = t
				_say()}))
	# the focus rests on the one thing to press for as long as the player has not moved it elsewhere
	if want_focus == "" or want_focus == auto_key or find_key(self, want_focus) == null:
		auto_key = "main" if not main.disabled else ("invite" if not invite.disabled else ("chat" if state >= Session.ROOM_STARTING else "leave"))
		want_focus = auto_key


func gameflow_active() -> bool:
	return portal.gameflow != null and bool(portal.gameflow.active)


func _all_back(members: Array) -> bool:
	for m in members:
		if int(m.get("phase", 0)) != 0:
			return false
	return true


func _slot_taken(members: Array, k: int) -> bool:
	for m in members:
		if int(m.slot) == k:
			return true
	return false


func _names(list: Array) -> String:
	if list.size() == 1:
		return String(list[0])
	if list.size() == 2:
		return "%s and %s" % [list[0], list[1]]
	return "%d players" % list.size()


var odd_ids := {}


func _find_odd(members: Array, host_member: Dictionary) -> void:
	# whose copy of the game is not what most of the room has (a tie: not what the host has)
	odd_ids = {}
	if not bool(room.get("mismatch", false)):
		return
	var groups := {}
	for m in members:
		var k := "%d/%d/%d" % [int(m.get("fix_set", 0)), int(m.get("fix_words", 0)), int(m.get("arith_does", 0))]
		groups[k] = int(groups.get(k, 0)) + 1
	var host_key := "%d/%d/%d" % [int(host_member.get("fix_set", 0)), int(host_member.get("fix_words", 0)), int(host_member.get("arith_does", 0))]
	var best := host_key
	for k in groups:
		if int(groups[k]) > int(groups.get(best, 0)):
			best = k
	for m in members:
		var k := "%d/%d/%d" % [int(m.get("fix_set", 0)), int(m.get("fix_words", 0)), int(m.get("arith_does", 0))]
		if k != best:
			odd_ids[String(m.id)] = true


func _is_odd(member: Dictionary, _host_member: Dictionary) -> bool:
	return odd_ids.has(String(member.get("id", "")))


func _mismatch_text(members: Array, mine: Dictionary, host_member: Dictionary) -> String:
	if not bool(room.get("mismatch", false)):
		return ""
	var odd := []
	for m in members:
		if _is_odd(m, host_member):
			odd.append(m)
	if odd.is_empty():
		return "These copies of the game do not match - somebody needs to update."
	if odd.size() == 1:
		if bool(odd[0].me):
			return "Your game is a different version from the others' - you need to update."
		return "%s's game is a different version - they need to update." % String(odd[0].name)
	var names := []
	for m in odd:
		names.append("you" if bool(m.me) else String(m.name))
	return "%s have a different version of the game - they need to update." % " and ".join(PackedStringArray(names))


func _routes_text(members: Array) -> String:
	var trying := 0
	var relay := 0
	for m in members:
		if bool(m.me):
			continue
		match int(m.route):
			Session.ROUTE_RELAY: relay += 1
			Session.ROUTE_DIRECT, Session.ROUTE_SELF: pass
			_: trying += 1
	if trying > 0:
		return "Finding each other..."
	if relay > 0:
		return "Connected (%d through the relay). The game is starting." % relay
	return "Connected. The game is starting."


func _member_actions(m: Dictionary, i_host: bool, state: int) -> Array:
	var acts := []
	if bool(m.me):
		return acts
	var id := String(m.id)
	var name := String(m.name)
	if not bool(m.get("is_friend", false)):
		acts.append({"text": "Add as a friend", "icon": "plus", "run": func() -> void:
			portal.session.friend_add_id(id)
			portal.call("toast", "Asked %s to be friends" % name, "good")})
	if i_host and state == Session.ROOM_OPEN:
		var slot := int(m.slot)
		acts.append({"text": "Take out of the room", "icon": "cross", "run": func() -> void:
			portal.call("confirm", "Take %s out of the room?" % name, "", "Take out", func() -> void: portal.session.kick(slot), true)})
	return acts


func _set_option(key: String, value: int) -> void:
	var options: Dictionary = (room.get("options", {}) as Dictionary).duplicate()
	options[key] = value
	portal.session.set_options(options)


func _say() -> void:
	var text := chat_typed.strip_edges()
	chat_typed = ""
	if text != "":
		portal.session.chat(text)
	want_focus = "chat"
	rebuild()


func _ask_leave() -> void:
	var members: Array = room.get("members", [])
	if members.size() <= 1:
		_leave()
		return
	portal.call("confirm", "Leave the room?", "", "Leave", _leave, false, "Stay")


func _leave() -> void:
	leaving = true
	portal.session.leave()
	portal.call("home")


func back() -> bool:
	if int(room.get("state", 0)) >= Session.ROOM_JOINING:
		_ask_leave()
		return true
	return false


func session_changed(what: String) -> void:
	if (what == "room" or what == "chat" or what == "friends" or what == "game") and not leaving:
		rebuild()


func session_event(e: Dictionary) -> void:
	if int(e.type) == Session.EV_GAME_OVER:
		played = true
		want_focus = "main"
		rebuild()


# ---- a seat ---------------------------------------------------------------------------------
class Seat extends W.Focusable:
	var member := {}
	var starting := false
	var odd := false
	var portrait: Control

	func build() -> void:
		if member.is_empty():
			return
		portrait = W.Portrait.new()
		portrait.character = member.get("character", {})
		portrait.framed = false
		portrait.set_process(true)
		add_child(portrait)
		var pad := UI.px(10)
		var text_h := UI.px(150)
		portrait.position = Vector2(pad, pad)
		portrait.size = Vector2(size.x - pad * 2.0, maxf(UI.px(40), size.y - text_h - pad))
		var over := SeatText.new()
		over.seat = self
		add_child(over)
		over.position = Vector2.ZERO
		over.size = size

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(16)
		var e := eased()
		UI.focus_glow(self, r, radius, e)
		if member.is_empty():
			# an open seat: a dashed outline and what to do about it
			draw_style_box(UI.box(radius, Color(UI.PANEL.r, UI.PANEL.g, UI.PANEL.b, 0.35).lerp(UI.PANEL_HOT, e)), r)
			_dashes(r.grow(-UI.px(1)), radius, Color(1, 1, 1, 0.20 + 0.3 * e))
			UI.focus_ring(self, r, radius, e)
			var m := UI.px(64)
			var c := Vector2(size.x * 0.5, size.y * 0.40)
			draw_style_box(UI.box(m * 0.5, Color(1, 1, 1, 0.04), Color(1, 1, 1, 0.22 + 0.4 * e), maxf(1.5, UI.px(2))), Rect2(c - Vector2(m, m) * 0.5, Vector2(m, m)))
			UI.icon(self, "plus", Rect2(c - Vector2(m, m) * 0.22, Vector2(m, m) * 0.44), Color(1, 1, 1, 0.5 + 0.5 * e))
			UI.text(self, Rect2(UI.px(10), c.y + m * 0.5 + UI.px(18), size.x - UI.px(20), UI.px(30)), "Open seat", UI.bold(), 21, UI.DIM, HORIZONTAL_ALIGNMENT_CENTER)
			UI.text(self, Rect2(UI.px(10), c.y + m * 0.5 + UI.px(48), size.x - UI.px(20), UI.px(26)), "Invite a friend", UI.sans(), 17, UI.FAINT if e < 0.5 else UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER)
			return
		var ready := bool(member.get("ready", false)) or bool(member.get("host", false))
		var line := UI.LINE
		if odd:
			line = Color(UI.RED.r, UI.RED.g, UI.RED.b, 0.8)
		elif bool(member.get("ready", false)):
			line = Color(UI.GREEN.r, UI.GREEN.g, UI.GREEN.b, 0.55)
		if UI.skinned("surface", [self, "seat", r, radius, e, false]):
			if line != UI.LINE:                 # ready / a different version: the seat's coloured line stays
				draw_style_box(UI.box(radius, Color(0, 0, 0, 0), line, maxf(1.0, UI.px(2))), r.grow(UI.px(2)))
		else:
			draw_style_box(UI.box(radius, Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, Color(0, 0, 0, 0.28), UI.px(16)), r)
			draw_style_box(UI.box(radius, Color(UI.PANEL.r, UI.PANEL.g, UI.PANEL.b, 0.86).lerp(UI.PANEL_HOT, e * 0.6), line, maxf(1.0, UI.px(1.5))), r)
		UI.focus_ring(self, r, radius, e)

	func _dashes(r: Rect2, radius: float, colour: Color) -> void:
		var w := maxf(1.5, UI.px(2))
		var dash := UI.px(12)
		var x := r.position.x + radius
		while x < r.end.x - radius:
			var x2 := minf(x + dash, r.end.x - radius)
			draw_line(Vector2(x, r.position.y), Vector2(x2, r.position.y), colour, w)
			draw_line(Vector2(x, r.end.y), Vector2(x2, r.end.y), colour, w)
			x += dash * 2.0
		var y := r.position.y + radius
		while y < r.end.y - radius:
			var y2 := minf(y + dash, r.end.y - radius)
			draw_line(Vector2(r.position.x, y), Vector2(r.position.x, y2), colour, w)
			draw_line(Vector2(r.end.x, y), Vector2(r.end.x, y2), colour, w)
			y += dash * 2.0
		draw_arc(r.position + Vector2(radius, radius), radius, PI, PI * 1.5, 8, colour, w, true)
		draw_arc(Vector2(r.end.x - radius, r.position.y + radius), radius, PI * 1.5, TAU, 8, colour, w, true)
		draw_arc(r.end - Vector2(radius, radius), radius, 0.0, PI * 0.5, 8, colour, w, true)
		draw_arc(Vector2(r.position.x + radius, r.end.y - radius), radius, PI * 0.5, PI, 8, colour, w, true)


class SeatText extends Control:
	# what is written on a seat, drawn above its portrait
	var seat: Control

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var member: Dictionary = seat.get("member")
		var pad := UI.px(16)
		var text_top := size.y - UI.px(150)
		var w := size.x - pad * 2.0
		var c: Dictionary = member.get("character", {})
		var name := String(member.get("name", ""))
		# who: the name friends see
		var tag := ""
		if bool(member.get("host", false)):
			tag = "HOST"
		var y := text_top + UI.px(6)
		var av := UI.px(34)
		if size.x < UI.px(230):
			av = -UI.px(10)             # a narrow seat: the name gets the whole line
		else:
			W.Avatar.draw_avatar(self, Rect2(pad, y, av, av), name, String(member.get("id", name)), -1)
		var name_right := size.x - pad
		if bool(member.get("me", false)):
			var yw := UI.text_width("you", UI.bold(), 14) + UI.px(16)
			var yr := Rect2(name_right - yw, y + UI.px(5), yw, UI.px(24))
			draw_style_box(UI.box(UI.px(12), Color(1, 1, 1, 0.09), Color(1, 1, 1, 0.2), 1), yr)
			UI.text(self, yr, "you", UI.bold(), 14, UI.DIM, HORIZONTAL_ALIGNMENT_CENTER)
			name_right = yr.position.x - UI.px(8)
		UI.text(self, Rect2(pad + av + UI.px(10), y, name_right - (pad + av + UI.px(10)), UI.px(34)), name, UI.bold(), 21, UI.TEXT)
		y += UI.px(44)
		# the character they play
		if String(c.get("name", "")) != "":
			UI.text(self, Rect2(pad, y, w, UI.px(32)), String(c.name), UI.serif_bold(), 24, UI.GOLD_HI)
			UI.text(self, Rect2(pad, y + UI.px(32), w, UI.px(24)), UI.class_line(c), UI.sans(), 16, UI.DIM)
		else:
			UI.text(self, Rect2(pad, y, w, UI.px(32)), "No character chosen", UI.sans(), 18, UI.FAINT)
		# the mark at the bottom: ready, host, or what is wrong
		var by := size.y - UI.px(38)
		var mark := "Not ready"
		var colour := UI.FAINT
		var icon_name := ""
		if bool(seat.get("odd")):
			mark = "Different version"
			colour = UI.RED
			icon_name = "warn"
		elif bool(seat.get("starting")) and not bool(member.get("me", false)):
			match int(member.get("route", 0)):
				2, 4:
					mark = "Connected" + (" - %d ms" % int(member.rtt_ms) if int(member.get("rtt_ms", -1)) >= 0 else "")
					colour = UI.GREEN
					icon_name = "check"
				3:
					mark = "Connected by relay" + (" - %d ms" % int(member.rtt_ms) if int(member.get("rtt_ms", -1)) >= 0 else "")
					colour = UI.GOLD
					icon_name = "check"
				_:
					mark = "Connecting..."
					colour = UI.DIM
		elif int(member.get("phase", 0)) == 2 and not bool(seat.get("starting")):
			mark = "In the game"
			colour = UI.VIOLET
			icon_name = "sword"
		elif bool(member.get("host", false)):
			mark = "Host"
			colour = UI.GOLD
			icon_name = "crown"
		elif bool(member.get("ready", false)):
			mark = "Ready"
			colour = UI.GREEN
			icon_name = "check"
		var x := pad
		if icon_name != "":
			var isz := UI.px(20)
			UI.icon(self, icon_name, Rect2(x, by + UI.px(2), isz, isz), colour)
			x += isz + UI.px(8)
		else:
			draw_arc(Vector2(x + UI.px(9), by + UI.px(12)), UI.px(7), 0.0, TAU, 20, colour, maxf(1.5, UI.px(2)), true)
			x += UI.px(26)
		UI.text(self, Rect2(x, by, size.x - x - pad, UI.px(24)), mark, UI.bold(), 17, colour)


# ---- the code ---------------------------------------------------------------------------------
class CodeView extends Control:
	var code := ""

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		UI.text(self, Rect2(0, UI.px(22), size.x, UI.px(24)), "ROOM CODE", UI.spaced(UI.bold(), 3.0), 15, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER)
		var font := UI.spaced(UI.bold(), 14.0)
		var size_px := 92.0
		while size_px > 30.0 and UI.text_width(code, font, size_px) > size.x - UI.px(40):
			size_px -= 4.0
		# the spacing after the last letter would push the code off centre
		var w := UI.text_width(code, font, size_px)
		UI.text(self, Rect2((size.x - w) * 0.5 + UI.px(7), UI.px(46), w + UI.px(8), size.y - UI.px(46)), code, font, size_px, UI.GOLD_HI)


# ---- the chat ---------------------------------------------------------------------------------
class ChatView extends Control:
	var lines: Array = []
	var my_name := ""

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE
		clip_contents = true

	func _draw() -> void:
		if lines.is_empty():
			UI.text(self, Rect2(0, size.y - UI.px(40), size.x, UI.px(30)), "Nobody has said anything yet.", UI.sans(), 17, UI.FAINT)
			return
		var y := size.y
		for k in range(lines.size() - 1, -1, -1):
			var line: Dictionary = lines[k]
			var from := String(line.get("from", ""))
			var para := TextParagraph.new()
			para.width = size.x
			if from == "":
				para.add_string(String(line.text), UI.sans(), UI.fs(16))
			else:
				para.add_string(from + "  ", UI.bold(), UI.fs(18))
				para.add_string(String(line.text), UI.sans(), UI.fs(18))
			var h := para.get_size().y
			y -= h + UI.px(8)
			if y < -h:
				break
			if from == "":
				para.draw(get_canvas_item(), Vector2(0, y), UI.FAINT)
			else:
				para.draw(get_canvas_item(), Vector2(0, y), UI.TEXT)
				# the name again in its own colour, over the first line
				var tint := UI.tint_of(from, 0.45, 0.95) if from != my_name else UI.GOLD_HI
				var name_line := TextLine.new()
				name_line.add_string(from, UI.bold(), UI.fs(18))
				draw_rect(Rect2(0, y, name_line.get_size().x, name_line.get_size().y), Color(UI.PANEL.r, UI.PANEL.g, UI.PANEL.b, 1.0))
				name_line.draw(get_canvas_item(), Vector2(0, y), tint)


class Banner extends Control:
	var text := ""
	var detail := ""

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		draw_style_box(UI.box(UI.px(14), Color(0.30, 0.08, 0.07, 0.92), Color(UI.RED.r, UI.RED.g, UI.RED.b, 0.75), maxf(1.0, UI.px(1.5))), r)
		var isz := UI.px(30)
		UI.icon(self, "warn", Rect2(UI.px(22), (size.y - isz) * 0.5, isz, isz), UI.RED)
		var x := UI.px(70)
		if detail != "" and detail != text:
			UI.text(self, Rect2(x, UI.px(10), size.x - x - UI.px(20), UI.px(30)), text, UI.bold(), 21, UI.TEXT)
			UI.text(self, Rect2(x, UI.px(38), size.x - x - UI.px(20), UI.px(24)), detail, UI.sans(), 15, Color(1, 0.82, 0.8, 0.85))
		else:
			UI.text(self, Rect2(x, 0, size.x - x - UI.px(20), size.y), text, UI.bold(), 21, UI.TEXT)
