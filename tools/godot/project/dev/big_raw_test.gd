extends SceneTree
# Authored input through actual production RtaMachine -> RtaDrawer; no game.
const PHASES := ["seed", "same_count_move_recolour", "grow", "shrink_reuse", "zero", "flat", "raw_threshold_return", "raw_stress"]
const COUNTS := [98307,98307,147459,110001,0,48,98307,294912]
const OFFSETS := [Vector2(-.025,-.02),Vector2(.025,.02),Vector2(-.02,.025),Vector2(.02,-.025),Vector2.ZERO,Vector2(-.025,.025),Vector2.ZERO,Vector2(-.015,.015)]
const COLOURS := [Color.RED,Color.GREEN,Color.BLUE,Color.YELLOW,Color.CYAN,Color.MAGENTA,Color.WHITE]
const MADE := [1,0,1,0,0,0,1,1]
const REUSED := [0,1,0,1,0,0,0,0]
var output := ""
var library := ""
var finished := false
var reflect_readback_y: bool = false
var machine: RtaMachine
var drawer: RtaDrawer

func _initialize() -> void:
	_run.call_deferred()

func _timeout() -> void:
	if not finished:
		printerr("big_raw: FAIL 60-second GPU timeout")
		quit(2)

func _match(actual: Color, expected: Color) -> bool:
	return absf(actual.r-expected.r)<.12 and absf(actual.g-expected.g)<.12 and absf(actual.b-expected.b)<.12

func _rect(tile: int, phase: int) -> Rect2:
	var projected_centre: Vector2 = Vector2(.18+float(tile%4)*.2133333333,.30 if tile<4 else .70)+OFFSETS[phase]
	# get_shown_image flips RenderingDevice readback (Vulkan/D3D12), unlike GL.
	# Reflect rectangle edges and phase motion only for those actual drivers.
	var image_centre: Vector2 = Vector2(projected_centre.x,1.0-projected_centre.y if reflect_readback_y else projected_centre.y)
	return Rect2(image_centre-Vector2(.07,.11),Vector2(.14,.22))

