extends Node
# er_layer.gd - figures posed by the game's own skeletons, drawn by Godot in scene mode (look.er_models).
#
# The game decides everything: where a character stands, how it is turned, every joint of every pose comes from the
# game's animation code through the library (rtag_skeletons_get: RtaMachine.get_skeletons; tools/godot/lib/skeleton_export.h).
# Godot only draws.  Per frame, before the drawer takes the frame:
#   - the local player's figure is found: the skeleton whose root is nearest the view's player position (all objects
#     posed by the same animation state are one figure: body, head, what it wears), and the rigid models in its hands;
#   - with er_models = on or self, those objects are left out of the drawer's frame (RtaDrawer.set_hidden_objects) and drawn
#     here instead, posed by the frame's joints:
#       self  the game's own bind-pose mesh (the packets' sources: rest-pose model space, joints, weights), skinned by a
#             Godot skeleton made from the pose stream - the check that the stream is what the game drew (er check);
#       on    the owner's own Elden Ring models (converted locally into local/souls-ref/er-models: never in the
#             repository, never shared), retargeted: er_joint_map.cfg names which joint of the game's skeleton drives which
#             bone of theirs.  Without that folder nothing changes (the game's figure is drawn as always).
# Nothing here reaches the simulation: two copies in one room, one with the layer and one without, stay in step.
#
#   app er check FILE        from now on, every frame: the frame's skeletons into Skeleton3D nodes (rest from the bind
#                            pose, pose from the joint frames), the game's bind-pose sources skinned through them, compared
#                            with the corners the game's programs drew; one line per skeleton appended to FILE
#   app er check off
#   app er info              what is loaded, found and hidden
#   app er dump FILE         this frame's player skeleton (parents, bind pose, joint frames) as JSON
#   app er auto              what the bind-pose reader (_auto_table) makes of the player's skeleton

var main: Node
var view: Node                  # scene_view.gd
var machine: RtaMachine
var drawer: Object
var mode := "off"
var hidden_sent := false
var check_path := ""
var checks := 0
var data := {}                  # this frame's get_skeletons()
var player_skeleton := -1       # index into data.skeletons
var player_state := 0
var player_offset := -1           # the player's animation state, from its object (0x114 when found that way)
var hidden: PackedInt64Array = PackedInt64Array()
var held_objects: PackedInt64Array = PackedInt64Array()    # rigid models in the player's hands (weapons)
var held_pieces: PackedInt32Array = PackedInt32Array()
var hands_found: Array = []
var skel_nodes := {}            # key -> Skeleton3D (the check and "self")
var said := {}
# drawing (the world's scenario; RenderingServer objects)
var scenario: RID
var self_instance: RID
var self_skeleton: RID
var self_mesh: ArrayMesh
var self_material: StandardMaterial3D
# the Elden Ring figure
var er_dir := ""
var er_loaded := false
var er_failed := ""
var er_skeleton: Skeleton3D     # the figure's skeleton (from its glTF), rest pose = the model's bind pose
var er_meshes: Array = []       # [{mesh: Mesh, skin: Skin, instance: RID, skeleton: RID, binds: PackedInt32Array}]
var er_weapons: Array = []      # [{mesh: Mesh, instance: RID, bone: int, hand: String, local: Transform3D}]
var er_order: PackedInt32Array = PackedInt32Array()   # bones, parents first
var er_map: Array = []          # [{er: int, game: int, game_aim: int, er_aim: int, align: Basis}]
var er_by_bone := {}            # er bone -> entry of er_map
var er_axes := Basis()          # the model's space -> the game's model space (rotation only)
var er_scale := 1.0             # metres of the model -> units of the game
var er_aligned_for := -1        # joint count the alignment was made for
var er_globals: Array = []      # this frame's bone globals (world)
var er_set_loaded := ""
# a light of the figure's own where the scene has none of Godot's (the game's overhead view: its colours are lit by the game
# itself; a figure of ours would be black): a key light from above the camera and a fill, on our figure only (layer 20)
const OWN_LAYER := 1 << 19
var own_lights: Array = []          # [light RID, instance RID]
var er_root: Node


func _ready() -> void:
	machine = main.machine
	drawer = main.drawer


func release() -> void:
	for pair in own_lights:
		RenderingServer.free_rid(pair[1])
		RenderingServer.free_rid(pair[0])
	own_lights.clear()
	for rid in [self_instance, self_skeleton]:
		if rid.is_valid():
			RenderingServer.free_rid(rid)
	self_instance = RID()
	self_skeleton = RID()
	for m in er_meshes:
		for key in ["instance", "skeleton"]:
			if (m[key] as RID).is_valid():
				RenderingServer.free_rid(m[key])
	for w in er_weapons:
		if (w.instance as RID).is_valid():
			RenderingServer.free_rid(w.instance)
	er_meshes.clear()
	er_weapons.clear()


func command(w: PackedStringArray) -> void:
	if w.size() >= 3 and w[1] == "check":
		check_path = "" if w[2] == "off" else w[2]
	elif w.size() >= 2 and w[1] == "info":
		print("[blank %d] rta_godot: er: %s" % [main.blanks, info_text()])
	elif w.size() >= 3 and w[1] == "dump":
		_dump(w[2])
	elif w.size() >= 2 and w[1] == "auto":
		# what the bind-pose reader makes of the player's skeleton (against a [jointsN] row of the map, if there is one)
		print("[blank %d] rta_godot: er auto: %s" % [main.blanks, str(_auto_table(_player())) if not _player().is_empty() else "no player skeleton"])


