extends "res://portal/screen.gd"
# modes.gd - the portal's first screen: which game - CLASSIC or REMASTERED (edition.gd).
#
# Two big cards, each with a picture (drawn here, or the game's own painting through the art skin:
# gameart/portal_skin.gd mode_art), one line of what it is, what it keeps, and two buttons:
#   Play     straight into the game alone
#   Online   Home: rooms, friends, characters - a room plays the type of its host
# The choice is remembered in the profile ([settings] game) and can be changed here (Home's "Change") or in
# Settings -> Game.  Classic: the game as it was (its own HUD, overhead camera, original combat and music, no Elden
# Ring layer) with the sharp art pack and paced at 60.  Remastered: the new HUD, the lighting presets and cleaner
# models, 120 Hz where the display has it, all five views, Hardcore mode, aiming where you look, boss music, and the
# Elden Ring layer when the player's own Elden Ring files are on this computer.

const Edition := preload("res://portal/edition.gd")

const CARDS := [
	["classic", "CLASSIC", "The original game, exactly as it was.",
		["Its own HUD, the overhead camera, original combat and music", "No Hardcore, no aim mode, no Elden Ring layer"],
		"Kept: the sharp art pack, paced at 60 fps"],
	["remastered", "REMASTERED", "The combined version: the game remade with the Elden Ring layer.",
		["New HUD, lighting presets, cleaner models, 120 Hz, all five views", "Hardcore combat and weapons, aim where you look, boss music"],
		""],
]


func hints() -> Array:
	return [hint_select(), hint_back("Back" if (portal.get("stack") as Array).size() > 1 else "Quit")]


func build() -> void:
	var chosen := String(portal.call("edition"))
	say(Rect2(0, 0, size.x, UI.px(60)), "Choose your game", 46, UI.TEXT, UI.serif_bold(), HORIZONTAL_ALIGNMENT_CENTER)
	say(Rect2(0, UI.px(62), size.x, UI.px(30)), "Both play the same characters and friends. You can change this any time in Settings.", 19, UI.DIM, null, HORIZONTAL_ALIGNMENT_CENTER)
	var top := UI.px(118)
	var gap := UI.px(40)
	var w := minf((size.x - gap) * 0.5, UI.px(820))
	var h := size.y - top
	var x0 := roundf((size.x - (w * 2.0 + gap)) * 0.5)
	var er := Edition.er_models_found()
	for k in CARDS.size():
		var spec: Array = CARDS[k]
		var kind := String(spec[0])
		var card := ModeCard.new()
		card.kind = kind
		card.title = String(spec[1])
		card.line = String(spec[2])
		card.facts = spec[3]
		card.kept = String(spec[4])
		card.chosen = chosen == kind
		if kind == Edition.REMASTERED:
			card.kept = "Elden Ring look: on - your own Elden Ring files" if er else "Elden Ring look: needs your own Elden Ring copy - see setup"
			card.kept_ok = er
		var r := Rect2(x0 + k * (w + gap), top, w, h)
		put(card, r)
		var bh := UI.px(68)
		var pad := UI.px(30)
		var by := r.end.y - pad - bh
		var bw := (r.size.x - pad * 2.0 - UI.px(14)) * 0.5
		var play := W.Btn.new("Play", "sword", "primary" if (chosen == kind or (chosen == "" and kind == Edition.REMASTERED)) else "normal")
		play.height = 68.0
		play.font_size = 24.0
		play.fixed = true
		play.key = kind + "_play"
		put(play, Rect2(r.position.x + pad, by, bw, bh))
		play.activated.connect(func() -> void: portal.call("play_edition", kind, "play"))
		var online := W.Btn.new("Online", "people", "normal")
		online.height = 68.0
		online.font_size = 24.0
		online.fixed = true
		online.key = kind + "_online"
		put(online, Rect2(r.position.x + pad + bw + UI.px(14), by, bw, bh))
		online.activated.connect(func() -> void: portal.call("play_edition", kind, "online"))
		card.buttons = [play, online]
		var art := ModeArt.new()
		art.card = card
		card.art = art
		card.add_child(art)
		art.position = Vector2(UI.px(18), UI.px(18)).round()
		art.size = Vector2(r.size.x - UI.px(36), r.size.y * 0.46).round()
	if want_focus == "":
		want_focus = (chosen if chosen != "" else Edition.REMASTERED) + "_play"


