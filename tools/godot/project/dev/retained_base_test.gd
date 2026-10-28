extends SceneTree
# Actual production retained scene placement, using authored RTAG packets only.
const PHASES := ["seed", "repeat", "move", "recolour", "material_hide", "material_restore", "grow", "shrink", "flat_quad", "flat_triangle", "retained_return", "absent", "reappear", "resize", "resize_back", "retire_target", "recreate_target", "absent_before_flat", "flat_after_empty", "retained_after_flat", "absent_before_rebind", "rebind_same_material", "retire_material_idle", "material_recreated"]
const EXPECTED := [["red","black"],["red","black"],["black","green"],["black","blue"],["black","black"],["black","blue"],["yellow","yellow"],["cyan","black"],["black","magenta"],["white","black"],["cyan","black"],["black","black"],["cyan","black"],["cyan","black"],["cyan","black"],["black","black"],["cyan","black"],["black","black"],["black","magenta"],["cyan","black"],["black","black"],["cyan","black"],["black","black"],["cyan","black"]]
var output := ""
var library := ""
var finished := false
var machine: RtaMachine
var drawer: RtaDrawer
var results: Array = []
var old_scenario: RID
var made_before_idle := -1
var held_before_idle := -1
var held_after_idle := -1
var frame_before_idle := -1

func _initialize() -> void:
	_run.call_deferred()

func _timeout() -> void:
	if not finished:
		printerr("retained_base: FAIL 40-second GPU timeout")
		quit(2)

func _matches(c: Color, name: String) -> bool:
	var high := [c.r > 0.75, c.g > 0.75, c.b > 0.75]
	var low := [c.r < 0.075, c.g < 0.075, c.b < 0.075]
	match name:
		"black": return low[0] and low[1] and low[2]
		"red": return high[0] and low[1] and low[2]
		"green": return low[0] and high[1] and low[2]
		"blue": return low[0] and low[1] and high[2]
		"yellow": return high[0] and high[1] and low[2]
		"cyan": return low[0] and high[1] and high[2]
		"magenta": return high[0] and low[1] and high[2]
		"white": return high[0] and high[1] and high[2]
	return false

