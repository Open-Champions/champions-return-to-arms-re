extends CanvasLayer
# testerkit.gd - the tester's kit in the Godot program (tools/recomp/app/testerkit.h is the native programs' and the
# library's half): F8 (or L3 + R3 held for a second on a controller) takes a bug report - the library copies the last
# 60 s of the tick log and the input record out of its rings, this script adds a picture of the window and the host's
# settings, a box takes a short text (optional; Enter saves, Escape drops) and the library zips it all into
# <data>/reports.  F9 shows or hides the build line (top right).  A crash report the library's handler wrote in the run
# before is announced at the start.  Nothing is uploaded: the player sends the zip himself.
#
# Tests: the script lines "app report open | type TEXT | enter | escape | line | info" (main.gd hands them here).

var machine: Object = null
var host: Node = null                   # main.gd: its settings for the report, its pointer
var person := true                      # not in a test window (it takes no keys); RTA_TESTERKIT=1 makes one behave as a person's
var folder := ""                        # the report being made (the box is open)
var chord_time := 0.0
var chord_done := false
var box_buttons := {}                   # controller buttons held when the box opened (they do not count as a press)
var note_until := 0.0
var line_label: Label
var note_label: Label
var box: PanelContainer
var edit: LineEdit


func setup(the_machine: Object, the_host: Node, is_person: bool) -> void:
	machine = the_machine
	host = the_host
	person = is_person or OS.get_environment("RTA_TESTERKIT") == "1"


func _ready() -> void:
	layer = 100
	line_label = Label.new()
	line_label.text = String(machine.call("build_line")) if machine != null else ""
	line_label.add_theme_font_size_override("font_size", 12)
	line_label.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85, 0.9))
	line_label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.8))
	line_label.add_theme_constant_override("shadow_offset_x", 1)
	line_label.add_theme_constant_override("shadow_offset_y", 1)
	line_label.anchor_left = 1.0
	line_label.anchor_right = 1.0
	line_label.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	line_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	line_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	line_label.visible = person and line_label.text != ""
	add_child(line_label)
	note_label = Label.new()
	note_label.add_theme_font_size_override("font_size", 16)
	note_label.add_theme_color_override("font_color", Color(0.95, 0.88, 0.56))
	note_label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.9))
	note_label.add_theme_constant_override("shadow_offset_x", 1)
	note_label.add_theme_constant_override("shadow_offset_y", 1)
	note_label.anchor_left = 0.5
	note_label.anchor_right = 0.5
	note_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	note_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	note_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	note_label.visible = false
	add_child(note_label)
	_make_box()
	_fit()
	get_viewport().size_changed.connect(_fit)
	var told := String(machine.call("report_told")) if machine != null else ""
	if told != "":
		print("rta_godot: " + told.replace("\n", " "))
		_note("crash report from last time: reports/" + told.get_slice("\n", 1).get_file(), 12.0)


func _make_box() -> void:
	box = PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.06, 0.07, 0.09, 0.92)
	style.border_color = Color(0.95, 0.88, 0.56)
	style.border_width_top = 2
	style.content_margin_left = 16
	style.content_margin_right = 16
	style.content_margin_top = 12
	style.content_margin_bottom = 12
	box.add_theme_stylebox_override("panel", style)
	box.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	box.custom_minimum_size = Vector2(560, 0)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.grow_vertical = Control.GROW_DIRECTION_BOTH
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	box.add_child(column)
	var title := Label.new()
	title.text = "Report a bug"
	title.add_theme_font_size_override("font_size", 18)
	title.add_theme_color_override("font_color", Color(0.95, 0.88, 0.56))
	column.add_child(title)
	var ask := Label.new()
	ask.text = "What happened? (optional)"
	column.add_child(ask)
	edit = LineEdit.new()
	edit.max_length = 400
	edit.placeholder_text = "e.g. the boar walked through the wall here"
	edit.text_submitted.connect(func(_t: String) -> void: _finish(true))
	column.add_child(edit)
	var keys := Label.new()
	keys.text = "Enter or Start: save      Esc or Select: drop      (the report stays on this computer)"
	keys.add_theme_font_size_override("font_size", 12)
	keys.add_theme_color_override("font_color", Color(0.6, 0.6, 0.6))
	column.add_child(keys)
	box.visible = false
	add_child(box)


