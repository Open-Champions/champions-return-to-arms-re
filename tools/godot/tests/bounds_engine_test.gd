extends SceneTree
# Engine dependency control only: production pooled instances ignore culling.
# A fixed live instance keeps its mesh RID throughout all observed transitions.
const CODE := "shader_type spatial; render_mode unshaded,cull_disabled; void fragment(){ ALBEDO=vec3(1.0,0.0,0.0); }"
const SIZE := Vector2i(64,64)
var out: String = ""
var vp: SubViewport
var mesh := RID()
var instance := RID()
var shader := RID()
var material := RID()
var rows: Array = []
var captures: Dictionary = {}
var finished: bool = false
var mesh_identity: String = ""
var instance_identity: String = ""

func _initialize() -> void:
	_run.call_deferred()

func _timeout() -> void:
	if not finished:
		printerr("bounds_engine: FAIL 40-second GPU timeout")
		quit(2)

func _positions(centre_x: float) -> PackedByteArray:
	# Six uncompressed float3 positions, matching the production vertex upload API.
	return PackedFloat32Array([
		centre_x-0.5,-0.5,-4.0, centre_x+0.5,-0.5,-4.0, centre_x-0.5,0.5,-4.0,
		centre_x-0.5,0.5,-4.0, centre_x+0.5,-0.5,-4.0, centre_x+0.5,0.5,-4.0
	]).to_byte_array()

func _box(centre_x: float) -> AABB:
	# Nonzero depth avoids a degenerate culling volume; all vertices lie inside it.
	return AABB(Vector3(centre_x-0.5,-0.5,-4.01),Vector3(1.0,1.0,0.02))

func _black(colour: Color) -> bool:
	return colour.r<0.075 and colour.g<0.075 and colour.b<0.075

func _red(colour: Color) -> bool:
	return colour.r>0.75 and colour.g<0.075 and colour.b<0.075

func _shot(name: String, visible: bool) -> void:
	for tick in 4:
		await process_frame
		await RenderingServer.frame_post_draw
	var image: Image = vp.get_texture().get_image()
	var row: Dictionary = {"phase":name,"expected_visible":visible,"passed":false,
		"mesh_rid":str(mesh.get_id()),"instance_rid":str(instance.get_id())}
	if image != null and not image.is_empty():
		image.convert(Image.FORMAT_RGBA8)
		var lit: int = 0
		var outside: int = 0
		var wrong_colour: int = 0
		for y in image.get_height():
			for x in image.get_width():
				var colour: Color = image.get_pixel(x,y)
				if _black(colour):
					continue
				lit += 1
				if not _red(colour):
					wrong_colour += 1
				var point := Vector2((float(x)+0.5)/SIZE.x,(float(y)+0.5)/SIZE.y)
				if not Rect2(0.34,0.34,0.32,0.32).has_point(point):
					outside += 1
		var centre: Color = image.get_pixel(32,32)
		var coverage: bool = lit>SIZE.x*SIZE.y*0.02 if visible else lit==0
		var save_exit: int = image.save_png(out.path_join(name+".png"))
		var rgba: PackedByteArray = image.get_data()
		var hashing := HashingContext.new()
		hashing.start(HashingContext.HASH_SHA256)
		hashing.update(rgba)
		var rgba_sha256: String = hashing.finish().hex_encode()
		var raw_file: FileAccess = FileAccess.open(out.path_join(name+".rgba"),FileAccess.WRITE)
		var raw_saved: bool = raw_file != null
		if raw_file != null:
			raw_file.store_buffer(rgba)
			raw_file.close()
		captures[name] = rgba
		row.merge({"size":[image.get_width(),image.get_height()],"centre_rgb":[centre.r,centre.g,centre.b],
			"coloured_pixels":lit,"pixels_outside_expected_bounds":outside,"wrong_colour_pixels":wrong_colour,
			"coverage_valid":coverage,"capture_exit":save_exit,"raw_rgba_saved":raw_saved,
			"rgba_bytes":rgba.size(),"rgba_sha256":rgba_sha256},true)
		row.passed = image.get_size()==SIZE and (_red(centre) if visible else _black(centre)) and coverage and outside==0 and wrong_colour==0 and save_exit==OK and raw_saved and rgba.size()==SIZE.x*SIZE.y*4
	row.passed = bool(row.passed) and row.mesh_rid==mesh_identity and row.instance_rid==instance_identity
	rows.append(row)
	print("bounds_engine: ",JSON.stringify(row))

