extends Control
# top.gd - the upper part of the picture: the large bar of the boss and of the enemy the
# player's attack is aimed at, the game's own one-line message, the name of a level on
# entry, the level-up banner, and what the network has to say (stalls, a desync, chat).
# (The radar and the compass strip are compass.gd: they turn with the camera and are drawn
# every frame; this piece is drawn again only when something it shows changes.)

const Style := preload("res://hud/style.gd")
const Hud := preload("res://hud/hud.gd")

const FOCUS_LINGER := 3.5

var hud: Node
var focus_uid := 0                      # the enemy shown in the target frame
var focus_until := 0.0
var focus_name := ""
var focus := {"hp": 0.0, "max": 1.0, "shown": 1.0, "ghost": 1.0, "hit_at": -10.0, "alpha": 0.0, "mini": false}
var boss := {"uid": 0, "name": "", "hp": 0.0, "max": 1.0, "shown": 1.0, "ghost": 1.0, "hit_at": -10.0, "alpha": 0.0}
var message := ""
var message_alpha := 0.0
var level_seen := ""
var level_at := -100.0
var level_title := ""
var levelup_at := -100.0
var levelup_level := 0
var chat: Array = []
var test_notice := 0
var test_chat: Array = []
var last_signature := ""


func test(w: Array) -> void:
	# pictures of states a run without a network cannot reach; what they show is marked as test data
	if w.size() >= 2 and str(w[0]) == "notice":
		test_notice = str(w[1]).to_int()
	elif w.size() >= 2 and str(w[0]) == "chat":
		test_chat.append([1, "TEST DATA 2: " + " ".join(PackedStringArray(w.slice(1)))])


func tick() -> void:
	var c: PackedFloat32Array = hud.creatures
	var n := c.size() / Hud.C_STRIDE
	var now: float = hud.now
	# which enemy the target frame is about: the one the local player's attack is aimed at, kept a while after
	var target_uid: int = hud.me.get("target_uid", 0)
	var boss_index := -1
	var focus_index := -1
	var boss_best := 1e30
	for k in range(n):
		var o := k * Hud.C_STRIDE
		var flags := int(c[o + Hud.C_FLAGS])
		var uid := int(c[o + Hud.C_UID])
		if (flags & Hud.CF_BOSS) != 0 and (flags & (Hud.CF_DEAD | Hud.CF_INERT)) == 0 and (flags & Hud.CF_HOSTILE) != 0:
			var metered := uid == int(hud.frame.get("boss_uid", 0))
			var d: float = c[o + Hud.C_SZ] if not metered else -1.0
			# a boss the game's own meter is not (yet) about gets the bar only once it is in the fight: before that
			# (a level's fade-in) its name is the kind's and would change to the meter's own when the meter comes on
			var engaged: bool = metered or uid == boss.uid or (flags & (Hud.CF_AGGRO | Hud.CF_TARGETED | Hud.CF_ATTACKING)) != 0
			if engaged and d < boss_best:
				boss_best = d
				boss_index = k
		if uid == target_uid and target_uid != 0 and (flags & Hud.CF_HOSTILE) != 0:
			focus_uid = uid
			focus_until = now + FOCUS_LINGER
		if uid == focus_uid:
			focus_index = k
	if boss_index >= 0:
		var o := boss_index * Hud.C_STRIDE
		var uid := int(c[o + Hud.C_UID])
		if boss.uid != uid:
			boss.uid = uid
			boss.shown = clampf(c[o + Hud.C_HP] / maxf(c[o + Hud.C_MAX], 0.001), 0.0, 1.0)
			boss.ghost = boss.shown
		# the name is taken when the bar first shows a creature and again while the game's meter is about it, never
		# back from the meter's name to the kind's
		if uid == int(hud.frame.get("boss_uid", 0)) or boss.get("named_uid", 0) != uid:
			boss.name = Style.pretty(hud.creature_name(boss_index))
			boss["named_uid"] = uid
		boss.hp = c[o + Hud.C_HP]
		boss.max = c[o + Hud.C_MAX]
		_ease(boss, 1.0)
	else:
		_ease(boss, 0.0)
	if focus_index >= 0 and now < focus_until and focus_uid != boss.uid:
		var o := focus_index * Hud.C_STRIDE
		var flags := int(c[o + Hud.C_FLAGS])
		focus.hp = c[o + Hud.C_HP]
		focus.max = c[o + Hud.C_MAX]
		focus.mini = (flags & Hud.CF_MINIBOSS) != 0
		focus_name = Style.pretty(hud.creature_name(focus_index))
		if focus.alpha <= 0.0:
			focus.shown = clampf(focus.hp / maxf(focus.max, 0.001), 0.0, 1.0)
			focus.ghost = focus.shown
		if (flags & Hud.CF_DEAD) != 0:
			focus_until = minf(focus_until, now + 0.6)
		_ease(focus, 1.0)
	else:
		if focus_index < 0:
			focus.hp = 0.0 if focus.alpha > 0.0 and now < focus_until else focus.hp
		_ease(focus, 0.0)
		if focus.alpha <= 0.0:
			focus_uid = 0
	# the game's own message
	var text: String = hud.frame.get("message", "") if (hud.ok and hud.own_text) else ""
	if text != "":
		message = text
		message_alpha = move_toward(message_alpha, 1.0, hud.dt / 0.15)
	else:
		message_alpha = move_toward(message_alpha, 0.0, hud.dt / 0.4)
	# a level's name when it is entered
	if hud.ok and (hud.phase & Hud.PH_LEVEL) != 0:
		var level: String = hud.frame.get("level", "")
		if level != level_seen and hud.show > 0.5:
			level_seen = level
			level_title = hud.frame.get("level_title", "")
			level_at = now
	for e in hud.events:
		if e.kind == 7 and not hud.me.is_empty() and int(e.slot) == int(hud.me.get("slot", -1)):
			levelup_at = now
			levelup_level = int(e.amount)
	chat = hud.frame.get("chat", []) if hud.ok else []
	if not test_chat.is_empty():
		chat = chat + test_chat
	# drawn again only when what it shows changed, or while something of it moves
	var notice: int = maxi(test_notice, int(hud.frame.get("net_notice", 0)) if hud.ok else 0)
	var sig := "%d|%d|%s|%.3f|%.3f|%.2f|%d|%.3f|%.3f|%.2f|%d|%s|%.2f|%s|%d|%d" % [hud.layout, int(hud.s * 100.0), str(hud.area), boss.shown, boss.ghost, boss.alpha, int(boss.hp),
		focus.shown, focus.ghost, focus.alpha, int(focus.hp), focus_name, message_alpha, message, chat.size(), notice]
	if sig != last_signature or notice > 0 or now - level_at < 4.6 or now - levelup_at < 3.3:
		last_signature = sig
		queue_redraw()


