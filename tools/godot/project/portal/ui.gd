extends RefCounted
# ui.gd - the portal's look in one place: colours, metrics, fonts and the drawing helpers
# every screen and widget uses.
#
# Everything is drawn by code - shapes, gradients, a restrained glow.  No pictures and no
# game art.  Fonts: the one Godot carries inside the engine (Open Sans, SIL Open Font
# License) for everything that is read, and for headings a serif the computer already has
# (asked for by name at run time, never copied: Charter on a Mac, Georgia or Palatino
# elsewhere; without one the headings fall back to Open Sans).
#
# Sizes are "design pixels" of a picture 1080 high.  `s` is the factor from design pixels
# to real ones; portal.gd sets it from the size of the viewport it is in, so the same
# layout is right at 1280 x 720, at 4K, at 21:9 and at 4:3.

const BG_TOP := Color(0.035, 0.043, 0.071)
const BG_BOTTOM := Color(0.016, 0.018, 0.027)
const PANEL := Color(0.066, 0.076, 0.108)
const PANEL_ALPHA := 0.82
const PANEL_UP := Color(0.098, 0.112, 0.156)         # a control resting on a panel
const PANEL_HOT := Color(0.135, 0.150, 0.205)        # ... with the focus on it
const LINE := Color(1, 1, 1, 0.085)
const LINE_STRONG := Color(1, 1, 1, 0.16)
const TEXT := Color(0.955, 0.945, 0.915)
const DIM := Color(0.70, 0.725, 0.79)
const FAINT := Color(0.47, 0.50, 0.58)
const GOLD := Color(0.945, 0.745, 0.365)             # the accent: focus, the one thing to press
const GOLD_HI := Color(1.0, 0.875, 0.60)
const GOLD_DEEP := Color(0.62, 0.40, 0.14)
const EMBER := Color(0.93, 0.44, 0.21)
const GREEN := Color(0.44, 0.83, 0.54)               # online, ready
const BLUE := Color(0.44, 0.68, 0.98)                # in a room
const VIOLET := Color(0.72, 0.58, 0.99)              # in a game
const RED := Color(0.95, 0.38, 0.33)
const INK := Color(0.05, 0.045, 0.035)               # text on gold

const DESIGN_HEIGHT := 1080.0
const MIN_DESIGN_WIDTH := 1440.0                     # 4:3 at full height

static var s := 1.0
static var pad_glyphs := false                       # the last input came from a controller
static var _sans: Font
static var _bold: Font
static var _serif: Font
static var _serif_bold: Font
static var _spaced := {}
static var _boxes := {}


static func set_scale_for(size: Vector2) -> void:
	s = maxf(0.25, minf(size.y / DESIGN_HEIGHT, size.x / MIN_DESIGN_WIDTH))


static func px(v: float) -> float:
	return roundf(v * s)


static func fs(v: float) -> int:
	# a font size: never below what can be read
	return maxi(10, int(roundf(v * s)))


static func v2(x: float, y: float) -> Vector2:
	return Vector2(roundf(x * s), roundf(y * s))


# ---- fonts ---------------------------------------------------------------------------------
static func sans() -> Font:
	if _sans == null:
		_sans = ThemeDB.fallback_font
	return _sans


static func bold() -> Font:
	if _bold == null:
		var v := FontVariation.new()
		v.base_font = ThemeDB.fallback_font
		v.variation_embolden = 0.6
		_bold = v
	return _bold


static func _system_serif(weight: int) -> Font:
	var f := SystemFont.new()
	f.font_names = PackedStringArray(["Charter", "Bitstream Charter", "Georgia", "Palatino Linotype", "Book Antiqua", "DejaVu Serif", "Liberation Serif"])
	f.font_weight = weight
	f.allow_system_fallback = true
	f.antialiasing = TextServer.FONT_ANTIALIASING_GRAY
	f.hinting = TextServer.HINTING_LIGHT
	f.subpixel_positioning = TextServer.SUBPIXEL_POSITIONING_AUTO
	f.fallbacks = [ThemeDB.fallback_font]
	return f


static func serif() -> Font:
	if _serif == null:
		_serif = _system_serif(400)
	return _serif


