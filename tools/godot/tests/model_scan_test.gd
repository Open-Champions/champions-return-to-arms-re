extends SceneTree
# Private authored ABI fixture. Production RtaDrawer APIs only; no game library.
const PHASES := ["empty","near_shared_normals","repeat","move_recolour","grow20","empty_after_grow","small_after_grow","hidden","far","return_near","smooth1_control","zero_contact_texture_control","restore"]
const SIZE := Vector2i(256,256)
const EXPECTED_MODELS := [0,2,2,2,40,0,2,0,2,2,2,2,2]
const EXPECTED_CURVED := [0,2,2,2,40,0,2,0,0,2,0,2,2]
const GLOBALS := {
	"rta_sky_zenith":Vector4.ZERO,"rta_sky_ground":Vector4.ZERO,"rta_sky_sun":Vector4(0,0,1,0),"rta_sky_sun_colour":Vector4(1,1,1,0),
	"rta_lock":Vector4.ZERO,"rta_lock_player":Vector4.ZERO,"rta_fog_range":Vector4(400,1350,0,200),"rta_fog_amount":Vector4(0,0.5,1,0),
	"rta_fog_colour":Vector4.ZERO,"rta_light_ambient":Vector4(1,1,1,0),"rta_model":Vector4(0.35,0.7,1,0.7),"rta_model_rim":Vector4(0.8,0.9,1,0),"rta_tween":Vector4.ZERO}
var output := ""
var library := ""
var machine: RtaMachine
var drawer: RtaDrawer
var contact_image: Image
var contact_texture: ImageTexture
var ring_texture: ImageTexture
var rows: Array = []
var raw: Array[PackedByteArray] = []
var finished := false
var previous_models := 0
var previous_curved := 0
var previous_hidden := 0

func _initialize() -> void:
	_run.call_deferred()

func _timeout() -> void:
	if not finished:
		printerr("model_scan: FAIL 45-second authored GPU timeout")
		quit(2)

func _expected(phase: int) -> PackedFloat32Array:
	var found := PackedFloat32Array()
	if phase in [0,5]: return found
	if phase == 4:
		for n in 16: found.append_array(PackedFloat32Array([float((n%5)*60-120),float((n/5)*60-90),0.0,12.0]))
	else:
		found.append_array(PackedFloat32Array([60.0 if phase==3 else 0.0,1200.0 if phase==8 else 0.0,0.0,20.0]))
	return found

func _upload(found: PackedFloat32Array, zero: bool) -> void:
	for n in 16:
		var offset := n*4
		var colour := Color(0,0,0,0)
		if not zero and offset+3<found.size(): colour=Color(found[offset],found[offset+1],found[offset+2],found[offset+3])
		contact_image.set_pixel(n,0,colour)
	contact_texture.update(contact_image)

func _different(a: PackedByteArray,b: PackedByteArray) -> int:
	if a.size()!=b.size(): return -1
	var changed := 0
	for n in a.size():
		if a[n]!=b[n]: changed += 1
	return changed

func _digest(bytes: PackedByteArray) -> String:
	var context := HashingContext.new()
	if context.start(HashingContext.HASH_SHA256)!=OK or context.update(bytes)!=OK: return ""
	return context.finish().hex_encode()

