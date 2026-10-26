extends RefCounted
# The drawer's rta_variants.txt covers GS shaders. These separate remaster/ER shaders also need actual mesh
# layouts in the world's scenario. Zero-area triangles exercise their pipelines without contributing a pixel.
const ResourceBudget := preload("res://resource_budget.gd")
var queue: Array = []
var held: Array = []
var instances: Array[RID] = []
var skeleton := RID()
var scenario := RID()
var last_frame := -1
var initialized := false


func tick(to: RID, look: Dictionary) -> void:
	if not to.is_valid():
		return
	if scenario != to:
		release()
		scenario = to
		initialized = false
	if not initialized:
		initialized = true
		var shaders: Array = []
		if String(look.get("remaster_models", "on")) == "on":
			shaders.append("remaster_model")
		if String(look.get("er_models", "off")) == "on" or String(look.get("er_creatures", "off")) == "on":
			shaders.append("er_armour")
		if String(look.get("er_world", "on")) == "on":
			shaders.append_array(["er_grass", "er_ruin"])
		for name in shaders:
			for bones in [0, 4, 8] if name in ["remaster_model", "er_armour"] else [0]:
				for compressed in [false, true]:
					queue.append([name, bones, compressed])
	if queue.is_empty():
		if last_frame >= 0 and Engine.get_process_frames() > last_frame + 4:
			release()
		return
	var started := ResourceBudget.begin()
	if started < 0:
		return
	var item: Array = queue.pop_front()
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.ZERO, Vector3.ZERO])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP, Vector3.UP, Vector3.UP])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2.ZERO])
	if item[0] != "er_grass":      # _tuft uses unindexed position/normal/UV; the other layers carry tangents
		arrays[Mesh.ARRAY_TANGENT] = PackedFloat32Array([1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1])
		arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2])
	if int(item[1]) > 0:
		var bones := PackedInt32Array()
		var weights := PackedFloat32Array()
		bones.resize(3 * int(item[1]))
		weights.resize(bones.size())
		for i in 3:
			weights[i * int(item[1])] = 1.0
		arrays[Mesh.ARRAY_BONES] = bones
		arrays[Mesh.ARRAY_WEIGHTS] = weights
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/%s.gdshader" % item[0])
	var mesh := ArrayMesh.new()
	var flags := Mesh.ARRAY_FLAG_COMPRESS_ATTRIBUTES if bool(item[2]) else 0
	if int(item[1]) == 8:
		flags |= Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, flags)
	mesh.surface_set_material(0, material)
	var base := mesh.get_rid()
	if item[0] == "er_grass":
		var multi := MultiMesh.new()
		multi.transform_format = MultiMesh.TRANSFORM_3D
		multi.use_colors = true
		multi.use_custom_data = true
		multi.mesh = mesh
		multi.instance_count = 1
		multi.set_instance_transform(0, Transform3D.IDENTITY)
		base = multi.get_rid()
		held.append(multi)
	var instance := RenderingServer.instance_create2(base, scenario)
	RenderingServer.instance_set_ignore_culling(instance, true)
	RenderingServer.instance_geometry_set_cast_shadows_setting(instance, RenderingServer.SHADOW_CASTING_SETTING_OFF)
	if int(item[1]) > 0:
		if not skeleton.is_valid():
			skeleton = RenderingServer.skeleton_create()
			RenderingServer.skeleton_allocate_data(skeleton, 1)
			RenderingServer.skeleton_bone_set_transform(skeleton, 0, Transform3D.IDENTITY)
		RenderingServer.instance_attach_skeleton(instance, skeleton)
	instances.append(instance)
	held.append(mesh)
	held.append(material)
	last_frame = Engine.get_process_frames()
	ResourceBudget.end(started)


func release() -> void:
	for instance in instances:
		RenderingServer.free_rid(instance)
	instances.clear()
	if skeleton.is_valid():
		RenderingServer.free_rid(skeleton)
	skeleton = RID()
	held.clear()
	queue.clear()
	last_frame = -1
