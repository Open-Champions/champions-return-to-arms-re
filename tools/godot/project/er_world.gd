extends Node
# er_world.gd - the Elden Ring WORLD layer (look.er_world = on | off; scene mode, Remastered only: the Classic look sets it
# off).  The owner's own Elden Ring materials, grass and skies over the game's levels.  Only what is SEEN changes: the
# level's collision, paths and scripts are the game's, and nothing here reaches the simulation (two copies in a room, one
# with the layer and one without, stay in step).
#
# The files are the owner's own, converted on this machine into a local folder (never in the repository, never shared):
# $RTA_ER_WORLD, else local/souls-ref/er-world beside the staged project.  Without the folder nothing changes.
#   materials/<class>/albedo.png, normal.png     one square picture each (the class's Elden Ring terrain material)
#   grass/blades.png                              the grass cards (alpha: cut out)
#   sky/clouds.png                                a cloud layer (equirectangular above the horizon; alpha: cover)
#
# 1. Materials (RtaDrawer.set_world_layer, rta_world.cpp; shaders/er_world.gdshaderinc): every piece of a level is read
#    by its texture as one of grass, dirt, stone, cobble, wood, metal, sand, snow (or none) - its texels' colours and the
#    texture's edges - with a table of our own over it (er_world.cfg: by texture name, or a class remapped per level);
#    such a piece keeps its texture's colour at a coarse scale (the level's painted light) and takes its fine detail and
#    relief from the class's material, at world scale, triplanar.  `app er world info FILE` writes what was read.
# 2. Grass: points scattered by the drawer on the grass-class ground (RtaDrawer.get_grass: on what faces up, on pieces
#    that are mostly ground (not a bush's mound), where the texel under it is grass itself and no painted feature - a
#    flower, a stone, a path's edge - lies within a few units, not under a see-through decal and not against a wall),
#    drawn here as one MultiMesh of crossed cards near the eye, swaying, thinning out with distance
#    (shaders/er_grass.gdshader); no collision.
# 3. Sky: the cloud layer over scene_view.gd's sky sphere, tinted by the level's own sky colours (shaders/sky.gdshader).
# 4. Rebuild (look.er_rebuild): Elden Ring ruin pieces fitted over some of a level's shapes on this machine
#    (tools/godot/er_world_fit.py, which refuses a piece that strays more than a hand's width from the shape it stands in
#    for): rebuild/<level>/rebuild.json in the folder.  The drawer leaves out what the game draws inside the pieces'
#    volumes (RtaDrawer.set_world_hide: drawing only; the game's collision is untouched) and the pieces are drawn at its
#    place in the list (shaders/er_ruin.gdshader), in the colour the game gave the shape there and lit as the level's own
#    pieces are, with shadows of their own.  Their meshes and pictures (made by er_mesh_bake.gd) are read on worker threads
#    when the level is entered; until they are in, the game's own shapes are drawn.  An overlay (laid over the game's own
#    surface, nothing left out) has watch-only volumes instead: it is drawn only on frames the game drew a packet it lies on.
#
#   app er world info FILE     the textures drawn in the last 2 frames with what they read as, as JSON (and a summary)
#   app er world cost          the layer's own time per frame (mean and worst, microseconds) since the last `cost`
#   app er world grass [FILE]  how many points are scattered and drawn (FILE: every point near the eye, a line each)
#   app er world dump FILE     the next list's packets (every draw, world space) as an OBJ file (er_world_fit.py's input)
#   app er world rebuild       what the rebuild drew and left out

const CLASSES := ["grass", "dirt", "stone", "cobble", "wood", "metal", "sand", "snow", "water", "lava", "ice"]
const TEXTURE_SIZE := 1024
# scale, keep, amount of the classes the table (er_world.cfg) does not name: the liquids and ice keep most of the game's own
# picture (its painted ripples, its glowing flows) and take a broad, soft relief of their own
const CLASS_DEFAULTS := {"water": [240.0, 0.9, 0.45], "lava": [170.0, 0.75, 0.6], "ice": [150.0, 0.65, 0.55]}

var main: Node
var view: Node                  # scene_view.gd
var drawer: Object
var machine: RtaMachine
var cfg := ConfigFile.new()
var folder := ""
var have := false               # the materials were found and loaded
var on := false
var level := ""
var sent_key := ""
var reset_again := false
var reset_low := false
var reset_frames := 0
var albedo_array: Texture2DArray
var normal_array: Texture2DArray
var said := {}
var forced_off := OS.get_environment("RTA_ER_WORLD") == "off"     # (tests: a copy without it, whatever the look says)
# grass
var grass_mesh: ArrayMesh
var grass_material: ShaderMaterial
var grass_multimesh: RID
var grass_instance: RID
var grass_scenario: RID
var grass_eye := Vector3(1e9, 0, 0)
var grass_frame := 0
var grass_count := 0
var grass_on := false
var grass_epoch := -1
var blades_texture: Texture2D
# sky
var clouds_texture: Texture2D
# rebuild
var rebuild := {}               # the level's rebuild.json, with its loaded pieces (level, volumes, pieces: [{instance, ...}])
var rebuild_tried := {}         # levels that have none
var rebuild_sent := ""
var rebuild_orders := {}        # per volume: its place in the list last seen
var rebuild_pending := {}       # a level's pieces being read on worker threads: level, data, paths, started
# cost
var cost_sum := 0
var cost_worst := 0
var cost_frames := 0
var frame_no := 0