static func serif_bold() -> Font:
	if _serif_bold == null:
		_serif_bold = _system_serif(700)
	return _serif_bold


# The same font with its letters set apart (headings in capitals); `extra` in design pixels.
static func spaced(base: Font, extra: float) -> Font:
	var amount := int(roundf(extra * s))
	var key := [base.get_instance_id(), amount]
	var f: FontVariation = _spaced.get(key)
	if f == null:
		if _spaced.size() > 64:
			_spaced.clear()
		f = FontVariation.new()
		f.base_font = base
		f.spacing_glyph = amount
		_spaced[key] = f
	return f


# ---- boxes ---------------------------------------------------------------------------------
static func _q(c: Color) -> Color:
	return Color(snappedf(c.r, 0.01), snappedf(c.g, 0.01), snappedf(c.b, 0.01), snappedf(c.a, 0.02))


static func box(radius: float, fill: Color, border := Color(0, 0, 0, 0), border_width := 0.0, glow := Color(0, 0, 0, 0), glow_size := 0.0) -> StyleBoxFlat:
	var key := [int(radius), _q(fill), _q(border), int(border_width), _q(glow), int(glow_size)]
	var b: StyleBoxFlat = _boxes.get(key)
	if b == null:
		if _boxes.size() > 400:
			_boxes.clear()
		b = StyleBoxFlat.new()
		b.bg_color = key[1]
		b.set_corner_radius_all(int(radius))
		b.corner_detail = 8
		b.anti_aliasing = true
		b.anti_aliasing_size = 0.9
		b.set_border_width_all(int(border_width))
		b.border_color = key[2]
		if glow_size > 0.0:
			b.shadow_color = key[4]
			b.shadow_size = int(glow_size)
		_boxes[key] = b
	return b


# A panel: dark, slightly see-through, a hairline round it and a lighter line along its top.
static func panel(ci: CanvasItem, rect: Rect2, radius := 14.0, alpha := 1.0, fill := PANEL) -> void:
	var r := px(radius)
	ci.draw_style_box(box(r, Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, Color(0, 0, 0, 0.30 * alpha), px(18)), rect)
	ci.draw_style_box(box(r, Color(fill.r, fill.g, fill.b, PANEL_ALPHA * alpha), Color(LINE.r, LINE.g, LINE.b, LINE.a * alpha), maxf(1.0, px(1))), rect)
	sheen(ci, rect, r, 0.035 * alpha)


# A soft light from the top of a box (the "gradient" of a surface).
static func sheen(ci: CanvasItem, rect: Rect2, radius: float, strength := 0.04) -> void:
	var inset := maxf(radius * 0.5, 1.0)
	var a := rect.position + Vector2(inset, 1.0)
	var w := rect.size.x - inset * 2.0
	var h := minf(rect.size.y * 0.55, rect.size.y - 2.0)
	if w <= 0.0 or h <= 0.0:
		return
	var top := Color(1, 1, 1, strength)
	var none := Color(1, 1, 1, 0)
	ci.draw_polygon(PackedVector2Array([a, a + Vector2(w, 0), a + Vector2(w, h), a + Vector2(0, h)]), PackedColorArray([top, top, none, none]))


# The focus mark: a gold line round the box and a quiet glow.  t: 0..1 (eased in by the widget).
static func focus_ring(ci: CanvasItem, rect: Rect2, radius: float, t: float) -> void:
	if t <= 0.01:
		return
	var grown := rect.grow(px(3) * t)
	ci.draw_style_box(box(radius + px(3), Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, Color(GOLD.r, GOLD.g, GOLD.b, 0.22 * t), px(16)), grown)
	ci.draw_style_box(box(radius + px(3), Color(0, 0, 0, 0), Color(GOLD.r, GOLD.g, GOLD.b, t), maxf(2.0, px(2.5))), grown)


static func rule(ci: CanvasItem, a: Vector2, b: Vector2, colour := LINE, width := 1.0) -> void:
	ci.draw_line(a, b, colour, maxf(1.0, px(width)))