func _ease(b: Dictionary, target_alpha: float) -> void:
	var frac: float = clampf(b.hp / maxf(b.max, 0.001), 0.0, 1.0)
	if frac < b.shown - 0.0005:
		b.hit_at = hud.now
	b.shown = move_toward(b.shown, frac, maxf(absf(b.shown - frac) * 12.0, 0.2) * hud.dt)
	if hud.now - b.hit_at > 0.4:
		b.ghost = move_toward(b.ghost, b.shown, 0.8 * hud.dt)
	b.ghost = maxf(b.ghost, b.shown)
	b.alpha = move_toward(b.alpha, target_alpha, hud.dt / (0.18 if target_alpha > 0.0 else 0.5))


func _draw() -> void:
	var t0: int = hud.draw_begin()
	var s: float = hud.s
	var area: Rect2 = hud.area
	var cx: float = area.get_center().x
	var y: float = area.position.y
	if hud.layout != Hud.LAYOUT_OVERHEAD and not hud.me.is_empty():
		y += 44.0 * s                   # under the compass strip (compass.gd)
	# boss
	if boss.alpha > 0.01:
		var w: float = minf(600.0 * s, area.size.x * 0.56)
		var a: float = boss.alpha
		Style.text(self, Vector2(cx, y + 20.0 * s), boss.name, 22.0 * s, Color(Style.TEXT, a), 1, true)
		var rect := Rect2(Vector2(cx - w * 0.5, y + 30.0 * s).round(), Vector2(w, 18.0 * s).round())
		Style.bar(self, rect, boss.shown, boss.ghost, Style.BOSS_A, Style.BOSS_B, s, a)
		for side in [-1.0, 1.0]:
			var d := Vector2(cx + side * (w * 0.5 + 14.0 * s), rect.get_center().y)
			Style.glyph(self, 11, d, 9.0 * s, Color(Style.BOSS_B, a))
		Style.text(self, Vector2(cx, rect.position.y + 14.0 * s), "%s / %s" % [Style.number(boss.hp), Style.number(boss.max)], 13.0 * s, Color(Style.TEXT, a), 1, true)
		y += 62.0 * s
	# the targeted enemy
	if focus.alpha > 0.01:
		var w: float = minf(420.0 * s, area.size.x * 0.42)
		var a: float = focus.alpha
		Style.text(self, Vector2(cx, y + 18.0 * s), focus_name, 18.0 * s, Color(Style.TEXT, a), 1, true)
		var rect := Rect2(Vector2(cx - w * 0.5, y + 26.0 * s).round(), Vector2(w, 14.0 * s).round())
		Style.bar(self, rect, focus.shown, focus.ghost, Style.BOSS_A if focus.mini else Style.ENEMY_A, Style.BOSS_B if focus.mini else Style.ENEMY_B, s, a)
		Style.text(self, Vector2(cx, rect.position.y + 11.5 * s), "%s / %s" % [Style.number(focus.hp), Style.number(focus.max)], 12.0 * s, Color(Style.TEXT, a), 1, true)
		y += 52.0 * s
	# the game's own message
	if message_alpha > 0.01:
		var size: float = 19.0 * s
		var w: float = Style.text_width(message, size, true) + 36.0 * s
		var rect := Rect2(Vector2(cx - w * 0.5, y + 14.0 * s).round(), Vector2(w, 36.0 * s).round())
		Style.panel(self, rect, s, message_alpha, 18.0)
		Style.text(self, Vector2(cx, rect.position.y + 24.5 * s), message, size, Color(Style.TEXT, message_alpha), 1, true)
		y += 56.0 * s
	# entering a level: its name for a few seconds
	var age: float = hud.now - level_at
	if age < 4.5 and level_title != "":
		var a: float = clampf(age / 0.4, 0.0, 1.0) * clampf((4.5 - age) / 0.8, 0.0, 1.0)
		var at := Vector2(cx, area.position.y + area.size.y * 0.22)
		Style.text(self, at, level_title, 40.0 * s, Color(Style.TEXT, a), 1, true)
		var half: float = Style.text_width(level_title, 40.0 * s, true) * 0.5 * Style.ease_out(age / 0.8)
		draw_line(at + Vector2(-half, 14.0 * s), at + Vector2(half, 14.0 * s), Color(Style.XP_B, 0.8 * a), maxf(1.0, 2.0 * s), true)
	# level up
	age = hud.now - levelup_at
	if age < 3.2:
		var a: float = clampf(age / 0.2, 0.0, 1.0) * clampf((3.2 - age) / 0.7, 0.0, 1.0)
		var pop: float = 1.0 + 0.25 * maxf(0.0, 1.0 - age / 0.25)
		var at := Vector2(cx, area.position.y + area.size.y * 0.30)
		Style.text(self, at, "LEVEL %d" % levelup_level, 46.0 * s * pop, Color(Style.XP_B, a), 1, true)
		Style.text(self, at + Vector2(0, 30.0 * s), "Level up", 18.0 * s, Color(Style.TEXT, a), 1, true)
	_network(s)
	hud.draw_end(t0)


