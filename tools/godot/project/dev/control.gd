extends Node
# dev/control.gd - a control port for test runs of the Godot scene (main.gd --control PORT): the counterpart of the
# native program's control socket (tools/recomp/app/control.h), so that a driver that looks at the game while it runs
# (tools/recomp/app/playtest.py) can play the Godot copy as it plays the native one.  127.0.0.1 only; a test aid, never
# part of what a player uses.  One command a line, one line of answer starting with "ok" (or "err ..."):
#
#   pad BUTTONS|none [lx ly rx ry]   hold this controller state on port 1 from now on (buttons joined by +)
#   release                          give port 1 back to the keyboard and controller
#   peek ADDRESS LENGTH              -> "ok HEX": that many bytes of the game's memory (ADDRESS decimal or 0x..)
#   poke ADDRESS HEX                 write bytes into the game's memory (a tester's write; teleports are announced by the driver)
#   info                             -> "ok blanks=N level=NAME process_usec=N"
#   shot FILE.png                    the Godot window's own picture after this frame ("app windowshot")
#   app TEXT                         an "app ..." script line for the host (main.gd _host_command)
#   sceneopt NAME VALUE              a scene option of the drawer (rta_scene.cpp set_scene_option; a test aid)
#   quit                             end the program as a script's quit does
#
# Commands are carried out in _process, before the controller is read for the frame let go in it.

const G_LEVEL_NAME := 0x41B721          # g_levelName (tools/recomp/app/tour.py)

var main: Node
var server := TCPServer.new()
var peers: Array = []                   # [StreamPeerTCP, buffer]: several drivers at once (a player and a look at the state)
var held := false
var buttons := 0
var sticks := [128, 128, 128, 128]


func start(port: int) -> bool:
	var err := server.listen(port, "127.0.0.1")
	print("rta_godot: control port %d on 127.0.0.1: %s" % [port, "listening" if err == OK else "error %d" % err])
	return err == OK


var last_draws := -1
var last_frame := -1


func poll() -> void:
	_watch_frames()
	while server.is_connection_available():
		peers.append([server.take_connection(), ""])
	for entry in peers.duplicate():
		var peer: StreamPeerTCP = entry[0]
		peer.poll()
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			peers.erase(entry)
			continue
		var n := peer.get_available_bytes()
		if n > 0:
			var got: Array = peer.get_data(n)
			if got[0] == OK:
				entry[1] += (got[1] as PackedByteArray).get_string_from_utf8()
		while String(entry[1]).find("\n") >= 0:
			var text: String = entry[1]
			var at := text.find("\n")
			var line := text.substr(0, at).strip_edges()
			entry[1] = text.substr(at + 1)
			if line != "":
				peer.put_data((_run(line) + "\n").to_utf8_buffer())


func _watch_frames() -> void:
	# a frame of the game whose list draws next to nothing while the one before drew a scene (a black or empty picture
	# shown for a frame - a flicker a player sees): marked in the frame log and printed, with the level
	var machine: Object = main.get("machine")
	if machine == null:
		return
	var frame := int(machine.call("get_frame_number"))
	if frame == last_frame:
		return
	last_frame = frame
	var draws := int(machine.call("get_draw_count"))
	if last_draws >= 40 and draws <= 2:
		var level: String = machine.call("peek_string", G_LEVEL_NAME, 16)
		print("rta_godot: control: frame %d of %s drew %d (the one before %d)" % [frame, level, draws, last_draws])
		main.call("frame_mark", "control few-draws %d %s" % [draws, level])
	last_draws = draws


func _number(text: String) -> int:
	return text.hex_to_int() if text.begins_with("0x") else text.to_int()


func _run(line: String) -> String:
	var w := line.split(" ", false)
	var machine: Object = main.get("machine")
	if w[0] == "shot" or (w[0] == "peek" and w.size() >= 3 and _number(w[2]) > 4096):
		# a picture read back or a large block copied costs this frame time: marked in the frame log, so that a measure
		# of the game's pacing can leave those frames out (playtest.py frames)
		main.call("frame_mark", "control " + w[0])
	match w[0]:
		"pad":
			buttons = 0
			if w.size() >= 2 and w[1] != "none":
				for name in w[1].split("+"):
					buttons |= int(main.BUTTON_NAMES.get(name, 0))
			sticks = [128, 128, 128, 128]
			for k in range(4):
				if w.size() > 2 + k:
					sticks[k] = clampi(w[2 + k].to_int(), 0, 255)
			held = true
			return "ok"
		"release":
			held = false
			return "ok"
		"peek":
			if w.size() < 3:
				return "err peek ADDRESS LENGTH"
			var bytes: PackedByteArray = machine.call("peek_bytes", _number(w[1]), _number(w[2]))
			return "ok " + bytes.hex_encode()
		"poke":
			if w.size() < 3:
				return "err poke ADDRESS HEX"
			var ok: bool = machine.call("poke_bytes", _number(w[1]), w[2].hex_decode())
			return "ok" if ok else "err poke refused"
		"info":
			return "ok blanks=%d level=%s process_usec=%d" % [int(main.get("blanks")), machine.call("peek_string", G_LEVEL_NAME, 16),
				int(main.get("process_usec"))]
		"shot":
			if w.size() < 2:
				return "err shot FILE"
			main.call("_host_command", "windowshot " + line.substr(line.find(w[1])))
			return "ok"
		"app":
			main.call("_host_command", line.substr(4))
			return "ok"
		"sceneopt":
			# a scene option of the drawer (rta_scene.cpp set_scene_option: keep, batch, prepass, packets, near_fade ...)
			var drawer: Object = main.get("drawer")
			if drawer == null or w.size() < 3:
				return "err sceneopt NAME VALUE (scene mode)"
			drawer.call("set_scene_option", w[1], w[2].to_float())
			return "ok"
		"quit":
			main.call("_finish", 0)
			return "ok"
	return "err unknown command " + w[0]
