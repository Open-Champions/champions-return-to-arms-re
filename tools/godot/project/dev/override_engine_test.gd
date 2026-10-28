extends SceneTree
var out := ""
var vp: SubViewport
var mi: MeshInstance3D
var quad: QuadMesh
var quad2: QuadMesh
var surface: ShaderMaterial
var surface_shader: Shader
var shader_a := RID()
var shader_c := RID()
var material_a := RID()
var material_c := RID()
var rows: Array = []
var finished := false
const CODE := "shader_type spatial; render_mode unshaded,cull_disabled; uniform vec4 tint=vec4(1.0,0.0,0.0,1.0); void fragment(){ ALBEDO=tint.rgb; }"

func _initialize() -> void: _run.call_deferred()
func _timeout() -> void:
	if not finished:
		printerr("override_engine: FAIL timeout")
		quit(2)
func _matches(c: Color, want: Color) -> bool:
	return absf(c.r-want.r)<0.08 and absf(c.g-want.g)<0.08 and absf(c.b-want.b)<0.08
func _shot(name: String, want: Color) -> void:
	for frame in 4:
		await process_frame
		await RenderingServer.frame_post_draw
	var img := vp.get_texture().get_image()
	var center := img.get_pixel(32,32)
	var corner := img.get_pixel(1,1)
	var saved := img.save_png(out.path_join(name+".png"))
	var ok := _matches(center,want) and _matches(corner,Color.BLACK) and saved==OK
	rows.append({"phase":name,"passed":ok,"center":[center.r,center.g,center.b],"expected":[want.r,want.g,want.b],"corner":[corner.r,corner.g,corner.b],"capture_exit":saved})
func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size()!=2 or args[0]!="--out" or DisplayServer.get_name()=="headless" or RenderingServer.get_video_adapter_name().is_empty():
		printerr("override_engine: --out DIR and real GPU required")
		quit(2)
		return
	out=ProjectSettings.globalize_path(args[1])
	if DirAccess.make_dir_recursive_absolute(out)!=OK:
		quit(2)
		return
	root.title="AGENT TEST - engine override dependencies"
	root.set_flag(Window.FLAG_NO_FOCUS,true)
	create_timer(40).timeout.connect(_timeout)
	vp=SubViewport.new();vp.size=Vector2i(64,64);vp.own_world_3d=true
	vp.render_target_clear_mode=SubViewport.CLEAR_MODE_ALWAYS
	vp.render_target_update_mode=SubViewport.UPDATE_ALWAYS
	root.add_child(vp)
	var camera:=Camera3D.new();camera.position=Vector3(0,0,2);camera.fov=60;vp.add_child(camera)
	surface_shader=Shader.new();surface_shader.code=CODE
	surface=ShaderMaterial.new();surface.shader=surface_shader;surface.set_shader_parameter("tint",Color.BLUE)
	quad=QuadMesh.new();quad.size=Vector2(1,1);quad.material=surface
	quad2=QuadMesh.new();quad2.size=Vector2(1,1);quad2.material=surface
	mi=MeshInstance3D.new();mi.mesh=quad;vp.add_child(mi)
	shader_a=RenderingServer.shader_create();RenderingServer.shader_set_code(shader_a,CODE)
	material_a=RenderingServer.material_create();RenderingServer.material_set_shader(material_a,shader_a)
	RenderingServer.material_set_param(material_a,"tint",Color.RED)
	var old_id:=material_a.get_id()
	RenderingServer.instance_geometry_set_material_override(mi.get_instance(),material_a)
	await _shot("A_red",Color.RED)
	RenderingServer.material_set_param(material_a,"tint",Color(0,1,0,1))
	await _shot("same_A_uniform_green",Color(0,1,0,1))
	RenderingServer.shader_set_code(shader_a,CODE.replace("ALBEDO=tint.rgb","ALBEDO=vec3(tint.g,0.0,0.0)"))
	await _shot("same_A_shader_red",Color.RED)
	RenderingServer.instance_set_base(mi.get_instance(),RID())
	await _shot("empty_base",Color.BLACK)
	RenderingServer.instance_set_base(mi.get_instance(),quad2.get_rid())
	await _shot("new_base_keeps_A",Color.RED)
	RenderingServer.instance_geometry_set_material_override(mi.get_instance(),RID())
	await _shot("explicit_clear_surface_blue",Color.BLUE)
	RenderingServer.instance_geometry_set_material_override(mi.get_instance(),material_a)
	await _shot("A_restored",Color.RED)
	RenderingServer.free_rid(material_a);material_a=RID()
	await _shot("free_A_restores_surface_blue",Color.BLUE)
	shader_c=RenderingServer.shader_create();RenderingServer.shader_set_code(shader_c,CODE)
	material_c=RenderingServer.material_create();RenderingServer.material_set_shader(material_c,shader_c)
	RenderingServer.material_set_param(material_c,"tint",Color.YELLOW)
	RenderingServer.instance_geometry_set_material_override(mi.get_instance(),material_c)
	await _shot("new_C_yellow",Color.YELLOW)
	RenderingServer.instance_set_base(mi.get_instance(),RID())
	RenderingServer.instance_set_base(mi.get_instance(),quad.get_rid())
	await _shot("empty_rebind_keeps_C",Color.YELLOW)
	var passed:=old_id!=material_c.get_id()
	for row in rows: passed=passed and bool(row.passed)
	var report:={"passed":passed,"godot":Engine.get_version_info(),"cases":rows,"old_A_full_rid":old_id,"new_C_full_rid":material_c.get_id(),"new_generation_identity_differs":old_id!=material_c.get_id(),"driver":RenderingServer.get_current_rendering_driver_name(),"adapter":RenderingServer.get_video_adapter_name(),"scope":"Authored Godot4.5.2 engine assumption control only; does not exercise the production RtaDrawer helper or prove allocator local-index reuse. No repeated override setter during same-A uniform/shader/base updates."}
	var f:=FileAccess.open(out.path_join("override-engine-result.json"),FileAccess.WRITE)
	if f==null:
		quit(2)
		return
	f.store_string(JSON.stringify(report,"	")+"\n");f.close()
	RenderingServer.instance_geometry_set_material_override(mi.get_instance(),RID())
	vp.queue_free()
	for frame in 2: await process_frame
	RenderingServer.free_rid(material_c);material_c=RID()
	RenderingServer.free_rid(shader_a);RenderingServer.free_rid(shader_c)
	mi=null;vp=null;quad=null;quad2=null;surface=null;surface_shader=null
	for frame in 2: await process_frame
	finished=true
	quit(0 if passed else 1)