func session_changed(_what: String) -> void:
	pass


# ---- a card ---------------------------------------------------------------------------------------------------------
class ModeCard extends Control:
	var kind := ""
	var title := ""
	var line := ""
	var facts: Array = []
	var kept := ""
	var kept_ok := true
	var chosen := false
	var buttons: Array = []
	var art: Control
	var e := 0.0                    # one of its buttons has the focus (eased)
	var t := 0.0

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _process(delta: float) -> void:
		var owner_now := get_viewport().gui_get_focus_owner()
		var hot := false
		for b in buttons:
			if b == owner_now:
				hot = true
		var to := 1.0 if hot else 0.0
		if absf(e - to) > 0.001:
			e = move_toward(e, to, delta * 6.0)
			queue_redraw()
			if art != null:
				art.queue_redraw()
		t += delta
		if kind == "remastered" and art != null:
			art.queue_redraw()      # the light moves a little

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(20)
		UI.focus_glow(self, r, radius, e)
		if not UI.skinned("surface", [self, "panel", r, radius, e, false]):
			draw_style_box(UI.box(radius, Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, Color(0, 0, 0, 0.32), UI.px(18)), r)
			draw_style_box(UI.box(radius, Color(UI.PANEL.r, UI.PANEL.g, UI.PANEL.b, 0.90).lerp(UI.PANEL_HOT, e * 0.5), UI.LINE if e < 0.5 else Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.5), maxf(1.0, UI.px(1.5))), r)
		var art_h := r.size.y * 0.46
		var x := r.position.x + UI.px(32)
		var w := r.size.x - UI.px(64)
		var y := UI.px(18) + art_h + UI.px(10)
		UI.text(self, Rect2(x, y, w, UI.px(60)), title, UI.spaced(UI.serif_bold(), 6.0), 48, UI.GOLD_HI.lerp(Color.WHITE, 0.15 * e))
		y += UI.px(62)
		UI.text(self, Rect2(x, y, w, UI.px(32)), line, UI.bold(), 22, UI.TEXT)
		y += UI.px(46)
		for f in facts:
			UI.dot(self, Vector2(x + UI.px(5), y + UI.px(14)), UI.px(3.5), UI.GOLD, false)
			UI.text(self, Rect2(x + UI.px(20), y, w - UI.px(20), UI.px(28)), String(f), UI.sans(), 18, UI.DIM)
			y += UI.px(32)
		if kept != "":
			y += UI.px(4)
			var colour := UI.GREEN if kept_ok else UI.GOLD
			UI.icon(self, "check" if kept_ok else "warn", Rect2(x - UI.px(2), y + UI.px(3), UI.px(22), UI.px(22)), colour)
			UI.text(self, Rect2(x + UI.px(28), y, w - UI.px(28), UI.px(28)), kept, UI.bold(), 18, colour)


