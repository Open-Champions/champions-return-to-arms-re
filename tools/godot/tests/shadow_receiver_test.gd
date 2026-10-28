extends SceneTree
# Actual production scene_take -> retained mesh -> scene_caster, plus an authored receiver.
const PHASES := ["seed_far","left_shadow","left_unshadowed","left_shadow_restored","right_shadow","right_repeat","outside","return_left"]
const CASTER_X := [1000.0,-1.0,-1.0,-1.0,1.0,1.0,1000.0,-1.0]
const SHADOW := ["none","A","none","A","B","B","none","A"]
const SIZE := Vector2i(128,128)
const TAN_HALF_FOV := 0.5773502691896257
const RECEIVER_CODE := "shader_type spatial; render_mode cull_disabled,specular_disabled,ambient_light_disabled; void fragment(){ ALBEDO=vec3(1.0); ROUGHNESS=1.0; } void light(){ DIFFUSE_LIGHT += ATTENUATION*LIGHT_COLOR/PI; }"
var out: String = ""
var library: String = ""
var machine: RtaMachine
var drawer: RtaDrawer
var scenario := RID()
var sun := RID()
var sun_instance := RID()
var receiver_instance := RID()
var receiver_mesh: PlaneMesh
var receiver_material: ShaderMaterial
var receiver_shader: Shader
var rows: Array = []
var images: Array[Image] = []
var raw_images: Array[PackedByteArray] = []
var finished: bool = false

func _initialize() -> void:
	_run.call_deferred()

func _timeout() -> void:
	if not finished:
		printerr("shadow_receiver: FAIL 40-second GPU timeout")
		quit(2)

func _black(colour: Color) -> bool:
	return maxf(colour.r,maxf(colour.g,colour.b))<0.075

func _cyan(colour: Color) -> bool:
	return colour.r<0.15 and colour.g>0.7 and colour.b>0.7

func _grey(colour: Color) -> bool:
	return maxf(absf(colour.r-colour.g),absf(colour.g-colour.b))<0.06

func _luma(colour: Color) -> float:
	return (colour.r+colour.g+colour.b)/3.0

func _shadow_centre(name: String) -> Vector2:
	# Receiver depth7; rays(1,-1,0) shift the caster shadow+1X.
	return Vector2(0.5 if name=="A" else 0.5+2.0/(14.0*TAN_HALF_FOV),0.5)

func _roi(image: Image, point: Vector2) -> Dictionary:
	var centre := Vector2i(int(point.x*SIZE.x),int(point.y*SIZE.y))
	var sum: float = 0.0
	var lo: float = 1.0
	var hi: float = 0.0
	var grey: bool = true
	for dy in range(-2,3):
		for dx in range(-2,3):
			var colour: Color = image.get_pixel(centre.x+dx,centre.y+dy)
			var value: float = _luma(colour)
			sum += value
			lo=minf(lo,value)
			hi=maxf(hi,value)
			grey=grey and _grey(colour)
	return {"mean":sum/25.0,"minimum":lo,"maximum":hi,"all_grey":grey,"centre_pixel":[centre.x,centre.y]}

func _add_receiver_and_sun() -> void:
	receiver_shader=Shader.new()
	receiver_shader.code=RECEIVER_CODE
	receiver_material=ShaderMaterial.new()
	receiver_material.shader=receiver_shader
	receiver_mesh=PlaneMesh.new()
	receiver_mesh.size=Vector2(6.0,6.0)
	receiver_mesh.orientation=PlaneMesh.FACE_Y
	receiver_mesh.material=receiver_material
	receiver_instance=RenderingServer.instance_create2(receiver_mesh.get_rid(),scenario)
	RenderingServer.instance_set_transform(receiver_instance,Transform3D(Basis(),Vector3(0,-1,0)))
	RenderingServer.instance_geometry_set_cast_shadows_setting(receiver_instance,RenderingServer.SHADOW_CASTING_SETTING_OFF)
	RenderingServer.directional_shadow_atlas_set_size(2048,true)
	RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_HARD)
	sun=RenderingServer.directional_light_create()
	RenderingServer.light_set_color(sun,Color.WHITE)
	RenderingServer.light_set_param(sun,RenderingServer.LIGHT_PARAM_ENERGY,1.0)
	RenderingServer.light_set_shadow(sun,true)
	RenderingServer.light_directional_set_shadow_mode(sun,RenderingServer.LIGHT_DIRECTIONAL_SHADOW_ORTHOGONAL)
	RenderingServer.light_set_param(sun,RenderingServer.LIGHT_PARAM_SHADOW_MAX_DISTANCE,20.0)
	RenderingServer.light_set_param(sun,RenderingServer.LIGHT_PARAM_SHADOW_BIAS,0.005)
	RenderingServer.light_set_param(sun,RenderingServer.LIGHT_PARAM_SHADOW_NORMAL_BIAS,0.0)
	RenderingServer.light_set_param(sun,RenderingServer.LIGHT_PARAM_SHADOW_BLUR,0.0)
	RenderingServer.light_set_cull_mask(sun,1)
	sun_instance=RenderingServer.instance_create2(sun,scenario)
	RenderingServer.instance_set_transform(sun_instance,Transform3D(Basis(),Vector3.ZERO).looking_at(Vector3(1,-1,0),Vector3(0,0,1)))