# A horizontal rule that fades out at both ends (under headings).
static func fade_rule(ci: CanvasItem, a: Vector2, length: float, colour := GOLD, alpha := 0.55) -> void:
	var h := maxf(1.0, px(1.5))
	var c := Color(colour.r, colour.g, colour.b, alpha)
	var n := Color(colour.r, colour.g, colour.b, 0)
	var mid := a + Vector2(length * 0.35, 0)
	ci.draw_polygon(PackedVector2Array([a, mid, mid + Vector2(0, h), a + Vector2(0, h)]), PackedColorArray([c, c, c, c]))
	ci.draw_polygon(PackedVector2Array([mid, a + Vector2(length, 0), a + Vector2(length, h), mid + Vector2(0, h)]), PackedColorArray([c, n, n, c]))


# ---- text ----------------------------------------------------------------------------------
# One line in a rectangle, cut with an ellipsis when it does not fit.  Returns the width used.
static func text(ci: CanvasItem, rect: Rect2, string: String, font: Font, size: float, colour: Color, align := HORIZONTAL_ALIGNMENT_LEFT, valign := 0.5) -> float:
	if string == "" or rect.size.x <= 2.0:
		return 0.0
	var line := TextLine.new()
	line.add_string(string, font, fs(size))
	line.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	line.width = rect.size.x
	var size_now := line.get_size()
	var w := minf(size_now.x, rect.size.x)
	var x := rect.position.x
	if align == HORIZONTAL_ALIGNMENT_CENTER:
		x += (rect.size.x - w) * 0.5
	elif align == HORIZONTAL_ALIGNMENT_RIGHT:
		x += rect.size.x - w
	line.draw(ci.get_canvas_item(), Vector2(roundf(x), roundf(rect.position.y + (rect.size.y - size_now.y) * valign)), colour)
	return w


static func text_width(string: String, font: Font, size: float) -> float:
	return font.get_string_size(string, HORIZONTAL_ALIGNMENT_LEFT, -1, fs(size)).x


static func line_height(font: Font, size: float) -> float:
	return font.get_height(fs(size))


# A Label made in the portal's type (for text that wraps or sits in a container).
static func label(string: String, size := 22.0, colour := TEXT, font: Font = null, wrap := false) -> Label:
	var l := Label.new()
	l.text = string
	l.add_theme_font_override("font", font if font != null else sans())
	l.add_theme_font_size_override("font_size", fs(size))
	l.add_theme_color_override("font_color", colour)
	l.add_theme_constant_override("line_spacing", int(px(4)))
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	else:
		l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		l.clip_text = true
	return l


# ---- small things --------------------------------------------------------------------------
static func hue_of(key: String) -> float:
	return float(absi(key.hash()) % 360) / 360.0


static func tint_of(key: String, saturation := 0.42, value := 0.78) -> Color:
	return Color.from_hsv(hue_of(key), saturation, value)


static func initials(name: String) -> String:
	var parts := name.strip_edges().split(" ", false)
	if parts.is_empty():
		return "?"
	if parts.size() == 1:
		return parts[0].substr(0, 1).to_upper()
	return (parts[0].substr(0, 1) + parts[parts.size() - 1].substr(0, 1)).to_upper()


static func ago(seconds: int) -> String:
	if seconds < 90:
		return "just now"
	if seconds < 3600:
		return "%d min ago" % int(seconds / 60.0)
	if seconds < 86400 * 2:
		return "%d h ago" % int(seconds / 3600.0)
	return "%d days ago" % int(seconds / 86400.0)


# A round mark: a filled circle with a soft halo (presence dots, ready marks).
static func dot(ci: CanvasItem, centre: Vector2, radius: float, colour: Color, halo := true) -> void:
	if halo:
		ci.draw_circle(centre, radius * 2.1, Color(colour.r, colour.g, colour.b, 0.13), true, -1.0, true)
	ci.draw_circle(centre, radius, colour, true, -1.0, true)


