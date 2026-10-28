extends SceneTree
# Real-GPU, authored-data-only RtaGpuTimer regression. No game library or disc.
var output := ""
var timer: RefCounted
var vp: SubViewport
var mat: ShaderMaterial
var rows: Array = []
var checks := {}
var render_world := false
var tag_world := false
var done := false

func _initialize() -> void:
	_run.call_deferred()

func _begin() -> void:
	if timer != null:
		timer.begin_frame(tag_world and render_world)

func _end() -> void:
	if timer != null:
		timer.end_frame()

func _viewport() -> SubViewport:
	var target := SubViewport.new()
	target.size = Vector2i(1280, 720)
	target.disable_3d = true
	target.render_target_update_mode = SubViewport.UPDATE_DISABLED
	get_root().add_child(target)
	var rectangle := ColorRect.new()
	rectangle.size = Vector2(target.size)
	rectangle.material = mat
	target.add_child(rectangle)
	return target

func _stage(label: String, work: int, cadence: int, tagged: bool, count: int) -> void:
	mat.set_shader_parameter("work_steps", work)
	tag_world = tagged
	for i in range(count):
		render_world = cadence > 0 and (cadence == 1 or i % cadence == 0)
		if render_world:
			RenderingServer.viewport_set_active(vp.get_viewport_rid(), false)
			RenderingServer.viewport_set_active(vp.get_viewport_rid(), true)
			RenderingServer.viewport_set_update_mode(vp.get_viewport_rid(), RenderingServer.VIEWPORT_UPDATE_ONCE)
		if label == "held_duplicate_poll":
			timer.begin_frame(false)
			timer.begin_frame(false)
		await process_frame
		rows.append({"stage": label, "step": i, "requested": render_world, "sample": timer.sample()})

func _fresh(label: String) -> Array:
	var found := {}
	for row in rows:
		if row.stage == label and row.step >= 30 and not row.sample.is_empty():
			found[row.sample.frame] = row.sample
	return found.values()

func _median(label: String) -> float:
	var values: Array = []
	for sample in _fresh(label):
		values.append(float(sample.gpu_ms))
	values.sort()
	return float(values[values.size() / 2]) if not values.is_empty() else -1.0

