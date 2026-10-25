extends Node
# er_layer.gd - figures posed by the game's own skeletons, drawn by Godot in scene mode (look.er_models).
#
# The game decides everything: where a character stands, how it is turned, every joint of every pose comes from the
# game's animation code through the library (rtag_skeletons_get: RtaMachine.get_skeletons; tools/godot/lib/skeleton_export.h).
# Godot only draws.  Per frame, before the drawer takes the frame:
#   - the players' figures are found: the library names every player of the game (slot, its creature, its animation
#     state, its character class and the class of the weapon in its hand - the Hardcore mode's classes, soulscombat.h);
#     a player's figure is every object posed by its animation state (body, head, what it wears), and the rigid models
#     at its hands are what it holds.  Every machine of a net game runs every player, so the other machines' players
#     are in the same stream as this one's;
#   - with er_models = on, those objects are left out of the drawer's frame (RtaDrawer.set_hidden_objects) and drawn here
#     instead: the owner's own Elden Ring models (converted locally into local/souls-ref/er-models: never in the
#     repository, never shared), retargeted: er_joint_map.cfg names which joint of the game's skeleton drives which bone
#     of theirs.  The outfit by the character's class (look.er_set = auto) or one named outfit for everyone; the weapon
#     in hand by its class (er-models/weapons/<class>.glb), its grip put where the game's own weapon is held, along the
#     game's weapon; capes, skirts and hair swing (springs of our own, presentation only).  Without the folder nothing
#     changes (the game's figures are drawn as always);
#   - with er_models = self, the local player's own bind-pose mesh (the packets' sources), skinned by a Godot skeleton
#     made from the pose stream - the check that the stream is what the game drew (er check).
# Nothing here reaches the simulation: two copies in one room, one with the layer and one without, stay in step.
#
#   app er check FILE        from now on, every frame: the frame's skeletons into Skeleton3D nodes (rest from the bind
#                            pose, pose from the joint frames), the game's bind-pose sources skinned through them, compared
#                            with the corners the game's programs drew; one line per skeleton appended to FILE
#   app er check off
#   app er info              what is loaded, found and hidden, per player
#   app er dump FILE         this frame's person skeletons (parents, bind pose, joint frames) and players as JSON
#   app er auto              what the bind-pose reader (_auto_table) makes of every person skeleton of the frame
#   app er catch N FILE      the first frame from now with an N-joint skeleton: `dump` to FILE (and its auto reading printed),
#                            and three pictures 20 frames apart (FILE without .json, -0..2.png)
#   app er cost              the layer's own time per frame (mean and worst, microseconds) since the last `cost`
#   app er creatures FILE    every skeleton of the frame that is not a player's, with what the game says it is, as JSON
#
# With look.er_creatures = on, the game's monsters too: each told by its class and level record (er_creatures.cfg, read
# only), drawn as a local model of a similar build (er-models/creatures/<model>) retargeted from its own skeleton
# (_auto_table for people, _auto_four for four-legged ones); a class with no model keeps the game's figure.

var main: Node
var view: Node                  # scene_view.gd
var machine: RtaMachine
var drawer: Object
var mode := "off"
var hidden_sent := false
var check_path := ""
var checks := 0
var data := {}                  # this frame's get_skeletons()
var player_skeleton := -1       # index into data.skeletons: the local player's
var player_state := 0
var player_offset := -1         # the player's animation state, from its object (0x114 when found that way)
var hidden: PackedInt64Array = PackedInt64Array()
var held_objects: PackedInt64Array = PackedInt64Array()    # rigid models in the local player's hands
var hands_found: Array = []
var skel_nodes := {}            # key -> Skeleton3D (the check and "self")
var said := {}
# drawing (the world's scenario; RenderingServer objects)
var scenario: RID
var self_instance: RID
var self_skeleton: RID
var self_mesh: ArrayMesh
var self_material: StandardMaterial3D
# the Elden Ring figures
const CLASS_SETS := ["barbarian", "cleric", "necromancer", "ranger", "wizard", "berserker", "shaman"]   # record +0x50
const WEAPON_NAMES := ["", "dagger", "sword", "axe", "mace", "great", "spear", "staff", "bow"]      # soulscombat WC_*
const DT := 1.0 / 60.0
var models := {}                # outfit -> model (below), or {"failed": why}
var weapon_models := {}         # weapon class name -> {mesh, materials, axis, side, length} or {} (none)
var figures := {}               # key ("slot0".. or "local") -> figure: {set, instances, globals, springs, weapons, used}
var targets: Array = []         # this frame's: [{key, skeleton, set, slot, wclass, held: [...]}]
var game_weapons := {}          # signature -> {axis, side} of a game weapon in its own model space (from its vertices)
var want_mesh := false
var catch_joints := 0
var catch_path := ""
var catch_shots := 0
var catch_frame := 0
var er_root: Node
var er_failed := ""
var creatures_on := false          # look.er_creatures
var creature_cfg: ConfigFile        # er_creatures.cfg (null: not read yet)
var creature_said := {}             # identity text -> printed once
# a light of the figures' own where the scene has none of Godot's (the game's overhead view: its colours are lit by the game
# itself; a figure of ours would be black): a key light from above the camera and a fill, on our figures only (layer 20)
const OWN_LAYER := 1 << 19
var own_lights: Array = []          # [light RID, instance RID]
# cost of the layer (before_frame + frame), microseconds
var cost_sum := 0
var cost_worst := 0
var cost_frames := 0
var cost_start := 0
var bf_spent := 0
var part_us := {"get": 0, "find": 0, "draw": 0}


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
	for key in figures:
		_free_figure(figures[key])
	figures.clear()


func _free_figure(f: Dictionary) -> void:
	for m in f.get("instances", []):
		for key in ["instance", "skeleton"]:
			if (m[key] as RID).is_valid():
				RenderingServer.free_rid(m[key])
	for w in f.get("weapons", {}).values():
		if (w.instance as RID).is_valid():
			RenderingServer.free_rid(w.instance)
	f["instances"] = []
	f["weapons"] = {}


func command(w: PackedStringArray) -> void:
	if w.size() >= 3 and w[1] == "check":
		check_path = "" if w[2] == "off" else w[2]
	elif w.size() >= 2 and w[1] == "info":
		print("[blank %d] rta_godot: er: %s" % [main.blanks, info_text()])
	elif w.size() >= 3 and w[1] == "dump":
		_dump(w[2])
	elif w.size() >= 2 and w[1] == "auto":
		# what the bind-pose reader makes of every person skeleton of the frame
		for s in data.get("skeletons", []):
			if int(s.joint_count) >= 30:
				print("[blank %d] rta_godot: er auto: %d joints (state %x): %s" % [main.blanks, int(s.joint_count), int(s.state), str(_auto_table(s))])
	elif w.size() >= 4 and w[1] == "catch":
		# app er catch N FILE: the first frame from now with a skeleton of N joints is dumped to FILE
		catch_joints = w[2].to_int()
		catch_path = w[3]
	elif w.size() >= 3 and w[1] == "creatures":
		# app er creatures FILE: every skeleton of the frame that is not a player's, with what the game says it is, as JSON
		_dump(w[2], true)
	elif w.size() >= 2 and w[1] == "cost":
		var nf := maxf(1.0, float(cost_frames))
		print("[blank %d] rta_godot: er cost: %d frames, mean %.1f us (get_skeletons %.1f, finding %.1f, posing and drawing %.1f), worst %d us, %d figures drawn now" % [main.blanks, cost_frames,
			float(cost_sum) / nf, part_us.get / nf, part_us.find / nf, part_us.draw / nf, cost_worst, targets.size()])
		part_us = {"get": 0, "find": 0, "draw": 0}
		cost_sum = 0
		cost_worst = 0
		cost_frames = 0


func info_text() -> String:
	var per := PackedStringArray()
	for t in targets:
		var held := PackedStringArray()
		for h in t.held:
			held.append("%s %s at joint %d (%d pieces)%s" % [h.what, h.hand, h.joint, h.pieces.size(), "" if h.drawn else " (not drawn)"])
		var spread := 0.0
		var far := PackedStringArray()
		var fg: Array = figures.get(t.key, {}).get("globals", [])
		var msk: Skeleton3D = models[t.set].skeleton
		for b in fg.size():
			var gt = fg[b]
			if gt is Transform3D:
				var d := (gt as Transform3D).origin.distance_to((data.skeletons[t.skeleton].joints[0] as Transform3D).origin)
				spread = maxf(spread, d)
				var sc := (gt as Transform3D).basis.get_scale().x
				if d > 60.0 or absf(sc - fg.size() * 0.0 - (gt as Transform3D).basis.get_scale().y) > 1.0:
					far.append(msk.get_bone_name(b))
		if not far.is_empty():
			per.append("FAR: " + ",".join(far))
		per.append("%s: set %s, bones within %.0f units, skeleton %d (%d joints), weapon class %s, holds [%s]" % [t.key, t.set, spread, t.skeleton,
			int(data.skeletons[t.skeleton].joint_count), WEAPON_NAMES[t.wclass] if t.wclass > 0 and t.wclass < WEAPON_NAMES.size() else str(t.wclass), ", ".join(held)])
	return "mode %s, %s, players %d, figures drawn %d [%s], local skeleton %d (state %x at +0x%x of the player, %d joints), %d objects hidden, %d checks" % [mode,
		"models " + ",".join(PackedStringArray(models.keys())) if er_failed == "" else er_failed, data.get("players", []).size(), targets.size(), "; ".join(per),
		player_skeleton, player_state, player_offset, int(_player().get("joint_count", 0)), hidden.size(), checks]