# Notices are drawn by their own item (the Notice piece shares this script's helper): they must show whatever the
# playing HUD does - over a menu as well.
static func draw_notice(ci: CanvasItem, hud: Node) -> void:
	if hud.notices.is_empty():
		return
	var s: float = hud.s
	var n: Dictionary = hud.notices[hud.notices.size() - 1]
	var wall := Time.get_ticks_msec() / 1000.0
	var age: float = wall - float(n.born)
	var life: float = float(n.seconds)
	var a: float = clampf(age / 0.2, 0.0, 1.0) * clampf((life + 0.5 - age) / 0.5, 0.0, 1.0)
	var w: float = 350.0 * s
	var h: float = 86.0 * s
	var area: Rect2 = hud.area
	var top: float = area.position.y + (166.0 * s if (hud.layout == Hud.LAYOUT_OVERHEAD and hud.setting.radar and hud.show > 0.0) else 0.0)
	var o := Vector2(area.end.x - w + (1.0 - Style.ease_out(age / 0.3)) * 40.0 * s, top).round()
	Style.panel(ci, Rect2(o, Vector2(w, h)), s, a, 8.0)
	ci.draw_rect(Rect2(o + Vector2(0, 8.0 * s), Vector2(3.0 * s, h - 16.0 * s)), Color(Style.PARTY, a))
	# who: a disc with the first letter
	var c := o + Vector2(32.0, 30.0) * s
	ci.draw_circle(c, 17.0 * s, Color(Style.PARTY.darkened(0.45), a))
	Style.text(ci, c + Vector2(0, 7.0 * s), str(n.get("who", "?")).substr(0, 1).to_upper(), 20.0 * s, Color(Style.TEXT, a), 1, true)
	var x: float = o.x + 60.0 * s
	var title: String = str(n.get("title", ""))
	while title.length() > 8 and Style.text_width(title, 15.0 * s, true) > w - 72.0 * s:
		title = title.substr(0, title.length() - 2)
	Style.text(ci, Vector2(x, o.y + 25.0 * s), title, 15.0 * s, Color(Style.TEXT, a), 0, true)
	Style.text(ci, Vector2(x, o.y + 44.0 * s), str(n.get("text", "")), 13.0 * s, Color(Style.TEXT_DIM, a))
	# how to answer: the key, or both sticks of the controller pressed together and held
	var y: float = o.y + 68.0 * s
	var pad := Input.get_connected_joypads().size() > 0
	var accept: String = str(n.get("accept_text", "Accept"))
	if pad:
		var hold: float = clampf(hud.notice_hold / 0.5, 0.0, 1.0)
		for k in range(2):
			var sc := Vector2(x + 9.0 * s + 22.0 * s * k, y - 4.0 * s)
			ci.draw_circle(sc, 8.5 * s, Color(0.10, 0.10, 0.13, 0.95 * a))
			ci.draw_arc(sc, 8.5 * s, 0, TAU, 20, Color(1, 1, 1, 0.4 * a), 1.0, true)
			ci.draw_circle(sc, 3.5 * s, Color(Style.TEXT, a))
			if hold > 0.0:
				ci.draw_arc(sc, 8.5 * s, -PI * 0.5, -PI * 0.5 + TAU * hold, 20, Color(Style.XP_B, a), 2.0 * s, true)
		Style.text(ci, Vector2(x + 48.0 * s, y), "hold both sticks: " + accept, 12.0 * s, Color(Style.TEXT, a))
	else:
		var cw: float = Style.keycap(ci, Vector2(x, y - 4.0 * s), "F2", 11.0 * s, a)
		Style.text(ci, Vector2(x + cw + 8.0 * s, y), accept, 12.0 * s, Color(Style.TEXT, a))
	# the time it has left
	var left: float = clampf(1.0 - age / life, 0.0, 1.0)
	ci.draw_rect(Rect2(o + Vector2(8.0 * s, h - 4.0 * s), Vector2((w - 16.0 * s) * left, maxf(1.0, 2.0 * s))), Color(Style.PARTY, 0.8 * a))


