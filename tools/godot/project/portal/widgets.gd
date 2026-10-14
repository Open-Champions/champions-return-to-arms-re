extends RefCounted
# widgets.gd - the portal's controls.  Every one is a Control drawn by code (ui.gd) that
# can take the focus: a controller's direction pad or stick moves the focus, A / cross
# presses, and a mouse does the same by pointing (pointing at a control gives it the focus,
# so there is one highlight, not two).
#
#   Focusable   the base: focus animation, pointing, `activated`
#   Btn         a button (kinds: normal, primary, ghost, danger), optional icon
#   Tile        a large choice with icon, title and one line of explanation (home)
#   Choice      a setting with a few values: left / right changes it
#   Gauge       a setting from 0 to 1 (a volume)
#   Field       a line of text; typed on a keyboard, or through the on-screen keys (osk.gd)
#   Row         a person in a list: avatar, name, what they do, the character they play, and
#               actions that left / right walks through (one focus stop per row)
#   Portrait    a character's picture: a drawn stand-in until a live viewport is handed in
#   Avatar      a round mark with initials and a presence dot
#   Hints       the line at the bottom: which button does what
#   Heading     a section heading with a fading rule

const UI := preload("res://portal/ui.gd")


class Focusable extends Control:
	signal activated
	var key := ""                   # a name the screen uses to give the focus back after a rebuild
	var disabled := false
	var ft := 0.0                   # focus, eased 0..1
	var pressed_t := 0.0

	func _init() -> void:
		focus_mode = Control.FOCUS_ALL
		mouse_filter = Control.MOUSE_FILTER_STOP
		set_process(false)

	func _ready() -> void:
		focus_entered.connect(_focus_changed)
		focus_exited.connect(_focus_changed)
		mouse_entered.connect(_pointed)
		if disabled:
			focus_mode = Control.FOCUS_NONE

	func set_disabled(value: bool) -> void:
		disabled = value
		focus_mode = Control.FOCUS_NONE if value else Control.FOCUS_ALL
		queue_redraw()

	func _pointed() -> void:
		if not disabled and focus_mode != Control.FOCUS_NONE and not has_focus():
			grab_focus()

	func _focus_changed() -> void:
		set_process(true)
		queue_redraw()

	func _process(delta: float) -> void:
		var target := 1.0 if has_focus() else 0.0
		ft = move_toward(ft, target, delta / 0.11)
		pressed_t = move_toward(pressed_t, 0.0, delta / 0.16)
		queue_redraw()
		if is_equal_approx(ft, target) and pressed_t <= 0.0:
			set_process(false)

	func press() -> void:
		if disabled:
			return
		pressed_t = 1.0
		set_process(true)
		activated.emit()

	func _gui_input(event: InputEvent) -> void:
		if disabled:
			return
		var mouse := event as InputEventMouseButton
		if mouse != null and mouse.button_index == MOUSE_BUTTON_LEFT and not mouse.pressed and Rect2(Vector2.ZERO, size).has_point(mouse.position):
			accept_event()
			_clicked(mouse.position)
		elif event.is_action_pressed("ui_accept") and not event.is_echo():
			accept_event()
			press()

	func _clicked(_at: Vector2) -> void:
		press()

	func eased() -> float:
		return ft * ft * (3.0 - 2.0 * ft)