func _player() -> Dictionary:
	if player_skeleton < 0:
		return {}
	return data.skeletons[player_skeleton]


# ---------------------------------------------------------------------------------------------------------------------
# Before the drawer takes the frame: find the figures; leave out what is drawn here.
func before_frame(wanted: String) -> void:
	cost_start = Time.get_ticks_usec()
	mode = wanted
	creatures_on = view != null and String(view.look.get("er_creatures", "off")) == "on"
	var drawing := mode == "self" or mode == "on" or creatures_on
	if not drawing and check_path == "":
		if hidden_sent:
			drawer.call("set_hidden_objects", PackedInt64Array())
			hidden_sent = false
		targets = []
		_hide_drawn()
		bf_spent = Time.get_ticks_usec() - cost_start
		return
	var t_get := Time.get_ticks_usec()
	data = machine.get_skeletons(mode == "self" or check_path != "" or want_mesh)
	want_mesh = false
	part_us.get += Time.get_ticks_usec() - t_get
	if data.is_empty():
		data = {"skeletons": []}
	_find_player()
	if catch_shots > 0:
		catch_frame += 1
		if catch_frame % 20 == 1:
			main.pending_shots.append(catch_path.get_basename() + "-%d.png" % (3 - catch_shots))
			catch_shots -= 1
	if catch_joints > 0:
		for sk in data.skeletons:
			if int(sk.joint_count) == catch_joints:
				_dump(catch_path)
				catch_shots = 3             # and pictures of the frame drawn now and the next two (main.gd's shots)
				catch_frame = 0
				print("[blank %d] rta_godot: er catch: %d joints (state %x), dumped to %s; auto: %s" % [main.blanks, catch_joints, int(sk.state), catch_path, str(_auto_table(sk))])
				catch_joints = 0
				break
	if check_path != "":
		_check()
	var hide := PackedInt64Array()
	targets = []
	if mode == "self" and player_skeleton >= 0:
		hide = hidden.duplicate()
		hide.append_array(held_objects)
	if mode == "on" or creatures_on:
		var t_find := Time.get_ticks_usec()
		if mode == "on":
			_find_targets()
		if creatures_on:
			_find_creatures()
		part_us.find += Time.get_ticks_usec() - t_find
		for t in targets:
			hide.append_array(t.objects)
			for h in t.held:
				if h.drawn and not h.own:
					hide.append(h.object)
	if not hide.is_empty():
		drawer.call("set_hidden_objects", hide)
		hidden_sent = true
	elif hidden_sent:
		drawer.call("set_hidden_objects", PackedInt64Array())
		hidden_sent = false
	bf_spent = Time.get_ticks_usec() - cost_start


# the hands of a person skeleton: joints with three or more children (the fingers) low and to the side in the bind pose
# ([joint, "left" / "right"]; the figure's left is at +x)
func _hands_of(p: Dictionary) -> Array:
	var t := _auto_cached(p)
	var out: Array = []
	for side in ["left", "right"]:
		if t.has(side + "_hand"):
			out.append([int(t[side + "_hand"][0]), side])
	return out


# a skeleton's build: its joint count and its parents (two builds of one count differ in their parents)
func _build_key(p: Dictionary) -> String:
	var parent: PackedInt32Array = p.parent
	var h := hash(parent)
	return "%d:%d" % [int(p.joint_count), h]


var _auto_cache := {}
func _auto_cached(p: Dictionary) -> Dictionary:
	var key := _build_key(p)
	if not _auto_cache.has(key):
		_auto_cache[key] = _auto_table(p)
	return _auto_cache[key]


func _find_player() -> void:
	player_skeleton = -1
	player_state = 0
	hidden = PackedInt64Array()
	held_objects = PackedInt64Array()
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
	hidden = _objects_of(player_state)
	hands_found = []
	for h in _hands_of(skeletons[player_skeleton]):
		hands_found.append((skeletons[player_skeleton].joints[h[0]] as Transform3D).origin)
	for h in _held(skeletons[player_skeleton], hidden):
		if not h.own:
			held_objects.append(h.object)


# every object posed by one animation state: one figure (body, head, what it wears)
func _objects_of(state: int) -> PackedInt64Array:
	var objects := {}
	for s in data.skeletons:
		if int(s.state) == state:
			objects[int(s.object)] = true
	var out := PackedInt64Array()
	for o in objects:
		out.append(o)
	return out


# What a figure holds: rigid models whose own matrix is at one of its hands (the game hangs a weapon on an attach point of
# the hand's joint: model_getAttachPoint): its own origin within 20 units of the hand (a spear's is at its butt).
# [{piece, object, joint, hand, at: Transform3D (the model's matrix in the world)}]
const ATTACH_FRAMES := 4
var attach_seen := {}               # "<state>:<hand>" -> {rel, frame, count}: a model of another object held at that hand
func _held(p: Dictionary, own: PackedInt64Array) -> Array:
	var out: Array = []
	if not data.has("piece_kind"):
		return out
	var kinds: PackedInt32Array = data.piece_kind
	var skel_of: PackedInt32Array = data.piece_skeleton
	var objs: PackedInt32Array = data.piece_object
	var flags: PackedInt32Array = data.piece_flags
	var slot0: Array = data.piece_slot0
	var hands := _hands_of(p)
	var groups := {}
	# (the weapon is drawn as part of its bearer's object: rigid pieces, no pose of their own, their matrix at a hand)
	var frame_now := Engine.get_process_frames()
	for i in kinds.size():
		if kinds[i] != 2 or skel_of[i] >= 0:
			continue
		var at: Transform3D = slot0[i]
		var best := -1
		var best_d := 20.0
		for k in hands.size():
			var d := at.origin.distance_to((p.joints[hands[k][0]] as Transform3D).origin)
			if d < best_d:
				best_d = d
				best = k
		if best < 0:
			continue
		if not own.has(objs[i]):
			# a model of another object at a hand (a shield the game draws as an object of its own): held only when it has
			# kept its place against the hand's joint for ATTACH_FRAMES frames - loot or another figure's weapon passing a
			# hand does not (the object numbers are the frame's, so the hand is what is followed)
			var rel := (p.joints[hands[best][0]] as Transform3D).affine_inverse() * at
			var akey := "%x:%s" % [int(p.state), String(hands[best][1])]
			var seen: Dictionary = attach_seen.get(akey, {})
			if seen.is_empty() or int(seen.frame) != frame_now:
				var steady := not seen.is_empty() and int(seen.frame) >= frame_now - 2 and (seen.rel as Transform3D).origin.distance_to(rel.origin) < 1.5 \
					and ((seen.rel as Transform3D).basis.x - rel.basis.x).length() < 0.1 * maxf(rel.basis.x.length(), 1e-3)
				seen = {"rel": rel, "frame": frame_now, "count": (int(seen.count) + 1) if steady else 1}
				attach_seen[akey] = seen
			if int(seen.count) < ATTACH_FRAMES:
				continue
		var key := "%d:%d:%d:%d" % [objs[i], roundi(at.origin.x * 4.0), roundi(at.origin.y * 4.0), roundi(at.origin.z * 4.0)]
		if not groups.has(key):
			groups[key] = {"pieces": PackedInt32Array(), "object": objs[i], "joint": int(hands[best][0]), "hand": String(hands[best][1]), "at": at,
				"count": 0, "drawn": false, "what": "", "own": own.has(objs[i])}
			out.append(groups[key])
		if (flags[i] & 2) == 0:             # (the environment-map pass of a two-pass packet repeats the first)
			groups[key].pieces.append(i)
			groups[key].count += int(data.piece_source_count[i])
	return out


# The players to draw this frame, each with its outfit and what it holds.
func _find_targets() -> void:
	if er_failed != "":
		return
	var skeletons: Array = data.skeletons
	var players: Array = data.get("players", [])
	var who := String(view.look.get("er_who", "all")) if view != null else "all"
	var list: Array = []
	# (in a net game this machine's own player is drawn from its prediction copy - another object, the one the controls
	# name - so the local slot takes the local skeleton found by the controls)
	var local_slot := int(machine.get_controls_hud().get("slot", -1))
	for pl in players:
		var found := -1
		# (only when the controls named it: the nearest-skeleton guess can be anyone - in drunare's cut scene a 55-joint
		# figure of the scene's was taken for the player and drawn in its outfit)
		if int(pl.slot) == local_slot and player_skeleton >= 0 and player_offset >= 0 and player_offset < 0x800:
			found = player_skeleton
		else:
			for k in skeletons.size():
				if int(skeletons[k].state) == int(pl.state) and int(skeletons[k].joint_count) >= 30:
					found = k
					break
		if found >= 0:
			list.append({"key": "slot%d" % int(pl.slot), "skeleton": found, "slot": int(pl.slot), "cls": int(pl.character_class),
				"wclass": int(pl.weapon_class), "item": int(pl.weapon_item), "local": found == player_skeleton})
	if players.is_empty() and player_skeleton >= 0 and player_offset >= 0 and player_offset < 0x800:
		# a library from before the players were added: the local player alone, its class not known
		list.append({"key": "local", "skeleton": player_skeleton, "slot": -1, "cls": -1, "wclass": -1, "item": 0, "local": true})
	var want_set := String(view.look.get("er_set", "auto")) if view != null else "auto"
	for t in list:
		if who == "me" and not t.local:
			continue
		var set_name := want_set
		if want_set == "auto" or want_set == "":
			set_name = String(CLASS_SETS[t.cls]) if t.cls >= 0 and t.cls < CLASS_SETS.size() else "default"
		var model := _model(set_name)
		if model.is_empty() and _loading(set_name):
			continue
		if model.is_empty() and set_name != "default":
			set_name = "default"
			model = _model(set_name)
		if model.is_empty():
			continue
		var s: Dictionary = skeletons[t.skeleton]
		if not _align(model, s):
			continue
		t["set"] = set_name
		t["objects"] = _objects_of(int(s.state))
		t["held"] = _held(s, t.objects)
		_weapons_for(t)
		targets.append(t)


