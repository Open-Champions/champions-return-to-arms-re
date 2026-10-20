extends "res://portal/screen.gd"
# first.gd - the first start: one question, "What should friends call you?".  Nothing else:
# no account, no password.  Who the player is online is a key file the session makes by
# itself; the name is only a label and can be changed in the settings.

const Keys := preload("res://portal/keys.gd")

var typed := ""
var field: W.Field
var keys: Control
var go_button: W.Btn
var note: Label


func chrome() -> bool:
	return false


func hints() -> Array:
	if UI.pad_glyphs:
		return [hint_select("Type"), {"pad": "x", "key": "Backspace", "text": "Delete"}, {"pad": "start", "key": "Enter", "text": "Continue"}]
	return [{"pad": "a", "key": "Enter", "text": "Continue"}]


func problem() -> String:
	var t := typed.strip_edges()
	if t.to_utf8_buffer().size() < 3:
		return "At least 3 characters." if t != "" else ""
	if t.to_utf8_buffer().size() > 24:
		return "At most 24 characters."
	return ""


func valid() -> bool:
	return typed.strip_edges().to_utf8_buffer().size() >= 3 and problem() == ""


func build() -> void:
	var with_keys := UI.pad_glyphs
	var cw := minf(size.x, UI.px(920))
	var x := (size.x - cw) * 0.5
	keys = null
	var keys_h := 0.0
	if with_keys:
		keys = Keys.new()
		keys.mode = "name"
		keys.done_text = "Continue"
		keys_h = keys.wanted_size().y
	var total := UI.px(64 + 12 + 34 + 40 + 100 + 40) + (keys_h if with_keys else UI.px(24 + 68))
	var y := maxf(0.0, (size.y - total) * (0.5 if with_keys else 0.42))
	say(Rect2(x, y, cw, UI.px(64)), "What should friends call you?", 52, UI.TEXT, UI.serif_bold(), HORIZONTAL_ALIGNMENT_CENTER)
	y += UI.px(64 + 12)
	say(Rect2(x, y, cw, UI.px(34)), "That is all there is to set up. You can change it whenever you like.", 21, UI.DIM, null, HORIZONTAL_ALIGNMENT_CENTER)
	y += UI.px(34 + 40)
	field = W.Field.new("Your name", 24)
	field.large = true
	field.height = 100.0
	field.key = "name"
	field.text = typed
	var fw := minf(cw, UI.px(680))
	put(field, Rect2(x + (cw - fw) * 0.5, y, fw, UI.px(100)))
	field.edited.connect(_edited)
	field.submitted.connect(func(_t: String) -> void: _continue())
	y += UI.px(100)
	note = say(Rect2(x, y + UI.px(6), cw, UI.px(30)), problem(), 18, UI.EMBER, null, HORIZONTAL_ALIGNMENT_CENTER)
	y += UI.px(40)
	if with_keys:
		field.focus_mode = Control.FOCUS_NONE
		field.set_editing(true)
		keys.field = field
		add_child(keys)
		keys.build()
		keys.position = Vector2(roundf((size.x - keys.size.x) * 0.5), y)
		keys.done.connect(_continue)
		want_focus = want_focus if want_focus.begins_with("key_") else "key_q"
	else:
		y += UI.px(24)
		go_button = W.Btn.new("Continue", "", "primary")
		go_button.height = 68.0
		go_button.font_size = 24.0
		go_button.key = "continue"
		go_button.fixed = true
		go_button.disabled = not valid()
		var bw := UI.px(320)
		put(go_button, Rect2((size.x - bw) * 0.5, y, bw, UI.px(68)))
		go_button.activated.connect(_continue)
		want_focus = "name"


func _edited(text: String) -> void:
	typed = text
	note.text = problem()
	if go_button != null and is_instance_valid(go_button):
		go_button.set_disabled(not valid())


func device_changed() -> void:
	rebuild()
	portal.call("refresh_hints")


func shortcut(name: String) -> bool:
	if name == "x" and keys != null and UI.pad_glyphs:
		keys.call("delete_one")
		return true
	if name == "start":
		_continue()
		return true
	return false


func back() -> bool:
	return true                     # there is nothing to go back to yet


func _continue() -> void:
	if not valid():
		note.text = problem() if problem() != "" else "Type a name first."
		return
	portal.call("set_name_shown", typed.strip_edges())
	if portal.profile.game_ready() or bool(portal.options.stub_game):
		portal.call("go", "home", {}, true)
	else:
		portal.call("go", "home", {}, true)
		portal.call("go", "disc", {"first": true})
