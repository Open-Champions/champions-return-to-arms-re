extends SceneTree
# Actual production view.gd presentation with an authored quadrant texture and fake drawer.
# No RtaMachine, game library, disc or game-derived image is used.
#   Godot --path PROJECT --rendering-method forward_plus --rendering-driver vulkan \
#     --script res://dev/presentation_resize_test.gd -- --out PRIVATE_DIR
# Repeat with gl_compatibility / opengl3. --wrong-flip is a negative control: a
# bottom-up texture is deliberately presented without its required correction.
# Exit 0: all checks pass; 1: layout/pixel mismatch; 2: setup failure or 30s timeout.

const VIEW_SCRIPT := "res://view.gd"
const SOURCE_SIZE := Vector2i(64, 48)
var output := ""
var wrong_flip := false
var finished := false
var results: Array = []

class AuthoredDrawer extends RefCounted:
	var texture: ImageTexture
	var flipped := false

	func get_shown_texture() -> RID:
		return texture.get_rid()

	func get_shown_region() -> Rect2:
		return Rect2(Vector2.ZERO, Vector2(texture.get_size()))

	func get_shown_flipped() -> bool:
		return flipped

	func get_shown_stored() -> bool:
		return false


func _initialize() -> void:
	_run.call_deferred()


func _timed_out() -> void:
	if not finished:
		printerr("presentation_resize: FAIL 30-second timeout")
		finished = true
		quit(2)


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index < args.size():
		if args[index] == "--wrong-flip":
			wrong_flip = true
		elif args[index] == "--out" and index + 1 < args.size():
			output = ProjectSettings.globalize_path(args[index + 1])
			index += 1
		else:
			printerr("presentation_resize: expected --out DIR or --wrong-flip")
			quit(2)
			return
		index += 1
	var driver := RenderingServer.get_current_rendering_driver_name()
	var renderer := RenderingServer.get_current_rendering_method()
	var adapter := RenderingServer.get_video_adapter_name()
	if DisplayServer.get_name().to_lower() == "headless" or driver.to_lower() == "dummy" or adapter.is_empty():
		printerr("presentation_resize: real GPU required; refusing dummy/headless renderer")
		quit(2)
		return
	if renderer not in ["forward_plus", "gl_compatibility"]:
		printerr("presentation_resize: expected Forward+ or Compatibility")
		quit(2)
		return
	if output != "" and DirAccess.make_dir_recursive_absolute(output) != OK:
		printerr("presentation_resize: cannot create private output directory")
		quit(2)
		return
	var view_source := load(VIEW_SCRIPT) as GDScript
	if view_source == null:
		printerr("presentation_resize: production view script could not be loaded")
		quit(2)
		return
	create_timer(30.0).timeout.connect(_timed_out)
	var viewport := SubViewport.new()
	viewport.disable_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
	root.add_child(viewport)
	var view := Control.new()
	view.set_script(view_source)
	view.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	viewport.add_child(view)
	var drawer := AuthoredDrawer.new()
	view.set("drawer", drawer)
	# These integer rectangles are independent expected values, not values returned
	# by the production _picture_rect implementation under test.
	var cases := [
		{"name": "4x3_initial", "size": Vector2i(96, 72), "aspect": 4.0 / 3.0, "rect": Rect2(0, 0, 96, 72)},
		{"name": "4x3_wide", "size": Vector2i(160, 90), "aspect": 4.0 / 3.0, "rect": Rect2(20, 0, 120, 90)},
		{"name": "4x3_return", "size": Vector2i(96, 72), "aspect": 4.0 / 3.0, "rect": Rect2(0, 0, 96, 72)},
		{"name": "16x9_initial", "size": Vector2i(96, 72), "aspect": 16.0 / 9.0, "rect": Rect2(0, 9, 96, 54)},
		{"name": "16x9_wide", "size": Vector2i(160, 90), "aspect": 16.0 / 9.0, "rect": Rect2(0, 0, 160, 90)},
		{"name": "16x9_return", "size": Vector2i(96, 72), "aspect": 16.0 / 9.0, "rect": Rect2(0, 9, 96, 54)},
	]
	var all_passed := true
	for bottom_up in [false, true]:
		drawer.texture = _texture(bottom_up)
		drawer.flipped = bottom_up and not wrong_flip
		for item in cases:
			viewport.size = item.size
			view.size = Vector2(item.size)
			view.set("aspect", item.aspect)
			view.queue_redraw()
			for _frame in range(4):
				await process_frame
				await RenderingServer.frame_post_draw
			var label: String = ("flipped_" if bottom_up else "upright_") + String(item.name)
			var result := _inspect(viewport, view, label, item.rect, bottom_up)
			results.append(result)
			all_passed = all_passed and bool(result.passed)
			print("presentation_resize: %s %s" % ["PASS" if result.passed else "FAIL", label])
	var report := {"passed": all_passed, "godot": Engine.get_version_info().get("string", ""),
		"renderer": renderer, "driver": driver, "adapter": adapter, "wrong_flip_control": wrong_flip,
		"view_script": VIEW_SCRIPT, "view_sha256": FileAccess.get_file_as_string(VIEW_SCRIPT).sha256_text(),
		"source_size": [SOURCE_SIZE.x, SOURCE_SIZE.y], "cases": results,
		"scope": "production view rectangle, resize and flip presentation only; synthetic texture, no game data"}
	if output != "":
		var file := FileAccess.open(output.path_join("presentation-resize-result.json"), FileAccess.WRITE)
		if file == null:
			printerr("presentation_resize: cannot write result")
			quit(2)
			return
		file.store_string(JSON.stringify(report, "\t") + "\n")
		file.close()
	print("presentation_resize: ", JSON.stringify(report))
	finished = true
	viewport.queue_free()
	quit(0 if all_passed else 1)