# ---------------------------------------------------------------------------------------------------------------------
# The weapons: the game's weapon in hand swapped for the Elden Ring weapon of its class (er-models/weapons/<class>.glb,
# a rigid model whose origin is its grip; <class>.json its axes).  The game's own weapon tells where and how it is held:
# its matrix (the hand joint's attach point, slot 0 of its piece) and its own long and side axes (from its vertices, once
# per weapon).  The new weapon's grip is put at the figure's hand where the game's grip is at the game's hand, its long
# axis along the game weapon's, its side axis along the game weapon's side; its size is its own (metres, by the figure's
# scale).  A shield (a piece at the other hand) becomes the shield model.
func _weapons_for(t: Dictionary) -> void:
	var weapon_name: String = WEAPON_NAMES[t.wclass] if t.wclass > 0 and t.wclass < WEAPON_NAMES.size() else "sword"
	var main_hand: String = "left" if weapon_name == "bow" else "right"
	var have_main := false
	for h in t.held:
		if h.hand == main_hand and not have_main:
			h.what = weapon_name
			have_main = true
	for h in t.held:
		if h.what == "":
			h.what = weapon_name if (not have_main and weapon_name == "bow") else "shield"
			have_main = have_main or h.what == weapon_name
	for h in t.held:
		var wm: Dictionary = _weapon_model(h.what)
		if wm.is_empty():
			continue
		var sig: String = "%s:%x:%d" % [h.what, int(t.item) if h.what != "shield" else 0, h.count]
		if not game_weapons.has(sig):
			if data.has("source_position"):
				game_weapons[sig] = _game_axes(h)
			else:
				want_mesh = true            # its vertices next frame; the game's weapon is drawn until then
				continue
		if (game_weapons[sig] as Dictionary).is_empty():
			continue
		h["sig"] = sig
		h.drawn = true


# a game weapon's long and side axes in its own model space, from its bind-pose vertices (the piece's sources)
func _game_axes(h: Dictionary) -> Dictionary:
	var src: PackedVector3Array = data.source_position
	var pos := PackedVector3Array()
	for i in h.pieces:
		var first := int(data.piece_source_first[i])
		var count := int(data.piece_source_count[i])
		if first + count <= src.size():
			pos.append_array(src.slice(first, first + count))
	var n := pos.size()
	if n < 4:
		return {}
	var mean := Vector3.ZERO
	for v in pos:
		mean += v
	mean /= float(n)
	var c := [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
	for v in pos:
		var d := v - mean
		for r in 3:
			for q in 3:
				c[r][q] += d[r] * d[q]
	var cov := Basis(Vector3(c[0][0], c[1][0], c[2][0]), Vector3(c[0][1], c[1][1], c[2][1]), Vector3(c[0][2], c[1][2], c[2][2]))
	var axis := _principal(cov, Vector3(0.31, 0.83, 0.47))
	var l1 := axis.dot(cov * axis)
	var deflated := Basis(cov.x - axis * axis.x * l1, cov.y - axis * axis.y * l1, cov.z - axis * axis.z * l1)
	var side := _principal(deflated, axis.cross(Vector3(0.2, 0.9, 0.4)).normalized())
	side = (side - axis * side.dot(axis)).normalized()
	var lo := 0.0; var hi := 0.0; var slo := 0.0; var shi := 0.0
	for v in pos:
		lo = minf(lo, v.dot(axis)); hi = maxf(hi, v.dot(axis))
		slo = minf(slo, v.dot(side)); shi = maxf(shi, v.dot(side))
	if hi < -lo:
		axis = -axis
		var t := lo; lo = -hi; hi = -t
	if shi < -slo:
		side = -side
	# the check that the sources are the pieces' own model space: through their matrix they are the corners the game drew
	var err := -1.0
	if data.has("full_position"):
		var at: Transform3D = h.at
		var fp: PackedVector3Array = data.full_position
		var fs: PackedInt32Array = data.full_source
		err = 0.0
		for i in h.pieces:
			var ff := int(data.piece_full_first[i])
			var first := int(data.piece_source_first[i])
			for c2 in range(ff, ff + mini(int(data.piece_full_count[i]), 60)):
				err = maxf(err, (at * src[first + fs[c2]]).distance_to(fp[c2]))
	var scale: Vector3 = (h.at as Transform3D).basis.get_scale()
	print("rta_godot: er: game weapon (%s, %d pieces, %d vertices) at joint %d: long axis %s (%.1f units out, %.1f back, its matrix's scale %s), side %s; its vertices through its matrix: %.4f units from the corners drawn" % [
		h.what, h.pieces.size(), n, h.joint, str(axis), hi, -lo, str(scale), str(side), err])
	return {"axis": axis, "side": side, "length": hi, "back": -lo}


func _principal(m: Basis, start: Vector3) -> Vector3:
	var v := start.normalized()
	for i in 40:
		var w := m * v
		if w.length() < 1e-12:
			break
		v = w.normalized()
	return v


func _weapon_model(cls: String) -> Dictionary:
	if weapon_models.has(cls):
		return weapon_models[cls]
	var path := _er_folder().path_join("weapons").path_join(cls + ".glb")
	var info_path := path.get_basename() + ".json"
	if not FileAccess.file_exists(path) or not FileAccess.file_exists(info_path):
		weapon_models[cls] = {}
		return {}
	var got = _gltf(path)
	if got == null:
		return {}                       # being read (the game's weapon until then)
	weapon_models[cls] = {}
	if not (got is Node):
		return {}
	var root: Node = got
	var found: Array = []
	_meshes(root, found)
	if found.is_empty():
		root.queue_free()
		return {}
	_holder().add_child(root)
	(root as Node3D).visible = false
	var info = JSON.parse_string(FileAccess.get_file_as_string(info_path))
	if not (info is Dictionary):
		return {}
	var mesh: Mesh = (found[0] as MeshInstance3D).mesh
	var a: Array = info.axis
	var s: Array = info.side
	var shift := 0.0
	var size := 1.0
	var cfg := ConfigFile.new()
	if cfg.load("res://er_joint_map.cfg") == OK and cfg.has_section_key("weapons", cls):
		var v: Array = cfg.get_value("weapons", cls)
		shift = float(v[0])
		size = float(v[1]) if v.size() > 1 else 1.0
	weapon_models[cls] = {"mesh": mesh, "materials": _in_order(mesh), "axis": Vector3(a[0], a[1], a[2]).normalized(),
		"side": Vector3(s[0], s[1], s[2]).normalized(), "length": float(info.length), "shift": shift, "size": size, "model": String(info.get("model", ""))}
	print("rta_godot: er: weapon %s loaded (%s, %.2f m)" % [cls, String(info.get("model", "")), float(info.length)])
	return weapon_models[cls]


# A glTF file read and made into nodes on a worker thread (it took 50 to 100 ms each on the main thread: the outfit, the
# weapon and the creatures' figures at the moment the layer was turned on or a new kind came into view, one stop of 0.2 s
# in a picture).  Returns the scene's root when it is there, null while it is being read, false when it could not be.
var loads := {}                     # path -> {"task": WorkerThreadPool task, "out": {"root": Node}}
func _gltf(path: String) -> Variant:
	if loads.has(path):
		var l: Dictionary = loads[path]
		if not WorkerThreadPool.is_task_completed(int(l.task)):
			return null
		WorkerThreadPool.wait_for_task_completion(int(l.task))
		loads.erase(path)
		return (l.out as Dictionary).get("root", false)
	var out := {}
	var task := WorkerThreadPool.add_task(func() -> void:
		var doc := GLTFDocument.new()
		var state := GLTFState.new()
		if doc.append_from_file(path, state) == OK:
			out["root"] = doc.generate_scene(state))
	loads[path] = {"task": task, "out": out}
	return null


# Every task given to the pool must be waited for: one never asked for again (its figure left the view, the level
# changed, the program is ending) keeps this script's lambda in the pool, and the pool then destroys it after the
# script is gone - a crash when the program ends (signal 11 in WorkerThreadPool::finish, seen after a recording).
func _exit_tree() -> void:
	for path in loads:
		var l: Dictionary = loads[path]
		WorkerThreadPool.wait_for_task_completion(int(l.task))
		var root: Variant = (l.out as Dictionary).get("root", null)
		if root is Node:
			(root as Node).free()
	loads.clear()


func _loading(set_name: String) -> bool:
	return loads.has(_er_folder().path_join(set_name).path_join("figure.glb"))


func _holder() -> Node:
	if er_root == null:
		er_root = Node3D.new()
		add_child(er_root)
	return er_root


func _hide_drawn() -> void:
	if self_instance.is_valid():
		RenderingServer.instance_set_visible(self_instance, false)
	for key in figures:
		_hide_figure(figures[key])


func _hide_figure(f: Dictionary) -> void:
	for m in f.get("instances", []):
		RenderingServer.instance_set_visible(m.instance, false)
	for w in f.get("weapons", {}).values():
		RenderingServer.instance_set_visible(w.instance, false)


# ---------------------------------------------------------------------------------------------------------------------
# After the drawer has taken the frame: draw the figures.
func frame(to_scenario: RID) -> void:
	var started := Time.get_ticks_usec()
	if to_scenario != scenario:
		release()
		scenario = to_scenario
	var drawing := (mode == "self" and player_skeleton >= 0) or ((mode == "on" or creatures_on) and not targets.is_empty())
	if not drawing:
		_hide_drawn()
		for pair in own_lights:
			RenderingServer.instance_set_visible(pair[1], false)
		_count(started)
		return
	_own_light()
	if mode == "self":
		for key in figures:
			_hide_figure(figures[key])
		_draw_self()
	else:
		if self_instance.is_valid():
			RenderingServer.instance_set_visible(self_instance, false)
		var drawn := {}
		var t_draw := Time.get_ticks_usec()
		for t in targets:
			_draw_figure(t)
			drawn[t.key] = true
		part_us.draw += Time.get_ticks_usec() - t_draw
		var gone: Array = []
		for key in figures:
			if not drawn.has(key):
				_hide_figure(figures[key])
				# a creature's figure not drawn for two seconds (it died, or is out of sight) is let go
				var f: Dictionary = figures[key]
				f["unseen"] = int(f.get("unseen", 0)) + 1
				if String(key).begins_with("c") and int(f.unseen) > 120:
					gone.append(key)
			else:
				figures[key]["unseen"] = 0
		for key in gone:
			_free_figure(figures[key])
			figures.erase(key)
	_count(started)


func _count(started: int) -> void:
	var spent := Time.get_ticks_usec() - started + bf_spent
	cost_sum += spent
	cost_frames += 1
	cost_worst = maxi(cost_worst, spent)


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



func _dump(path: String, creatures := false) -> void:
	var out := {"tick": machine.get_sim_tick(), "local": player_skeleton, "players": data.get("players", []), "skeletons": []}
	for k in (data.get("skeletons", []) as Array).size():
		var p: Dictionary = data.skeletons[k]
		if int(p.joint_count) < (2 if creatures else 30):
			continue
		var s := {"index": k, "object": p.object, "state": p.state, "clip": p.clip, "parent": Array(p.parent), "bind": [], "joints": []}
		if creatures:
			s["identity"] = _identity(p)
		for j in int(p.joint_count):
			var b: Vector3 = p.bind[j]
			s.bind.append([b.x, b.y, b.z])
			var t: Transform3D = p.joints[j]
			s.joints.append([t.basis.x.x, t.basis.y.x, t.basis.z.x, t.origin.x, t.basis.x.y, t.basis.y.y, t.basis.z.y, t.origin.y, t.basis.x.z, t.basis.y.z, t.basis.z.z, t.origin.z])
		s["held"] = []
		for h in _held(p, _objects_of(int(p.state))):
			var a: Transform3D = h.at
			s.held.append({"object": h.object, "joint": h.joint, "hand": h.hand, "count": h.count, "pieces": Array(h.pieces),
				"at": [a.basis.x.x, a.basis.y.x, a.basis.z.x, a.origin.x, a.basis.x.y, a.basis.y.y, a.basis.z.y, a.origin.y, a.basis.x.z, a.basis.y.z, a.basis.z.z, a.origin.z],
				"attach": _rows((p.joints[h.joint] as Transform3D).affine_inverse() * a)})
		# the scene's model pieces near it: what could be in its hands
		s["near"] = []
		var root: Vector3 = (p.joints[0] as Transform3D).origin
		for i in (data.piece_kind as PackedInt32Array).size():
			if data.piece_slot0[i] == null:
				continue
			var at: Transform3D = data.piece_slot0[i]
			if at.origin.distance_to(root) > 90.0:
				continue
			var sk := int(data.piece_skeleton[i])
			s.near.append({"piece": i, "object": int(data.piece_object[i]), "kind": int(data.piece_kind[i]), "skeleton": sk,
				"state": int(data.skeletons[sk].state) if sk >= 0 else 0, "flags": int(data.piece_flags[i]), "count": int(data.piece_source_count[i]), "at": _rows(at)})
		out.skeletons.append(s)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(out))
		file.close()