static func world_folder() -> String:
	if OS.has_environment("RTA_ER_WORLD_DIR"):
		return OS.get_environment("RTA_ER_WORLD_DIR")
	return ProjectSettings.globalize_path("res://").path_join("../../souls-ref/er-world").simplify_path()


static func found() -> bool:
	return FileAccess.file_exists(world_folder().path_join("materials/grass/albedo.png"))


# before any shader that names them is made (scene_view.add_globals)
static func add_globals() -> void:
	for name in ["rta_er", "rta_er_scale_a", "rta_er_scale_b", "rta_er_scale_c", "rta_er_keep_a", "rta_er_keep_b", "rta_er_keep_c", "rta_er_amount_a",
			"rta_er_amount_b", "rta_er_amount_c", "rta_er_reader", "rta_er_sky"]:
		RenderingServer.global_shader_parameter_add(name, RenderingServer.GLOBAL_VAR_TYPE_VEC4, Vector4(0, 1, 1, 0))
	RenderingServer.global_shader_parameter_add("rta_er_albedo", RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2DARRAY, RID())
	RenderingServer.global_shader_parameter_add("rta_er_normal", RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2DARRAY, RID())
	RenderingServer.global_shader_parameter_add("rta_er_clouds", RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2D, RID())


func _ready() -> void:
	drawer = main.drawer
	machine = main.machine
	cfg.load("res://er_world.cfg")
	folder = world_folder()
	if not found():
		print("rta_godot: er world: no materials in %s - the levels stay as the game draws them" % folder)
		return
	var t0 := Time.get_ticks_usec()
	var albedos: Array[Image] = []
	var normals: Array[Image] = []
	for c in CLASSES:
		albedos.append(_picture(folder.path_join("materials/%s/albedo.png" % c), Color(0.5, 0.5, 0.5)))
		normals.append(_picture(folder.path_join("materials/%s/normal.png" % c), Color(0.5, 0.5, 1.0)))
	albedo_array = Texture2DArray.new()
	albedo_array.create_from_images(albedos)
	normal_array = Texture2DArray.new()
	normal_array.create_from_images(normals)
	RenderingServer.global_shader_parameter_set("rta_er_albedo", albedo_array.get_rid())
	RenderingServer.global_shader_parameter_set("rta_er_normal", normal_array.get_rid())
	var blades := folder.path_join("grass/blades.png")
	if FileAccess.file_exists(blades):
		var img := Image.load_from_file(blades)
		if img != null:
			img.generate_mipmaps()
			blades_texture = ImageTexture.create_from_image(img)
	var clouds := folder.path_join("sky/clouds.png")
	if FileAccess.file_exists(clouds):
		var img := Image.load_from_file(clouds)
		if img != null:
			img.generate_mipmaps()
			clouds_texture = ImageTexture.create_from_image(img)
			RenderingServer.global_shader_parameter_set("rta_er_clouds", clouds_texture.get_rid())
	have = true
	print("rta_godot: er world: %d materials from %s in %.0f ms%s%s" % [CLASSES.size(), folder, (Time.get_ticks_usec() - t0) / 1000.0,
		", grass" if blades_texture != null else "", ", clouds" if clouds_texture != null else ""])


# a picture at TEXTURE_SIZE with its mip maps (a grey one where the file is missing)
func _picture(path: String, fill: Color) -> Image:
	var img: Image = null
	if FileAccess.file_exists(path):
		img = Image.load_from_file(path)
	if img == null:
		img = Image.create(TEXTURE_SIZE, TEXTURE_SIZE, false, Image.FORMAT_RGBA8)
		img.fill(fill)
	img.convert(Image.FORMAT_RGBA8)
	if img.get_width() != TEXTURE_SIZE or img.get_height() != TEXTURE_SIZE:
		img.resize(TEXTURE_SIZE, TEXTURE_SIZE, Image.INTERPOLATE_LANCZOS)
	img.generate_mipmaps()
	return img


func _num(section: String, key: String, fallback: float) -> float:
	# the level's own section over the general one
	var lv := "level." + level
	if cfg.has_section_key(lv, key):
		return float(cfg.get_value(lv, key))
	if cfg.has_section_key(section, key):
		return float(cfg.get_value(section, key))
	return fallback


func _look_num(key: String, section: String, cfg_key: String, fallback: float) -> float:
	# a look key given (command line, script) over the table
	if view.look.has(key) and view.look_given.has(key):
		return float(view.look[key])
	return _num(section, cfg_key, fallback)