func _capture(phase: int) -> void:
	for tick in 4:
		await process_frame
		await RenderingServer.frame_post_draw
	var name: String = PHASES[phase]
	var row: Dictionary = {"phase":name,"frame":machine.get_frame_number(),"expected_shadow":SHADOW[phase],"expected_caster_x":CASTER_X[phase],"passed":false}
	var image: Image = drawer.get_shown_image()
	if image == null or image.is_empty() or image.get_size()!=SIZE:
		rows.append(row)
		images.append(null)
		raw_images.append(PackedByteArray())
		return
	image.convert(Image.FORMAT_RGBA8)
	var lit: int = 0
	var cyan_count: int = 0
	var outside: int = 0
	var wrong_colour: int = 0
	var cyan_outside: int = 0
	var caster_x: float = CASTER_X[phase]
	var caster_centre := Vector2(0.5+caster_x/(12.0*TAN_HALF_FOV),0.5)
	var caster_bounds := Rect2(caster_centre-Vector2(0.055,0.055),Vector2(0.11,0.11))
	for y in SIZE.y:
		for x in SIZE.x:
			var colour: Color = image.get_pixel(x,y)
			if _black(colour):
				continue
			lit += 1
			var point := Vector2((float(x)+0.5)/SIZE.x,(float(y)+0.5)/SIZE.y)
			if not Rect2(0.11,0.11,0.78,0.78).has_point(point):
				outside += 1
			if _cyan(colour):
				cyan_count += 1
				if not caster_bounds.has_point(point):
					cyan_outside += 1
			elif not _grey(colour):
				wrong_colour += 1
	var want_visible: bool = absf(caster_x)<2.0
	var cyan_valid: bool = cyan_count>40 and cyan_count<240 if want_visible else cyan_count==0
	var byte_data: PackedByteArray = image.get_data()
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(byte_data)
	var byte_hash: String = hashing.finish().hex_encode()
	var png_exit: int = image.save_png(out.path_join(name+".png"))
	var file: FileAccess = FileAccess.open(out.path_join(name+".rgba"),FileAccess.WRITE)
	var raw_saved: bool = file != null
	if file != null:
		file.store_buffer(byte_data)
		file.close()
	var scene_info: Dictionary = drawer.get_scene_info()
	var figures: String = scene_info.get("figures","")
	var match_result: RegExMatch = RegEx.create_from_string("kept meshes: ([0-9.]+) draws.*? ([0-9.]+) made, ([0-9.]+) written again in place, ([0-9]+) held").search(figures)
	var kept: Dictionary = {}
	if match_result != null:
		kept={"draws_per_list":float(match_result.get_string(1)),"made_per_list":float(match_result.get_string(2)),"written_again_per_list":float(match_result.get_string(3)),"held":int(match_result.get_string(4))}
	var kept_valid: bool = not kept.is_empty() and int(kept.get("held",-1))==1 and float(kept.get("made_per_list",0.0))>0.0 and (phase==0 or float(kept.get("written_again_per_list",0.0))>0.0)
	var camera: Transform3D = scene_info.get("camera",Transform3D())
	var camera_valid: bool = camera.origin.is_equal_approx(Vector3(0,6,0)) and camera.basis.x.is_equal_approx(Vector3(1,0,0)) and camera.basis.y.is_equal_approx(Vector3(0,0,-1)) and camera.basis.z.is_equal_approx(Vector3(0,1,0))
	row.merge({"size":[SIZE.x,SIZE.y],"scenario_id":str(scenario.get_id()),"same_scenario":drawer.get_world_scenario()==scenario,
		"roi_A":_roi(image,_shadow_centre("A")),"roi_B":_roi(image,_shadow_centre("B")),
		"lit_pixels":lit,"cyan_pixels":cyan_count,"cyan_coverage_valid":cyan_valid,"cyan_outside_expected_bounds":cyan_outside,
		"pixels_outside_receiver_bounds":outside,"wrong_colour_pixels":wrong_colour,"camera_valid":camera_valid,
		"scene_figures":figures,"drawer_figures":drawer.figures(),"retained_rounded_per_list":kept,"retained_path_valid":kept_valid,
		"capture_exit":png_exit,"raw_rgba_saved":raw_saved,"rgba_bytes":byte_data.size(),"rgba_sha256":byte_hash},true)
	row["base_pixels_valid"]=lit>SIZE.x*SIZE.y*0.40 and lit<SIZE.x*SIZE.y*0.65 and cyan_valid and cyan_outside==0 and outside==0 and wrong_colour==0
	row.passed=bool(row.base_pixels_valid) and camera_valid and kept_valid and bool(row.same_scenario) and png_exit==OK and raw_saved and byte_data.size()==SIZE.x*SIZE.y*4 and machine.get_frame_number()==phase+1
	rows.append(row)
	images.append(image)
	raw_images.append(byte_data)

