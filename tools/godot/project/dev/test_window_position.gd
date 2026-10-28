extends SceneTree
# Authored host geometry only; no game library, disc or desktop input needed.
var checks := 0
var failures := 0


func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		printerr("test_window_position: FAIL ", label)


func _initialize() -> void:
	var host: Node = load("res://main.gd").new()
	var area := Rect2i(100, 50, 2560, 1440)
	var size := Vector2i(640, 480)
	var fallback := Vector2i(1996, 986)
	for text in ["", "40", "40,40,40", "x,40", "40,", "1.5,2", "2147483648,0", "0,-2147483649"]:
		check(host._test_window_position(text, area, size) == fallback, "invalid request uses default: " + text)
	for pair in [["40,40", Vector2i(40, 40)], ["700,40", Vector2i(700, 40)],
		["-640,20", Vector2i(-640, 20)], ["0,0", Vector2i.ZERO], [" +12, -34 ", Vector2i(12, -34)]]:
		check(host._test_window_position(pair[0], area, size) == pair[1], "explicit request: " + pair[0])
	host._parse_arguments()
	check(host.opt.test_position == "-20,70", "test-position survives the engine argument boundary")
	host.free()
	print("test_window_position: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)