func _rows(a: Transform3D) -> Array:
	return [a.basis.x.x, a.basis.y.x, a.basis.z.x, a.origin.x, a.basis.x.y, a.basis.y.y, a.basis.z.y, a.origin.y, a.basis.x.z, a.basis.y.z, a.basis.z.z, a.origin.z]


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
# The Elden Ring outfits (local files only), one loaded model per outfit, shared by every figure wearing it.
func _er_folder() -> String:
	if OS.has_environment("RTA_ER_MODELS"):
		return OS.get_environment("RTA_ER_MODELS")
	# beside the staged project: <root>/local/godot-*/project -> <root>/local/souls-ref/er-models
	return ProjectSettings.globalize_path("res://").path_join("../../souls-ref/er-models").simplify_path()


func _model(set_name: String) -> Dictionary:
	if models.has(set_name):
		var m: Dictionary = models[set_name]
		return {} if m.has("failed") else m
	var dir := _er_folder().path_join(set_name)
	var figure_path := dir.path_join("figure.glb")
	if not FileAccess.file_exists(figure_path):
		models[set_name] = {"failed": "no " + figure_path}
		if not said.has("no " + set_name):
			said["no " + set_name] = true
			print("rta_godot: er: no outfit %s (%s): its figures are the game's" % [set_name, figure_path])
		return {}
	var got = _gltf(figure_path)
	if got == null:
		return {}                       # being read (the game's figure until then)
	if not (got is Node):
		models[set_name] = {"failed": "could not read " + figure_path}
		return {}
	var root: Node = got
	var found := {"skeleton": null}
	var instances: Array = []
	_collect(root, instances, found)
	var sk: Skeleton3D = found.skeleton
	if sk == null or instances.is_empty():
		models[set_name] = {"failed": "no skinned figure in " + figure_path}
		root.queue_free()
		return {}
	_holder().add_child(root)
	(root as Node3D).visible = false
	var count := sk.get_bone_count()
	var m := {"name": set_name, "skeleton": sk, "count": count, "parent": PackedInt32Array(), "rest": [], "grest": [], "grest_basis": [],
		"meshes": [], "aligns": {}, "springs": {}}
	for b in count:
		m.parent.append(sk.get_bone_parent(b))
		m.rest.append(sk.get_bone_rest(b))
		m.grest.append(sk.get_bone_global_rest(b))
		m.grest_basis.append(sk.get_bone_global_rest(b).basis.orthonormalized())
	var used := {}
	for mi in instances:
		var inst: MeshInstance3D = mi
		var skin: Skin = inst.skin
		if skin == null or inst.mesh == null:
			continue
		var binds := PackedInt32Array()
		var poses: Array = []
		for b in skin.get_bind_count():
			var bone := skin.get_bind_bone(b)
			if bone < 0:
				bone = sk.find_bone(skin.get_bind_name(b))
			binds.append(bone)
			poses.append(skin.get_bind_pose(b))
			if bone >= 0:
				used[bone] = true
		m.meshes.append({"mesh": inst.mesh, "binds": binds, "poses": poses, "materials": _in_order(inst.mesh)})
	# the bones that swing (figure.json, written by the converter): each with the centre of what it carries
	var json_path := dir.path_join("figure.json")
	if FileAccess.file_exists(json_path):
		var j = JSON.parse_string(FileAccess.get_file_as_string(json_path))
		if j is Dictionary and j.has("springs"):
			for name in j.springs:
				var b := sk.find_bone(name)
				var tip: Array = j.springs[name].tip
				if b >= 0 and used.has(b):
					m.springs[b] = Vector3(tip[0], tip[1], tip[2])
	for name in ["R_Hand", "L_Hand"]:
		var b := sk.find_bone(name)
		m[name] = b
		if b >= 0:
			used[b] = true
	m["used"] = used
	m["order"] = PackedInt32Array()      # filled by _align (the mapped bones join the used ones)
	print("rta_godot: er: outfit %s loaded: %d bones (%d carry the mesh), %d skinned meshes, %d swinging bones" % [set_name, count, used.size(),
		m.meshes.size(), m.springs.size()])
	models[set_name] = m
	return m