func _judge_shadows() -> bool:
	if images.size()!=PHASES.size() or images[2]==null:
		return false
	var reference_A: Dictionary = rows[2].get("roi_A",{})
	var reference_B: Dictionary = rows[2].get("roi_B",{})
	var reference_valid: bool = float(reference_A.get("minimum",0.0))>0.4 and float(reference_B.get("minimum",0.0))>0.4 and bool(reference_A.get("all_grey",false)) and bool(reference_B.get("all_grey",false))
	var reference: float = (float(reference_A.get("mean",0.0))+float(reference_B.get("mean",0.0)))*0.5
	var passed: bool = reference_valid
	for phase in rows.size():
		var row: Dictionary = rows[phase]
		var expected: String = SHADOW[phase]
		var roi_valid: bool = reference_valid and row.has("roi_A") and row.has("roi_B")
		for letter in ["A","B"]:
			var roi: Dictionary = row.get("roi_"+letter,{})
			var ref: Dictionary = reference_A if letter=="A" else reference_B
			var dark: bool = expected==letter
			var okay: bool = bool(roi.get("all_grey",false)) and (float(roi.get("maximum",1.0))<float(ref.get("minimum",0.0))*0.55 if dark else float(roi.get("minimum",0.0))>float(ref.get("mean",1.0))*0.85)
			row["roi_"+letter+"_expected_dark"]=dark
			row["roi_"+letter+"_valid"]=okay
			roi_valid=roi_valid and okay
		var dark_pixels: int = 0
		var outside: int = 0
		var image: Image = images[phase]
		if image != null:
			var allowed: Rect2 = Rect2(_shadow_centre(expected)-Vector2(0.06,0.06),Vector2(0.12,0.12))
			for y in SIZE.y:
				for x in SIZE.x:
					var point := Vector2((float(x)+0.5)/SIZE.x,(float(y)+0.5)/SIZE.y)
					if not Rect2(0.16,0.16,0.68,0.68).has_point(point):
						continue
					var colour: Color = image.get_pixel(x,y)
					if not _cyan(colour) and _grey(colour) and _luma(colour)<reference*0.45:
						dark_pixels += 1
						if expected=="none" or not allowed.has_point(point):
							outside += 1
		var mask_valid: bool = outside==0 and (dark_pixels>16 and dark_pixels<320 if expected!="none" else dark_pixels==0)
		row.merge({"unshadowed_reference_valid":reference_valid,"shadow_roi_valid":roi_valid,"dark_receiver_pixels":dark_pixels,"dark_pixels_outside_expected_shadow":outside,"shadow_mask_valid":mask_valid},true)
		row.passed=bool(row.passed) and roi_valid and mask_valid
		passed=passed and bool(row.passed)
	return passed

