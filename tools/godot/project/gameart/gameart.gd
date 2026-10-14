extends RefCounted
# gameart.gd - the game's own interface art, read at run time from the PLAYER'S disc image.
#
# Nothing of the game is in this project: catalogue.gd says only WHERE a picture is (archive, entry, how its
# two fields are woven, the part used, the art pack's file name).  The pictures are read from the disc image
# the game library is given (--disc, $RTA_DISC, user://settings.cfg [game] disc), decoded here (the texture
# packets of tools/play-net/disctex.py: GS transfers, swizzled 4- and 8-bit pages, palettes), and - where the
# player has a 4x art pack (tools/play-net/README.md) - taken from the pack's enlarged file of the same name.
# Results are cached as PNG under the player's data folder (user://gameart/cache), so a later start reads
# no disc at all.
#
#   GameArt.start()                       once (any skin calls it): finds the disc, loads or builds the cache
#   GameArt.ready() -> bool               the art is there (the "game" look can be drawn)
#   GameArt.mode() -> "game" | "clean"    the player's choice (user://gameart.cfg [gameart] art = auto|game|clean)
#   GameArt.tex(id, scale := 1.0)         Texture2D of a catalogue entry; `scale` = screen pixels per texel of the
#                                         returned picture's source, picks a sharp smaller copy when drawn small
#   GameArt.texel(id) -> float            pixels of the loaded picture per game texel (4 from the pack, 1 disc)
#   GameArt.font(id) -> Font              the game's bitmap fonts as a Godot font (null when not loaded)
#   GameArt.nine(ci, id_prefix, rect, border, ...)   nine-slice of the frame pieces (frame_topleft ...)
# A command line "--art-pack DIR" or [gameart] pack = DIR names the pack; default: the emulator's folder
# (macOS ~/Library/Application Support/Play-RTA/textures/replace) or <user data>/art-pack.

const Cat := preload("res://gameart/catalogue.gd")
const CACHE := "user://gameart/cache"
const SETTINGS := "user://gameart.cfg"
const CACHE_VERSION := 3

static var _started := false
static var _ready := false
static var _working := false
static var disc_path := ""
static var pack_dir := ""
static var problem := ""                 # why the art is not there, in words
static var stats := {}                   # what the start did: times, counts (for the notes and `cost`)
static var _images := {}                 # id -> Image (RGBA8, alpha 0..255)
static var _lazy := {}                   # id -> true: in the cache, not read yet
static var _texel := {}                  # id -> pixels per game texel
static var _textures := {}               # [id, level] -> ImageTexture
static var _fonts := {}
static var _glyphs := {}                 # font id -> {glyphs: [[code,u0,u1,v0,v1,yoff,adv]], kerns: [[left,right,amount]]}
static var _mutex := Mutex.new()
static var _task := -1
static var _listeners: Array[Callable] = []


# ---- the switch -----------------------------------------------------------------------------------------
static func setting() -> String:
	var c := ConfigFile.new()
	if c.load(SETTINGS) == OK:
		return String(c.get_value("gameart", "art", "auto"))
	return "auto"


static func set_setting(value: String) -> void:
	var c := ConfigFile.new()
	c.load(SETTINGS)
	c.set_value("gameart", "art", value)
	c.save(SETTINGS)


# "game" when the player wants it (or did not choose) and the art is there; "clean" otherwise
static func mode() -> String:
	var want := setting()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--art="):
			want = a.substr(6)
	if want == "clean":
		return "clean"
	start()
	return "game" if _ready else "clean"


static func ready() -> bool:
	return _ready


# the player wants the game's look and a disc image is there (the art may still be on its way: when_ready)
static func wanted() -> bool:
	var want := setting()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--art="):
			want = a.substr(6)
	if want == "clean":
		return false
	start()
	return disc_path != "" and problem == ""


