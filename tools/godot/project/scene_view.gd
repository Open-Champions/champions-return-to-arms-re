extends Node
# scene_view.gd - the look of scene mode (--mode scene): what Godot adds once the game's scene is in world space.
#
# RtaDrawer puts the 3-D scene into a Godot scenario as meshes in the game's world coordinates (x and y on the
# ground, z up; a character is 60 to 72 units tall) under a camera that follows the game's.  This script owns what
# is Godot's own in that world, each piece with a switch ("the look"):
#
#   sky       a sky for every level.  The game clears the picture to one colour per level and, in 19 of 111 levels,
#             draws a painted dome that ends 18 degrees above the horizon (docs/issues/native-first-person-world.md).
#             Here a sphere round the camera is drawn first (shaders/sky.gdshader): where the level has a dome it
#             continues the dome's own upper edge, colour for colour, to the zenith (the game's dome is still drawn,
#             over it: there is no seam); where it has none, a horizon, a zenith and a glow round the sun are made
#             from the level's clear colour - a light colour gives an open sky, black stays dark above
#   fog       haze by distance and height (shaders/atmosphere.gdshaderinc), complete where the level's cells end, in
#             the colour of the sky at the horizon
#   sun       a directional light with a soft shadow map: where it does not reach, the game's colours are darkened and
#             take the sky's tint; where it does they are the game's own.  In a dark level it is a dim light from
#             straight above (a soft shadow under everything) instead
#   lights    Godot point lights at the game's own lights - the light nodes of its light grid (RtaMachine.get_lights:
#             the level's torches and braziers, LightEffect objects, spell effects), in their colour made a little
#             warmer, their range the game's radius (whose flicker the game drives), with a slight flicker of Godot's
#             own; the nearest `light_shadows` (2) throw shadows.  light_energy, light_max (8)
#   lamp      a warm point light carried by the first player (auto: in dark levels, and only where none of the game's
#             lights reaches)
#   bloom     Godot's glow on what is bright (the game's own glows, fires, the sky round the sun)
#   grade     a little contrast and saturation
#   foliage   the level's cut-out cards (the crowns of trees, hung at head height) thin out within 64 units of the eye
#   fill      the ceilings and skirts the library generates for a level (rtag_fill_get): drawn with a swatch of the level's own
#             wall texture, darkened, a crease where they meet the wall, lit by the point lights, hazed (RtaDrawer, rta_fill.cpp;
#             shaders/fill.gdshader).  fill_light (0..1, default 0.42), fill_scale (swatch repeats per 64 units)
#   aa        multisampling of the 3-D surface (0, 2, 4, 8)
#   adaptive_aa on (default in Remastered only) | off: preserve requested AA/scale while GPU work fits 60 Hz;
#             hold expensive tween redraws, then 4x -> 2x -> native pixels without AA -> small scale steps.
#             Restores quality with hysteresis; frozen during loading, cutscenes and active fades. Classic bypasses it.
#   batch     on (default) | off: the level's draws gathered into batches, a two-pass chunk drawn as one (rta_scene.cpp,
#             Scene::batch_on; RTA_BATCH=0 off).  prepass on (default) | off: the solid batches' depth drawn first
#   models    cleaner models (on by default, in every view): the game's solid models are drawn with a form light per pixel
#             by the game's own normals (model_form 0..1), a rim light in the sky's colour (model_rim 0..1), a texture
#             sampled one mip step finer (model_sharp: footprint scale, 1 = as the level), and their skinned packets
#             (characters, creatures) curved: every triangle made model_smooth x model_smooth PN triangles (1 = as the game
#             has them; an edge whose normals part by more than model_crease, a cosine, stays hard; only within model_near units
#             of the eye: RtaDrawer, rta_scene.cpp)
#   backdrop  a ground for a level that shows none (off | on | auto: auto = in a view along the ground when the frame has
#             had none of the level's own draws for half a second - the arenas some levels are, entered alone, put the
#             character in the clear colour): flagstones at the character's feet in a colour from the level's sky
#             (shaders/backdrop.gdshader), fading into the haze
#   contact   contact shadows (0..1, 0 = none): a soft dark patch on the level under every standing figure, from the
#             figures' feet the drawer finds in the frame (get_sky_info().contacts)
#   er_models off | on | self: the players drawn as other figures posed by the game's own skeletons (er_layer.gd):
#             on = the owner's own converted Elden Ring models, when their local folder is there (nothing changes
#             otherwise); self = the local player's own bind-pose mesh re-skinned in Godot (the skeleton stream's check)
#   er_set    auto (the default: each player's outfit by its character class) or one of the local outfits for everyone
#             (a folder of er-models: default, barbarian, cleric, ...)
#   er_who    all (the default: every player of the game, this machine's and the others') | me (the local player only)
#   er_springs on | off: capes, skirts and hair swing (er_layer.gd's springs; presentation only)
#   er_metal  0..1 (default 0.5): how much of the outfits' metal maps is taken (no reflections here for a metal to show)
#   er_creatures off | on: the game's monsters drawn as local models of a similar build, posed by their own skeletons
#             (er_layer.gd, er_creatures.cfg: which class is which model); a class with no model keeps its own figure
#   er_style  fit (the default: the player's own figure dressed in the outfit's pieces, er_fit.gd) | replace (rounds 1-3)
#   er_outfits per class "class:auto|original|<outfit>;..." (the portal's Settings; er_fit.cfg [auto] for auto)
#   er_world  on (default) | off: the Elden Ring world layer (er_world.gd): the owner's own Elden Ring materials on the
#             level's pieces by what their textures read as, grass on the grass, clouds in the sky - when their local
#             folder is there (nothing changes otherwise); the Classic look sets it off.  er_world_strength 0..1,
#             er_grass (points per 1000 square units; 0 = no grass), er_rebuild on | off (Elden Ring ruin pieces fitted over
#             some of the level's shapes, where the folder has them for the level: er_world.gd)
#   remaster_models on (default) | off: the game's own figures drawn as smooth meshes baked on this machine from their own
#             bind-pose meshes, posed by the game's own skin matrices, with maps derived from their (art pack) textures
#             (model_remaster.gd, RtaRemaster; model_remaster.cfg per model); the Classic look sets it off
#
# Each of sky, fog, sun, lamp, bloom, grade, foliage, fill is  off | on | auto.  auto - the default - means: in the views that look
# along the ground (chase, shoulder, first person: tools/recomp/app/fpview.h), not in the game's own overhead view
# and not while the game's own camera has the frame (a cutscene, a dialogue, a menu): there the picture is the
# game's, as it always was.
#
#   --look sky=on,fog=off,aa=2,...          on the command line (main.gd)
#   app look KEY VALUE                      from a script, at a chosen tick; "app look info" prints what is in force
#   main.apply_settings({"look": "..."})    from the portal
# Further keys: shade (0..1: what a shadow leaves of a colour; default by level), fog_start, fog_end (units),
# fog_amount (0..1), sun_az, sun_el (degrees; default: by level), bloom_strength, sky_sun (0..1: the glow round the sun),
# shadow_splits (1, 2 or 4 shadow maps for the sun: every one is a pass over all that casts), shadow_far (units).
# The older switches still work: --shadow (sun=on), --light (lamp=on), app scene shadow|light on|off,
# app camera pull F | orbit DEG | raise DEG | game  (a camera that is not the game's: it shows what the game culled).
#
# Per level, everything is taken from the game while it runs: the clear colour and the dome from the frame's own
# draws (RtaDrawer.get_sky_info), the level's name, light level and far plane from the machine's memory.  Nothing
# of a level is written down here.

const G_PLAYERS := 0x4D8AF0             # symbols: g_players; +0x43d8 the first player's object, +0x10 its position
const G_LEVEL_NAME := 0x41B721          # g_levelName
const G_WORLD_LIGHT := 0x5D347C         # g_worldLightLevel: 0x80, or 0x40 / 0x20 in dark levels
const G_FAR_CLIP := 0x7D8A04            # g_farClip
const VIEW_CHASE := 2
const SUN_CLEAR := 0.004                # how clearly a level's textures must say where its light comes from

