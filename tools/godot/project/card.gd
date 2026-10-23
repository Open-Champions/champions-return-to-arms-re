extends Node
# card.gd - the character card: the local player's character drawn alone, turning slowly, lit by lights of its own, as a
# texture the portal shows on its character card (portal/widgets.gd Portrait.texture).
#
#   main.get_character_card() -> Texture2D       (the game scene: res://main.tscn's root, main.gd)
#   e.g. in the portal:  portrait.texture = handover.game.call("get_character_card")
# The texture is a SubViewport's (a ViewportTexture): it changes by itself; it shows nothing until the character has been
# seen standing still once in scene mode (has_figure()).  The background is transparent.
#
# RtaDrawer copies the player's model packets out of the scene into this SubViewport's world (extension/src/rta_card.cpp);
# this script says when (the character has stood still for half a second; again every 6 seconds while it stands, so
# that a new weapon or armour shows) and turns the figure.  In first person the game leaves the player out of its frames:
# the card keeps what it had.

const SIZE := Vector2i(256, 320)
const TURN_SPEED := 0.45                # radians a second

var main: Node
var drawer: Object
var viewport: SubViewport
var camera: Camera3D
var still_frames := 0
var last_feet := Vector3(1e9, 0, 0)
var since_capture := 1000000
var turn := 0.0
var framed_height := -1.0
var asked_msec := -100000               # when texture() was last asked for


func _ready() -> void:
	viewport = SubViewport.new()
	viewport.size = SIZE
	viewport.world_3d = World3D.new()          # a world of its own (own_world_3d would render a COPY of it, without the figure)
	viewport.transparent_bg = true
	viewport.msaa_3d = Viewport.MSAA_4X
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(viewport)
	camera = Camera3D.new()
	camera.fov = 30.0
	camera.near = 4.0
	camera.far = 2000.0
	viewport.add_child(camera)
	var environment := Environment.new()
	environment.background_mode = Environment.BG_CLEAR_COLOR
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	viewport.add_child(world_environment)
	# a warm key light from the front left above, a cool rim light from behind (the game's world: z up)
	for spec in [[Vector3(-0.55, -0.75, 0.55), Color(1.0, 0.88, 0.72), 0.95], [Vector3(0.45, 0.85, 0.25), Color(0.62, 0.74, 1.0), 0.70]]:
		var light := DirectionalLight3D.new()
		light.light_color = spec[1]
		light.light_energy = spec[2]
		light.shadow_enabled = false
		viewport.add_child(light)
		light.look_at_from_position(Vector3.ZERO, -Vector3(spec[0]), Vector3(0, 0, 1))
	_frame(64.0)
	drawer.call("set_card_scenario", viewport.find_world_3d().scenario)
	if OS.has_environment("RTA_CARD_TEST"):         # test aid: a box where the figure stands
		var box := MeshInstance3D.new()
		box.mesh = BoxMesh.new()
		box.scale = Vector3(6, 6, 6)
		box.position = Vector3(30, 0, 3)
		viewport.add_child(box)


func texture() -> Texture2D:
	asked_msec = Time.get_ticks_msec()
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	return viewport.get_texture()


func has_figure() -> bool:
	return int(drawer.call("get_card_info").get("draws", 0)) > 0


func _frame(height: float) -> void:
	# the figure stands at the origin, feet at z 0: the whole of it in the picture, a little room above the head
	var fit := height * 1.26
	var distance := fit * 0.5 / tan(deg_to_rad(camera.fov * 0.5))
	var at := Vector3(0, 0, height * 0.49)
	camera.look_at_from_position(at + Vector3(0, -distance, height * 0.10), at, Vector3(0, 0, 1))
	framed_height = height


# Before the drawer takes the frame (scene_view.gd before_frame)
func before_frame() -> void:
	var view: Dictionary = main.machine.get_view()
	var feet: Vector3 = view.get("player", Vector3.ZERO)
	var visible: bool = bool(view.get("valid", false)) and bool(view.get("have_player", false)) and not bool(view.get("hide_player", false))
	# First-person body modes may expose only the near-clipped arms. Keep the last whole
	# character portrait; do not replace it with a partial first-person packet capture.
	visible = visible and int(view.get("shown", 0)) != 4
	if feet.distance_to(last_feet) < 0.4:
		still_frames += 1
	else:
		still_frames = 0
	last_feet = feet
	since_capture += 1
	var capture := visible and still_frames >= 30 and (since_capture >= 360 or not has_figure())
	if capture:
		since_capture = 0
	drawer.call("card_focus", feet, capture)


# After the drawer has taken the frame
func frame(delta: float) -> void:
	# drawn only while somebody can see it: the portal in front (its cards show it), or the texture asked for in the last
	# two seconds (a test's shot) - a 3-D picture of its own every refresh costs the game's frame time otherwise
	var portal: Node = main.get("portal")
	var wanted: bool = (portal != null and bool(portal.get("shown"))) or Time.get_ticks_msec() - asked_msec < 2000 or OS.has_environment("RTA_CARD_TEST")
	var mode := SubViewport.UPDATE_ALWAYS if wanted else SubViewport.UPDATE_DISABLED
	if viewport.render_target_update_mode != mode:
		viewport.render_target_update_mode = mode
	turn = fmod(turn + TURN_SPEED * delta, TAU)
	drawer.call("set_card_turn", turn)
	var height := float(drawer.call("get_card_info").get("height", 0.0))
	if height > 20.0 and absf(height - framed_height) > 2.0:
		_frame(height)


func info_text() -> String:
	return "card: %s; camera %s, viewport %s, world %s" % [str(drawer.call("get_card_info")), str(camera.global_transform), str(viewport.size), str(viewport.world_3d.scenario)]
