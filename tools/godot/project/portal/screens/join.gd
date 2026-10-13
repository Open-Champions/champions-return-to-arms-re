extends "res://portal/screen.gd"
# join.gd - join with a code: the five characters the host reads out.  With a controller
# the letters are on screen; with a keyboard they are typed.  What the service answers when
# it does not work ("no such room", "the room is full", "the game has started") is shown
# under the code, in its own words.  Friends whose room can be joined right now are listed
# beside it: one press.

const Session := preload("res://portal/session.gd")
const Keys := preload("res://portal/keys.gd")
const CODE_LENGTH := 5

var typed := ""
var problem := ""
var busy := false
var field: W.Field
var keys: Control
var note: Label
var join_button: W.Btn


func takes_errors() -> bool:
	return true


func hints() -> Array:
	if UI.pad_glyphs:
		return [hint_select("Type"), {"pad": "x", "key": "Backspace", "text": "Delete"}, {"pad": "start", "key": "Enter", "text": "Join"}, hint_back()]
	return [{"pad": "a", "key": "Enter", "text": "Join"}, hint_back()]


func build() -> void:
	var joinable: Array = portal.session.friends().filter(func(f: Dictionary) -> bool: return bool(f.joinable))
	var with_keys := UI.pad_glyphs
	var side_w := 0.0
	var gap := UI.px(44)
	if not joinable.is_empty():
		side_w = clampf(size.x * 0.34, UI.px(430), UI.px(560))
	var main_w := size.x - (side_w + gap if side_w > 0.0 else 0.0)
	var cw := minf(main_w, UI.px(760))
	var x := (main_w - cw) * 0.5
	keys = null
	var keys_h := 0.0
	if with_keys:
		keys = Keys.new()
		keys.mode = "code"
		keys.done_text = "Join"
		keys_h = keys.wanted_size().y
	var total := UI.px(60 + 8 + 34 + 34 + 120 + 44) + (keys_h if with_keys else UI.px(16 + 68))
	var y := maxf(0.0, (size.y - total) * (0.5 if with_keys else 0.36))
	say(Rect2(x, y, cw, UI.px(60)), "Join with a code", 46, UI.TEXT, UI.serif_bold(), HORIZONTAL_ALIGNMENT_CENTER)
	y += UI.px(68)
	say(Rect2(x, y, cw, UI.px(34)), "Ask the host for the five characters on their screen.", 21, UI.DIM, null, HORIZONTAL_ALIGNMENT_CENTER)
	y += UI.px(68)
	field = W.Field.new("- - - - -", CODE_LENGTH)
	field.upper = true
	field.large = true
	field.height = 120.0
	field.key = "code"
	field.text = typed
	var fw := minf(cw, UI.px(520))
	put(field, Rect2(x + (cw - fw) * 0.5, y, fw, UI.px(120)))
	field.edited.connect(_edited)
	field.submitted.connect(func(_t: String) -> void: _join())
	y += UI.px(120)
	note = say(Rect2(x, y + UI.px(8), cw, UI.px(30)), _note_text(), 19, UI.EMBER if problem != "" else UI.DIM, null, HORIZONTAL_ALIGNMENT_CENTER)
	y += UI.px(44)
	if with_keys:
		field.focus_mode = Control.FOCUS_NONE
		field.set_editing(true)
		keys.field = field
		add_child(keys)
		keys.build()
		keys.position = Vector2(roundf(x + (cw - keys.size.x) * 0.5), y)
		keys.done.connect(_join)
		if not want_focus.begins_with("key_") and not want_focus.begins_with("friend:"):
			want_focus = "key_A"
	else:
		y += UI.px(16)
		join_button = W.Btn.new("Join", "door", "primary")
		join_button.height = 68.0
		join_button.font_size = 24.0
		join_button.key = "join"
		join_button.fixed = true
		join_button.disabled = typed.length() != CODE_LENGTH or busy
		var bw := UI.px(300)
		put(join_button, Rect2(x + (cw - bw) * 0.5, y, bw, UI.px(68)))
		join_button.activated.connect(_join)
		if not want_focus.begins_with("friend:"):
			want_focus = "code"
	if side_w > 0.0:
		var rx := main_w + gap
		panel_at(Rect2(rx, 0, side_w, size.y), 18.0)
		var col := scroller(Rect2(rx + UI.px(14), UI.px(14), side_w - UI.px(20), size.y - UI.px(28)), 8.0)
		col.add_child(W.Heading.new("Friends you can join now", str(joinable.size())))
		for f in joinable:
			var row := W.Row.new()
			var id := String(f.id)
			row.key = "friend:" + id
			row.who = String(f.name)
			row.seed_key = id
			row.presence = int(f.presence)
			row.status = "%d of 4 in the room" % int(f.room_players)
			row.status_colour = UI.BLUE
			row.detail = UI.character_line(f.get("character", {}))
			row.actions = [{"id": "join", "text": "Join", "icon": "door"}]
			row.action.connect(func(_what: String) -> void: portal.call("join_friend", id))
			col.add_child(row)


func _note_text() -> String:
	if problem != "":
		return problem
	if busy:
		return "Looking for room %s..." % typed
	return ""


func _edited(text: String) -> void:
	typed = text
	problem = ""
	busy = false
	note.text = ""
	if join_button != null and is_instance_valid(join_button):
		join_button.set_disabled(typed.length() != CODE_LENGTH)


func _join() -> void:
	if typed.length() != CODE_LENGTH:
		problem = "A room code has five characters."
		rebuild()
		return
	if portal.call("need_disc"):
		return
	problem = ""
	busy = true
	rebuild()
	portal.call("join_code", typed)


func session_event(e: Dictionary) -> void:
	if int(e.type) == Session.EV_ERROR:
		busy = false
		problem = String(e.text)
		rebuild()


func session_changed(what: String) -> void:
	if what == "friends":
		rebuild()


func device_changed() -> void:
	rebuild()
	portal.call("refresh_hints")


func shortcut(name: String) -> bool:
	if name == "x" and keys != null and UI.pad_glyphs:
		keys.call("delete_one")
		return true
	if name == "start":
		_join()
		return true
	return false
