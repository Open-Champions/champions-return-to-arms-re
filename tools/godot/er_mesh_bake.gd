# er_mesh_bake.gd - the Elden Ring world layer's rebuild: the fitted pieces' meshes and pictures made ready for the game
# (er_world_fit.py runs it; it reads and writes only the owner's local files, nothing of it is tracked).
#
#   Godot --headless --path <an empty folder with a project.godot> --script er_mesh_bake.gd -- JOBS.json
#
# JOBS.json: [{"mesh": "<piece>.v2", "out": "<piece>.mesh.res"} | {"texture": "<picture>.png", "out": "<picture>.tex.res"}]
#
# A mesh: per surface its corners (position, normal, uv, colour: the game's colour there and a relief's height) and triangles
# (er_world_fit.py write_v2).  Each surface gets its tangents, is made lighter until its triangles fit its budget (meshoptimizer,
# through ImporterMesh: UV seams and sharp edges kept), and gets lower levels of detail under that for the distance; the
# result is an ArrayMesh resource the game loads on a worker thread (er_world.gd).  A picture: an Image with its mip maps,
# read without decoding.
extends SceneTree


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		print("er_mesh_bake: no jobs file")
		quit(2)
		return
	var jobs = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if typeof(jobs) != TYPE_ARRAY:
		print("er_mesh_bake: the jobs file is not a list")
		quit(2)
		return
	var t0 := Time.get_ticks_msec()
	for job in jobs:
		if job.has("texture"):
			_texture(String(job.texture), String(job.out))
		else:
			_mesh(String(job.mesh), String(job.out))
	print("er_mesh_bake: done, %d jobs in %.1f s" % [jobs.size(), (Time.get_ticks_msec() - t0) / 1000.0])
	quit(0)


func _texture(src: String, dst: String) -> void:
	var img := Image.load_from_file(src)
	if img == null:
		print("er_mesh_bake: cannot read %s" % src)
		return
	if img.get_format() != Image.FORMAT_RGBA8:
		img.convert(Image.FORMAT_RGBA8)
	img.generate_mipmaps()
	var err := ResourceSaver.save(img, dst, ResourceSaver.FLAG_COMPRESS)
	print("er_mesh_bake: picture %s %dx%d (%s)" % [dst.get_file(), img.get_width(), img.get_height(), "ok" if err == OK else "error %d" % err])


func _mesh(src: String, dst: String) -> void:
	var f := FileAccess.open(src, FileAccess.READ)
	if f == null:
		print("er_mesh_bake: cannot read %s" % src)
		return
	if f.get_32() != 0x32425245:
		print("er_mesh_bake: %s is not a v2 mesh" % src)
		return
	var surfaces := f.get_32()
	var final := ImporterMesh.new()
	var before := 0
	var after := 0
	for s in surfaces:
		var nv := f.get_32()
		var ni := f.get_32()
		var budget := f.get_32()
		var pos := f.get_buffer(nv * 12).to_float32_array()
		var nrm := f.get_buffer(nv * 12).to_float32_array()
		var uvs := f.get_buffer(nv * 8).to_float32_array()
		var col := f.get_buffer(nv * 16).to_float32_array()
		var idx := f.get_buffer(ni * 4).to_int32_array()
		var verts := PackedVector3Array()
		var norms := PackedVector3Array()
		var uv := PackedVector2Array()
		var colours := PackedColorArray()
		verts.resize(nv)
		norms.resize(nv)
		uv.resize(nv)
		colours.resize(nv)
		for i in nv:
			verts[i] = Vector3(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2])
			norms[i] = Vector3(nrm[i * 3], nrm[i * 3 + 1], nrm[i * 3 + 2])
			uv[i] = Vector2(uvs[i * 2], uvs[i * 2 + 1])
			colours[i] = Color(col[i * 4], col[i * 4 + 1], col[i * 4 + 2], col[i * 4 + 3])
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = verts
		arrays[Mesh.ARRAY_NORMAL] = norms
		arrays[Mesh.ARRAY_TEX_UV] = uv
		arrays[Mesh.ARRAY_COLOR] = colours
		arrays[Mesh.ARRAY_INDEX] = idx
		var st := SurfaceTool.new()
		st.create_from_arrays(arrays)
		st.generate_tangents()
		arrays = st.commit_to_arrays()
		before += idx.size() / 3
		# lighter: the finest level of detail meshoptimizer makes that fits the budget becomes the surface itself
		if budget > 0 and idx.size() / 3 > budget:
			var probe := ImporterMesh.new()
			probe.add_surface(Mesh.PRIMITIVE_TRIANGLES, arrays)
			probe.generate_lods(25.0, 60.0, [])
			var chosen := PackedInt32Array()
			for l in probe.get_surface_lod_count(0):
				var li := probe.get_surface_lod_indices(0, l)
				if li.size() / 3 <= budget:
					chosen = li
					break
			if chosen.is_empty() and probe.get_surface_lod_count(0) > 0:
				chosen = probe.get_surface_lod_indices(0, probe.get_surface_lod_count(0) - 1)
			if not chosen.is_empty():
				arrays = _compact(arrays, chosen)
		after += (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
		final.add_surface(Mesh.PRIMITIVE_TRIANGLES, arrays)
	final.generate_lods(25.0, 60.0, [])
	var mesh := final.get_mesh()
	var err := ResourceSaver.save(mesh, dst, ResourceSaver.FLAG_COMPRESS)
	var lods := []
	for s in final.get_surface_count():
		lods.append(final.get_surface_lod_count(s))
	print("er_mesh_bake: mesh %s: %d surfaces, %d -> %d triangles, levels of detail %s (%s)" % [dst.get_file(), surfaces, before, after, str(lods),
		"ok" if err == OK else "error %d" % err])


# the corners the new triangles use, alone
func _compact(arrays: Array, indices: PackedInt32Array) -> Array:
	var remap := {}
	var order := PackedInt32Array()
	var out_idx := PackedInt32Array()
	out_idx.resize(indices.size())
	for k in indices.size():
		var o := indices[k]
		if not remap.has(o):
			remap[o] = order.size()
			order.append(o)
		out_idx[k] = remap[o]
	var out := []
	out.resize(Mesh.ARRAY_MAX)
	for a in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_COLOR]:
		var src = arrays[a]
		var dst = src.duplicate()
		dst.resize(order.size())
		for k in order.size():
			dst[k] = src[order[k]]
		out[a] = dst
	var tan: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
	var nt := PackedFloat32Array()
	nt.resize(order.size() * 4)
	for k in order.size():
		for c in 4:
			nt[k * 4 + c] = tan[order[k] * 4 + c]
	out[Mesh.ARRAY_TANGENT] = nt
	out[Mesh.ARRAY_INDEX] = out_idx
	return out