func _network(s: float) -> void:
	var area: Rect2 = hud.area
	var notice: int = hud.frame.get("net_notice", 0) if hud.ok else 0
	var made_up := false
	if test_notice > 0:
		notice = test_notice
		made_up = true
	if notice > 0:
		var who := ""
		var slot: int = hud.frame.get("net_notice_slot", -1)
		if slot >= 0 and slot < hud.players.size() and hud.players[slot].get("present", false):
			who = hud.players[slot].name
		var text := ""
		var colour := Style.WARN
		match notice:
			1: text = "Waiting for the other players"
			2:
				text = ("%s is out of sync" % who) if who != "" else "A player is out of sync"
				colour = Style.DANGER
			3:
				text = "The characters no longer match (checksum)"
				colour = Style.DANGER
			4: text = "Leaving the game"
			5:
				text = "Connection lost"
				colour = Style.DANGER
		if made_up:
			text += "   (TEST DATA)"
		var size: float = 17.0 * s
		var w: float = Style.text_width(text, size, true) + 52.0 * s
		var rect := Rect2(Vector2(area.get_center().x - w * 0.5, area.position.y + area.size.y * 0.16).round(), Vector2(w, 34.0 * s).round())
		Style.rounded(self, rect, 17.0 * s, Color(0.05, 0.05, 0.07, 0.86), Color(colour, 0.9), maxi(1, int(round(1.5 * s))))
		var pulse: float = 0.6 + 0.4 * sin(hud.now * 6.0)
		draw_circle(rect.position + Vector2(18.0, 17.0) * s, 5.0 * s, Color(colour, pulse))
		Style.text(self, rect.position + Vector2(32.0 * s, 23.0 * s), text, size, Style.TEXT, 0, true)
	# chat: the newest lines, above the player's frame on the left
	if not chat.is_empty():
		var x: float = area.position.x
		var y: float = area.end.y - (104.0 + 62.0 + 3.0 * 58.0 + 14.0) * s
		var first: int = maxi(0, chat.size() - 5)
		for k in range(chat.size() - 1, first - 1, -1):
			var line: Array = chat[k]
			var text: String = line[1]
			var w: float = Style.text_width(text, 15.0 * s) + 20.0 * s
			Style.rounded(self, Rect2(Vector2(x, y - 20.0 * s), Vector2(w, 26.0 * s)), 6.0 * s, Color(0.04, 0.05, 0.07, 0.66))
			draw_rect(Rect2(Vector2(x, y - 16.0 * s), Vector2(3.0 * s, 18.0 * s)), Style.PARTY)
			Style.text(self, Vector2(x + 10.0 * s, y - 1.0 * s), text, 15.0 * s, Style.TEXT)
			y -= 30.0 * s