const GLOBALS := {
	"rta_sky_zenith": Vector4(0, 0, 0, 0), "rta_sky_ground": Vector4(0, 0, 0, 0), "rta_sky_sun": Vector4(0, 0, 1, 0),
	"rta_sky_sun_colour": Vector4(1, 1, 1, 0), "rta_lock": Vector4(0, 0, 0, 0), "rta_lock_player": Vector4(0, 0, 0, 0), "rta_fog_range": Vector4(400, 1350, 0, 200), "rta_fog_amount": Vector4(0, 0.5, 1, 0),
	"rta_fog_colour": Vector4(0, 0, 0, 0), "rta_light_ambient": Vector4(1, 1, 1, 0),
	"rta_model": Vector4(0, 0, 1, 0), "rta_model_rim": Vector4(0, 0, 0, 0),
	"rta_tween": Vector4(0, 0, 0, 0),       # x: game frames past the last one (a picture between game frames: RtaDrawer.redraw)
}

var look := {
	"sky": "auto", "fog": "auto", "sun": "auto", "lamp": "auto", "bloom": "auto", "grade": "auto", "foliage": "auto", "fill": "auto", "lights": "auto", "aa": "4", "scale3d": 1.0, "adaptive_aa": "on", "batch": "on", "prepass": "on",
	"shade": -1.0, "fog_start": 380.0, "fog_end": 1350.0, "fog_amount": 1.0, "sun_az": -1000.0, "sun_el": -1000.0,
	"bloom_strength": 1.0, "sky_sun": 1.0, "shadow_splits": 4.0, "shadow_far": 1100.0,
	"fill_light": 0.36, "fill_scale": 1.0, "light_energy": 1.0, "light_shadows": 2.0, "light_max": 8.0,
	"sun_gain": 1.0, "saturation": 1.10, "contrast": 1.06, "brightness": 1.0, "preset": "on", "balance": "0.6",
	"backdrop": "auto", "models": "on", "model_smooth": 2.0, "model_crease": 0.35, "model_near": 520.0, "model_rim": 0.35, "model_form": 0.7, "model_sharp": 0.6, "contact": 0.55,
	"er_models": "off", "er_set": "auto", "er_who": "all", "er_springs": "on", "er_metal": 0.5, "er_creatures": "off", "er_style": "fit", "er_outfits": "",
	"remaster_models": "on",
	"er_world": "on", "er_world_strength": 1.0, "er_grass": 1.2, "er_rebuild": "on",
}
# Per level presets (tools/godot/presets.py): the look keys above, by level, picked from what the level's own colours
# are (its clear colour, its dome, its light level, the game's light nodes, the picture the game's own camera gives) by
# a walk through every level, plus hand-tuning.  Files, each over the one before (ConfigFile: a [section] per level name,
# [*] for every level):
#   res://presets/levels.cfg     picked by presets.py `make` (tracked: our own look numbers, no colour of the game)
#   res://presets/tuning.cfg     the hand-tuning (tracked: my own numbers, no colour of the game)
#   user://look_presets.cfg      the player's own;  --look-presets FILE (main.gd) or $RTA_LOOK_PRESETS: one more on top
# A key given on the command line or by "app look KEY VALUE" stays as given; "preset=off" leaves every preset out.
var presets := {}                       # level -> {key: value}
var preset_files: PackedStringArray = PackedStringArray()
var look_given := {}                    # keys the command line or a script set: presets do not touch them
var look_defaults := {}
var preset_applied := ""
var fill_sent := {}
var card: Node                          # card.gd: the character card (the portal's Portrait.texture)
var lamp_before := Vector3.ZERO
var lamp_now := Vector3.ZERO
var lamp_before_ok := false
var scale_set := -1.0
var frames_taken := 0                   # lists taken (er_layer.gd: which figures were drawn in the last one)
var er: Node                            # er_layer.gd: figures posed by the game's skeletons (look.er_models)
var remaster: Node                      # model_remaster.gd: the game's own figures remastered (look.remaster_models)
var material_warmup := preload("res://material_warmup.gd").new()
var world_layer: Node                   # er_world.gd: the Elden Ring world layer (look.er_world)
var torches: Array = []                 # [{light, instance, address, shadow}] Godot's lights at the game's
var torch_clock := 0.0
var lamp_share := 0.0                   # the carried lamp, eased: 1 where none of the game's lights reaches
var game_lights := 0                    # this frame: how many of the game's lights are near
var shadow_set := Vector2(-1, -1)
var sun_found := Vector2(217.0, 48.0)   # azimuth and elevation of the level's light, degrees: read out of its textures
var sun_fixed := false
var sun_last := Vector2(217.0, 48.0)    # the last direction a level's textures gave clearly (the levels of this game are
                                        # painted alike: the first level says -33 degrees clearly, the forest the same faintly)
# How dark a shadow is: the part of a colour that is left where the sun does not reach.  The Compatibility renderer
# draws a light that has a shadow map in a pass of its own and ADDS that pass to the picture as stored values, after
# the conversion from linear light; a sun of energy (1 - shade)^2.2 therefore adds (1 - shade) of the stored colour
# (measured: test/scene/cal).  What arrives without the sun is put in by the shader itself (rta_light_ambient).
var shade := 0.64
var forward_plus := true                # Forward+ / Mobile add lights in linear light; the Compatibility renderer differs (_lights)

var main: Node
var drawer: Object
var machine: RtaMachine
var scenario: RID
var environment: RID
var viewport: RID
var gpu_quality := preload("res://gpu_quality.gd").new()
var gpu_requested_samples := -1
var gpu_sample_frame := -1
var gpu_sample_usec := 0
var gpu_level := ""
var gpu_measure_viewport: RID
var gpu_hud_fade := -1
var sun: RID
var sun_instance: RID
var lamp: RID
var lamp_instance: RID
var sky_mesh: SphereMesh
var sky_material: ShaderMaterial
var sky_instance: RID
var ring_texture: ImageTexture
var ring_image: Image
var pull_back := 1.0
var orbit := 0.0
var raise := 0.0
# the level that is running, as far as it is known
var level := ""
var sky_version := -1
var sky_clear := Color(-1, -1, -1)
var level_dark := false
var level_dome := false
var level_light := 128
var horizon := Color.BLACK
var zenith := Color.BLACK
var ground_amount := 0.0                # 0: the game's own view .. 1: a view along the ground (eased)
var in_force := {}
var said := {}
var aa_set := -1
var contact_image: Image                # 16 x 1, RGBA float: the frame's standing figures (x, y, z of the feet, radius)
var contact_texture: ImageTexture
var contacts_now := 0
var model_sent := {}
var backdrop_mesh: PlaneMesh
var backdrop_material: ShaderMaterial
var backdrop_instance: RID
var backdrop_bare := 0                  # frames in a row without the level's own draws
var backdrop_z := 0.0
var backdrop_on := false
var classic_look := {}                 # portal/edition.gd CLASSIC_LOOK as key -> value (_classic_look_in_force)


static var globals_added := false
const ErWorld := preload("res://er_world.gd")

static func add_globals() -> void:
	# before any shader that names them is made (main.gd, before the drawer)
	if globals_added:
		return
	globals_added = true
	for name in GLOBALS:
		RenderingServer.global_shader_parameter_add(name, RenderingServer.GLOBAL_VAR_TYPE_VEC4, GLOBALS[name])
	RenderingServer.global_shader_parameter_add("rta_sky_ring", RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2D, RID())
	RenderingServer.global_shader_parameter_add("rta_contacts", RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2D, RID())
	ErWorld.add_globals()