# ---- icons: drawn, never pictures ----------------------------------------------------------
# `rect` is the box the icon fills; every icon is designed in a unit square.
static func icon(ci: CanvasItem, name: String, rect: Rect2, colour: Color) -> void:
	var u := minf(rect.size.x, rect.size.y)
	var o := rect.position + (rect.size - Vector2(u, u)) * 0.5
	var w := maxf(1.5, u * 0.085)
	match name:
		"sword":
			ci.draw_set_transform(o + Vector2(u, u) * 0.5, deg_to_rad(45.0), Vector2(u, u))
			ci.draw_colored_polygon(PackedVector2Array([Vector2(0, -0.52), Vector2(0.075, -0.40), Vector2(0.075, 0.16), Vector2(-0.075, 0.16), Vector2(-0.075, -0.40)]), colour)
			ci.draw_rect(Rect2(-0.24, 0.16, 0.48, 0.075), colour)
			ci.draw_rect(Rect2(-0.045, 0.235, 0.09, 0.20), colour)
			ci.draw_circle(Vector2(0, 0.47), 0.065, colour, true, -1.0, true)
			ci.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
		"banner":
			ci.draw_line(o + Vector2(0.24, 0.08) * u, o + Vector2(0.24, 0.94) * u, colour, w, true)
			ci.draw_colored_polygon(_pts(o, u, [0.24, 0.12, 0.86, 0.12, 0.70, 0.33, 0.86, 0.54, 0.24, 0.54]), colour)
			ci.draw_circle(o + Vector2(0.24, 0.08) * u, w * 0.9, colour, true, -1.0, true)
		"key":
			ci.draw_arc(o + Vector2(0.30, 0.50) * u, 0.17 * u, 0.0, TAU, 28, colour, w, true)
			ci.draw_line(o + Vector2(0.47, 0.50) * u, o + Vector2(0.92, 0.50) * u, colour, w, true)
			ci.draw_line(o + Vector2(0.76, 0.50) * u, o + Vector2(0.76, 0.68) * u, colour, w, true)
			ci.draw_line(o + Vector2(0.89, 0.50) * u, o + Vector2(0.89, 0.64) * u, colour, w, true)
		"people":
			_bust(ci, o + Vector2(0.66, 0.40) * u, 0.26 * u, Color(colour.r, colour.g, colour.b, colour.a * 0.55))
			_bust(ci, o + Vector2(0.38, 0.48) * u, 0.32 * u, colour)
		"person":
			_bust(ci, o + Vector2(0.50, 0.44) * u, 0.36 * u, colour)
		"gear":
			var c := o + Vector2(0.5, 0.5) * u
			for k in 8:
				var a := TAU * k / 8.0
				ci.draw_set_transform(c, a, Vector2.ONE)
				ci.draw_rect(Rect2(-0.085 * u, -0.46 * u, 0.17 * u, 0.17 * u), colour)
			ci.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
			ci.draw_arc(c, 0.26 * u, 0.0, TAU, 32, colour, 0.17 * u, true)
		"plus":
			ci.draw_line(o + Vector2(0.5, 0.18) * u, o + Vector2(0.5, 0.82) * u, colour, w * 1.2, true)
			ci.draw_line(o + Vector2(0.18, 0.5) * u, o + Vector2(0.82, 0.5) * u, colour, w * 1.2, true)
		"check":
			ci.draw_polyline(_pts(o, u, [0.16, 0.54, 0.40, 0.76, 0.84, 0.26]), colour, w * 1.5, true)
		"cross":
			ci.draw_line(o + Vector2(0.22, 0.22) * u, o + Vector2(0.78, 0.78) * u, colour, w * 1.3, true)
			ci.draw_line(o + Vector2(0.78, 0.22) * u, o + Vector2(0.22, 0.78) * u, colour, w * 1.3, true)
		"chevron":
			ci.draw_polyline(_pts(o, u, [0.36, 0.20, 0.66, 0.50, 0.36, 0.80]), colour, w * 1.3, true)
		"chevron_left":
			ci.draw_polyline(_pts(o, u, [0.64, 0.20, 0.34, 0.50, 0.64, 0.80]), colour, w * 1.3, true)
		"copy":
			ci.draw_style_box(box(u * 0.10, Color(0, 0, 0, 0), colour, maxf(1.5, w * 0.9)), Rect2(o + Vector2(0.32, 0.30) * u, Vector2(0.50, 0.58) * u))
			ci.draw_polyline(_pts(o, u, [0.22, 0.68, 0.18, 0.68, 0.18, 0.14, 0.62, 0.14, 0.62, 0.20]), colour, maxf(1.5, w * 0.9), true)
		"crown":
			ci.draw_colored_polygon(_pts(o, u, [0.12, 0.74, 0.10, 0.30, 0.32, 0.52, 0.50, 0.20, 0.68, 0.52, 0.90, 0.30, 0.88, 0.74]), colour)
			ci.draw_rect(Rect2(o + Vector2(0.12, 0.79) * u, Vector2(0.76, 0.08) * u), colour)
		"dots":
			for k in 3:
				ci.draw_circle(o + Vector2(0.22 + 0.28 * k, 0.5) * u, 0.075 * u, colour, true, -1.0, true)
		"bell":
			ci.draw_colored_polygon(_pts(o, u, [0.50, 0.12, 0.66, 0.20, 0.74, 0.40, 0.76, 0.62, 0.88, 0.76, 0.12, 0.76, 0.24, 0.62, 0.26, 0.40, 0.34, 0.20]), colour)
			ci.draw_arc(o + Vector2(0.5, 0.80) * u, 0.10 * u, 0.0, PI, 12, colour, w, true)
		"eye":
			var pts := PackedVector2Array()
			for k in 25:
				var t := k / 24.0
				pts.append(o + Vector2(0.08 + 0.84 * t, 0.5 - sin(t * PI) * 0.30) * u)
			for k in 25:
				var t := 1.0 - k / 24.0
				pts.append(o + Vector2(0.08 + 0.84 * t, 0.5 + sin(t * PI) * 0.30) * u)
			ci.draw_polyline(pts, colour, w, true)
			ci.draw_circle(o + Vector2(0.5, 0.5) * u, 0.13 * u, colour, true, -1.0, true)
		"screen":
			ci.draw_style_box(box(u * 0.08, Color(0, 0, 0, 0), colour, maxf(1.5, w)), Rect2(o + Vector2(0.10, 0.16) * u, Vector2(0.80, 0.54) * u))
			ci.draw_line(o + Vector2(0.34, 0.86) * u, o + Vector2(0.66, 0.86) * u, colour, w, true)
			ci.draw_line(o + Vector2(0.50, 0.70) * u, o + Vector2(0.50, 0.86) * u, colour, w, true)
		"speaker":
			ci.draw_colored_polygon(_pts(o, u, [0.12, 0.38, 0.30, 0.38, 0.52, 0.18, 0.52, 0.82, 0.30, 0.62, 0.12, 0.62]), colour)
			ci.draw_arc(o + Vector2(0.52, 0.5) * u, 0.20 * u, -0.9, 0.9, 12, colour, w, true)
			ci.draw_arc(o + Vector2(0.52, 0.5) * u, 0.36 * u, -0.9, 0.9, 16, colour, w, true)
		"pad":
			pad_shape(ci, Rect2(o + Vector2(0.04, 0.20) * u, Vector2(0.92, 0.60) * u), colour, Color(0, 0, 0, 0), 0.0)
		"layers":
			ci.draw_polyline(_pts(o, u, [0.50, 0.14, 0.90, 0.36, 0.50, 0.58, 0.10, 0.36, 0.50, 0.14]), colour, w, true)
			ci.draw_polyline(_pts(o, u, [0.10, 0.54, 0.50, 0.76, 0.90, 0.54]), colour, w, true)
			ci.draw_polyline(_pts(o, u, [0.10, 0.70, 0.50, 0.92, 0.90, 0.70]), colour, w, true)
		"door":
			ci.draw_polyline(_pts(o, u, [0.56, 0.14, 0.20, 0.14, 0.20, 0.86, 0.56, 0.86]), colour, w, true)
			ci.draw_line(o + Vector2(0.44, 0.50) * u, o + Vector2(0.90, 0.50) * u, colour, w, true)
			ci.draw_polyline(_pts(o, u, [0.74, 0.34, 0.90, 0.50, 0.74, 0.66]), colour, w, true)
		"chat":
			ci.draw_style_box(box(u * 0.14, Color(0, 0, 0, 0), colour, maxf(1.5, w)), Rect2(o + Vector2(0.10, 0.14) * u, Vector2(0.80, 0.54) * u))
			ci.draw_colored_polygon(_pts(o, u, [0.26, 0.66, 0.44, 0.66, 0.24, 0.90]), colour)
		"warn":
			ci.draw_polyline(_pts(o, u, [0.50, 0.12, 0.92, 0.84, 0.08, 0.84, 0.50, 0.12]), colour, w, true)
			ci.draw_line(o + Vector2(0.50, 0.38) * u, o + Vector2(0.50, 0.60) * u, colour, w, true)
			ci.draw_circle(o + Vector2(0.50, 0.72) * u, w * 0.6, colour, true, -1.0, true)
		"disc":
			ci.draw_arc(o + Vector2(0.5, 0.5) * u, 0.38 * u, 0.0, TAU, 40, colour, w, true)
			ci.draw_arc(o + Vector2(0.5, 0.5) * u, 0.10 * u, 0.0, TAU, 20, colour, w, true)
			ci.draw_arc(o + Vector2(0.5, 0.5) * u, 0.25 * u, -1.3, -0.3, 10, Color(colour.r, colour.g, colour.b, colour.a * 0.6), w * 0.8, true)
		"back":
			ci.draw_polyline(_pts(o, u, [0.46, 0.24, 0.18, 0.50, 0.46, 0.76]), colour, w * 1.2, true)
			ci.draw_line(o + Vector2(0.18, 0.50) * u, o + Vector2(0.84, 0.50) * u, colour, w * 1.2, true)
		_:
			ci.draw_arc(o + Vector2(0.5, 0.5) * u, 0.3 * u, 0.0, TAU, 24, colour, w, true)