class Btn extends Focusable:
	var text := ""
	var icon := ""
	var kind := "normal"
	var font_size := 22.0
	var height := 60.0
	var badge := ""                 # a small count at the right (requests waiting)
	var align_left := false
	var fill_width := false
	var fixed := false              # the size is given from outside (a key of the on-screen keys)
	var selected := false           # a tab that is open: a gold mark at its left

	func _init(p_text := "", p_icon := "", p_kind := "normal") -> void:
		super()
		text = p_text
		icon = p_icon
		kind = p_kind

	func _ready() -> void:
		super()
		fit()

	func fit() -> void:
		if fixed:
			queue_redraw()
			return
		var w := UI.px(28.0) * 2.0
		if text != "":
			w += UI.text_width(text, UI.bold(), font_size)
		if icon != "":
			w += UI.px(height * 0.42) + (UI.px(12) if text != "" else 0.0)
			if text == "":
				w = UI.px(height)
		if badge != "":
			w += UI.px(40)
		custom_minimum_size = Vector2(ceilf(w), UI.px(height))
		queue_redraw()

	func set_text(value: String) -> void:
		text = value
		fit()

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(minf(height * 0.5, 14.0))
		var e := eased()
		var fill := UI.PANEL_UP.lerp(UI.PANEL_HOT, e)
		var ink := UI.TEXT
		var line := UI.LINE_STRONG
		match kind:
			"primary":
				fill = UI.GOLD.lerp(UI.GOLD_HI, e * 0.8)
				ink = UI.INK
				line = Color(1, 1, 1, 0.25)
			"ghost":
				fill = Color(UI.PANEL_UP.r, UI.PANEL_UP.g, UI.PANEL_UP.b, 0.0).lerp(UI.PANEL_HOT, e)
				line = Color(1, 1, 1, 0.10 + 0.08 * e)
				ink = UI.DIM.lerp(UI.TEXT, e)
			"danger":
				fill = Color(0.30, 0.10, 0.10).lerp(Color(0.52, 0.15, 0.14), e)
				line = Color(UI.RED.r, UI.RED.g, UI.RED.b, 0.5)
		if disabled:
			if kind == "primary":
				# what will be the one thing to press, not yet: an outline in its colour
				fill = Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.07)
				ink = Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.50)
				line = Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.30)
			else:
				fill = Color(fill.r, fill.g, fill.b, fill.a * 0.35)
				ink = Color(ink.r, ink.g, ink.b, 0.35)
				line = Color(1, 1, 1, 0.05)
		if pressed_t > 0.0:
			r = r.grow(-UI.px(2) * pressed_t)
		UI.focus_glow(self, r, radius, e)
		if UI.skinned("surface", [self, "button_" + kind, r, radius, e, disabled]):
			if kind == "primary":
				ink = UI.TEXT if not disabled else Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.50)
		else:
			draw_style_box(UI.box(radius, fill, line, maxf(1.0, UI.px(1))), r)
			if kind == "primary" and not disabled:
				UI.sheen(self, r, radius, 0.22)
			elif not disabled:
				UI.sheen(self, r, radius, 0.035)
		UI.focus_ring(self, r, radius, e)
		if selected:
			draw_style_box(UI.box(UI.px(2), UI.GOLD), Rect2(r.position.x + UI.px(8), r.position.y + r.size.y * 0.25, UI.px(4), r.size.y * 0.5))
			ink = UI.GOLD_HI if kind != "primary" else ink
		var pad := UI.px(28.0)
		var x := r.position.x + pad
		var icon_size := UI.px(height * 0.42)
		var content := 0.0
		if icon != "":
			content += icon_size + (UI.px(12) if text != "" else 0.0)
		if text != "":
			content += UI.text_width(text, UI.bold(), font_size)
		if text == "":
			x = r.position.x + (r.size.x - icon_size) * 0.5
		elif not align_left and not fill_width:
			x = r.position.x + maxf(pad * 0.5, (r.size.x - content - (UI.px(40) if badge != "" else 0.0)) * 0.5)
		if icon != "":
			UI.icon(self, icon, Rect2(x, r.position.y + (r.size.y - icon_size) * 0.5, icon_size, icon_size), ink)
			x += icon_size + UI.px(12)
		if text != "":
			UI.text(self, Rect2(x, r.position.y, r.end.x - x - pad * 0.4 - (UI.px(40) if badge != "" else 0.0), r.size.y), text, UI.bold(), font_size, ink)
		if badge != "":
			var bw := maxf(UI.px(30), UI.text_width(badge, UI.bold(), 16) + UI.px(16))
			var b := Rect2(r.end.x - bw - UI.px(14), r.position.y + (r.size.y - UI.px(28)) * 0.5, bw, UI.px(28))
			draw_style_box(UI.box(b.size.y * 0.5, UI.EMBER), b)
			UI.text(self, b, badge, UI.bold(), 16, Color.WHITE, HORIZONTAL_ALIGNMENT_CENTER)


class Tile extends Focusable:
	var title := ""
	var note := ""
	var icon := ""
	var accent := false             # the first choice: a warmer fill
	var tag := ""                   # a small label at the right ("3 online")
	var tag_colour := UI.GREEN

	func _init(p_title := "", p_note := "", p_icon := "") -> void:
		super()
		title = p_title
		note = p_note
		icon = p_icon

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(16)
		var e := eased()
		if pressed_t > 0.0:
			r = r.grow(-UI.px(3) * pressed_t)
		var fill := UI.PANEL.lerp(UI.PANEL_HOT, e)
		var alpha := 0.80 + 0.14 * e
		if disabled:
			alpha = 0.45
		UI.focus_glow(self, r, radius, e)
		if not UI.skinned("surface", [self, "tile", r, radius, e, disabled]):
			draw_style_box(UI.box(radius, Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, Color(0, 0, 0, 0.28), UI.px(16)), r)
			draw_style_box(UI.box(radius, Color(fill.r, fill.g, fill.b, alpha), UI.LINE if e < 0.5 else Color(1, 1, 1, 0.02), maxf(1.0, UI.px(1))), r)
			UI.sheen(self, r, radius, 0.03 + 0.03 * e)
		# a warm wash from the left on the focused tile
		if e > 0.01:
			var c := Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.10 * e)
			var n := Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.0)
			var inset := Vector2(radius * 0.35, maxf(2.0, UI.px(3)))
			var a := r.position + inset
			var z := r.size - inset * 2.0
			draw_polygon(PackedVector2Array([a, a + Vector2(z.x * 0.7, 0), a + Vector2(z.x * 0.7, z.y), a + Vector2(0, z.y)]), PackedColorArray([c, n, n, c]))
		UI.focus_ring(self, r, radius, e)
		var h := r.size.y
		var medal := minf(h - UI.px(40), UI.px(92))
		var mrect := Rect2(r.position.x + UI.px(28), r.position.y + (h - medal) * 0.5, medal, medal)
		var ring := UI.GOLD.lerp(UI.GOLD_HI, e) if not disabled else UI.FAINT
		if not UI.skinned("surface", [self, "medal", mrect, medal * 0.5, e, disabled]):
			draw_style_box(UI.box(medal * 0.5, Color(ring.r, ring.g, ring.b, 0.10 + 0.08 * e), Color(ring.r, ring.g, ring.b, 0.55 + 0.45 * e), maxf(1.5, UI.px(2))), mrect)
		UI.icon(self, icon, mrect.grow(-medal * 0.24), ring)
		var x := mrect.end.x + UI.px(28)
		var right := r.end.x - UI.px(30)
		var chevron := UI.px(26)
		UI.icon(self, "chevron", Rect2(right - chevron, r.position.y + (h - chevron) * 0.5, chevron, chevron), Color(1, 1, 1, 0.18 + 0.6 * e))
		right -= chevron + UI.px(16)
		if tag != "":
			var tw := UI.text_width(tag, UI.bold(), 17) + UI.px(40)
			var trect := Rect2(right - tw, r.position.y + (h - UI.px(34)) * 0.5, tw, UI.px(34))
			draw_style_box(UI.box(trect.size.y * 0.5, Color(tag_colour.r, tag_colour.g, tag_colour.b, 0.13), Color(tag_colour.r, tag_colour.g, tag_colour.b, 0.45), 1), trect)
			UI.dot(self, trect.position + Vector2(UI.px(17), trect.size.y * 0.5), UI.px(4.5), tag_colour, false)
			UI.text(self, Rect2(trect.position.x + UI.px(28), trect.position.y, tw - UI.px(34), trect.size.y), tag, UI.bold(), 17, tag_colour)
			right = trect.position.x - UI.px(16)
		var ink := UI.TEXT if not disabled else UI.FAINT
		var title_h := UI.line_height(UI.serif_bold(), 34)
		var note_h := UI.line_height(UI.sans(), 19)
		var top := r.position.y + (h - title_h - note_h - UI.px(2)) * 0.5
		UI.text(self, Rect2(x, top, right - x, title_h), title, UI.serif_bold(), 34, ink)
		UI.text(self, Rect2(x, top + title_h + UI.px(2), right - x, note_h), note, UI.sans(), 19, UI.DIM if not disabled else UI.FAINT)


