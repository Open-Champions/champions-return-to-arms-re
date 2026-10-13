extends Control
# keys.gd - letters to press with a controller: a panel of keys that types into a Field.
# A keyboard never needs it (a Field takes typing directly); a screen shows it when the
# last input came from a controller.
#
#   mode "name"   letters in both cases, digits, a blank and a few marks
#   mode "code"   the capitals and digits a room code or a friend code is made of
#   mode "chat"   as "name"
# X / square deletes, START is "done" (the screen's shortcut() calls delete_one() / finish()).

const UI := preload("res://portal/ui.gd")
const W := preload("res://portal/widgets.gd")

signal done
const NAME_ROWS := ["1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm,.-"]
const CODE_ROWS := ["ABCDEFGH", "JKLMNPQR", "STUVWXYZ", "23456789"]

var field: Control                  # W.Field
var mode := "name"
var shift := true
var done_text := "Done"
var key_size := 62.0
var _letters: Array = []


func wanted_size() -> Vector2:
	var rows: Array = CODE_ROWS if mode == "code" else NAME_ROWS
	var cols := String(rows[0]).length()
	var gap := 8.0
	return UI.v2(cols * key_size + (cols - 1) * gap, (rows.size() + 1) * key_size + rows.size() * gap)


func build() -> void:
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_letters.clear()
	var rows: Array = CODE_ROWS if mode == "code" else NAME_ROWS
	var cols := String(rows[0]).length()
	var gap := UI.px(8)
	var k := UI.px(key_size)
	custom_minimum_size = wanted_size()
	size = custom_minimum_size
	for r in rows.size():
		var row := String(rows[r])
		for c in row.length():
			var b := _key(row[c], Rect2(c * (k + gap), r * (k + gap), k, k))
			b.key = "key_" + row[c]
			_letters.append(b)
			b.activated.connect(_type.bind(b))
	var y := rows.size() * (k + gap)
	var total := cols * k + (cols - 1) * gap
	var x := 0.0
	if mode != "code":
		var wide := (total - gap * 3.0) * 0.20
		var sh := _key("Shift", Rect2(x, y, wide, k))
		sh.key = "key_shift"
		sh.font_size = 18.0
		sh.activated.connect(func() -> void:
			shift = not shift
			_relabel())
		x += wide + gap
		var space := _key("Space", Rect2(x, y, (total - gap * 3.0) * 0.36, k))
		space.key = "key_space"
		space.font_size = 18.0
		space.activated.connect(func() -> void:
			field.call("type_text", " ")
			shift = true
			_relabel())
		x += (total - gap * 3.0) * 0.36 + gap
		var del := _key("Delete", Rect2(x, y, wide, k))
		del.key = "key_delete"
		del.font_size = 18.0
		del.activated.connect(delete_one)
		x += wide + gap
		var ok := _key(done_text, Rect2(x, y, total - x, k), "primary")
		ok.key = "key_done"
		ok.font_size = 19.0
		ok.activated.connect(finish)
	else:
		var half := (total - gap) * 0.5
		var del := _key("Delete", Rect2(0, y, half, k))
		del.key = "key_delete"
		del.font_size = 18.0
		del.activated.connect(delete_one)
		var ok := _key(done_text, Rect2(half + gap, y, half, k), "primary")
		ok.key = "key_done"
		ok.font_size = 19.0
		ok.activated.connect(finish)
	_relabel()


func _key(text: String, rect: Rect2, kind := "normal") -> W.Btn:
	var b := W.Btn.new(text, "", kind)
	b.height = key_size
	b.font_size = 24.0
	b.fixed = true
	add_child(b)
	b.position = rect.position.round()
	b.size = rect.size.round()
	return b


func _relabel() -> void:
	if mode == "code":
		return
	for b in _letters:
		var ch: String = String(b.key).substr(4)
		b.text = ch.to_upper() if shift else ch
		b.queue_redraw()


func _type(b: W.Btn) -> void:
	field.call("type_text", String(b.text))
	if mode != "code" and shift:
		shift = false
		_relabel()


func delete_one() -> void:
	field.call("backspace")
	if mode != "code" and String(field.get("text")) == "":
		shift = true
		_relabel()


func finish() -> void:
	done.emit()


func first_key() -> Control:
	return _letters[0] if not _letters.is_empty() else null
