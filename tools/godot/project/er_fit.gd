extends RefCounted
# er_fit.gd - the local outfit's pieces FITTED onto the game's own figure (er_layer.gd, look.er_models = on, er_style fit).
#
# Round 4 (docs/issues/native-er-layer.md): the game's character keeps its own body - face, race, tail, silhouette - and
# wears the outfit's pieces (helm, chest, arms, legs, cape) on top.  Once per outfit and game figure (on a worker thread):
#
#   regions   every mapped pair of the joint map (er_layer.gd _align: a game joint and the outfit's bone, each with the
#             joint / bone it aims at) is a region: a segment from the game's joint to its aim joint in the game's bind
#             pose, and the matching segment of the outfit's skeleton.  An outfit bone that is not mapped (twists, fingers,
#             cloth) belongs to the region of its nearest mapped ancestor; a game joint likewise (but for the tail and
#             the other chains off the trunk: those are no limb an armour piece covers).
#   profiles  per region, round its segment, in 3 bands along it x 8 sectors round it: how far the game's body reaches
#             (the largest distance of its bind-pose vertices from the segment) and where the outfit's piece starts
#             (a low percentile of the piece's distances: its inside).  Their ratio (with a small margin) is how much
#             the piece is widened or narrowed there, so that it sits on the game's body instead of inside it or
#             floating off it; smoothed over neighbouring cells and read between them.
#   placing   an outfit vertex is carried by each region it is weighted to: measured along and round the outfit's
#             segment, put at the same place along the game's segment (the bone's length is the game's) and round it
#             (by the profile's ratio there); the regions' results blended by its weights.  Normals and tangents turn
#             with their regions.
#   skinning  the vertex is then skinned to the game's own joints (each outfit bone -> its region's game joint), with the
#             skin matrices the game's body is drawn with - the piece moves exactly as the body under it - and the
#             cloth bones (capes, skirts) as extra bones that swing (er_layer.gd's springs).
#   leaving   a piece (HD helm, BD chest, AM arms, LG legs, or one named mesh) that would have to be stretched out of its
#     out     shape to fit (much more than twice, or less than two thirds, over much of it) is left out for that figure,
#             as are the parts er_fit.cfg names per class; the hands of the arm pieces are left out (the game's hands
#             grip and open; a rigid glove would poke through them) - the game's own hands are drawn.
# Nothing of either game is in this file.

const NT := 3                       # bands along a segment
const NA := 8                       # sectors round it
const MARGIN_REL := 0.05            # the piece's inside this much beyond the body ...
const MARGIN_ABS := 0.35            # ... and this many game units (the figure is about 65 units tall)
const S_MIN := 0.7
const S_MAX := 2.3
const BAD_LOW := 0.72               # a piece whose vertices need a widening below this ...
const BAD_HIGH := 2.1               # ... or above this (both before clamping) ...
const BAD_SHARE := 0.3              # ... for more than this share of them is left out


