extends SceneTree
# Actual GPU regression of production RtaMachine -> RtaDrawer target reuse.
# Requires only the authored msaa_frame_library.cpp fixture, never a game library/disc.
# python tools/godot/tests/run_msaa.py builds the ABI fixture and runs this script.
const SIZE := 64
const PHASES := ["narrow_initial", "narrow_repeat", "narrow_idle", "wide_cancel_announcement", "narrow_cancel_return", "wide_transition", "wide_repeat", "wide_idle", "narrow_return", "narrow_final"]
var output := ""
var library := ""
var samples := 4
var finished := false
var machine: RtaMachine
var drawer: RtaDrawer
var results: Array = []
var retained: PackedByteArray
var last_texture: RID
var seen_textures: Array[RID] = []

func _initialize() -> void:
	_run.call_deferred()

func _timeout() -> void:
	if not finished:
		printerr("msaa_transition: FAIL 30-second GPU timeout")
		finished = true
		quit(2)

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var i := 0
	while i < args.size():
		if args[i] not in ["--out", "--lib", "--samples"] or i + 1 >= args.size():
			printerr("msaa_transition: expected --out DIR --lib FIXTURE_DLL [--samples 0|4]")
			quit(2)
			return
		match args[i]:
			"--out": output = ProjectSettings.globalize_path(args[i + 1])
			"--lib": library = ProjectSettings.globalize_path(args[i + 1])
			"--samples": samples = args[i + 1].to_int()
		i += 2
	if output.is_empty() or library.is_empty() or samples not in [0, 4]:
		printerr("msaa_transition: output, fixture library and samples 0|4 required")
		quit(2)
		return
	if DisplayServer.get_name().to_lower() == "headless" or RenderingServer.get_video_adapter_name().is_empty():
		printerr("msaa_transition: a real Windows/GPU viewport is required")
		quit(2)
		return
	if DirAccess.make_dir_recursive_absolute(output) != OK:
		printerr("msaa_transition: cannot create output directory")
		quit(2)
		return
	create_timer(30.0).timeout.connect(_timeout)
	machine = RtaMachine.new()
	if not machine.load_library(library) or machine.start({"lists": 1, "sound": 0}) != 0:
		printerr("msaa_transition: fixture cannot start: ", machine.get_error())
		quit(2)
		return
	drawer = RtaDrawer.new()
	drawer.setup(machine, root.get_viewport_rid(), Vector2i(SIZE,SIZE), samples)
	drawer.set_shader_code(FileAccess.get_file_as_string("res://shaders/gs_draw.gdshaderinc"))
	var passed := true
	for phase in range(PHASES.size()):
		if machine.step(-1) != 1:
			printerr("msaa_transition: missing authored frame ", phase)
			quit(2)
			return
		drawer.submit()
		# Submission uses UPDATE_ONCE; do not submit/repaint another list while observing its result.
		for frame in range(4):
			await process_frame
			await RenderingServer.frame_post_draw
		var texture := drawer.get_shown_texture()
		var image := drawer.get_shown_image()
		var row := {"phase": PHASES[phase], "frame": machine.get_frame_number(), "passed": false}
		if image != null and not image.is_empty() and image.get_size() == Vector2i(SIZE,SIZE):
			var right := PackedByteArray()
			for y in range(4,60):
				if y >= 28 and y < 36:
					continue
				for x in range(40,60):
					var p := image.get_pixel(x,y)
					right.append(int(round(p.r*255.0)))
					right.append(int(round(p.g*255.0)))
					right.append(int(round(p.b*255.0)))
			if phase == 0:
				retained = right
			var wrong := 0
			for k in range(right.size()):
				var x := 40 + (k / 3) % 20
				var expected := int(retained[k])
				if phase >= 6 and x >= 44 and x < 48:
					expected = 255 if k % 3 == 2 else 0
				if abs(int(right[k])-expected) > 3:
					wrong += 1
			var grey := 0
			var bright := 0
			for y in range(4,60):
				for x in range(2,32):
					var p := image.get_pixel(x,y)
					if p.r > 0.9 and p.g > 0.9 and p.b > 0.9:
						bright += 1
					if p.r > 0.04 and p.r < 0.96 and absf(p.r-p.g) < 0.015 and absf(p.r-p.b) < 0.015:
						grey += 1
			var top := image.get_pixel(48,16)
			var bottom := image.get_pixel(48,48)
			var seed_ok := (top.g > 0.4 and top.r < 0.1 and bottom.r > 0.65 and bottom.g < 0.2) or (top.r > 0.65 and top.g < 0.2 and bottom.g > 0.4 and bottom.r < 0.1)
			var wide := phase in [3,5,6,7]
			var expected_aa := samples == 4 and phase in [5,6,7]
			if texture not in seen_textures:
				seen_textures.append(texture)
			var texture_ok := (phase in [0,5,8] or texture == last_texture) and seen_textures.size() <= 2
			last_texture = texture
			var depth_pixel := image.get_pixel(0,32)
			var depth_expected := Color.BLUE if phase in [6,7] else (Color.GREEN if phase in [5,8] else Color.RED)
			# KEEP preserves colour; these real viewports begin each newly rendered 3-D frame
			# with cleared depth even in the zero-sample control. Same-frame probes still
			# require the nearer red/blue layer to defeat the later lower green layer.
			var depth_ok := absf(depth_pixel.r-depth_expected.r) < 0.05 and absf(depth_pixel.g-depth_expected.g) < 0.05 and absf(depth_pixel.b-depth_expected.b) < 0.05
			row.merge({"width": SIZE, "height": SIZE, "logical_width": 1280 if wide else 640,
				"requested_samples": 4 if expected_aa else 0, "partial_edge_pixels": grey,
				"opaque_triangle_pixels": bright, "retained_rgb_mismatches": wrong,
				"depth_pixel_rgb": [depth_pixel.r,depth_pixel.g,depth_pixel.b], "depth_reset_or_order_valid": depth_ok,
				"unchanged_mode_reuses_texture": texture_ok, "target_texture_id": texture.get_id(), "seed_pattern_valid": seed_ok,
				"capture_exit": image.save_png(output.path_join(PHASES[phase]+".png"))})
			row.passed = depth_ok and seed_ok and wrong == 0 and texture_ok and bright > 300 and row.capture_exit == OK
			row.passed = bool(row.passed) and (grey >= 12 if expected_aa else grey == 0)
		passed = passed and bool(row.passed)
		results.append(row)
		print("msaa_transition: ", JSON.stringify(row))
	var report := {"passed": passed, "godot": Engine.get_version_info().get("string", ""),
		"adapter": RenderingServer.get_video_adapter_name(), "driver": RenderingServer.get_current_rendering_driver_name(),
		"renderer": RenderingServer.get_current_rendering_method(), "setup_samples": samples, "distinct_target_textures": seen_textures.size(),
		"scope": "authored RTAG frames through production RtaMachine and RtaDrawer; actual GPU coverage, colour retention and mode-change depth reset",
		"shader_sha256": FileAccess.get_file_as_string("res://shaders/gs_draw.gdshaderinc").sha256_text(),
		"drawer_figures": drawer.figures(), "cases": results}
	var file := FileAccess.open(output.path_join("msaa-transition-result.json"),FileAccess.WRITE)
	if file == null:
		printerr("msaa_transition: cannot write result")
		quit(2)
		return
	file.store_string(JSON.stringify(report,"\t")+"\n")
	file.close()
	drawer.release()
	machine.stop()
	finished = true
	quit(0 if passed else 1)
