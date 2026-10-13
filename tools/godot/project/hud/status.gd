extends Control
# status.gd - the player's frame (health, mana, experience as bars with their numbers, level,
# status glyphs) and the frames of the other players in the game.
#
# Layouts: overhead and third person put the frame in the lower left corner (third person a
# little smaller, so that the character in the middle stays free); first person shows only
# two slim bars in the lower middle and the status glyphs above them.

const Style := preload("res://hud/style.gd")
const Hud := preload("res://hud/hud.gd")

var hud: Node
var shown := {}                         # slot -> {hp, ghost, hit_at, mana, mana_ghost, mana_at, xp}: the bars as drawn (eased)
var last_signature := ""
var level_flash := -10.0
var level_shown := -1
var hurt_at := -10.0


func tick() -> void:
	var moving := false
	for slot in range(hud.players.size()):
		var p: Dictionary = hud.players[slot]
		if not p.get("present", false):
			shown.erase(slot)
			continue
		var hp: float = clampf(p.health / maxf(p.health_max, 0.001), 0.0, 1.0)
		var mana: float = clampf(p.mana / maxf(p.mana_max, 0.001), 0.0, 1.0)
		var span: float = maxf(1.0, p.xp_next - p.xp_base)
		var xp: float = clampf((p.xp - p.xp_base) / span, 0.0, 1.0) if p.xp_next > p.xp_base else 0.0
		var b = shown.get(slot)
		if b == null:
			b = {"hp": hp, "ghost": hp, "hit_at": -10.0, "mana": mana, "mana_ghost": mana, "mana_at": -10.0, "xp": xp}
			shown[slot] = b
		if hp < b.hp - 0.0005:
			b.hit_at = hud.now
			if p.get("local", false):
				hurt_at = hud.now
		if mana < b.mana - 0.0005:
			b.mana_at = hud.now
		var before: float = b.hp + b.ghost + b.mana + b.mana_ghost + b.xp
		b.hp = _ease(b.hp, hp)
		b.mana = _ease(b.mana, mana)
		b.xp = _ease(b.xp, xp) if xp >= b.xp else xp        # a new level starts the bar again
		if hud.now - b.hit_at > 0.4:
			b.ghost = move_toward(b.ghost, b.hp, 0.9 * hud.dt)
		b.ghost = maxf(b.ghost, b.hp)
		if hud.now - b.mana_at > 0.4:
			b.mana_ghost = move_toward(b.mana_ghost, b.mana, 0.9 * hud.dt)
		b.mana_ghost = maxf(b.mana_ghost, b.mana)
		if absf(before - (b.hp + b.ghost + b.mana + b.mana_ghost + b.xp)) > 0.00001:
			moving = true
	for e in hud.events:
		if e.kind == 7 and hud.players[e.slot].get("local", false):
			level_flash = hud.now
	if not hud.me.is_empty():
		if level_shown >= 0 and hud.me.level > level_shown:
			level_flash = hud.now
		level_shown = hud.me.level
	# drawn again only when something that is shown changed
	var sig := "%d|%d|%.1f|%s" % [hud.layout, int(hud.s * 100.0), hud.area.size.x, str(hud.area.position)]
	for p in hud.players:
		if p.get("present", false):
			sig += "|%s%d%d%d%d%d%d%d%d" % [p.name, p.level, int(p.health), int(p.health_max), int(p.mana), int(p.mana_max), p.xp, int(p.alive), p.status.size()]
			var st: PackedFloat32Array = p.status
			for k in range(0, st.size(), 4):
				sig += "%d:%d" % [int(st[k]), int(st[k + 2] * 4.0)]
	var low: bool = not hud.me.is_empty() and hud.me.alive and hud.me.health < 0.25 * hud.me.health_max
	if moving or sig != last_signature or low or hud.now - level_flash < 3.0 or hud.now - hurt_at < 0.5 or hud.setting.fake_party > 0:
		last_signature = sig
		queue_redraw()