# job: {
#   surfaces: [{arrays, name, part}],  bind_mats: per surface Array of Transform3D (bind index -> outfit rest space),
#   bind_bones: per surface PackedInt32Array (bind index -> outfit bone),
#   er_parent: PackedInt32Array, er_rest: Array[Transform3D] (global rests), er_names: PackedStringArray,
#   cloth: {bone: tip Vector3}, axes: Basis, k: float, map: [{er, ea, game, ga, name}],
#   game_bind: Array[Vector3], game_parent: PackedInt32Array, n: int,
#   body_pos: PackedVector3Array, body_joints: PackedInt32Array, body_weights: PackedFloat32Array,
#   drop: PackedStringArray (name parts to leave out), keep_hands: bool, label: String }
static func compute(job: Dictionary) -> Dictionary:
	var started := Time.get_ticks_msec()
	var map: Array = job.map
	var n := int(job.n)
	var k := float(job.k)
	var axes: Basis = job.axes
	var er_parent: PackedInt32Array = job.er_parent
	var er_rest: Array = job.er_rest
	var er_names: PackedStringArray = job.er_names
	var game_bind: Array = job.game_bind
	var game_parent: PackedInt32Array = job.game_parent
	var cloth: Dictionary = job.cloth
	var nb := er_parent.size()
	# ---- the regions
	var regions: Array = []
	var by_er := {}
	var by_game := {}
	var forward := Vector3(0, -1, 0)    # the game's figures face -y in their bind pose
	var up := Vector3(0, 0, 1)
	for e in map:
		var eb := int(e.er)
		var ea := int(e.ea)
		var gj := int(e.game)
		var ga := int(e.ga)
		var p_er: Vector3 = (er_rest[eb] as Transform3D).origin
		var g0: Vector3 = game_bind[gj]
		var d_er := Vector3.ZERO
		var d_g := Vector3.ZERO
		if ea >= 0 and ga >= 0 and ga < n:
			d_er = (er_rest[ea] as Transform3D).origin - p_er
			d_g = (game_bind[ga] as Vector3) - g0
		var ball := d_er.length() < 1e-4 or d_g.length() < 1e-4
		var turn := axes
		var len_er := 0.0
		var len_g := 0.0
		if ball:
			# a joint with nothing to aim at (the head): its segment is the figure's up, as long as the outfit's own
			# bone is (its length is set from the profile below)
			d_er = axes.inverse() * up
			len_er = 0.25 * k / maxf(k, 1e-4)
			d_g = up
		else:
			turn = _arc((axes * d_er).normalized(), d_g.normalized()) * axes
			len_er = d_er.length()
			len_g = d_g.length()
		var a := d_g.normalized()
		var u := forward - a * forward.dot(a)
		if u.length() < 0.3:
			u = up - a * up.dot(a)
		u = u.normalized()
		var r := {"name": String(e.name), "er": eb, "game": gj, "p_er": p_er, "d_er": d_er.normalized(), "len_er": maxf(len_er, 1e-4),
			"g0": g0, "a": a, "u": u, "w": a.cross(u), "len_g": len_g, "ball": ball, "turn": turn,
			"body": _cells(), "er_in": [], "s": PackedFloat32Array()}
		var lists: Array = []
		for c in NT * NA:
			lists.append([])            # (plain arrays: a packed one taken out of an Array is a copy)
		r.er_in = lists
		by_er[eb] = regions.size()
		by_game[gj] = regions.size()
		regions.append(r)
	if regions.is_empty():
		return {"failed": "no mapped joints"}
	# every outfit bone -> its region (the nearest mapped ancestor; the root's region for the rest)
	var root_region := 0
	var shallow := 1 << 30
	for i in regions.size():
		var d := _depth(er_parent, int(regions[i].er))
		if d < shallow:
			shallow = d
			root_region = i
	var region_of := PackedInt32Array()
	region_of.resize(nb)
	for b in nb:
		var q := b
		var found := -1
		while q >= 0:
			if by_er.has(q):
				found = int(by_er[q])
				break
			q = er_parent[q]
		region_of[b] = found if found >= 0 else root_region
	# every game joint -> its region: a mapped joint its own; an unmapped one that of its nearest mapped ancestor when that
	# is a hand, a foot or the head (fingers, toes, a jaw, ears: what a glove, a boot or a helm has to cover), else none
	# (a tail, the game's own cape chain or skirt: no armour covers them, they stay outside it)
	var game_region := PackedInt32Array()
	game_region.resize(n)
	for j in n:
		var q := j
		var found := -1
		var first := true
		while q >= 0:
			if by_game.has(q):
				var reg: Dictionary = regions[int(by_game[q])]
				if first or String(reg.name).ends_with("_hand") or String(reg.name).ends_with("_foot") or String(reg.name) == "head":
					found = int(by_game[q])
				break
			first = false
			q = game_parent[q] if q < game_parent.size() else -1
		game_region[j] = found
	# ---- the game's body: per region and cell, how far it reaches
	var bp: PackedVector3Array = job.body_pos
	var bj: PackedInt32Array = job.body_joints
	var bw: PackedFloat32Array = job.body_weights
	for v in bp.size():
		var best := -1
		var bwt := 0.0
		for q in 4:
			var w := bw[v * 4 + q]
			if w > bwt:
				bwt = w
				best = bj[v * 4 + q]
		if best < 0 or best >= n or game_region[best] < 0:
			continue
		var r: Dictionary = regions[game_region[best]]
		var loc := _local_game(r, bp[v])
		var cell := _cell(loc.t, loc.ang)
		var cells: PackedFloat32Array = r.body
		cells[cell] = maxf(cells[cell], loc.rad)
		r.body = cells
	# ---- the outfit's vertices in its rest space, their regions, and the inside of each piece per cell
	var surfaces: Array = job.surfaces
	var prepared: Array = []
	for si in surfaces.size():
		var s: Dictionary = surfaces[si]
		var arrays: Array = s.arrays
		var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var bones_a = arrays[Mesh.ARRAY_BONES]
		var weights_a = arrays[Mesh.ARRAY_WEIGHTS]
		var nv := verts.size()
		var per := 4
		if bones_a != null and nv > 0 and (bones_a as PackedInt32Array).size() >= nv * 8:
			per = 8
		var bind_mats: Array = job.bind_mats[si]
		var bind_bones: PackedInt32Array = job.bind_bones[si]
		var rest_pos := PackedVector3Array()
		rest_pos.resize(nv)
		var vb := PackedInt32Array()          # per vertex 4 (outfit bone)
		var vw := PackedFloat32Array()
		vb.resize(nv * 4)
		vw.resize(nv * 4)
		var dom := PackedInt32Array()         # dominant region (-1: none); cloth-carried vertices marked by +1000
		dom.resize(nv)
		for v in nv:
			var x := Vector3.ZERO
			var tot := 0.0
			var top := [-1, -1, -1, -1]
			var topw := [0.0, 0.0, 0.0, 0.0]
			for q in per:
				var w: float = (weights_a as PackedFloat32Array)[v * per + q] if weights_a != null else 0.0
				if w <= 0.0:
					continue
				var bi: int = (bones_a as PackedInt32Array)[v * per + q]
				if bi < 0 or bi >= bind_bones.size():
					continue
				x += w * ((bind_mats[bi] as Transform3D) * verts[v])
				tot += w
				# keep the four heaviest
				var at := -1
				for z in 4:
					if top[z] < 0 or topw[z] < w:
						at = z
						break
				if at >= 0:
					for z in range(3, at, -1):
						top[z] = top[z - 1]
						topw[z] = topw[z - 1]
					top[at] = bind_bones[bi]
					topw[at] = w
			rest_pos[v] = x / tot if tot > 0.0 else verts[v]
			var sw := 0.0
			for z in 4:
				sw += topw[z]
			var region_w := {}
			var cloth_w := 0.0
			for z in 4:
				vb[v * 4 + z] = top[z]
				vw[v * 4 + z] = topw[z] / sw if sw > 0.0 else 0.0
				if top[z] >= 0:
					var rg := region_of[top[z]]
					region_w[rg] = float(region_w.get(rg, 0.0)) + topw[z]
					if cloth.has(top[z]):
						cloth_w += topw[z]
			var d := -1
			var dw := 0.0
			for rg in region_w:
				if float(region_w[rg]) > dw:
					dw = float(region_w[rg])
					d = int(rg)
			dom[v] = d + (1000 if cloth_w > 0.0 else 0)
			# the inside of the piece: only vertices held mostly by one region and not by cloth
			if d >= 0 and cloth_w <= 0.0 and sw > 0.0 and dw / sw > 0.7:
				var r: Dictionary = regions[d]
				var loc := _local_er(r, rest_pos[v], k)
				var cell := _cell(loc.t, loc.ang)
				(r.er_in[cell] as Array).append(float(loc.rad))
		prepared.append({"rest": rest_pos, "vb": vb, "vw": vw, "dom": dom})
	# ---- the ratios per cell
	for r in regions:
		var s := PackedFloat32Array()
		s.resize(NT * NA)
		var known := PackedByteArray()
		known.resize(NT * NA)
		var raw := PackedFloat32Array()
		raw.resize(NT * NA)
		var inner := PackedFloat32Array()
		inner.resize(NT * NA)
		for c in NT * NA:
			var inside: Array = r.er_in[c]
			var body := float((r.body as PackedFloat32Array)[c])
			if inside.size() >= 3 and body > 0.0:
				inside.sort()
				var lo := float(inside[int(inside.size() * 0.15)])
				var want := body * (1.0 + MARGIN_REL) + MARGIN_ABS
				raw[c] = want / maxf(lo, 0.05)
				inner[c] = lo
				s[c] = clampf(raw[c], S_MIN, S_MAX)
				known[c] = 1
		# cells with nothing to measure take their neighbours' (round the segment first, then along it)
		for it in 6:
			for c in NT * NA:
				if known[c] == 1:
					continue
				var t := c / NA
				var ang := c % NA
				var sum := 0.0
				var cnt := 0
				for nbr in [t * NA + (ang + 1) % NA, t * NA + (ang + NA - 1) % NA, (t - 1) * NA + ang if t > 0 else -1, (t + 1) * NA + ang if t < NT - 1 else -1]:
					if nbr >= 0 and known[nbr] == 1:
						sum += s[nbr]
						cnt += 1
				if cnt > 0:
					s[c] = sum / cnt
					var isum := 0.0
					var icnt := 0
					for nbr in [t * NA + (ang + 1) % NA, t * NA + (ang + NA - 1) % NA, (t - 1) * NA + ang if t > 0 else -1, (t + 1) * NA + ang if t < NT - 1 else -1]:
						if nbr >= 0 and known[nbr] == 1:
							isum += inner[nbr]
							icnt += 1
					inner[c] = isum / maxi(icnt, 1)
					known[c] = 2
			for c in NT * NA:
				if known[c] == 2:
					known[c] = 1
		var any := false
		for c in NT * NA:
			if known[c] == 1:
				any = true
			else:
				s[c] = 1.0
		# smoothed: round the segment [1 2 1], along it [1 2 1]
		var sm := PackedFloat32Array()
		sm.resize(NT * NA)
		for c in NT * NA:
			var t := c / NA
			var ang := c % NA
			var round_v := (s[t * NA + (ang + NA - 1) % NA] + 2.0 * s[c] + s[t * NA + (ang + 1) % NA]) * 0.25
			sm[c] = round_v
		var sm2 := PackedFloat32Array()
		sm2.resize(NT * NA)
		for c in NT * NA:
			var t := c / NA
			var ang := c % NA
			var a0 := sm[(t - 1) * NA + ang] if t > 0 else sm[c]
			var a2 := sm[(t + 1) * NA + ang] if t < NT - 1 else sm[c]
			sm2[c] = (a0 + 2.0 * sm[c] + a2) * 0.25
		r.s = sm2
		r.inner = inner
		r.raw = raw
		r.measured = any
		var mean := 0.0
		for c in NT * NA:
			mean += sm2[c]
		mean /= float(NT * NA)
		r.s_mean = mean
		if r.ball:
			# along the head as round it
			r.len_g = float(r.len_er) * k * mean
	# ---- the cloth bones in the game's bind pose (their region's fit), parents first
	var cloth_list: Array = []
	var cloth_index := {}
	var pending: Array = cloth.keys()
	pending.sort_custom(func(x, y): return _depth(er_parent, int(x)) < _depth(er_parent, int(y)))
	for b in pending:
		var reg: Dictionary = regions[region_of[int(b)]]
		var rest_t: Transform3D = er_rest[int(b)]
		var origin := _place(reg, rest_t.origin, k)
		var basis: Basis = (reg.turn as Basis) * rest_t.basis.orthonormalized()
		var par := er_parent[int(b)]
		cloth_index[int(b)] = cloth_list.size()
		var tip: Vector3 = cloth[b]
		cloth_list.append({"bone": int(b), "name": er_names[int(b)], "bind": Transform3D(basis, origin), "parent_cloth": int(cloth_index.get(par, -1)) if cloth.has(par) else -1,
			"joint": int(reg.game), "tip": tip * k * float(reg.s_mean)})
	# ---- which pieces stay
	var drop: PackedStringArray = job.get("drop", PackedStringArray())
	var part_bad := {}                  # part -> [bad, all]
	for si in surfaces.size():
		var part := String(surfaces[si].part)
		var pr: Dictionary = prepared[si]
		var dom: PackedInt32Array = pr.dom
		var rest_pos: PackedVector3Array = pr.rest
		var cnt: Array = part_bad.get(part, [0, 0])
		for v in range(0, dom.size(), 3):
			var d := dom[v]
			if d < 0 or d >= 1000:
				continue
			var r: Dictionary = regions[d]
			var loc := _local_er(r, rest_pos[v], k)
			var c := _cell(loc.t, loc.ang)
			var rv := float((r.raw as PackedFloat32Array)[c])
			cnt[1] += 1
			if rv > 0.0 and (rv < BAD_LOW or rv > BAD_HIGH):
				cnt[0] += 1
		part_bad[part] = cnt
	var left_out := PackedStringArray()
	for part in part_bad:
		var cnt: Array = part_bad[part]
		if int(cnt[1]) > 0 and float(cnt[0]) / float(cnt[1]) > BAD_SHARE:
			left_out.append("%s (%.0f%% would be stretched out of shape)" % [part, 100.0 * float(cnt[0]) / float(cnt[1])])
	# ---- the fitted surfaces
	# a converted part holds alternatives of some meshes (numbered #NN# in their names: the other game shows one of them by
	# what else is worn); drawn together they lie in each other: of each group of er_fit.cfg [variants] the lowest present
	var variants: Array = job.get("variants", [])
	var present := {}
	for si in surfaces.size():
		var num := _variant(String(surfaces[si].name))
		if num >= 0:
			present["%s:%d" % [surfaces[si].part, num]] = true
	var out_surfaces: Array = []
	var dropped_hands := 0
	for si in surfaces.size():
		var s: Dictionary = surfaces[si]
		var name := String(s.name)
		var part := String(s.part)
		var skip := ""
		for pat in drop:
			if pat != "" and (name.contains(pat) or part == pat):
				skip = "er_fit.cfg"
		for lo in left_out:
			if lo.begins_with(part + " "):
				skip = "stretched"
		var num := _variant(name)
		if num >= 0:
			for group in variants:
				if (group as Array).has(num):
					for other in group:
						if int(other) < num and present.has("%s:%d" % [part, int(other)]):
							skip = "variant"
		if skip != "":
			continue
		var pr: Dictionary = prepared[si]
		var arrays: Array = s.arrays
		var rest_pos: PackedVector3Array = pr.rest
		var vb: PackedInt32Array = pr.vb
		var vw: PackedFloat32Array = pr.vw
		var dom: PackedInt32Array = pr.dom
		var nv := rest_pos.size()
		var normals = arrays[Mesh.ARRAY_NORMAL]
		var tangents = arrays[Mesh.ARRAY_TANGENT]
		var pos := PackedVector3Array()
		pos.resize(nv)
		var nrm := PackedVector3Array()
		nrm.resize(nv)
		var tan := PackedFloat32Array()
		if tangents != null and (tangents as PackedFloat32Array).size() == nv * 4:
			tan.resize(nv * 4)
		var bones := PackedInt32Array()
		bones.resize(nv * 4)
		var weights := PackedFloat32Array()
		weights.resize(nv * 4)
		var bind_mats: Array = job.bind_mats[si]
		var turn0: Basis = bind_mats[0].basis if bind_mats.size() > 0 else Basis()
		for v in nv:
			var x := rest_pos[v]
			var acc := Vector3.ZERO
			var nacc := Vector3.ZERO
			var tacc := Vector3.ZERO
			var tw := 0.0
			var n_in: Vector3 = turn0 * (normals as PackedVector3Array)[v] if normals != null else Vector3.UP
			var t_in := Vector3.ZERO
			if tan.size() > 0:
				t_in = turn0 * Vector3((tangents as PackedFloat32Array)[v * 4], (tangents as PackedFloat32Array)[v * 4 + 1], (tangents as PackedFloat32Array)[v * 4 + 2])
			var slot := {}
			for z in 4:
				var b := vb[v * 4 + z]
				var w := vw[v * 4 + z]
				if b < 0 or w <= 0.0:
					continue
				var rg := region_of[b]
				var r: Dictionary = regions[rg]
				acc += _place(r, x, k) * w
				nacc += (r.turn as Basis) * n_in * w
				tacc += (r.turn as Basis) * t_in * w
				tw += w
				var pal := n + int(cloth_index[b]) if cloth_index.has(b) else int(r.game)
				slot[pal] = float(slot.get(pal, 0.0)) + w
			pos[v] = acc / tw if tw > 0.0 else _place(regions[root_region], x, k)
			nrm[v] = nacc.normalized() if nacc.length() > 1e-6 else Vector3.UP
			if tan.size() > 0:
				var tt := tacc - nrm[v] * tacc.dot(nrm[v])
				tt = tt.normalized() if tt.length() > 1e-6 else Vector3.RIGHT
				tan[v * 4] = tt.x
				tan[v * 4 + 1] = tt.y
				tan[v * 4 + 2] = tt.z
				tan[v * 4 + 3] = (tangents as PackedFloat32Array)[v * 4 + 3]
			var z := 0
			for pal in slot:
				if z < 4:
					bones[v * 4 + z] = int(pal)
					weights[v * 4 + z] = float(slot[pal]) / tw
					z += 1
			for zz in range(z, 4):
				bones[v * 4 + zz] = 0
				weights[v * 4 + zz] = 0.0
		# the triangles: the hands of the arm pieces left out (every corner on a hand region), and all turned so that their
		# front is the outside (Godot's front faces are clockwise)
		var index = arrays[Mesh.ARRAY_INDEX]
		var idx := PackedInt32Array()
		if index == null:
			for v in nv:
				idx.append(v)
		else:
			idx = (index as PackedInt32Array).duplicate()
		var kept := PackedInt32Array()
		var facing := 0.0
		for tri in range(0, idx.size() - 2, 3):
			var i0 := idx[tri]
			var i1 := idx[tri + 1]
			var i2 := idx[tri + 2]
			if not bool(job.get("keep_hands", false)) and part == "AM" and _on_hand(regions, dom, i0) and _on_hand(regions, dom, i1) and _on_hand(regions, dom, i2):
				dropped_hands += 1
				continue
			kept.append(i0)
			kept.append(i1)
			kept.append(i2)
			var g := (pos[i1] - pos[i0]).cross(pos[i2] - pos[i0])
			facing += g.dot(nrm[i0] + nrm[i1] + nrm[i2])
		if kept.is_empty():
			continue
		var turned := facing > 0.0
		if turned:
			for tri in range(0, kept.size() - 2, 3):
				var keep1 := kept[tri + 1]
				kept[tri + 1] = kept[tri + 2]
				kept[tri + 2] = keep1
		var out := []
		out.resize(Mesh.ARRAY_MAX)
		out[Mesh.ARRAY_VERTEX] = pos
		out[Mesh.ARRAY_NORMAL] = nrm
		if tan.size() > 0:
			out[Mesh.ARRAY_TANGENT] = tan
		out[Mesh.ARRAY_TEX_UV] = arrays[Mesh.ARRAY_TEX_UV]
		out[Mesh.ARRAY_BONES] = bones
		out[Mesh.ARRAY_WEIGHTS] = weights
		out[Mesh.ARRAY_INDEX] = kept
		out_surfaces.append({"arrays": out, "surface": si, "name": name, "part": part, "turned": turned})
	# the regions as the drawing needs them (the legs' reach for the capes' capsules)
	var reach := {}
	for r in regions:
		var m := 0.0
		for c in NT * NA:
			m = maxf(m, float((r.body as PackedFloat32Array)[c]))
		reach[String(r.name)] = m
	var summary := PackedStringArray()
	for r in regions:
		summary.append("%s %.2f" % [r.name, float(r.s_mean)])
	return {"surfaces": out_surfaces, "cloth": cloth_list, "n": n, "left_out": left_out, "reach": reach, "dropped_hands": dropped_hands,
		"summary": ", ".join(summary), "ms": Time.get_ticks_msec() - started, "label": String(job.get("label", ""))}