func info_text() -> String:
	return "mode %s, models %s (%s), player skeleton %d (state %x at +0x%x of the player, %d joints), %d objects hidden, %d held, %d checks" % [mode,
		"loaded" if er_loaded else "not loaded", er_dir if er_failed == "" else er_failed, player_skeleton, player_state, player_offset,
		int(_player().get("joint_count", 0)), hidden.size(), held_objects.size(), checks]


func _player() -> Dictionary:
	if player_skeleton < 0:
		return {}
	return data.skeletons[player_skeleton]


# ---------------------------------------------------------------------------------------------------------------------
# Before the drawer takes the frame: find the player's figure; leave it out when it is drawn here.
func before_frame(wanted: String) -> void:
	mode = wanted
	var want_set := String(view.look.get("er_set", "default")) if view != null else "default"
	if want_set != er_set_loaded and (er_loaded or er_failed != ""):
		_unload()                               # another outfit asked for: loaded the next time it is drawn
	if mode == "on" and not er_loaded and er_failed == "":
		_load_er()
	var drawing := mode == "self" or (mode == "on" and er_loaded)
	if not drawing and check_path == "":
		if hidden_sent:
			drawer.call("set_hidden_objects", PackedInt64Array())
			hidden_sent = false
		_hide_drawn()
		return
	data = machine.get_skeletons(mode == "self" or check_path != "")
	_find_player()
	if check_path != "":
		_check()
	if drawing and player_skeleton >= 0:
		var all := hidden.duplicate()
		all.append_array(held_objects)
		drawer.call("set_hidden_objects", all)
		hidden_sent = true
	elif hidden_sent:
		drawer.call("set_hidden_objects", PackedInt64Array())
		hidden_sent = false


func _find_player() -> void:
	player_skeleton = -1
	player_state = 0
	hidden = PackedInt64Array()
	held_objects = PackedInt64Array()
	held_pieces = PackedInt32Array()
	var skeletons: Array = data.get("skeletons", [])
	if skeletons.is_empty():
		return
	# the local player: the skeleton whose animation state lies in the player's own object (the controls know its address:
	# a creature's state is at +0x114, animation.md 2.1); without that, the one whose root is nearest the view's player
	var hud: Dictionary = machine.get_controls_hud()
	var me := int(hud.get("player", 0))
	var v: Dictionary = machine.get_view()
	var feet: Vector3 = v.get("player", Vector3.ZERO)
	var have := bool(v.get("have_player", false))
	var best := 1e9
	for k in skeletons.size():
		var s: Dictionary = skeletons[k]
		if int(s.joint_count) < 30:          # a person (the players' skeletons have 37 to 64 joints)
			continue
		var offset := int(s.state) - me
		var d: float
		if me != 0 and offset >= 0 and offset < 0x800:
			d = -1e6 + offset
		else:
			var root: Vector3 = (s.joints[0] as Transform3D).origin
			d = root.distance_to(feet) if have else float(k) + 1e5
		if d < best:
			best = d
			player_skeleton = k
	player_offset = int(skeletons[player_skeleton].state) - me if player_skeleton >= 0 and me != 0 else -1
	if player_skeleton < 0:
		return
	player_state = int(skeletons[player_skeleton].state)
	var objects := {}
	for k in skeletons.size():
		if int(skeletons[k].state) == player_state:
			objects[int(skeletons[k].object)] = true
	for o in objects:
		hidden.append(o)
	# what the player holds: rigid models whose own matrix is at one of the hands (the game hangs a weapon on an attach
	# point of the hand's joint: model_getAttachPoint): its own origin within 20 units of the hand (a spear's is at its butt)
	var p: Dictionary = skeletons[player_skeleton]
	# a hand: a joint with three or more children (the fingers) low and to the side in the bind pose - found from the
	# skeleton itself
	var children := {}
	for j in p.joint_count:
		var parent := int(p.parent[j])
		if parent >= 0:
			children[parent] = int(children.get(parent, 0)) + 1
	var hand_points: Array = []
	for j in children:
		if int(children[j]) >= 3 and (p.bind[j] as Vector3).z < (p.bind[0] as Vector3).z + 8.0 and absf((p.bind[j] as Vector3).x) > 10.0:
			hand_points.append((p.joints[j] as Transform3D).origin)
	hands_found = hand_points
	var kinds: PackedInt32Array = data.piece_kind
	var skel_of: PackedInt32Array = data.piece_skeleton
	var objs: PackedInt32Array = data.piece_object
	var slot0: Array = data.piece_slot0
	var held := {}
	for i in kinds.size():
		if kinds[i] != 2 or skel_of[i] >= 0 or objects.has(objs[i]):
			continue
		var at: Vector3 = (slot0[i] as Transform3D).origin
		for h in hand_points:
			if at.distance_to(h) < 20.0:
				held[objs[i]] = true
				held_pieces.append(i)
	for o in held:
		held_objects.append(o)


# ---------------------------------------------------------------------------------------------------------------------
# The pose stream into a Skeleton3D: rest = the bind pose (every joint's axes along the model's; its origin bind[j]),
# pose = the joint frames the game posed (global; made local to the parent here).
func _skeleton3d(key: String, s: Dictionary) -> Skeleton3D:
	var n := int(s.joint_count)
	var sk: Skeleton3D = skel_nodes.get(key)
	if sk == null or sk.get_bone_count() != n:
		if sk != null:
			sk.queue_free()
		sk = Skeleton3D.new()
		add_child(sk)
		for j in n:
			sk.add_bone("joint%d" % j)
		for j in n:
			var parent := int(s.parent[j])
			sk.set_bone_parent(j, parent)
			var rest_at: Vector3 = s.bind[j] - (s.bind[parent] if parent >= 0 else Vector3.ZERO)
			sk.set_bone_rest(j, Transform3D(Basis(), rest_at))
		skel_nodes[key] = sk
	var joints: Array = s.joints
	for j in n:
		var g: Transform3D = joints[j]
		var parent := int(s.parent[j])
		var local: Transform3D = g if parent < 0 else (joints[parent] as Transform3D).affine_inverse() * g
		sk.set_bone_pose_position(j, local.origin)
		sk.set_bone_pose_rotation(j, local.basis.get_rotation_quaternion())
		sk.set_bone_pose_scale(j, local.basis.get_scale())
	sk.force_update_all_bone_transforms()
	return sk