func _ready() -> void:
	forward_plus = RenderingServer.get_current_rendering_method() != "gl_compatibility"
	drawer = main.drawer
	machine = main.machine
	if main.opt.shadow:
		look.sun = "on"
	if main.opt.light:
		look.lamp = "on"
	pull_back = main.opt.pull_back
	orbit = main.opt.orbit
	if int(main.opt.samples) > 0:
		look.aa = str(main.opt.samples)
	if forward_plus:
		look.saturation = 1.22             # Forward+ greys the lit scene a little against the Compatibility renderer (fifth round)
	look_defaults = look.duplicate()
	set_look(String(main.opt.look))
	_load_presets()
	ring_image = Image.create(256, 2, false, Image.FORMAT_RGB8)
	ring_texture = ImageTexture.create_from_image(ring_image)
	RenderingServer.global_shader_parameter_set("rta_sky_ring", ring_texture.get_rid())
	contact_image = Image.create(16, 1, false, Image.FORMAT_RGBAF)
	contact_texture = ImageTexture.create_from_image(contact_image)
	RenderingServer.global_shader_parameter_set("rta_contacts", contact_texture.get_rid())
	RenderingServer.directional_shadow_atlas_set_size(4096, true)
	RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_MEDIUM)
	sky_mesh = SphereMesh.new()
	sky_mesh.radius = 1.0
	sky_mesh.height = 2.0
	sky_mesh.radial_segments = 48
	sky_mesh.rings = 24
	sky_material = ShaderMaterial.new()
	sky_material.shader = load("res://shaders/sky.gdshader")
	drawer.call("set_fill_shader", load("res://shaders/fill.gdshader"), load("res://shaders/fill_skirt.gdshader"))
	card = Node.new()
	card.set_script(load("res://card.gd"))
	card.set("main", main)
	card.set("drawer", drawer)
	add_child(card)
	er = Node.new()
	er.set_script(load("res://er_layer.gd"))
	er.set("main", main)
	er.set("view", self)
	add_child(er)
	remaster = Node.new()
	remaster.set_script(load("res://model_remaster.gd"))
	remaster.set("main", main)
	remaster.set("view", self)
	remaster.set("er", er)
	add_child(remaster)
	_world_layer_if_wanted()
	_camera_options()


# The Elden Ring world layer (er_world.gd) is made - and its materials read, about half a second - only when look.er_world
# is on: never in Classic (the portal's Classic look sets it off), and at the first frame after a switch to Remastered
# (clear_look puts the key back on).  Once made it stays and follows the key itself (er_world.gd before_frame).
func _world_layer_if_wanted() -> void:
	if world_layer != null or String(look.get("er_world", "on")) != "on":
		return
	world_layer = Node.new()
	world_layer.set_script(ErWorld)
	world_layer.set("main", main)
	world_layer.set("view", self)
	add_child(world_layer)


# every key the portal's Classic look sets is at that value now (portal/edition.gd CLASSIC_LOOK)
func _classic_look_in_force() -> bool:
	if classic_look.is_empty():
		for part in String(load("res://portal/edition.gd").CLASSIC_LOOK).split(",", false):
			var kv := part.split("=")
			if kv.size() == 2:
				classic_look[kv[0].strip_edges()] = kv[1].strip_edges()
	for key in classic_look:
		var now = look.get(key, null)
		if now == null:
			return false
		if now is float or now is int:
			if not is_equal_approx(float(now), String(classic_look[key]).to_float()):
				return false
		elif String(now) != String(classic_look[key]):
			return false
	return true


func set_look(text: String) -> void:
	for part in text.split(",", false):
		var kv := part.split("=")
		if kv.size() == 2:
			_put(kv[0].strip_edges(), kv[1].strip_edges())


# keys given before (the portal's Classic look) back to their defaults and to the level's presets
func clear_look(keys: PackedStringArray) -> void:
	for key in keys:
		if look_defaults.has(key):
			look[key] = look_defaults[key]
			look_given.erase(key)
	if level != "":
		_apply_preset(level)            # the level's presets again, now that these keys are free


func _put(key: String, value: String, given := true) -> void:
	if not look.has(key):
		push_warning("look: no such key " + key)
		return
	if look[key] is float:
		look[key] = value.to_float()
	else:
		look[key] = value
	if given:
		look_given[key] = true


func _load_presets() -> void:
	var files := PackedStringArray(["res://presets/levels.cfg", "res://presets/tuning.cfg", "user://look_presets.cfg"])
	var extra := String(main.opt.get("look_presets", ""))
	if extra == "" and OS.has_environment("RTA_LOOK_PRESETS"):
		extra = OS.get_environment("RTA_LOOK_PRESETS")
	if extra != "":
		files.append(extra)
	for path in files:
		var config := ConfigFile.new()
		if not FileAccess.file_exists(path) or config.load(path) != OK:
			continue
		preset_files.append(path)
		for section in config.get_sections():
			var d: Dictionary = presets.get(section, {})
			for key in config.get_section_keys(section):
				if look.has(key):
					d[key] = str(config.get_value(section, key))
			presets[section] = d
	print("rta_godot: look presets: %d levels from %s" % [presets.size() - (1 if presets.has("*") else 0), ", ".join(preset_files) if not preset_files.is_empty() else "no file"])


func _apply_preset(name: String) -> void:
	# the defaults, then [*], then the level's own; never over what was given
	var use := String(look.preset) != "off"
	var d := {}
	if use:
		d = (presets.get("*", {}) as Dictionary).duplicate()
		d.merge(presets.get(name, {}), true)
	for key in look_defaults:
		if look_given.has(key) or key == "preset":
			continue
		if d.has(key):
			_put(key, String(d[key]), false)
		else:
			look[key] = look_defaults[key]
	preset_applied = name if use and presets.has(name) else ""
	if use:
		print("rta_godot: level %s: look preset %s" % [name, str(presets.get(name, {})) if presets.has(name) else "none (defaults%s)" % (" and [*]" if presets.has("*") else "")])


func _free_torches() -> void:
	for t in torches:
		RenderingServer.free_rid(t.instance)
		RenderingServer.free_rid(t.light)
	torches.clear()


func release() -> void:
	material_warmup.release()
	if er != null:
		er.call("release")
	if remaster != null:
		remaster.call("release")
	if world_layer != null:
		world_layer.call("release")
	_free_torches()
	for rid in [sun_instance, lamp_instance, sky_instance, sun, lamp, backdrop_instance]:
		if rid.is_valid():
			RenderingServer.free_rid(rid)
	backdrop_instance = RID()
	sun_instance = RID()
	lamp_instance = RID()
	sky_instance = RID()
	sun = RID()
	lamp = RID()
	RenderingServer.global_shader_parameter_set("rta_sky_ring", RID())
	RenderingServer.global_shader_parameter_set("rta_contacts", RID())


func takes_input() -> bool:
	return false


func _wants(key: String, ground: bool) -> bool:
	var v := String(look[key])
	return v == "on" or (v == "auto" and ground)


func _camera_options() -> void:
	drawer.call("set_scene_option", "pull_back", pull_back)
	drawer.call("set_scene_option", "orbit", orbit)
	drawer.call("set_scene_option", "raise", raise)