# Before the drawer takes the frame: on or off, the table for this level
func before_frame() -> void:
	var started := Time.get_ticks_usec()
	frame_no += 1
	var name: String = machine.peek_string(0x41B721, 16)        # g_levelName (scene_view.gd G_LEVEL_NAME)
	# (er_world.cfg: a level's section may turn the layer off for that level - `layer = "off"`, with the reason beside it)
	on = have and not forced_off and String(view.look.get("er_world", "on")) == "on" and String(cfg.get_value("level." + name, "layer", "on")) != "off"
	if name != level:
		level = name
		drawer.call("world_reset")
		grass_eye = Vector3(1e9, 0, 0)
		reset_again = true
		reset_low = false
		reset_frames = 0
	elif reset_again and _level_running():
		# once more when the level has run a moment (g_simFrame): the last pictures of the screen before it (the character
		# choice's own little scene) are still drawn after the name changed, and grass grew on them, in the air
		reset_again = false
		drawer.call("world_reset")
		grass_eye = Vector3(1e9, 0, 0)
	var key := "%s|%s|%s" % [on, level, view.look.get("er_grass", 1.2)]
	if key != sent_key:
		sent_key = key
		drawer.call("set_world_layer", on, _table())
		if on and not said.has(level):
			said[level] = true
			print("rta_godot: er world: on for %s" % level)
	_rebuild_volumes()
	var strength := _look_num("er_world_strength", "world", "strength", 1.0) if on else 0.0
	RenderingServer.global_shader_parameter_set("rta_er", Vector4(strength, _num("world", "relief", 1.0), _num("world", "far", 2600.0), _num("world", "big", 0.35)))
	# per class, four to a vector: scale (units per repeat), keep (the game's own detail kept), amount (the material's)
	for part in 3:
		var sv := Vector4.ZERO
		var kv := Vector4.ZERO
		var mv := Vector4.ZERO
		for i in 4:
			var c := part * 4 + i
			if c >= CLASSES.size():
				break
			var d: Array = CLASS_DEFAULTS.get(CLASSES[c], [110.0, 0.6, 0.8])
			sv[i] = _num("scale", CLASSES[c], d[0])
			kv[i] = _num("keep", CLASSES[c], d[1])
			mv[i] = _num("amount", CLASSES[c], d[2])
		var suffix: String = ["a", "b", "c"][part]
		RenderingServer.global_shader_parameter_set("rta_er_scale_" + suffix, sv)
		RenderingServer.global_shader_parameter_set("rta_er_keep_" + suffix, kv)
		RenderingServer.global_shader_parameter_set("rta_er_amount_" + suffix, mv)
	RenderingServer.global_shader_parameter_set("rta_er_reader", Vector4(_num("reader", "grass_hue", 64.0), 0, 0, 0))
	_spend(started)


# the level has run a moment since its name changed: its g_simFrame started again and passed 30, or 120 pictures went by
func _level_running() -> bool:
	reset_frames += 1
	var sim := machine.peek_u32(0x44FDCC)
	if sim < 30:
		reset_low = true
	return (reset_low and sim >= 30) or reset_frames >= 120


# the table for the drawer: texture overrides, the level's class remaps, the reader's thresholds, the grass density
func _table() -> Dictionary:
	var t := {}
	if cfg.has_section("textures"):
		for k in cfg.get_section_keys("textures"):
			t[k] = String(cfg.get_value("textures", k))
	for section in ["remap", "level." + level]:
		if not cfg.has_section(section):
			continue
		for k in cfg.get_section_keys(section):
			if k.begins_with("remap.") or k.begins_with("remap_"):
				t["remap." + k.substr(6)] = String(cfg.get_value(section, k))
			elif section == "remap":
				t["remap." + k] = String(cfg.get_value(section, k))
	var reader := {"cobble_edge": 0.85, "wood_aniso": 1.45, "wood_edge": 0.25, "grass_hue": 64.0, "wood_coherence": 0.6, "metal_glint": 0.1,
		"metal_contrast": 0.85, "ice_edge": 0.6, "lava_hot": 0.25}
	for k in reader:
		t[k] = _num("reader", k, float(reader[k]))
	t["lava"] = _num("reader", "lava", 0.0)
	t["water"] = _num("reader", "water", 0.0)
	t["grass_ground"] = _num("grass", "ground", 0.3)
	t["grass_clear"] = _num("grass", "clear", 10.0)
	var density := _look_num("er_grass", "grass", "density", 1.2) if blades_texture != null else 0.0
	t["grass"] = density
	grass_on = density > 0.0
	return t


# Once per list, after the drawer has taken it: the grass near the eye; the sky's cloud layer
func frame(scenario: RID) -> void:
	var started := Time.get_ticks_usec()
	# (a level's own section names it sky_amount: an underwater or a cave level has no clouds)
	var sky_amount := _num("sky", "sky_amount", _num("sky", "amount", 1.0)) if on and clouds_texture != null else 0.0
	var tint := _num("sky", "tint", 0.75)
	RenderingServer.global_shader_parameter_set("rta_er_sky", Vector4(sky_amount, tint, _num("sky", "speed", 0.004), _num("sky", "scale", 1.0)))
	_grass(scenario)
	_rebuild_draw(scenario)
	_spend(started)


func _spend(started: int) -> void:
	var us := Time.get_ticks_usec() - started
	cost_sum += us
	cost_worst = maxi(cost_worst, us)
	cost_frames += 1