# skinning matrices of a Skeleton3D made by _skeleton3d: global pose x inverse rest (the rest's global is T(bind[j]))
func _skin_of(sk: Skeleton3D, s: Dictionary) -> Array:
	var out: Array = []
	for j in int(s.joint_count):
		out.append(sk.get_bone_global_pose(j) * Transform3D(Basis(), -(s.bind[j] as Vector3)))
	return out


func _check() -> void:
	if not data.has("full_position"):
		return
	var tick := machine.get_sim_tick()
	var skeletons: Array = data.skeletons
	var lines := PackedStringArray()
	var src_pos: PackedVector3Array = data.source_position
	var src_joints: PackedInt32Array = data.source_joints
	var src_weights: PackedFloat32Array = data.source_weights
	var full_pos: PackedVector3Array = data.full_position
	var full_src: PackedInt32Array = data.full_source
	var piece_skel: PackedInt32Array = data.piece_skeleton
	var first: PackedInt32Array = data.piece_full_first
	var count: PackedInt32Array = data.piece_full_count
	var sfirst: PackedInt32Array = data.piece_source_first
	for k in skeletons.size():
		var s: Dictionary = skeletons[k]
		if int(s.joint_count) < 1:
			continue
		var sk := _skeleton3d("check-%x-%d" % [int(s.state), int(s.joint_count)], s)
		var m := _skin_of(sk, s)
		var corners := 0
		var worst := 0.0
		var total := 0.0
		for i in piece_skel.size():
			if piece_skel[i] != k:
				continue
			for c in range(first[i], first[i] + count[i]):
				var v := sfirst[i] + full_src[c]
				var p := src_pos[v]
				var out := Vector3.ZERO
				for q in 4:
					var w := src_weights[v * 4 + q]
					if w > 0.0:
						out += w * ((m[src_joints[v * 4 + q]] as Transform3D) * p)
				var e := out.distance_to(full_pos[c])
				worst = maxf(worst, e)
				total += e
				corners += 1
		var root: Vector3 = (s.joints[0] as Transform3D).origin
		lines.append("tick %d skeleton %d state %x clip %x joints %d player %d corners %d skeleton3d_max %.5f mean %.6f root %.1f %.1f %.1f" % [tick, k,
			int(s.state), int(s.clip), int(s.joint_count), 1 if k == player_skeleton else 0, corners, worst, total / maxf(1.0, float(corners)), root.x, root.y, root.z])
	checks += 1
	var file := FileAccess.open(check_path, FileAccess.READ_WRITE if FileAccess.file_exists(check_path) else FileAccess.WRITE)
	if file != null:
		file.seek_end()
		for line in lines:
			file.store_line(line)
		file.close()


func _dump(path: String) -> void:
	var p := _player()
	if p.is_empty():
		return
	var out := {"tick": machine.get_sim_tick(), "state": p.state, "clip": p.clip, "parent": Array(p.parent), "bind": [], "joints": []}
	for j in int(p.joint_count):
		var b: Vector3 = p.bind[j]
		out.bind.append([b.x, b.y, b.z])
		var t: Transform3D = p.joints[j]
		out.joints.append([t.basis.x.x, t.basis.y.x, t.basis.z.x, t.origin.x, t.basis.x.y, t.basis.y.y, t.basis.z.y, t.origin.y, t.basis.x.z, t.basis.y.z, t.basis.z.z, t.origin.z])
	# the scene's model pieces near the player: what could be in its hands
	out["near"] = []
	var root: Vector3 = (p.joints[0] as Transform3D).origin
	var kinds: PackedInt32Array = data.piece_kind
	for i in kinds.size():
		if kinds[i] != 2:
			continue
		var at: Vector3 = (data.piece_slot0[i] as Transform3D).origin
		if at.distance_to(root) > 80.0:
			continue
		var sk := int(data.piece_skeleton[i])
		out.near.append({"piece": i, "object": int(data.piece_object[i]), "skeleton": sk, "state": int(data.skeletons[sk].state) if sk >= 0 else 0,
			"flags": int(data.piece_flags[i]), "at": [at.x, at.y, at.z], "hidden": hidden.has(int(data.piece_object[i])) or held_objects.has(int(data.piece_object[i]))})
	out["hands"] = []
	for h in hands_found:
		out.hands.append([h.x, h.y, h.z])
	if er_loaded and er_globals.size() == er_skeleton.get_bone_count():
		out["er_scale"] = er_scale
		out["er_axes"] = [er_axes.x.x, er_axes.y.x, er_axes.z.x, er_axes.x.y, er_axes.y.y, er_axes.z.y, er_axes.x.z, er_axes.y.z, er_axes.z.z]
		out["er_bones"] = []
		for b in er_skeleton.get_bone_count():
			var g: Transform3D = er_globals[b]
			var r: Transform3D = er_skeleton.get_bone_global_rest(b)
			out.er_bones.append({"name": er_skeleton.get_bone_name(b), "parent": er_skeleton.get_bone_parent(b), "mapped": er_by_bone.has(b),
				"global": [g.basis.x.x, g.basis.y.x, g.basis.z.x, g.origin.x, g.basis.x.y, g.basis.y.y, g.basis.z.y, g.origin.y, g.basis.x.z, g.basis.y.z, g.basis.z.z, g.origin.z],
				"rest": [r.basis.x.x, r.basis.y.x, r.basis.z.x, r.origin.x, r.basis.x.y, r.basis.y.y, r.basis.z.y, r.origin.y, r.basis.x.z, r.basis.y.z, r.basis.z.z, r.origin.z]})
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(out))
		file.close()