# sizes for the window as it is (a 4K or Retina window has three times the pixels of 720 lines)
func _fit() -> void:
	var s := clampf(get_viewport().get_visible_rect().size.y / 720.0, 1.0, 4.0)
	line_label.add_theme_font_size_override("font_size", int(12 * s))
	# the new HUD's minimap stands in the top right corner: the line goes left of it
	var hud := false
	if host != null:
		for child in host.get_children():
			if child.scene_file_path == "res://hud/hud.tscn":
				hud = true
	line_label.offset_right = -(8 + (150 if hud else 0)) * s
	line_label.offset_left = line_label.offset_right
	line_label.offset_top = 4 * s
	note_label.add_theme_font_size_override("font_size", int(16 * s))
	note_label.offset_top = 48 * s
	box.custom_minimum_size = Vector2(560 * s, 0)
	var style := box.get_theme_stylebox("panel") as StyleBoxFlat
	if style != null:
		style.content_margin_left = 16 * s
		style.content_margin_right = 16 * s
		style.content_margin_top = 12 * s
		style.content_margin_bottom = 12 * s
		style.border_width_top = int(2 * s)
	var sizes := [18, 14, 14, 12]
	var column := box.get_child(0)
	column.add_theme_constant_override("separation", int(8 * s))
	for k in column.get_child_count():
		(column.get_child(k) as Control).add_theme_font_size_override("font_size", int(sizes[k] * s))


func is_open() -> bool:
	return folder != ""


func _note(text: String, seconds: float) -> void:
	note_label.text = text
	note_label.visible = person
	note_until = Time.get_ticks_msec() / 1000.0 + seconds


func open() -> void:
	if is_open() or machine == null:
		return
	var lines := ""
	if host != null and host.has_method("report_lines"):
		lines = String(host.call("report_lines"))
	folder = String(machine.call("report_begin", lines))
	if folder == "":
		_note("this game library has no bug report (built before it)", 5.0)
		return
	# the picture: what the window shows now (the box is not in it yet)
	var image := get_viewport().get_texture().get_image()
	if image != null:
		image.save_png(folder.path_join("screenshot.png"))
	print("rta_godot: report: taken " + folder)
	box_buttons.clear()
	for button in [JOY_BUTTON_START, JOY_BUTTON_BACK]:
		box_buttons[button] = _joy(button)
	if host != null:
		host.set("pointer_let_go", true)
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	edit.text = ""
	box.visible = person
	if person:
		edit.grab_focus()


func _finish(keep: bool) -> void:
	if not is_open():
		return
	var zip := String(machine.call("report_finish", folder, edit.text.strip_edges(), keep))
	folder = ""
	box.visible = false
	edit.release_focus()
	if not keep:
		_note("report dropped", 3.0)
	elif zip == "":
		_note("the report could not be written", 8.0)
	else:
		print("rta_godot: report: saved %s (it stays on this computer: send it yourself)" % zip)
		_note("report saved: reports/" + zip.get_file(), 8.0)


func _joy(button: int) -> bool:
	var pads := Input.get_connected_joypads()
	return pads.size() > 0 and Input.is_joy_button_pressed(pads[0], button)


func _process(delta: float) -> void:
	if note_label.visible and Time.get_ticks_msec() / 1000.0 > note_until:
		note_label.visible = false
	if not person:
		return
	# L3 + R3 held for a second: the box (once per hold)
	if _joy(JOY_BUTTON_LEFT_STICK) and _joy(JOY_BUTTON_RIGHT_STICK):
		chord_time += delta
		if chord_time >= 1.0 and not chord_done and not is_open():
			chord_done = true
			open()
	else:
		chord_time = 0.0
		chord_done = false
	if is_open():
		for button in box_buttons:
			var now := _joy(button)
			if now and not box_buttons[button]:
				_finish(button == JOY_BUTTON_START)
				return
			box_buttons[button] = now


func _input(event: InputEvent) -> void:
	if not person:
		return
	var key := event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	if is_open():
		if key.physical_keycode == KEY_ESCAPE:
			_finish(false)
			get_viewport().set_input_as_handled()
		return
	if key.physical_keycode == KEY_F8:
		open()
		get_viewport().set_input_as_handled()
	elif key.physical_keycode == KEY_F9:
		line_label.visible = not line_label.visible and line_label.text != ""
		get_viewport().set_input_as_handled()


func command(words: PackedStringArray, text: String) -> void:
	var what := words[1] if words.size() >= 2 else "info"
	match what:
		"open":
			open()
		"type":
			edit.text += text.substr(text.find("type") + 5)
		"enter":
			_finish(true)
		"escape":
			_finish(false)
		"line":
			line_label.visible = not line_label.visible
		_:
			print("rta_godot: report: box %s, line %s, note '%s', build %s" % ["open" if is_open() else "closed",
				"shown" if line_label.visible else "hidden", note_label.text if note_label.visible else "", line_label.text])