# The joint map (er_joint_map.cfg) and, once per model and game skeleton, how the two bind poses sit against each other.
func _align(m: Dictionary, p: Dictionary, reader := "person") -> bool:
	var n := int(p.joint_count)
	var akey := _build_key(p)
	if (m.aligns as Dictionary).has(akey):
		return not (m.aligns[akey] as Dictionary).is_empty()
	m.aligns[akey] = {}
	var sk: Skeleton3D = m.skeleton
	var cfg := ConfigFile.new()
	if cfg.load("res://er_joint_map.cfg") != OK:
		er_failed = "no er_joint_map.cfg"
		return false
	var section := "joints%d" % n
	var table := {}
	# the joints told apart by where they sit in the skeleton's bind pose (_auto_table), with the bone names of the
	# map's [auto] section; a [jointsN] row of our own is taken instead when it is of the same build (the same head and
	# hips: two skeletons of one joint count can be built differently - the shaman's and the berserker's 64)
	var found := _auto_cached(p) if reader == "person" else _four_cached(p)
	var auto_section := "auto" if reader == "person" else "auto_four"
	if reader != "person":
		section = "none"
	var row_fits := cfg.has_section(section) and (found.is_empty() or (int(cfg.get_value(section, "frame_head", -1)) == int(found.frame_head)
		and int(cfg.get_value(section, "frame_left", -1)) == int(found.frame_left)))
	if row_fits:
		for key in cfg.get_section_keys(section):
			table[key] = cfg.get_value(section, key)
	else:
		if found.is_empty() or not cfg.has_section(auto_section):
			if not said.has(section):
				said[section] = true
				print("rta_godot: er: the joint map has no [%s] of this build, and the skeleton could not be read by itself" % section)
			return false
		for key in found:
			if key.begins_with("frame_"):
				table[key] = found[key]
			elif cfg.has_section_key(auto_section, key):
				var names: Array = cfg.get_value(auto_section, key)
				table[key] = [found[key][0], found[key][1], names[0], names[1]]
		var said_key := "%s:%s:%d:%s" % [section, m.name, int(found.frame_head), akey]
		if not said.has(said_key):
			said[said_key] = true
			var line := PackedStringArray()
			for key in table:
				line.append("%s = %s" % [key, str(table[key])])
			print("rta_godot: er: %s: a %d-joint skeleton (head at joint %d) read by itself (%s): %s" % [m.name, n, int(found.frame_head), reader, ", ".join(line)])
	var game_rest := func(j: int) -> Vector3: return p.bind[j]
	var er_rest := func(b: int) -> Vector3: return (m.grest[b] as Transform3D).origin
	# the two figures' up, forward and left, from their own bind poses (named in the map's [frame] section)
	var f := "frame"
	var g_head := int(table.get("frame_head", 16))
	var g_feet: Array = table.get("frame_toes", [6, 11])
	var g_left := int(table.get("frame_left", 2))
	var g_right := int(table.get("frame_right", 7))
	var e_head := sk.find_bone(String(cfg.get_value(f, "head", "Head")))
	var e_toes: Array = cfg.get_value(f, "toes", ["L_Toe0", "R_Toe0"])
	var e_left := sk.find_bone(String(cfg.get_value(f, "left", "L_Thigh")))
	var e_right := sk.find_bone(String(cfg.get_value(f, "right", "R_Thigh")))
	var e_feet := [sk.find_bone(String(e_toes[0])), sk.find_bone(String(e_toes[1]))]
	if e_head < 0 or e_left < 0 or e_right < 0 or e_feet[0] < 0 or e_feet[1] < 0:
		if not said.has("frame " + String(m.name)):
			said["frame " + String(m.name)] = true
			print("rta_godot: er: outfit %s: its skeleton lacks the bones of the joint map's [frame]" % m.name)
		return false
	var g_ground: Vector3 = (game_rest.call(int(g_feet[0])) + game_rest.call(int(g_feet[1]))) * 0.5
	var e_ground: Vector3 = (er_rest.call(e_feet[0]) + er_rest.call(e_feet[1])) * 0.5
	var g_up: Vector3 = (game_rest.call(g_head) - g_ground)
	var e_up: Vector3 = (er_rest.call(e_head) - e_ground)
	var g_side: Vector3 = (game_rest.call(g_left) - game_rest.call(g_right))
	var e_side: Vector3 = (er_rest.call(e_left) - er_rest.call(e_right))
	var al := {"map": [], "by_bone": {}, "by_name": {}, "scale": g_up.length() / maxf(e_up.length(), 1e-4)}
	al["axes"] = _frame_basis(g_up, g_side) * _frame_basis(e_up, e_side).inverse()
	for key in table:
		if key.begins_with("frame_"):
			continue
		var v: Array = table[key]
		# key = our own name; v = [joint of the game, the joint its aim is taken toward, bone of the model, its aim bone]
		var gj := int(v[0])
		var ga := int(v[1])
		var eb_bone := sk.find_bone(String(v[2]))
		var ea := sk.find_bone(String(v[3])) if String(v[3]) != "" else -1
		if gj < 0 or gj >= n or eb_bone < 0:
			continue
		# align: turns the model's bone (its rest, carried into the game's model space) so that its aim lies along the
		# game's joint's aim in the bind pose; the game's bind pose has every joint's axes along the model's
		var align := Basis()
		if ga >= 0 and ga < n and ea >= 0:
			var from: Vector3 = (al.axes as Basis) * (er_rest.call(ea) - er_rest.call(eb_bone))
			var to: Vector3 = game_rest.call(ga) - game_rest.call(gj)
			if from.length() > 1e-5 and to.length() > 1e-5:
				align = _arc(from.normalized(), to.normalized())
		var entry := {"name": key, "er": eb_bone, "game": gj, "align": align, "fixed": align * (al.axes as Basis) * (m.grest_basis[eb_bone] as Basis)}
		al.map.append(entry)
		al.by_bone[eb_bone] = entry
		al.by_name[key] = gj
	# the root of the mapped bones (the one nearest the skeleton's root), and the bones a frame computes: those that carry
	# the mesh or a weapon, the mapped ones and their ancestors, parents first
	var root_entry: Dictionary = {}
	for e in al.map:
		if root_entry.is_empty() or _depth_in(m, int(e.er)) < _depth_in(m, int(root_entry.er)):
			root_entry = e
	if root_entry.is_empty():
		return false
	al["root"] = root_entry
	var need := {}
	for b in (m.used as Dictionary).keys() + al.by_bone.keys():
		var q := int(b)
		while q >= 0 and not need.has(q):
			need[q] = true
			q = int(m.parent[q])
	var order := PackedInt32Array()
	var placed := {}
	var pending: Array = need.keys()
	while not pending.is_empty():
		var rest: Array = []
		for b in pending:
			var parent := int(m.parent[b])
			if parent < 0 or placed.has(parent):
				order.append(b)
				placed[b] = true
			else:
				rest.append(b)
		if rest.size() == pending.size():
			break
		pending = rest
	al["order"] = order
	# the mapped root's ancestors (Master, the root motion bones) and the other roots are carried rigidly with it; every
	# other bone follows its parent
	var under := {}
	for b in order:
		under[b] = true
	var q := int(m.parent[int(root_entry.er)])
	while q >= 0:
		under[q] = false
		q = int(m.parent[q])
	al["under"] = under
	m.aligns[akey] = al
	print("rta_godot: er: %s: %d joints mapped for a %d-joint skeleton; %.2f units a metre; %d of %d bones computed a frame" % [m.name,
		al.map.size(), n, al.scale, order.size(), int(m.count)])
	return true


func _depth_in(m: Dictionary, b: int) -> int:
	var d := 0
	var q := int(m.parent[b])
	while q >= 0:
		d += 1
		q = int(m.parent[q])
	return d


