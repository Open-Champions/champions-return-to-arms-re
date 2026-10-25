extends RefCounted
# edition.gd - which game the player plays: CLASSIC or REMASTERED (the portal's first screen, screens/modes.gd).
#
# No new game code: each choice is a set of the settings and room options that already exist.
#
#   classic      the game as it was: the game's own HUD (interface "original"), the overhead camera only (V does
#                not cycle), the original combat (combat.mode off, combat.aim off), no Elden Ring layer, the game's
#                own music (the boss-music director off), the look as the game draws it (scene_view.gd look keys
#                off: no sky, fog, sun, lamp, bloom, grade, Godot lights, fill, backdrop, contact shadows, cleaner
#                models, presets).  Kept: the art pack (the sharp pictures) and the display rate 60 (paced at 60).
#   remastered   the combined version: the new HUD, the look presets and cleaner models (scene_view.gd defaults),
#                the display rate auto (120 on a 120 Hz display), all five views, Hardcore mode (combat.mode
#                hardcore), aiming where you look (combat.aim look), the boss-music director with the player's own
#                tracks and - when they are on this computer - the player's Elden Ring boss tracks, and the Elden
#                Ring models layer (look.er_models, er_creatures) when the player's own converted models are there.
#
# The profile keeps the choice ([settings] game = classic | remastered; "" = never chosen: the portal behaves as
# before this screen existed).  The game scene gets it through handover.gd (main.gd `opt`) and, for a game that is
# already running, through main.gd apply_settings({"edition": ...}).
#
# Online the room carries the type the way its other options travel: in what each copy says of itself (net2 "copy",
# the fix-set word count), bit ROOM_BIT for Remastered - next to Hardcore (0x8000) and aiming (0x4000), which a
# Remastered copy has on as well.  A copy of the other type makes the room's copies differ (the session's own check
# then refuses the start) and the room screen offers the switch.

const CLASSIC := "classic"
const REMASTERED := "remastered"
const ROOM_BIT := 0x2000

# the look keys Classic turns off (scene_view.gd); Remastered leaves them to their defaults and the level presets
const CLASSIC_LOOK := "sky=off,fog=off,sun=off,lamp=off,bloom=off,grade=off,foliage=off,fill=off,lights=off,backdrop=off,contact=0,models=off,preset=off,er_models=off,er_creatures=off"
const CLASSIC_KEYS := ["sky", "fog", "sun", "lamp", "bloom", "grade", "foliage", "fill", "lights", "backdrop", "contact", "models", "preset", "er_models", "er_creatures"]


static func title(kind: String) -> String:
	return "Classic" if kind == CLASSIC else ("Remastered" if kind == REMASTERED else "")


# ---- the player's own Elden Ring files (never in the repository, never fetched) ------------------------------------
# The same places er_layer.gd and the music director look: $RTA_ER_MODELS, else beside the staged project
# (<root>/local/godot-*/project -> <root>/local/souls-ref/er-models); $RTA_ER_MUSIC, else .../souls-ref/er-music.
static func er_models_folder() -> String:
	if OS.has_environment("RTA_ER_MODELS"):
		return OS.get_environment("RTA_ER_MODELS")
	return ProjectSettings.globalize_path("res://").path_join("../../souls-ref/er-models").simplify_path()


static func er_models_found() -> bool:
	return FileAccess.file_exists(er_models_folder().path_join("default/figure.glb"))


static func er_creatures_found() -> bool:
	return DirAccess.dir_exists_absolute(er_models_folder().path_join("creatures"))


static func er_music_folder() -> String:
	if OS.has_environment("RTA_ER_MUSIC"):
		return OS.get_environment("RTA_ER_MUSIC")
	return ProjectSettings.globalize_path("res://").path_join("../../souls-ref/er-music").simplify_path()


# the player's Elden Ring boss tracks: the rows of <er-music>/BOSS-LIST.tsv (file, wem_id, ...) whose
# all/<wem_id>.ogg is there
static func er_boss_tracks() -> PackedStringArray:
	var out := PackedStringArray()
	var folder := er_music_folder()
	var f := FileAccess.open(folder.path_join("BOSS-LIST.tsv"), FileAccess.READ)
	if f == null:
		return out
	f.get_line()                        # the heading
	while not f.eof_reached():
		var cols := f.get_line().split("\t")
		if cols.size() < 2 or cols[1].strip_edges() == "":
			continue
		var path := folder.path_join("all").path_join(cols[1].strip_edges() + ".ogg")
		if FileAccess.file_exists(path) and not out.has(path):
			out.append(path)
	return out


# ---- what the game scene is given -----------------------------------------------------------------------------------
# {edition, view, views_locked, combat, aim, look, display_rate, hud_mode, music, music_er, er_models, er_note}
static func game_options(kind: String, view: String) -> Dictionary:
	if kind == CLASSIC:
		return {"edition": CLASSIC, "view": "overhead", "views_locked": true, "combat": "off", "aim": "off", "look": CLASSIC_LOOK,
			"display_rate": "60", "hud_mode": "original", "music": "off", "music_er": "off", "er_models": false, "er_note": ""}
	if kind == REMASTERED:
		var er := er_models_found()
		var look := "er_models=on,er_creatures=%s" % ("on" if er_creatures_found() else "off") if er else ""
		return {"edition": REMASTERED, "view": view if view != "" else "chase", "views_locked": false, "combat": "hardcore", "aim": "look",
			"look": look, "display_rate": "auto", "hud_mode": "new", "music": "on", "music_er": "on" if not er_boss_tracks().is_empty() else "off",
			"er_models": er, "er_note": "" if er else "Elden Ring look: needs your own Elden Ring copy - see setup"}
	return {}


# ---- the room -------------------------------------------------------------------------------------------------------
# "remastered" | "classic" | "" (the copy has said nothing of itself yet)
static func of_member(m: Dictionary) -> String:
	if int(m.get("fix_set", 0)) == 0 and int(m.get("fix_words", 0)) == 0:
		return ""
	return REMASTERED if (int(m.get("fix_words", 0)) & ROOM_BIT) != 0 else CLASSIC


# what this copy says of itself with the type folded in: "fix=9ac29719 words=189" -> words | ROOM_BIT for Remastered
static func copy_text(text: String, kind: String) -> String:
	if kind != REMASTERED:
		return text
	var at := text.find("words=")
	if at < 0:
		return text
	var words := text.substr(at + 6).get_slice(" ", 0).to_int() | ROOM_BIT
	return text.substr(0, at) + "words=%d" % words