# Before the drawer takes the frame: what this frame is drawn with.
func before_frame() -> void:
	if card != null:
		card.call("before_frame")
	if er != null:
		er.call("before_frame", String(look.er_models))
	if remaster != null:
		remaster.call("before_frame")
	_world_layer_if_wanted()
	if world_layer != null:
		world_layer.call("before_frame")
	var view: Dictionary = machine.get_view()
	var ground := bool(view.get("valid", false)) and bool(view.get("active", false)) and not bool(view.get("fallback", false)) \
			and int(view.get("shown", 0)) >= VIEW_CHASE
	ground_amount = move_toward(ground_amount, 1.0 if ground else 0.0, 0.07)
	in_force = {"ground": ground}
	for key in ["sky", "fog", "sun", "lamp", "bloom", "grade", "fill", "lights"]:
		in_force[key] = _wants(key, ground)
	# the lamp, by itself, only where it is dark
	if String(look.lamp) == "auto":
		in_force.lamp = ground and level_dark
	drawer.call("set_scene_option", "sky", 1.0 if in_force.sky else 0.0)
	drawer.call("set_scene_option", "near_fade", 1.0 if _wants("foliage", ground) else 0.0)
	# the level's draws gathered into batches, a two-pass chunk drawn as one (rta_scene.cpp, Scene::batch_on); off: each by itself
	drawer.call("set_scene_option", "batch", 0.0 if String(look.batch) == "off" or OS.get_environment("RTA_BATCH") == "0" else 1.0)
	drawer.call("set_scene_option", "prepass", 0.0 if String(look.prepass) == "off" or OS.get_environment("RTA_PREPASS") == "0" else 1.0)
	drawer.call("set_scene_option", "fill", 1.0 if in_force.fill else 0.0)
	for key in ["fill_light", "fill_scale"]:
		if fill_sent.get(key, -1.0) != float(look[key]):
			fill_sent[key] = float(look[key])
			drawer.call("set_scene_option", key, float(look[key]))
	# cleaner models: the drawer's part (which draws, how many curved triangles); the shader's part in _models()
	var models_on := _wants("models", true)
	in_force["models"] = models_on
	var model_options := {"model_look": 1.0 if models_on else 0.0, "model_smooth": float(look.model_smooth) if models_on else 1.0,
		"model_crease": float(look.model_crease), "model_near": float(look.model_near), "contacts": 1.0 if models_on and float(look.contact) > 0.0 else 0.0}
	for key in model_options:
		if model_sent.get(key, -1.0) != model_options[key]:
			model_sent[key] = model_options[key]
			drawer.call("set_scene_option", key, model_options[key])
	var feet_now: Vector3 = view.get("player", Vector3.ZERO)
	RenderingServer.global_shader_parameter_set("rta_lock_player", Vector4(feet_now.x, feet_now.y, feet_now.z, 0.0))
	drawer.call("set_scene_option", "feet_x", feet_now.x)
	drawer.call("set_scene_option", "feet_y", feet_now.y)
	drawer.call("set_scene_option", "feet_z", feet_now.z)
	drawer.call("set_scene_option", "lit", 1.0 if (in_force.sun or in_force.lamp or in_force.lights) else 0.0)
	# Classic: the world blended in stored values as the GS blends (rta_drawer.h stored_world: an additive light shaft over
	# dark water as bright as the native program's), while every key the portal's Classic look turns off is off
	drawer.call("set_scene_option", "stored_world", 1.0 if _classic_look_in_force() else 0.0)
	drawer.call("set_scene_option", "shadows", 1.0 if (in_force.sun or (in_force.lights and float(look.light_shadows) > 0.0)) else 0.0)


# Once per list, after the drawer has taken it.
func frame() -> void:
	frames_taken += 1
	var world: RID = drawer.call("get_world_scenario")
	if not world.is_valid():
		return
	if world != scenario:
		_make(world)
	material_warmup.tick(scenario, look)
	_level()
	var info: Dictionary = drawer.call("get_sky_info")
	_sun_from_level(info)
	_palette(info)
	var sky_on: bool = in_force.get("sky", false) and bool(info.get("active", false))
	RenderingServer.instance_set_visible(sky_instance, sky_on)
	_haze()
	_torches()
	_lights()
	_models(info)
	_backdrop(info)
	_post()
	if card != null:
		card.call("frame", 1.0 / 60.0)
	if remaster != null:
		remaster.call("frame", scenario)
	if er != null:
		er.call("frame", scenario)
	if world_layer != null:
		world_layer.call("frame", scenario)


# A picture between two game frames (main.gd, the display rate above 60): the drawer draws the last frame again with
# its camera and kept models carried T game frames on; here the Elden Ring figures and the carried lamp.
func tween(t: float) -> void:
	if er != null:
		er.call("tween", t)
	if remaster != null:
		remaster.call("tween", t)
	if lamp_instance.is_valid() and lamp_before_ok:
		RenderingServer.instance_set_transform(lamp_instance, Transform3D(Basis(), lamp_before.lerp(lamp_now, 1.0 + t)))


func _make(to: RID) -> void:
	_free_torches()
	for rid in [sun_instance, lamp_instance, sky_instance, sun, lamp, backdrop_instance]:
		if rid.is_valid():
			RenderingServer.free_rid(rid)
	backdrop_instance = RID()
	backdrop_on = false
	scenario = to
	environment = drawer.call("get_world_environment")
	viewport = drawer.call("get_world_viewport")
	aa_set = -1
	scale_set = -1.0
	shadow_set = Vector2(-1, -1)
	sun = RenderingServer.directional_light_create()
	RenderingServer.light_set_shadow(sun, true)
	RenderingServer.light_directional_set_shadow_mode(sun, RenderingServer.LIGHT_DIRECTIONAL_SHADOW_PARALLEL_4_SPLITS)
	RenderingServer.light_directional_set_blend_splits(sun, true)
	RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_SHADOW_MAX_DISTANCE, 1100.0)
	RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_SHADOW_BIAS, 0.6)
	RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_SHADOW_NORMAL_BIAS, 3.0)
	RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_SHADOW_BLUR, 2.2)
	RenderingServer.light_set_cull_mask(sun, 1)         # not the generated ceilings (layer 2: rta_fill.cpp): the sun does not reach them
	sun_instance = RenderingServer.instance_create2(sun, scenario)
	lamp = RenderingServer.omni_light_create()
	RenderingServer.light_set_color(lamp, Color(1.0, 0.74, 0.42))
	# Godot's point light falls off as distance^-attenuation, and the game's unit is small (a character is about 65
	# high, the lamp is carried at its shoulder): a gentle exponent and an energy to match
	RenderingServer.light_set_param(lamp, RenderingServer.LIGHT_PARAM_ENERGY, 2.6)
	RenderingServer.light_set_param(lamp, RenderingServer.LIGHT_PARAM_RANGE, 330.0)
	RenderingServer.light_set_param(lamp, RenderingServer.LIGHT_PARAM_ATTENUATION, 0.9)
	lamp_instance = RenderingServer.instance_create2(lamp, scenario)
	sky_instance = RenderingServer.instance_create2(sky_mesh.get_rid(), scenario)
	RenderingServer.instance_geometry_set_material_override(sky_instance, sky_material.get_rid())
	RenderingServer.instance_set_ignore_culling(sky_instance, true)
	RenderingServer.instance_geometry_set_cast_shadows_setting(sky_instance, RenderingServer.SHADOW_CASTING_SETTING_OFF)
	RenderingServer.instance_set_pivot_data(sky_instance, -1000000.0, false)        # before every draw of the list
	RenderingServer.instance_set_visible(sky_instance, false)


func _level() -> void:
	var light := int(machine.peek_u32(G_WORLD_LIGHT)) & 0xFF
	if light != level_light and light > 0:
		level_light = light             # written when the level's options are read: after its first frames
		sky_version = -1
	var name := machine.peek_string(G_LEVEL_NAME, 16)
	if name == level:
		return
	level = name
	if remaster != null:
		remaster.call("new_level")
	_apply_preset(name)
	drawer.call("sky_reset")
	sky_version = -1
	sky_clear = Color(-1, -1, -1)
	said.clear()
	sun_found = sun_last            # until this level's own textures say otherwise: where the last clear one was lit from
	sun_fixed = false


# ---- the sky's colours -----------------------------------------------------------------------
static func _saturate(c: Color, by: float) -> Color:
	var grey := c.r * 0.30 + c.g * 0.59 + c.b * 0.11
	return Color(clampf(grey + (c.r - grey) * by, 0, 1), clampf(grey + (c.g - grey) * by, 0, 1), clampf(grey + (c.b - grey) * by, 0, 1))


