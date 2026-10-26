extends Node
# music.gd - the music director: the player's OWN music for boss fights.
#
# Nothing is shipped and nothing is fetched.  The feature is a folder in the game's data
# folder (the one the memory cards are in: --data, default user://data):
#     music/boss/            tracks for boss fights
#     music/level/<level>/   reserved: a level's own music   (not played yet)
#     music/menu/            reserved: the front end          (not played yet)
# into which a player puts audio files he owns: .ogg, .mp3, .wav - what Godot plays itself.
# With an empty or missing folder nothing changes at all.
#
# When the game's state says a boss is engaged (the game's own boss meter is up, or a boss
# is after a player: hud.gd / gamestate.h) and there are tracks, the GAME's music is faded
# down and one of the player's tracks fades in: shuffled, none again before all were
# played, looped while the fight lasts.  A few seconds after the boss is dead, or every
# local player is, or the boss is left behind, it crosses back to the game's music.
#
# The game's music at its own volume: the sound core mixes music as stream 2 of its stream
# driver, apart from speech (streams 0, 1) and effects (tools/recomp/sound/drivers.cpp).
# The control asked for is machine.set_option("music_volume", "0..1") (the patch line is in
# tools/godot/hud-recomp.patch).  Until the library has it, the whole game mix is ducked by
# a fixed amount instead (DUCK_DB) - effects and speech go down with the music then.
#
# Settings ([hud] in user://hud.cfg, or "app hud music on|off", "app hud music-volume 0.8").

const EXTENSIONS := ["ogg", "mp3", "wav"]
const FADE_IN := 1.6                    # seconds
const FADE_OUT := 3.0
const HOLD_AFTER := 4.0                 # the fight is over: this long before the game's music comes back
const DUCK_DB := -14.0                  # the whole mix, when the music cannot be turned down by itself
const BUS := "HudMusic"
# Loudness (docs/issues/audio-quality.md): a track is played at this RMS level at music volume 1, so that the default
# 0.8 puts it where the game's own music is (its music stream alone: -24 to -33 dBFS RMS by level, median -28).  The
# tracks players put in are mastered far louder (the Elden Ring ones: median -13 dBFS RMS, peaks at and over full
# scale): as they were they came in 13 dB over the game's music, and the game's effects on top went past full scale.
const TARGET_RMS_DB := -24.0
const PEAK_CEILING := 0.70              # -3.1 dBFS: the loudest sample of a track after its gain, at volume 1

enum { IDLE, LOADING, PLAYING, LEAVING }

var hud: Node
var state := IDLE
var level := 0.0                        # 0 the game's music .. 1 the player's track
var tracks: PackedStringArray = PackedStringArray()
var er_tracks := false                 # the portal's Remastered: the player's own Elden Ring boss tracks too, when they are on
                                        # this computer (portal/edition.gd er_boss_tracks: never shipped, never fetched)
var bag: Array = []                     # what is left of the shuffle
var last_track := ""
var folder := ""
var scanned_for := ""
var player: AudioStreamPlayer
var loader: Thread
var loaded: AudioStream
var loading_path := ""
var trim_db := 0.0                      # the playing track's loudness gain (_loudness_db)
var calm_for := 0.0
var has_music_volume := -1              # -1 not tried, 0 the library has no such option, 1 it has
var duck_applied := 0.0
var game_base_db := 0.0
var game_base_known := false
var log_lines := 0
var rng := RandomNumberGenerator.new()
var forced := -1                       # test aid ("app audio engage on|off|auto", dev/audio_tap.gd): engaged by hand, never, or by the game
var tap_bus := -1                       # test aid: the game's own sound on a bus of its own, to measure it (music.gd tap())
var tap_peak := -200.0
var tap_sum := 0.0
var tap_n := 0