func _hide_drawn() -> void:
	if self_instance.is_valid():
		RenderingServer.instance_set_visible(self_instance, false)
	for m in er_meshes:
		RenderingServer.instance_set_visible(m.instance, false)
	for w in er_weapons:
		RenderingServer.instance_set_visible(w.instance, false)


# ---------------------------------------------------------------------------------------------------------------------
# After the drawer has taken the frame: draw the figure.
func frame(to_scenario: RID) -> void:
	if to_scenario != scenario:
		release()
		scenario = to_scenario
	var drawing := (mode == "self" or (mode == "on" and er_loaded)) and player_skeleton >= 0
	if not drawing:
		_hide_drawn()
		for pair in own_lights:
			RenderingServer.instance_set_visible(pair[1], false)
		return
	_own_light()
	if mode == "self":
		for m in er_meshes:
			RenderingServer.instance_set_visible(m.instance, false)
		for w in er_weapons:
			RenderingServer.instance_set_visible(w.instance, false)
		_draw_self()
	else:
		if self_instance.is_valid():
			RenderingServer.instance_set_visible(self_instance, false)
		_draw_er()


# the game's own bind-pose mesh of the player's figure, skinned by a Skeleton3D made from the pose stream
func _draw_self() -> void:
	var p := _player()
	if not data.has("full_position"):
		return
	var sk := _skeleton3d("self", p)
	var m := _skin_of(sk, p)
	var n := int(p.joint_count)
	if not self_skeleton.is_valid():
		self_skeleton = RenderingServer.skeleton_create()
	RenderingServer.skeleton_allocate_data(self_skeleton, n)
	for j in n:
		RenderingServer.skeleton_bone_set_transform(self_skeleton, j, m[j])
	var positions := PackedVector3Array()
	var normals := PackedVector3Array()
	var colours := PackedColorArray()
	var bones := PackedInt32Array()
	var weights := PackedFloat32Array()
	var src_pos: PackedVector3Array = data.source_position
	var src_nrm: PackedVector3Array = data.source_normal
	var src_joints: PackedInt32Array = data.source_joints
	var src_weights: PackedFloat32Array = data.source_weights
	var full_src: PackedInt32Array = data.full_source
	var full_colour: PackedColorArray = data.full_colour
	var piece_skel: PackedInt32Array = data.piece_skeleton
	var first: PackedInt32Array = data.piece_full_first
	var count: PackedInt32Array = data.piece_full_count
	var sfirst: PackedInt32Array = data.piece_source_first
	var skeletons: Array = data.skeletons
	for i in piece_skel.size():
		if piece_skel[i] < 0 or int(skeletons[piece_skel[i]].state) != player_state:
			continue
		if (int(data.piece_flags[i]) & 2) != 0:       # the environment-map pass of a two-pass packet: the second pass has it
			continue
		for c in range(first[i], first[i] + count[i]):
			var v := sfirst[i] + full_src[c]
			positions.append(src_pos[v])
			normals.append(src_nrm[v])
			var col := full_colour[c]
			colours.append(Color(minf(col.r, 1.0) * 0.6, minf(col.g, 1.0) * 0.6, minf(col.b, 1.0) * 0.6, 1.0))
			for q in 4:
				bones.append(src_joints[v * 4 + q])
				weights.append(src_weights[v * 4 + q])
	if positions.is_empty():
		return
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = positions
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_COLOR] = colours
	arrays[Mesh.ARRAY_BONES] = bones
	arrays[Mesh.ARRAY_WEIGHTS] = weights
	if self_mesh == null:
		self_mesh = ArrayMesh.new()
		self_material = StandardMaterial3D.new()
		self_material.vertex_color_use_as_albedo = true
		self_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		self_material.cull_mode = BaseMaterial3D.CULL_DISABLED
		self_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		self_material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_ALWAYS
	self_mesh.clear_surfaces()
	self_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	self_mesh.surface_set_material(0, self_material)
	if not self_instance.is_valid():
		self_instance = RenderingServer.instance_create2(self_mesh.get_rid(), scenario)
		RenderingServer.instance_attach_skeleton(self_instance, self_skeleton)
	_place(self_instance, [])
	RenderingServer.instance_set_visible(self_instance, true)
	var root: Vector3 = (p.joints[0] as Transform3D).origin
	RenderingServer.instance_set_custom_aabb(self_instance, AABB(root - Vector3(120, 120, 120), Vector3(240, 240, 240)))


# ---------------------------------------------------------------------------------------------------------------------
# The Elden Ring figure (local files only).
func _unload() -> void:
	release()
	if er_root != null:
		er_root.queue_free()
	er_root = null
	er_skeleton = null
	er_loaded = false
	er_failed = ""
	er_set_loaded = ""
	er_aligned_for = -1
	er_map.clear()
	er_by_bone.clear()
	_depths.clear()


func _er_folder() -> String:
	if OS.has_environment("RTA_ER_MODELS"):
		return OS.get_environment("RTA_ER_MODELS")
	# beside the staged project: <root>/local/godot-*/project -> <root>/local/souls-ref/er-models
	return ProjectSettings.globalize_path("res://").path_join("../../souls-ref/er-models").simplify_path()