func _observe(image: Image, phase: int) -> Dictionary:
	var size := image.get_size()
	var expected: Array = EXPECTED[phase]
	var left := image.get_pixel(int(size.x*0.33), int(size.y*0.5))
	var right := image.get_pixel(int(size.x*0.66), int(size.y*0.5))
	var outside := 0
	var lit := 0
	for y in size.y:
		for x in size.x:
			if _matches(image.get_pixel(x,y), "black"):
				continue
			lit += 1
			var p := Vector2((float(x)+0.5)/size.x,(float(y)+0.5)/size.y)
			var allowed := false
			if expected[0] != "black":
				allowed = Rect2(0.20,0.30,0.30,0.40).has_point(p)
			if expected[1] != "black":
				allowed = allowed or Rect2(0.50,0.30,0.30,0.40).has_point(p)
			if not allowed:
				outside += 1
	var blank: bool = expected[0] == "black" and expected[1] == "black"
	var coverage := lit == 0 if blank else lit > size.x*size.y*0.02
	return {"passed": _matches(left,expected[0]) and _matches(right,expected[1]) and coverage and outside == 0,
		"size": [size.x,size.y], "expected": expected, "left_rgb": [left.r,left.g,left.b], "right_rgb": [right.r,right.g,right.b],
		"coloured_pixels": lit,"pixels_outside_expected_bounds": outside,"coverage_valid": coverage}

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var k := 0
	while k < args.size():
		if k+1 >= args.size() or args[k] not in ["--out","--lib"]:
			printerr("retained_base: expected --out DIR --lib AUTHORED_LIBRARY")
			quit(2)
			return
		if args[k] == "--out": output = ProjectSettings.globalize_path(args[k+1])
		else: library = ProjectSettings.globalize_path(args[k+1])
		k += 2
	if output.is_empty() or library.is_empty() or DisplayServer.get_name() == "headless" or RenderingServer.get_video_adapter_name().is_empty():
		printerr("retained_base: authored library/output and a real GPU are required")
		quit(2)
		return
	if DirAccess.make_dir_recursive_absolute(output) != OK:
		quit(2)
		return
	root.title = "AGENT TEST - authored retained base"
	root.set_flag(Window.FLAG_NO_FOCUS,true)
	create_timer(40.0).timeout.connect(_timeout)
	machine = RtaMachine.new()
	if not machine.load_library(library) or machine.start({"lists":1,"scene3d":1,"sound":0}) != 0:
		printerr("retained_base: fixture start failed: ",machine.get_error())
		quit(2)
		return
	drawer = RtaDrawer.new()
	drawer.setup(machine,root.get_viewport_rid(),Vector2i(64,64),0)
	drawer.set_shader_code(FileAccess.get_file_as_string("res://shaders/gs_draw.gdshaderinc"))
	drawer.set_scene_mode(true)
	for option in ["packets","keep","shadows"]: drawer.set_scene_option(option,1)
	for option in ["batch","prepass","model_look","model_smooth","lit","contacts","sky","near_fade","tween"]: drawer.set_scene_option(option,0)
	var passed := true
	for phase in PHASES.size():
		if phase == 13: drawer.set_output_size(Vector2i(96,96))
		if phase == 14: drawer.set_output_size(Vector2i(64,64))
		if machine.step(-1) != 1:
			printerr("retained_base: missing authored frame ",phase)
			quit(2)
			return
		drawer.submit()
		if phase == 22:
			# 193 real production submissions cross the 120-list expiry and 64-list sweep.
			# Empty models keep the old pool slot/cache but clear its base; no production hooks.
			for idle in 192:
				if machine.step(-1) != 1:
					printerr("retained_override: missing retirement idle list")
					quit(2)
					return
				drawer.submit()
		for tick in 4:
			await process_frame
			await RenderingServer.frame_post_draw
		var row := {"phase":PHASES[phase],"frame":machine.get_frame_number(),"passed":false}
		if phase == 15:
			row.passed = not drawer.get_shown_texture().is_valid()
			row["retired_target_has_no_picture"] = row.passed
		else:
			var image := drawer.get_shown_image()
			if image != null and not image.is_empty():
				row.merge(_observe(image,phase),true)
				var want := 96 if phase == 13 else 64
				row.passed = row.passed and image.get_size() == Vector2i(want,want)
				row["capture_exit"] = image.save_png(output.path_join(PHASES[phase]+".png"))
				row.passed = row.passed and row.capture_exit == OK
			var scenario := drawer.get_world_scenario()
			row["scenario_id"] = scenario.get_id()
			if phase == 14: old_scenario = scenario
			if phase == 16:
				row["new_scenario_after_retirement"] = scenario.is_valid() and scenario != old_scenario
				row.passed = row.passed and row.new_scenario_after_retirement
		row["scene_figures"] = drawer.get_scene_info().get("figures","")
		row["drawer_figures"] = drawer.figures()
		var mat_match := RegEx.create_from_string("([0-9]+) materials made \\(([0-9]+) held\\)").search(String(row.drawer_figures))
		if mat_match != null:
			row["materials_made"] = int(mat_match.get_string(1))
			row["materials_held"] = int(mat_match.get_string(2))
		if phase == 21:
			frame_before_idle = machine.get_frame_number()
			made_before_idle = int(row.get("materials_made",-1))
			held_before_idle = int(row.get("materials_held",-1))
		if phase == 22:
			row["actual_idle_submission_count"] = machine.get_frame_number() - frame_before_idle
			row.passed = row.passed and row.actual_idle_submission_count == 193
			held_after_idle = int(row.get("materials_held",-1))
			row["idle_retired_materials"] = held_after_idle >= 0 and held_before_idle > held_after_idle
			row.passed = row.passed and row.idle_retired_materials
		if phase == 23:
			row["same_state_material_recreated"] = made_before_idle >= 0 and int(row.get("materials_made",-1)) > made_before_idle
			row.passed = row.passed and row.same_state_material_recreated
		results.append(row)
		passed = passed and bool(row.passed)
		print("retained_base: ",JSON.stringify(row))
	var figures := String(drawer.get_scene_info().get("figures",""))
	var pattern := RegEx.create_from_string("kept meshes: ([0-9.]+) draws.*? ([0-9.]+) made, ([0-9.]+) written again")
	# Long empty submissions deliberately dilute the final formatted averages. Require
	# both positives in ONE recorded pre-idle snapshot, rather than combining rows.
	var retained_evidence: Dictionary = {}
	for index in mini(22,results.size()):
		var snapshot: Dictionary = results[index]
		var sample := pattern.search(String(snapshot.get("scene_figures","")))
		if sample != null and float(sample.get_string(1)) > 0.0 and float(sample.get_string(3)) > 0.0:
			retained_evidence = {"phase_index":index,"phase":snapshot.phase,"frame":snapshot.frame,
				"kept_draws_per_list":float(sample.get_string(1)),"written_again_per_list":float(sample.get_string(3)),
				"scene_figures":snapshot.scene_figures,"before_retirement_idle":true}
			break
	var retained_path := not retained_evidence.is_empty()
	passed = passed and retained_path
	var report := {"passed":passed,"godot":Engine.get_version_info(),"driver":RenderingServer.get_current_rendering_driver_name(),
		"adapter":RenderingServer.get_video_adapter_name(),"retained_path_confirmed":retained_path,"retained_path_evidence":retained_evidence,"scene_figures":figures,"cases":results,
		"scope":"Authored24phase production retained fixture: adds unused-base-to-flat-clear, same-material rebind and actual material expiry/recreation. No game data.",
		"caster_coverage":"shadows1 exercises scene_caster and new-scenario reset; no direct shadow-receiver or AABB-culling pixel proof (instances ignore culling).",
		"shader_sha256":FileAccess.get_file_as_string("res://shaders/gs_draw.gdshaderinc").sha256_text()}
	var file := FileAccess.open(output.path_join("retained-base-result.json"),FileAccess.WRITE)
	if file == null:
		printerr("retained_base: cannot write result")
		quit(2)
		return
	file.store_string(JSON.stringify(report,"\t")+"\n")
	file.close()
	drawer.release()
	machine.stop()
	drawer = null
	machine = null
	for tick in 2: await process_frame
	finished = true
	quit(0 if passed else 1)