# ---- grass ------------------------------------------------------------------------------------------------------------
func _grass(scenario: RID) -> void:
	var show := on and grass_on and blades_texture != null and bool(view.in_force.get("ground", false))
	if not show:
		if grass_instance.is_valid():
			RenderingServer.instance_set_visible(grass_instance, false)
		return
	if scenario != grass_scenario or not grass_instance.is_valid():
		_grass_make(scenario)
	RenderingServer.instance_set_visible(grass_instance, true)
	var info: Dictionary = machine.get_view()
	var eye: Vector3 = info.get("eye", Vector3.ZERO)
	grass_frame += 1
	# the points again when the eye has moved a little, or now and then (new pieces of the level came into view)
	# (and when a piece of grass ground the game had left out is drawn again: RtaDrawer.get_grass_epoch)
	var epoch: int = drawer.call("get_grass_epoch")
	if eye.distance_to(grass_eye) < _num("grass", "move", 40.0) and grass_frame < 45 and epoch == grass_epoch:
		return
	grass_epoch = epoch
	grass_frame = 0
	grass_eye = eye
	var radius := _num("grass", "radius", 1400.0)
	var points: PackedFloat32Array = drawer.call("get_grass", eye, radius, int(_num("grass", "max", 60000.0)))
	var n := points.size() / 10
	grass_count = n
	var height := _num("grass", "height", 34.0)
	var buffer := PackedFloat32Array()
	buffer.resize(n * 20)          # transform (12), colour (4), custom (4)
	var o := 0
	for i in n:
		var b := i * 10
		var seed := points[b + 6]
		var yaw := seed * 917.0
		# no wider than its room: a tuft's cards reach 0.8 of its height out from its foot, and must not lean over a flagstone,
		# a path or a kerb that lies that near (rta_world.cpp: room)
		var s := minf(height * (0.7 + 0.6 * fmod(seed * 37.0, 1.0)), points[b + 9] * 1.25)
		var c := cos(yaw) * s
		var si := sin(yaw) * s
		# rows of the basis (x, y, z axes scaled) and the origin: the game's z is up
		buffer[o + 0] = c; buffer[o + 1] = -si; buffer[o + 2] = 0.0; buffer[o + 3] = points[b]
		buffer[o + 4] = si; buffer[o + 5] = c; buffer[o + 6] = 0.0; buffer[o + 7] = points[b + 1]
		buffer[o + 8] = 0.0; buffer[o + 9] = 0.0; buffer[o + 10] = s; buffer[o + 11] = points[b + 2] - 0.5
		buffer[o + 12] = points[b + 3]; buffer[o + 13] = points[b + 4]; buffer[o + 14] = points[b + 5]; buffer[o + 15] = 1.0
		buffer[o + 16] = seed; buffer[o + 17] = points[b + 7]; buffer[o + 18] = points[b + 8]; buffer[o + 19] = 0.0
		o += 20
	RenderingServer.multimesh_allocate_data(grass_multimesh, n, RenderingServer.MULTIMESH_TRANSFORM_3D, true, true)
	if n > 0:
		RenderingServer.multimesh_set_buffer(grass_multimesh, buffer)
	RenderingServer.multimesh_set_visible_instances(grass_multimesh, n)
	var aabb := AABB(eye - Vector3(radius, radius, 1000.0), Vector3(radius * 2.0, radius * 2.0, 2000.0))
	RenderingServer.multimesh_set_custom_aabb(grass_multimesh, aabb)


func _grass_make(scenario: RID) -> void:
	_grass_free()
	grass_scenario = scenario
	if grass_mesh == null:
		grass_mesh = _tuft()
		grass_material = ShaderMaterial.new()
		grass_material.shader = load("res://shaders/er_grass.gdshader")
		grass_material.set_shader_parameter("blades", blades_texture)
		grass_mesh.surface_set_material(0, grass_material)
	grass_multimesh = RenderingServer.multimesh_create()
	RenderingServer.multimesh_set_mesh(grass_multimesh, grass_mesh.get_rid())
	grass_instance = RenderingServer.instance_create()
	RenderingServer.instance_set_base(grass_instance, grass_multimesh)
	RenderingServer.instance_set_scenario(grass_instance, scenario)
	RenderingServer.instance_geometry_set_cast_shadows_setting(grass_instance, RenderingServer.SHADOW_CASTING_SETTING_OFF)
	RenderingServer.instance_set_pivot_data(grass_instance, 1.0e6, false)     # after the level's draws (the transparent pass)
	grass_eye = Vector3(1e9, 0, 0)


# a tuft: three cards crossed at 60 degrees, one unit high and 1.6 wide, standing on z = 0; UV.y 0 at the top
func _tuft() -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for k in 3:
		var a := PI * k / 3.0
		var d := Vector3(cos(a), sin(a), 0.0) * 0.8      # the card's picture is twice as wide as high: a little narrower here
		var u0 := 0.0
		var corners := [[-d, Vector2(u0, 1.0)], [d, Vector2(u0 + 1.0, 1.0)], [d + Vector3(0, 0, 1), Vector2(u0 + 1.0, 0.0)], [-d + Vector3(0, 0, 1), Vector2(u0, 0.0)]]
		for idx in [0, 1, 2, 0, 2, 3]:
			st.set_normal(Vector3(0, 0, 1))
			st.set_uv(corners[idx][1])
			st.add_vertex(corners[idx][0])
	return st.commit()