static func _pts(o: Vector2, u: float, flat: Array) -> PackedVector2Array:
	var a := PackedVector2Array()
	for k in range(0, flat.size(), 2):
		a.append(o + Vector2(flat[k], flat[k + 1]) * u)
	return a


static func _bust(ci: CanvasItem, centre: Vector2, size: float, colour: Color) -> void:
	# a head and shoulders
	ci.draw_circle(centre + Vector2(0, -size * 0.42), size * 0.36, colour, true, -1.0, true)
	var pts := PackedVector2Array()
	for k in 17:
		var a := PI + PI * k / 16.0
		pts.append(centre + Vector2(cos(a) * size * 0.72, size * 0.86 + sin(a) * size * 0.78))
	ci.draw_colored_polygon(pts, colour)


# The outline of a two-stick controller in `rect` (the settings' picture and the small icon).
static func pad_shape(ci: CanvasItem, rect: Rect2, fill: Color, line: Color, line_width: float) -> void:
	var o := rect.position
	var z := rect.size
	var flat := [0.20, 0.06, 0.36, 0.06, 0.40, 0.12, 0.60, 0.12, 0.64, 0.06, 0.80, 0.06, 0.90, 0.16, 0.985, 0.66, 0.97, 0.90,
		0.88, 0.99, 0.79, 0.93, 0.68, 0.66, 0.32, 0.66, 0.21, 0.93, 0.12, 0.99, 0.03, 0.90, 0.015, 0.66, 0.10, 0.16]
	var pts := PackedVector2Array()
	for k in range(0, flat.size(), 2):
		pts.append(o + Vector2(flat[k] * z.x, flat[k + 1] * z.y))
	var smooth := _round_polygon(pts, 3)
	if fill.a > 0.0:
		ci.draw_colored_polygon(smooth, fill)
	if line.a > 0.0 and line_width > 0.0:
		smooth.append(smooth[0])
		ci.draw_polyline(smooth, line, line_width, true)


static func _round_polygon(pts: PackedVector2Array, rounds: int) -> PackedVector2Array:
	# corner cutting: every round replaces each corner by two points a quarter along its edges
	var a := pts
	for r in rounds:
		var b := PackedVector2Array()
		for k in a.size():
			var p := a[k]
			var q := a[(k + 1) % a.size()]
			b.append(p.lerp(q, 0.25))
			b.append(p.lerp(q, 0.75))
		a = b
	return a