func _palette(info: Dictionary) -> void:
	if not bool(info.get("have_clear", false)):
		return
	var clear: Color = info.clear
	var version := int(info.get("version", 0))
	if version == sky_version and clear.is_equal_approx(sky_clear):
		return
	sky_version = version
	sky_clear = clear
	level_dome = bool(info.get("dome", false))
	var top := 0.0
	var bottom := -0.03
	var ground := Color.BLACK
	var brightest: float = max(clear.r, clear.g, clear.b)
	if level_dome:
		# the painted dome: its own edges by direction; above the upper one its colour goes on, a little deeper, to the zenith
		top = float(info.top)
		bottom = float(info.bottom)
		var bytes: PackedByteArray = info.ring
		ring_image = Image.create_from_data(256, 2, false, Image.FORMAT_RGB8, bytes)
		var sum := Color(0, 0, 0)
		var low := Color(0, 0, 0)
		for k in range(0, 256, 4):
			sum += ring_image.get_pixel(k, 0)
			low += ring_image.get_pixel(k, 1)
		horizon = Color(sum.r / 64.0, sum.g / 64.0, sum.b / 64.0)
		low = Color(low.r / 64.0, low.g / 64.0, low.b / 64.0)
		zenith = _saturate(horizon, 1.12) * 0.70
		ground = low * 0.85
		brightest = max(horizon.r, horizon.g, horizon.b)
		level_dark = brightest < 0.16 and level_light < 128
	else:
		level_dark = brightest < 0.09
		if level_dark:
			# black above, as the game has it: only a breath of colour at the horizon so that walls have an edge
			horizon = Color(clear.r + 0.016, clear.g + 0.018, clear.b + 0.026)
			zenith = Color(clear.r * 0.5 + 0.002, clear.g * 0.5 + 0.003, clear.b * 0.5 + 0.006)
			ground = Color(clear.r * 0.5, clear.g * 0.5, clear.b * 0.5)
		else:
			# an open sky from one colour: paler and lighter at the horizon, deeper overhead
			var light := Color(brightest, brightest, brightest)
			horizon = clear.lerp(light, 0.30).lerp(Color(1, 1, 1), 0.16)
			zenith = _saturate(clear, 1.22) * 0.60
			ground = horizon.lerp(clear * 0.55, 0.65)
		ring_image = Image.create(256, 2, false, Image.FORMAT_RGB8)
		ring_image.fill(horizon)
	ring_texture.update(ring_image)
	RenderingServer.global_shader_parameter_set("rta_sky_zenith", Vector4(zenith.r, zenith.g, zenith.b, top))
	RenderingServer.global_shader_parameter_set("rta_sky_ground", Vector4(ground.r, ground.g, ground.b, bottom))
	var words := "%s %s %s" % [clear.to_html(false), level_dome, level_dark]
	if said.get("sky", "") != words and in_force.get("ground", false):
		said["sky"] = words
		print("rta_godot: level %s: clear colour %d %d %d, %s; light level %d; sky %s: horizon %s zenith %s" % [level, int(clear.r * 255), int(clear.g * 255),
			int(clear.b * 255), ("a dome from %.0f to %.0f degrees" % [rad_to_deg(bottom), rad_to_deg(top)]) if level_dome else "no dome", level_light,
			"dark" if level_dark else "open", horizon.to_html(false), zenith.to_html(false)])


func _sun_from_level(info: Dictionary) -> void:
	# The level's light is painted into its textures; the drawer reads out of them where it comes from
	# (RtaDrawer.get_sky_info: `sun`, a vector toward the light whose length says how clearly the textures agree).
	# Taken once it rests on enough of the level, then kept: a sun that wanders while one walks is worse than one that
	# is a little off.  Until then, and where the textures say nothing (a dark level): from the upper left of the view
	# the level was painted for.
	if sun_fixed or level_dark:
		return
	var samples := int(info.get("sun_samples", 0))
	if samples < 30000:
		return
	var toward: Vector3 = info.get("sun", Vector3.ZERO)
	var flat := Vector2(toward.x, toward.y)
	sun_fixed = samples >= 150000
	if flat.length() < SUN_CLEAR:
		if sun_fixed:
			print("rta_godot: level %s: the textures do not say where the light comes from (strength %.4f, toward %s; %d vertices): the default stays" % [level,
				flat.length(), str(toward), samples])
		return                              # no side is lighter than the other: the default stays
	var az := rad_to_deg(atan2(flat.y, flat.x))
	var el := clampf(rad_to_deg(atan2(toward.z, flat.length())), 38.0, 62.0)
	sun_found = Vector2(az, el)
	sun_last = sun_found
	if not said.has("sun") or sun_fixed:
		said["sun"] = true
		print("rta_godot: level %s: the painted light comes from azimuth %.0f, elevation %.0f (%s; %d vertices; strength %.4f)" % [level, az, el,
			"kept" if sun_fixed else "so far", samples, flat.length()])


func _sun_direction() -> Vector3:
	# the direction the light travels.  By itself: from the upper left of the view the level was painted for, 48 degrees
	# up - in a dark level from nearly overhead
	var az := float(look.sun_az)
	var el := float(look.sun_el)
	if el < -900.0:
		el = 82.0 if level_dark else sun_found.y
	if az < -900.0:
		az = sun_found.x
	var e := deg_to_rad(el)
	var a := deg_to_rad(az)
	return -Vector3(cos(a) * cos(e), sin(a) * cos(e), sin(e))


func _haze() -> void:
	var on: bool = in_force.get("fog", false)
	var amount := float(look.fog_amount) * (ground_amount if String(look.fog) == "auto" else 1.0) if on else 0.0
	var far := machine.peek_f32(G_FAR_CLIP)
	if far < 100.0 or far > 4000.0:
		far = 1800.0
	var start := float(look.fog_start)
	var end: float = min(float(look.fog_end), far * 0.78)
	var view: Dictionary = machine.get_view()
	var feet: Vector3 = view.get("player", Vector3.ZERO)
	var eye: Vector3 = view.get("eye", feet)
	if not in_force.get("ground", false):
		start += eye.distance_to(feet)          # a camera high above: the haze begins beyond the character, not at it
		end += eye.distance_to(feet) * 0.5
	if level_dark:
		start *= 0.55                           # darkness closes in sooner than daylight haze
		end *= 0.80
	RenderingServer.global_shader_parameter_set("rta_fog_range", Vector4(start, max(end, start + 100.0), feet.z + 70.0, 260.0))
	RenderingServer.global_shader_parameter_set("rta_fog_amount", Vector4(amount, 0.0 if level_dark else 0.55, 1.0, 0.0))
	RenderingServer.global_shader_parameter_set("rta_fog_colour", Vector4(horizon.r, horizon.g, horizon.b, 1.0))
	Engine.set_meta("rta_haze", [start, max(end, start + 100.0), amount, eye, far])     # for the HUD's bars (hud/world.gd)