func _texture(bottom_up: bool) -> ImageTexture:
	var image := Image.create(SOURCE_SIZE.x, SOURCE_SIZE.y, false, Image.FORMAT_RGBA8)
	image.fill_rect(Rect2i(0, 0, 32, 24), Color.RED)
	image.fill_rect(Rect2i(32, 0, 32, 24), Color.GREEN)
	image.fill_rect(Rect2i(0, 24, 32, 24), Color.BLUE)
	image.fill_rect(Rect2i(32, 24, 32, 24), Color.YELLOW)
	if bottom_up:
		image.flip_y()
	return ImageTexture.create_from_image(image)


func _expected(point: Vector2, rect: Rect2) -> Color:
	if not rect.has_point(point):
		return Color.BLACK
	var right := point.x >= rect.position.x + rect.size.x * 0.5
	var lower := point.y >= rect.position.y + rect.size.y * 0.5
	if lower:
		return Color.YELLOW if right else Color.BLUE
	return Color.GREEN if right else Color.RED


func _inspect(viewport: SubViewport, view: Control, label: String, expected_rect: Rect2, bottom_up: bool) -> Dictionary:
	var actual_rect: Rect2 = view.call("_picture_rect")
	var result := {"name": label, "size": [viewport.size.x, viewport.size.y],
		"expected_rect": [expected_rect.position.x, expected_rect.position.y, expected_rect.size.x, expected_rect.size.y],
		"actual_rect": [actual_rect.position.x, actual_rect.position.y, actual_rect.size.x, actual_rect.size.y],
		"bottom_up_source": bottom_up, "passed": false}
	var image := viewport.get_texture().get_image()
	if image == null or image.is_empty() or image.get_size() != viewport.size:
		result["error"] = "No real image of the requested size"
		return result
	var mismatches := 0
	for y in range(viewport.size.y):
		for x in range(viewport.size.x):
			var pixel := image.get_pixel(x, y)
			var expected := _expected(Vector2(x + 0.5, y + 0.5), expected_rect)
			if absf(pixel.r - expected.r) > 0.02 or absf(pixel.g - expected.g) > 0.02 or absf(pixel.b - expected.b) > 0.02:
				mismatches += 1
	result["checked_pixels"] = viewport.size.x * viewport.size.y
	result["pixel_mismatches"] = mismatches
	result["rect_matches"] = actual_rect.is_equal_approx(expected_rect)
	result["passed"] = bool(result.rect_matches) and mismatches == 0
	if output != "":
		result["capture_exit"] = image.save_png(output.path_join(label + ".png"))
		result["passed"] = bool(result.passed) and result.capture_exit == OK
	return result
