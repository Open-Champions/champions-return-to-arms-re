extends SceneTree
# Authored projected-geometry regression for the production non-GS_WORLD shader.
# No game library, disc, symbols, assets or translated game code are used.
# Run twice on a real GPU (a small ordinary window is sufficient):
#   Godot --path PROJECT --rendering-method forward_plus --rendering-driver vulkan \
#     --script res://dev/draw_depth_test.gd -- --out PRIVATE_DIR
#   Godot --path PROJECT --rendering-method gl_compatibility --rendering-driver opengl3 \
#     --script res://dev/draw_depth_test.gd -- --out ANOTHER_PRIVATE_DIR
# Optional --shader FILE supplies a saved production shader for a negative control.
# Exit 0: every pixel check passed; 1: rendered mismatch; 2: invalid setup/timeout.

const SIZE := 64
const SHADER_PATH := "res://shaders/gs_draw.gdshaderinc"
const EVERYWHERE := AABB(Vector3(-1000000.0, -1000000.0, -1000000.0), Vector3(2000000.0, 2000000.0, 2000000.0))
var output := ""
var shader_path := SHADER_PATH
var shader: Shader
var finished := false
var results: Array = []
var report: Dictionary = {}


func _initialize() -> void:
	_run.call_deferred()


func _timed_out() -> void:
	if not finished:
		printerr("draw_depth: FAIL 30-second GPU-test timeout")
		finished = true
		quit(2)


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var i := 0
	while i < args.size():
		if args[i] not in ["--out", "--shader"] or i + 1 >= args.size():
			printerr("draw_depth: expected --out DIR or --shader FILE")
			quit(2)
			return
		if args[i] == "--out":
			output = ProjectSettings.globalize_path(args[i + 1])
		else:
			shader_path = args[i + 1]
		i += 2
	var driver := RenderingServer.get_current_rendering_driver_name()
	var method := RenderingServer.get_current_rendering_method()
	var adapter := RenderingServer.get_video_adapter_name()
	if DisplayServer.get_name().to_lower() == "headless" or driver.to_lower() == "dummy" or adapter.is_empty():
		printerr("draw_depth: refusing a dummy/headless renderer; a real GPU is required")
		quit(2)
		return
	if method not in ["forward_plus", "gl_compatibility"]:
		printerr("draw_depth: expected Forward+ or Compatibility, got ", method)
		quit(2)
		return
	if not FileAccess.file_exists(shader_path):
		printerr("draw_depth: shader does not exist: ", shader_path)
		quit(2)
		return
	if output != "" and DirAccess.make_dir_recursive_absolute(output) != OK:
		printerr("draw_depth: cannot create output: ", output)
		quit(2)
		return
	var body := FileAccess.get_file_as_string(shader_path)
	if body.is_empty():
		printerr("draw_depth: shader is empty or unreadable")
		quit(2)
		return
	shader = Shader.new()
	# The same production variant as a projected, untextured depth-tested GS draw.
	# Do not replace vertex/depth logic with a test-only shader.
	shader.code = "shader_type spatial;\n#define GS_DEPTH_WRITE\n" + body
	report = {"godot": Engine.get_version_info().get("string", ""), "renderer": method,
		"driver": driver, "adapter": adapter, "shader": shader_path,
		"shader_sha256": body.sha256_text(), "scope": "authored projected GS depth ordering; no game data"}
	create_timer(30.0).timeout.connect(_timed_out)
	var red := Color(1.0, 0.0, 0.0, 1.0)
	var green := Color(0.0, 1.0, 0.0, 1.0)
	var far := {"depth": 0.25, "colour": red}
	var near := {"depth": 0.75, "colour": green}
	var cases := [
		{"name": "depth_zero_clear", "layers": [], "expected": Color.BLACK},
		{"name": "far_over_zero", "layers": [far], "expected": red},
		{"name": "near_over_zero", "layers": [near], "expected": green},
		{"name": "far_then_near", "layers": [far, near], "expected": green},
		{"name": "near_then_far", "layers": [near, far], "expected": green},
	]
	var passed := true
	for item in cases:
		var result: Dictionary = await _case(item.name, item.layers, item.expected)
		results.append(result)
		passed = passed and bool(result.passed)
		print("draw_depth: %s %s" % ["PASS" if result.passed else "FAIL", item.name])
	report["passed"] = passed
	report["cases"] = results
	if output != "":
		var file := FileAccess.open(output.path_join("draw-depth-result.json"), FileAccess.WRITE)
		if file == null:
			printerr("draw_depth: cannot write result")
			quit(2)
			return
		file.store_string(JSON.stringify(report, "\t") + "\n")
		file.close()
	print("draw_depth: ", JSON.stringify(report))
	finished = true
	quit(0 if passed else 1)