func _observe(image: Image, phase: int) -> Dictionary:
	var size := image.get_size()
	var regions: Array = []
	var wrong := 0
	var outside := 0
	var lit := 0
	var inside := 0
	for tile in 8:
		var rectangle := _rect(tile,phase)
		var centre := rectangle.get_center()*Vector2(size)
		var pixel := image.get_pixel(int(centre.x),int(centre.y))
		var expected: Color = COLOURS[(tile+phase*2)%7]
		regions.append({"tile":tile,"rect":[rectangle.position.x,rectangle.position.y,rectangle.size.x,rectangle.size.y],"expected_rgb":[expected.r,expected.g,expected.b],"actual_rgba":[pixel.r,pixel.g,pixel.b,pixel.a],"passed":_match(pixel,Color.BLACK if phase==4 else expected)})
	for y in size.y:
		for x in size.x:
			var colour := image.get_pixel(x,y)
			var p := Vector2((float(x)+.5)/size.x,(float(y)+.5)/size.y)
			var allowed := false
			if phase!=4:
				for tile in 8:
					var rectangle := _rect(tile,phase)
					if rectangle.grow(1.5/size.x).has_point(p): allowed=true
					if rectangle.grow(-2.0/size.x).has_point(p):
						inside+=1
						if not _match(colour,COLOURS[(tile+phase*2)%7]): wrong+=1
			if not _match(colour,Color.BLACK):
				lit+=1
				if not allowed: outside+=1
	var good := wrong==0 and outside==0 and (lit==0 if phase==4 else lit>size.x*size.y*.15)
	for row in regions: good=good and row.passed
	return {"passed":good,"size":[size.x,size.y],"regions":regions,"interior_pixels_checked":inside,"wrong_interior_pixels":wrong,"outside_pixels":outside,"lit_pixels":lit}

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var k := 0
	while k<args.size():
		if k+1>=args.size() or args[k] not in ["--out","--lib"]:
			printerr("big_raw: expected --out DIR --lib AUTHORED_LIBRARY")
			quit(2)
			return
		if args[k]=="--out": output=ProjectSettings.globalize_path(args[k+1])
		else: library=ProjectSettings.globalize_path(args[k+1])
		k+=2
	if output.is_empty() or library.is_empty() or DisplayServer.get_name()=="headless" or RenderingServer.get_video_adapter_name().is_empty():
		printerr("big_raw: authored library/output and actual GPU required")
		quit(2)
		return
	var actual_driver: String = RenderingServer.get_current_rendering_driver_name()
	if actual_driver not in ["vulkan","opengl3","d3d12"]:
		printerr("big_raw: unsupported readback oracle driver ",actual_driver)
		quit(2)
		return
	reflect_readback_y=actual_driver in ["vulkan","d3d12"]
	if DirAccess.make_dir_recursive_absolute(output)!=OK:
		quit(2)
		return
	root.title="AGENT TEST - authored BIG raw fill"
	root.set_flag(Window.FLAG_NO_FOCUS,true)
	create_timer(60.0).timeout.connect(_timeout)
	machine=RtaMachine.new()
	if not machine.load_library(library) or machine.start({"lists":1,"scene3d":1,"sound":0})!=0:
		printerr("big_raw: fixture library start failed")
		quit(2)
		return
	drawer=RtaDrawer.new()
	drawer.setup(machine,root.get_viewport_rid(),Vector2i(128,128),0)
	# Match the production main.gd loader; dependencies are staged and imported first.
	var shader_include := load("res://shaders/gs_draw.gdshaderinc") as ShaderInclude
	if shader_include == null:
		printerr("big_raw: required production ShaderInclude failed to load")
		quit(2)
		return
	drawer.set_shader_code(shader_include.code)
	drawer.set_scene_mode(true)
	for option in ["packets","keep","shadows","batch","prepass","model_look","model_smooth","lit","contacts","sky","near_fade","tween"]: drawer.set_scene_option(option,0)
	var passed := true
	var results: Array = []
	var old_made := 0
	var old_reused := 0
	var pattern := RegEx.create_from_string("big draws written in place ([0-9]+), made ([0-9]+)")
	for phase in PHASES.size():
		if machine.step(-1)!=1:
			printerr("big_raw: missing authored phase ",phase)
			quit(2)
			return
		drawer.submit()
		for tick in 4:
			await process_frame
			await RenderingServer.frame_post_draw
		var row := {"phase":PHASES[phase],"frame":machine.get_frame_number(),"count":COUNTS[phase],"passed":false}
		row["frame_counts_match"]=machine.get_vertex_count()==COUNTS[phase]+6 and machine.get_draw_count()==2 and machine.get_frame_number()==phase+1
		row["drawer_figures"]=drawer.figures()
		row["scene_figures"]=drawer.get_scene_info().get("figures","")
		row["frame_description"]=drawer.describe_frame(4)
		var found := pattern.search(String(row.drawer_figures))
		row["big_path_counts_found"]=found!=null
		if found!=null:
			var reused := int(found.get_string(1))
			var made := int(found.get_string(2))
			row["big_made"]=made
			row["big_reused"]=reused
			row["big_made_delta"]=made-old_made
			row["big_reused_delta"]=reused-old_reused
			row["big_path_delta_matches"]=made-old_made==MADE[phase] and reused-old_reused==REUSED[phase]
			old_made=made
			old_reused=reused
		var image := drawer.get_shown_image()
		if image!=null and not image.is_empty():
			row.merge(_observe(image,phase),true)
			row["capture_exit"]=image.save_png(output.path_join(PHASES[phase]+".png"))
			image.convert(Image.FORMAT_RGBA8)
			var file := FileAccess.open(output.path_join(PHASES[phase]+".rgba"),FileAccess.WRITE)
			if file!=null:
				file.store_buffer(image.get_data())
				file.close()
			row["raw_rgba_written"]=file!=null
			row.passed=row.passed and image.get_size()==Vector2i(128,128) and row.capture_exit==OK and row.raw_rgba_written
		row.passed=row.passed and row.frame_counts_match and row.get("big_path_delta_matches",false)
		passed=passed and row.passed
		results.append(row)
		print("big_raw: ",JSON.stringify(row))
	var report := {"passed":passed,"godot":Engine.get_version_info(),"driver":RenderingServer.get_current_rendering_driver_name(),"adapter":RenderingServer.get_video_adapter_name(),"cases":results,"scope":"Authored eight-phase production BIG raw geometry; no normals/packets/batch, count changes, same-count position+colour mutation, zero, flat/raw layout and 294912-corner stress. No game/disc/assets.","samples":0,"output_size":[128,128],"shader_sha256":FileAccess.get_file_as_string("res://shaders/gs_draw.gdshaderinc").sha256_text()}
	var file := FileAccess.open(output.path_join("big-raw-result.json"),FileAccess.WRITE)
	if file==null:
		quit(2)
		return
	file.store_string(JSON.stringify(report,"\t")+"\n")
	file.close()
	drawer.release()
	machine.stop()
	drawer=null
	machine=null
	for tick in 2: await process_frame
	finished=true
	quit(0 if passed else 1)