class Choice extends Focusable:
	signal changed(index: int)
	var title := ""
	var note := ""
	var options: PackedStringArray = PackedStringArray()
	var index := 0
	var locked := false             # shown, cannot be changed (a guest sees the host's choice)

	func _init(p_title := "", p_options: PackedStringArray = PackedStringArray(), p_index := 0, p_note := "") -> void:
		super()
		title = p_title
		options = p_options
		index = p_index
		note = p_note

	func _ready() -> void:
		super()
		custom_minimum_size = Vector2(UI.px(360), UI.px(82 if note != "" else 64))

	func step(by: int) -> void:
		if locked or options.size() < 2:
			return
		index = posmod(index + by, options.size())
		pressed_t = 0.6
		set_process(true)
		changed.emit(index)
		queue_redraw()

	func _gui_input(event: InputEvent) -> void:
		if event.is_action_pressed("ui_left"):
			accept_event()
			step(-1)
		elif event.is_action_pressed("ui_right"):
			accept_event()
			step(1)
		else:
			super(event)

	func press() -> void:
		step(1)

	func _clicked(at: Vector2) -> void:
		step(-1 if at.x < size.x * 0.62 and at.x > size.x * 0.45 else 1)

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(12)
		var e := eased()
		UI.focus_glow(self, r, radius, e)
		if not UI.skinned("surface", [self, "choice", r, radius, e, false]):
			draw_style_box(UI.box(radius, UI.PANEL_UP.lerp(UI.PANEL_HOT, e), UI.LINE, maxf(1.0, UI.px(1))), r)
		UI.focus_ring(self, r, radius, e)
		var pad := UI.px(24)
		var left := Rect2(r.position.x + pad, r.position.y, r.size.x * 0.5 - pad, r.size.y)
		if note != "":
			var th := UI.line_height(UI.bold(), 21)
			var nh := UI.line_height(UI.sans(), 16)
			var top := (r.size.y - th - nh) * 0.5
			UI.text(self, Rect2(left.position.x, top, left.size.x, th), title, UI.bold(), 21, UI.TEXT)
			UI.text(self, Rect2(left.position.x, top + th, left.size.x, nh), note, UI.sans(), 16, UI.DIM)
		else:
			UI.text(self, left, title, UI.bold(), 21, UI.TEXT)
		var value := options[index] if index >= 0 and index < options.size() else ""
		var arrow := UI.px(20)
		var right := r.end.x - pad
		var can := not locked and options.size() > 1
		var vrect := Rect2(r.position.x + r.size.x * 0.5, r.position.y, r.size.x * 0.5 - pad, r.size.y)
		if can:
			UI.icon(self, "chevron", Rect2(right - arrow, (r.size.y - arrow) * 0.5, arrow, arrow), Color(1, 1, 1, 0.25 + 0.6 * e))
			UI.icon(self, "chevron_left", Rect2(vrect.position.x, (r.size.y - arrow) * 0.5, arrow, arrow), Color(1, 1, 1, 0.25 + 0.6 * e))
			vrect = Rect2(vrect.position.x + arrow + UI.px(8), vrect.position.y, vrect.size.x - (arrow + UI.px(8)) * 2.0, vrect.size.y)
		UI.text(self, vrect, value, UI.bold(), 21, UI.GOLD.lerp(UI.GOLD_HI, e) if can else UI.DIM, HORIZONTAL_ALIGNMENT_CENTER if can else HORIZONTAL_ALIGNMENT_RIGHT)