func _ease(from: float, to: float) -> float:
	return move_toward(from, to, maxf(absf(from - to) * 10.0, 0.15) * hud.dt)


func _draw() -> void:
	var t0: int = hud.draw_begin()
	if not hud.me.is_empty():
		if hud.layout == Hud.LAYOUT_FIRST:
			_minimal(hud.me)
		else:
			_frame(hud.me)
			_party()
	hud.draw_end(t0)


func _numbers(a: float, b: float) -> String:
	return "%s / %s" % [Style.number(ceilf(a) if a > 0.0 and a < 1.0 else a), Style.number(b)]


func _frame(p: Dictionary) -> void:
	var s: float = hud.s * (0.9 if hud.layout == Hud.LAYOUT_THIRD else 1.0)
	var b: Dictionary = shown.get(p.slot, {})
	if b.is_empty():
		return
	var w: float = 392.0 * s
	var h: float = 104.0 * s
	var o := Vector2(hud.area.position.x, hud.area.end.y - h).round()
	Style.panel(self, Rect2(o, Vector2(w, h)), s)
	# the level in a ring that fills with experience
	var c := o + Vector2(42.0, 42.0) * s
	var r: float = 27.0 * s
	draw_circle(c, r, Color(0, 0, 0, 0.55))
	draw_arc(c, r - 2.0 * s, 0, TAU, 48, Color(1, 1, 1, 0.12), 3.0 * s, true)
	if b.xp > 0.001:
		draw_arc(c, r - 2.0 * s, -PI * 0.5, -PI * 0.5 + TAU * b.xp, 48, Style.XP_B, 3.0 * s, true)
	var flash: float = clampf(1.0 - (hud.now - level_flash) / 3.0, 0.0, 1.0)
	if flash > 0.0:
		draw_arc(c, r + (2.0 + 10.0 * (1.0 - flash)) * s, 0, TAU, 48, Color(Style.XP_B, flash), 2.5 * s, true)
	var pending: bool = p.level_ack < p.level
	var level_colour := Style.TEXT
	if pending:
		level_colour = Style.XP_B.lerp(Style.TEXT, 0.5 + 0.5 * sin(hud.now * 5.0))
	var digits := str(p.level)
	Style.text(self, c + Vector2(0, (9.5 if digits.length() < 3 else 8.0) * s), digits, (27.0 if digits.length() < 3 else 21.0) * s, level_colour, 1, true)
	# name and class
	var x: float = o.x + 82.0 * s
	var right: float = o.x + w - 16.0 * s
	var name_w: float = Style.text(self, Vector2(x, o.y + 26.0 * s), p.name, 19.0 * s, Style.TEXT, 0, true)
	var klass: String = p.class_name
	if klass != "" and name_w + Style.text_width(klass, 14.0 * s) + 14.0 * s < right - x:
		Style.text(self, Vector2(right, o.y + 26.0 * s), klass, 14.0 * s, Style.TEXT_DIM, 2)
	# health
	var hr := Rect2(Vector2(x, o.y + 35.0 * s).round(), Vector2(right - x, 20.0 * s).round())
	var low: bool = p.alive and p.health < 0.25 * p.health_max
	var ha := Style.HEALTH_A
	var hb := Style.HEALTH_B
	if low:
		var pulse: float = 0.5 + 0.5 * sin(hud.now * 9.0)
		ha = Style.HEALTH_A.lerp(Style.HEALTH_LOW, pulse)
		hb = Style.HEALTH_B.lerp(Color(1, 0.7, 0.6), pulse)
	var ahead: float = (p.health + p.health_coming) / maxf(p.health_max, 0.001) if p.health_coming > 0.01 else 0.0
	Style.bar(self, hr, b.hp, b.ghost, ha, hb, s, 1.0, ahead, Style.HEAL)
	var hit: float = clampf(1.0 - (hud.now - hurt_at) / 0.3, 0.0, 1.0)
	if hit > 0.0:
		draw_rect(hr.grow(2.0 * s), Color(1, 1, 1, 0.5 * hit), false, 2.0 * s)
	if p.alive:
		Style.text(self, Vector2(hr.end.x - 7.0 * s, hr.position.y + 15.0 * s), _numbers(p.health, p.health_max), 14.0 * s, Style.TEXT, 2, true)
	else:
		Style.skull(self, hr.position + Vector2(12.0, 10.0) * s, 8.0 * s, Style.TEXT_DIM)
		Style.text(self, Vector2(hr.position.x + 26.0 * s, hr.position.y + 15.0 * s), "down", 14.0 * s, Style.TEXT_DIM, 0, true)
	# mana
	var mr := Rect2(Vector2(x, o.y + 61.0 * s).round(), Vector2(right - x, 14.0 * s).round())
	var mahead: float = (p.mana + p.mana_coming) / maxf(p.mana_max, 0.001) if p.mana_coming > 0.01 else 0.0
	Style.bar(self, mr, b.mana, b.mana_ghost, Style.MANA_A, Style.MANA_B, s, 1.0, mahead, Color(0.62, 0.86, 1.0))
	Style.text(self, Vector2(mr.end.x - 7.0 * s, mr.position.y + 11.5 * s), _numbers(p.mana, p.mana_max), 12.0 * s, Style.TEXT, 2, true)
	# experience: a thin bar across the foot of the frame, its numbers small beside it
	var xp_text := "XP  %s / %s" % [Style.number(p.xp), Style.number(p.xp_next)] if p.xp_next > 0 else "XP  %s" % Style.number(p.xp)
	var tw: float = Style.text_width(xp_text, 12.0 * s)
	var xr := Rect2(Vector2(o.x + 16.0 * s, o.y + 88.0 * s).round(), Vector2(w - 32.0 * s - tw - 12.0 * s, 5.0 * s).round())
	Style.bar(self, xr, b.xp, 0.0, Style.XP_A, Style.XP_B, s)
	Style.text(self, Vector2(right, o.y + 94.5 * s), xp_text, 12.0 * s, Style.TEXT_DIM, 2)
	if pending:
		Style.text(self, Vector2(o.x + 16.0 * s, o.y - 44.0 * s), "Level up - open the character screen", 14.0 * s, Color(Style.XP_B, 0.75 + 0.25 * sin(hud.now * 5.0)), 0, true)
	_status_row(p, Vector2(o.x + 16.0 * s, o.y - 20.0 * s), s)


