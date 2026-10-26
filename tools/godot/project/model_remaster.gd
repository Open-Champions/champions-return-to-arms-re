extends Node
# model_remaster.gd - the game's own figures remastered (look.remaster_models = on | off; scene mode, Remastered only:
# the Classic look sets it off).
#
# Every skinned figure the game draws - the players, the monsters, the people - is taken from the frame (RtaRemaster.scan:
# per object its bind-pose packets, the skeleton that poses it) and, once per model, baked on this machine into a smooth
# mesh of the same shape (RtaRemaster.bake_start: Loop subdivision with the model's hard edges kept as creases, fitted
# through the game's own vertices, skin weights subdivided with it; rta_remaster.h).  Then the game's own skinned packets
# of that object are left out of the drawer's frame (RtaDrawer.set_hidden_skinned: what it holds - a rigid weapon - stays
# the game's; a figure er_layer.gd replaces is left to it) and the baked mesh is drawn in their place, skinned every frame
# by the very matrices the game's own vertex program used (RtaRemaster.pose): the animation is the game's to the vertex.
# Its colour is the game's own texture as that draw has it (the art pack's 4x picture where there is one:
# RtaDrawer.get_piece_textures), with two maps derived from that picture here (normal, ORM: RtaRemaster.derive_maps), lit
# as the outfit pieces are (shaders/remaster_model.gdshader).  The packets drawn with one texture state are one surface
# (RtaRemaster.merge).  Elden Ring / Tripo outfits (er_layer.gd, er_fit.gd) still dress the figure: a fitted outfit's
# pieces are drawn over the body.
#
# Nothing is kept with the program: the baked meshes and maps go to the user data folder (user://model-remaster/), made
# from the player's own disc as it plays.  Per model choices are ours, in model_remaster.cfg (tracked; no game data).
# Levels: 0 is the game's own mesh, then each split 1 -> 4 (as many as stay under max_tris); the finest is drawn within
# lod_near units of the eye, the one below it (not 0) out to lod_far, level 0 beyond.  Nothing here reaches the
# simulation (two copies in a room stay in step with it on or off).

const OWN_LAYER := 1 << 19
const CLASS_NAMES := ["barbarian", "cleric", "shadowknight", "ranger", "wizard", "berserker", "shaman"]
const CACHE := "user://model-remaster"
const MESH_VERSION := 6         # 3: welded within a tolerance, T-junctions split; 4: covered layers drawn inside; 5: decals; 6: welded only where skinned alike
const MAPS_VERSION := 4         # of the derived maps (in the cache's names): 3 = seven classes, the AUX map; 4 = strands on a face are skin
const G_PLAYERS := 0x4D8AF0     # the player records (record +0x54: the figure chosen, 0..11)
const PLAYER_RECORD := 0x4C30

var main: Node
var view: Node                  # scene_view.gd
var er: Node                    # er_layer.gd (what it leaves out, its light of a figure, its scene info)
var machine: RtaMachine
var drawer: Object
var rm: RefCounted              # RtaRemaster
var cfg: ConfigFile
var shader: Shader
var scenario: RID
var on := false
var bakes := {}                 # model key -> {state: running|ready|failed, name, levels: [[packet arrays]], piece_keys, merged}
var figs := {}                  # figure id (state:n) -> {instance, skeleton, key, gkey, level, seen, order, mats}
var packets := {}               # packet key -> its material's signature
var packet_draw := {}           # packet key -> the texture and state it was last drawn with
var packet_tex := {}             # packet key -> the texture id its signature was made with
var templates := {}             # signature -> {params, version, maps_key, maps_set}
var maps := {}                  # texture|class|options -> {state, since, rid, size, job, normal, orm}
var maps_running := 0
var targets: Array = []
var scan_now := {}
var hide_sent := false
var unstable := {}              # figure id -> {key, changes}
var options_of := {}
var said := {}
var frame_no := 0
var cost_sum := 0
var cost_frames := 0
var cost_worst := 0
var figures_sum := 0
var spent := 0
var debug := OS.get_environment("RTA_REMASTER_DEBUG") == "1"
var forced_off := OS.get_environment("RTA_REMASTER_MODELS") == "off"     # (tests: a copy without it, whatever the look says)
var dump_dir := OS.get_environment("RTA_REMASTER_DUMP")         # (tuning: each texture's picture and its classes, into this folder)
var aim := {}                   # app remaster aim: {name, pull, orbit, raise, height} - the camera on a figure of that name
var aim_said := ""
var part_us := {}               # where the layer's own time goes (info_text)
var packets_version := 0
var merges_running := 0
var io_tasks: Array = []
var settled := {}               # figure id|key -> the frame its packets were last all found with their materials
var dressed := {}               # this frame: objects er_layer.gd dresses in a fitted outfit
var seek := {}                  # app remaster seek: {name} - the player walked (the script's controller) to a figure of that name


func _ready() -> void:
	machine = main.machine
	drawer = main.drawer
	rm = ClassDB.instantiate("RtaRemaster") if ClassDB.class_exists("RtaRemaster") else null
	cfg = ConfigFile.new()
	if cfg.load("res://model_remaster.cfg") != OK:
		cfg = ConfigFile.new()
	# (tests) RTA_REMASTER_SET="key=value,...": choices over every figure's, without editing model_remaster.cfg
	for kv in OS.get_environment("RTA_REMASTER_SET").split(",", false):
		var k := kv.get_slice("=", 0)
		var v := kv.get_slice("=", 1)
		cfg.set_value("default", k, v.to_float() if v.is_valid_float() else v)
	shader = load("res://shaders/remaster_model.gdshader")
	DirAccess.make_dir_recursive_absolute(CACHE + "/mesh")
	DirAccess.make_dir_recursive_absolute(CACHE + "/maps")
	if rm == null:
		print("rta_godot: remaster: the extension has no RtaRemaster: the game's own figures stay as they are")


