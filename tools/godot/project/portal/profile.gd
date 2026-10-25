extends RefCounted
# profile.gd - what the portal remembers on this computer: the name friends see, the
# character played last, the characters it has seen, and the settings.  One small file
# (portal.cfg) in the player's data folder.  No password, no account: who the player is
# online is the session's own key file (tools/recomp/net2/session.h, "net2-identity.key").
#
# The interface setting is also written where the HUD reads it (user://hud.cfg, [hud] mode),
# and the disc image's path where the game scene reads it (user://settings.cfg, [game] disc).

const VIEWS := ["overhead", "action", "chase", "shoulder", "first"]
const DEFAULTS := {
	"view": "overhead", "fullscreen": false, "sharpness": 2, "wide": true,
	"volume": 1.0, "music": 0.8, "effects": 1.0, "interface": "new", "glyphs": "auto",
	"game": "",                     # classic | remastered (edition.gd; the portal's first screen); "" = never chosen
	"er_outfits": "",               # per character class: auto | original | an outfit folder ("class:choice;...", settings.gd Game)
}

var folder := "user://"
var cfg := ConfigFile.new()
var dirty := false


func load_from(dir: String) -> void:
	folder = dir
	if not folder.ends_with("/"):
		folder += "/"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	cfg = ConfigFile.new()
	cfg.load(folder + "portal.cfg")


func save() -> void:
	cfg.save(folder + "portal.cfg")
	dirty = false


func name_shown() -> String:
	return String(cfg.get_value("player", "name", ""))


func set_name_shown(value: String) -> void:
	cfg.set_value("player", "name", value)
	save()


func first_start_done() -> bool:
	return name_shown() != ""


func setting(key: String) -> Variant:
	return cfg.get_value("settings", key, DEFAULTS.get(key))


func edition() -> String:
	var kind := String(setting("game"))
	return kind if kind in ["classic", "remastered"] else ""


func set_setting(key: String, value: Variant) -> void:
	cfg.set_value("settings", key, value)
	save()
	if key == "interface":
		# the HUD's own switch (tools/godot/project/hud/hud.gd reads [hud] mode)
		var hud := ConfigFile.new()
		hud.load(folder + "hud.cfg")
		hud.set_value("hud", "mode", "new" if String(value) == "new" else "original")
		hud.save(folder + "hud.cfg")


# ---- characters ----------------------------------------------------------------------------
# A character is {name, cls, level}: text as the game gave it (read from the running game's
# state, or from the memory card through the session's local_characters).
func character() -> Dictionary:
	var c: Variant = cfg.get_value("character", "last", {})
	return c if c is Dictionary else {}


func set_character(c: Dictionary) -> void:
	cfg.set_value("character", "last", {"name": String(c.get("name", "")), "cls": String(c.get("cls", "")), "level": int(c.get("level", 0))})
	remember_character(c)
	save()


func known_characters() -> Array:
	var list: Variant = cfg.get_value("character", "known", [])
	return list if list is Array else []


func remember_character(c: Dictionary) -> void:
	var name := String(c.get("name", ""))
	if name == "":
		return
	var list := known_characters().duplicate()
	var entry := {"name": name, "cls": String(c.get("cls", "")), "level": int(c.get("level", 0))}
	for k in list.size():
		if String(list[k].get("name", "")) == name:
			list[k] = entry
			cfg.set_value("character", "known", list)
			return
	list.push_front(entry)
	cfg.set_value("character", "known", list)


# ---- the disc image ------------------------------------------------------------------------
func disc_path() -> String:
	var args := OS.get_cmdline_user_args()
	var at := args.find("--disc")
	if at >= 0 and at + 1 < args.size():
		return args[at + 1]
	if OS.has_environment("RTA_DISC"):
		return OS.get_environment("RTA_DISC")
	var game := ConfigFile.new()
	if game.load(folder + "settings.cfg") == OK:
		return String(game.get_value("game", "disc", ""))
	return ""


func disc_found() -> bool:
	var path := disc_path()
	return path != "" and FileAccess.file_exists(path)


# the game library (res://gamelib.gd): built on this computer from the player's disc by the installer
func library_path() -> String:
	var args := OS.get_cmdline_user_args()
	var at := args.find("--lib")
	return (load("res://gamelib.gd") as GDScript).call("find", args[at + 1] if at >= 0 and at + 1 < args.size() else "")


func library_found() -> bool:
	return library_path() != ""


# both: the disc image and the library made from it
func game_ready() -> bool:
	return disc_found() and library_found()


func set_disc_path(path: String) -> void:
	var game := ConfigFile.new()
	game.load(folder + "settings.cfg")
	game.set_value("game", "disc", path)
	game.save(folder + "settings.cfg")