func _ready() -> void:
	rng.randomize()
	if AudioServer.get_bus_index(BUS) < 0:
		AudioServer.add_bus()
		AudioServer.set_bus_name(AudioServer.bus_count - 1, BUS)
		AudioServer.set_bus_send(AudioServer.bus_count - 1, "Master")
	player = AudioStreamPlayer.new()
	player.bus = BUS
	player.volume_db = -80.0
	add_child(player)


func _exit_tree() -> void:
	if loader != null and loader.is_started():
		loader.wait_to_finish()


func say(text: String) -> void:
	if log_lines < 200:
		log_lines += 1
		print("hud music: " + text)


func _data_folder() -> String:
	var host: Node = hud.host
	var data := ""
	if host != null and host.get("opt") != null:
		data = str(host.opt.get("data", ""))
	if data == "":
		data = ProjectSettings.globalize_path("user://data")
	return data


func scan() -> void:
	folder = _data_folder().path_join("music/boss")
	tracks = PackedStringArray()
	var dir := DirAccess.open(folder)
	if dir != null:
		for name in dir.get_files():
			if name.get_extension().to_lower() in EXTENSIONS and not name.begins_with("."):
				tracks.append(folder.path_join(name))
		tracks.sort()
	if er_tracks:
		for path in (load("res://portal/edition.gd") as GDScript).call("er_boss_tracks"):
			tracks.append(path)
	bag = bag.filter(func(path): return path in tracks)
	say("%d track(s) in %s%s" % [tracks.size(), folder, " and the player's Elden Ring boss tracks" if er_tracks else ""])


func _next_track() -> String:
	# shuffle: every track once before any comes again, and not the same one twice in a row across two rounds
	if bag.is_empty():
		bag = Array(tracks)
		for k in range(bag.size() - 1, 0, -1):
			var j := rng.randi_range(0, k)
			var t = bag[k]
			bag[k] = bag[j]
			bag[j] = t
		if bag.size() > 1 and bag[bag.size() - 1] == last_track:
			var t = bag[0]
			bag[0] = bag[bag.size() - 1]
			bag[bag.size() - 1] = t
	last_track = bag.pop_back()
	return last_track


static func _load(path: String) -> AudioStream:
	# on a thread: reading and (for ogg) parsing a file must not hold a frame
	match path.get_extension().to_lower():
		"ogg":
			var s := AudioStreamOggVorbis.load_from_file(path)
			if s != null:
				s.loop = true
			return s
		"mp3":
			var bytes := FileAccess.get_file_as_bytes(path)
			if bytes.is_empty():
				return null
			var s := AudioStreamMP3.new()
			s.data = bytes
			s.loop = true
			return s
		"wav":
			var s := AudioStreamWAV.load_from_file(path)
			if s != null:
				s.loop_mode = AudioStreamWAV.LOOP_FORWARD
				s.loop_begin = 0
				var bytes_per_frame: int = (2 if s.format == AudioStreamWAV.FORMAT_16_BITS else 1) * (2 if s.stereo else 1)
				s.loop_end = s.data.size() / maxi(1, bytes_per_frame)
			return s
	return null


func _boss_engaged() -> bool:
	if not hud.ok or (hud.phase & hud.PH_LEVEL) == 0 or (hud.phase & (hud.PH_LOADING | hud.PH_FRONTEND | hud.PH_DEAD)) != 0:
		return false
	if int(hud.frame.get("boss_uid", 0)) != 0:
		return true                     # the game's own boss meter is up
	var c: PackedFloat32Array = hud.creatures
	for k in range(c.size() / hud.C_STRIDE):
		var flags := int(c[k * hud.C_STRIDE + hud.C_FLAGS])
		if (flags & hud.CF_BOSS) != 0 and (flags & hud.CF_HOSTILE) != 0 and (flags & (hud.CF_DEAD | hud.CF_INERT)) == 0 \
				and ((flags & (hud.CF_AGGRO | hud.CF_TARGETED)) != 0 or c[k * hud.C_STRIDE + hud.C_HP] < c[k * hud.C_STRIDE + hud.C_MAX]):
			return true
	return false