func _lights() -> void:
	var sun_on: bool = in_force.get("sun", false)
	var lamp_on: bool = in_force.get("lamp", false)
	var s := float(look.shade)
	if s < 0.0:
		s = 0.64
		if level_dark:
			s = 0.84 if level_light >= 128 else 0.90
	shade = s
	var ambient := Color(1, 1, 1)
	var direction := _sun_direction()
	var want := Vector2(float(look.shadow_splits), float(look.shadow_far))
	if want != shadow_set and sun.is_valid():
		shadow_set = want
		RenderingServer.light_directional_set_shadow_mode(sun, RenderingServer.LIGHT_DIRECTIONAL_SHADOW_PARALLEL_4_SPLITS if want.x >= 4.0 else (
			RenderingServer.LIGHT_DIRECTIONAL_SHADOW_PARALLEL_2_SPLITS if want.x >= 2.0 else RenderingServer.LIGHT_DIRECTIONAL_SHADOW_ORTHOGONAL))
		RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_SHADOW_MAX_DISTANCE, want.y)
	if sun_on:
		# what is left in a shadow takes a little of the sky's tint; the sun brings the rest back, so that a lit
		# surface that faces it has the game's own colour
		var tint := Color(1, 1, 1)
		var top: float = max(zenith.r, zenith.g, zenith.b)
		if top > 0.05 and not level_dark:
			tint = Color(1, 1, 1).lerp(Color(zenith.r / top, zenith.g / top, zenith.b / top), 0.30)
		ambient = Color(s * tint.r, s * tint.g, s * tint.b)
		if forward_plus and String(look.balance) != "off":
			# Forward+ (Metal, Vulkan) adds the lights in linear light: the shadowed part arrives as lin(colour x ambient)
			# (EMISSION), so the sun must bring 1 - lin(ambient) of lin(colour) for a lit surface that faces it to be the
			# game's own colour again.  The Compatibility rule below left Forward+'s lit scenes darker and greyer (fifth
			# round: valor 51/61/46 against 58/65/44); Godot takes a light's colour as sRGB and makes it linear itself.
			# Measured against the Compatibility renderer at the same ticks (local/godot-r6/balance: hub, valor, drunare,
			# tormenta): the full linear rule overshoots it (hub 114 against 107, valor 47 against 35 of 255) - the
			# Compatibility picture, the look of the earlier rounds, keeps its shadows deeper - and the old rule fell short
			# (86, 29).  `balance` (0..1, default 0.6) goes that part of the way from the old rule to the linear one.
			var lin := Color(1.0 - ambient.srgb_to_linear().r, 1.0 - ambient.srgb_to_linear().g, 1.0 - ambient.srgb_to_linear().b)
			var peak: float = max(lin.r, lin.g, lin.b, 0.0001)
			var old_energy: float = pow(max(1.0 - ambient.r, 1.0 - ambient.g, 1.0 - ambient.b), 2.2)
			var part: float = clampf(float(look.balance) if String(look.balance).is_valid_float() else 0.6, 0.0, 1.0)
			RenderingServer.light_set_color(sun, Color(lin.r / peak, lin.g / peak, lin.b / peak).linear_to_srgb())
			RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_ENERGY, lerpf(old_energy, peak, part) * float(look.sun_gain))
		else:
			var add := Color((1.0 - ambient.r), (1.0 - ambient.g), (1.0 - ambient.b))
			var energy: float = max(add.r, add.g, add.b)
			RenderingServer.light_set_color(sun, Color(pow(add.r / energy, 2.2), pow(add.g / energy, 2.2), pow(add.b / energy, 2.2)))
			RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_ENERGY, pow(energy, 2.2) * float(look.sun_gain))
		RenderingServer.instance_set_transform(sun_instance, Transform3D(Basis(), Vector3.ZERO).looking_at(direction, Vector3(0, 0, 1)))
	RenderingServer.global_shader_parameter_set("rta_light_ambient", Vector4(ambient.r, ambient.g, ambient.b, 1.0))
	RenderingServer.instance_set_visible(sun_instance, sun_on)
	# the carried lamp, by itself (auto), only where none of the game's lights reaches the player
	if String(look.lamp) == "auto":
		lamp_share = move_toward(lamp_share, 0.0 if game_lights > 0 else 1.0, 0.03)
	else:
		lamp_share = 1.0
	RenderingServer.light_set_param(lamp, RenderingServer.LIGHT_PARAM_ENERGY, 2.6 * lamp_share)
	RenderingServer.instance_set_visible(lamp_instance, lamp_on and lamp_share > 0.01)
	# the sky's own sun: where the light comes from, in an open sky without a painted dome
	var glow := float(look.sky_sun) * (0.0 if (level_dark or level_dome) else 0.9)
	var warm := Color(1.0, 0.93, 0.80).lerp(horizon, 0.35)
	RenderingServer.global_shader_parameter_set("rta_sky_sun", Vector4(-direction.x, -direction.y, -direction.z, glow))
	RenderingServer.global_shader_parameter_set("rta_sky_sun_colour", Vector4(warm.r, warm.g, warm.b, 0.0))
	if lamp_on:
		var object := machine.peek_u32(G_PLAYERS + 0x43D8)
		if object != 0:
			var at := Vector3(machine.peek_f32(object + 0x10), machine.peek_f32(object + 0x14), machine.peek_f32(object + 0x18))
			lamp_before = lamp_now
			lamp_now = at + Vector3(0, 0, 74)
			lamp_before_ok = lamp_before.distance_to(lamp_now) < 40.0
			RenderingServer.instance_set_transform(lamp_instance, Transform3D(Basis(), lamp_now))


# ---- the game's own lights ---------------------------------------------------------------------
func _torch_slot(k: int) -> Dictionary:
	while torches.size() <= k:
		var light := RenderingServer.omni_light_create()
		# Godot's fall-off is distance^-attenuation, and the game's units are small (a torch reaches 240): 0.35 (stage 4's measure)
		RenderingServer.light_set_param(light, RenderingServer.LIGHT_PARAM_ATTENUATION, 0.35)
		RenderingServer.light_set_param(light, RenderingServer.LIGHT_PARAM_SHADOW_BIAS, 0.4)
		RenderingServer.light_set_param(light, RenderingServer.LIGHT_PARAM_SHADOW_NORMAL_BIAS, 2.0)
		RenderingServer.light_set_param(light, RenderingServer.LIGHT_PARAM_SHADOW_BLUR, 1.5)
		var instance := RenderingServer.instance_create2(light, scenario)
		RenderingServer.instance_set_visible(instance, false)
		torches.append({"light": light, "instance": instance, "address": 0, "shadow": false})
	return torches[k]


func _torches() -> void:
	var on: bool = in_force.get("lights", false)
	game_lights = 0
	var feet: Vector3 = machine.get_view().get("player", Vector3.ZERO)
	var eye: Vector3 = machine.get_view().get("eye", feet)
	var found: Array = machine.get_lights(eye, 1300.0, 96) if (on or String(look.lamp) == "auto") else []
	for g in found:
		if Vector3(g.position).distance_to(feet) < float(g.radius) * 0.85:
			game_lights += 1
	var wanted := int(look.light_max) if on else 0
	found.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return Vector3(a.position).distance_to(eye) < Vector3(b.position).distance_to(eye))
	torch_clock += 1.0 / 60.0
	var shadows := int(look.light_shadows)
	var dark_gain := 1.8 if level_dark else 0.8
	for k in range(max(wanted, torches.size())):
		var t := _torch_slot(k)
		if k >= wanted or k >= found.size():
			RenderingServer.instance_set_visible(t.instance, false)
			continue
		var g: Dictionary = found[k]
		var c: Color = g.colour
		var peak: float = max(c.r, c.g, c.b, 0.001)
		var hue := Color(c.r / peak, c.g / peak, c.b / peak).lerp(Color(1.0, 0.70, 0.42), 0.30)
		var phase := float(int(g.address) % 997) * 0.37
		var flicker := 1.0 + 0.06 * sin(torch_clock * 7.3 + phase) + 0.04 * sin(torch_clock * 13.7 + phase * 1.9) + 0.03 * sin(torch_clock * 23.1 + phase * 0.7)
		RenderingServer.light_set_color(t.light, hue)
		RenderingServer.light_set_param(t.light, RenderingServer.LIGHT_PARAM_ENERGY, float(look.light_energy) * 2.4 * dark_gain * clampf(peak, 0.25, 1.6) * flicker)
		RenderingServer.light_set_param(t.light, RenderingServer.LIGHT_PARAM_RANGE, clampf(float(g.radius) * 1.15, 60.0, 1400.0))
		var shadow := k < shadows
		if shadow != bool(t.shadow):
			t.shadow = shadow
			RenderingServer.light_set_shadow(t.light, shadow)
		t.address = int(g.address)
		RenderingServer.instance_set_transform(t.instance, Transform3D(Basis(), Vector3(g.position)))
		RenderingServer.instance_set_visible(t.instance, true)


func lights_text() -> String:
	var view: Dictionary = machine.get_view()
	var eye: Vector3 = view.get("eye", Vector3.ZERO)
	var text := "the game's lights within 1300 of the eye:"
	for g in machine.get_lights(eye, 1300.0, 96):
		text += "\n  node 0x%x at %s colour %s radius %.0f (second %.2f) falloff %.6f floor %.2f; %.0f from the eye" % [int(g.address), str(g.position),
			str(g.colour), float(g.radius), float(g.radius_2), float(g.falloff), float(g.floor), Vector3(g.position).distance_to(eye)]
	return text