func _grass_free() -> void:
	for rid in [grass_instance, grass_multimesh]:
		if rid.is_valid():
			RenderingServer.free_rid(rid)
	grass_instance = RID()
	grass_multimesh = RID()


# ---- rebuild ----------------------------------------------------------------------------------------------------------
func _rebuild_wanted() -> bool:
	return on and String(view.look.get("er_rebuild", "on")) == "on"


# Before the drawer takes the frame: the volumes it leaves out (none when the rebuild is off, the level has none, or its
# pieces are still being read)
func _rebuild_volumes() -> void:
	# (no level between two levels: its name is empty, and an empty pending read's level is empty too - nothing to poll)
	if _rebuild_wanted() and level != "" and rebuild.get("level", "") != level and not rebuild_tried.has(level):
		if not rebuild_pending.has("paths") or rebuild_pending.get("level", "") != level:
			_rebuild_load(level)        # (when the level is entered: the pieces asked of worker threads)
		else:
			_rebuild_poll()
	var want: bool = _rebuild_wanted() and rebuild.get("level", "") == level and not rebuild.get("pieces", []).is_empty()
	var key := "%s|%s" % [want, level]
	if key == rebuild_sent:
		return
	rebuild_sent = key
	drawer.call("set_world_hide", rebuild.get("volumes", []) if want else [])
	rebuild_orders.clear()


func _rebuild_load(name: String) -> void:
	var path := folder.path_join("rebuild/%s/rebuild.json" % name)
	if not have or not FileAccess.file_exists(path):
		rebuild_tried[name] = true          # (none for this level: not looked for again)
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(data) != TYPE_DICTIONARY:
		rebuild_tried[name] = true
		return
	var base := path.get_base_dir()
	# the baked meshes and pictures, read by worker threads (ResourceLoader); a folder made before them: the old way, here
	var paths := {}
	for p in data.get("pieces", []):
		if not p.has("mesh_res"):
			paths.clear()
			break
		paths[base.path_join(String(p.mesh_res))] = true
		for s in p.get("surfaces", []):
			for key in ["albedo", "normal", "metal", "mask"]:
				if s.has(key + "_res"):
					paths[base.path_join(String(s[key + "_res"]))] = true
	rebuild_pending = {"level": name, "data": data, "base": base, "paths": paths.keys(), "started": Time.get_ticks_usec()}
	if paths.is_empty():
		_rebuild_finish({})
		return
	for f in paths:
		ResourceLoader.load_threaded_request(f, "", false, ResourceLoader.CACHE_MODE_REUSE)


func _rebuild_poll() -> void:
	if not rebuild_pending.has("paths"):
		return
	if not rebuild_pending.has("loaded"):
		for f in rebuild_pending.paths:
			if ResourceLoader.load_threaded_get_status(f) == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
				return
		var loaded := {}
		for f in rebuild_pending.paths:
			if ResourceLoader.load_threaded_get_status(f) == ResourceLoader.THREAD_LOAD_LOADED:
				loaded[f] = ResourceLoader.load_threaded_get(f)
			else:
				print("rta_godot: er world: rebuild: could not read %s" % f)
		rebuild_pending["loaded"] = loaded
		rebuild_pending["textures"] = {}
		rebuild_pending["made_usec"] = 0
	# the pictures put on the card two a frame (each a few milliseconds: all at once was a stall of 70-160 ms on a busy
	# machine)
	var t0 := Time.get_ticks_usec()
	var made := 0
	for f in rebuild_pending.loaded:
		var img = rebuild_pending.loaded[f]
		if img is Image and not rebuild_pending.textures.has(f):
			rebuild_pending.textures[f] = ImageTexture.create_from_image(img)
			made += 1
			if made >= 2:
				break
	rebuild_pending.made_usec += Time.get_ticks_usec() - t0
	if made > 0:
		return
	_rebuild_finish(rebuild_pending.loaded)


