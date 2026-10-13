extends Control
# view.gd - the picture in the window: letterboxed to the shape the frame says it is meant
# to be seen in (the console's picture is 4:3 whatever its pixel counts are).
#   texture  the library's own picture (picture mode), or
#   drawer   RtaDrawer: the surface the display circuit reads, as Godot drew it

var texture: Texture2D
var drawer: Object
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
	if drawer != null:
		var shown: RID = drawer.call("get_shown_texture")
		if shown.is_valid():
			var source: Rect2 = drawer.call("get_shown_region")
			RenderingServer.canvas_item_add_texture_rect_region(get_canvas_item(), _picture_rect(), shown, source)
	elif texture != null:
		draw_texture_rect(texture, _picture_rect(), false)
	if message != "":
		draw_string(ThemeDB.fallback_font, Vector2(24, 48), message, HORIZONTAL_ALIGNMENT_LEFT, size.x - 48, 16, Color(0.9, 0.9, 0.9))
