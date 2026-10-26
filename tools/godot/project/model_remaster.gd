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
const MESH_VERSION := 2

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


func _ready() -> void:
	machine = main.machine
	drawer = main.drawer
	rm = ClassDB.instantiate("RtaRemaster") if ClassDB.class_exists("RtaRemaster") else null
	cfg = ConfigFile.new()
	if cfg.load("res://model_remaster.cfg") != OK:
		cfg = ConfigFile.new()
	shader = load("res://shaders/remaster_model.gdshader")
	DirAccess.make_dir_recursive_absolute(CACHE + "/mesh")
	DirAccess.make_dir_recursive_absolute(CACHE + "/maps")
	if rm == null:
		print("rta_godot: remaster: the extension has no RtaRemaster: the game's own figures stay as they are")


func _opt(name: String) -> Dictionary:
	if options_of.has(name):
		return options_of[name]
	var o := {"off": false, "levels": 2, "crease": 0.5, "fit": 8, "keep": 1.0, "max_tris": 80000, "lod_near": 260.0, "lod_far": 1200.0,
		"class": "auto", "strength": 1.6, "metal": 0.85, "rough": 1.0, "gain": 1.0, "bump": 1.0, "cavity": 1.0, "game_light": 1.0}
	var sections := ["default"]
	var parts := name.split(".")
	for i in parts.size():
		sections.append(".".join(parts.slice(0, i + 1)))
	for s in sections:
		if cfg.has_section(s):
			for k in cfg.get_section_keys(s):
				o[k] = cfg.get_value(s, k)
	options_of[name] = o
	return o


func _name_of(f: Dictionary) -> String:
	for p in scan_now.get("players", []):
		# a player's figure is posed by an animation state inside its creature (er_layer.gd _find_player)
		var off := int(f.state) - int(p.get("object", 0))
		if int(p.state) == int(f.state) or (int(p.get("object", 0)) != 0 and off >= 0 and off < 0x800):
			var c := int(p.character_class)
			return "player." + (CLASS_NAMES[c] if c >= 0 and c < CLASS_NAMES.size() else str(c))
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
		scan_now = {}
		if hide_sent:
			drawer.call("set_hidden_skinned", PackedInt64Array())
			hide_sent = false
		spent = Time.get_ticks_usec() - started
		return
	scan_now = rm.call("scan", machine)
	_poll_bakes()
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
		if not bakes.has(key):
			if not _load_cached(key, name) and int(rm.call("bakes_running")) < 2:
				var k2 := String(rm.call("bake_start", machine, obj, {"levels": int(o.levels), "crease": float(o.crease), "fit": int(o.fit),
					"keep": float(o.keep), "max_tris": int(o.max_tris)}))
				if k2 != "":
					bakes[key] = {"state": "running", "name": name, "started": Time.get_ticks_msec()}
			continue
		var b: Dictionary = bakes[key]
		if String(b.state) != "ready" or not _materials_ready(f):
			continue
		f["bake"] = b
		hide.append(obj)
		targets.append(f)
	if debug and frame_no % 240 == 0:
		var lines := PackedStringArray()
		for f in scan_now.get("figures", []):
			var b: Dictionary = bakes.get(String(f.key), {})
			lines.append("%x %s %s %s %d packets %d corners bake %s materials %s" % [int(f.object), String(f.get("id", "?")), String(f.get("name", "?")), String(f.key),
				(f.pieces as PackedInt32Array).size(), int(f.corners), String(b.get("state", "-")), str(_materials_ready(f))])
		print("rta_godot: remaster: frame %d: %d figures, %d drawn here (players %s):\n  %s" % [frame_no, (scan_now.get("figures", []) as Array).size(), targets.size(),
			str(scan_now.get("players", [])), "\n  ".join(lines)])
		print("rta_godot: remaster: left to the game: %s" % str(scan_now.get("rejected", [])))
	if not targets.is_empty() or hide_sent:
		drawer.call("set_hidden_skinned", hide)
		hide_sent = not targets.is_empty()
	spent = Time.get_ticks_usec() - started


func _materials_ready(f: Dictionary) -> bool:
	for pk in f.piece_keys:
		if not packets.has(String(pk)):
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
		b["merged"] = {}
		_save_cached(key, b)
		print("rta_godot: remaster: %s baked (%s): %s" % [b.name, key, r.stats])


