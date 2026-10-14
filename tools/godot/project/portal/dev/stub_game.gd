extends Node
# stub_game.gd - a stand-in for the game scene, for the portal's own pictures and tests
# (--portal-stub-game): something colourful that moves, so that the hand-over, the notices
# over a running game and the blurred picture behind the portal can be seen without the
# game.  Nothing of the game is in it.

var canvas: Control
var machine: Object = null
var started := true
var player: Object = null
var opt := {}


var game_seconds := 0.0             # a session's game: "over" after this long (0: never)
var clock := 0.0
var told_running := false


func _ready() -> void:
	canvas = Picture.new()
	canvas.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(canvas)
	var args := OS.get_cmdline_user_args()
	var at := args.find("--stub-game-seconds")
	if at >= 0 and at + 1 < args.size():
		game_seconds = args[at + 1].to_float()


func _process(delta: float) -> void:
	# standing in for tools/recomp/net2/launch.cpp: tell the room the game runs, and later that it is over
	var portal := get_tree().get_first_node_in_group("portal")
	if portal == null or not portal.session.available() or String(portal.handover.intent.get("kind", "")) != "session" or not portal.handover.running:
		clock = 0.0
		told_running = false
		return
	clock += delta
	if not told_running and clock > 2.5:
		told_running = true
		portal.session.game_state("stand-in", true)
	if game_seconds > 0.0 and clock > game_seconds:
		clock = 0.0
		told_running = false
		portal.session.game_state("", false)


func _finish(_code: int) -> void:
	get_tree().quit(0)


class Picture extends Control:
	var t := 0.0

	func _process(delta: float) -> void:
		t += delta
		queue_redraw()

	func _draw() -> void:
		var z := size
		draw_rect(Rect2(Vector2.ZERO, z), Color(0.10, 0.16, 0.12))
		draw_polygon(PackedVector2Array([Vector2(0, 0), Vector2(z.x, 0), Vector2(z.x, z.y * 0.45), Vector2(0, z.y * 0.45)]),
			PackedColorArray([Color(0.30, 0.42, 0.62), Color(0.42, 0.52, 0.70), Color(0.78, 0.66, 0.50), Color(0.70, 0.60, 0.50)]))
		for k in 9:
			var x := z.x * (0.06 + 0.11 * k)
			var h := z.y * (0.18 + 0.08 * sin(k * 2.3))
			draw_colored_polygon(PackedVector2Array([Vector2(x - z.x * 0.05, z.y * 0.45), Vector2(x, z.y * 0.45 - h), Vector2(x + z.x * 0.05, z.y * 0.45)]), Color(0.12, 0.26, 0.18))
		for k in 5:
			var c := Vector2(z.x * (0.2 + 0.15 * k) + sin(t * 0.8 + k) * z.x * 0.03, z.y * (0.62 + 0.05 * cos(t * 0.6 + k * 1.7)))
			draw_circle(c, z.y * 0.035, Color.from_hsv(0.08 + 0.17 * k, 0.6, 0.9), true, -1.0, true)
			draw_rect(Rect2(c.x - z.y * 0.03, c.y - z.y * 0.065, z.y * 0.06 * (0.4 + 0.12 * k), z.y * 0.008), Color(0.9, 0.25, 0.2))
		var font := ThemeDB.fallback_font
		draw_string(font, Vector2(z.x * 0.03, z.y * 0.95), "The game runs here - this picture is a stand-in drawn for the portal's tests", HORIZONTAL_ALIGNMENT_LEFT, -1, int(z.y * 0.022), Color(1, 1, 1, 0.7))