# ---------------------------------------------------------------------------------------------------------------------
# One figure, this frame: its bones from the game's joints, the springs, the skin, the weapons.
func _draw_figure(t: Dictionary) -> void:
	var p: Dictionary = data.skeletons[t.skeleton]
	var m: Dictionary = models[t.set]
	var al: Dictionary = m.aligns[_build_key(p)]
	var f: Dictionary = figures.get(t.key, {})
	if f.get("set", "") != t.set:
		if not f.is_empty():
			_free_figure(f)
		f = {"set": t.set, "instances": [], "weapons": {}, "springs": {}, "globals": []}
		figures[t.key] = f
	var joints: Array = p.joints
	var k := float(al.scale) * float(p.scale)
	var kv := Vector3(k, k, k)
	var g: Array = f.globals
	if g.size() != int(m.count):
		g.resize(int(m.count))
	var parent: PackedInt32Array = m.parent
	var rest: Array = m.rest
	var grest: Array = m.grest
	var by_bone: Dictionary = al.by_bone
	var under: Dictionary = al.under
	var springs: Dictionary = m.springs if view == null or String(view.look.get("er_springs", "on")) != "off" else {}
	var state: Dictionary = f.springs
	# a mapped bone: the game's joint's turn since its bind pose (its axes in the bind pose are the model's), applied to
	# the model's bone as it rests, carried into the game's model space and aligned; its place: from its parent, by the
	# model's own proportions (scaled to the game's figure) - the root's from the game's
	var root_entry: Dictionary = al.root
	var root_bone := int(root_entry.er)
	var root_global := Transform3D(((joints[int(root_entry.game)] as Transform3D).basis.orthonormalized() * (root_entry.fixed as Basis)).scaled(kv),
		(joints[int(root_entry.game)] as Transform3D).origin)
	var root_rest: Transform3D = grest[root_bone]
	var above := root_global * Transform3D(root_rest.basis.scaled(kv), root_rest.origin * k).affine_inverse()
	var down := Vector3(0, 0, -1)
	# the legs as capsules (thigh and shin, from the game's own joints), for the swinging bones to stay out of: a cape or a
	# skirt is pushed off a leg rather than passing through it (a simple collision of our own; presentation only)
	var capsules: Array = []
	if not springs.is_empty():
		var leg_r := LEG_RADIUS * k
		for side in ["left", "right"]:
			var seg: Array = []
			for part in ["_thigh", "_calf", "_foot"]:
				if (al.by_name as Dictionary).has(side + part):
					seg.append((joints[int(al.by_name[side + part])] as Transform3D).origin)
			for q in range(seg.size() - 1):
				capsules.append([seg[q], seg[q + 1], leg_r * (1.0 if q == 0 else 0.75)])
	for b in al.order:
		if b == root_bone:
			g[b] = root_global
			continue
		var par := parent[b]
		if par < 0 or not under[b]:
			var r: Transform3D = grest[b]
			g[b] = above * Transform3D(r.basis.scaled(kv), r.origin * k)
			continue
		var from_parent: Transform3D = g[par] * (rest[b] as Transform3D)
		if by_bone.has(b):
			var e: Dictionary = by_bone[b]
			g[b] = Transform3D(((joints[int(e.game)] as Transform3D).basis.orthonormalized() * (e.fixed as Basis)).scaled(kv), from_parent.origin)
		elif springs.has(b):
			# a spring: the centre of what the bone carries is a weight that lags behind where the pose puts it, pulled
			# back toward it and down by gravity, at its own distance from the bone's origin; the bone turns toward it
			var tip: Vector3 = from_parent * (springs[b] as Vector3)
			var origin := from_parent.origin
			var s: Dictionary = state.get(b, {})
			if s.is_empty() or (s.p as Vector3).distance_to(tip) > 60.0:
				s = {"p": tip, "v": Vector3.ZERO}
				state[b] = s
			var v: Vector3 = s.v
			var pos: Vector3 = s.p
			v += (tip - pos) * SPRING_PULL * DT + down * (SPRING_GRAVITY * k) * DT
			v *= SPRING_DAMP
			pos += v * DT
			var length := (tip - origin).length()
			var dir := (pos - origin)
			if dir.length() > 1e-4 and length > 1e-4:
				var want := (tip - origin) / length
				var now := dir.normalized()
				# no more than SPRING_MAX from where the pose holds it
				var angle := want.angle_to(now)
				if angle > SPRING_MAX:
					now = want.slerp(now, SPRING_MAX / angle).normalized()
				pos = origin + now * length
				for cap in capsules:
					var a0: Vector3 = cap[0]
					var ab: Vector3 = (cap[1] as Vector3) - a0
					var u := clampf((pos - a0).dot(ab) / maxf(ab.length_squared(), 1e-6), 0.0, 1.0)
					var near := a0 + ab * u
					var off := pos - near
					var r := float(cap[2])
					if off.length() < r:
						# out to the capsule's skin, away from the leg (behind it when it is on the axis), at the bone's length
						var away := off.normalized() if off.length() > 1e-4 else (pos - origin).normalized()
						pos = origin + ((near + away * r) - origin).normalized() * length
						v -= away * minf(0.0, v.dot(away))
				now = (pos - origin).normalized()
				g[b] = Transform3D(_arc(want, now) * from_parent.basis, origin)
			else:
				g[b] = from_parent
			s.p = pos
			s.v = v
		else:
			g[b] = from_parent
	# the skin
	var root_at: Vector3 = (joints[0] as Transform3D).origin
	# the bones of the game frame before, for the pictures drawn between game frames (tween): only when this figure was
	# drawn in that frame too and did not jump
	var now_frame := int(view.frames_taken) if view != null else 0
	var before_ok := int(f.get("g_frame", -10)) == now_frame - 1 and (f.get("g_root", root_at) as Vector3).distance_to(root_at) < 40.0
	f["g_before"] = f.get("g_now", []) if before_ok else []
	f["g_now"] = g.duplicate()
	f["g_frame"] = now_frame
	f["g_root"] = root_at
	_skin(f, m, g, root_at, t)
	# the weapons
	var weapons: Dictionary = f.weapons
	var shown := {}
	for h in t.held:
		if not h.drawn:
			continue
		var wm: Dictionary = _weapon_model(h.what)
		var ga: Dictionary = game_weapons[h.sig]
		var at: Transform3D = h.at
		var game_axis := (at.basis * (ga.axis as Vector3)).normalized()
		var game_side := at.basis * (ga.side as Vector3)
		game_side = (game_side - game_axis * game_side.dot(game_axis)).normalized()
		var er_axis: Vector3 = wm.axis
		var er_side: Vector3 = wm.side
		var turn := Basis(game_axis, game_side, game_axis.cross(game_side)) * Basis(er_axis, er_side, er_axis.cross(er_side)).inverse()
		# the grip: where the game's grip is, measured from the game's hand, measured from the figure's hand
		var hand_bone := int(m.get("L_Hand" if h.hand == "left" else "R_Hand", -1))
		var game_hand: Vector3 = (joints[int(h.joint)] as Transform3D).origin
		var grip := at.origin + (((g[hand_bone] as Transform3D).origin - game_hand) if hand_bone >= 0 else Vector3.ZERO)
		grip += game_axis * float(wm.shift) * k
		var key := String(h.hand)
		var w: Dictionary = weapons.get(key, {})
		if w.is_empty() or w.what != h.what:
			if not w.is_empty():
				RenderingServer.free_rid(w.instance)
			w = {"what": h.what, "instance": RenderingServer.instance_create2((wm.mesh as Mesh).get_rid(), scenario)}
			weapons[key] = w
		var size := k * float(wm.size)
		var place := Transform3D(turn.scaled(Vector3(size, size, size)), grip)
		w["before"] = w.get("now", place) if before_ok and w.has("now") else place
		w["now"] = place
		RenderingServer.instance_set_transform(w.instance, place)
		_place(w.instance, wm.materials, t)
		RenderingServer.instance_set_visible(w.instance, true)
		shown[key] = true
	for key in weapons:
		if not shown.has(key):
			RenderingServer.instance_set_visible(weapons[key].instance, false)
			(weapons[key] as Dictionary).erase("now")
	f["drawn_frame"] = now_frame


# The skin of a figure from its model's bone globals G (this game frame's, or one between two: tween).
func _skin(f: Dictionary, m: Dictionary, g: Array, root_at: Vector3, t: Dictionary) -> void:
	var instances: Array = f.instances
	for i in (m.meshes as Array).size():
		var mesh: Dictionary = m.meshes[i]
		if instances.size() <= i:
			var sk_rid := RenderingServer.skeleton_create()
			RenderingServer.skeleton_allocate_data(sk_rid, (mesh.binds as PackedInt32Array).size())
			var inst := RenderingServer.instance_create2((mesh.mesh as Mesh).get_rid(), scenario)
			RenderingServer.instance_attach_skeleton(inst, sk_rid)
			instances.append({"instance": inst, "skeleton": sk_rid})
		var binds: PackedInt32Array = mesh.binds
		var poses: Array = mesh.poses
		var rid: RID = instances[i].skeleton
		for q in binds.size():
			var bone := binds[q]
			RenderingServer.skeleton_bone_set_transform(rid, q, (g[bone] as Transform3D) * (poses[q] as Transform3D) if bone >= 0 and g[bone] != null else Transform3D())
		if t.has("tween"):
			continue                    # between game frames: only the bones move (the order and the box are the frame's)
		_place(instances[i].instance, mesh.materials, t)
		RenderingServer.instance_set_visible(instances[i].instance, true)
		RenderingServer.instance_set_custom_aabb(instances[i].instance, AABB(root_at - Vector3(120, 120, 120), Vector3(240, 240, 240)))


# A picture between game frames (main.gd, the display rate above 60): every figure drawn in the last game frame posed T
# game frames on from its bones there, along their motion since the frame before (T < 0: between the two); the weapons
# the same way.  Nothing is found or read from the game: only the last two frames' bones are blended.
func tween(t: float) -> void:
	if view == null:
		return
	var now_frame := int(view.frames_taken)
	for key in figures:
		var f: Dictionary = figures[key]
		if int(f.get("drawn_frame", -10)) != now_frame:
			continue
		var before: Array = f.get("g_before", [])
		var now: Array = f.get("g_now", [])
		if before.size() != now.size() or now.is_empty() or not models.has(f.set):
			continue
		var g: Array = []
		g.resize(now.size())
		var w := 1.0 + t
		for b in now.size():
			var a = before[b]
			var c = now[b]
			if a == null or c == null:
				g[b] = c
			else:
				g[b] = (a as Transform3D).interpolate_with(c as Transform3D, w)
		_skin(f, models[f.set], g, (f.g_root as Vector3), {"key": key, "tween": true})
		for wk in f.weapons:
			var wd: Dictionary = f.weapons[wk]
			if wd.has("now") and wd.has("before"):
				RenderingServer.instance_set_transform(wd.instance, (wd.before as Transform3D).interpolate_with(wd.now as Transform3D, w))