# The pieces made from what was read (on this thread: the materials, the pictures put on the card - a few milliseconds)
func _rebuild_finish(loaded: Dictionary) -> void:
	var t0 := Time.get_ticks_usec()
	var name: String = rebuild_pending.level
	var data: Dictionary = rebuild_pending.data
	var base: String = rebuild_pending.base
	var waited := (t0 - int(rebuild_pending.started)) / 1000.0
	var textures: Dictionary = rebuild_pending.get("textures", {})
	var spread := int(rebuild_pending.get("made_usec", 0)) / 1000.0
	rebuild_pending = {}
	_rebuild_free()
	var pieces := []
	var triangles := 0
	for p in data.get("pieces", []):
		var mesh: Mesh = null
		if p.has("mesh_res"):
			mesh = loaded.get(base.path_join(String(p.mesh_res)), null) as Mesh      # (one file per piece: its own)
		else:
			mesh = _rebuild_read_bin(base.path_join(String(p.mesh)), p.get("surfaces", []))
		if mesh == null or mesh.get_surface_count() == 0:
			continue
		var materials := []
		var surfaces: Array = p.get("surfaces", [])
		for si in mini(surfaces.size(), mesh.get_surface_count()):
			var s: Dictionary = surfaces[si]
			var m := ShaderMaterial.new()
			m.shader = load("res://shaders/er_ruin.gdshader")
			m.set_shader_parameter("has_albedo", s.has("albedo"))
			for key in ["albedo", "normal", "metal", "mask"]:
				if not s.has(key):
					continue
				var tex: Texture2D = null
				var res_path := base.path_join(String(s.get(key + "_res", "")))
				if s.has(key + "_res") and textures.has(res_path):
					tex = textures[res_path]
				else:
					var file := base.path_join(String(s[key]))
					if not textures.has(file):
						var img := Image.load_from_file(file)
						if img != null:
							img.generate_mipmaps()
							textures[file] = ImageTexture.create_from_image(img)
					tex = textures.get(file, null)
				if tex != null:
					m.set_shader_parameter(key + "_tex", tex)
					if key != "albedo":
						m.set_shader_parameter("has_" + key, true)
			var game_light := bool(s.get("game_light", false))
			m.set_shader_parameter("game_light", game_light)
			var lr: Array = p.get("light_ref", [0.5, 0.5, 0.5])
			m.set_shader_parameter("light_ref", Vector3(float(lr[0]), float(lr[1]), float(lr[2])))
			# the recipe's own material for this surface (er_world_fit.py "surfaces": a gold moulding, a marble)
			var params: Dictionary = s.get("params", {})
			for key in params:
				var v = params[key]
				if typeof(v) == TYPE_ARRAY and v.size() == 3:
					# (a Vector3: a Color would be made linear on its way in, and the shader works in stored values)
					v = Vector3(float(v[0]), float(v[1]), float(v[2]))
				elif typeof(v) == TYPE_ARRAY and v.size() == 2:
					v = Vector2(float(v[0]), float(v[1]))
				elif String(key).ends_with("_channel"):
					v = int(v)
				m.set_shader_parameter(String(key), v)
			# (without the game's colour per corner: drawn towards the colour of what it stands in for, from the piece's
			# own mean - a surface laid in another colour has that colour as its mean, as far as it is laid)
			var mean: Array = s.get("albedo_mean", [0.5, 0.5, 0.5])
			var rc = params.get("recolour", null)
			if typeof(rc) == TYPE_ARRAY and rc.size() == 3:
				var k := float(params.get("recolour_amount", 0.0))
				mean = [lerpf(float(mean[0]), float(rc[0]), k), lerpf(float(mean[1]), float(rc[1]), k), lerpf(float(mean[2]), float(rc[2]), k)]
			materials.append({"material": m, "mean": mean, "tint": float(s.get("tint", -1.0)), "game_light": game_light})
			mesh.surface_set_material(si, m)
		var aabb := mesh.get_aabb()
		for m in materials:
			(m.material as ShaderMaterial).set_shader_parameter("ground_z", aabb.position.z)   # (the grime near its foot)
		for si in mesh.get_surface_count():
			triangles += (mesh.surface_get_array_index_len(si) if mesh is ArrayMesh else 0) / 3
		pieces.append({"name": p.name, "mesh": mesh, "materials": materials, "volumes": p.get("volumes", [p.volume]).map(func(x): return int(x)),
			"watch": p.get("watch", []).map(func(x): return int(x)),
			"tint_amount": float(p.get("tint", 0.6)),
			"instance": RID(), "caster": RID(), "scenario": RID(), "tinted": 0.0, "aabb": aabb, "shown": false, "shown_rid": RID(), "at": -2.0})
	data["pieces"] = pieces
	rebuild = data
	print("rta_godot: er world: rebuild for %s, %d pieces (%d triangles) over %d volumes: read in %.0f ms on worker threads, pictures put on the card in %.1f ms (two a frame), made in %.1f ms" % [
		name, pieces.size(), triangles, data.get("volumes", []).size(), waited, spread, (Time.get_ticks_usec() - t0) / 1000.0])


# a piece written before the baked meshes (er_world_fit.py's .bin: positions, normals, uvs, indices), read here
func _rebuild_read_bin(file: String, surfaces: Array) -> ArrayMesh:
	var bytes := FileAccess.get_file_as_bytes(file)
	if bytes.size() < 8:
		return null
	var head := bytes.slice(0, 8).to_int32_array()
	var nv := head[0]
	var ni := head[1]
	var at := 8
	var pos := bytes.slice(at, at + nv * 12).to_float32_array(); at += nv * 12
	var nrm := bytes.slice(at, at + nv * 12).to_float32_array(); at += nv * 12
	var uvs := bytes.slice(at, at + nv * 8).to_float32_array(); at += nv * 8
	var idx := bytes.slice(at, at + ni * 4).to_int32_array()
	var mesh := ArrayMesh.new()
	for s in surfaces:
		var first := int(s.first)
		var count := int(s.count)
		if count <= 0:
			continue
		var remap := {}
		var sv := PackedVector3Array()
		var sn := PackedVector3Array()
		var su := PackedVector2Array()
		var si := PackedInt32Array()
		si.resize(count)
		for k in count:
			var o := idx[first + k]
			if not remap.has(o):
				remap[o] = sv.size()
				sv.append(Vector3(pos[o * 3], pos[o * 3 + 1], pos[o * 3 + 2]))
				sn.append(Vector3(nrm[o * 3], nrm[o * 3 + 1], nrm[o * 3 + 2]))
				su.append(Vector2(uvs[o * 2], uvs[o * 2 + 1]))
			si[k] = remap[o]
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = sv
		arrays[Mesh.ARRAY_NORMAL] = sn
		arrays[Mesh.ARRAY_TEX_UV] = su
		arrays[Mesh.ARRAY_INDEX] = si
		var st := SurfaceTool.new()
		st.create_from_arrays(arrays)
		st.generate_tangents()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, st.commit_to_arrays())
	return mesh


