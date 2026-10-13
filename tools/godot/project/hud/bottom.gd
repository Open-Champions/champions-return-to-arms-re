extends Control
# bottom.gd - the lower part of the picture: potions and the two quick slots with their
# buttons, counts and cooldowns, the weapon in hand, the interaction prompt, the gold
# counter and the feed of what was gained (gold, experience, items), and the ring of the
# game's quick-cast selector while it is held open.
#
# Slots show the ability's name as text (no game art): two letters large, the name small.

const Style := preload("res://hud/style.gd")
const Hud := preload("res://hud/hud.gd")

const FEED_TIME := 5.0
const FEED_LINES := 6

var hud: Node
var feed: Array = []                    # {text, colour, icon, born, amount, key}
var gold_shown := -1.0
var gold_bump := -10.0
var prompt_alpha := 0.0
var prompt_text := ""
var prompt_button := 0
var prompt_kind := 0
var potion_flash := [-10.0, -10.0]
var potions_seen := [-1, -1]
var last_signature := ""
var selector_alpha := 0.0

const KIND_WORDS := {2: "Open the door", 3: "Open", 4: "Save point", 5: "Trade", 6: "Travel", 7: "Talk", 8: "Pick up", 9: "Use", 10: "Enter"}


func tick() -> void:
	var now: float = hud.now
	var me: Dictionary = hud.me
	for e in hud.events:
		if e.slot < 0 or e.slot >= hud.players.size() or not hud.players[e.slot].get("local", false):
			continue                    # (kills are not listed: the experience line says it)
		match int(e.kind):
			5: _feed("xp", "+{n} experience", e.amount, Style.XP_TEXT, 2)
			6:
				if e.amount > 0:
					_feed("gold", "+{n} gold", e.amount, Style.GOLD, 1)
					gold_bump = now
				else:
					_feed("spent", "{n} gold", e.amount, Style.TEXT_DIM, 1)
			8: _feed("item:" + e.text, e.text + "{x}", e.amount, Style.TEXT, 3)
			10: _feed("died", "You have fallen", 0, Style.DANGER, 4)
	var k := 0
	while k < feed.size():
		if now - feed[k].born > FEED_TIME:
			feed.remove_at(k)
		else:
			k += 1
	if not me.is_empty():
		var total: float = me.gold + me.gold_coming
		if gold_shown < 0.0:
			gold_shown = total
		gold_shown = move_toward(gold_shown, total, maxf(absf(total - gold_shown) * 6.0, 30.0) * hud.dt)
		for kind in range(2):
			var have: int = me.health_potions if kind == 0 else me.mana_potions
			if potions_seen[kind] >= 0 and have != potions_seen[kind]:
				potion_flash[kind] = now
			potions_seen[kind] = have
	var prompt: Dictionary = hud.frame.get("prompt", {}) if hud.ok else {}
	# (a view that leaves the player's model out also leaves the game's own prompt out: Player_draw draws it)
	var view: Dictionary = hud.frame.get("view", {}) if hud.ok else {}
	if prompt.get("active", false) and (hud.own_text or view.get("hide_player", false)):
		prompt_text = prompt.text
		prompt_button = prompt.button
		prompt_kind = prompt.kind
		prompt_alpha = move_toward(prompt_alpha, 1.0, hud.dt / 0.12)
	else:
		prompt_alpha = move_toward(prompt_alpha, 0.0, hud.dt / 0.2)
	selector_alpha = move_toward(selector_alpha, 1.0 if me.get("selector_open", false) else 0.0, hud.dt / 0.12)
	# drawn again only when something shown changed or moves
	var sig := "%d|%d|%s|%d|%.2f|%.2f|%d" % [hud.layout, int(hud.s * 100.0), str(hud.area), feed.size(), prompt_alpha, selector_alpha, int(hud.frame.get("boss_uid", 0)) if hud.ok else 0]
	var busy := false
	if not me.is_empty():
		sig += "|%d|%d|%d|%s|%d|%d" % [me.health_potions, me.mana_potions, int(gold_shown), me.weapon, me.ammunition, me.get("selector_position", -1)]
		for q in me.slots:
			if q.filled:
				sig += "|%s%d%d%d" % [q.name, int(q.cooldown * 20.0), int(q.active), int(q.enough_mana)]
				if q.cooldown > 0.0 or q.active:
					busy = true
		busy = busy or me.health_coming > 0.01 or me.mana_coming > 0.01
	if sig != last_signature or busy or not feed.is_empty() or now - gold_bump < 0.6 or now - potion_flash[0] < 0.6 or now - potion_flash[1] < 0.6 \
			or (prompt_alpha > 0.0 and prompt_alpha < 1.0):
		last_signature = sig
		queue_redraw()