class Gauge extends Focusable:
	signal changed(value: float)
	var title := ""
	var value := 1.0
	var note := ""

	func _init(p_title := "", p_value := 1.0, p_note := "") -> void:
		super()
		title = p_title
		value = p_value
		note = p_note

	func _ready() -> void:
		super()
		custom_minimum_size = Vector2(UI.px(360), UI.px(82 if note != "" else 64))

	func step(by: float) -> void:
		var v := clampf(snappedf(value + by, 0.05), 0.0, 1.0)
		if v != value:
			value = v
			changed.emit(value)
			queue_redraw()

	func _gui_input(event: InputEvent) -> void:
		if event.is_action_pressed("ui_left", true):
			accept_event()
			step(-0.05)
		elif event.is_action_pressed("ui_right", true):
			accept_event()
			step(0.05)
		else:
			var mouse := event as InputEventMouseButton
			var motion := event as InputEventMouseMotion
			if (mouse != null and mouse.pressed and mouse.button_index == MOUSE_BUTTON_LEFT) or (motion != null and (motion.button_mask & MOUSE_BUTTON_MASK_LEFT) != 0):
				var at: Vector2 = (event as InputEventMouse).position
				var bar := _bar()
				if at.x > bar.position.x - UI.px(16):
					accept_event()
					value = clampf(snappedf((at.x - bar.position.x) / bar.size.x, 0.05), 0.0, 1.0)
					changed.emit(value)
					queue_redraw()

	func _bar() -> Rect2:
		var pad := UI.px(24)
		var w := size.x * 0.5 - pad - UI.px(64)
		return Rect2(size.x * 0.5, (size.y - UI.px(10)) * 0.5, w, UI.px(10))

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(12)
		var e := eased()
		UI.focus_glow(self, r, radius, e)
		if not UI.skinned("surface", [self, "gauge", r, radius, e, false]):
			draw_style_box(UI.box(radius, UI.PANEL_UP.lerp(UI.PANEL_HOT, e), UI.LINE, maxf(1.0, UI.px(1))), r)
		UI.focus_ring(self, r, radius, e)
		var pad := UI.px(24)
		var left := Rect2(pad, 0, size.x * 0.5 - pad * 2.0, size.y)
		if note != "":
			var th := UI.line_height(UI.bold(), 21)
			var nh := UI.line_height(UI.sans(), 16)
			var top := (r.size.y - th - nh) * 0.5
			UI.text(self, Rect2(left.position.x, top, left.size.x, th), title, UI.bold(), 21, UI.TEXT)
			UI.text(self, Rect2(left.position.x, top + th, left.size.x, nh), note, UI.sans(), 16, UI.DIM)
		else:
			UI.text(self, left, title, UI.bold(), 21, UI.TEXT)
		var bar := _bar()
		draw_style_box(UI.box(bar.size.y * 0.5, Color(0, 0, 0, 0.45)), bar)
		if value > 0.0:
			draw_style_box(UI.box(bar.size.y * 0.5, UI.GOLD.lerp(UI.GOLD_HI, e)), Rect2(bar.position, Vector2(maxf(bar.size.y, bar.size.x * value), bar.size.y)))
		var knob := bar.position + Vector2(bar.size.x * value, bar.size.y * 0.5)
		draw_circle(knob, UI.px(9 + 2 * e), UI.TEXT, true, -1.0, true)
		UI.text(self, Rect2(bar.end.x + UI.px(12), 0, UI.px(52), size.y), "%d" % int(roundf(value * 100.0)), UI.bold(), 20, UI.DIM, HORIZONTAL_ALIGNMENT_RIGHT)