# the baked model in the user data folder: its levels, a set of Mesh arrays a packet ([] for an empty one)
func _save_cached(key: String, b: Dictionary) -> void:
	var file := FileAccess.open("%s/mesh/%s.bin" % [CACHE, key], FileAccess.WRITE)
	if file != null:
		file.store_var({"version": MESH_VERSION, "piece_keys": b.piece_keys, "levels": b.levels})
		file.close()


func _load_cached(key: String, name: String) -> bool:
	var path := "%s/mesh/%s.bin" % [CACHE, key]
	if not FileAccess.file_exists(path):
		return false
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return false
	var d = file.get_var()
	file.close()
	if not (d is Dictionary) or int(d.get("version", 0)) != MESH_VERSION or not d.has("levels"):
		return false
	bakes[key] = {"state": "ready", "name": name, "levels": d.levels, "piece_keys": d.piece_keys, "merged": {}}
	print("rta_godot: remaster: %s from the cache (%s, %d levels)" % [name, key, (d.levels as Array).size()])
	return true


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
	var tex: Dictionary = drawer.call("get_piece_textures")
	for f in scan_now.get("figures", []):
		var o := _opt(String(f.get("name", "")))
		var keys: PackedStringArray = f.piece_keys
		var pieces: PackedInt32Array = f.pieces
		for n in keys.size():
			var t = tex.get(int(pieces[n]))
			if t == null:
				continue
			var pk := String(keys[n])
			# known with this texture: nothing to do (its signature is made only when the texture changes)
			var tid: int = (t[0] as RID).get_id()
			if int(packet_tex.get(pk, -1)) == tid and packets.has(pk):
				var known: Dictionary = templates.get(packets[pk], {})
				if not known.is_empty() and bool(known.maps_set):
					continue
			packet_tex[pk] = tid
			_packet(pk, t, o, n)
	var info: Dictionary = er.call("_scene_info") if er != null else drawer.call("get_scene_info")
	var cam: Transform3D = info.get("camera", Transform3D())
	var orders: Dictionary = info.get("hidden_orders", {})
	for f in targets:
		_draw(f, cam, orders)
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
	var us := Time.get_ticks_usec() - started + spent
	cost_sum += us
	cost_frames += 1
	cost_worst = maxi(cost_worst, us)
	figures_sum += targets.size()