func _status_row(p: Dictionary, at: Vector2, s: float, centred := false) -> void:
	var st: PackedFloat32Array = p.status
	var n := st.size() / 4
	if n == 0:
		return
	var step: float = 34.0 * s
	var x: float = at.x - (step * (n - 1) * 0.5 if centred else 0.0)
	for k in range(n):
		var seconds: float = st[k * 4 + 2]
		var most: float = st[k * 4 + 3]
		var c := Vector2(x + step * k, at.y)
		Style.status_icon(self, int(st[k * 4]), c, 14.0 * s, seconds / most if (seconds >= 0.0 and most > 0.0) else -1.0)
		if seconds >= 0.95:
			Style.text(self, c + Vector2(0, 26.0 * s), "%d" % int(ceilf(seconds)), 11.0 * s, Style.TEXT, 1, true)


func _party() -> void:
	# the other players: compact frames stacked above the player's own
	var s: float = hud.s
	var w: float = 250.0 * s
	var h: float = 50.0 * s
	var y: float = hud.area.end.y - (104.0 + 62.0) * s * (0.9 if hud.layout == Hud.LAYOUT_THIRD else 1.0)
	for slot in range(hud.players.size() - 1, -1, -1):
		var p: Dictionary = hud.players[slot]
		if not p.get("present", false) or p.get("local", false):
			continue
		var b: Dictionary = shown.get(slot, {})
		if b.is_empty():
			continue
		y -= h
		var o := Vector2(hud.area.position.x, y).round()
		y -= 8.0 * s
		var alpha: float = 1.0 if p.alive else 0.6
		Style.panel(self, Rect2(o, Vector2(w, h)), s, alpha, 6.0)
		draw_rect(Rect2(o + Vector2(0, 6.0 * s), Vector2(3.0 * s, h - 12.0 * s)), Color(Style.PARTY, alpha))
		var tag := "%d" % p.level
		Style.text(self, o + Vector2(14.0, 19.0) * s, p.name, 14.0 * s, Color(Style.TEXT, alpha), 0, true)
		Style.text(self, o + Vector2(w - 12.0 * s, 19.0 * s), "Lv " + tag, 12.0 * s, Color(Style.TEXT_DIM, alpha), 2)
		if p.get("fake", false):
			Style.text(self, o + Vector2(w + 8.0 * s, 30.0 * s), "TEST DATA - not a player", 12.0 * s, Style.WARN, 0, true)
		var hr := Rect2((o + Vector2(14.0, 26.0) * s).round(), Vector2(w - 26.0 * s, 9.0 * s).round())
		if p.alive:
			Style.bar(self, hr, b.hp, b.ghost, Style.HEALTH_A, Style.HEALTH_B, s, alpha)
			Style.bar(self, Rect2(hr.position + Vector2(0, 13.0 * s), Vector2(hr.size.x, 4.0 * s)).abs(), b.mana, 0.0, Style.MANA_A, Style.MANA_B, s, alpha)
		else:
			Style.skull(self, hr.position + Vector2(7.0, 7.0) * s, 7.0 * s, Style.TEXT_DIM)
			Style.text(self, hr.position + Vector2(20.0, 12.0) * s, "down", 13.0 * s, Style.TEXT_DIM, 0, true)
		var st: PackedFloat32Array = p.status
		for k in range(mini(st.size() / 4, 4)):
			Style.status_icon(self, int(st[k * 4]), o + Vector2(w + 18.0 * s + 26.0 * s * k, 12.0 * s), 9.0 * s, -1.0)