func tick() -> void:
	var enabled: bool = hud.setting.get("music", true)
	if hud.ok and (hud.phase & hud.PH_LEVEL) != 0:
		var here: String = hud.frame.get("level", "")
		if here != scanned_for:
			scanned_for = here
			scan()                      # once per level: files put there while playing are found at the next level
	var engaged: bool = enabled and not tracks.is_empty() and (forced == 1 if forced >= 0 else _boss_engaged())
	var dt: float = hud.dt
	match state:
		IDLE:
			if engaged:
				loading_path = _next_track()
				loaded = null
				if loader != null and loader.is_started():
					loader.wait_to_finish()
				loader = Thread.new()
				loader.start(func():
					var stream := _load(loading_path)
					var loudness := _loudness_db(stream) if stream != null else Vector3(0.0, -200.0, -200.0)
					call_deferred("_loaded", loading_path, stream, loudness))
				state = LOADING
				say("boss engaged at tick %d: loading %s" % [hud.frame.get("tick", 0), loading_path.get_file()])
		LOADING:
			pass
		PLAYING:
			level = move_toward(level, 1.0, dt / FADE_IN)
			calm_for = 0.0 if engaged else calm_for + dt
			if calm_for > HOLD_AFTER or not enabled:
				state = LEAVING
				say("the fight is over (tick %d): back to the game's music over %.1f s" % [hud.frame.get("tick", 0) if hud.ok else 0, FADE_OUT])
		LEAVING:
			level = move_toward(level, 0.0, dt / FADE_OUT)
			if engaged and enabled:
				state = PLAYING         # it was not over
				calm_for = 0.0
			elif level <= 0.0:
				player.stop()
				player.stream = null
				state = IDLE
				say("the game's music has the stage again")
	_apply()


# On the loader's thread: the whole track mixed once (AudioStreamPlayback.mix_audio, nothing is heard), its RMS and
# peak, and the gain that brings it to TARGET_RMS_DB without its peak passing PEAK_CEILING: (gain dB, RMS dB, peak dB).
static func _loudness_db(stream: AudioStream) -> Vector3:
	var playback := stream.instantiate_playback()
	var seconds := minf(stream.get_length(), 20.0 * 60.0)
	if playback == null or seconds <= 0.0 or not playback.has_method("mix_audio"):
		return Vector3(0.0, -200.0, -200.0)
	playback.start(0.0)
	var left := int(seconds * AudioServer.get_mix_rate())
	var sum := 0.0
	var peak := 0.0
	var n := 0
	while left > 0:
		var block: PackedVector2Array = playback.mix_audio(1.0, mini(left, 8192))
		if block.is_empty():
			break
		for v in block:
			sum += v.x * v.x + v.y * v.y
			peak = maxf(peak, maxf(absf(v.x), absf(v.y)))
		n += block.size() * 2
		left -= block.size()
	playback.stop()
	if n == 0 or sum <= 0.0:
		return Vector3(0.0, -200.0, -200.0)
	var rms := sqrt(sum / n)
	var gain := minf(db_to_linear(TARGET_RMS_DB) / rms, PEAK_CEILING / maxf(peak, 1e-6))
	return Vector3(linear_to_db(gain), linear_to_db(rms), linear_to_db(peak))


func _loaded(path: String, stream: AudioStream, loudness := Vector3.ZERO) -> void:
	if loader != null and loader.is_started():
		loader.wait_to_finish()
	if state != LOADING or path != loading_path:
		return
	if stream == null:
		say("cannot play %s (not ogg, mp3 or wav that Godot reads): left out" % path.get_file())
		tracks.remove_at(tracks.find(path))
		state = IDLE
		return
	player.stream = stream
	player.volume_db = -80.0
	trim_db = loudness.x
	player.play()
	level = 0.0
	calm_for = 0.0
	state = PLAYING
	say("playing %s (%.1f s, looped; RMS %.1f dBFS, peak %+.1f dBFS as decoded, played %+.1f dB)" % [path.get_file(), stream.get_length(),
		loudness.y, loudness.z, trim_db])