func _load_er() -> void:
	var folder := _er_folder()
	var set_name := String(view.look.get("er_set", "default")) if view != null and view.look.has("er_set") else "default"
	er_set_loaded = set_name
	er_dir = folder.path_join(set_name)
	var figure_path := er_dir.path_join("figure.glb")
	if not FileAccess.file_exists(figure_path):
		er_failed = "no " + figure_path
		return
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if doc.append_from_file(figure_path, state) != OK:
		er_failed = "could not read " + figure_path
		return
	var root := doc.generate_scene(state)
	er_skeleton = null
	var instances: Array = []
	_collect(root, instances)
	if er_skeleton == null or instances.is_empty():
		er_failed = "no skinned figure in " + figure_path
		root.queue_free()
		return
	add_child(root)
	er_root = root
	(root as Node3D).visible = false
	for mi in instances:
		var inst: MeshInstance3D = mi
		var skin: Skin = inst.skin
		if skin == null or inst.mesh == null:
			continue
		var binds := PackedInt32Array()
		for b in skin.get_bind_count():
			var bone := skin.get_bind_bone(b)
			if bone < 0:
				bone = er_skeleton.find_bone(skin.get_bind_name(b))
			binds.append(bone)
		er_meshes.append({"mesh": inst.mesh, "skin": skin, "instance": RID(), "skeleton": RID(), "binds": binds, "materials": _in_order(inst.mesh)})
	# weapons: weapon-right.glb / weapon-left.glb, each rigid, its origin at the grip (the converter puts it there)
	for hand in ["right", "left"]:
		var path := er_dir.path_join("weapon-%s.glb" % hand)
		if not FileAccess.file_exists(path):
			continue
		var wdoc := GLTFDocument.new()
		var wstate := GLTFState.new()
		if wdoc.append_from_file(path, wstate) != OK:
			continue
		var wroot := wdoc.generate_scene(wstate)
		var found: Array = []
		_meshes(wroot, found)
		root.add_child(wroot)
		(wroot as Node3D).visible = false
		var bone := er_skeleton.find_bone("R_Weapon" if hand == "right" else "L_Weapon")
		if bone < 0:
			bone = er_skeleton.find_bone("R_Hand" if hand == "right" else "L_Hand")
		for f in found:
			er_weapons.append({"mesh": (f as MeshInstance3D).mesh, "instance": RID(), "bone": bone, "hand": hand, "materials": _in_order((f as MeshInstance3D).mesh),
				"local": (f as MeshInstance3D).global_transform if (f as Node3D).is_inside_tree() else Transform3D()})
	# the bones, parents before children
	er_order = PackedInt32Array()
	var placed := {}
	while er_order.size() < er_skeleton.get_bone_count():
		var progressed := false
		for b in er_skeleton.get_bone_count():
			if placed.has(b):
				continue
			var parent := er_skeleton.get_bone_parent(b)
			if parent < 0 or placed.has(parent):
				er_order.append(b)
				placed[b] = true
				progressed = true
		if not progressed:
			break
	er_loaded = true
	print("rta_godot: er: loaded %s: %d bones, %d skinned meshes, %d weapons" % [er_dir, er_skeleton.get_bone_count(), er_meshes.size(), er_weapons.size()])


# The world's draws are all in Godot's transparent pass, in the list's order (RtaDrawer::place: a sorting offset each),
# the game's clearing of the frame among them: a figure of ours goes there too, at the place of the draws it stands in for
# (get_scene_info().hidden_order), depth tested and written like them.
func _in_order(mesh: Mesh) -> Array:
	var out: Array = []
	for i in mesh.get_surface_count():
		var m := mesh.surface_get_material(i)
		var copy: StandardMaterial3D = (m.duplicate() if m is StandardMaterial3D else StandardMaterial3D.new())
		copy.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS if copy.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR else BaseMaterial3D.TRANSPARENCY_ALPHA
		copy.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_ALWAYS
		copy.cull_mode = BaseMaterial3D.CULL_DISABLED
		out.append(copy)
	return out


func _own_light() -> void:
	var lit := bool(view.in_force.get("sun", false)) or bool(view.in_force.get("lamp", false)) or bool(view.in_force.get("lights", false))
	if own_lights.is_empty():
		for k in 2:
			var light := RenderingServer.directional_light_create()
			RenderingServer.light_set_param(light, RenderingServer.LIGHT_PARAM_ENERGY, 1.15 if k == 0 else 0.45)
			RenderingServer.light_set_cull_mask(light, OWN_LAYER)
			var inst := RenderingServer.instance_create2(light, scenario)
			own_lights.append([light, inst])
	var cam: Transform3D = drawer.call("get_scene_info").get("camera", Transform3D())
	for k in own_lights.size():
		# key: from over the camera's shoulder, down at 50 degrees; fill: from the other side, low
		var dir := (-cam.basis.z).normalized()
		var flat := Vector3(dir.x, dir.y, 0.0).normalized() if Vector3(dir.x, dir.y, 0.0).length() > 0.01 else Vector3(1, 0, 0)
		var side := flat.cross(Vector3(0, 0, 1)).normalized()
		var toward := (flat + side * (0.6 if k == 0 else -0.8) + Vector3(0, 0, -1.2 if k == 0 else -0.3)).normalized()
		RenderingServer.instance_set_transform(own_lights[k][1], Transform3D(Basis.looking_at(toward, Vector3(0, 0, 1)), Vector3.ZERO))
		RenderingServer.instance_set_visible(own_lights[k][1], not lit)