class Field extends Focusable:
	signal submitted(text: String)
	signal edited(text: String)
	signal wants_keys                # a controller pressed A: the screen opens the on-screen keys
	var text := ""
	var placeholder := ""
	var max_length := 24
	var upper := false              # codes: capitals and digits only
	var large := false              # a code or a name, set big
	var height := 64.0
	var caret_t := 0.0
	var editing := false            # the on-screen keys are typing into it: caret and ring stay on

	func _init(p_placeholder := "", p_max := 24) -> void:
		super()
		placeholder = p_placeholder
		max_length = p_max

	func _ready() -> void:
		super()
		custom_minimum_size = Vector2(UI.px(320), UI.px(height))

	func _process(delta: float) -> void:
		super(delta)
		if has_focus() or editing:
			caret_t += delta
			set_process(true)
			queue_redraw()

	func set_text(value: String) -> void:
		text = _clean(value)
		queue_redraw()

	func set_editing(value: bool) -> void:
		editing = value
		set_process(true)
		queue_redraw()

	func _clean(value: String) -> String:
		var out := ""
		for ch in value:
			var c := ch.unicode_at(0)
			if c < 32:
				continue
			if upper:
				ch = ch.to_upper()
				if not ((ch >= "A" and ch <= "Z") or (ch >= "0" and ch <= "9") or ch == "-"):
					continue
			out += ch
		while out.to_utf8_buffer().size() > max_length:
			out = out.substr(0, out.length() - 1)
		return out

	func type_text(more: String) -> void:
		var before := text
		text = _clean(text + more)
		if text != before:
			caret_t = 0.0
			edited.emit(text)
			queue_redraw()

	func backspace() -> void:
		if text != "":
			text = text.substr(0, text.length() - 1)
			caret_t = 0.0
			edited.emit(text)
			queue_redraw()

	func _gui_input(event: InputEvent) -> void:
		var k := event as InputEventKey
		if k != null and k.pressed:
			if k.keycode == KEY_ENTER or k.keycode == KEY_KP_ENTER:
				accept_event()
				if not k.echo:
					submitted.emit(text)
			elif k.keycode == KEY_BACKSPACE:
				accept_event()
				backspace()
			elif k.keycode == KEY_V and (k.meta_pressed or k.ctrl_pressed):
				accept_event()
				type_text(DisplayServer.clipboard_get())
			elif k.unicode >= 32 and not k.ctrl_pressed and not k.meta_pressed:
				accept_event()
				type_text(String.chr(k.unicode))
			return
		var mouse := event as InputEventMouseButton
		if mouse != null and mouse.button_index == MOUSE_BUTTON_LEFT and not mouse.pressed:
			accept_event()
			grab_focus()
		elif event is InputEventJoypadButton and event.is_action_pressed("ui_accept"):
			accept_event()
			wants_keys.emit()

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(12)
		var e := eased()
		if editing:
			e = 1.0
		UI.focus_glow(self, r, radius, e)
		if not UI.skinned("surface", [self, "field", r, radius, e, false]):
			draw_style_box(UI.box(radius, Color(0.02, 0.024, 0.036, 0.85), UI.LINE_STRONG, maxf(1.0, UI.px(1))), r)
		UI.focus_ring(self, r, radius, e)
		var pad := UI.px(22)
		var font := UI.bold()
		var fsize := 24.0
		var align := HORIZONTAL_ALIGNMENT_LEFT
		if large:
			font = UI.spaced(UI.bold(), 6.0 if upper else 1.0)
			fsize = height * 0.46
			align = HORIZONTAL_ALIGNMENT_CENTER
		var area := Rect2(pad, 0, size.x - pad * 2.0, size.y)
		var w := 0.0
		var ghost_w := 0.0
		if text == "":
			ghost_w = UI.text(self, area, placeholder, UI.sans() if not large else font, fsize if not large else fsize * 0.62, UI.FAINT, align)
		else:
			w = UI.text(self, area, text, font, fsize, UI.TEXT, align)
		if (has_focus() or editing) and fmod(caret_t, 1.0) < 0.55:
			var x := area.position.x + w + UI.px(3)
			if align == HORIZONTAL_ALIGNMENT_CENTER:
				x = area.position.x + (area.size.x + w) * 0.5 + UI.px(3)
				if text == "":
					x = area.position.x + (area.size.x - ghost_w) * 0.5 - UI.px(8)
			elif text == "":
				x = area.position.x - UI.px(7)
			var ch := UI.px(fsize * 1.1)
			draw_rect(Rect2(x, (size.y - ch) * 0.5, maxf(2.0, UI.px(2.5)), ch), UI.GOLD)


class Avatar extends Control:
	var who := ""                   # a name: the initials
	var seed_key := ""              # what the colour is taken from (the id)
	var presence := -1              # -1 no dot; 0 offline, 1 online, 2 in a room, 3 in a game

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		draw_avatar(self, Rect2(Vector2.ZERO, size), who, seed_key, presence)

	static func presence_colour(p: int) -> Color:
		match p:
			1: return UI.GREEN
			2: return UI.BLUE
			3: return UI.VIOLET
		return UI.FAINT

	static func draw_avatar(ci: CanvasItem, rect: Rect2, name: String, seed_text: String, p: int) -> void:
		var d := minf(rect.size.x, rect.size.y)
		var c := rect.position + rect.size * 0.5
		var tint := UI.tint_of(seed_text if seed_text != "" else name, 0.40, 0.62)
		var dark := UI.tint_of(seed_text if seed_text != "" else name, 0.50, 0.30)
		if p == 0:
			tint = tint.lerp(Color(0.3, 0.32, 0.36), 0.7)
			dark = dark.lerp(Color(0.15, 0.16, 0.19), 0.7)
		ci.draw_circle(c, d * 0.5, dark, true, -1.0, true)
		ci.draw_circle(c + Vector2(0, -d * 0.06), d * 0.40, Color(tint.r, tint.g, tint.b, 0.55), true, -1.0, true)
		ci.draw_arc(c, d * 0.5 - 0.5, 0.0, TAU, 40, Color(1, 1, 1, 0.16), maxf(1.0, UI.px(1.5)), true)
		var ini := UI.initials(name)
		var size_design := d / UI.s * (0.40 if ini.length() < 2 else 0.33)
		UI.text(ci, rect, ini, UI.bold(), size_design, Color(1, 1, 1, 0.95 if p != 0 else 0.6), HORIZONTAL_ALIGNMENT_CENTER)
		if p >= 0:
			var at := c + Vector2(d * 0.36, d * 0.36)
			ci.draw_circle(at, d * 0.17, UI.BG_BOTTOM, true, -1.0, true)
			if p == 0:
				ci.draw_arc(at, d * 0.095, 0.0, TAU, 16, UI.FAINT, maxf(1.5, d * 0.04), true)
			else:
				ci.draw_circle(at, d * 0.115, presence_colour(p), true, -1.0, true)