const SPRING_PULL := 140.0          # 1/s^2: how hard the pose pulls the weight back
const SPRING_GRAVITY := 9.8         # m/s^2 (times the figure's units a metre)
const SPRING_DAMP := 0.86           # of the speed kept a frame
const SPRING_MAX := 1.0             # radians at most from the pose
const LEG_RADIUS := 0.11            # metres (times the figure's units a metre): the thigh's capsule; the shin's 3/4 of it


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
		# the maps (normal, metalness, roughness from the outfit's own textures): the world here has no reflections of
		# Godot's for a metal to show (the game's scene is drawn by its own shaders), so a metal map at full strength
		# reads black; it is taken at look.er_metal of its strength (default 0.5)
		if copy.metallic_texture != null:
			copy.metallic = float(view.look.get("er_metal", 0.5)) if view != null else 0.5
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
	var cam: Transform3D = _scene_info().get("camera", Transform3D())
	for k in own_lights.size():
		# key: from over the camera's shoulder, down at 50 degrees; fill: from the other side, low
		var dir := (-cam.basis.z).normalized()
		var flat := Vector3(dir.x, dir.y, 0.0).normalized() if Vector3(dir.x, dir.y, 0.0).length() > 0.01 else Vector3(1, 0, 0)
		var side := flat.cross(Vector3(0, 0, 1)).normalized()
		var toward := (flat + side * (0.6 if k == 0 else -0.8) + Vector3(0, 0, -1.2 if k == 0 else -0.3)).normalized()
		RenderingServer.instance_set_transform(own_lights[k][1], Transform3D(Basis.looking_at(toward, Vector3(0, 0, 1)), Vector3.ZERO))
		RenderingServer.instance_set_visible(own_lights[k][1], not lit)


var info_frame := -1
var info_now := {}
func _scene_info() -> Dictionary:           # the drawer's scene info, once a frame (it is not cheap: its figures line)
	if info_frame != Engine.get_process_frames():
		info_frame = Engine.get_process_frames()
		info_now = drawer.call("get_scene_info")
	return info_now


var last_order := -1.0
var orders_frame := -1
var first_order := -1.0
var orders := {}                    # this frame's drawer: per object left out, the place of its first draw
func _place(instance: RID, materials: Array, t: Dictionary = {}) -> void:
	RenderingServer.instance_set_layer_mask(instance, 1 | OWN_LAYER)
	for i in materials.size():
		RenderingServer.instance_set_surface_override_material(instance, i, (materials[i] as Material).get_rid())
	# each figure at the place of the first of its own draws the drawer left out (a creature drawn before the leaves over it
	# stays under them; the first hidden draw of the whole frame may be another figure's); without one this frame (the
	# list the drawer took was drawn before the objects were named), the place that figure had last - not the end of
	# the pass, where it was drawn over everything, the overhead view's see-through leaves among it
	if orders_frame != Engine.get_process_frames():
		orders_frame = Engine.get_process_frames()
		var info: Dictionary = _scene_info()
		orders = info.get("hidden_orders", {})
		first_order = float(info.get("hidden_order", -1.0))
	var order := -1.0
	for o in t.get("objects", PackedInt64Array()):
		if orders.has(o) and (order < 0.0 or float(orders[o]) < order):
			order = float(orders[o])
	if order < 0.0 and t.is_empty():
		order = first_order
	var key := String(t.get("key", ""))
	if order >= 0.0:
		if key != "" and figures.has(key):
			figures[key]["order"] = order
		last_order = order
	elif key != "" and figures.has(key) and figures[key].has("order"):
		order = float(figures[key].order)
	else:
		order = last_order
	RenderingServer.instance_set_pivot_data(instance, order + 0.5 if order >= 0.0 else 1.0e6, false)


func _collect(node: Node, out: Array, found: Dictionary) -> void:
	if node is Skeleton3D and found.skeleton == null:
		found.skeleton = node
	if node is MeshInstance3D and (node as MeshInstance3D).skin != null:
		out.append(node)
	for c in node.get_children():
		_collect(c, out, found)


func _meshes(node: Node, out: Array) -> void:
	if node is MeshInstance3D:
		out.append(node)
	for c in node.get_children():
		_meshes(c, out)



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
	# the arms: from the chest sideways, along the branch that reaches farthest out.  Which joint is which is read from
	# lengths along the chain, not from how many children a joint has (a forearm with a twist joint has two; a hand with
	# one finger joint - a mitten - has one): the hand is where about three quarters of the chain's length lie behind
	# (what is past it is the fingers), the elbow halfway between the shoulder and the hand, the shoulder the chain's
	# first joint or - when the first link is a clavicle - its second
	var reach := PackedFloat32Array()            # the longest way down the tree from each joint
	reach.resize(n)
	for r in range(n - 1, -1, -1):
		for c in kids[r]:
			reach[r] = maxf(reach[r], reach[c] + bind[c].distance_to(bind[r]))
	for c in kids[chest]:
		if side[c] <= 0.18 * h:
			continue
		var prefix := "left" if bind[c].x > 0.0 else "right"
		# along the branch that reaches farthest (a twist or elbow helper may stick out further sideways than the hand)
		var arm: Array = follow.call(c, func(q: int) -> float: return reach[q] + bind[q].distance_to(bind[parent[q]]))
		if arm.size() < 3:
			continue
		var along := PackedFloat32Array([0.0])
		for k in range(1, arm.size()):
			along.append(along[k - 1] + bind[arm[k]].distance_to(bind[arm[k - 1]]))
		var total: float = along[arm.size() - 1]
		if total < 0.05 * h:
			continue
		var hand_at := -1
		for k in range(1, arm.size()):
			if hand_at < 0 or absf(along[k] - 0.78 * total) < absf(along[hand_at] - 0.78 * total):
				hand_at = k
		# a joint with fingers (two or more children) near there is the hand
		for k in range(1, arm.size()):
			if (kids[arm[k]] as Array).size() >= 2 and absf(along[k] - along[hand_at]) < 0.08 * total and along[k] > 0.55 * total:
				hand_at = k
				break
		var best_score := 1e9
		var shoulder_at := 0
		var elbow_at := -1
		for start in [0, 1]:
			if start >= hand_at - 1:
				continue
			var mid: float = (along[start] + along[hand_at]) * 0.5
			var e := -1
			for k in range(start + 1, hand_at):
				if e < 0 or absf(along[k] - mid) < absf(along[e] - mid):
					e = k
			if e < 0:
				continue
			var d1: float = along[e] - along[start]
			var d2: float = along[hand_at] - along[e]
			# a clavicle is short and goes sideways; an upper arm about as long as the forearm
			var score := absf(d1 - d2) / maxf(d1 + d2, 1e-4) + (0.0 if start == 0 else 0.05)
			if score < best_score:
				best_score = score
				shoulder_at = start
				elbow_at = e
		if elbow_at < 0:
			continue
		var hand: int = arm[hand_at]
		var finger: int = arm[mini(hand_at + 1, arm.size() - 1)] if hand_at + 1 < arm.size() else -1
		for q in kids[hand]:
			if finger == -1 or bind[q].distance_to(bind[hand]) > bind[finger].distance_to(bind[hand]):
				finger = q
		if shoulder_at == 1:
			out[prefix + "_clavicle"] = [arm[0], arm[1]]
		out[prefix + "_upper_arm"] = [arm[shoulder_at], arm[elbow_at]]
		out[prefix + "_forearm"] = [arm[elbow_at], hand]
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



# ---------------------------------------------------------------------------------------------------------------------
# Creatures (look.er_creatures = on): the game's monsters drawn as local models of a similar build.  Which creature a
# skeleton is: its animation state lies at +0x114 of its creature (as the players'), whose class is told by its virtual
# table (+0x48) and, for one loaded from the level, by the record's class name (+0x34) - read only.  er_creatures.cfg
# (our own) names, per class, the model folder (er-models/creatures/<model>) and how the joints are read from the bind
# pose ("person": _auto_table; "four": _auto_four).  A class it does not name, or a model that is not there, keeps the
# game's own figure.  What the creature holds is part of its own objects: hidden with it (the model carries its own).
func _creature_table() -> ConfigFile:
	if creature_cfg == null:
		creature_cfg = ConfigFile.new()
		if creature_cfg.load("res://er_creatures.cfg") != OK:
			print("rta_godot: er: no er_creatures.cfg: the creatures are the game's")
	return creature_cfg


var identities := {}                # state -> identity (checked again by its virtual table each frame)
func _identity(p: Dictionary) -> Dictionary:
	var cfg := _creature_table()
	var obj := (int(p.state) - 0x114) & 0x1ffffff
	var vt := int(machine.peek_u32(obj + 0x48)) & 0x1ffffff
	var known: Dictionary = identities.get(int(p.state), {})
	if not known.is_empty() and int(known.vtable) == vt:
		return known
	var cls := String(cfg.get_value("classes", "0x%x" % vt, ""))
	var rec := ""
	var family: Array = []
	if cls != "":
		var rec_at := int(machine.peek_u32(obj + 0x34)) & 0x1ffffff
		rec = machine.peek_string(rec_at, 32) if rec_at != 0 else ""
		if rec != "" and cfg.has_section_key("families", rec):
			family = cfg.get_value("families", rec)
		elif cfg.has_section_key("families", cls):
			family = cfg.get_value("families", cls)
	var id := {"object": obj, "vtable": vt, "class": cls, "record": rec, "family": family}
	if identities.size() > 512:
		identities.clear()
	identities[int(p.state)] = id
	return id