static func _variant(name: String) -> int:
	var at := name.find("#")
	if at < 0:
		return -1
	var end := name.find("#", at + 1)
	if end < 0:
		return -1
	var text := name.substr(at + 1, end - at - 1)
	return text.to_int() if text.is_valid_int() else -1


static func _cells() -> PackedFloat32Array:
	var c := PackedFloat32Array()
	c.resize(NT * NA)
	return c


static func _depth(parent: PackedInt32Array, b: int) -> int:
	var d := 0
	var q := parent[b]
	while q >= 0 and d < 512:
		d += 1
		q = parent[q]
	return d


static func _on_hand(regions: Array, dom: PackedInt32Array, v: int) -> bool:
	var d := dom[v] % 1000 if dom[v] >= 0 else -1
	return d >= 0 and String(regions[d].name).ends_with("_hand")


# a point of the game's bind pose measured against a region's game segment: t along it (0 at the joint, 1 at its aim),
# its distance from it and the angle round it (from the figure's front)
static func _local_game(r: Dictionary, p: Vector3) -> Dictionary:
	var d: Vector3 = p - (r.g0 as Vector3)
	var a: Vector3 = r.a
	var len_g := maxf(float(r.len_g), 1e-3) if not r.ball else 1.0
	var along := d.dot(a)
	var radial := d - a * along
	return {"t": along / len_g if not r.ball else 0.5, "rad": radial.length(), "ang": atan2(radial.dot(r.w), radial.dot(r.u))}