class Portrait extends Control:
	# A character's picture.  Until the scene that shows the game can hand in a live view of
	# one character (set `texture`), this draws a stand-in: a hooded figure before a ring of
	# light, in a colour taken from the class's name.
	var character := {}             # name, cls, level
	var texture: Texture2D
	var empty_text := ""
	var framed := true
	var t := 0.0

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _process(delta: float) -> void:
		t += delta
		queue_redraw()

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(14)
		var key := String(character.get("cls", ""))
		var has := String(character.get("name", "")) != ""
		var hue := UI.hue_of(key) if key != "" else 0.10
		var deep := Color.from_hsv(hue, 0.55, 0.20)
		var glow := Color.from_hsv(hue, 0.50, 0.95)
		if not has:
			deep = Color(0.08, 0.09, 0.12)
			glow = Color(0.6, 0.62, 0.7)
		if UI.skinned("portrait", [self, r, character, framed, empty_text]):
			return
		if framed:
			draw_style_box(UI.box(radius, Color(0.02, 0.022, 0.034, 0.9), UI.LINE_STRONG, maxf(1.0, UI.px(1))), r)
		var inner := r.grow(-UI.px(3)) if framed else r
		if texture != null:
			draw_texture_rect(texture, inner, false)
			return
		# the ground: the class colour rising from below
		var a := inner.position
		var z := inner.size
		var low := Color(deep.r, deep.g, deep.b, 0.95)
		var high := Color(deep.r * 0.25, deep.g * 0.25, deep.b * 0.3, 0.0)
		var inset := radius * 0.4
		draw_polygon(PackedVector2Array([a + Vector2(inset, inset), a + Vector2(z.x - inset, inset), a + z - Vector2(inset, inset), a + Vector2(inset, z.y - inset)]),
			PackedColorArray([high, high, low, low]))
		var c := a + Vector2(z.x * 0.5, z.y * 0.46)
		var u := minf(z.x, z.y)
		# the ring of light: three arcs, turning slowly
		var turn := t * 0.12
		for k in 3:
			var rr := u * (0.30 + 0.055 * k)
			var alpha := 0.34 - 0.10 * k
			var start := turn * (1.0 if k % 2 == 0 else -1.4) + k * 2.1
			draw_arc(c, rr, start, start + PI * 1.25, 48, Color(glow.r, glow.g, glow.b, alpha), maxf(1.0, UI.px(2.0 - 0.5 * k)), true)
			draw_arc(c, rr, start + PI * 1.4, start + PI * 1.85, 24, Color(glow.r, glow.g, glow.b, alpha * 0.6), maxf(1.0, UI.px(2.0 - 0.5 * k)), true)
		draw_circle(c, u * 0.27, Color(glow.r, glow.g, glow.b, 0.07), true, -1.0, true)
		draw_circle(c, u * 0.18, Color(glow.r, glow.g, glow.b, 0.07), true, -1.0, true)
		# the figure: a hood and a cloak, dark against the light
		var ink := Color(0.035, 0.038, 0.055, 0.96) if has else Color(0.10, 0.11, 0.14, 0.9)
		var fig := PackedVector2Array()
		var base_y := a.y + z.y - inset
		var shoulder := u * 0.36
		var top := c.y - u * 0.25
		for k in 25:
			var ang := PI + PI * k / 24.0
			fig.append(Vector2(c.x + cos(ang) * u * 0.125, top + u * 0.13 + sin(ang) * u * 0.155))
		fig.append(Vector2(c.x + u * 0.15, top + u * 0.24))
		fig.append(Vector2(c.x + shoulder * 0.82, top + u * 0.33))
		fig.append(Vector2(c.x + shoulder, base_y))
		fig.append(Vector2(c.x - shoulder, base_y))
		fig.append(Vector2(c.x - shoulder * 0.82, top + u * 0.33))
		fig.append(Vector2(c.x - u * 0.15, top + u * 0.24))
		draw_colored_polygon(fig, ink)
		# the rim of light on the hood
		var rim := PackedVector2Array()
		for k in 13:
			var ang := PI * 1.12 + PI * 0.5 * k / 12.0
			rim.append(Vector2(c.x + cos(ang) * u * 0.125, top + u * 0.13 + sin(ang) * u * 0.155))
		draw_polyline(rim, Color(glow.r, glow.g, glow.b, 0.55 if has else 0.2), maxf(1.0, UI.px(1.5)), true)
		if not has and empty_text != "":
			UI.text(self, Rect2(a.x, a.y + z.y * 0.80, z.x, z.y * 0.14), empty_text, UI.sans(), 18, UI.DIM, HORIZONTAL_ALIGNMENT_CENTER)