func _place(instance: RID, materials: Array) -> void:
	RenderingServer.instance_set_layer_mask(instance, 1 | OWN_LAYER)
	for i in materials.size():
		RenderingServer.instance_set_surface_override_material(instance, i, (materials[i] as Material).get_rid())
	var order := float(drawer.call("get_scene_info").get("hidden_order", -1.0))
	RenderingServer.instance_set_pivot_data(instance, order + 0.5 if order >= 0.0 else 1.0e6, false)


func _collect(node: Node, out: Array) -> void:
	if node is Skeleton3D and er_skeleton == null:
		er_skeleton = node
	if node is MeshInstance3D and (node as MeshInstance3D).skin != null:
		out.append(node)
	for c in node.get_children():
		_collect(c, out)


func _meshes(node: Node, out: Array) -> void:
	if node is MeshInstance3D:
		out.append(node)
	for c in node.get_children():
		_meshes(c, out)


# The joint map (er_joint_map.cfg) and, once per skeleton, how the two bind poses sit against each other.
func _align(p: Dictionary) -> bool:
	if er_aligned_for == int(p.joint_count) and not er_map.is_empty():
		return true
	er_map.clear()
	er_by_bone.clear()
	var cfg := ConfigFile.new()
	if cfg.load("res://er_joint_map.cfg") != OK:
		er_failed = "no er_joint_map.cfg"
		return false
	var section := "joints%d" % int(p.joint_count)
	var table := {}
	if cfg.has_section(section):
		for key in cfg.get_section_keys(section):
			table[key] = cfg.get_value(section, key)
	else:
		# no row of our own for this skeleton: the joints told apart by where they sit in its bind pose (_auto_table),
		# with the bone names of the map's [auto] section
		var found := _auto_table(p)
		if found.is_empty() or not cfg.has_section("auto"):
			if not said.has(section):
				said[section] = true
				print("rta_godot: er: the joint map has no [%s], and the skeleton could not be read by itself" % section)
			return false
		for key in found:
			if key.begins_with("frame_"):
				table[key] = found[key]
			elif cfg.has_section_key("auto", key):
				var names: Array = cfg.get_value("auto", key)
				table[key] = [found[key][0], found[key][1], names[0], names[1]]
		if not said.has(section):
			said[section] = true
			var line := PackedStringArray()
			for key in table:
				line.append("%s = %s" % [key, str(table[key])])
			print("rta_godot: er: [%s] read from the skeleton itself: %s" % [section, ", ".join(line)])
	var n := int(p.joint_count)
	var game_rest := func(j: int) -> Vector3: return p.bind[j]
	var er_rest := func(b: int) -> Vector3: return er_skeleton.get_bone_global_rest(b).origin
	# the two figures' up, forward and left, from their own bind poses (named in the map's [frame] section)
	var f := "frame"
	var g_head := int(table.get("frame_head", 16))
	var g_feet: Array = table.get("frame_toes", [6, 11])
	var g_left := int(table.get("frame_left", 2))
	var g_right := int(table.get("frame_right", 7))
	var e_head := er_skeleton.find_bone(String(cfg.get_value(f, "head", "Head")))
	var e_toes: Array = cfg.get_value(f, "toes", ["L_Toe0", "R_Toe0"])
	var e_left := er_skeleton.find_bone(String(cfg.get_value(f, "left", "L_Thigh")))
	var e_right := er_skeleton.find_bone(String(cfg.get_value(f, "right", "R_Thigh")))
	var e_feet := [er_skeleton.find_bone(String(e_toes[0])), er_skeleton.find_bone(String(e_toes[1]))]
	if e_head < 0 or e_left < 0 or e_right < 0 or e_feet[0] < 0 or e_feet[1] < 0:
		er_failed = "the model's skeleton lacks the bones of the joint map's [frame]"
		return false
	var g_ground: Vector3 = (game_rest.call(int(g_feet[0])) + game_rest.call(int(g_feet[1]))) * 0.5
	var e_ground: Vector3 = (er_rest.call(e_feet[0]) + er_rest.call(e_feet[1])) * 0.5
	var g_up: Vector3 = (game_rest.call(g_head) - g_ground)
	var e_up: Vector3 = (er_rest.call(e_head) - e_ground)
	var g_side: Vector3 = (game_rest.call(g_left) - game_rest.call(g_right))
	var e_side: Vector3 = (er_rest.call(e_left) - er_rest.call(e_right))
	er_scale = g_up.length() / maxf(e_up.length(), 1e-4)
	var gb := _frame_basis(g_up, g_side)
	var eb := _frame_basis(e_up, e_side)
	er_axes = gb * eb.inverse()
	for key in table:
		if key.begins_with("frame_"):
			continue
		var v: Array = table[key]
		# key = our own name; v = [joint of the game, the joint its aim is taken toward, bone of the model, its aim bone]
		var gj := int(v[0])
		var ga := int(v[1])
		var eb_bone := er_skeleton.find_bone(String(v[2]))
		var ea := er_skeleton.find_bone(String(v[3])) if String(v[3]) != "" else -1
		if gj < 0 or gj >= n or eb_bone < 0:
			continue
		# align: turns the model's bone (its rest, carried into the game's model space) so that its aim lies along the
		# game's joint's aim in the bind pose; the game's bind pose has every joint's axes along the model's
		var align := Basis()
		if ga >= 0 and ga < n and ea >= 0:
			var from: Vector3 = er_axes * (er_rest.call(ea) - er_rest.call(eb_bone))
			var to: Vector3 = game_rest.call(ga) - game_rest.call(gj)
			if from.length() > 1e-5 and to.length() > 1e-5:
				align = _arc(from.normalized(), to.normalized())
		var entry := {"name": key, "er": eb_bone, "game": gj, "align": align}
		er_map.append(entry)
		er_by_bone[eb_bone] = entry
	er_aligned_for = n
	print("rta_godot: er: %d joints mapped for a %d-joint skeleton; %.2f units a metre" % [er_map.size(), n, er_scale])
	return true


