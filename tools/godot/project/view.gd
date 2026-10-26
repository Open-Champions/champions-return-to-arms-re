extends Control
# view.gd - the picture in the window: letterboxed to the shape the frame says it is meant
# to be seen in (the console's picture is 4:3 whatever its pixel counts are).
#   texture  the library's own picture (picture mode), or
#   drawer   RtaDrawer: the surface the display circuit reads, as Godot drew it

var texture: Texture2D
var drawer: Object
# Forward+ / Mobile: a picture drawn in stored values (RtaDrawer.get_shown_stored, gs_draw.gdshaderinc GS_STORED_SPACE)
# carries Godot's sRGB curve on top: taken off here.  COLOR already holds the texture's colour times the modulate (Godot 4
# canvas_item): sampling TEXTURE again squared every value - the whole window was darker than the game's own picture
# (the title screen's mean 72 against 123 of 255; docs/issues/remastered-complete.md, bug 6)
const DECODE := "shader_type canvas_item;\nuniform bool decode = false;\nvoid fragment() {\n\tvec4 c = COLOR;\n" + \
	"\tif (decode) c.rgb = mix(c.rgb / 12.92, pow((c.rgb + vec3(0.055)) / 1.055, vec3(2.4)), step(vec3(0.04045), c.rgb));\n\tCOLOR = c;\n}\n"
var decoding: ShaderMaterial
var aspect := 4.0 / 3.0
var message := "":
	set(value):
		message = value
		queue_redraw()


func _picture_rect() -> Rect2:
	var shape: float = size.x / max(size.y, 1.0)
	var w: float = size.x
	var h: float = size.y
	if shape > aspect:
		w = h * aspect
	else:
		h = w / aspect
	return Rect2((size - Vector2(w, h)) * 0.5, Vector2(w, h))


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color.BLACK)
	if drawer != null and drawer.has_method("get_shown_stored"):
		if decoding == null:
			var shader := Shader.new()
			shader.code = DECODE
			decoding = ShaderMaterial.new()
			decoding.shader = shader
			material = decoding
		decoding.set_shader_parameter("decode", bool(drawer.call("get_shown_stored")))
	if drawer != null:
		var shown: RID = drawer.call("get_shown_texture")
		if shown.is_valid():
			var source: Rect2 = drawer.call("get_shown_region")
			var rect := _picture_rect()
			var flipped: bool = drawer.has_method("get_shown_flipped") and bool(drawer.call("get_shown_flipped"))
			if flipped:         # Forward+ keeps the surface bottom up: turned over about the picture's middle
				RenderingServer.canvas_item_add_set_transform(get_canvas_item(), Transform2D(0.0, Vector2(1, -1), 0.0, Vector2(0, rect.position.y * 2.0 + rect.size.y)))
			RenderingServer.canvas_item_add_texture_rect_region(get_canvas_item(), rect, shown, source)
			if flipped:
				RenderingServer.canvas_item_add_set_transform(get_canvas_item(), Transform2D.IDENTITY)
	elif texture != null:
		draw_texture_rect(texture, _picture_rect(), false)
	if message != "":
		draw_string(ThemeDB.fallback_font, Vector2(24, 48), message, HORIZONTAL_ALIGNMENT_LEFT, size.x - 48, 16, Color(0.9, 0.9, 0.9))