class Row extends Focusable:
	# A person in a list.  The row is one focus stop; left / right walks through `actions`
	# (dictionaries: id, text, icon, kind) and A presses the one selected - the first by default.
	signal action(id: String)
	var who := ""
	var seed_key := ""
	var presence := -1
	var status := ""
	var status_colour := UI.DIM
	var detail := ""                # the character they play: "Name - level 12 Class"
	var actions: Array = []
	var selected := 0
	var height := 88.0
	var compact := false

	func _ready() -> void:
		super()
		custom_minimum_size = Vector2(UI.px(300), UI.px(height))
		focus_entered.connect(func() -> void: selected = 0)

	func _gui_input(event: InputEvent) -> void:
		if event.is_action_pressed("ui_left") and selected > 0:
			accept_event()
			selected -= 1
			queue_redraw()
		elif event.is_action_pressed("ui_right") and selected < actions.size() - 1:
			accept_event()
			selected += 1
			queue_redraw()
		elif event is InputEventMouseMotion:
			var k := _action_at((event as InputEventMouseMotion).position)
			if k >= 0 and k != selected:
				selected = k
				queue_redraw()
		else:
			super(event)

	func press() -> void:
		if actions.is_empty():
			return
		pressed_t = 1.0
		set_process(true)
		action.emit(String(actions[clampi(selected, 0, actions.size() - 1)].id))

	func _clicked(at: Vector2) -> void:
		var k := _action_at(at)
		if k >= 0:
			selected = k
			press()
		elif not has_focus():
			grab_focus()

	func _chip_rects() -> Array:
		var rects := []
		var x := size.x - UI.px(16)
		var h := UI.px(46)
		for k in range(actions.size() - 1, -1, -1):
			var a: Dictionary = actions[k]
			var w := UI.px(44)
			if String(a.get("text", "")) != "":
				w = UI.text_width(String(a.text), UI.bold(), 18) + UI.px(36) + (UI.px(26) if String(a.get("icon", "")) != "" else 0.0)
			rects.push_front(Rect2(x - w, (size.y - h) * 0.5, w, h))
			x -= w + UI.px(8)
		return rects

	func _action_at(at: Vector2) -> int:
		var rects := _chip_rects()
		for k in rects.size():
			if (rects[k] as Rect2).has_point(at):
				return k
		return -1

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(12)
		var e := eased()
		var fill := UI.PANEL_UP.lerp(UI.PANEL_HOT, e)
		UI.focus_glow(self, r, radius, e)
		if not UI.skinned("surface", [self, "row", r, radius, e, false]):
			draw_style_box(UI.box(radius, Color(fill.r, fill.g, fill.b, 0.45 + 0.55 * e), Color(1, 1, 1, 0.05), maxf(1.0, UI.px(1))), r)
		UI.focus_ring(self, r, radius, e)
		var av := UI.px(height - 30.0)
		var arect := Rect2(UI.px(16), (size.y - av) * 0.5, av, av)
		Avatar.draw_avatar(self, arect, who, seed_key, presence)
		var x := arect.end.x + UI.px(18)
		var rects := _chip_rects()
		var right := size.x - UI.px(18)
		if e > 0.02 and not rects.is_empty():
			right = (rects[0] as Rect2).position.x - UI.px(14)
		var nh := UI.line_height(UI.bold(), 23)
		var sh := UI.line_height(UI.sans(), 17)
		var lines := 1 + (1 if status != "" or detail != "" else 0)
		var top := (size.y - nh - (sh if lines > 1 else 0.0)) * 0.5
		UI.text(self, Rect2(x, top, right - x, nh), who, UI.bold(), 23, UI.TEXT if presence != 0 else UI.DIM)
		if lines > 1:
			var used := 0.0
			if status != "":
				used = UI.text(self, Rect2(x, top + nh, right - x, sh), status, UI.bold(), 17, status_colour)
			if detail != "":
				var dx := x + used + (UI.px(14) if used > 0.0 else 0.0)
				if used > 0.0:
					draw_circle(Vector2(x + used + UI.px(7), top + nh + sh * 0.55), maxf(1.0, UI.px(2)), UI.FAINT)
				UI.text(self, Rect2(dx, top + nh, right - dx, sh), detail, UI.sans(), 17, UI.DIM if presence != 0 else UI.FAINT)
		if e > 0.02:
			for k in rects.size():
				var a: Dictionary = actions[k]
				var chip: Rect2 = rects[k]
				var on := k == selected
				var kind := String(a.get("kind", "normal"))
				var cf := Color(1, 1, 1, 0.07)
				var ink := UI.TEXT
				var line := Color(1, 1, 1, 0.14)
				if on:
					cf = UI.GOLD if kind != "danger" else UI.RED
					ink = UI.INK if kind != "danger" else Color.WHITE
					line = Color(1, 1, 1, 0.3)
				cf.a *= e
				ink.a *= e
				line.a *= e
				draw_style_box(UI.box(chip.size.y * 0.5, cf, line, 1), chip)
				var cx := chip.position.x + UI.px(18)
				var icon_name := String(a.get("icon", ""))
				var label := String(a.get("text", ""))
				if icon_name != "":
					var isz := UI.px(20)
					if label == "":
						cx = chip.position.x + (chip.size.x - isz) * 0.5
					UI.icon(self, icon_name, Rect2(cx, chip.position.y + (chip.size.y - isz) * 0.5, isz, isz), ink)
					cx += isz + UI.px(6)
				if label != "":
					UI.text(self, Rect2(cx, chip.position.y, chip.end.x - cx - UI.px(10), chip.size.y), label, UI.bold(), 18, ink)


class Heading extends Control:
	var text := ""
	var count := ""
	var size_px := 17.0

	func _init(p_text := "", p_count := "") -> void:
		text = p_text
		count = p_count
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _ready() -> void:
		custom_minimum_size = Vector2(UI.px(120), UI.px(44))

	func _draw() -> void:
		var font := UI.spaced(UI.bold(), 2.5)
		var w := UI.text(self, Rect2(0, 0, size.x, size.y - UI.px(10)), text.to_upper(), font, size_px, UI.GOLD, HORIZONTAL_ALIGNMENT_LEFT, 0.7)
		if count != "":
			UI.text(self, Rect2(w + UI.px(12), 0, size.x - w - UI.px(12), size.y - UI.px(10)), count, UI.bold(), size_px, UI.FAINT, HORIZONTAL_ALIGNMENT_LEFT, 0.7)
		UI.fade_rule(self, Vector2(0, size.y - UI.px(6)), size.x, UI.GOLD, 0.35)