# The game's person skeletons told apart by their bind pose (z up, the figure's left at +x): the pelvis is the joint two
# of whose branches go down to the ground, one on either side; the spine goes up from it to the joint the arms leave,
# sideways; the head is above that.  Returns our names -> [joint, aim joint], and frame_head / frame_toes / frame_left /
# frame_right; {} when the skeleton is not of that build.
func _auto_table(p: Dictionary) -> Dictionary:
	var n := int(p.joint_count)
	var bind: PackedVector3Array = p.bind
	var parent: PackedInt32Array = p.parent
	var kids := []
	kids.resize(n)
	for j in n:
		kids[j] = []
	for j in n:
		if parent[j] >= 0:
			kids[parent[j]].append(j)
	var lo := PackedFloat32Array(); var hi := PackedFloat32Array(); var side := PackedFloat32Array()
	lo.resize(n); hi.resize(n); side.resize(n)
	var top := -1e9; var bottom := 1e9
	for j in range(n - 1, -1, -1):           # parents come before their children in the game's order
		lo[j] = bind[j].z; hi[j] = bind[j].z; side[j] = absf(bind[j].x)
		for c in kids[j]:
			lo[j] = minf(lo[j], lo[c]); hi[j] = maxf(hi[j], hi[c]); side[j] = maxf(side[j], side[c])
		top = maxf(top, bind[j].z); bottom = minf(bottom, bind[j].z)
	var h := top - bottom
	if h < 1.0:
		return {}
	var follow := func(start: int, key: Callable) -> Array:
		var chain := [start]
		var j := start
		while not (kids[j] as Array).is_empty():
			var best: int = kids[j][0]
			for c in kids[j]:
				if key.call(c) > key.call(best):
					best = c
			j = best
			chain.append(j)
		return chain
	var pelvis := -1; var left_hip := -1; var right_hip := -1
	for j in n:
		var l := -1; var r := -1
		for c in kids[j]:
			if lo[c] < bind[j].z - 0.3 * h:
				if bind[c].x > 0.02 * h and l < 0: l = c
				elif bind[c].x < -0.02 * h and r < 0: r = c
		if l >= 0 and r >= 0:
			pelvis = j; left_hip = l; right_hip = r
			break
	if pelvis < 0:
		return {}
	var down := func(c: int) -> float: return -lo[c]
	var up := func(c: int) -> float: return hi[c] - side[c] * 0.5
	var out := {}
	var leg := func(hip: int, prefix: String) -> Array:
		var chain: Array = follow.call(hip, down)
		if chain.size() < 3:
			return []
		var toe: int = chain[-1]
		var foot: int = chain[-2]
		var knee: int = chain[1]
		var mid := (bind[hip].z + bind[foot].z) * 0.5
		for k in range(1, chain.size() - 2):
			if absf(bind[chain[k]].z - mid) < absf(bind[knee].z - mid):
				knee = chain[k]
		out[prefix + "_thigh"] = [hip, knee]
		out[prefix + "_calf"] = [knee, foot]
		out[prefix + "_foot"] = [foot, toe]
		return chain
	var lchain: Array = leg.call(left_hip, "left")
	var rchain: Array = leg.call(right_hip, "right")
	if lchain.is_empty() or rchain.is_empty():
		return {}
	# the spine: up from the pelvis to the joint the arms leave
	var spine_start := -1
	for c in kids[pelvis]:
		if c != left_hip and c != right_hip and (spine_start < 0 or hi[c] > hi[spine_start]):
			spine_start = c
	if spine_start < 0:
		return {}
	var spine := []
	var j := spine_start
	var chest := -1
	while true:
		spine.append(j)
		var arms := 0
		for c in kids[j]:
			if side[c] > 0.18 * h and absf(bind[c].x) < side[c]:
				arms += 1
		if arms >= 2:
			chest = j
			break
		var nxt := -1
		for c in kids[j]:
			if nxt < 0 or up.call(c) > up.call(nxt):
				nxt = c
		if nxt < 0:
			break
		j = nxt
	if chest < 0 or spine.size() < 2:
		return {}
	var head := -1
	for c in kids[chest]:
		if side[c] < 0.18 * h and (head < 0 or hi[c] > hi[head]):
			head = c
	if head < 0:
		return {}
	var hchain: Array = follow.call(head, func(c: int) -> float: return hi[c])
	var head_joint: int = head
	for k in hchain:
		if (kids[k] as Array).size() >= 2 or k == hchain[-1]:
			head_joint = k
			break
	var s_count := spine.size()
	out["pelvis"] = [pelvis, spine[0]]
	out["spine"] = [spine[0], spine[mini(1, s_count - 1)]]
	if s_count >= 3:
		out["chest"] = [spine[1], spine[2]]
	if s_count >= 4:
		out["upper_chest"] = [spine[s_count - 2], spine[s_count - 1]]
	out["neck"] = [chest, head_joint]
	out["head"] = [head_joint, -1]
	for c in kids[chest]:
		if side[c] <= 0.18 * h:
			continue
		var prefix := "left" if bind[c].x > 0.0 else "right"
		var arm: Array = follow.call(c, func(q: int) -> float: return side[q] + (0.0 if (kids[q] as Array).is_empty() else 0.001))
		if arm.size() < 4:
			continue
		var hand: int = arm[-1]
		for k in arm:
			if (kids[k] as Array).size() >= 2:
				hand = k
				break
		var at: int = arm.find(hand)
		if at < 3:
			continue
		var finger: int = hand
		for q in kids[hand]:
			if finger == hand or bind[q].distance_to(bind[hand]) > bind[finger].distance_to(bind[hand]):
				finger = q
		out[prefix + "_clavicle"] = [arm[0], arm[1]]
		out[prefix + "_upper_arm"] = [arm[1], arm[at - 1]]
		out[prefix + "_forearm"] = [arm[at - 1], hand]
		out[prefix + "_hand"] = [hand, finger]
	out["frame_head"] = head_joint
	out["frame_toes"] = [lchain[-1], rchain[-1]]
	out["frame_left"] = left_hip
	out["frame_right"] = right_hip
	return out