func _find_creatures() -> void:
	if er_failed != "":
		return
	var skeletons: Array = data.skeletons
	var skip := {}
	for t in targets:
		skip[int(skeletons[t.skeleton].state)] = true
	for pl in data.get("players", []):
		skip[int(pl.state)] = true
	if player_skeleton >= 0 and player_offset >= 0 and player_offset < 0x800:
		skip[int(skeletons[player_skeleton].state)] = true
	# one figure per pose (a figure drawn as several objects has one pose); several figures can share one animation state
	# (a band of archers runs one), so the state names the kind - its creature's class - and the pose the figure
	var poses := {}
	var per_state := {}
	var ids := {}
	for k in skeletons.size():
		var s: Dictionary = skeletons[k]
		var st := int(s.state)
		if skip.has(st) or int(s.joint_count) < 8:
			continue
		# (one pose buffer can be drawn at several places - a band sharing its animation: then each place is a figure)
		var root: Vector3 = (s.joints[0] as Transform3D).origin
		var pkey := "%x:%d:%d:%d:%d" % [st, int(s.pose), roundi(root.x / 8.0), roundi(root.y / 8.0), roundi(root.z / 8.0)]
		if poses.has(pkey):
			var more: Dictionary = poses[pkey]
			more["objects"] = (more.objects as PackedInt64Array) + PackedInt64Array([int(s.object)])
			continue
		if not ids.has(st):
			ids[st] = _identity(s)
		var id: Dictionary = ids[st]
		var said_key := "%s/%s/%d" % [id.class, id.record, int(s.joint_count)]
		if not creature_said.has(said_key):
			creature_said[said_key] = true
			print("rta_godot: er: creature %s (record \"%s\"), %d joints: %s" % [id.class if id.class != "" else "unknown 0x%x" % int(id.vtable),
				id.record, int(s.joint_count), ("drawn as " + String(id.family[0])) if not (id.family as Array).is_empty() else "the game's own"])
		if (id.family as Array).is_empty():
			continue
		var set_name := "creatures/" + String(id.family[0])
		var model := _model(set_name)
		if model.is_empty() or not _align(model, s, String(id.family[1])):
			continue
		var n := int(per_state.get(st, 0))
		per_state[st] = n + 1
		var t := {"key": "c%x:%d" % [st, n], "skeleton": k, "set": set_name, "slot": -1, "cls": -1, "wclass": -1, "item": 0, "local": false,
			"creature": true, "objects": PackedInt64Array([int(s.object)]), "held": []}
		poses[pkey] = t
		targets.append(t)


var _four_cache := {}
func _four_cached(p: Dictionary) -> Dictionary:
	var key := _build_key(p)
	if not _four_cache.has(key):
		_four_cache[key] = _auto_four(p)
	return _four_cache[key]


# A four-legged skeleton read from its bind pose (z up, the figure's left at +x, facing -y, as the people's): the two
# joints from which a branch goes down on either side are the hips and the shoulders - the front one the shoulders; the spine is the way between them, the
# neck and head the shoulders' remaining branch that reaches farthest forward, the tail the hips' remaining branch.  Each
# leg: its first joint, a knee halfway, the foot and the toe at its end.
func _auto_four(p: Dictionary) -> Dictionary:
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
	var lo := PackedFloat32Array()
	lo.resize(n)
	var top := -1e9
	var bottom := 1e9
	for j in range(n - 1, -1, -1):
		lo[j] = bind[j].z
		for c in kids[j]:
			lo[j] = minf(lo[j], lo[c])
		top = maxf(top, bind[j].z)
		bottom = minf(bottom, bind[j].z)
	var h := top - bottom
	if h < 1.0:
		return {}
	# the girdles: joints with a branch going down on each side
	var girdles: Array = []
	for j in n:
		var l := -1
		var r := -1
		for c in kids[j]:
			if lo[c] < bind[j].z - 0.4 * (bind[j].z - bottom):
				if bind[c].x > 0.01 * h and l < 0:
					l = c
				elif bind[c].x < -0.01 * h and r < 0:
					r = c
		if l >= 0 and r >= 0:
			girdles.append([j, l, r])
	if girdles.size() < 2:
		return {}
	var path_to_root := func(j: int) -> Array:
		var out: Array = []
		while j >= 0:
			out.append(j)
			j = parent[j]
		return out
	# the head: of all joints, the one farthest from both girdles' middle along the line between them - forward is the end
	# where the head is; it is not on a leg branch
	var a: int = girdles[0][0]
	var b: int = girdles[1][0]
	var leg_roots := {}
	for g in girdles:
		leg_roots[g[1]] = true
		leg_roots[g[2]] = true
	var on_leg := func(j: int) -> bool:
		var q := j
		while q >= 0:
			if leg_roots.has(q):
				return true
			q = parent[q]
		return false
	var axis := (bind[b] - bind[a])
	if axis.length() < 1e-4:
		return {}
	axis = axis.normalized()
	var head := -1
	var tail := -1
	for j in n:
		if on_leg.call(j) or j == a or j == b:
			continue
		var t := (bind[j] - bind[a]).dot(axis)
		if head < 0 or t > (bind[head] - bind[a]).dot(axis):
			head = j
		if tail < 0 or t < (bind[tail] - bind[a]).dot(axis):
			tail = j
	# which girdle is in front: the figures face -y in their bind pose (as the people do)
	var hips: Array = girdles[0]
	var shoulders: Array = girdles[1]
	if bind[a].y < bind[b].y:
		hips = girdles[1]
		shoulders = girdles[0]
		var swap := head
		head = tail
		tail = swap
	# the spine: the way from the hips to the shoulders through the tree
	var up_h: Array = path_to_root.call(int(hips[0]))
	var up_s: Array = path_to_root.call(int(shoulders[0]))
	var common := -1
	for q in up_h:
		if up_s.has(q):
			common = q
			break
	if common < 0:
		return {}
	var spine: Array = up_h.slice(0, up_h.find(common) + 1)
	var rest: Array = up_s.slice(0, up_s.find(common))
	rest.reverse()
	spine.append_array(rest)              # hips ... shoulders
	if spine.size() < 2:
		return {}
	# the neck: the head's way up to the shoulders (or to the spine where it leaves it)
	var neck: Array = []
	var q := head
	while q >= 0 and not spine.has(q):
		neck.append(q)
		q = parent[q]
	neck.reverse()                        # from the spine out to the head's end
	var out := {}
	var hip := int(spine[0])
	var sh := int(spine[spine.size() - 1])
	out["pelvis"] = [hip, int(spine[1])]
	if spine.size() >= 3:
		out["spine"] = [int(spine[1]), int(spine[2])]
	if spine.size() >= 4:
		out["chest"] = [int(spine[spine.size() - 3]), int(spine[spine.size() - 2])]
	if not neck.is_empty():
		out["upper_chest"] = [sh, int(neck[0])]
		# the head joint: the last of the chain with two or more children (the jaw leaves it), else the one before the end
		var hj: int = neck[neck.size() - 2] if neck.size() >= 2 else neck[0]
		for k in neck:
			if (kids[k] as Array).size() >= 2 and k != neck[0]:
				hj = k
		var nj: int = neck[0] if neck[0] != hj else sh
		out["neck"] = [nj, hj]
		out["head"] = [hj, -1]
		out["frame_head"] = hj
	else:
		return {}
	# the tail: from the hips' remaining branch
	var tq := tail
	var tchain: Array = []
	while tq >= 0 and not spine.has(tq):
		tchain.append(tq)
		tq = parent[tq]
	tchain.reverse()
	if tchain.size() >= 2:
		out["tail"] = [int(tchain[0]), int(tchain[1])]
	var leg := func(root: int, names: Array) -> Array:
		var chain := [root]
		var j := root
		while not (kids[j] as Array).is_empty():
			var best: int = kids[j][0]
			for c in kids[j]:
				if lo[c] < lo[best]:
					best = c
			j = best
			chain.append(j)
		if chain.size() < 3:
			return []
		var toe: int = chain[-1]
		var foot: int = chain[-2] if chain.size() >= 4 else chain[-1]
		var knee: int = chain[1]
		var mid := (bind[root].z + bind[foot].z) * 0.5
		for k in range(1, chain.size() - 1):
			if chain[k] != foot and absf(bind[chain[k]].z - mid) < absf(bind[knee].z - mid):
				knee = chain[k]
		out[names[0]] = [root, knee]
		out[names[1]] = [knee, foot]
		if foot != toe:
			out[names[2]] = [foot, toe]
		return chain
	var lh: Array = leg.call(int(hips[1]), ["left_thigh", "left_calf", "left_foot"])
	var rh: Array = leg.call(int(hips[2]), ["right_thigh", "right_calf", "right_foot"])
	leg.call(int(shoulders[1]), ["left_upper_arm", "left_forearm", "left_hand"])
	leg.call(int(shoulders[2]), ["right_upper_arm", "right_forearm", "right_hand"])
	if lh.is_empty() or rh.is_empty():
		return {}
	out["frame_toes"] = [lh[-1], rh[-1]]
	out["frame_left"] = int(hips[1])
	out["frame_right"] = int(hips[2])
	return out
