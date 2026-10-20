extends RefCounted
# gamelib.gd - where the game library is.
#
# The game is not in this program.  An exported application holds only Godot, the extension and these scripts; the game
# library (librta_game: the game's own code, translated) is made on the player's computer from the player's own disc by
# the installer (tools/install/fromdisc.py --godot), which puts it in one place per user:
#   macOS    ~/Library/Application Support/Open Champions/RTA Godot/librta_game.dylib
#   Linux    $XDG_DATA_HOME (or ~/.local/share)/open-champions/rta-godot/librta_game.so
#   Windows  %APPDATA%\Open Champions\RTA Godot\librta_game.dll
# Looked for, in this order: --lib FILE, user://settings.cfg [game] library (chosen once in the portal's first-start
# screen), beside the extension (res://bin in the staged project), beside the executable (and the bundle's Frameworks /
# Resources), the per-user place above.

static func file_name(base := "librta_game") -> String:
	match OS.get_name():
		"Windows":
			return base + ".dll"
		"macOS":
			return base + ".dylib"
	return base + ".so"


static func standard_folder() -> String:
	match OS.get_name():
		"Windows":
			return OS.get_environment("APPDATA").path_join("Open Champions").path_join("RTA Godot")
		"macOS":
			return OS.get_environment("HOME").path_join("Library/Application Support/Open Champions/RTA Godot")
	var data := OS.get_environment("XDG_DATA_HOME")
	if data == "":
		data = OS.get_environment("HOME").path_join(".local/share")
	return data.path_join("open-champions").path_join("rta-godot")


static func saved() -> String:
	var config := ConfigFile.new()
	if config.load("user://settings.cfg") == OK:
		return String(config.get_value("game", "library", ""))
	return ""


static func save(path: String) -> void:
	var config := ConfigFile.new()
	config.load("user://settings.cfg")
	config.set_value("game", "library", path)
	config.save("user://settings.cfg")


static func candidates(given := "") -> PackedStringArray:
	var out := PackedStringArray()
	if given != "" and (given.contains("/") or given.contains("\\")):
		out.append(given)
		return out
	var file := file_name(given if given != "" else "librta_game")
	var mine := saved()
	if mine != "":
		out.append(mine)
	var exe := OS.get_executable_path().get_base_dir()
	out.append_array([ProjectSettings.globalize_path("res://bin/" + file), exe.path_join(file), exe.path_join("../Frameworks/" + file),
		exe.path_join("../Resources/" + file), standard_folder().path_join(file)])
	return out


# "" when there is none
static func find(given := "") -> String:
	for path in candidates(given):
		if FileAccess.file_exists(path):
			return path
	return ""


static func explain() -> String:
	return ("The game itself is not in this program: it is built on this computer from your own disc by the installer " +
		"(install-mac.command, install-linux.sh or install-windows.bat of the Open Champions workspace), which puts the " +
		"game library here:\n%s\nRun it once, or choose the library file if you built it elsewhere.") % standard_folder().path_join(file_name())