# the card's picture, clipped to its place
class ModeArt extends Control:
	var card: Control

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE
		clip_contents = true

	func _draw() -> void:
		var art := Rect2(Vector2.ZERO, size)
		var kind := String(card.get("kind"))
		var e := float(card.get("e"))
		if not UI.skinned("mode_art", [self, art, kind, e]):
			if kind == "classic":
				_classic_art(art)
			else:
				_remastered_art(art, float(card.get("t")))
		# the edge of the picture into the card
		var low := Color(UI.PANEL.r, UI.PANEL.g, UI.PANEL.b, 0.95)
		var none := Color(UI.PANEL.r, UI.PANEL.g, UI.PANEL.b, 0.0)
		var mid := art.position + Vector2(0, art.size.y * 0.62)
		draw_polygon(PackedVector2Array([mid, mid + Vector2(art.size.x, 0), art.end, Vector2(art.position.x, art.end.y)]), PackedColorArray([none, none, low, low]))
		if bool(card.get("chosen")):
			var tag := "YOUR CHOICE"
			var tw := UI.text_width(tag, UI.spaced(UI.bold(), 2.0), 15) + UI.px(34)
			var tr := Rect2(art.end.x - tw - UI.px(14), art.position.y + UI.px(14), tw, UI.px(32))
			draw_style_box(UI.box(tr.size.y * 0.5, Color(0.05, 0.05, 0.06, 0.78), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.8), maxf(1.0, UI.px(1.5))), tr)
			UI.text(self, tr, tag, UI.spaced(UI.bold(), 2.0), 15, UI.GOLD_HI, HORIZONTAL_ALIGNMENT_CENTER)

	# ---- our own pictures (no art of anybody's): drawn shapes and gradients -----------------------------------------
	func _grad(rect: Rect2, top: Color, bottom: Color) -> void:
		draw_polygon(PackedVector2Array([rect.position, Vector2(rect.end.x, rect.position.y), rect.end, Vector2(rect.position.x, rect.end.y)]),
			PackedColorArray([top, top, bottom, bottom]))

	func _classic_art(a: Rect2) -> void:
		# the game's own view: high above a tiled floor, a torch, the hero - in warm, old colours
		_grad(a, Color(0.20, 0.14, 0.08), Color(0.09, 0.06, 0.035))
		var c := a.get_center() + Vector2(0, a.size.y * 0.06)
		var cell := a.size.y * 0.16
		# the floor: a lattice of diamonds, fading towards the edges
		for i in range(-7, 8):
			for j in range(-5, 6):
				var p := c + Vector2((i - j) * cell, (i + j) * cell * 0.5)
				if not a.grow(-UI.px(4)).has_point(p):
					continue
				var fade := clampf(1.0 - p.distance_to(c) / (a.size.x * 0.55), 0.0, 1.0)
				var shade := 0.10 + 0.05 * float((i + j) & 1)
				var col := Color(0.62, 0.45, 0.25, shade * fade + 0.02)
				var d := PackedVector2Array([p + Vector2(0, -cell * 0.5), p + Vector2(cell, 0), p + Vector2(0, cell * 0.5), p + Vector2(-cell, 0)])
				draw_colored_polygon(d, col)
				d.append(d[0])
				draw_polyline(d, Color(0.9, 0.7, 0.4, 0.10 * fade), maxf(1.0, UI.px(1)), true)
		# torch light
		var torch := c + Vector2(cell * 2.6, -cell * 1.1)
		for k in 6:
			draw_circle(torch, cell * (2.4 - k * 0.36), Color(1.0, 0.62, 0.25, 0.035 + k * 0.012))
		draw_circle(torch, cell * 0.16, Color(1.0, 0.85, 0.5, 0.95))
		# the hero from above: shoulders, head, a sword held out
		var hero := c + Vector2(-cell * 0.6, cell * 0.2)
		draw_circle(hero + Vector2(cell * 0.12, cell * 0.16), cell * 0.62, Color(0, 0, 0, 0.30))
		draw_colored_polygon(PackedVector2Array([hero + Vector2(-cell * 0.55, 0), hero + Vector2(0, -cell * 0.30), hero + Vector2(cell * 0.55, 0), hero + Vector2(0, cell * 0.32)]), Color(0.55, 0.30, 0.18))
		draw_circle(hero, cell * 0.24, Color(0.86, 0.68, 0.48))
		draw_line(hero + Vector2(cell * 0.45, -cell * 0.05), hero + Vector2(cell * 1.5, -cell * 0.62), Color(0.88, 0.88, 0.92), maxf(2.0, UI.px(4)), true)
		draw_line(hero + Vector2(cell * 0.40, -cell * 0.18), hero + Vector2(cell * 0.56, cell * 0.10), UI.GOLD, maxf(2.0, UI.px(4)), true)
		# a vignette
		_vignette(a, 0.55)

	func _remastered_art(a: Rect2, t: float) -> void:
		# a view along the ground: a low sun behind a ridge and a keep, haze, a blade raised in the near ground
		_grad(Rect2(a.position, Vector2(a.size.x, a.size.y * 0.62)), Color(0.09, 0.07, 0.17), Color(0.62, 0.30, 0.16))
		_grad(Rect2(a.position + Vector2(0, a.size.y * 0.62), Vector2(a.size.x, a.size.y * 0.38)), Color(0.20, 0.10, 0.09), Color(0.05, 0.04, 0.06))
		var sun := a.position + Vector2(a.size.x * 0.62, a.size.y * 0.56)
		var pulse := 1.0 + 0.03 * sin(t * 0.8)
		for k in 8:
			draw_circle(sun, a.size.y * (0.62 - k * 0.07) * pulse, Color(1.0, 0.70, 0.35, 0.03 + k * 0.012))
		draw_circle(sun, a.size.y * 0.075, Color(1.0, 0.92, 0.70, 0.95))
		# rays
		for k in 9:
			var ang := -PI * 0.92 + k * PI * 0.105 + 0.02 * sin(t * 0.5 + k)
			var tip := sun + Vector2(cos(ang), sin(ang)) * a.size.x * 0.9
			var side := Vector2(-sin(ang), cos(ang)) * a.size.y * 0.018
			draw_colored_polygon(PackedVector2Array([sun + side * 0.2, tip + side * 3.0, tip - side * 3.0, sun - side * 0.2]), Color(1.0, 0.80, 0.50, 0.035))
		# the ridge and a keep on it
		var ground := a.position.y + a.size.y * 0.66
		var ridge := PackedVector2Array([Vector2(a.position.x, a.end.y)])
		for k in 13:
			var fx := float(k) / 12.0
			ridge.append(Vector2(a.position.x + fx * a.size.x, ground - a.size.y * (0.06 + 0.07 * sin(fx * 7.0 + 1.3) + 0.04 * sin(fx * 17.0))))
		ridge.append(a.end)
		draw_colored_polygon(ridge, Color(0.07, 0.05, 0.08))
		var keep := Vector2(a.position.x + a.size.x * 0.30, ground - a.size.y * 0.10)
		var kw := a.size.y * 0.09
		draw_rect(Rect2(keep - Vector2(kw * 0.5, kw * 2.2), Vector2(kw, kw * 2.2)), Color(0.07, 0.05, 0.08))
		draw_rect(Rect2(keep - Vector2(kw * 1.3, kw * 1.2), Vector2(kw * 2.6, kw * 1.2)), Color(0.07, 0.05, 0.08))
		draw_colored_polygon(PackedVector2Array([keep + Vector2(-kw * 0.6, -kw * 2.2), keep + Vector2(0, -kw * 3.0), keep + Vector2(kw * 0.6, -kw * 2.2)]), Color(0.07, 0.05, 0.08))
		draw_rect(Rect2(keep + Vector2(-kw * 0.12, -kw * 1.7), Vector2(kw * 0.24, kw * 0.34)), Color(1.0, 0.75, 0.40, 0.85))
		# haze
		for k in 3:
			var hy := ground - a.size.y * (0.02 + k * 0.05)
			_grad(Rect2(Vector2(a.position.x, hy), Vector2(a.size.x, a.size.y * 0.05)), Color(1.0, 0.65, 0.45, 0.0), Color(1.0, 0.65, 0.45, 0.06))
		# a blade raised in the near ground (first person), its edge catching the sun
		var hilt := a.position + Vector2(a.size.x * 0.84, a.size.y * 1.02)
		var tip := a.position + Vector2(a.size.x * 0.70, a.size.y * 0.22)
		var along := (tip - hilt).normalized()
		var across := Vector2(-along.y, along.x) * a.size.y * 0.035
		draw_colored_polygon(PackedVector2Array([hilt + across, tip + across * 0.15, tip, hilt - across]), Color(0.62, 0.64, 0.70))
		draw_colored_polygon(PackedVector2Array([hilt + across, tip + across * 0.15, tip]), Color(0.92, 0.88, 0.80))
		draw_line(hilt + across * 3.2 + along * a.size.y * 0.10, hilt - across * 3.2 + along * a.size.y * 0.10, Color(0.55, 0.40, 0.20), maxf(3.0, UI.px(9)), true)
		_vignette(a, 0.45)

	func _vignette(a: Rect2, strength: float) -> void:
		var dark := Color(0, 0, 0, strength)
		var none := Color(0, 0, 0, 0)
		var band := a.size.x * 0.16
		draw_polygon(PackedVector2Array([a.position, a.position + Vector2(band, 0), a.position + Vector2(band, a.size.y), Vector2(a.position.x, a.end.y)]), PackedColorArray([dark, none, none, dark]))
		draw_polygon(PackedVector2Array([Vector2(a.end.x - band, a.position.y), Vector2(a.end.x, a.position.y), a.end, Vector2(a.end.x - band, a.end.y)]), PackedColorArray([none, dark, dark, none]))
