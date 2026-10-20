extends RefCounted
# memcard.gd - characters from a memory card: the player's own saves of this game (and of the one before it, whose
# characters the game's own "Import" takes) copied out of a memory card image into the copy's own card folder, where
# the game's character screens list them.
#
# What it reads: a PCSX2 memory card file (.ps2: the PlayStation 2 card's own file system, pages of 512 bytes with or
# without their 16 bytes of error correction), or a folder that holds the save directories themselves.  It takes the
# directories whose names begin with the game's (or its predecessor's) product code, file by file, into
# DATA/card/mc0/NAME/ - a directory already there is left as it is unless `replace`.  Nothing is sent anywhere.
#
#   var result: Dictionary = MemCard.bring(path, card_folder)    # {"ok", "copied": [names], "skipped": [...], "error"}

const PREFIXES := ["BASLUS-20973", "BASLUS-20565"]     # this game's saves; the first game's (its import screen lists both)
const MAGIC := "Sony PS2 Memory Card Format "
const DF_DIRECTORY := 0x0020
const DF_EXISTS := 0x8000

var data: PackedByteArray
var page_len := 512
var raw_page := 528
var pages_per_cluster := 2
var cluster_size := 1024
var alloc_offset := 0
var root_cluster := 0
var ifc := PackedInt64Array()
var error := ""


static func bring(path: String, card_folder: String, replace := false) -> Dictionary:
	var result := {"ok": false, "copied": [], "skipped": [], "error": ""}
	if DirAccess.dir_exists_absolute(path):
		return _bring_folder(path, card_folder, replace, result)
	var card = load("res://portal/memcard.gd").new()
	if not card.open(path):
		result.error = card.error
		return result
	for entry in card.list_dir(card.root_cluster):
		var name := String(entry.name)
		if not (entry.mode & DF_DIRECTORY) or not _ours(name):
			continue
		var to := card_folder.path_join(name)
		if DirAccess.dir_exists_absolute(to) and not replace:
			result.skipped.append(name)
			continue
		DirAccess.make_dir_recursive_absolute(to)
		for f in card.list_dir(int(entry.cluster)):
			if (f.mode & DF_DIRECTORY) or String(f.name) in [".", ".."]:
				continue
			var file := FileAccess.open(to.path_join(String(f.name)), FileAccess.WRITE)
			if file == null:
				result.error = "cannot write in " + to
				return result
			file.store_buffer(card.read_chain(int(f.cluster), int(f.length)))
			file.close()
		result.copied.append(name)
	result.ok = result.error == ""
	if result.copied.is_empty() and result.skipped.is_empty() and result.ok:
		result.ok = false
		result.error = "no save of this game on that card"
	return result


static func _ours(name: String) -> bool:
	for p in PREFIXES:
		if name.begins_with(p):
			return true
	return false


static func _bring_folder(path: String, card_folder: String, replace: bool, result: Dictionary) -> Dictionary:
	# a folder of save directories (or one save directory itself)
	var dirs := PackedStringArray()
	if _ours(path.get_file()):
		dirs.append(path)
	else:
		for d in DirAccess.get_directories_at(path):
			if _ours(d):
				dirs.append(path.path_join(d))
	for d in dirs:
		var name := d.get_file()
		var to := card_folder.path_join(name)
		if DirAccess.dir_exists_absolute(to) and not replace:
			result.skipped.append(name)
			continue
		DirAccess.make_dir_recursive_absolute(to)
		for f in DirAccess.get_files_at(d):
			DirAccess.copy_absolute(d.path_join(f), to.path_join(f))
		result.copied.append(name)
	result.ok = not dirs.is_empty()
	if dirs.is_empty():
		result.error = "no save of this game in that folder"
	return result


func open(path: String) -> bool:
	data = FileAccess.get_file_as_bytes(path)
	if data.size() < 0x200 or data.slice(0, MAGIC.length()).get_string_from_ascii() != MAGIC:
		error = "not a PlayStation 2 memory card file"
		return false
	page_len = data.decode_u16(0x28)
	pages_per_cluster = data.decode_u16(0x2A)
	var clusters := int(data.decode_u32(0x30))
	alloc_offset = int(data.decode_u32(0x34))
	root_cluster = int(data.decode_u32(0x3C))
	cluster_size = page_len * pages_per_cluster
	var pages := clusters * pages_per_cluster
	# with the error correction bytes (16 for every 512) or without
	raw_page = page_len + page_len / 32 if data.size() >= pages * (page_len + page_len / 32) else page_len
	for k in 32:
		ifc.append(int(data.decode_u32(0x50 + k * 4)))
	if page_len <= 0 or pages_per_cluster <= 0 or cluster_size > 65536:
		error = "the card's layout is not one this reads"
		return false
	return true


func cluster(absolute: int) -> PackedByteArray:
	var out := PackedByteArray()
	for k in pages_per_cluster:
		var at := (absolute * pages_per_cluster + k) * raw_page
		if at + page_len > data.size():
			out.resize(out.size() + page_len)
			continue
		out.append_array(data.slice(at, at + page_len))
	return out


func fat(n: int) -> int:
	var per := cluster_size / 4
	var indirect := n / per
	var table := cluster(ifc[indirect / per])
	var fat_cluster := int(table.decode_u32((indirect % per) * 4))
	return int(cluster(fat_cluster).decode_u32((n % per) * 4))


func read_chain(first: int, length: int) -> PackedByteArray:
	var out := PackedByteArray()
	var n := first
	var guard := 0
	while out.size() < length and guard < 100000:
		out.append_array(cluster(alloc_offset + n))
		var e := fat(n)
		if (e & 0x80000000) == 0 or (e & 0x7FFFFFFF) == 0x7FFFFFFF:
			break
		n = e & 0x7FFFFFFF
		guard += 1
	return out.slice(0, length)


func list_dir(first: int) -> Array:
	# the directory's first entry ("."): its length is the number of entries
	var head := read_chain(first, 512)
	if head.size() < 512:
		return []
	var count := int(head.decode_u32(4))
	var bytes := read_chain(first, count * 512)
	var out := []
	for k in count:
		var e := bytes.slice(k * 512, k * 512 + 512)
		if e.size() < 512:
			break
		var mode := e.decode_u16(0)
		if not (mode & DF_EXISTS):
			continue
		out.append({"mode": mode, "length": int(e.decode_u32(4)), "cluster": int(e.decode_u32(0x10)),
			"name": e.slice(0x40, 0x60).get_string_from_ascii()})
	return out