func _backdrop(info: Dictionary) -> void:
	# bare: none of the level's own pieces reaches under the player's feet (some arenas, entered alone, put the
	# character where the game has no ground at all)
	var bare := int(info.get("ground_near", 1)) == 0
	backdrop_bare = maxi(backdrop_bare, 0) + 1 if bare else mini(backdrop_bare, 0) - 1
	var mode := String(look.backdrop)
	# on after half a second without ground under the feet, off after a second with it again
	var want: bool = mode == "on" or (mode == "auto" and in_force.get("ground", false) and (backdrop_bare > 30 or (backdrop_on and backdrop_bare > -60)))
	if want and not backdrop_instance.is_valid():
		backdrop_mesh = PlaneMesh.new()
		backdrop_mesh.size = Vector2(9000, 9000)
		backdrop_mesh.orientation = PlaneMesh.FACE_Z      # the game's world is z up
		backdrop_material = ShaderMaterial.new()
		backdrop_material.shader = load("res://shaders/backdrop.gdshader")
		backdrop_instance = RenderingServer.instance_create2(backdrop_mesh.get_rid(), scenario)
		RenderingServer.instance_geometry_set_material_override(backdrop_instance, backdrop_material.get_rid())
		RenderingServer.instance_geometry_set_cast_shadows_setting(backdrop_instance, RenderingServer.SHADOW_CASTING_SETTING_OFF)
		RenderingServer.instance_set_pivot_data(backdrop_instance, -900000.0, false)   # after the sky, before every draw of the list
	if not backdrop_instance.is_valid():
		return
	if want:
		var view: Dictionary = machine.get_view()
		var feet: Vector3 = view.get("player", Vector3.ZERO)
		# under the feet, where they are: a character the game lets fall through nothing stands on it all the same
		backdrop_z = feet.z if not backdrop_on else move_toward(backdrop_z, feet.z, maxf(2.0, absf(feet.z - backdrop_z) * 0.5))
		RenderingServer.instance_set_transform(backdrop_instance, Transform3D(Basis(), Vector3(feet.x, feet.y, backdrop_z - 0.5)))
		var tint := horizon.lerp(Color(0.5, 0.48, 0.45), 0.55)
		var stone := Color(tint.r, tint.g, tint.b) * (0.42 if level_dark else 0.62)
		backdrop_material.set_shader_parameter("stone", Vector3(stone.r, stone.g, stone.b))
		backdrop_material.set_shader_parameter("feet", feet)
		if not backdrop_on:
			print("rta_godot: level %s: no ground of its own under the character: the backdrop is laid at z %.1f" % [level, backdrop_z])
	RenderingServer.instance_set_visible(backdrop_instance, want)
	backdrop_on = want


func _models(info: Dictionary) -> void:
	var on: bool = in_force.get("models", false)
	RenderingServer.global_shader_parameter_set("rta_model", Vector4(float(look.model_rim) if on else 0.0, float(look.model_form) if on else 0.0,
		float(look.model_sharp) if on else 1.0, float(look.contact) if on else 0.0))
	# the rim: the sky's colour at the horizon, lighter; a dark level's a little warm, as from the torches
	var rim := horizon.lerp(Color(1, 1, 1), 0.45)
	if level_dark or max(horizon.r, horizon.g, horizon.b) < 0.2:
		rim = Color(0.62, 0.52, 0.42)
	RenderingServer.global_shader_parameter_set("rta_model_rim", Vector4(rim.r, rim.g, rim.b, 0.0))
	var found: PackedFloat32Array = info.get("contacts", PackedFloat32Array())
	var n := mini(found.size() / 4, 16)
	if n == 0 and contacts_now == 0:
		return
	for k in 16:
		if k < n:
			contact_image.set_pixel(k, 0, Color(found[k * 4], found[k * 4 + 1], found[k * 4 + 2], found[k * 4 + 3]))
		else:
			contact_image.set_pixel(k, 0, Color(0, 0, 0, 0))
	contact_texture.update(contact_image)
	contacts_now = n


func _post() -> void:
	if not environment.is_valid():
		return
	_gpu_quality_update()
	var bloom: bool = in_force.get("bloom", false)
	var strength := float(look.bloom_strength)
	RenderingServer.environment_set_glow(environment, bloom, PackedFloat32Array([0.0, 0.35, 0.8, 1.0, 0.6, 0.0, 0.0]), 0.55 * strength, 1.0, 0.05, 0.0,
		RenderingServer.ENV_GLOW_BLEND_MODE_SCREEN, 0.74, 2.0, 12.0, 0.0, RID())
	var grade: bool = in_force.get("grade", false)
	RenderingServer.environment_set_adjustment(environment, grade, float(look.brightness), float(look.contrast), float(look.saturation), false, RID())
	# the 3-D surface drawn at a share of its pixels and enlarged (FSR 1, sharpened): scale3d 1.0 = every pixel
	var scale3d := clampf(float(look.scale3d), 0.5, 1.0)
	# display.upscale (main.gd): above 60 pictures a second only, the 3-D surface at 3/4 each way, enlarged
	var mode := RenderingServer.VIEWPORT_SCALING_3D_MODE_FSR
	var up := String(main.get("upscale")) if main != null else "off"
	if up != "off" and int(main.get("tween_n")) > 1 and scale3d >= 0.999:
		scale3d = 0.75
		if up == "metalfx" and RenderingServer.get_current_rendering_driver_name() == "metal" and RenderingServer.get_current_rendering_method() == "forward_plus":
			mode = RenderingServer.VIEWPORT_SCALING_3D_MODE_METALFX_SPATIAL
	if gpu_quality_enabled():
		scale3d = maxf(0.5, scale3d * gpu_quality.quality().y)
		# The fallback resizes only the world. Bilinear was closer to the native
		# reference than FSR/MetalFX in the fixed-tick comparisons, with no extra
		# sharpening passes. Preserve an explicitly selected upscaler/scale.
		if gpu_quality.quality().y < 0.999 and up == "off" and float(look.scale3d) >= 0.999:
			mode = RenderingServer.VIEWPORT_SCALING_3D_MODE_BILINEAR
	if scale3d != scale_set and viewport.is_valid():
		scale_set = scale3d
		RenderingServer.viewport_set_scaling_3d_mode(viewport, RenderingServer.VIEWPORT_SCALING_3D_MODE_BILINEAR if scale3d >= 0.999 else mode)
		RenderingServer.viewport_set_scaling_3d_scale(viewport, scale3d)
		RenderingServer.viewport_set_fsr_sharpness(viewport, 0.2)
	var samples := int(String(look.aa).to_int())
	if gpu_quality_enabled():
		samples = int(gpu_quality.quality().x)
	if samples != aa_set and viewport.is_valid():
		aa_set = samples
		RenderingServer.viewport_set_msaa_3d(viewport, RenderingServer.VIEWPORT_MSAA_8X if samples >= 8 else (RenderingServer.VIEWPORT_MSAA_4X if samples >= 4 else (
			RenderingServer.VIEWPORT_MSAA_2X if samples >= 2 else RenderingServer.VIEWPORT_MSAA_DISABLED)))


func gpu_quality_enabled() -> bool:
	return main != null and String(main.opt.edition) == "remastered" and String(look.adaptive_aa) != "off"


func gpu_between_allowed() -> bool:
	return not gpu_quality_enabled() or gpu_quality.between