func _apply() -> void:
	var eased: float = level * level * (3.0 - 2.0 * level)
	var volume: float = clampf(float(hud.setting.get("music_volume", 0.8)), 0.0, 1.0)
	if player.playing:
		player.volume_db = linear_to_db(maxf(0.0001, eased * volume)) + trim_db
	# the game's own music down by the same curve
	var machine: Object = hud.machine
	if machine == null:
		return
	if has_music_volume != 0 and machine.has_method("set_option"):
		var want: float = 1.0 - eased
		if absf(want - (1.0 - duck_applied)) > 0.004 or has_music_volume < 0:
			var took: bool = machine.call("set_option", "music_volume", "%.3f" % want)
			if has_music_volume < 0:
				has_music_volume = 1 if took else 0
				say("the library %s" % ("turns its music down by itself (music_volume)" if took else "has no music_volume option yet: the whole game mix is ducked by %.0f dB instead" % DUCK_DB))
			duck_applied = eased
		if has_music_volume == 1:
			return
	elif has_music_volume < 0:
		has_music_volume = 0
		say("the host has no set_option: the whole game mix is ducked by %.0f dB instead" % DUCK_DB)
	# no separate control: the whole mix of the game goes down by a fixed amount while the player's track is up
	var game_player: AudioStreamPlayer = hud.host.get("player") if hud.host != null else null
	if game_player == null:
		return
	if not game_base_known:
		game_base_db = game_player.volume_db
		game_base_known = true
	if absf(eased - duck_applied) > 0.004 or (eased == 0.0 and duck_applied != 0.0):
		duck_applied = eased
		game_player.volume_db = game_base_db + DUCK_DB * eased


# Test aid ("app hud music tap"): the game's own sound goes through a bus of its own (which still ends in the master
# bus - muted in a test, so nothing is heard) at full level, and its level is measured between two "music say" lines.
func tap() -> void:
	var game_player: AudioStreamPlayer = hud.host.get("player") if hud.host != null else null
	if game_player == null or tap_bus >= 0:
		return
	AudioServer.add_bus()
	tap_bus = AudioServer.bus_count - 1
	AudioServer.set_bus_name(tap_bus, "HudGameTap")
	AudioServer.set_bus_send(tap_bus, "Master")
	game_player.bus = "HudGameTap"
	game_player.volume_db = 0.0
	game_base_known = false


func _process(_delta: float) -> void:
	if tap_bus >= 0:
		var peak: float = maxf(AudioServer.get_bus_peak_volume_left_db(tap_bus, 0), AudioServer.get_bus_peak_volume_right_db(tap_bus, 0))
		tap_peak = maxf(tap_peak, peak)
		tap_sum += db_to_linear(peak)
		tap_n += 1


# for the report of a test run
func figures() -> String:
	var bus := AudioServer.get_bus_index(BUS)
	var text := "state %s, level %.2f, track %s, own bus peak %.1f dB, game music %s" % [["idle", "loading", "playing", "leaving"][state], level,
		last_track.get_file() if last_track != "" else "-", AudioServer.get_bus_peak_volume_left_db(bus, 0) if bus >= 0 else -200.0,
		("music_volume %.2f" % (1.0 - duck_applied)) if has_music_volume == 1 else ("whole mix %+.1f dB" % (DUCK_DB * duck_applied))]
	if tap_bus >= 0:
		text += "; the game's own sound since the last line: peak %.1f dB, mean level %.1f dB over %d pictures" % [tap_peak, linear_to_db(maxf(1e-9, tap_sum / maxf(1.0, tap_n))), tap_n]
		tap_peak = -200.0
		tap_sum = 0.0
		tap_n = 0
	return text
