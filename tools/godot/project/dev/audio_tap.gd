extends Node
# audio_tap.gd - test aid (main.gd --audio-tap FILE.wav): what Godot's master bus mixes - the game's sound and the
# player's own boss music together, after Godot's resampling and the buses' volumes - written to a WAV file (32-bit
# float, at the mix rate), from an AudioEffectCapture at the head of the master bus.  The capture sits before the bus's
# own volume and mute, so a test run (--mute, --test: the master bus muted) records everything and nobody hears it.
# docs/issues/audio-quality.md.
#
# Beside the WAV:
#   FILE-clock.tsv   once a second: wall time, seconds captured, seconds of the game's sound the mixer asked for
#                    (RtaAudioStream), the capture's discarded frames.  Captured or asked-for time that falls behind
#                    the wall clock is time the device was handed nothing from Godot's mixer.
#   FILE-marks.tsv   "app audio mark NAME" lines of a script: the wall time and the position in the WAV (seconds)
# Script lines for the host ("app audio ..."):
#   app audio mark NAME          a named place in the recording
#   app audio engage on|off|auto the HUD's boss music director engaged by hand, never, or by the game's state
#                                (to record the player's own boss music without finding a boss first)

var main: Node
var path := ""
var file: FileAccess
var clock_log: FileAccess
var marks: FileAccess
var fx: AudioEffectCapture
var frames := 0
var rate := 48000
var t0 := 0
var last_second := -1


func start(wav_path: String) -> void:
	path = wav_path
	rate = int(AudioServer.get_mix_rate())
	fx = AudioEffectCapture.new()
	fx.buffer_length = 10.0
	AudioServer.add_bus_effect(0, fx, 0)
	file = FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_warning("audio tap: cannot write " + path)
		return
	_header()
	clock_log = FileAccess.open(path.get_basename() + "-clock.tsv", FileAccess.WRITE)
	clock_log.store_line("wall_s\tcaptured_s\tgame_asked_s\tgame_requests\tdiscarded_frames\tmix_rate\toutput_latency_ms")
	marks = FileAccess.open(path.get_basename() + "-marks.tsv", FileAccess.WRITE)
	marks.store_line("wall_s\twav_s\tname")
	t0 = Time.get_ticks_usec()
	print("audio tap: the master bus at %d Hz into %s (output latency %.1f ms)" % [rate, path, AudioServer.get_output_latency() * 1000.0])


func _header() -> void:
	var data := frames * 8
	var h := PackedByteArray()
	h.resize(44)
	h.encode_u32(0, 0x46464952)        # RIFF
	h.encode_u32(4, data + 36)
	h.encode_u32(8, 0x45564157)        # WAVE
	h.encode_u32(12, 0x20746d66)       # "fmt "
	h.encode_u32(16, 16)
	h.encode_u16(20, 3)                # IEEE float
	h.encode_u16(22, 2)
	h.encode_u32(24, rate)
	h.encode_u32(28, rate * 8)
	h.encode_u16(32, 8)
	h.encode_u16(34, 32)
	h.encode_u32(36, 0x61746164)       # data
	h.encode_u32(40, data)
	var at := file.get_position()
	file.seek(0)
	file.store_buffer(h)
	if frames > 0:
		file.seek(at)


func drain() -> void:
	if file == null or fx == null:
		return
	var n := fx.get_frames_available()
	if n > 0:
		file.store_buffer(fx.get_buffer(n).to_byte_array())
		frames += n


func _process(_delta: float) -> void:
	if file == null:
		return
	drain()
	var wall := (Time.get_ticks_usec() - t0) / 1000000.0
	if int(wall) != last_second:
		last_second = int(wall)
		var asked := 0.0
		var requests := 0
		if ClassDB.class_exists("RtaAudioStream"):
			asked = RtaAudioStream.get_frames_mixed() / 48000.0
			requests = RtaAudioStream.get_requests()
		clock_log.store_line("%.3f\t%.3f\t%.3f\t%d\t%d\t%d\t%.1f" % [wall, float(frames) / rate, asked, requests, fx.get_discarded_frames(),
			rate, AudioServer.get_output_latency() * 1000.0])
		if last_second % 5 == 0:
			_header()
			file.flush()


func command(w: PackedStringArray) -> void:
	if w.size() >= 3 and w[1] == "mark" and marks != null:
		drain()
		marks.store_line("%.3f\t%.4f\t%s" % [(Time.get_ticks_usec() - t0) / 1000000.0, float(frames) / rate, " ".join(w.slice(2))])
		marks.flush()
	elif w.size() >= 3 and w[1] == "engage":
		var hud: Node = main.get("hud_node") if main != null else null
		var music: Node = hud.get("music") if hud != null else null
		if music != null:
			music.set("forced", 1 if w[2] == "on" else 0 if w[2] == "off" else -1)
			print("audio tap: boss music director engaged %s" % w[2])


func finish() -> void:
	if file == null:
		return
	drain()
	_header()
	file.close()
	file = null
	var wall := (Time.get_ticks_usec() - t0) / 1000000.0
	print("audio tap: %.2f s captured in %.2f s of wall time, %d frames discarded by the capture" % [float(frames) / rate, wall,
		fx.get_discarded_frames()])
	if clock_log != null:
		clock_log.close()
	if marks != null:
		marks.close()