# a point of the outfit's rest pose measured against the region's outfit segment, in game units and directions
static func _local_er(r: Dictionary, x: Vector3, k: float) -> Dictionary:
	var d: Vector3 = x - (r.p_er as Vector3)
	var de: Vector3 = r.d_er
	var along := d.dot(de)
	var radial: Vector3 = (r.turn as Basis) * (d - de * along) * k
	return {"t": along / float(r.len_er) if not r.ball else 0.5, "along": along, "rad": radial.length(), "ang": atan2(radial.dot(r.w), radial.dot(r.u)), "radial": radial}


static func _cell(t: float, ang: float) -> int:
	var ti := clampi(int(floorf(clampf(t, 0.0, 0.999) * NT)), 0, NT - 1)
	var ai := int(floorf((ang + PI) / TAU * NA)) % NA
	return ti * NA + clampi(ai, 0, NA - 1)


# the ratio at (t, angle), read between the cells' centres
static func _ratio(r: Dictionary, t: float, ang: float, which := "s") -> float:
	var s: PackedFloat32Array = r[which]
	var ft := clampf(t, 0.0, 1.0) * NT - 0.5
	var t0 := clampi(int(floorf(ft)), 0, NT - 1)
	var t1 := clampi(t0 + 1, 0, NT - 1)
	var wt := clampf(ft - floorf(ft), 0.0, 1.0) if ft >= 0.0 and ft <= NT - 1 else 0.0
	var fa := (ang + PI) / TAU * NA - 0.5
	var a0 := int(floorf(fa))
	var wa := fa - floorf(fa)
	var a0i := (a0 % NA + NA) % NA
	var a1i := (a0i + 1) % NA
	var lo := lerpf(s[t0 * NA + a0i], s[t0 * NA + a1i], wa)
	var hi := lerpf(s[t1 * NA + a0i], s[t1 * NA + a1i], wa)
	return lerpf(lo, hi, wt)