func _run() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var index: int = 0
	while index<args.size():
		if index+1>=args.size() or args[index] not in ["--out","--lib"]:
			printerr("shadow_receiver: --out EMPTY_DIRECTORY --lib AUTHORED_LIBRARY required")
			quit(2)
			return
		if args[index]=="--out": out=ProjectSettings.globalize_path(args[index+1])
		else: library=ProjectSettings.globalize_path(args[index+1])
		index += 2
	if out.is_empty() or library.is_empty() or DisplayServer.get_name()=="headless" or RenderingServer.get_video_adapter_name().is_empty() or not DirAccess.dir_exists_absolute(out) or not DirAccess.get_files_at(out).is_empty() or not DirAccess.get_directories_at(out).is_empty():
		printerr("shadow_receiver: real GPU, authored library, and existing EMPTY private output required")
		quit(2)
		return
	root.title="AGENT TEST - production retained shadow receiver"
	root.set_flag(Window.FLAG_NO_FOCUS,true)
	create_timer(40.0).timeout.connect(_timeout)
	machine=RtaMachine.new()
	if not machine.load_library(library) or machine.start({"lists":1,"scene3d":1,"sound":0})!=0:
		printerr("shadow_receiver: authored library start failed: ",machine.get_error())
		quit(2)
		return
	drawer=RtaDrawer.new()
	drawer.setup(machine,root.get_viewport_rid(),SIZE,0)
	drawer.set_shader_code((load("res://shaders/gs_draw.gdshaderinc") as ShaderInclude).code)
	drawer.set_scene_mode(true)
	for option in ["packets","keep","shadows"]: drawer.set_scene_option(option,1)
	for option in ["batch","prepass","model_look","lit","contacts","sky","near_fade","tween"]: drawer.set_scene_option(option,0)
	drawer.set_scene_option("model_smooth",1)
	for phase in PHASES.size():
		if machine.step(-1)!=1:
			printerr("shadow_receiver: missing authored frame ",phase)
			quit(2)
			return
		drawer.submit()
		if phase==0:
			scenario=drawer.get_world_scenario()
			if not scenario.is_valid():
				printerr("shadow_receiver: production world scenario absent")
				quit(2)
				return
			_add_receiver_and_sun()
		# No black ABI clearing quad; explicitly clear the authored world instead.
		var environment: RID = drawer.get_world_environment()
		RenderingServer.environment_set_background(environment,RenderingServer.ENV_BG_COLOR)
		RenderingServer.environment_set_bg_color(environment,Color.BLACK)
		RenderingServer.light_set_shadow(sun,phase!=2)
		await _capture(phase)
	var passed: bool = _judge_shadows()
	var repeat_equal: bool = not raw_images[4].is_empty() and raw_images[4]==raw_images[5]
	var return_equal: bool = not raw_images[1].is_empty() and raw_images[1]==raw_images[3] and raw_images[1]==raw_images[7]
	var far_equal: bool = not raw_images[0].is_empty() and raw_images[0]==raw_images[6]
	passed=passed and repeat_equal and return_equal and far_equal
	for row in rows: print("shadow_receiver: ",JSON.stringify(row))
	# These authored instances belong to the production scenario: free them first.
	RenderingServer.free_rid(receiver_instance)
	RenderingServer.free_rid(sun_instance)
	RenderingServer.free_rid(sun)
	receiver_instance=RID();sun_instance=RID();sun=RID()
	receiver_mesh=null;receiver_material=null;receiver_shader=null
	drawer.release()
	machine.stop()
	drawer=null;machine=null
	for tick in 2: await process_frame
	var report: Dictionary = {"passed":passed,"godot":Engine.get_version_info(),"driver":RenderingServer.get_current_rendering_driver_name(),"adapter":RenderingServer.get_video_adapter_name(),
		"cases":rows,"stationary_full_rgba_equal":repeat_equal,"return_full_rgba_equal":return_equal,"outside_full_rgba_equal":far_equal,
		"scenario_id":str(scenario.get_id()),"scope":"Authored ABI exercises production retained packet mesh updates and normally culled scene_caster, with a separate authored lit receiver and directional light. No game data or production hooks.",
		"identity_limit":"Constant packet mesh/kind/count and held1/positive written-again figures ground the existing in-place source branch. Rounded per-list figures are not exact totals or runtime mesh/caster RID values.",
		"capture_alpha_limit":"Production get_shown_image returns RGB8; RGBA8 alpha255 is synthesized, not original scene alpha.",
		"negative_control_contract":"The separately built one-line no-customAABB variant must retain visible cyan movement but fail moved receiver shadow masks. If it passes, stale-bounds discrimination is not established."}
	var file: FileAccess = FileAccess.open(out.path_join("shadow-receiver-result.json"),FileAccess.WRITE)
	if file==null:
		printerr("shadow_receiver: cannot save result")
		quit(2)
		return
	file.store_string(JSON.stringify(report,"\t")+"\n")
	file.close()
	finished=true
	quit(0 if passed else 1)