func _capture(phase: int,found: PackedFloat32Array,contact_ok: bool) -> void:
	for tick in 4:
		await process_frame
		await RenderingServer.frame_post_draw
	var image: Image = drawer.get_shown_image()
	var bytes := PackedByteArray()
	var scene_info: Dictionary=drawer.get_scene_info()
	var figures := String(scene_info.get("figures",""))
	var model_pattern := RegEx.create_from_string("models: ([0-9.]+) solid model draws a list in the cleaner look, ([0-9.]+) of them curved \\(([0-9]+) x ([0-9]+)\\), ([0-9.]+) curved corners a list")
	var match_row := model_pattern.search(figures)
	var model_total := -1
	var curved_total := -1
	var counters_ok := false
	var frames := machine.get_frame_number()
	# Existing public API exposes rounded per-list averages only. Each authored
	# model has exactly2draws, so totals are even. At<=13lists, .1 rounding has
	# <.65draw error: decoding to nearest even total is unambiguous. This is a
	# fixture-specific inference, not a new exact production counter interface.
	if match_row!=null and frames==phase+1:
		model_total=roundi(float(match_row.get_string(1))*frames/2.0)*2
		curved_total=roundi(float(match_row.get_string(2))*frames/2.0)*2
		var hidden_total := int(scene_info.get("hidden_draws",-1))
		counters_ok=model_total-previous_models==EXPECTED_MODELS[phase] and curved_total-previous_curved==EXPECTED_CURVED[phase] and hidden_total-previous_hidden==(2 if phase==7 else 0)
		counters_ok=counters_ok and int(match_row.get_string(3))==(1 if phase==10 else 2) and int(match_row.get_string(4))==(1 if phase==10 else 2)
		# Generated corners count only mesh rebuilds; retained hits still count
		# curved draws. Require initial actual PN generation, not a false equality
		# between cumulative generated corners and every curved draw thereafter.
		if phase==1: counters_ok=counters_ok and float(match_row.get_string(5))>0.0
		previous_models=model_total
		previous_curved=curved_total
		previous_hidden=hidden_total
	var row := {"phase":PHASES[phase],"frame":frames,"passed":false,"ordered_contact_float_bytes_equal":contact_ok,
		"contact_float_bytes_hex":found.to_byte_array().hex_encode(),"contacts":Array(found),"expected_contacts":Array(_expected(phase)),
		"model_smooth":1 if phase==10 else 2,"model_look":true,"contacts_enabled":true,"contact_texture_intentionally_zero":phase==11,
		"hidden_object101":phase==7,"far_contact_only_pixel_coverage":phase==8,"scene_figures":figures,"drawer_figures":drawer.figures(),
		"per_phase_model_curved_hidden_counts_valid":counters_ok,"inferred_even_model_total":model_total,"inferred_even_curved_total":curved_total,
		"expected_phase_models":EXPECTED_MODELS[phase],"expected_phase_curved":EXPECTED_CURVED[phase],"hidden_draws_cumulative":scene_info.get("hidden_draws",-1),
		"generated_curved_corners_per_list_rounded":float(match_row.get_string(5)) if match_row!=null else -1.0}
	if image!=null and not image.is_empty() and image.get_size()==SIZE:
		image.convert(Image.FORMAT_RGBA8)
		bytes=image.get_data()
		var visible := 0
		var model_pixels := 0
		for y in SIZE.y:
			for x in SIZE.x:
				var colour := image.get_pixel(x,y)
				if maxf(colour.r,maxf(colour.g,colour.b))>0.075: visible += 1
				if colour.b>colour.r+0.1 and colour.g>colour.r+0.1: model_pixels += 1
		var png_exit: int=image.save_png(output.path_join(PHASES[phase]+".png"))
		var file := FileAccess.open(output.path_join(PHASES[phase]+".rgba"),FileAccess.WRITE)
		if file!=null:
			file.store_buffer(bytes)
			file.close()
		row.merge({"visible_pixels":visible,"model_coloured_pixels":model_pixels,"png_exit":png_exit,"rgba_bytes":bytes.size(),
			"raw_sha256":_digest(bytes),"raw_saved":file!=null},true)
		var body_expected := phase not in [0,5,7,8]
		row.passed=contact_ok and counters_ok and visible>512 and (model_pixels>24 if body_expected else model_pixels==0) and png_exit==OK and file!=null and bytes.size()==SIZE.x*SIZE.y*4
	rows.append(row)
	raw.append(bytes)
	print("model_scan: ",JSON.stringify(row))

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index<args.size():
		if index+1>=args.size() or args[index] not in ["--out","--lib"]:
			printerr("model_scan: --out EXISTING_EMPTY_DIRECTORY --lib AUTHORED_LIBRARY required")
			quit(2)
			return
		if args[index]=="--out": output=ProjectSettings.globalize_path(args[index+1])
		else: library=ProjectSettings.globalize_path(args[index+1])
		index += 2
	if output.is_empty() or library.is_empty() or not DirAccess.dir_exists_absolute(output) or not DirAccess.get_files_at(output).is_empty() or not DirAccess.get_directories_at(output).is_empty() or DisplayServer.get_name()=="headless" or RenderingServer.get_video_adapter_name().is_empty():
		printerr("model_scan: actual GPU and fresh existing empty private output required")
		quit(2)
		return
	root.title="AGENT TEST - authored model scan"
	root.set_flag(Window.FLAG_NO_FOCUS,true)
	create_timer(45.0).timeout.connect(_timeout)
	for name in GLOBALS: RenderingServer.global_shader_parameter_add(name,RenderingServer.GLOBAL_VAR_TYPE_VEC4,GLOBALS[name])
	RenderingServer.global_shader_parameter_add("rta_sky_ring",RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2D,RID())
	RenderingServer.global_shader_parameter_add("rta_contacts",RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2D,RID())
	var ring_image := Image.create(2,2,false,Image.FORMAT_RGB8)
	ring_image.fill(Color.BLACK)
	ring_texture=ImageTexture.create_from_image(ring_image)
	RenderingServer.global_shader_parameter_set("rta_sky_ring",ring_texture.get_rid())
	contact_image=Image.create(16,1,false,Image.FORMAT_RGBAF)
	contact_image.fill(Color(0,0,0,0))
	contact_texture=ImageTexture.create_from_image(contact_image)
	RenderingServer.global_shader_parameter_set("rta_contacts",contact_texture.get_rid())
	machine=RtaMachine.new()
	if not machine.load_library(library) or machine.start({"lists":1,"scene3d":1,"sound":0})!=0:
		printerr("model_scan: authored library start failed: ",machine.get_error())
		quit(2)
		return
	drawer=RtaDrawer.new()
	drawer.setup(machine,root.get_viewport_rid(),SIZE,4)
	drawer.set_shader_code((load("res://shaders/gs_draw.gdshaderinc") as ShaderInclude).code)
	drawer.set_scene_mode(true)
	for option in ["packets","keep","model_look","contacts"]: drawer.set_scene_option(option,1)
	for option in ["batch","prepass","shadows","lit","sky","near_fade","tween"]: drawer.set_scene_option(option,0)
	drawer.set_scene_option("model_near",520)
	drawer.set_scene_option("model_crease",0.35)
	for phase in PHASES.size():
		drawer.set_hidden_objects(PackedInt64Array([101]) if phase==7 else PackedInt64Array())
		drawer.set_scene_option("model_smooth",1 if phase==10 else 2)
		if machine.step(-1)!=1:
			printerr("model_scan: missing authored ABI frame ",phase)
			quit(2)
			return
		drawer.submit()
		var found: PackedFloat32Array=drawer.get_sky_info().get("contacts",PackedFloat32Array())
		var contact_ok := found.to_byte_array()==_expected(phase).to_byte_array()
		_upload(found,phase==11)
		await _capture(phase,found,contact_ok)
	var passed := rows.size()==PHASES.size()
	for row in rows: passed=passed and bool(row.passed)
	var same_near := raw[1]==raw[2] and raw[1]==raw[6] and raw[1]==raw[9] and raw[1]==raw[12]
	var same_empty := raw[0]==raw[5]
	var smooth_differences := _different(raw[1],raw[10])
	var contact_differences := _different(raw[1],raw[11])
	var pattern := RegEx.create_from_string("models: ([0-9.]+) solid model draws a list in the cleaner look, ([0-9.]+) of them curved \\(2 x 2\\), ([0-9.]+) curved corners a list")
	var evidence := pattern.search(String(rows[1].scene_figures))
	var curved_path := evidence!=null and float(evidence.get_string(2))>0.0 and float(evidence.get_string(3))>0.0
	passed=passed and same_near and same_empty and smooth_differences>0 and contact_differences>0 and curved_path
	var report := {"passed":passed,"godot":Engine.get_version_info(),"driver":RenderingServer.get_current_rendering_driver_name(),"adapter":RenderingServer.get_video_adapter_name(),
		"cases":rows,"near_repeat_and_restores_full_bytes_equal":same_near,"empty_after_growth_full_bytes_equal":same_empty,"smooth1_control_differing_bytes":smooth_differences,
		"zero_contact_texture_control_differing_bytes":contact_differences,"curved_model_path_positive":curved_path,"requested_samples":4,"performance_qualified":false,
		"scope":"Authored13phase production model scan, PN model and contact-ground fixture; no game data. Far geometry is offscreen: far retention is contact-byte coverage only.",
		"limits":"Complete weld table is not observable through public APIs. CPU source-extracted controls qualify its exact state. Model/curved totals inferred from rounded averages using this13list authored even-draw invariant; hidden totals are public cumulative values. Positive curved figures plus smooth1 pixel differences prove curved output, not isolated shared-normal contribution. get_shown_image is RGB8; stored RGBA8 alpha255 is synthesized."}
	drawer.release()
	machine.stop()
	drawer=null
	machine=null
	RenderingServer.global_shader_parameter_set("rta_contacts",RID())
	RenderingServer.global_shader_parameter_set("rta_sky_ring",RID())
	contact_texture=null
	ring_texture=null
	contact_image=null
	for name in GLOBALS: RenderingServer.global_shader_parameter_remove(name)
	RenderingServer.global_shader_parameter_remove("rta_contacts")
	RenderingServer.global_shader_parameter_remove("rta_sky_ring")
	for tick in 2: await process_frame
	var result_file := FileAccess.open(output.path_join("model-scan-result.json"),FileAccess.WRITE)
	if result_file==null:
		printerr("model_scan: cannot save result")
		quit(2)
		return
	result_file.store_string(JSON.stringify(report,"\t")+"\n")
	result_file.close()
	finished=true
	quit(0 if passed else 1)