# an outfit rest-pose point carried by a region into the game's bind pose: the same place along the game's segment (the
# bone's length is the game's), and round it moved out (or in) by as much as the piece's inside has to move there to sit
# on the game's body - the inside (its radius times the profile's ratio), and everything further out by the same distance:
# a pauldron, a crest, a cape or wings keep their own size and shape instead of being magnified with the body's girth
static func _place(r: Dictionary, x: Vector3, k: float) -> Vector3:
	var loc := _local_er(r, x, k)
	var s := _ratio(r, float(loc.t), float(loc.ang))
	var inside := _ratio(r, float(loc.t), float(loc.ang), "inner")
	var rad := float(loc.rad)
	var moved := rad * s if rad <= inside else rad + inside * (s - 1.0)
	var radial: Vector3 = loc.radial
	var out_dir := radial / rad if rad > 1e-5 else Vector3.ZERO
	if r.ball:
		var turned: Vector3 = (r.turn as Basis) * (x - (r.p_er as Vector3)) * k
		var dist := turned.length()
		var moved_b := dist * s if dist <= inside else dist + inside * (s - 1.0)
		return (r.g0 as Vector3) + (turned / dist * moved_b if dist > 1e-5 else Vector3.ZERO)
	var along_g: float = float(loc.t) * float(r.len_g)
	return (r.g0 as Vector3) + (r.a as Vector3) * along_g + out_dir * moved


static func _arc(a: Vector3, b: Vector3) -> Basis:
	var c := a.cross(b)
	var d := a.dot(b)
	if c.length() < 1e-6:
		if d > 0.0:
			return Basis()
		var perp := a.cross(Vector3(1, 0, 0))
		if perp.length() < 1e-3:
			perp = a.cross(Vector3(0, 1, 0))
		return Basis(perp.normalized(), PI)
	return Basis(c.normalized(), atan2(c.length(), d))