func _rebuild_draw(scenario: RID) -> void:
	var pieces: Array = rebuild.get("pieces", [])
	if pieces.is_empty():
		return
	var show: bool = _rebuild_wanted() and rebuild.get("level", "") == level and bool(view.in_force.get("ground", false))
	var hide_info: Array = drawer.call("get_world_hide") if show else []
	for p in pieces:
		if show and (p.scenario != scenario or not p.instance.is_valid()):
			_rebuild_place(p, scenario)
		# an overlay (laid over the game's own surface, which stays drawn) is drawn only on the frames the game drew what
		# it lies on: its watch-only volumes (the game culls far chunks; a piece drawn without them floats in the haze)
		var seen := show
		if show and not p.watch.is_empty():
			seen = false
			for vi in p.watch:
				if vi < hide_info.size() and (hide_info[vi] as Array).size() > 4 and bool(hide_info[vi][4]):
					seen = true
					break
		# (the server is told only of a change: an overlay is cut into a part per game packet, a hundred or more pieces)
		if p.instance.is_valid() and (seen != bool(p.shown) or p.instance != p.shown_rid):
			p.shown = seen
			p.shown_rid = p.instance
			RenderingServer.instance_set_visible(p.instance, seen)
			RenderingServer.instance_set_visible(p.caster, seen)
		if not seen or p.volumes.is_empty():
			if seen and p.at != 1.0e6:
				p.at = 1.0e6
				RenderingServer.instance_set_pivot_data(p.instance, 1.0e6, false)     # (an overlay: after the game's own surface)
			continue
		# each piece at the place of the first draw it stands in for (or where that was last); its colour, the mean of
		# what its volumes left out
		var at := -1.0
		var sum := Vector3.ZERO
		var weight := 0.0
		for vi in p.volumes:
			if vi >= hide_info.size():
				continue
			var info: Array = hide_info[vi]
			if float(info[0]) >= 0.0:
				rebuild_orders[vi] = float(info[0])
			var o := float(rebuild_orders.get(vi, -1.0))
			if o >= 0.0 and (at < 0.0 or o < at):
				at = o
			var c: Color = info[2]
			if c.a > 0.0:
				sum += Vector3(c.r, c.g, c.b) * float(info[3])
				weight += float(info[3])
		var pivot := at + 0.5 if at >= 0.0 else 1.0e6
		if pivot != float(p.at):
			p.at = pivot
			RenderingServer.instance_set_pivot_data(p.instance, pivot, false)
		if weight > 0.0:
			var colour := Color(sum.x / weight, sum.y / weight, sum.z / weight, 1.0)
			if weight != float(p.tinted):
				p.tinted = weight
				for m in p.materials:
					if m.game_light:
						continue            # (its colour is the game's own, per corner)
					var mean: Array = m.mean
					var own := Vector3(maxf(float(mean[0]), 0.05), maxf(float(mean[1]), 0.05), maxf(float(mean[2]), 0.05))
					var want := Vector3(colour.r, colour.g, colour.b)
					# the brightness the game's shape had (its texture with the game's vertex light: lit as the level's own
					# pieces are), the hue and saturation drawn towards it by tint_amount
					var lum_own := own.dot(Vector3(0.3, 0.59, 0.11))
					var lum_want := want.dot(Vector3(0.3, 0.59, 0.11))
					var amount: float = m.tint if m.tint >= 0.0 else p.tint_amount
					var hue := Vector3.ONE.lerp(want / maxf(lum_want, 0.02) / (own / lum_own), amount)
					var t := (hue * clampf(lum_want / lum_own, 0.25, 2.5)).clamp(Vector3(0.1, 0.1, 0.1), Vector3(3.0, 3.0, 3.0))
					(m.material as ShaderMaterial).set_shader_parameter("tint", t)


func _rebuild_place(p: Dictionary, scenario: RID) -> void:
	for key in ["instance", "caster"]:
		if p[key].is_valid():
			RenderingServer.free_rid(p[key])
	p.scenario = scenario
	p.at = -2.0
	p.instance = RenderingServer.instance_create2(p.mesh.get_rid(), scenario)
	RenderingServer.instance_geometry_set_cast_shadows_setting(p.instance, RenderingServer.SHADOW_CASTING_SETTING_OFF)
	# its shadow: a twin drawn only into the shadow maps, opaque (the transparent pass casts none)
	p.caster = RenderingServer.instance_create2(p.mesh.get_rid(), scenario)
	if rebuild_caster == null:
		rebuild_caster = StandardMaterial3D.new()
		rebuild_caster.cull_mode = BaseMaterial3D.CULL_DISABLED
	for i in p.mesh.get_surface_count():
		RenderingServer.instance_set_surface_override_material(p.caster, i, rebuild_caster.get_rid())
	RenderingServer.instance_geometry_set_cast_shadows_setting(p.caster, RenderingServer.SHADOW_CASTING_SETTING_SHADOWS_ONLY)