func _feed(key: String, pattern: String, amount: float, colour: Color, icon: int) -> void:
	# the same kind of gain within the line's life adds up instead of making a new line
	for f in feed:
		if f.key == key and hud.now - f.born < FEED_TIME - 1.0:
			f.amount += amount
			f.text = _line(pattern, f.amount)
			f.born = hud.now - 0.2
			f.bump = hud.now
			return
	feed.append({"key": key, "text": _line(pattern, amount), "colour": colour, "icon": icon, "born": hud.now, "amount": amount, "bump": hud.now})
	if feed.size() > FEED_LINES:
		feed.pop_front()


func _line(pattern: String, amount: float) -> String:
	return pattern.replace("{n}", Style.number(amount)).replace("{x}", ("  x" + Style.number(amount)) if amount > 1.5 else "")


func test(w: Array) -> void:
	if w.size() >= 2 and str(w[0]) == "feed":
		_feed("test" + str(feed.size()), " ".join(PackedStringArray(w.slice(1))) + "  (TEST DATA)", 0, Style.TEXT, 3)


func _draw() -> void:
	var t0: int = hud.draw_begin()
	var me: Dictionary = hud.me
	if not me.is_empty():
		var s: float = hud.s
		var area: Rect2 = hud.area
		var first: bool = hud.layout == Hud.LAYOUT_FIRST
		var third: bool = hud.layout == Hud.LAYOUT_THIRD
		var k: float = s * (0.82 if first else (0.9 if third else 1.0))
		# where the bar of slots sits: overhead in the middle, in the close views to the right (the character has the middle)
		var bar_w: float = (2.0 * 50.0 + 2.0 * 64.0 + 4.0 * 10.0 + 22.0) * k
		var x: float = area.get_center().x - bar_w * 0.5
		if first or third:
			x = area.end.x - bar_w
		# at 4:3 the slots must not run into the player's frame on the left
		x = maxf(x, area.position.x + 392.0 * s + 28.0 * s) if not (first or third) else x
		x = minf(x, area.end.x - bar_w)
		var base: float = area.end.y
		# the game's own boss meter is drawn across the lower middle (y 414..430 of 448) and no switch hides it yet: step over it
		if not (first or third) and int(hud.frame.get("boss_uid", 0)) != 0 and not hud.setting.get("game_meter_hidden", false):
			base = minf(base, hud.picture.position.y + hud.picture.size.y * (406.0 / 448.0))
		_slots(me, Vector2(x, base), k)
		_gold(me, s, first, (64.0 * k + 34.0 * s) if (first or third) else 0.0)
		_prompt(s, (area.end.y - 158.0 * s) if first else (base - 64.0 * k - 60.0 * s))
		if selector_alpha > 0.01:
			_selector(me, s)
	hud.draw_end(t0)