class Hints extends Control:
	# items: dictionaries {pad, key, text}; pad is a, b, x, y, start, lb, rb, dpad, lr
	var items: Array = []
	var left_text := ""
	var left_colour := UI.DIM
	var style := "xbox"             # or "ps": the shapes instead of the letters

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func set_items(value: Array) -> void:
		items = value
		queue_redraw()

	func _draw() -> void:
		var h := size.y
		var x := size.x
		var g := UI.px(34)
		for k in range(items.size() - 1, -1, -1):
			var it: Dictionary = items[k]
			var label := String(it.get("text", ""))
			var tw := UI.text_width(label, UI.sans(), 19)
			x -= tw
			UI.text(self, Rect2(x, 0, tw + 2.0, h), label, UI.sans(), 19, UI.DIM)
			x -= UI.px(10)
			if UI.pad_glyphs:
				var gw := glyph_width(String(it.get("pad", "a")), style, g)
				x -= gw
				draw_glyph(self, Rect2(x, (h - g) * 0.5, gw, g), String(it.get("pad", "a")), style)
			else:
				var cap := String(it.get("key", "Enter"))
				var cw := maxf(g, UI.text_width(cap, UI.bold(), 15) + UI.px(20))
				x -= cw
				var crect := Rect2(x, (h - UI.px(30)) * 0.5, cw, UI.px(30))
				draw_style_box(UI.box(UI.px(7), Color(1, 1, 1, 0.07), Color(1, 1, 1, 0.22), 1), crect)
				UI.text(self, crect, cap, UI.bold(), 15, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
			x -= UI.px(30)
		if left_text != "":
			UI.dot(self, Vector2(UI.px(7), h * 0.5), UI.px(5), left_colour)
			UI.text(self, Rect2(UI.px(24), 0, maxf(10.0, x - UI.px(24)), h), left_text, UI.sans(), 18, UI.DIM)

	static func glyph_label(name: String, glyph_style: String) -> String:
		if glyph_style == "ps":
			return {"start": "OPTIONS", "lb": "L1", "rb": "R1", "lr": "L1  R1", "dpad": "D-PAD", "back": "SHARE"}.get(name, name.to_upper()) as String
		return {"start": "START", "lb": "LB", "rb": "RB", "lr": "LB  RB", "dpad": "D-PAD", "back": "BACK"}.get(name, name.to_upper()) as String

	static func glyph_width(name: String, glyph_style: String, round_size: float) -> float:
		if name in ["a", "b", "x", "y"]:
			return round_size
		return UI.text_width(glyph_label(name, glyph_style), UI.bold(), 13) + UI.px(18)

	static func draw_glyph(ci: CanvasItem, rect: Rect2, name: String, glyph_style := "xbox") -> void:
		if UI.skinned("pad_glyph", [ci, rect, name, glyph_style]):
			return
		var c := rect.position + rect.size * 0.5
		var rad := minf(rect.size.x, rect.size.y) * 0.5
		var face := {"a": UI.GREEN, "b": UI.RED, "x": UI.BLUE, "y": UI.GOLD}
		if face.has(name):
			var colour: Color = face[name]
			ci.draw_circle(c, rad, Color(1, 1, 1, 0.07), true, -1.0, true)
			ci.draw_arc(c, rad - 0.5, 0.0, TAU, 32, Color(colour.r, colour.g, colour.b, 0.75), maxf(1.5, UI.px(2)), true)
			if glyph_style == "ps":
				var q := rad * 0.42
				var w := maxf(1.5, UI.px(2.2))
				match name:
					"a":
						ci.draw_line(c - Vector2(q, q), c + Vector2(q, q), UI.TEXT, w, true)
						ci.draw_line(c + Vector2(q, -q), c + Vector2(-q, q), UI.TEXT, w, true)
					"b":
						ci.draw_arc(c, q * 1.1, 0.0, TAU, 24, UI.TEXT, w, true)
					"x":
						ci.draw_rect(Rect2(c - Vector2(q, q), Vector2(q, q) * 2.0), UI.TEXT, false, w)
					"y":
						ci.draw_polyline(PackedVector2Array([c + Vector2(0, -q * 1.15), c + Vector2(q * 1.1, q * 0.8), c + Vector2(-q * 1.1, q * 0.8), c + Vector2(0, -q * 1.15)]), UI.TEXT, w, true)
			else:
				UI.text(ci, rect, name.to_upper(), UI.bold(), rad * 1.05 / UI.s, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
			return
		var label := glyph_label(name, glyph_style)
		var cw := UI.text_width(label, UI.bold(), 13) + UI.px(18)
		var crect := Rect2(rect.end.x - cw, rect.position.y + rect.size.y * 0.5 - UI.px(14), cw, UI.px(28))
		ci.draw_style_box(UI.box(UI.px(14), Color(1, 1, 1, 0.07), Color(1, 1, 1, 0.25), 1), crect)
		UI.text(ci, crect, label, UI.bold(), 13, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