func _gpu_quality_update() -> void:
	if not gpu_quality_enabled() or not viewport.is_valid():
		return
	var requested := int(String(look.aa).to_int())
	if requested != gpu_requested_samples:
		gpu_requested_samples = requested
		gpu_quality.configure(requested)
	if level != gpu_level:
		gpu_level = level
		gpu_quality.reset_observations()
		gpu_sample_usec = 0
	# Read existing presentation flags only. The HUD fade word can stay at 128
	# throughout normal play: require a change or an actually submitted overlay
	# (docs/fade-lifetime.md), not the retained value alone. The display colour
	# multipliers are 128 when neutral (docs/loading-transitions.md).
	var hud_fade: int = machine.peek_u32(0x4F66AC)
	var hud_fading: bool = (gpu_hud_fade >= 0 and hud_fade != gpu_hud_fade) or (hud_fade > 0 and bool(drawer.call("has_screen_overlay")))
	gpu_hud_fade = hud_fade
	var safe: bool = (machine.peek_u32(0x506094) & 0xFF) == 0 and machine.peek_u32(0x506048) == 0 \
		and machine.peek_u32(0x50604C) == 0 and not hud_fading \
		and machine.peek_u32(0x44FD8C) == 128 and machine.peek_u32(0x44FD90) == 128 and machine.peek_u32(0x44FD94) == 128 \
		and machine.peek_u32(0x44FD88) >= 128 \
		and machine.peek_string(0x41B6D0, 16) == "" and (machine.peek_u32(0x41B510) & 0xFF) == 0 \
		and (machine.peek_u32(0x44FCD0) & 0xFF) == 0
	var info: Dictionary = machine.get_view()
	safe = safe and bool(info.get("valid", false)) and bool(info.get("active", false)) and not bool(info.get("fallback", false))
	if not safe:
		gpu_quality.update(0.0, 0.0, false, 1000.0 / 60.0)
		gpu_sample_usec = 0
		_gpu_quality_log(-1.0, false)
		return
	var measured := -1.0
	var timer: RefCounted = main.get("gpu_timer")
	if timer != null and bool(timer.call("is_available")):
		var sample: Dictionary = timer.call("sample")
		if sample.is_empty() or int(sample.frame) == gpu_sample_frame:
			return
		gpu_sample_frame = int(sample.frame)
		measured = float(sample.gpu_ms)
	else:
		if gpu_measure_viewport != viewport:
			gpu_measure_viewport = viewport
			RenderingServer.viewport_set_measure_render_time(viewport, true)
		measured = RenderingServer.viewport_get_measured_render_time_gpu(viewport)
	var now := Time.get_ticks_usec()
	var elapsed := (now - gpu_sample_usec) / 1000000.0 if gpu_sample_usec > 0 else 1.0 / 60.0
	gpu_sample_usec = now
	if gpu_quality.update(measured, elapsed, true, float(main.get("refresh_s")) * 1000.0):
		var q := gpu_quality.quality()
		print("rta_gpu_quality: level=%s gpu=%.2fms samples=%d scale=%.2f blank=%d" % [level, gpu_quality.ema, int(q.x), q.y, main.blanks])
	_gpu_quality_log(measured, true)


func _gpu_quality_log(measured: float, safe: bool) -> void:
	if String(main.opt.frame_log) != "":
		var q := gpu_quality.quality()
		main.frame_rows.append("G,%d,%d,%d,%.4f,%.4f,%d,%d,%.3f,%d,%d" % [main.blanks, Time.get_ticks_usec(), gpu_sample_frame,
			measured, gpu_quality.ema, gpu_quality.rung, int(q.x), q.y, int(safe), int(gpu_quality.between)])


func stats_text() -> String:
	# one line for tools/godot/presets.py: what the level's own colours and lights are, as this script sees them now
	var info: Dictionary = drawer.call("get_sky_info")
	var clear: Color = info.get("clear", Color.BLACK)
	var view: Dictionary = machine.get_view()
	var eye: Vector3 = view.get("eye", Vector3.ZERO)
	var found: Array = machine.get_lights(eye, 1300.0, 96)
	var sum := Color(0, 0, 0)
	for g in found:
		sum += Color(g.colour)
	var n: int = maxi(found.size(), 1)
	var toward: Vector3 = info.get("sun", Vector3.ZERO)
	return "level=%s clear=%.4f,%.4f,%.4f have_clear=%d dome=%d dark=%d light=%d far=%.0f horizon=%s zenith=%s sun=%.1f,%.1f,%.5f,%d lights=%d lights_colour=%.3f,%.3f,%.3f shade=%.3f preset=%s ground=%d level_draws=%d ground_near=%d feet=%s backdrop=%d" % [
		level, clear.r, clear.g, clear.b, 1 if bool(info.get("have_clear", false)) else 0, 1 if level_dome else 0, 1 if level_dark else 0, level_light,
		machine.peek_f32(G_FAR_CLIP), horizon.to_html(false), zenith.to_html(false), sun_found.x, sun_found.y, Vector2(toward.x, toward.y).length(),
		int(info.get("sun_samples", 0)), found.size(), sum.r / n, sum.g / n, sum.b / n, shade, preset_applied if preset_applied != "" else "-",
		1 if in_force.get("ground", false) else 0, int(info.get("level_draws", -1)), int(info.get("ground_near", -1)),
		str(view.get("player", Vector3.ZERO)).replace(" ", ""), 1 if backdrop_on else 0]


func info_text() -> String:
	return "look %s; in force %s; level %s (%s%s, light %d), ground view %.2f, shade %.2f, horizon %s zenith %s" % [str(look), str(in_force), level,
		"dark" if level_dark else "open", ", dome" if level_dome else "", level_light, ground_amount, shade, horizon.to_html(false), zenith.to_html(false)]


func command(w: PackedStringArray) -> void:
	if w[0] == "look":
		if w.size() >= 2 and w[1] == "info":
			print("[blank %d] rta_godot: %s" % [main.blanks, info_text()])
		elif w.size() >= 2 and w[1] == "lights":
			print("[blank %d] rta_godot: %s" % [main.blanks, lights_text()])
		elif w.size() >= 2 and w[1] == "stats":
			print("[blank %d] rta_look_stats %s" % [main.blanks, stats_text()])
		elif w.size() >= 3:
			_put(w[1], w[2])
	elif w[0] == "scene" and w.size() >= 3:
		if w[1] == "shadow":
			_put("sun", "on" if w[2] == "on" else "off")
		elif w[1] == "light":
			_put("lamp", "on" if w[2] == "on" else "off")
		elif w[1] == "shade":
			_put("shade", w[2])
		elif w[1] == "describe" and w.size() >= 4:
			# debugging: the draws of this frame that go to the 3-D surface, into a file
			var file := FileAccess.open(w[3], FileAccess.WRITE)
			if file != null:
				file.store_string(str(drawer.call("describe_frame", w[2].to_int())))
				file.close()
	elif w[0] == "remaster" and remaster != null:
		remaster.call("command", w)
	elif w[0] == "er" and w.size() >= 2 and w[1] == "world" and world_layer != null:
		world_layer.call("command", w)
	elif w[0] == "er" and er != null:
		er.call("command", w)
	elif w[0] == "card" and w.size() >= 2 and card != null:
		# app card info | app card shot FILE: the character card's picture as it is now (after this frame is drawn)
		if w[1] == "info":
			print("[blank %d] rta_godot: %s" % [main.blanks, card.call("info_text")])
		elif w[1] == "shot" and w.size() >= 3:
			var path := w[2]
			await RenderingServer.frame_post_draw
			var image: Image = (card.call("texture") as Texture2D).get_image()
			image.save_png(path)
			print("rta_godot: wrote %s (%d x %d), the character card; %s" % [path, image.get_width(), image.get_height(), card.call("info_text")])
	elif w[0] == "camera" and w.size() >= 2:
		if w[1] == "game":
			drawer.call("set_scene_option", "focus", 390.0)
			pull_back = 1.0
			orbit = 0.0
			raise = 0.0
		elif w.size() >= 3 and w[1] == "pull":
			pull_back = w[2].to_float()
		elif w.size() >= 3 and w[1] == "orbit":
			orbit = w[2].to_float()
		elif w.size() >= 3 and w[1] == "raise":
			raise = w[2].to_float()
		elif w.size() >= 3 and w[1] == "focus":
			drawer.call("set_scene_option", "focus", w[2].to_float())
		elif w.size() >= 3 and w[1] == "around":
			# app camera around DEG [PULL [RAISE]]: round the local player (the turn's point is the player's chest, not the
			# overhead view's 390 units out): to see a character from the front, close
			var view: Dictionary = machine.get_view()
			var eye: Vector3 = view.get("eye", Vector3.ZERO)
			var forward: Vector3 = view.get("forward", Vector3(0, 1, 0))
			var feet: Vector3 = view.get("player", eye)
			drawer.call("set_scene_option", "focus", maxf((feet + Vector3(0, 0, 34) - eye).dot(forward), 20.0))
			orbit = w[2].to_float()
			pull_back = w[3].to_float() if w.size() >= 4 else 1.0
			raise = w[4].to_float() if w.size() >= 5 else 0.0
		_camera_options()


func _exit_tree() -> void:
	if Engine.has_meta("rta_haze"):
		Engine.remove_meta("rta_haze")