# every canvas item of the running program drawn again (once, when the art arrives)
static func redraw_all() -> void:
	var tree := Engine.get_main_loop() as SceneTree
	if tree == null:
		return
	var stack: Array[Node] = [tree.root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is CanvasItem:
			(n as CanvasItem).queue_redraw()
		for c in n.get_children():
			stack.append(c)


# a function called once the art has arrived (a first start builds the cache on a thread)
static func when_ready(f: Callable) -> void:
	if _ready:
		f.call()
	else:
		_listeners.append(f)


# ---- start ----------------------------------------------------------------------------------------------
static func start() -> void:
	if _started:
		return
	_started = true
	var t0 := Time.get_ticks_usec()
	disc_path = _find_disc()
	pack_dir = _find_pack()
	if disc_path == "":
		problem = "no disc image found"
		return
	var index := ConfigFile.new()
	var sig := _disc_signature()
	var complete: bool = index.load(CACHE + "/index.cfg") == OK and index.get_value("cache", "disc", "") == sig \
		and int(index.get_value("cache", "version", 0)) == CACHE_VERSION and int(index.get_value("cache", "catalogue", 0)) == Cat.VERSION
	if complete:
		for id in Cat.ENTRIES:
			if String(index.get_value("entries", id, "")) != _source_of(id) or not FileAccess.file_exists(CACHE + "/" + id + ".rgba"):
				complete = false
				break
	if complete:
		# a cached start: every picture from the cache, nothing read from the disc
		_load_cached(index)
		stats["start"] = "cached"
		stats["start_us"] = Time.get_ticks_usec() - t0
		_ready = true
		return
	# a first start (or the disc / pack / catalogue changed): build the cache on a thread; clean until it is done
	_working = true
	stats["start"] = "building"
	_task = WorkerThreadPool.add_task(_build.bind(sig, t0), false, "gameart cache")


static func _arrived() -> void:
	_ready = _images.size() > 0 or not _lazy.is_empty()
	if _ready:
		redraw_all()
	for f in _listeners:
		if f.is_valid():
			f.call()
	_listeners.clear()


static func wait() -> void:
	# for tests: block until a first start's thread is done
	if _task >= 0:
		WorkerThreadPool.wait_for_task_completion(_task)
		_task = -1
		if not _ready:
			_arrived()


static func _find_disc() -> String:
	var args := OS.get_cmdline_user_args()
	for k in range(args.size() - 1):
		if args[k] == "--disc":
			return args[k + 1] if FileAccess.file_exists(args[k + 1]) else ""
	if OS.has_environment("RTA_DISC") and FileAccess.file_exists(OS.get_environment("RTA_DISC")):
		return OS.get_environment("RTA_DISC")
	var c := ConfigFile.new()
	if c.load("user://settings.cfg") == OK:
		var p := String(c.get_value("game", "disc", ""))
		if p != "" and FileAccess.file_exists(p):
			return p
	return ""


static func _find_pack() -> String:
	var args := OS.get_cmdline_user_args()
	for k in range(args.size() - 1):
		if args[k] == "--art-pack":
			return args[k + 1]
	var c := ConfigFile.new()
	if c.load(SETTINGS) == OK and String(c.get_value("gameart", "pack", "")) != "":
		return String(c.get_value("gameart", "pack", ""))
	var candidates := [ProjectSettings.globalize_path("user://art-pack")]
	if OS.get_name() == "macOS":
		candidates.append(OS.get_environment("HOME") + "/Library/Application Support/Play-RTA/textures/replace")
	for p in candidates:
		if DirAccess.dir_exists_absolute(p):
			return p
	return ""


static func _disc_signature() -> String:
	var f := FileAccess.open(disc_path, FileAccess.READ)
	if f == null:
		return ""
	return "%s|%d" % [disc_path, f.get_length()]


static func _source_of(id: String) -> String:
	var e: Dictionary = Cat.ENTRIES[id]
	var name := String(e.name)
	if pack_dir != "" and FileAccess.file_exists(pack_dir + "/" + name):
		return "pack:" + name
	return "disc:" + name


static func _load_cached(index: ConfigFile) -> void:
	# nothing is read yet: each picture comes out of the cache when a skin first asks for it
	for id in Cat.ENTRIES:
		_texel[id] = float(index.get_value("texel", id, 1.0))
		_lazy[id] = true
	for id in ["font_med", "font_small", "font_title", "font_title_small"]:
		var j = JSON.parse_string(FileAccess.get_file_as_string(CACHE + "/" + id + ".json"))
		if j is Dictionary:
			_glyphs[id] = j


# ---- the cache: built once from the disc and the pack ---------------------------------------------------
static func _build(sig: String, t0: int) -> void:
	var iso := Iso.new()
	if not iso.open(disc_path):
		problem = "the disc image could not be read as ISO 9660"
		call_deferred_arrived()
		return
	DirAccess.make_dir_recursive_absolute(CACHE)
	var index := ConfigFile.new()
	var lumps := {}
	var n_pack := 0
	var n_disc := 0
	var bad := 0
	var slow := {}
	for id in Cat.ENTRIES:
		var te := Time.get_ticks_usec()
		var e: Dictionary = Cat.ENTRIES[id]
		var lump := String(e.lump)
		if not lumps.has(lump):
			lumps[lump] = iso.lump(lump)
		var entries: Dictionary = lumps[lump]
		if not entries.has(String(e.entry)):
			bad += 1
			continue
		var data: PackedByteArray = iso.read_entry(entries[String(e.entry)])
		var tex_data := data
		if String(e.entry).ends_with(".fnt"):
			var g := Fnt.parse(data)
			if g.is_empty():
				bad += 1
				continue
			_glyphs[id] = {"glyphs": g.glyphs, "kerns": g.kerns}
			var jf := FileAccess.open(CACHE + "/" + id + ".json", FileAccess.WRITE)
			jf.store_string(JSON.stringify(_glyphs[id]))
			jf = null
			tex_data = g.texture
		var source := _source_of(id)
		var img: Image = null
		var texel := 1.0
		if source.begins_with("pack:"):
			var r := _from_pack(e)
			if r.size() == 2:
				img = r[0]
				texel = r[1]
				n_pack += 1
		if img == null:
			var d := Tex.decode(tex_data)
			if d.is_empty() or int(d.w) != int(e.page[0]) or int(d.h) != int(e.page[1]):
				bad += 1          # not the picture the catalogue knows: another disc
				continue
			img = _shape(d, e)
			source = "disc:" + String(e.name)
			n_disc += 1
		var ts := Time.get_ticks_usec()
		_save(id, img)
		if Time.get_ticks_usec() - te > 100000:
			slow[id] = [(ts - te) / 1000, (Time.get_ticks_usec() - ts) / 1000]
		index.set_value("entries", id, _source_of(id))     # what was wanted: a pack file that failed is not tried at every start
		index.set_value("made_from", id, source)
		index.set_value("texel", id, texel)
		_mutex.lock()
		_images[id] = img
		_texel[id] = texel
		_mutex.unlock()
	index.set_value("cache", "disc", sig)
	index.set_value("cache", "version", CACHE_VERSION)
	index.set_value("cache", "catalogue", Cat.VERSION)
	if bad == 0:
		index.save(CACHE + "/index.cfg")
	else:
		problem = "%d pictures were not found on this disc image" % bad
	stats["from_pack"] = n_pack
	stats["from_disc"] = n_disc
	stats["missing"] = bad
	stats["slow_ms"] = slow
	stats["start_us"] = Time.get_ticks_usec() - t0
	call_deferred_arrived()


static func call_deferred_arrived() -> void:
	_working = false
	Callable(load("res://gameart/gameart.gd"), "_arrived").call_deferred()


# the cache's form: width, height, then RGBA8, compressed with zstd (writes and reads far faster than PNG)
static func _save(id: String, img: Image) -> void:
	var f := FileAccess.open_compressed(CACHE + "/" + id + ".rgba", FileAccess.WRITE, FileAccess.COMPRESSION_ZSTD)
	f.store_32(img.get_width())
	f.store_32(img.get_height())
	f.store_buffer(img.get_data())
	f = null


static func _read(id: String) -> Image:
	var f := FileAccess.open_compressed(CACHE + "/" + id + ".rgba", FileAccess.READ, FileAccess.COMPRESSION_ZSTD)
	if f == null:
		return null
	var w := f.get_32()
	var h := f.get_32()
	var data := f.get_buffer(w * h * 4)
	if w <= 0 or h <= 0 or data.size() != w * h * 4:
		return null
	return Image.create_from_data(w, h, false, Image.FORMAT_RGBA8, data)


static func _img(id: String) -> Image:
	var img: Image = _images.get(id)
	if img == null and _lazy.has(id):
		_lazy.erase(id)
		var t0 := Time.get_ticks_usec()
		img = _read(id)
		stats["lazy_us"] = int(stats.get("lazy_us", 0)) + Time.get_ticks_usec() - t0
		stats["lazy_count"] = int(stats.get("lazy_count", 0)) + 1
		if img != null:
			_images[id] = img
	return img


# the pack's enlarged file: first woven copy, the catalogue's rectangle, alpha made 0..255
static func _from_pack(e: Dictionary) -> Array:
	var img := Image.load_from_file(pack_dir + "/" + String(e.name))
	if img == null:
		return []
	img.convert(Image.FORMAT_RGBA8)
	var s := img.get_width() / int(e.page[0])
	if s < 1 or img.get_width() != s * int(e.page[0]):
		return []
	var r: Array = e.rect
	var part := img.get_region(Rect2i(int(r[0]) * s, int(r[1]) * s, int(r[2]) * s, int(r[3]) * s))
	if e.get("opaque", false):
		part.convert(Image.FORMAT_RGB8)          # opaque everywhere: alpha 255 without a pass over the pixels
		part.convert(Image.FORMAT_RGBA8)
	else:
		_double_alpha(part)
	return [part, float(s)]


static func _double_alpha(img: Image) -> void:
	var b := img.get_data()
	var n := b.size()
	for i in range(3, n, 4):
		var a := b[i]
		b[i] = 255 if a >= 128 else a * 2
	img.set_data(img.get_width(), img.get_height(), false, Image.FORMAT_RGBA8, b)


# woven two fields -> one picture, cut to the rectangle
static func _shape(d: Dictionary, e: Dictionary) -> Image:
	var w := int(d.w)
	var h := int(d.h)
	var src: PackedByteArray = d.rgba
	var rows := int(e.rows)
	var out := src
	var oh := h
	if rows > 0:
		out = PackedByteArray()
		var stride := w * 4
		for k in range(rows):
			out.append_array(src.slice(k * stride, (k + 1) * stride))
			var j := mini(rows + k, h - 1)
			out.append_array(src.slice(j * stride, (j + 1) * stride))
		oh = rows * 2
	var img := Image.create_from_data(w, oh, false, Image.FORMAT_RGBA8, out)
	if e.rect is Array:
		var r: Array = e.rect
		img = img.get_region(Rect2i(int(r[0]), int(r[1]), int(r[2]), int(r[3])))
	return img


# ---- what the skins call --------------------------------------------------------------------------------
static func has(id: String) -> bool:
	return _ready and (_images.has(id) or _lazy.has(id))


static func texel(id: String) -> float:
	return float(_texel.get(id, 1.0))


static func size_texels(id: String) -> Vector2:
	var img: Image = _img(id)
	if img == null:
		return Vector2.ZERO
	return Vector2(img.get_size()) / texel(id)


static func image(id: String) -> Image:
	return _img(id)


# `scale`: screen pixels per pixel of the loaded picture.  A picture drawn at a quarter of its size or less is
# given as a copy made smaller with a good filter (Lanczos), so that the enlarged art stays sharp, not grainy.
static func tex(id: String, scale := 1.0) -> Texture2D:
	var img: Image = _img(id)
	if img == null:
		return null
	var level := 0
	var k := scale
	while k < 0.5 and level < 4 and img.get_width() >> (level + 1) >= 8 and img.get_height() >> (level + 1) >= 4:
		k *= 2.0
		level += 1
	var key := [id, level]
	var t: ImageTexture = _textures.get(key)
	if t == null:
		var copy := img
		if level > 0:
			copy = img.duplicate()
			copy.resize(maxi(1, img.get_width() >> level), maxi(1, img.get_height() >> level), Image.INTERPOLATE_LANCZOS)
		t = ImageTexture.create_from_image(copy)
		_textures[key] = t
	return t


# draw a whole picture into `rect` (any size), the sharp copy for that size
static func draw(ci: CanvasItem, id: String, rect: Rect2, modulate := Color.WHITE) -> bool:
	var img: Image = _img(id)
	if img == null:
		return false
	var scale := minf(rect.size.x / img.get_width(), rect.size.y / img.get_height())
	var t := tex(id, scale)
	ci.draw_texture_rect(t, rect, false, modulate)
	return true


# draw a part (`src` in game texels of the picture) into `rect`
static func draw_part(ci: CanvasItem, id: String, rect: Rect2, src: Rect2, modulate := Color.WHITE) -> bool:
	var img: Image = _img(id)
	if img == null:
		return false
	var k := texel(id)
	var scale := minf(rect.size.x / maxf(1.0, src.size.x * k), rect.size.y / maxf(1.0, src.size.y * k))
	var t := tex(id, scale)
	var f := float(t.get_width()) / img.get_width() * k
	ci.draw_texture_rect_region(t, rect, Rect2(src.position * f, src.size * f), modulate, false, true)
	return true


# nine pieces <prefix>_topleft ... _botright; `border` = screen pixels of a corner piece's side.  The centre is
# not drawn (the skins lay their own fill); rails are stretched along their length.
static func nine(ci: CanvasItem, prefix: String, rect: Rect2, border: float, modulate := Color.WHITE) -> bool:
	if not has(prefix + "_topleft"):
		return false
	var b := minf(border, minf(rect.size.x, rect.size.y) * 0.5)
	var x0 := rect.position.x
	var y0 := rect.position.y
	var x1 := rect.end.x - b
	var y1 := rect.end.y - b
	var iw := x1 - x0 - b
	var ih := y1 - y0 - b
	var c := size_texels(prefix + "_topleft")
	var full := Rect2(Vector2.ZERO, c)
	draw_part(ci, prefix + "_topleft", Rect2(x0, y0, b, b), full, modulate)
	draw_part(ci, prefix + "_topright", Rect2(x1, y0, b, b), full, modulate)
	draw_part(ci, prefix + "_botleft", Rect2(x0, y1, b, b), full, modulate)
	draw_part(ci, prefix + "_botright", Rect2(x1, y1, b, b), full, modulate)
	if iw > 0.5:
		draw_part(ci, prefix + "_top", Rect2(x0 + b, y0, iw, b), Rect2(Vector2.ZERO, size_texels(prefix + "_top")), modulate)
		draw_part(ci, prefix + "_bot", Rect2(x0 + b, y1, iw, b), Rect2(Vector2.ZERO, size_texels(prefix + "_bot")), modulate)
	if ih > 0.5:
		draw_part(ci, prefix + "_left", Rect2(x0, y0 + b, b, ih), Rect2(Vector2.ZERO, size_texels(prefix + "_left")), modulate)
		draw_part(ci, prefix + "_right", Rect2(x1, y0 + b, b, ih), Rect2(Vector2.ZERO, size_texels(prefix + "_right")), modulate)
	return true


# ---- fonts ----------------------------------------------------------------------------------------------
# The game's .fnt: a page (woven like any interface picture), a 256-entry character map, 16-byte glyph records
# (code, u0, u1, v0, v1, y offset from the line's top, advance, first kerning record) and 6-byte kerning records
# (left glyph index, right glyph index, amount).  `cap` = the height the capital letters should have, as a
# share of the font size (Open Sans: 0.72), so that the game's font stands in at the sizes the layouts use.
static func font(id: String, cap := 0.72) -> Font:
	var key := [id, cap]
	if _fonts.has(key):
		return _fonts[key]
	var img: Image = _img(id)
	if img == null or not _glyphs.has(id):
		return null
	var k := texel(id)
	var gl: Array = _glyphs[id].glyphs
	var by_code := {}
	for g in gl:
		by_code[int(g[0])] = g
	# capital height without the shadow the page carries (about one texel round each letter)
	var caps: Array = []
	var bottoms: Array = []
	for ch in "HIEFTLN":
		var g = by_code.get(ch.unicode_at(0))
		if g != null:
			caps.append(float(g[4] - g[3]) - 2.0)
			bottoms.append(float(g[5] + g[4] - g[3]))
	caps.sort()
	bottoms.sort()
	var cap_h: float = caps[caps.size() / 2] if not caps.is_empty() else 14.0
	var base: float = (bottoms[bottoms.size() / 2] - 1.0) if not bottoms.is_empty() else 20.0
	var size := int(round(cap_h * k / cap))
	var f := FontFile.new()
	f.fixed_size = size
	f.fixed_size_scale_mode = TextServer.FIXED_SIZE_SCALE_ENABLED
	f.generate_mipmaps = true
	f.allow_system_fallback = false
	var cs := Vector2i(size, 0)
	var page := img
	f.set_texture_image(0, cs, 0, page)
	var lowest := base
	for g in gl:
		var code := int(g[0])
		if code == 0:
			continue
		var u0 := float(g[1])
		var u1 := float(g[2])
		var v0 := float(g[3])
		var v1 := float(g[4])
		f.set_glyph_advance(0, size, code, Vector2(float(g[6]) * k, 0))
		f.set_glyph_offset(0, cs, code, Vector2(0, (float(g[5]) - base) * k))
		f.set_glyph_size(0, cs, code, Vector2(u1 - u0, v1 - v0) * k)
		f.set_glyph_uv_rect(0, cs, code, Rect2(u0 * k, v0 * k, (u1 - u0) * k, (v1 - v0) * k))
		f.set_glyph_texture_idx(0, cs, code, 0)
		lowest = maxf(lowest, float(g[5]) + v1 - v0)
	f.set_cache_ascent(0, size, base * k)
	f.set_cache_descent(0, size, (lowest - base) * k * 0.6)
	for kr in _glyphs[id].kerns:
		var a := int(kr[0])
		var b := int(kr[1])
		if a < gl.size() and b < gl.size():
			f.set_kerning(0, size, Vector2i(int(gl[a][0]), int(gl[b][0])), Vector2(float(kr[2]) * k, 0))
	_fonts[key] = f
	return f


# ---- the disc image: ISO 9660 and the game's .LMP archives ----------------------------------------------
class Iso:
	var file: FileAccess
	var root := {}

	func open(path: String) -> bool:
		file = FileAccess.open(path, FileAccess.READ)
		if file == null:
			return false
		file.seek(16 * 2048)
		var v := file.get_buffer(2048)
		if v.size() < 2048 or v.slice(1, 6).get_string_from_ascii() != "CD001":
			return false
		root = _record(v, 156)
		return true

	func _record(d: PackedByteArray, o: int) -> Dictionary:
		var n := d[o + 32]
		return {"lba": d.decode_u32(o + 2), "size": d.decode_u32(o + 10), "flags": d[o + 25],
			"name": d.slice(o + 33, o + 33 + n).get_string_from_ascii().split(";")[0].to_upper()}

	func _list(dir: Dictionary) -> Array:
		file.seek(int(dir.lba) * 2048)
		var data := file.get_buffer(int(dir.size))
		var out := []
		var o := 0
		while o < data.size():
			var n := data[o]
			if n == 0:
				o = (o / 2048 + 1) * 2048
				continue
			out.append(_record(data, o))
			o += n
		return out

	func find(path: String) -> Dictionary:
		var at := root
		for part in path.to_upper().split("/"):
			var found := {}
			for r in _list(at):
				if r.name == part:
					found = r
					break
			if found.is_empty():
				return {}
			at = found
		return at

	# entry name -> [absolute offset, size]
	func lump(path: String) -> Dictionary:
		var r := find(path)
		if r.is_empty():
			return {}
		var base := int(r.lba) * 2048
		file.seek(base)
		var head := file.get_buffer(mini(int(r.size), 65536))
		var count := head.decode_u32(0)
		if count > 100000:
			return {}
		var need := 4 + count * 12
		if need > head.size():
			file.seek(base)
			head = file.get_buffer(mini(int(r.size), need + 65536))
		var out := {}
		for i in range(count):
			var name_at := head.decode_u32(4 + i * 12)
			var data_at := head.decode_u32(8 + i * 12)
			var size := head.decode_u32(12 + i * 12)
			if name_at + 64 > head.size():
				file.seek(base + name_at)
				var nb := file.get_buffer(64)
				out[nb.get_string_from_ascii().to_lower()] = [base + data_at, size]
			else:
				var e := name_at
				while e < head.size() and head[e] != 0:
					e += 1
				out[head.slice(name_at, e).get_string_from_ascii().to_lower()] = [base + data_at, size]
		return out

	func read_entry(where: Array) -> PackedByteArray:
		file.seek(int(where[0]))
		return file.get_buffer(int(where[1]))


class Fnt:
	static func parse(d: PackedByteArray) -> Dictionary:
		if d.size() < 0x214:
			return {}
		var n := d.decode_u16(0)
		var grec := d.decode_u32(8)
		var kern := d.decode_u32(12)
		var tex := d.decode_u32(16)
		if grec + n * 16 > d.size() or tex >= d.size():
			return {}
		var glyphs := []
		for i in range(n):
			var o := grec + i * 16
			glyphs.append([d.decode_u16(o), d.decode_u16(o + 2), d.decode_u16(o + 4), d.decode_u16(o + 6), d.decode_u16(o + 8), d.decode_s16(o + 10), d.decode_u16(o + 12)])
		var kerns := []
		var o2 := kern
		while o2 + 6 <= tex:
			var a := d.decode_u16(o2)
			if a == 0xffff:
				break
			kerns.append([a, d.decode_u16(o2 + 2), d.decode_s16(o2 + 4)])
			o2 += 6
		return {"glyphs": glyphs, "kerns": kerns, "texture": d.slice(tex)}


# ---- one texture: the GS packets of a .tex entry -> RGBA ------------------------------------------------
class Tex:
	const BLOCK_8x4 := [[0, 1, 4, 5, 16, 17, 20, 21], [2, 3, 6, 7, 18, 19, 22, 23], [8, 9, 12, 13, 24, 25, 28, 29], [10, 11, 14, 15, 26, 27, 30, 31]]
	const BLOCK_4x8 := [[0, 2, 8, 10], [1, 3, 9, 11], [4, 6, 12, 14], [5, 7, 13, 15], [16, 18, 24, 26], [17, 19, 25, 27], [20, 22, 28, 30], [21, 23, 29, 31]]
	const WORD := [0, 1, 4, 5, 8, 9, 12, 13]
	static var t32 := PackedInt32Array()
	static var t8 := PackedInt32Array()
	static var t4 := PackedInt32Array()

	static func _column_word(x: int, yy: int) -> Array:
		var r := yy & 3
		var xi := (x & 7) ^ (4 if ((yy + 2) >> 2) & 1 else 0)
		return [(yy >> 2) * 16 + (r & 1) * 2 + WORD[xi], r >> 1]

	static func _tables() -> void:
		if not t32.is_empty():
			return
		t32.resize(32 * 64)
		for y in range(32):
			for x in range(64):
				t32[y * 64 + x] = BLOCK_8x4[(y >> 3) & 3][(x >> 3) & 7] * 64 + ((y & 7) >> 1) * 16 + (y & 1) * 2 + WORD[x & 7]
		t8.resize(64 * 128)
		for y in range(64):
			for x in range(128):
				var cw := _column_word(x, y & 15)
				t8[y * 128 + x] = BLOCK_8x4[(y >> 4) & 3][(x >> 4) & 7] * 256 + cw[0] * 4 + cw[1] + (((x >> 3) & 1) << 1)
		t4.resize(128 * 128)
		for y in range(128):
			for x in range(128):
				var cw := _column_word(x, y & 15)
				t4[y * 128 + x] = (BLOCK_4x8[(y >> 4) & 7][(x >> 5) & 3] * 256 + cw[0] * 4) * 2 + cw[1] + (((x >> 3) & 3) << 1)

	static func _clut(i: int) -> int:
		return (i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)

	static func _transfers(d: PackedByteArray, start: int, end: int) -> Array:
		var dbw := 0
		var dpsm := 0
		var px := 0
		var py := 0
		var pw := 0
		var ph := 0
		var buffer := -1
		var out := []
		var o := start
		while o + 16 <= end:
			var low := d.decode_u64(o)
			o += 16
			var nloop := low & 0x7FFF
			var flg := (low >> 58) & 3
			var nreg := (low >> 60) & 15
			if flg == 0:
				for _i in range(nloop * (nreg if nreg != 0 else 16)):
					var value := d.decode_u64(o)
					var reg := d.decode_u64(o + 8) & 0xFF
					o += 16
					if reg == 0x50:
						buffer += 1
						dbw = (value >> 48) & 0x3F
						dpsm = (value >> 56) & 0x3F
					elif reg == 0x51:
						px = (value >> 32) & 0x7FF
						py = (value >> 48) & 0x7FF
					elif reg == 0x52:
						pw = value & 0xFFF
						ph = (value >> 32) & 0xFFF
			elif flg == 2:
				var bits := {0x00: 32, 0x14: 4, 0x13: 8}.get(dpsm, 0) as int
				if bits == 0 or buffer < 0:
					return []
				var size := (pw * ph * bits + 7) / 8
				if size > nloop * 16 or o + size > end:
					return []
				out.append({"buffer": buffer, "dbw": dbw, "dpsm": dpsm, "x": px, "y": py, "w": pw, "h": ph, "data": d.slice(o, o + size)})
				o += nloop * 16
			else:
				return []
		return out

	# {w, h, rgba} with alpha 0..255 (the console's 128 = opaque), or {} when this is not a picture we follow
	static func decode(d: PackedByteArray) -> Dictionary:
		if d.size() < 0x90:
			return {}
		var qwc := d.decode_u16(6)
		var flags := d.decode_u16(8)
		var tex0 := d.decode_u32(0x0C)
		var packet := d.decode_u32(0x10)
		if packet < 0x14 or packet + qwc * 16 > d.size() or flags & 0x0080:
			return {}
		var tbw := tex0 & 0x3F
		var psm := (tex0 >> 6) & 0x3F
		var nw := 1 << ((tex0 >> 12) & 15)
		var nh := 1 << ((tex0 >> 16) & 15)
		var pieces := _transfers(d, packet, packet + qwc * 16)
		if pieces.is_empty():
			return {}
		var last := int(pieces[-1].buffer)
		var image := pieces.filter(func(p): return int(p.buffer) == last)
		var palette := pieces.filter(func(p): return int(p.buffer) != last)
		# the palette, alpha already doubled
		var pal := PackedByteArray()
		if psm != 0x00:
			var entries := 256 if psm == 0x13 else 16
			if palette.size() != 1 or palette[0].data.size() < entries * 4:
				return {}
			var src: PackedByteArray = palette[0].data
			pal.resize(entries * 4)
			for i in range(entries):
				var j := _clut(i) if psm == 0x13 else i
				pal[i * 4] = src[j * 4]
				pal[i * 4 + 1] = src[j * 4 + 1]
				pal[i * 4 + 2] = src[j * 4 + 2]
				var a := src[j * 4 + 3]
				pal[i * 4 + 3] = 255 if a >= 128 else a * 2
		var first: Dictionary = image[0]
		var w := 0
		var h := 0
		var out := PackedByteArray()
		var plain: bool = image.size() == 1 and int(first.dpsm) == psm and int(first.dbw) == tbw and int(first.x) == 0 and int(first.y) == 0
		if plain:
			w = mini(int(first.w), nw)
			h = mini(int(first.h), nh)
			var fw := int(first.w)
			var src: PackedByteArray = first.data
			out.resize(w * h * 4)
			for y in range(h):
				for x in range(w):
					var i := y * fw + x
					var o := (y * w + x) * 4
					if psm == 0x00:
						out[o] = src[i * 4]
						out[o + 1] = src[i * 4 + 1]
						out[o + 2] = src[i * 4 + 2]
						var a := src[i * 4 + 3]
						out[o + 3] = 255 if a >= 128 else a * 2
					else:
						var c := src[i] if psm == 0x13 else ((src[i >> 1] >> (4 * (i & 1))) & 15)
						out[o] = pal[c * 4]
						out[o + 1] = pal[c * 4 + 1]
						out[o + 2] = pal[c * 4 + 2]
						out[o + 3] = pal[c * 4 + 3]
			return {"w": w, "h": h, "rgba": out}
		# swizzled: 32-bit pieces written into GS memory, read back as the texture's 4- or 8-bit format
		var dbw := int(first.dbw)
		if psm != 0x13 and psm != 0x14 or tbw != 2 * dbw or dbw == 0:
			return {}
		for p in image:
			if int(p.dpsm) != 0 or int(p.dbw) != dbw:
				return {}
		_tables()
		var pages := 1
		for p in image:
			if int(p.x) + int(p.w) > dbw * 64:
				return {}
			pages = maxi(pages, ((int(p.y) + int(p.h) - 1) >> 5) * dbw + dbw)
		if psm == 0x13:
			pages = maxi(pages, ((nh - 1) >> 6) * dbw + ((nw - 1) >> 7) + 1)
		else:
			pages = maxi(pages, ((nh - 1) >> 7) * dbw + ((nw - 1) >> 7) + 1)
		var mem := PackedByteArray()
		mem.resize(pages * 8192)
		var written := PackedByteArray()
		written.resize(pages * 2048)
		for p in image:
			var src: PackedByteArray = p.data
			var pw := int(p.w)
			for yy in range(int(p.h)):
				var y := int(p.y) + yy
				var row := (y >> 5) * dbw
				var ty := (y & 31) * 64
				for xx in range(pw):
					var x := int(p.x) + xx
					var word := (row + (x >> 6)) * 2048 + t32[ty + (x & 63)]
					var s := (yy * pw + xx) * 4
					var m := word * 4
					mem[m] = src[s]
					mem[m + 1] = src[s + 1]
					mem[m + 2] = src[s + 2]
					mem[m + 3] = src[s + 3]
					written[word] = 1
		# covered extent
		var texels := PackedInt32Array()
		texels.resize(nw * nh)
		var maxx := -1
		var maxy := -1
		for y in range(nh):
			for x in range(nw):
				var c := -1
				if psm == 0x13:
					var at := ((y >> 6) * dbw + (x >> 7)) * 8192 + t8[(y & 63) * 128 + (x & 127)]
					if at < mem.size() and written[at >> 2]:
						c = mem[at]
				else:
					var at := ((y >> 7) * dbw + (x >> 7)) * 16384 + t4[(y & 127) * 128 + (x & 127)]
					if (at >> 1) < mem.size() and written[at >> 3]:
						c = (mem[at >> 1] >> (4 * (at & 1))) & 15
				texels[y * nw + x] = c
				if c >= 0:
					maxx = maxi(maxx, x)
					maxy = maxi(maxy, y)
		if maxx < 0:
			return {}
		w = maxx + 1
		h = maxy + 1
		out.resize(w * h * 4)
		for y in range(h):
			for x in range(w):
				var c := texels[y * nw + x]
				var o := (y * w + x) * 4
				if c >= 0:
					out[o] = pal[c * 4]
					out[o + 1] = pal[c * 4 + 1]
					out[o + 2] = pal[c * 4 + 2]
					out[o + 3] = pal[c * 4 + 3]
		return {"w": w, "h": h, "rgba": out}