func _slots(me: Dictionary, at: Vector2, s: float) -> void:
	var x: float = at.x
	var bottom: float = at.y
	# potions: health (the game's potion button A), mana (button B)
	for kind in range(2):
		var size: float = 50.0 * s
		var rect := Rect2(Vector2(x, bottom - size).round(), Vector2(size, size).round())
		var have: int = me.health_potions if kind == 0 else me.mana_potions
		var colour: Color = (Style.HEALTH_B if kind == 0 else Style.MANA_B)
		var alpha: float = 1.0 if have > 0 else 0.4
		Style.panel(self, rect, s, 1.0, 8.0)
		var flash: float = clampf(1.0 - (hud.now - potion_flash[kind]) / 0.5, 0.0, 1.0)
		if flash > 0.0:
			Style.rounded(self, rect, 8.0 * s, Color(colour, 0.5 * flash))
		Style.flask(self, rect.get_center() + Vector2(0, 2.0 * s), 15.0 * s, Color(colour, alpha))
		# a potion at work: the rim fills as it is delivered
		var coming: float = me.health_coming if kind == 0 else me.mana_coming
		if coming > 0.01:
			draw_arc(rect.get_center(), size * 0.5 - 3.0 * s, 0, TAU, 40, Color(colour, 0.5 + 0.4 * sin(hud.now * 8.0)), 2.0 * s, true)
		Style.text(self, rect.end + Vector2(-6.0, -5.0) * s, str(have), 16.0 * s, Style.TEXT if have > 0 else Style.DANGER, 2, true)
		_cap(rect.position + Vector2(-4.0, -4.0) * s, 0x2 if kind == 0 else 0x1, s)
		x += size + 10.0 * s
	x += 12.0 * s
	# the two quick slots
	var masks := [0x20, 0x10]            # the game's ability buttons A and B (g_btnAbilityA / B, default map)
	for which in range(2):
		var size: float = 64.0 * s
		var rect := Rect2(Vector2(x, bottom - size).round(), Vector2(size, size).round())
		var q: Dictionary = me.slots[which]
		Style.panel(self, rect, s, 1.0, 9.0)
		if q.filled:
			var ready: bool = q.cooldown <= 0.0 and q.enough_mana
			var name: String = q.name
			var tint := Color.from_hsv(fmod(absf(float(q.skill_id)) * 0.137, 1.0), 0.45, 0.95)
			if q.active:
				Style.rounded(self, rect.grow(-2.0 * s), 8.0 * s, Color(tint, 0.30 + 0.15 * sin(hud.now * 10.0)), Color(tint, 0.9), maxi(1, int(2.0 * s)))
			var letters := _initials(name)
			Style.text(self, rect.get_center() + Vector2(0, 5.0 * s), letters, 26.0 * s, Color(tint, 1.0 if ready else 0.4), 1, true)
			var small := name if Style.text_width(name, 11.0 * s) < size - 6.0 * s else name.substr(0, 9) + "."
			Style.text(self, Vector2(rect.get_center().x, rect.end.y - 6.0 * s), small, 11.0 * s, Color(Style.TEXT_DIM, 1.0 if ready else 0.6), 1)
			if q.cooldown > 0.0:
				# the cooldown: a dark wedge that closes, and the seconds
				var frac: float = clampf(q.cooldown / maxf(q.cooldown_most, 0.05), 0.0, 1.0)
				var c := rect.get_center()
				var pts := PackedVector2Array([c])
				var steps := 24
				for j in range(steps + 1):
					var ang: float = -PI * 0.5 - TAU * frac * (float(j) / steps)
					var d := Vector2(cos(ang), sin(ang))
					var m: float = (size * 0.5 - 3.0 * s) / maxf(absf(d.x), absf(d.y))
					pts.append(c + d * m)
				if pts.size() >= 3 and frac > 0.02:
					draw_colored_polygon(pts, Color(0, 0, 0, 0.62))
				Style.text(self, c + Vector2(0, 7.0 * s), ("%.1f" % q.cooldown) if q.cooldown < 10.0 else str(int(q.cooldown)), 20.0 * s, Style.TEXT, 1, true)
			elif not q.enough_mana:
				Style.rounded(self, rect.grow(-2.0 * s), 8.0 * s, Color(Style.MANA_A, 0.25))
			if q.rank > 0:
				Style.text(self, rect.position + Vector2(size - 6.0 * s, 15.0 * s), str(q.rank), 12.0 * s, Style.TEXT_DIM, 2, true)
		else:
			draw_arc(rect.get_center(), 9.0 * s, 0, TAU, 24, Color(1, 1, 1, 0.14), maxf(1.0, 1.5 * s), true)
		_cap(rect.position + Vector2(-4.0, -4.0) * s, masks[which], s)
		x += size + 10.0 * s
	# the weapon in hand, as text; arrows or throwing weapons with their count
	var weapon: String = me.weapon
	if weapon != "":
		var label := weapon
		if (me.weapon_class == 4 or me.weapon_class == 6) and me.ammunition > 0:
			label += "  x%d" % me.ammunition
		var lw: float = Style.text_width(label, 13.0 * s) + 20.0 * s
		Style.rounded(self, Rect2(Vector2(at.x, bottom - 94.0 * s).round(), Vector2(lw, 22.0 * s).round()), 11.0 * s, Color(Style.INK, 0.62))
		Style.text(self, Vector2(at.x + 10.0 * s, bottom - 78.0 * s), label, 13.0 * s, Style.TEXT, 0)