func _opt(name: String) -> Dictionary:
	if options_of.has(name):
		return options_of[name]
	var o := {"off": false, "levels": 2, "crease": 0.5, "fit": 8, "keep": 1.0, "max_tris": 80000, "lod_near": 260.0, "lod_far": 1200.0,
		"class": "auto", "strength": 1.6, "metal": 0.85, "rough": 1.0, "gain": 1.0, "bump": 1.0, "cavity": 1.0, "game_light": 1.0,
		"strands": "hair" if name.begins_with("player") else "fur", "stone": false, "skin_hue_lo": -0.03, "skin_hue_hi": 0.105,
		"skin_v_lo": 0.42, "skin_s_hi": 0.7, "grey_metal": true, "gold": true,
		"sss": 1.0, "sheen": 1.0, "spec": 1.0, "shrink": 0.0, "dressed_shrink": 0.35, "game_match": 1.0, "scene_keep": 1.0, "game_sh": true, "fine": 8, "layer_reach": 2.0, "layer_gap": 0.0, "game_dir_sign": 1.0, "debug_view": 0}
	var sections := ["default"]
	var parts := name.split(".")
	for i in parts.size():
		sections.append(".".join(parts.slice(0, i + 1)))
	for s in sections:
		if cfg.has_section(s):
			for k in cfg.get_section_keys(s):
				o[k] = cfg.get_value(s, k)
	o["name"] = name
	options_of[name] = o
	return o


func _name_of(f: Dictionary) -> String:
	for p in scan_now.get("players", []):
		# a player's figure is posed by an animation state inside its creature (er_layer.gd _find_player)
		var off := int(f.state) - int(p.get("object", 0))
		if int(p.state) == int(f.state) or (int(p.get("object", 0)) != 0 and off >= 0 and off < 0x800):
			var c := int(p.character_class)
			var figure := int(machine.peek_u32(G_PLAYERS + int(p.slot) * PLAYER_RECORD + 0x54))
			return "player.%s.%d" % [CLASS_NAMES[c] if c >= 0 and c < CLASS_NAMES.size() else str(c), figure]
	if er != null and er.has_method("_identity"):
		var id: Dictionary = er.call("_identity", {"state": int(f.state)})
		if String(id.get("class", "")) != "":
			return "creature." + String(id.class)
	return "creature.unknown"


# ---------------------------------------------------------------------------------------------------------------------
# Before the drawer takes the frame: which figures are drawn here (their skinned packets left out of the drawer's frame).
func before_frame() -> void:
	var started := Time.get_ticks_usec()
	frame_no += 1
	var er_hide: PackedInt64Array = er.get("last_hide") if er != null and er.get("last_hide") != null else PackedInt64Array()
	on = rm != null and view != null and String(view.look.get("remaster_models", "on")) == "on" and not forced_off
	targets = []
	if not on:
		scan_now = rm.call("scan", machine) if rm != null and not (aim.is_empty() and seek.is_empty()) else {}
		if not (aim.is_empty() and seek.is_empty()):
			var per := {}
			for f in scan_now.get("figures", []):
				var st0 := int(f.state)
				f["id"] = "%x:%d" % [st0, int(per.get(st0, 0))]
				per[st0] = int(per.get(st0, 0)) + 1
				f["name"] = _name_of(f)
			_aim()
			_seek()
		if hide_sent:
			drawer.call("set_hidden_skinned", PackedInt64Array())
			hide_sent = false
		spent = Time.get_ticks_usec() - started
		return
	scan_now = rm.call("scan", machine)
	var t_scan := Time.get_ticks_usec()
	part_us["scan"] = int(part_us.get("scan", 0)) + t_scan - started
	_poll_bakes()
	_poll_loads()
	while not io_tasks.is_empty() and WorkerThreadPool.is_task_completed(int(io_tasks[0])):
		WorkerThreadPool.wait_for_task_completion(int(io_tasks.pop_front()))
	var hide := PackedInt64Array()
	var er_set := {}
	for o in er_hide:
		er_set[o] = true
	var per_state := {}
	for f in scan_now.get("figures", []):
		var obj := int(f.object)
		# the scene's object numbers are the frame's own: a figure is known from frame to frame by its animation state
		# (a guest address) and its place among that state's objects
		var st := int(f.state)
		var nth := int(per_state.get(st, 0))
		per_state[st] = nth + 1
		f["id"] = "%x:%d" % [st, nth]
		if er_set.has(obj):
			continue
		var name := _name_of(f)
		f["name"] = name
		if debug and not said.has(name):
			said[name] = true
			print("rta_godot: remaster: first %s (%d joints, %d corners) in %s" % [name, int(f.joints), int(f.corners), machine.peek_string(0x41B721, 16)])
		var o := _opt(name)
		if bool(o.off):
			continue
		var key := String(f.key)
		var u: Dictionary = unstable.get(f.id, {})
		if u.is_empty() or String(u.key) != key:
			unstable[f.id] = {"key": key, "changes": int(u.get("changes", -1)) + 1}
		if int(unstable[f.id].changes) > 6:
			continue                    # a model that keeps changing (moving texture coordinates): the game's own
		if not bakes.has(key) or String(bakes[key].state) == "stale":
			if bakes.has(key) or not _load_cached(key, name):
				if int(rm.call("bakes_running")) >= 2:
					continue
				var k2 := String(rm.call("bake_start", machine, obj, _bake_options(o)))
				if k2 != "":
					bakes[key] = {"state": "running", "name": name, "started": Time.get_ticks_msec()}
			continue
		var b: Dictionary = bakes[key]
		if String(b.state) != "ready" or not _materials_ready(f) or _merged(b, name).is_empty():
			continue
		f["bake"] = b
		hide.append(obj)
		targets.append(f)
	if debug and frame_no % 240 == 0:
		var lines := PackedStringArray()
		for f in scan_now.get("figures", []):
			var b: Dictionary = bakes.get(String(f.key), {})
			var nu := 0
			for u in (f.get("under", PackedInt32Array()) as PackedInt32Array):
				nu += 1 if int(u) >= 0 else 0
			lines.append("%x %s %s %s %d packets %d corners bake %s materials %s; %d shiny, %d over a first pass; rigid, unskinned, first passes %s" % [int(f.object),
				String(f.get("id", "?")), String(f.get("name", "?")), String(f.key), (f.pieces as PackedInt32Array).size(), int(f.corners), String(b.get("state", "-")),
				str(_materials_ready(f)), (f.get("shiny", PackedInt32Array()) as PackedInt32Array).size(), nu, str(f.get("passes", ""))])
		print("rta_godot: remaster: frame %d: %d figures, %d drawn here (players %s):\n  %s" % [frame_no, (scan_now.get("figures", []) as Array).size(), targets.size(),
			str(scan_now.get("players", [])), "\n  ".join(lines)])
		print("rta_godot: remaster: left to the game: %s" % str(scan_now.get("rejected", [])))
	_aim()
	_seek()
	if not targets.is_empty() or hide_sent:
		drawer.call("set_hidden_skinned", hide)
		hide_sent = not targets.is_empty()
	spent = Time.get_ticks_usec() - started
	part_us["choose"] = int(part_us.get("choose", 0)) + Time.get_ticks_usec() - t_scan


