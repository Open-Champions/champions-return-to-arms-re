extends Node
# scene_view.gd - what Godot adds once the game's scene is in world space (--mode scene).
#
# RtaDrawer puts the 3-D scene into a Godot scenario as meshes in the game's world
# coordinates (x and y on the ground, z up; a character is about 20 units tall) under a
# camera that follows the game's.  This script owns what is Godot's own in that world:
#   --shadow       a sun: a directional light with a shadow map.  The game's colours are kept
#                  where the sun reaches and darkened where it does not, so characters and
#                  props throw real-time shadows on the level
#   --light        a lamp: a warm point light carried above the first player
#   --pull-back F  the camera F times as far from the point it looks at as the game's is
#   --orbit DEG    ... and turned round the vertical through that point
# and the same from a script, at a chosen tick:
#   app scene shadow on|off      app scene light on|off      app scene shade S (0..1: what a shadow leaves; default 0.62)
#   app camera pull F | orbit DEG | raise DEG | game        (game: the game's own camera again)
# The lights are made through the RenderingServer in the drawer's scenario (it is not a
# World3D of the scene tree).

const G_PLAYERS := 0x4D8AF0             # symbols: g_players; +0x43d8 the first player's object, +0x10 its position
# How dark a shadow is: the part of a pixel's stored value that is left where the sun does not reach.
# The Compatibility renderer draws a light that has a shadow map in a pass of its own and ADDS that pass
# to the picture as stored values (after the conversion from linear light), so the two energies that add
# up to the game's own picture where the sun reaches are not a and 1 - a but shade^2.2 and (1 - shade)^2.2
# (measured: ambient 0.55 with a sun of 0.45 gave 2.2 times the game's light; test/scene/cal).
var shade := 0.62
var ambient_override := -1.0            # test aids ("app scene ambient E", "app scene sun E"): the energies themselves
var sun_override := -1.0

var main: Node
var scenario: RID
var sun: RID
var sun_instance: RID
var lamp: RID
var lamp_instance: RID
var shadow_on := false
var light_on := false
var pull_back := 1.0
var orbit := 0.0
var raise := 0.0
var lamp_said := false


func _ready() -> void:
	shadow_on = main.opt.shadow
	light_on = main.opt.light
	pull_back = main.opt.pull_back
	orbit = main.opt.orbit
	RenderingServer.directional_shadow_atlas_set_size(4096, true)
	_apply()


func release() -> void:
	for rid in [sun_instance, lamp_instance, sun, lamp]:
		if rid.is_valid():
			RenderingServer.free_rid(rid)
	sun_instance = RID()
	lamp_instance = RID()
	sun = RID()
	lamp = RID()


func takes_input() -> bool:
	return false


func _apply() -> void:
	var drawer: Object = main.drawer
	drawer.call("set_scene_option", "lit", 1.0 if (shadow_on or light_on) else 0.0)
	drawer.call("set_scene_option", "shadows", 1.0 if shadow_on else 0.0)
	drawer.call("set_scene_option", "ambient", ambient_override if ambient_override >= 0.0 else (pow(shade, 2.2) if shadow_on else 1.0))
	if sun.is_valid():
		RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_ENERGY, sun_override if sun_override >= 0.0 else pow(1.0 - shade, 2.2))
	drawer.call("set_scene_option", "pull_back", pull_back)
	drawer.call("set_scene_option", "orbit", orbit)
	drawer.call("set_scene_option", "raise", raise)
	if sun_instance.is_valid():
		RenderingServer.instance_set_visible(sun_instance, shadow_on)
	if lamp_instance.is_valid():
		RenderingServer.instance_set_visible(lamp_instance, light_on)


func _make_lights(to: RID) -> void:
	for rid in [sun_instance, lamp_instance, sun, lamp]:
		if rid.is_valid():
			RenderingServer.free_rid(rid)
	scenario = to
	sun = RenderingServer.directional_light_create()
	RenderingServer.light_set_color(sun, Color(1, 1, 1))
	RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_ENERGY, pow(1.0 - shade, 2.2))
	RenderingServer.light_set_shadow(sun, true)
	RenderingServer.light_directional_set_shadow_mode(sun, RenderingServer.LIGHT_DIRECTIONAL_SHADOW_PARALLEL_4_SPLITS)
	RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_SHADOW_MAX_DISTANCE, 1400.0)
	RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_SHADOW_BIAS, 0.6)
	RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_SHADOW_NORMAL_BIAS, 3.0)
	RenderingServer.light_set_param(sun, RenderingServer.LIGHT_PARAM_SHADOW_BLUR, 1.5)
	sun_instance = RenderingServer.instance_create2(sun, scenario)
	# from the upper left of the game's usual view, about 50 degrees above the ground (the world is z up)
	var direction := Vector3(0.50, 0.38, -0.78).normalized()
	RenderingServer.instance_set_transform(sun_instance, Transform3D(Basis(), Vector3.ZERO).looking_at(direction, Vector3(0, 0, 1)))
	lamp = RenderingServer.omni_light_create()
	RenderingServer.light_set_color(lamp, Color(1.0, 0.72, 0.38))
	# Godot's point light falls off as distance^-attenuation, and the game's unit is small (a character is
	# about 20 high, the lamp hangs 34 above the ground): a gentle exponent and an energy to match
	RenderingServer.light_set_param(lamp, RenderingServer.LIGHT_PARAM_ENERGY, 5.0)
	RenderingServer.light_set_param(lamp, RenderingServer.LIGHT_PARAM_RANGE, 190.0)
	RenderingServer.light_set_param(lamp, RenderingServer.LIGHT_PARAM_ATTENUATION, 0.35)
	lamp_instance = RenderingServer.instance_create2(lamp, scenario)
	_apply()


func frame() -> void:
	# once per list, after the drawer has taken it
	var drawer: Object = main.drawer
	var world: RID = drawer.call("get_world_scenario")
	if not world.is_valid():
		return
	if world != scenario:
		_make_lights(world)
	if light_on:
		var machine: RtaMachine = main.machine
		var object := machine.peek_u32(G_PLAYERS + 0x43D8)
		if object != 0:
			var at := Vector3(machine.peek_f32(object + 0x10), machine.peek_f32(object + 0x14), machine.peek_f32(object + 0x18))
			RenderingServer.instance_set_transform(lamp_instance, Transform3D(Basis(), at + Vector3(0, 0, 34)))
			if not lamp_said:
				lamp_said = true
				print("rta_godot: the lamp is carried at %s (the player's object at 0x%x)" % [at + Vector3(0, 0, 34), object])


func command(w: PackedStringArray) -> void:
	if w[0] == "scene" and w.size() >= 3:
		if w[1] == "shadow":
			shadow_on = w[2] == "on"
		elif w[1] == "light":
			light_on = w[2] == "on"
		elif w[1] == "shade":
			shade = w[2].to_float()
		elif w[1] == "sun":
			sun_override = w[2].to_float()
		elif w[1] == "ambient":
			ambient_override = w[2].to_float()
	elif w[0] == "camera" and w.size() >= 2:
		if w[1] == "game":
			pull_back = 1.0
			orbit = 0.0
			raise = 0.0
		elif w.size() >= 3 and w[1] == "pull":
			pull_back = w[2].to_float()
		elif w.size() >= 3 and w[1] == "orbit":
			orbit = w[2].to_float()
		elif w.size() >= 3 and w[1] == "raise":
			raise = w[2].to_float()
	_apply()