func _initials(name: String) -> String:
	var words := name.split(" ", false)
	if words.size() >= 2:
		return (words[0].substr(0, 1) + words[1].substr(0, 1)).to_upper()
	return name.substr(0, 2).capitalize()


func _cap(at: Vector2, game_mask: int, s: float) -> void:
	var label: String = hud.button_label(game_mask)
	_button(at + Vector2(0, 9.0 * s), label, 11.0 * s)


# a key's or a controller button's cap; the four face buttons are drawn as their shapes
func _button(left_centre: Vector2, label: String, size: float, alpha := 1.0) -> float:
	if label in ["tri", "cir", "cro", "squ"]:
		var r: float = size * 0.82
		var c := left_centre + Vector2(r, 0)
		draw_circle(c, r, Color(0.10, 0.10, 0.13, 0.95 * alpha))
		draw_arc(c, r, 0, TAU, 24, Color(1, 1, 1, 0.35 * alpha), 1.0, true)
		var w: float = maxf(1.5, size * 0.16)
		var g: float = r * 0.48
		match label:
			"tri": draw_polyline(PackedVector2Array([c + Vector2(0, -g * 1.1), c + Vector2(g, g * 0.75), c + Vector2(-g, g * 0.75), c + Vector2(0, -g * 1.1)]), Color(0.45, 0.90, 0.70, alpha), w, true)
			"cir": draw_arc(c, g, 0, TAU, 20, Color(0.98, 0.45, 0.42, alpha), w, true)
			"cro":
				draw_line(c + Vector2(-g, -g), c + Vector2(g, g), Color(0.55, 0.70, 1.0, alpha), w, true)
				draw_line(c + Vector2(-g, g), c + Vector2(g, -g), Color(0.55, 0.70, 1.0, alpha), w, true)
			"squ": draw_rect(Rect2(c - Vector2(g, g) * 0.9, Vector2(g, g) * 1.8), Color(0.95, 0.60, 0.85, alpha), false, w)
		return 2.0 * r
	return Style.keycap(self, left_centre, label, size, alpha)


func _gold(_me: Dictionary, s: float, minimal: bool, raise: float) -> void:
	var area: Rect2 = hud.area
	var text := Style.number(gold_shown)
	var bump: float = clampf(1.0 - (hud.now - gold_bump) / 0.5, 0.0, 1.0)
	var size: float = (20.0 + 5.0 * bump) * s
	var w: float = Style.text_width(text, size, true) + 46.0 * s
	var y: float = area.end.y
	var hide_counter: bool = minimal and bump <= 0.0 and feed.is_empty()
	if not hide_counter:
		var rect := Rect2(Vector2(area.end.x - w, y - 36.0 * s).round(), Vector2(w, 36.0 * s).round())
		rect.position.y -= raise
		Style.panel(self, rect, s, 1.0, 18.0)
		Style.coin(self, rect.position + Vector2(18.0, 18.0) * s, 9.0 * s)
		Style.text(self, Vector2(rect.end.x - 14.0 * s, rect.position.y + 25.0 * s), text, size, Style.GOLD.lerp(Color.WHITE, bump * 0.6), 2, true)
		y = rect.position.y - 10.0 * s
	else:
		y -= raise
	# the feed: newest at the bottom, each line slides in from the right and fades at the end of its life
	for k in range(feed.size() - 1, -1, -1):
		var f: Dictionary = feed[k]
		var age: float = hud.now - f.born
		var a: float = clampf(age / 0.18, 0.0, 1.0) * clampf((FEED_TIME - age) / 0.6, 0.0, 1.0)
		var slide: float = (1.0 - Style.ease_out(age / 0.25)) * 40.0 * s
		var pop: float = 1.0 + 0.12 * clampf(1.0 - (hud.now - f.bump) / 0.25, 0.0, 1.0)
		var fs: float = 16.0 * s * pop
		var tw: float = Style.text_width(f.text, fs, true)
		var right: float = area.end.x + slide
		Style.rounded(self, Rect2(Vector2(right - tw - 44.0 * s, y - 26.0 * s), Vector2(tw + 44.0 * s, 28.0 * s)), 14.0 * s, Color(0.04, 0.05, 0.07, 0.62 * a))
		var ic := Vector2(right - tw - 28.0 * s, y - 12.0 * s)
		match int(f.icon):
			1: Style.coin(self, ic, 7.0 * s, a)
			2: Style.glyph(self, 6, ic, 7.5 * s, Color(Style.XP_TEXT, a))
			3: Style.glyph(self, 11, ic, 7.0 * s, Color(Style.TEXT, a))
			4: Style.skull(self, ic, 7.0 * s, Color(Style.DANGER, a))
		Style.text(self, Vector2(right - 12.0 * s, y - 6.5 * s), f.text, fs, Color(f.colour, a), 2, true)
		y -= 32.0 * s