# (tests) app remaster aim NAME [SIZES [ORBIT [RAISE]]] | aim off: the camera on the figure whose name has NAME in it
# (nearest the player at first, then the same one while it is in the frame), SIZES times its height away
func command(w: PackedStringArray) -> void:
	if w.size() >= 3 and w[1] == "aim":
		if w[2] == "off":
			aim = {}
			drawer.call("set_scene_option", "aim", 0.0)
			drawer.call("set_scene_option", "orbit", 0.0)
			drawer.call("set_scene_option", "raise", 0.0)
			return
		aim = {"name": w[2].to_lower(), "sizes": w[3].to_float() if w.size() >= 4 else 2.2, "id": "", "up": w[6].to_float() if w.size() >= 7 else 0.5}
		drawer.call("set_scene_option", "orbit", w[4].to_float() if w.size() >= 5 else 0.0)
		drawer.call("set_scene_option", "raise", w[5].to_float() if w.size() >= 6 else 8.0)
	elif w.size() >= 3 and w[1] == "seek":
		seek = {} if w[2] == "off" else {"name": w[2].to_lower(), "near": w[3].to_float() if w.size() >= 4 else 90.0}
		main.call("_joy_state", 0, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
	elif w.size() >= 2 and w[1] == "info":
		print("rta_godot: remaster: aim %s; %s" % [str(aim), info_text()])


# (tests) the script's controller (app gcpad connect) walks the player to the nearest figure of the name, and stops near it
func _seek() -> void:
	if seek.is_empty():
		return
	var view: Dictionary = machine.get_view()
	var feet: Vector3 = view.get("player", Vector3.ZERO)
	var fwd: Vector3 = view.get("forward", Vector3(0, 1, 0))
	fwd.z = 0.0
	var best := 1e30
	var to := Vector3.ZERO
	for f in scan_now.get("figures", []):
		if not String(f.get("name", "")).to_lower().contains(String(seek.name)):
			continue
		var d: Vector3 = (f.root as Vector3) - feet
		d.z = 0.0
		if d.length() < best:
			best = d.length()
			to = d
	var stick := Vector2.ZERO
	if best < 1e29 and best > float(seek.near) and fwd.length() > 0.01:
		fwd = fwd.normalized()
		var right := fwd.cross(Vector3(0, 0, 1))
		var dn := to.normalized()
		stick = Vector2(dn.dot(right), -dn.dot(fwd)).normalized()
	main.call("_joy_state", 0, [stick.x, stick.y, 0.0, 0.0, 0.0, 0.0])
	seek["distance"] = best


func _aim() -> void:
	if aim.is_empty():
		return
	var figures: Array = scan_now.get("figures", [])
	var pick: Dictionary = {}
	for f in figures:
		if String(f.get("id", "")) == String(aim.id) and String(f.get("name", "")).to_lower().contains(String(aim.name)):
			pick = f
	if pick.is_empty():
		var feet: Vector3 = machine.get_view().get("player", Vector3.ZERO)
		var best := 1e30
		for f in figures:
			if not String(f.get("name", "")).to_lower().contains(String(aim.name)):
				continue
			var d := feet.distance_to(f.root)
			if d < best:
				best = d
				pick = f
	if pick.is_empty():
		drawer.call("set_scene_option", "aim", 0.0)
		if aim_said != "none " + String(aim.name):
			aim_said = "none " + String(aim.name)
			print("rta_godot: remaster: aim: no %s in the frame" % aim.name)
		return
	aim["id"] = String(pick.id)
	var lo: Vector3 = pick.low
	var hi: Vector3 = pick.high
	var size := maxf(hi.z - lo.z, maxf(hi.x - lo.x, hi.y - lo.y))
	var mid := (lo + hi) * 0.5
	mid.z = lerpf(lo.z, hi.z, float(aim.get("up", 0.5)))
	# SIZES below 20: times the figure's size; else units (the game's chase camera is some 300 units out)
	drawer.call("set_scene_option", "aim", maxf(size, 18.0) * float(aim.sizes) if float(aim.sizes) < 20.0 else float(aim.sizes))
	drawer.call("set_scene_option", "aim_x", mid.x)
	drawer.call("set_scene_option", "aim_y", mid.y)
	drawer.call("set_scene_option", "aim_z", mid.z)
	# from the far side of the figure from the player (the player not in between)
	var away: Vector3 = mid - (machine.get_view().get("player", mid) as Vector3)
	away.z = 0.0
	if away.length() > 5.0:
		away = away.normalized()
		drawer.call("set_scene_option", "aim_dx", away.x)
		drawer.call("set_scene_option", "aim_dy", away.y)
	else:
		drawer.call("set_scene_option", "aim_dx", 0.0)
		drawer.call("set_scene_option", "aim_dy", 0.0)
	if aim_said != String(pick.id):
		aim_said = String(pick.id)
		print("rta_godot: remaster: aim at %s %s (%.0f units, at %s)" % [String(pick.get("name", "")), String(pick.id), size, str(mid)])


func _materials_ready(f: Dictionary) -> bool:
	for pk in f.piece_keys:
		if not packets.has(String(f.name) + "|" + String(pk)):
			return false                # not drawn yet: its texture is not known
	return true


func _poll_bakes() -> void:
	for key in bakes:
		var b: Dictionary = bakes[key]
		if String(b.state) != "running":
			continue
		var r: Dictionary = rm.call("bake_take", key)
		if r.is_empty():
			continue
		if r.has("failed"):
			b["state"] = "failed"
			print("rta_godot: remaster: %s (%s) not baked: %s" % [b.name, key, r.failed])
			continue
		var levels: Array = []
		for L in r.levels:
			levels.append(L.surfaces)
		b["state"] = "ready"
		b["levels"] = levels
		b["piece_keys"] = r.piece_keys
		b["decals"] = r.get("decals", PackedInt32Array())
		b["merged"] = {}
		_save_cached(key, b)
		print("rta_godot: remaster: %s baked (%s): %s" % [b.name, key, r.stats])


# the baked model in the user data folder: its levels, a set of Mesh arrays a packet ([] for an empty one).  Written and
# read on worker threads (a dense model is megabytes: on the main thread it held up a frame).
# (the file is named by the model and the choices it was baked with: a changed choice bakes it again)
func _bake_options(o: Dictionary) -> Dictionary:
	return {"levels": int(o.levels), "crease": float(o.crease), "fit": int(o.fit), "keep": float(o.keep), "max_tris": int(o.max_tris),
		"layer_reach": float(o.layer_reach), "layer_gap": float(o.layer_gap)}


func _cache_path(key: String, name: String) -> String:
	return "%s/mesh/%s-%s.bin" % [CACHE, key, str(_bake_options(_opt(name))).md5_text().substr(0, 8)]


func _save_cached(key: String, b: Dictionary) -> void:
	var data := {"version": MESH_VERSION, "piece_keys": b.piece_keys, "levels": b.levels, "decals": b.get("decals", PackedInt32Array())}
	var path := _cache_path(key, String(b.name))
	io_tasks.append(WorkerThreadPool.add_task(func():
		var file := FileAccess.open(path, FileAccess.WRITE)
		if file != null:
			file.store_var(data)
			file.close(), false, "remaster save"))


func _load_cached(key: String, name: String) -> bool:
	var path := _cache_path(key, name)
	if not FileAccess.file_exists(path):
		return false
	var job := {"path": path, "out": null}
	job["task"] = WorkerThreadPool.add_task(func():
		var file := FileAccess.open(job.path, FileAccess.READ)
		if file != null:
			job["out"] = file.get_var()
			file.close(), false, "remaster load")
	bakes[key] = {"state": "loading", "name": name, "job": job}
	return true


func _poll_loads() -> void:
	for key in bakes:
		var b: Dictionary = bakes[key]
		if String(b.state) != "loading" or not WorkerThreadPool.is_task_completed(int(b.job.task)):
			continue
		WorkerThreadPool.wait_for_task_completion(int(b.job.task))
		var d = b.job.out
		b.erase("job")
		if not (d is Dictionary) or int(d.get("version", 0)) != MESH_VERSION or not d.has("levels"):
			b["state"] = "stale"            # baked again (below, when next seen)
			continue
		b["state"] = "ready"
		b["levels"] = d.levels
		b["piece_keys"] = d.piece_keys
		b["decals"] = d.get("decals", PackedInt32Array())
		b["merged"] = {}
		print("rta_godot: remaster: %s from the cache (%s, %d levels)" % [b.name, key, (d.levels as Array).size()])


# ---------------------------------------------------------------------------------------------------------------------
# After the drawer took the frame: the textures the game drew each packet with, the figures drawn.
func frame(to_scenario: RID) -> void:
	var started := Time.get_ticks_usec()
	if to_scenario != scenario:
		release()
		scenario = to_scenario
	if not on:
		_hide_all()
		return
	# a figure whose packets all have their materials (with maps) is looked at again only every 30 frames (a crowd of
	# figures is thousands of packets: going through them every frame was most of this layer's time)
	var todo: Array = []
	for f in scan_now.get("figures", []):
		var sk := "%s|%s" % [String(f.get("id", "")), String(f.key)]
		if not (settled.has(sk) and frame_no - int(settled[sk]) < 30):
			todo.append(f)
	var tex: Dictionary = drawer.call("get_piece_textures") if not todo.is_empty() else {}
	for f in todo:
		var o := _opt(String(f.get("name", "")))
		var all_set := true
		var keys: PackedStringArray = f.piece_keys
		var pieces: PackedInt32Array = f.pieces
		var ordinal := {}           # the figure's textures numbered in the order of its packets (cfg tex<K>)
		var shiny := {}
		for n in (f.get("shiny", PackedInt32Array()) as PackedInt32Array):
			shiny[n] = true
		# the texture each packet was last drawn with (a packet not drawn in this frame keeps its last); the figure's
		# materials are made once every packet has been seen, so that its textures are numbered the same way every run
		var missing := false
		var under: PackedInt32Array = f.get("under", PackedInt32Array())
		var envs: PackedInt32Array = f.get("env", PackedInt32Array())
		var decal := {}
		for n in ((bakes.get(String(f.key), {}) as Dictionary).get("decals", PackedInt32Array()) as PackedInt32Array):
			decal[int(n)] = true
		for n in keys.size():
			var t0 = tex.get(int(pieces[n]))
			if t0 != null:
				packet_draw[String(keys[n])] = t0
			elif not packet_draw.has(String(keys[n])):
				missing = true
			# the first pass of a two-pass packet: an environment map the second is blended over (the players' sheen)
			if n < envs.size() and int(envs[n]) >= 0:
				var te = tex.get(int(envs[n]))
				if te != null:
					packet_draw[String(keys[n]) + "|env"] = te
			# the first pass of a two-pass packet (a face's own colour, its paint blended over it in the second pass)
			if n < under.size() and int(under[n]) >= 0:
				var tu = tex.get(int(under[n]))
				if tu != null:
					packet_draw[String(keys[n]) + "|under"] = tu
				elif not packet_draw.has(String(keys[n]) + "|under"):
					missing = true
		if missing:
			continue
		for n in keys.size():
			var pk := String(keys[n])
			var t: Array = packet_draw[pk]
			var tex_id: int = (t[0] as RID).get_id()
			if not ordinal.has(tex_id):
				ordinal[tex_id] = ordinal.size()
			# known with this texture: nothing to do (its signature is made only when the texture changes; its template
			# takes its maps when they are made: _maps_tick)
			# (a packet's material is the figure's: two figures of one model - a player and the hub's statue of that
			# class - can have different choices)
			var pkn := String(f.name) + "|" + pk
			var tu: Array = packet_draw.get(pk + "|under", [])
			var te: Array = packet_draw.get(pk + "|env", [])
			var both := tex_id * 1000003 + ((tu[0] as RID).get_id() if not tu.is_empty() else 0) + ((te[0] as RID).get_id() * 7919 if not te.is_empty() else 0)
			if int(packet_tex.get(pkn, -1)) == both and packets.has(pkn) and templates.has(packets[pkn]):
				continue
			packet_tex[pkn] = both
			_packet(pkn, t, o, n, int(ordinal[tex_id]), shiny.has(n), tu, te, decal.has(n))
			all_set = false
		if debug and not said.has("env " + String(f.name)):
			said["env " + String(f.name)] = true
			var ne := 0
			var nt := 0
			for n in keys.size():
				ne += 1 if n < envs.size() and int(envs[n]) >= 0 else 0
				nt += 1 if packet_draw.has(String(keys[n]) + "|env") else 0
			print("rta_godot: remaster: %s: %d packets over an environment map, %d of their maps' textures known" % [String(f.name), ne, nt])
		if keys.size() > 0 and all_set and ordinal.size() > 0:
			settled["%s|%s" % [String(f.get("id", "")), String(f.key)]] = frame_no
	if settled.size() > 4096:
		settled.clear()
	var t_pk := Time.get_ticks_usec()
	part_us["packets"] = int(part_us.get("packets", 0)) + t_pk - started
	var info: Dictionary = er.call("_scene_info") if er != null else drawer.call("get_scene_info")
	var cam: Transform3D = info.get("camera", Transform3D())
	var orders: Dictionary = info.get("hidden_orders", {})
	# the figures er_layer.gd dresses in a fitted outfit (drawn over this body): the body is drawn a little inside itself
	# there (dressed_shrink), so that no part of the smoothed body pokes through the outfit fitted to the game's own mesh
	dressed = {}
	if er != null and er.get("targets") != null:
		for t in er.get("targets"):
			if (t as Dictionary).has("fit"):
				for ob in t.get("objects", PackedInt64Array()):
					dressed[int(ob)] = true
	var by_dist: Array = []
	for f in targets:
		by_dist.append([cam.origin.distance_squared_to(f.root as Vector3), f])
	by_dist.sort_custom(func(a, b): return a[0] < b[0])
	for i in by_dist.size():
		by_dist[i][1]["rank"] = i
	for f in targets:
		_draw(f, cam, orders)
	var t_draw := Time.get_ticks_usec()
	part_us["draw"] = int(part_us.get("draw", 0)) + t_draw - t_pk
	var gone: Array = []
	for id in figs:
		if int(figs[id].seen) != frame_no:
			RenderingServer.instance_set_visible(figs[id].instance, false)
			if frame_no - int(figs[id].seen) > 300:
				gone.append(id)
	for id in gone:
		_free_fig(figs[id])
		figs.erase(id)
	_maps_tick()
	part_us["maps"] = int(part_us.get("maps", 0)) + Time.get_ticks_usec() - t_draw
	var us := Time.get_ticks_usec() - started + spent
	cost_sum += us
	cost_frames += 1
	cost_worst = maxi(cost_worst, us)
	figures_sum += targets.size()


# A packet's material as the game draws it (its texture and that texture's state) and the class it is given: its
# signature.  Packets with one signature share a template (and are one surface of the figure); every figure makes its
# own material from a template (the game's light on each figure differs).
func _packet(pk: String, t: Array, o: Dictionary, part: int, tex_no: int, shiny := false, under: Array = [], env: Array = [], decal := false) -> void:
	# a two-pass packet whose first pass is its own colour: that is the texture (maps, classes), the second pass's
	# picture is laid over it as the game blends it (overlay_tex)
	var over: Array = []
	if not under.is_empty():
		over = t
		t = under
	var texture: RID = t[0]
	# a class, auto, or auto:<class> - by colour, what would be leather or cloth that class (a picture of a body: auto:skin);
	# a packet the game draws with an environment map under it (its first pass, left out with the body) can be told to
	# shine (cfg shiny: a class; the players' bodies have one under most of their packets - a sheen, not metal)
	var said_key := "pk %s %d %s %s" % [String(o.get("name", "")), tex_no, str(t.slice(4)), str(env.size())]
	if debug and not said.has(said_key):
		said[said_key] = true
		print("rta_godot: remaster: %s t%d: %s; env %s; under %s" % [String(o.get("name", "")), tex_no, str(t.slice(1)), str(env.slice(1)) if not env.is_empty() else "-",
			str(under.slice(1)) if not under.is_empty() else "-"])
	var shiny_cls := String(o.get("shiny", ""))
	var cls := String(o.get("part%d" % part, o.get("tex%d" % tex_no, shiny_cls if shiny and shiny_cls != "" else o["class"])))
	var prefer := ""
	if cls.begins_with("auto:"):
		prefer = cls.substr(5)
		cls = "auto"
	var mopts := {"strength": float(o.strength), "class": "" if cls == "auto" else cls, "metal": float(o.metal), "rough": float(o.rough),
		"strands": String(o.strands), "stone": bool(o.stone), "skin_hue_lo": float(o.skin_hue_lo), "skin_hue_hi": float(o.skin_hue_hi),
		"skin_v_lo": float(o.skin_v_lo), "skin_s_hi": float(o.skin_s_hi), "grey_metal": bool(o.grey_metal), "gold": bool(o.gold), "prefer": prefer,
		"rules": Array(o.get("tex%d_rules" % tex_no, [])) + Array(o.get("rules", []))}
	var mk := "%d|%s" % [texture.get_id(), str(mopts)]
	# a packet the game blends over what is behind it by its alpha (GS (Cs - Cd) As + Cd: lashes, a fringe): drawn here
	# with its empty part cut away (an opaque surface showed the picture's black where the game shows nothing)
	var alpha_blend: bool = t.size() > 8 and bool(t[7]) and t[8] == Vector4i(0, 1, 0, 1)
	# (GS Cs + Cd As: the picture plus what is behind it by its alpha - the players' bodies (alpha 0: opaque), and their
	# lashes and brows (dark, alpha high: mostly what is behind) - see-through where dark and mostly behind)
	var add_behind: bool = t.size() > 8 and bool(t[7]) and t[8] == Vector4i(1, 2, 0, 0)
	var sig := ("decal|" if decal else "") + ("ablend|" if alpha_blend else "") + ("addb|" if add_behind else "") + ("over%d|%s|%s|%s|" % [(over[0] as RID).get_id(), str(over[1]), str(over[2]), str(over[3])] if not over.is_empty() else "") + \
		("env%d|%s|%s|%s|" % [(env[0] as RID).get_id(), str(env[1]), str(t[7]), str(t[8]) if t.size() > 9 else ""] if not env.is_empty() and t.size() > 9 else "") + "%d|%s|%s|%s|%s|%d|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s" % [texture.get_id(), str(t[1]), str(t[2]), str(t[3]), str(t[4]), int(t[5]), str(t[6]), mk,
		str(o.gain), str(o.bump), str(o.cavity), str(o.sss), str(o.sheen), str(o.spec), str(o.shrink), str(o.game_match), str(o.scene_keep) + str(o.game_dir_sign) + str(o.debug_view)]
	if String(packets.get(pk, "")) != sig:
		packets_version += 1
	packets[pk] = sig
	if templates.has(sig):
		_template_maps(templates[sig])
		return
	var p := {"gain": float(o.gain), "bump": float(o.bump), "cavity": float(o.cavity), "game_light": float(o.game_light), "metal_amount": 1.0,
		"sss": float(o.sss), "sheen_amount": float(o.sheen), "spec_amount": float(o.spec), "shrink": float(o.shrink),
		"game_match": float(o.game_match), "scene_keep": float(o.scene_keep), "game_dir_sign": float(o.game_dir_sign), "debug_view": int(o.debug_view),
		"albedo_tex": texture, "tex_size": t[1], "tex_offset": t[2], "st_scale": t[3], "cut": float(t[4]), "alpha_from": int(t[5]), "ta0": float(t[6]),
		"has_over": not over.is_empty(), "has_env": false, "lift": 0.0}
	# a decal (eyes, brows, lips: a second picture on the face's own triangles) a hair above the surface, its picture's
	# empty part cut away where the game blends it
	if alpha_blend and float(t[4]) < 0.0:
		p["cut"] = 0.5
	p["see_behind"] = add_behind
	if decal:
		p["lift"] = float(o.get("decal_lift", 0.04))
		if t.size() > 7 and bool(t[7]) and float(t[4]) < 0.0:
			p["cut"] = 0.3
	# the environment map of the first pass, and how the game blends this pass over it (GS: (A - B) * C + D)
	if not env.is_empty() and t.size() > 9 and bool(t[7]):
		p["has_env"] = bool(o.get("env_sheen", true))
		p["env_tex"] = env[0]
		p["blend_abcd"] = t[8]
		p["blend_fix"] = float(t[9]) / 128.0
	if not over.is_empty():
		p["over_tex"] = over[0]
		p["over_size"] = over[1]
		p["over_offset"] = over[2]
		p["over_st"] = over[3]
		p["over_alpha_from"] = int(over[5])
		p["over_ta0"] = float(over[6])
	if not maps.has(mk):
		maps[mk] = {"state": "wait", "since": frame_no, "rid": texture, "size": t[1], "retried": false, "opts": mopts, "who": "%s-t%d" % [String(o.get("name", "")), tex_no]}
	if dump_dir != "":
		var whos: Dictionary = maps[mk].get("whos", {})
		whos["%s-t%d" % [String(o.get("name", "")), tex_no]] = true
		maps[mk]["whos"] = whos
	var tm := {"params": p, "version": 0, "maps_key": mk, "maps_set": false}
	templates[sig] = tm
	_template_maps(tm)


func _template_maps(tm: Dictionary) -> void:
	if bool(tm.maps_set):
		return
	var mp: Dictionary = maps.get(String(tm.maps_key), {})
	if String(mp.get("state", "")) == "done":
		tm.params["normal_tex"] = (mp.normal as Texture2D).get_rid()
		tm.params["mr_tex"] = (mp.orm as Texture2D).get_rid()
		tm.params["has_normal"] = true
		tm.params["has_mr"] = true
		if mp.get("aux") != null:
			tm.params["aux_tex"] = (mp.aux as Texture2D).get_rid()
			tm.params["has_aux"] = true
		tm["maps_set"] = true
		tm["version"] = int(tm.version) + 1


# a figure's own material of a signature, brought up to its template
func _figure_material(g: Dictionary, sig: String) -> RID:
	var own: Dictionary = g.mats
	var e: Dictionary = own.get(sig, {})
	if e.is_empty():
		var rid := RenderingServer.material_create()
		RenderingServer.material_set_shader(rid, shader.get_rid())
		e = {"rid": rid, "version": -1}
		own[sig] = e
	var tm: Dictionary = templates.get(sig, {})
	if not tm.is_empty() and int(e.version) != int(tm.version):
		for k in tm.params:
			RenderingServer.material_set_param(e.rid, k, tm.params[k])
		e["version"] = tm.version
	return e.rid


# the model's levels with its packets gathered by signature (one surface each), made once per grouping
func _merged(b: Dictionary, name: String) -> Dictionary:
	# The model's packets gathered by material signature into surfaces, per level, as meshes.  Building them (the merge
	# and Godot's own conversion of the arrays) is done on a worker thread: on the main thread a dense model held up a
	# frame by tens of milliseconds.  Until the grouping of the current materials is ready the last one stays in use;
	# {} when there has been none yet (the figure stays the game's).
	var mine: Dictionary = (b.get("by_name", {}) as Dictionary).get(name, {})
	if mine.is_empty():
		mine = {"version": -1, "last": {}}
		if not b.has("by_name"):
			b["by_name"] = {}
		b.by_name[name] = mine
	if int(mine.version) == packets_version:
		return mine.last
	var sigs: Array = []
	var group_of := {}
	var groups := PackedInt32Array()
	for pk in b.piece_keys:
		var sig := String(packets.get(name + "|" + String(pk), ""))
		if not group_of.has(sig):
			group_of[sig] = sigs.size()
			sigs.append(sig)
		groups.append(int(group_of[sig]))
	var gkey := "|".join(PackedStringArray(sigs))
	var merged: Dictionary = b.merged
	if merged.has(gkey):
		mine["version"] = packets_version
		mine["last"] = merged[gkey]
		return merged[gkey]
	var job: Dictionary = b.get("merge_job", {})
	if job.is_empty() or String(job.gkey) != gkey:
		if not job.is_empty():
			return mine.last                        # one at a time per model: the one running finishes first
		if merges_running >= 2:
			return mine.last
		job = {"gkey": gkey, "sigs": sigs, "groups": groups, "levels": b.levels, "out": []}
		job["task"] = WorkerThreadPool.add_task(_merge_task.bind(job), false, "remaster merge")
		merges_running += 1
		b["merge_job"] = job
		return mine.last
	if not WorkerThreadPool.is_task_completed(int(job.task)):
		return mine.last
	WorkerThreadPool.wait_for_task_completion(int(job.task))
	merges_running -= 1
	b.erase("merge_job")
	var m := {"gkey": gkey, "meshes": job.out, "sigs": sigs}
	merged[gkey] = m
	mine["version"] = packets_version
	mine["last"] = m
	return m


func _merge_task(job: Dictionary) -> void:
	var meshes: Array = []
	for surfaces in job.levels:
		var out: Array = rm.call("merge", surfaces, job.groups, (job.sigs as Array).size())
		var mesh := ArrayMesh.new()
		var sg := PackedInt32Array()
		for gi in out.size():
			var arrays: Array = out[gi]
			if arrays[Mesh.ARRAY_VERTEX] != null:
				mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
				sg.append(gi)
		mesh.set_meta("surface_group", sg)
		meshes.append(mesh)
	job["out"] = meshes


func _draw(f: Dictionary, cam: Transform3D, orders: Dictionary) -> void:
	var obj := int(f.object)
	var g: Dictionary = figs.get(String(f.id), {})
	if g.is_empty():
		g = {"instance": RenderingServer.instance_create(), "skeleton": RenderingServer.skeleton_create(), "gkey": "", "level": -1, "seen": 0, "order": -1.0, "mats": {}}
		RenderingServer.instance_set_scenario(g.instance, scenario)
		RenderingServer.instance_set_layer_mask(g.instance, 1 | OWN_LAYER)
		RenderingServer.instance_geometry_set_cast_shadows_setting(g.instance, RenderingServer.SHADOW_CASTING_SETTING_ON)
		RenderingServer.instance_attach_skeleton(g.instance, g.skeleton)
		figs[String(f.id)] = g
	var o := _opt(String(f.name))
	var root: Vector3 = f.root
	var m := _merged(f.bake, String(f.name))
	if m.is_empty():
		return
	var meshes: Array = m.meshes
	var top := meshes.size() - 1
	var dist := cam.origin.distance_to(root)
	# the finest level near the eye, the one below it (never the game's own, unless there is no other) further out, the
	# game's own mesh far away; a margin either way, so that a figure at a border does not flicker between two
	var was := int(g.level)
	var near := float(o.lod_near) * (1.1 if was == top else 0.9)
	var far := float(o.lod_far) * (1.1 if was != 0 else 0.9)
	var level := top if dist < near else (maxi(top - 1, mini(top, 1)) if dist < far else 0)
	# a crowd: only the `fine` figures nearest the eye get the finest level, the rest the one below it
	if level == top and top > 1 and int(f.get("rank", 0)) >= int(o.fine):
		level = top - 1
	if String(g.gkey) != String(m.gkey) or was != level:
		var mesh: ArrayMesh = meshes[level]
		RenderingServer.instance_set_base(g.instance, mesh.get_rid())
		var sg: PackedInt32Array = mesh.get_meta("surface_group")
		for s in mesh.get_surface_count():
			RenderingServer.instance_set_surface_override_material(g.instance, s, _figure_material(g, String(m.sigs[sg[s]])))
		g["gkey"] = m.gkey
		g["level"] = level
	rm.call("pose", machine, int(f.skeleton), g.skeleton)
	# the game's light on the figure: looked up every third frame (it walks the level's light grid; a crowd of figures
	# each frame was a millisecond and more), staggered over the figures
	# The game's light on the figure: fitted from its vertex program's colours (RtaRemaster.light_sh: exactly as bright as
	# the game's figure) and er_layer.gd's model of it (the sun's direction for the highlights) - looked at every second
	# frame, staggered over the figures (a crowd each frame: a millisecond and more of material parameters)
	var light: Dictionary
	var period := 2 if int(f.get("rank", 0)) < 4 else 4         # (the nearest four every second frame, the rest every fourth)
	if g.has("light") and (frame_no + int(g.get("stagger", 0))) % period != 0:
		light = g.light
	else:
		light = er.call("_game_light", int(f.state), root) if er != null and er.has_method("_game_light") else {}
		light["shrink"] = float(o.dressed_shrink) if dressed.has(obj) else float(o.shrink)
		var sh: PackedVector4Array = rm.call("light_sh", machine, f.pieces) if bool(o.game_sh) else PackedVector4Array()
		light["has_sh"] = sh.size() == 9
		if sh.size() == 9:
			light["game_sh"] = sh
	if not g.has("stagger"):
		g["stagger"] = figs.size() % 4
		if debug:
			print("rta_godot: remaster: %s %s: the game's light %s" % [String(f.name), String(f.id), str(light)])
	# (the figure's light set only when it changed or a material was made again: a crowd of figures, each with a few
	# materials, would otherwise cost thousands of calls a frame)
	var fresh := false
	for sig in m.sigs:
		var e: Dictionary = (g.mats as Dictionary).get(String(sig), {})
		var tm: Dictionary = templates.get(String(sig), {})
		if e.is_empty() or (not tm.is_empty() and int(e.version) != int(tm.version)):
			fresh = true
	if fresh or not is_same(light, g.get("light")) or String(g.gkey) != String(g.get("light_gkey", "")):
		for sig in m.sigs:
			var rid := _figure_material(g, String(sig))
			for k in light:
				RenderingServer.material_set_param(rid, k, light[k])
		g["light"] = light
		g["light_gkey"] = g.gkey
	# at the place of the figure's own first draw among the world's (the drawer's transparent pass keeps the list's order)
	if orders.has(obj):
		g["order"] = float(orders[obj])
	RenderingServer.instance_set_pivot_data(g.instance, float(g.order) + 0.5 if float(g.order) >= 0.0 else 1.0e6, false)
	RenderingServer.instance_set_custom_aabb(g.instance, AABB(root - Vector3(160, 160, 160), Vector3(320, 320, 320)))
	RenderingServer.instance_set_visible(g.instance, true)
	g["seen"] = frame_no


# the maps of a texture: derived once its art-pack picture has arrived (or, without one, from the game's own pixels),
# on a worker thread; kept in the user data folder by the picture's hash
func _maps_tick() -> void:
	for mk in maps:
		var mp: Dictionary = maps[mk]
		if String(mp.state) == "running":
			if WorkerThreadPool.is_task_completed(int(mp.task)):
				WorkerThreadPool.wait_for_task_completion(int(mp.task))
				maps_running -= 1
				var out: Dictionary = mp.job.out
				if out.has("normal"):
					var made: Dictionary = out.get("textures", {})
					for k in ["normal", "orm", "aux"]:
						mp[k] = made[k] if made.has(k) else (ImageTexture.create_from_image(out[k]) if out.get(k) != null else null)
					for sig in templates:
						if String(templates[sig].maps_key) == String(mk):
							_template_maps(templates[sig])
					mp["state"] = "done"
					mp["md5"] = String(mp.job.get("md5", ""))
					if debug:
						print("rta_godot: remaster: maps %dx%d %s%s" % [(out.normal as Image).get_width(), (out.normal as Image).get_height(), str(out.get("classes", "")),
							" (from the cache)" if out.get("cached", false) else ""])
				else:
					mp["state"] = "failed"
				mp.erase("job")
			continue
		if String(mp.state) != "wait" or frame_no - int(mp.since) < 45 or maps_running >= 2:
			continue
		var img := RenderingServer.texture_2d_get(mp.rid)
		if img == null or img.is_empty():
			mp["state"] = "failed"
			continue
		var size: Vector2 = mp.size
		if img.get_width() < int(size.x) * 2 and not bool(mp.retried) and main != null and int(main.get("art_pictures")) > 0:
			mp["retried"] = true            # the art pack's picture may not have arrived yet: once more, later
			mp["since"] = frame_no + 150
			continue
		var opts: Dictionary = (mp.opts as Dictionary).duplicate()
		opts["scale"] = maxf(1.0, float(img.get_width()) / maxf(1.0, size.x))
		var job := {"img": img, "opts": opts, "out": {}, "who": String(mp.get("who", ""))}
		mp["job"] = job
		mp["task"] = WorkerThreadPool.add_task(_derive.bind(job), false, "remaster maps")
		mp["state"] = "running"
		maps_running += 1


# on a worker thread: the maps, then their textures made there as well (a 4096 picture's three textures with their mip
# maps were a stall of a tenth of a second on the main thread); ORM and AUX at half size past 2048 (they are smooth)
func _derive(job: Dictionary) -> void:
	_derive_images(job)
	var out: Dictionary = job.out
	if not out.has("normal"):
		return
	for k in ["orm", "aux"]:
		var im: Image = out.get(k)
		if im != null and im.get_width() > 2048:
			im = im.duplicate()
			im.clear_mipmaps()
			im.resize(im.get_width() / 2, im.get_height() / 2, Image.INTERPOLATE_BILINEAR)
			im.generate_mipmaps()
			out[k] = im
	var tex := {}
	for k in ["normal", "orm", "aux"]:
		if out.get(k) != null:
			tex[k] = ImageTexture.create_from_image(out[k])
	out["textures"] = tex


func _derive_images(job: Dictionary) -> void:
	var img: Image = job.img
	var hc := HashingContext.new()
	hc.start(HashingContext.HASH_MD5)
	hc.update(img.get_data())
	var o: Dictionary = job.opts
	var md5 := hc.finish().hex_encode()
	job["md5"] = md5
	var opt_hash := str(o).md5_text().substr(0, 10)
	var tag := "v%d-%s-%dx%d-%s" % [MAPS_VERSION, md5, img.get_width(), img.get_height(), opt_hash]
	var base := "%s/maps/%s" % [CACHE, tag]
	# (tuning: a picture not yet in the dump folder is derived again, to be written there with its classes)
	var need_dump := dump_dir != "" and not FileAccess.file_exists("%s/%s.done" % [dump_dir, md5.substr(0, 8)])
	if not need_dump and FileAccess.file_exists(base + "-n.png") and FileAccess.file_exists(base + "-orm.png") and FileAccess.file_exists(base + "-aux.png"):
		var n := Image.load_from_file(base + "-n.png")
		var r := Image.load_from_file(base + "-orm.png")
		var a := Image.load_from_file(base + "-aux.png")
		if n != null and r != null and a != null:
			n.generate_mipmaps()
			r.generate_mipmaps()
			a.generate_mipmaps()
			job.out = {"normal": n, "orm": r, "aux": a, "cached": true}
			return
	if need_dump:
		o["class_picture"] = true
	var out: Dictionary = rm.call("derive_maps", img, o)
	if out.has("normal"):
		for k in ["normal", "orm", "aux"]:
			var i0: Image = (out[k] as Image).duplicate()
			i0.clear_mipmaps()
			i0.save_png(base + {"normal": "-n.png", "orm": "-orm.png", "aux": "-aux.png"}[k])
		if need_dump:
			# tuning (local): the picture, its classes and the options, named by the figure and the packet that first used it
			DirAccess.make_dir_recursive_absolute(dump_dir)
			var stem := "%s/%s-%s" % [dump_dir, String(job.who).replace("/", "_"), md5.substr(0, 8)]
			var a0: Image = img.duplicate()
			a0.clear_mipmaps()
			a0.save_png(stem + "-albedo.png")
			if out.get("class_picture") != null:
				(out.class_picture as Image).save_png(stem + "-class.png")
			var f := FileAccess.open(stem + ".txt", FileAccess.WRITE)
			if f != null:
				f.store_string("%s\n%s\n" % [str(o), str(out.get("classes", {}))])
				f.close()
			FileAccess.open("%s/%s.done" % [dump_dir, md5.substr(0, 8)], FileAccess.WRITE)
	job.out = out


# between two game frames: the poses carried on as the drawer carries the world (RtaDrawer.redraw)
func tween(t: float) -> void:
	for id in figs:
		if int(figs[id].seen) == frame_no:
			rm.call("tween", figs[id].skeleton, t)


func _hide_all() -> void:
	for id in figs:
		RenderingServer.instance_set_visible(figs[id].instance, false)


func _free_fig(g: Dictionary) -> void:
	RenderingServer.free_rid(g.instance)
	if rm != null:
		rm.call("forget", g.skeleton)
	RenderingServer.free_rid(g.skeleton)
	for sig in g.mats:
		RenderingServer.free_rid(g.mats[sig].rid)


func release() -> void:
	for id in figs:
		_free_fig(figs[id])
	figs.clear()


func info_text() -> String:
	var ready := 0
	for k in bakes:
		if String(bakes[k].state) == "ready":
			ready += 1
	var n := maxf(1.0, float(cost_frames))
	var states := {}
	for mk in maps:
		states[String(maps[mk].state)] = int(states.get(String(maps[mk].state), 0)) + 1
	var parts := PackedStringArray(["maps by state %s, %d running" % [str(states), maps_running]])
	for k in part_us:
		parts.append("%s %.0f" % [k, float(part_us[k]) / n])
	return "remaster: %s, %d models baked, %d textures with maps, %.1f figures a frame, own time %.0f us a frame (worst %d; %s)" % ["on" if on else "off", ready,
		maps.size(), figures_sum / n, cost_sum / n, cost_worst, ", ".join(parts)]


func _exit_tree() -> void:
	if cost_frames > 0:
		print("rta_godot: " + info_text())
	for mk in maps:
		if String(maps[mk].state) == "running":
			WorkerThreadPool.wait_for_task_completion(int(maps[mk].task))
			maps[mk]["md5"] = String(maps[mk].job.get("md5", ""))
	for key in bakes:
		if bakes[key].has("job"):
			WorkerThreadPool.wait_for_task_completion(int(bakes[key].job.task))
		if bakes[key].has("merge_job"):
			WorkerThreadPool.wait_for_task_completion(int(bakes[key].merge_job.task))
	for t in io_tasks:
		WorkerThreadPool.wait_for_task_completion(int(t))
	if dump_dir != "":
		# (tuning) which figures' textures each dumped picture is: md5 figure-t<K> ...
		var f := FileAccess.open(dump_dir.path_join("index-%d.txt" % OS.get_process_id()), FileAccess.WRITE)
		if f != null:
			for mk in maps:
				if maps[mk].has("md5"):
					f.store_line("%s %s" % [String(maps[mk].md5).substr(0, 8), " ".join(PackedStringArray((maps[mk].get("whos", {}) as Dictionary).keys()))])
			f.close()
	release()