var rebuild_caster: StandardMaterial3D


func _rebuild_free() -> void:
	for p in rebuild.get("pieces", []):
		for key in ["instance", "caster"]:
			if p[key].is_valid():
				RenderingServer.free_rid(p[key])
			p[key] = RID()
	rebuild = {}


func release() -> void:
	_rebuild_free()
	_grass_free()
	RenderingServer.global_shader_parameter_set("rta_er_albedo", RID())
	RenderingServer.global_shader_parameter_set("rta_er_normal", RID())
	RenderingServer.global_shader_parameter_set("rta_er_clouds", RID())


# ---- commands -----------------------------------------------------------------------------------------------------------
func command(w: PackedStringArray) -> void:
	if w.size() < 3:
		return
	if w[2] == "info":
		var info: Dictionary = drawer.call("get_world_info", 2)
		var text := "rta_godot: er world: %s, level %s, %d textures known, per class %s; grass: %d pieces, %d points, %d drawn; %d wall cells" % [
			"on" if on else "off", level, int(info.get("textures", 0)), str(info.get("per_class", {})), int(info.get("grass_pieces", 0)),
			int(info.get("grass_points", 0)), grass_count, int(info.get("wall_cells", 0))]
		print(text)
		if w.size() >= 4:
			var f := FileAccess.open(w[3], FileAccess.WRITE)
			if f != null:
				var seen: Array = info.get("seen", [])
				var rows := []
				for d in seen:
					var m: Color = d.mean
					rows.append({"id": d.id, "name": d.name, "class": d["class"], "class_b": d.class_b, "guess": d.guess, "table": d.table,
						"mean": [snappedf(m.r, 0.001), snappedf(m.g, 0.001), snappedf(m.b, 0.001)], "frac": Array(d.frac), "edge": d.edge,
						"aniso": d.aniso, "opaque": d.opaque, "draws": d.draws, "coherence": d.coherence, "sat": d.sat, "contrast": d.contrast,
						"glint": d.glint, "cool": d.cool, "tint": [snappedf(d.tint.r, 0.001), snappedf(d.tint.g, 0.001), snappedf(d.tint.b, 0.001)],
						"lit_grey": d.lit_grey, "hot": snappedf(d.hot, 0.001)})
				f.store_string(JSON.stringify({"level": level, "on": on, "per_class": info.get("per_class", {}), "textures": rows}, " "))
				f.close()
	elif w[2] == "cost":
		print("rta_godot: er world cost: %.0f us mean, %d us worst over %d frames" % [float(cost_sum) / maxf(cost_frames, 1), cost_worst, cost_frames])
		cost_sum = 0
		cost_worst = 0
		cost_frames = 0
	elif w[2] == "rebuild":
		var hide_info: Array = drawer.call("get_world_hide")
		var parts := []
		for vi in hide_info.size():
			var vol: Array = rebuild.get("volumes", [])[vi] if vi < rebuild.get("volumes", []).size() else []
			if vol.size() > 8 and (int(vol[8]) & 4) != 0:
				parts.append("volume %d (watch): seen in %d frames, %s this frame" % [vi, int(hide_info[vi][1]), "drawn" if bool(hide_info[vi][4]) else "not drawn"])
			else:
				parts.append("volume %d: %d draws left out, place %.0f, colour %s" % [vi, int(hide_info[vi][1]), float(hide_info[vi][0]), str(hide_info[vi][2])])
		print("rta_godot: er world rebuild: %s, %d pieces for %s; %s" % ["on" if _rebuild_wanted() else "off", rebuild.get("pieces", []).size(),
			rebuild.get("level", "-"), "; ".join(parts)])
	elif w[2] == "dump" and w.size() >= 4:
		drawer.call("world_dump", w[3])
	elif w[2] == "grass":
		if w.size() >= 4:
			# (test aid) every point within 6000 units of the eye: x y z r g b a line
			var pts: PackedFloat32Array = drawer.call("get_grass", machine.get_view().get("eye", Vector3.ZERO), 6000.0, 200000)
			var f := FileAccess.open(w[3], FileAccess.WRITE)
			if f != null:
				for i in pts.size() / 10:
					var k := i * 10
					f.store_line("%.1f %.1f %.1f %.3f %.3f %.3f %.1f" % [pts[k], pts[k + 1], pts[k + 2], pts[k + 3], pts[k + 4], pts[k + 5], pts[k + 9]])
				f.close()
		var info: Dictionary = drawer.call("get_world_info", 0)
		print("rta_godot: er world grass: %d pieces scanned, %d points, %d drawn near the eye" % [int(info.get("grass_pieces", 0)), int(info.get("grass_points", 0)), grass_count])