# A packet's material as the game draws it (its texture and that texture's state) and the class it is given: its
# signature.  Packets with one signature share a template (and are one surface of the figure); every figure makes its
# own material from a template (the game's light on each figure differs).
func _packet(pk: String, t: Array, o: Dictionary, part: int) -> void:
	var texture: RID = t[0]
	var cls := String(o.get("part%d" % part, o["class"]))
	var sig := "%d|%s|%s|%s|%s|%d|%s|%s|%s|%s|%s|%s|%s" % [texture.get_id(), str(t[1]), str(t[2]), str(t[3]), str(t[4]), int(t[5]), str(t[6]), cls,
		str(o.strength), str(o.metal), str(o.rough), str(o.gain), str(o.bump)]
	packets[pk] = sig
	if templates.has(sig):
		_template_maps(templates[sig])
		return
	var p := {"gain": float(o.gain), "bump": float(o.bump), "cavity": float(o.cavity), "game_light": float(o.game_light), "metal_amount": 1.0,
		"albedo_tex": texture, "tex_size": t[1], "tex_offset": t[2], "st_scale": t[3], "cut": float(t[4]), "alpha_from": int(t[5]), "ta0": float(t[6])}
	var mk := "%d|%s|%s|%s|%s" % [texture.get_id(), cls, str(o.strength), str(o.metal), str(o.rough)]
	if not maps.has(mk):
		maps[mk] = {"state": "wait", "since": frame_no, "rid": texture, "size": t[1], "retried": false,
			"opts": {"strength": float(o.strength), "class": "" if cls == "auto" else cls, "metal": float(o.metal), "rough": float(o.rough)}}
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
func _merged(b: Dictionary) -> Dictionary:
	var sigs: Array = []
	var group_of := {}
	var groups := PackedInt32Array()
	for pk in b.piece_keys:
		var sig := String(packets.get(String(pk), ""))
		if not group_of.has(sig):
			group_of[sig] = sigs.size()
			sigs.append(sig)
		groups.append(int(group_of[sig]))
	var gkey := "|".join(PackedStringArray(sigs))
	var merged: Dictionary = b.merged
	if merged.has(gkey):
		return merged[gkey]
	var meshes: Array = []
	for surfaces in b.levels:
		var out: Array = rm.call("merge", surfaces, groups, sigs.size())
		var mesh := ArrayMesh.new()
		var sg := PackedInt32Array()
		for gi in out.size():
			var arrays: Array = out[gi]
			if arrays[Mesh.ARRAY_VERTEX] != null:
				mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
				sg.append(gi)
		mesh.set_meta("surface_group", sg)
		meshes.append(mesh)
	var m := {"gkey": gkey, "meshes": meshes, "sigs": sigs}
	merged[gkey] = m
	return m


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
	var m := _merged(f.bake)
	var meshes: Array = m.meshes
	var top := meshes.size() - 1
	var dist := cam.origin.distance_to(root)
	# the finest level near the eye, the one below it (never the game's own, unless there is no other) further out, the
	# game's own mesh far away; a margin either way, so that a figure at a border does not flicker between two
	var was := int(g.level)
	var near := float(o.lod_near) * (1.1 if was == top else 0.9)
	var far := float(o.lod_far) * (1.1 if was != 0 else 0.9)
	var level := top if dist < near else (maxi(top - 1, mini(top, 1)) if dist < far else 0)
	if String(g.gkey) != String(m.gkey) or was != level:
		var mesh: ArrayMesh = meshes[level]
		RenderingServer.instance_set_base(g.instance, mesh.get_rid())
		var sg: PackedInt32Array = mesh.get_meta("surface_group")
		for s in mesh.get_surface_count():
			RenderingServer.instance_set_surface_override_material(g.instance, s, _figure_material(g, String(m.sigs[sg[s]])))
		g["gkey"] = m.gkey
		g["level"] = level
	rm.call("pose", machine, int(f.skeleton), g.skeleton)
	var light: Dictionary = er.call("_game_light", int(f.state), root) if er != null and er.has_method("_game_light") else {}
	for sig in m.sigs:
		var rid := _figure_material(g, String(sig))
		for k in light:
			RenderingServer.material_set_param(rid, k, light[k])
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
					mp["normal"] = ImageTexture.create_from_image(out.normal)
					mp["orm"] = ImageTexture.create_from_image(out.orm)
					mp["state"] = "done"
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
		var job := {"img": img, "opts": opts, "out": {}}
		mp["job"] = job
		mp["task"] = WorkerThreadPool.add_task(_derive.bind(job), false, "remaster maps")
		mp["state"] = "running"
		maps_running += 1


func _derive(job: Dictionary) -> void:
	var img: Image = job.img
	var hc := HashingContext.new()
	hc.start(HashingContext.HASH_MD5)
	hc.update(img.get_data())
	var o: Dictionary = job.opts
	var tag := "%s-%dx%d-%s-%s-%s-%s" % [hc.finish().hex_encode(), img.get_width(), img.get_height(), String(o["class"]) if String(o["class"]) != "" else "auto",
		str(o.strength), str(o.metal), str(o.rough)]
	var base := "%s/maps/%s" % [CACHE, tag]
	if FileAccess.file_exists(base + "-n.png") and FileAccess.file_exists(base + "-orm.png"):
		var n := Image.load_from_file(base + "-n.png")
		var r := Image.load_from_file(base + "-orm.png")
		if n != null and r != null:
			n.generate_mipmaps()
			r.generate_mipmaps()
			job.out = {"normal": n, "orm": r, "cached": true}
			return
	var out: Dictionary = rm.call("derive_maps", img, o)
	if out.has("normal"):
		var n0: Image = (out.normal as Image).duplicate()
		var r0: Image = (out.orm as Image).duplicate()
		n0.clear_mipmaps()
		r0.clear_mipmaps()
		n0.save_png(base + "-n.png")
		r0.save_png(base + "-orm.png")
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
	return "remaster: %s, %d models baked, %d textures with maps, %.1f figures a frame, own time %.0f us a frame (worst %d)" % ["on" if on else "off", ready,
		maps.size(), figures_sum / n, cost_sum / n, cost_worst]


func _exit_tree() -> void:
	if cost_frames > 0:
		print("rta_godot: " + info_text())
	for mk in maps:
		if String(maps[mk].state) == "running":
			WorkerThreadPool.wait_for_task_completion(int(maps[mk].task))
	release()
