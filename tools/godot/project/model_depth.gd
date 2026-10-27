extends RefCounted
# Depth for a model immediately before its existing ordered colour draw. Both
# shaders use their original vertex transform and alpha rejection. The twin adds
# no colour and casts no shadow; it never moves depth across an earlier effect.

var enabled := OS.get_environment("RTA_MODEL_DEPTH") != "0"
var twins := {}
var shaders := {}
var materials := {}


func depth_shader(source: Shader) -> Shader:
	var key := source.get_instance_id()
	if not shaders.has(key):
		var shader := Shader.new()
		shader.code = source.code.replace("shader_type spatial;", "shader_type spatial;\n#define MODEL_DEPTH")
		shaders[key] = shader
	return shaders[key]


func depth_material(source: ShaderMaterial) -> ShaderMaterial:
	var key := source.get_instance_id()
	if not materials.has(key):
		# Asset caches can be dropped between levels. A depth material must not
		# keep an old level's textures alive after its source material is gone.
		for old in materials.keys():
			if materials[old].source.get_ref() == null:
				materials.erase(old)
		var material := source.duplicate() as ShaderMaterial
		material.shader = depth_shader(source.shader)
		materials[key] = {"material": material, "source": weakref(source)}
	return materials[key].material


func create(source: RID, mesh: RID, scenario: RID) -> void:
	var instance := RenderingServer.instance_create2(mesh, scenario)
	RenderingServer.instance_geometry_set_cast_shadows_setting(instance, RenderingServer.SHADOW_CASTING_SETTING_OFF)
	RenderingServer.instance_set_visible(instance, false)
	twins[source] = {"instance": instance, "visible": false, "allowed": false}


func set_enabled(on: bool) -> void:
	if enabled == on:
		return
	enabled = on
	for t in twins.values():
		RenderingServer.instance_set_visible(t.instance, on and bool(t.visible) and bool(t.allowed))


func base(source: RID, mesh: RID) -> void:
	if twins.has(source):
		RenderingServer.instance_set_base(twins[source].instance, mesh)


func skeleton(source: RID, bones: RID) -> void:
	if twins.has(source):
		RenderingServer.instance_attach_skeleton(twins[source].instance, bones)


func transform(source: RID, value: Transform3D) -> void:
	if twins.has(source):
		RenderingServer.instance_set_transform(twins[source].instance, value)


func bounds(source: RID, box: AABB) -> void:
	if twins.has(source):
		RenderingServer.instance_set_custom_aabb(twins[source].instance, box)


func visible(source: RID, on: bool) -> void:
	if twins.has(source):
		twins[source].visible = on
		RenderingServer.instance_set_visible(twins[source].instance, on and enabled and bool(twins[source].allowed))


func order(source: RID, position: float) -> void:
	if twins.has(source):
		RenderingServer.instance_set_pivot_data(twins[source].instance, position - 0.125, false)


func surface(source: RID, index: int, material: RID) -> void:
	if twins.has(source):
		RenderingServer.instance_set_surface_override_material(twins[source].instance, index, material)


func free_instance(source: RID) -> void:
	if twins.has(source):
		RenderingServer.free_rid(twins[source].instance)
		twins.erase(source)
		if twins.is_empty():
			materials.clear()


func release() -> void:
	for source in twins.keys():
		free_instance(source)
	materials.clear()
	shaders.clear()


func allow(source: RID, on: bool) -> void:
	if twins.has(source):
		twins[source].allowed = on
		visible(source, twins[source].visible)