func _minimal(p: Dictionary) -> void:
	# first person: two slim bars under the middle of the picture, numbers small at their ends
	var s: float = hud.s
	var b: Dictionary = shown.get(p.slot, {})
	if b.is_empty():
		return
	var w: float = 300.0 * s
	var c: Vector2 = Vector2(hud.area.get_center().x, hud.area.end.y - 96.0 * s)
	var hr := Rect2(Vector2(c.x - w * 0.5, c.y).round(), Vector2(w, 9.0 * s).round())
	var low: bool = p.alive and p.health < 0.25 * p.health_max
	var ha := Style.HEALTH_A.lerp(Style.HEALTH_LOW, 0.5 + 0.5 * sin(hud.now * 9.0)) if low else Style.HEALTH_A
	var ahead: float = (p.health + p.health_coming) / maxf(p.health_max, 0.001) if p.health_coming > 0.01 else 0.0
	Style.bar(self, hr, b.hp, b.ghost, ha, Style.HEALTH_B, s, 1.0, ahead)
	var mr := Rect2(hr.position + Vector2(0, 13.0 * s), Vector2(w, 6.0 * s)).abs()
	Style.bar(self, mr, b.mana, b.mana_ghost, Style.MANA_A, Style.MANA_B, s)
	Style.text(self, Vector2(hr.position.x - 8.0 * s, hr.position.y + 9.0 * s), Style.number(p.health), 14.0 * s, Style.TEXT, 2, true)
	Style.text(self, Vector2(hr.end.x + 8.0 * s, hr.position.y + 9.0 * s), "Lv %d" % p.level, 13.0 * s, Style.TEXT_DIM, 0, true)
	if b.xp > 0.0:
		draw_rect(Rect2(mr.position + Vector2(0, 9.0 * s), Vector2(w * b.xp, maxf(1.0, 2.0 * s))), Color(Style.XP_B, 0.8))
	_status_row(p, Vector2(c.x, hr.position.y - 22.0 * s), s * 0.85, true)