func _run() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size()!=2 or args[0]!="--out" or DisplayServer.get_name()=="headless" or RenderingServer.get_video_adapter_name().is_empty():
		printerr("bounds_engine: --out FRESH_DIRECTORY and a real GPU are required")
		quit(2)
		return
	out=ProjectSettings.globalize_path(args[1])
	if not DirAccess.dir_exists_absolute(out) or not DirAccess.get_files_at(out).is_empty() or not DirAccess.get_directories_at(out).is_empty():
		printerr("bounds_engine: existing empty private output directory required")
		quit(2)
		return
	root.title="AGENT TEST - engine mesh bounds dependencies"
	root.set_flag(Window.FLAG_NO_FOCUS,true)
	create_timer(40.0).timeout.connect(_timeout)
	vp=SubViewport.new()
	vp.size=SIZE
	vp.own_world_3d=true
	vp.render_target_clear_mode=SubViewport.CLEAR_MODE_ALWAYS
	vp.render_target_update_mode=SubViewport.UPDATE_ALWAYS
	root.add_child(vp)
	var environment := Environment.new()
	environment.background_mode=Environment.BG_COLOR
	environment.background_color=Color.BLACK
	var world_environment := WorldEnvironment.new()
	world_environment.environment=environment
	vp.add_child(world_environment)
	var camera := Camera3D.new()
	camera.fov=60.0
	camera.near=0.1
	camera.far=30.0
	# Identity transform: looking along -Z. At Z=-4, the side plane is X=+/-2.3094.
	vp.add_child(camera)
	camera.make_current()
	shader=RenderingServer.shader_create()
	RenderingServer.shader_set_code(shader,CODE)
	material=RenderingServer.material_create()
	RenderingServer.material_set_shader(material,shader)
	mesh=RenderingServer.mesh_create()
	RenderingServer.mesh_add_surface(mesh,{"primitive":RenderingServer.PRIMITIVE_TRIANGLES,
		"format":RenderingServer.ARRAY_FORMAT_VERTEX|RenderingServer.ARRAY_FLAG_FORMAT_CURRENT_VERSION|RenderingServer.ARRAY_FLAG_USE_DYNAMIC_UPDATE,
		"vertex_data":_positions(8.0),"vertex_count":6,"aabb":_box(8.0)})
	RenderingServer.mesh_surface_set_material(mesh,0,material)
	RenderingServer.mesh_set_custom_aabb(mesh,_box(8.0))
	instance=RenderingServer.instance_create()
	RenderingServer.instance_set_scenario(instance,vp.find_world_3d().scenario)
	RenderingServer.instance_set_base(instance,mesh)
	RenderingServer.instance_set_ignore_culling(instance,false)
	RenderingServer.instance_geometry_set_cast_shadows_setting(instance,RenderingServer.SHADOW_CASTING_SETTING_OFF)
	mesh_identity=str(mesh.get_id())
	instance_identity=str(instance.get_id())
	await _shot("seed_outside",false)
	RenderingServer.mesh_surface_update_vertex_region(mesh,0,0,_positions(0.0))
	await _shot("inside_vertices_stale_bounds",false)
	RenderingServer.instance_set_ignore_culling(instance,true)
	await _shot("stale_bounds_ignore_culling",true)
	RenderingServer.instance_set_ignore_culling(instance,false)
	await _shot("stale_bounds_culling_restored",false)
	# The tested dependency: this setter must notify the existing bound instance.
	# No instance base assignment is made after the original binding above.
	RenderingServer.mesh_set_custom_aabb(mesh,_box(0.0))
	await _shot("updated_bounds_same_binding",true)
	RenderingServer.mesh_surface_update_vertex_region(mesh,0,0,_positions(-8.0))
	RenderingServer.mesh_set_custom_aabb(mesh,_box(-8.0))
	await _shot("outside_vertices_updated_bounds",false)
	RenderingServer.mesh_surface_update_vertex_region(mesh,0,0,_positions(0.0))
	RenderingServer.mesh_set_custom_aabb(mesh,_box(0.0))
	await _shot("inside_again_same_binding",true)
	var same_visible: bool = captures.get("stale_bounds_ignore_culling")==captures.get("updated_bounds_same_binding") and captures.get("updated_bounds_same_binding")==captures.get("inside_again_same_binding")
	var same_blank: bool = captures.get("seed_outside")==captures.get("inside_vertices_stale_bounds") and captures.get("seed_outside")==captures.get("stale_bounds_culling_restored") and captures.get("seed_outside")==captures.get("outside_vertices_updated_bounds")
	var passed: bool = rows.size()==7 and same_visible and same_blank
	for row in rows:
		passed = passed and bool(row.passed)
	RenderingServer.free_rid(instance)
	RenderingServer.free_rid(mesh)
	RenderingServer.free_rid(material)
	RenderingServer.free_rid(shader)
	instance=RID();mesh=RID();material=RID();shader=RID()
	vp.queue_free()
	for tick in 2:
		await process_frame
	vp=null
	var report: Dictionary = {"passed":passed,"godot":Engine.get_version_info(),
		"driver":RenderingServer.get_current_rendering_driver_name(),"adapter":RenderingServer.get_video_adapter_name(),
		"cases":rows,"same_visible_full_rgba":same_visible,"same_blank_full_rgba":same_blank,
		"mesh_rid":mesh_identity,"instance_rid":instance_identity,"base_assignments_during_observations":1,
		"scope":"Authored engine dependency control only. Vertex upload then custom AABB change notifies a live normally culled instance without rebinding its unchanged mesh RID. Stale-AABB/ignore-culling negative control; seven captures/six transitions. No game data or production helper exercised.",
		"production_limit":"Production ordinary pooled instances force ignore_culling=true. This engine control does not close production caster/receiver AABB pixel coverage or prove shadow receiver behaviour."}
	var file: FileAccess = FileAccess.open(out.path_join("bounds-engine-result.json"),FileAccess.WRITE)
	if file == null:
		printerr("bounds_engine: cannot write result")
		quit(2)
		return
	file.store_string(JSON.stringify(report,"\t")+"\n")
	file.close()
	finished=true
	quit(0 if passed else 1)