func _timeout() -> void:
	if not done:
		printerr("GPU_TIMER_TEST timeout")
		quit(2)

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2 or args[0] != "--out":
		printerr("expected --out PRIVATE_DIRECTORY")
		quit(2)
		return
	output = args[1]
	DirAccess.make_dir_recursive_absolute(output)
	if DisplayServer.get_name() == "headless" or RenderingServer.get_rendering_device() == null:
		printerr("GPU_TIMER_TEST requires a real RD renderer")
		quit(2)
		return
	if not ClassDB.class_exists("RtaGpuTimer"):
		printerr("GPU_TIMER_TEST requires the production extension")
		quit(2)
		return
	timer = ClassDB.instantiate("RtaGpuTimer")
	if not timer.has_method("set_viewport") or not timer.has_method("reset") or not timer.is_available():
		printerr("GPU_TIMER_TEST requires the completed RD provider")
		quit(1)
		return
	get_root().set_flag(Window.FLAG_NO_FOCUS, true)
	get_root().title = "AGENT TEST - authored completed GPU timer"
	get_root().size = Vector2i(384, 216)
	Engine.max_fps = 180
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	create_timer(35.0).timeout.connect(_timeout)
	var shader := Shader.new()
	shader.code = """
shader_type canvas_item;
render_mode unshaded;
uniform int work_steps = 8;
void fragment() {
 vec2 p = UV * vec2(1.327,2.173) + vec2(.1321,.717);
 for(int i=0;i<512;i++) { if(i>=work_steps) { break; } p=sin(p.yx*vec2(1.0013,1.0037)+vec2(.0017,.0023))+p*.017; }
 COLOR=vec4(.15+.75*abs(vec3(p,p.x-p.y)),1.0);
}
"""
	mat = ShaderMaterial.new()
	mat.shader = shader
	vp = _viewport()
	timer.set_viewport(vp.get_viewport_rid())
	RenderingServer.frame_pre_draw.connect(_begin)
	RenderingServer.frame_post_draw.connect(_end)
	await _stage("continuous_low", 8, 1, true, 90)
	await _stage("sparse_low", 8, 3, true, 180)
	await _stage("sparse_high", 512, 3, true, 180)
	await _stage("sparse_repeat", 8, 3, true, 180)
	var before: Dictionary = timer.sample()
	timer.reset()
	checks.reset_clears_immediately = timer.sample().is_empty()
	await _stage("untagged_high", 512, 1, false, 90)
	checks.untagged_world_rejected = timer.sample().is_empty()
	await _stage("reset_low", 8, 3, true, 180)
	var after: Dictionary = timer.sample()
	await _stage("held_duplicate_poll", 8, 0, false, 60)
	var held := _fresh("held_duplicate_poll")
	checks.held_frames_and_replayed_queries_keep_token = held.size() == 1
	checks.held_frames_keep_last_completed_value = held.size() == 1 and not timer.sample().is_empty()
	checks.reset_changes_epoch = not before.is_empty() and not after.is_empty() and int(after.generation) > int(before.generation)
	var old := vp
	old.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	vp = _viewport()
	var new_id := vp.get_viewport_rid().get_id()
	timer.set_viewport(vp.get_viewport_rid())
	checks.viewport_change_clears_immediately = timer.sample().is_empty()
	await _stage("new_viewport_low", 8, 3, true, 180)
	checks.current_viewport_only = true
	for sample in _fresh("new_viewport_low"):
		checks.current_viewport_only = checks.current_viewport_only and int(sample.viewport_id) == new_id
	var summaries := {}
	for label in ["continuous_low", "sparse_low", "sparse_high", "sparse_repeat", "reset_low", "new_viewport_low"]:
		var samples := _fresh(label)
		checks[label + "_fresh_batches"] = samples.size() >= (40 if label != "continuous_low" else 45)
		var requested := 0
		for row in rows:
			if row.stage == label and row.step >= 30 and bool(row.requested):
				requested += 1
		checks[label + "_no_replayed_world_ids"] = samples.size() <= requested + 1
		var valid := true
		for sample in samples:
			valid = valid and float(sample.gpu_ms) > 0.0 and sample.source == "rd_viewport" and int(sample.frame) > 0
		checks[label + "_completed_gpu_values"] = valid
		summaries[label] = {"unique_batches": samples.size(), "median_gpu_ms": _median(label)}
	checks.sparse_gpu_work_response = _median("sparse_high") > maxf(_median("sparse_low"), _median("sparse_repeat")) * 4.0
	checks.world_frame_ids_monotonic = true
	var previous := -1
	var generation := -1
	for row in rows:
		var sample: Dictionary = row.sample
		if sample.is_empty():
			continue
		if int(sample.generation) != generation:
			generation = int(sample.generation)
			previous = -1
		checks.world_frame_ids_monotonic = checks.world_frame_ids_monotonic and int(sample.frame) >= previous
		previous = int(sample.frame)
	RenderingServer.frame_pre_draw.disconnect(_begin)
	RenderingServer.frame_post_draw.disconnect(_end)
	var weak: WeakRef = weakref(timer)
	timer = null
	for i in range(8):
		await process_frame
	checks.pending_callbacks_release_owner = weak.get_ref() == null
	var passed := true
	for value in checks.values():
		passed = passed and bool(value)
	var report := {"passed": passed, "checks": checks, "summaries": summaries, "rows": rows, "driver": RenderingServer.get_current_rendering_driver_name(), "version": Engine.get_version_info(), "scope": "Production GPU timer with authored viewport work only; no game/steady FPS verdict."}
	var file := FileAccess.open(output.path_join("gpu-timer.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	done = true
	print("GPU_TIMER_TEST ", "PASS" if passed else "FAIL", " ", JSON.stringify({"checks": checks, "summaries": summaries}))
	quit(0 if passed else 1)