func _prompt(s: float, y: float) -> void:
	if prompt_alpha <= 0.01:
		return
	var text := prompt_text
	if text == "":
		text = KIND_WORDS.get(prompt_kind, "Use")
	var a: float = prompt_alpha
	var size: float = 19.0 * s
	var label: String = hud.button_label(prompt_button) if prompt_button != 0 else ""
	var cap_w: float = 0.0
	if label != "":
		cap_w = (2.0 * size * 0.82 if label in ["tri", "cir", "cro", "squ"] else maxf(size * 1.5, Style.text_width(label, size, true) + size * 0.9)) + 12.0 * s
	var tw: float = Style.text_width(text, size, true)
	var w: float = tw + cap_w + 40.0 * s
	var c: Vector2 = Vector2(hud.area.get_center().x, y)
	var rect := Rect2(Vector2(c.x - w * 0.5, c.y - 22.0 * s + (1.0 - a) * 8.0 * s).round(), Vector2(w, 44.0 * s).round())
	Style.panel(self, rect, s, a, 22.0)
	var x: float = rect.position.x + 20.0 * s
	if label != "":
		_button(Vector2(x, rect.get_center().y), label, size, a)
		x += cap_w
	Style.text(self, Vector2(x, rect.get_center().y + size * 0.36), text, size, Color(Style.TEXT, a), 0, true)


func _selector(me: Dictionary, s: float) -> void:
	# The game's quick-cast selector, held open with the direction pad: eight positions round the character.
	# Only the highlighted position is known as data without the ability records of all eight; the ring shows
	# which way is chosen and the two abilities bound now.
	var a: float = selector_alpha
	var c: Vector2 = hud.picture.get_center() + Vector2(0, hud.picture.size.y * 0.09)
	var r: float = 118.0 * s
	draw_arc(c, r, 0, TAU, 64, Color(0, 0, 0, 0.45 * a), 30.0 * s, true)
	draw_arc(c, r, 0, TAU, 64, Color(1, 1, 1, 0.10 * a), 30.0 * s, true)
	var chosen: int = me.get("selector_position", -1)
	for k in range(8):
		var ang: float = -PI * 0.5 + TAU * k / 8.0
		var p := c + Vector2(cos(ang), sin(ang)) * r
		if k == chosen:
			draw_arc(c, r, ang - TAU / 16.0, ang + TAU / 16.0, 12, Color(Style.XP_B, 0.85 * a), 30.0 * s, true)
		draw_circle(p, 4.0 * s, Color(1, 1, 1, (0.9 if k == chosen else 0.35) * a))
	Style.text(self, c + Vector2(0, -r - 26.0 * s), "Quick cast", 15.0 * s, Color(Style.TEXT, a), 1, true)
