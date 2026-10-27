extends SceneTree

# Compare the actual RenderingServer bones with the previous script expression,
# including missing bones and an invalid palette that must not partially write.
func _initialize() -> void:
	var writer := RtaRemaster.new()
	var skeleton := RenderingServer.skeleton_create()
	var binds := PackedInt32Array([2, 0, -1, 1])
	var globals := [Transform3D(Basis.from_euler(Vector3(0.2, -0.5, 1.1)), Vector3(3, -7, 12)), null,
		Transform3D(Basis.from_euler(Vector3(-0.7, 0.9, 0.3)).scaled(Vector3(0.5, 2, 1.5)), Vector3(-11, 23, 5))]
	var inverse_bind := [Transform3D(Basis.from_euler(Vector3(0.1, 0.3, -0.2)), Vector3(2, -3, 4)),
		Transform3D(Basis.IDENTITY, Vector3(-4, 2, 3)), Transform3D(), Transform3D()]
	RenderingServer.skeleton_allocate_data(skeleton, binds.size())
	var ok := writer.skin_palette(skeleton, binds, globals, inverse_bind)
	var expected: Array = []
	for q in binds.size():
		var bone := binds[q]
		var value: Transform3D = (globals[bone] as Transform3D) * (inverse_bind[q] as Transform3D) if bone >= 0 and globals[bone] != null else Transform3D()
		expected.append(value)
		ok = ok and RenderingServer.skeleton_bone_get_transform(skeleton, q) == value
	var invalid := PackedInt32Array([0, 999, -1, 1])
	ok = ok and not writer.skin_palette(skeleton, invalid, globals, inverse_bind)
	ok = ok and not writer.skin_palette(skeleton, binds, globals, [])
	for q in binds.size():
		ok = ok and RenderingServer.skeleton_bone_get_transform(skeleton, q) == expected[q]
	RenderingServer.free_rid(skeleton)
	if ok:
		print("SKIN_PALETTE_TEST PASS: exact transforms, missing bones, refusal before mutation")
	else:
		push_error("Skin palette changed the script's transforms or partially wrote invalid input")
	quit(0 if ok else 1)