func _frame_basis(up: Vector3, side: Vector3) -> Basis:
	var z := up.normalized()
	var x := (side - z * side.dot(z)).normalized()
	var y := z.cross(x)
	return Basis(x, y, z)


func _arc(a: Vector3, b: Vector3) -> Basis:
	var axis := a.cross(b)
	var s := axis.length()
	var c := clampf(a.dot(b), -1.0, 1.0)
	if s < 1e-6:
		if c > 0.0:
			return Basis()
		var any := a.cross(Vector3.RIGHT) if absf(a.x) < 0.9 else a.cross(Vector3.UP)
		return Basis(any.normalized(), PI)
	return Basis(axis / s, atan2(s, c))


func _draw_er() -> void:
	var p := _player()
	if not _align(p):
		return
	var joints: Array = p.joints
	var k := er_scale * float(p.scale)
	var count := er_skeleton.get_bone_count()
	er_globals.resize(count)
	# a mapped bone: the game's joint's turn since its bind pose (its axes in the bind pose are the model's), applied to
	# the model's bone as it rests, carried into the game's model space and aligned; its place: from its parent, by the
	# model's own proportions (scaled to the game's figure) - the pelvis's from the game's
	var root_entry: Dictionary = {}
	for e in er_map:
		if root_entry.is_empty() or er_skeleton.get_bone_parent(int(e.er)) == -1 or _depth(int(e.er)) < _depth(int(root_entry.er)):
			root_entry = e
	var root_bone := int(root_entry.er)
	var turn := func(e: Dictionary) -> Basis:
		var g: Transform3D = joints[int(e.game)]
		var r := g.basis.orthonormalized()
		return (r * (e.align as Basis) * er_axes * er_skeleton.get_bone_global_rest(int(e.er)).basis.orthonormalized()).scaled(Vector3(k, k, k))
	var root_global := Transform3D(turn.call(root_entry), (joints[int(root_entry.game)] as Transform3D).origin)
	# the bones above the mapped root follow it rigidly (W = root's global x its rest's inverse)
	var root_rest := er_skeleton.get_bone_global_rest(root_bone)
	var above := root_global * Transform3D(root_rest.basis.scaled(Vector3(k, k, k)), root_rest.origin * k).affine_inverse()
	for b in er_order:
		var parent := er_skeleton.get_bone_parent(b)
		if b == root_bone:
			er_globals[b] = root_global
		elif parent < 0 or _is_under(root_bone, b):
			# the mapped root's ancestors (Master, the root motion bones) and other roots: carried rigidly with it
			var rest := er_skeleton.get_bone_global_rest(b)
			er_globals[b] = above * Transform3D(rest.basis.scaled(Vector3(k, k, k)), rest.origin * k)
		else:
			# from the parent by the model's own proportions; a mapped bone turned as its joint
			var from_parent: Transform3D = er_globals[parent] * er_skeleton.get_bone_rest(b)
			if er_by_bone.has(b):
				er_globals[b] = Transform3D(turn.call(er_by_bone[b]), from_parent.origin)
			else:
				er_globals[b] = from_parent
	for m in er_meshes:
		var binds: PackedInt32Array = m.binds
		var skin: Skin = m.skin
		if not (m.skeleton as RID).is_valid():
			m.skeleton = RenderingServer.skeleton_create()
			RenderingServer.skeleton_allocate_data(m.skeleton, binds.size())
			m.instance = RenderingServer.instance_create2((m.mesh as Mesh).get_rid(), scenario)
			RenderingServer.instance_attach_skeleton(m.instance, m.skeleton)
		for i in binds.size():
			var bone := binds[i]
			var g: Transform3D = er_globals[bone] if bone >= 0 else Transform3D()
			RenderingServer.skeleton_bone_set_transform(m.skeleton, i, g * skin.get_bind_pose(i))
		_place(m.instance, m.materials)
		RenderingServer.instance_set_visible(m.instance, true)
		var root: Vector3 = (joints[0] as Transform3D).origin
		RenderingServer.instance_set_custom_aabb(m.instance, AABB(root - Vector3(120, 120, 120), Vector3(240, 240, 240)))
	for w in er_weapons:
		if not (w.instance as RID).is_valid():
			w.instance = RenderingServer.instance_create2((w.mesh as Mesh).get_rid(), scenario)
		var bone := int(w.bone)
		if bone < 0:
			continue
		var g: Transform3D = er_globals[bone]
		RenderingServer.instance_set_transform(w.instance, g * (w.local as Transform3D))
		_place(w.instance, w.materials)
		RenderingServer.instance_set_visible(w.instance, true)


var _depths := {}
func _depth(b: int) -> int:
	if _depths.has(b):
		return _depths[b]
	var d := 0
	var p := er_skeleton.get_bone_parent(b)
	while p >= 0:
		d += 1
		p = er_skeleton.get_bone_parent(p)
	_depths[b] = d
	return d


func _is_under(b: int, root: int) -> bool:
	var p := b
	while p >= 0:
		if p == root:
			return true
		p = er_skeleton.get_bone_parent(p)
	return false