func _quad(viewport: SubViewport, depth: float, colour: Color, priority: int, inset: float) -> bool:
	var lo := inset
	var hi := float(SIZE) - inset
	var vertices := PackedVector3Array([
		Vector3(lo, lo, depth), Vector3(hi, lo, depth), Vector3(hi, hi, depth),
		Vector3(lo, lo, depth), Vector3(hi, hi, depth), Vector3(lo, hi, depth)])
	var colours := PackedColorArray()
	var custom := PackedFloat32Array()
	for _vertex in vertices:
		# Production colour units: RGB 255 is white; alpha 128 is opaque.
		colours.append(Color(colour.r, colour.g, colour.b, 128.0 / 255.0))
		custom.append_array(PackedFloat32Array([0.0, 0.0, 1.0, 1.0]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colours
	arrays[Mesh.ARRAY_CUSTOM0] = custom
	var mesh := ArrayMesh.new()
	mesh.custom_aabb = EVERYWHERE
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {},
		Mesh.ARRAY_FORMAT_CUSTOM0 | (Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT))
	if mesh.get_surface_count() != 1:
		printerr("draw_depth: authored quad surface was not created")
		return false
	var material := ShaderMaterial.new()
	material.shader = shader
	# ALPHA in the production shader uses the transparent pass. Explicit priorities
	# force list order, independently of Godot's world-space distance sorting.
	material.render_priority = priority
	material.set_shader_parameter("target_size", Vector2(SIZE, SIZE))
	material.set_shader_parameter("target_scale", Vector2.ONE)
	material.set_shader_parameter("scissor", Vector4(0.0, 0.0, SIZE, SIZE))
	material.set_shader_parameter("textured", 0)
	material.set_shader_parameter("atst", 1)
	material.set_shader_parameter("blend", Vector4(0.0, 1.0, 0.0, 0.0))
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.material_override = material
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	viewport.add_child(instance)
	RenderingServer.instance_set_ignore_culling(instance.get_instance(), true)
	return true


func _case(label: String, layers: Array, expected: Color) -> Dictionary:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(SIZE, SIZE)
	viewport.own_world_3d = true
	viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.msaa_3d = Viewport.MSAA_DISABLED
	root.add_child(viewport)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color.BLACK
	world.environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	viewport.add_child(world)
	var camera := Camera3D.new()
	camera.position = Vector3(0.0, 0.0, 3.0)
	viewport.add_child(camera)
	camera.make_current()
	# The engine starts a reversed-Z surface at zero. Draw an explicit GS depth-zero
	# clear quad as well, followed by GS .25/.75, with greater depth meaning nearer.
	var geometry_valid := _quad(viewport, 0.0, Color.BLACK, -10, 0.0)
	var depths := [0.0]
	for index in range(layers.size()):
		var layer: Dictionary = layers[index]
		geometry_valid = _quad(viewport, float(layer.depth), layer.colour, index, 8.0) and geometry_valid
		depths.append(layer.depth)
	# Allow upload and first-use shader compilation before sampling the real target.
	for _frame in range(4):
		await process_frame
		await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	var result := {"name": label, "submitted_gs_depths": depths, "geometry_valid": geometry_valid, "passed": false}
	if image != null and not image.is_empty() and image.get_size() == Vector2i(SIZE, SIZE):
		var mismatches := 0
		for y in range(30, 35):
			for x in range(30, 35):
				var pixel := image.get_pixel(x, y)
				if absf(pixel.r - expected.r) > 0.05 or absf(pixel.g - expected.g) > 0.05 or absf(pixel.b - expected.b) > 0.05:
					mismatches += 1
		var center := image.get_pixel(32, 32)
		result["center_rgba"] = [center.r, center.g, center.b, center.a]
		result["interior_pixels"] = 25
		result["mismatches"] = mismatches
		result["passed"] = geometry_valid and mismatches == 0
		if output != "":
			result["capture_exit"] = image.save_png(output.path_join(label + ".png"))
			result["passed"] = bool(result.passed) and result.capture_exit == OK
	else:
		result["error"] = "No real 64x64 GPU image"
	viewport.queue_free()
	await process_frame
	return result
