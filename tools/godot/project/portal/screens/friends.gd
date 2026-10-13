extends "res://portal/screen.gd"
# friends.gd - the friends list.
#
# Each friend: the name they chose, what they are doing (offline, online, in a room - can it
# be joined? -, in a game - where), and THE CHARACTER THEY ARE PLAYING (name, level, class).
# A on a friend who can be joined joins; otherwise it invites.  Left / right walks through
# the row's other actions; X always invites.  Removing and blocking sit behind "more" and
# ask before they act.
# On the right: my own friend code (to read out or copy), adding a friend by their code,
# the players met lately with "Add", and the blocked ones.
# Invitations and friend requests that are waiting come first in the list.

const Session := preload("res://portal/session.gd")

var code_typed := ""
var add_field: W.Field


func hints() -> Array:
	return [hint_select(), {"pad": "x", "key": "X", "text": "Invite"}, hint_back()]


func build() -> void:
	var s: Node = portal.session
	var me: Dictionary = s.me()
	var friends: Array = s.friends()
	var requests: Array = s.requests()
	var invites: Array = s.invites()
	var gap := UI.px(36)
	var right_w := clampf(size.x * 0.34, UI.px(430), UI.px(580))
	var left_w := size.x - right_w - gap
	var online := 0
	for f in friends:
		if int(f.presence) > 0:
			online += 1
	say(Rect2(0, 0, left_w * 0.6, UI.px(60)), "Friends", 44, UI.TEXT, UI.serif_bold())
	if not friends.is_empty():
		say(Rect2(left_w * 0.5, UI.px(14), left_w * 0.5 - UI.px(20), UI.px(40)), "%d of %d online" % [online, friends.size()], 20, UI.DIM, null, HORIZONTAL_ALIGNMENT_RIGHT)
	var list_rect := Rect2(-UI.px(8), UI.px(68), left_w + UI.px(8), size.y - UI.px(68))
	var nothing := friends.is_empty() and requests.is_empty() and invites.is_empty()
	if nothing:
		var empty := Empty.new()
		empty.code = String(me.get("friend_code", ""))
		empty.offline = int(me.get("link", 0)) != Session.LINK_ONLINE
		empty.problem = String(me.get("problem", ""))
		put(empty, Rect2(0, UI.px(76), left_w, size.y - UI.px(76)))
	else:
		var box := scroller(list_rect, 8.0)
		if not invites.is_empty():
			box.add_child(W.Heading.new("Invitations", str(invites.size())))
			for v in invites:
				box.add_child(_invite_row(v))
		var incoming := requests.filter(func(r: Dictionary) -> bool: return bool(r.incoming))
		var outgoing := requests.filter(func(r: Dictionary) -> bool: return not bool(r.incoming))
		if not incoming.is_empty():
			box.add_child(W.Heading.new("Want to be your friend", str(incoming.size())))
			for r in incoming:
				box.add_child(_request_row(r))
		var playing := friends.filter(func(f: Dictionary) -> bool: return int(f.presence) >= Session.IN_ROOM)
		var idle := friends.filter(func(f: Dictionary) -> bool: return int(f.presence) == Session.ONLINE)
		var away := friends.filter(func(f: Dictionary) -> bool: return int(f.presence) == Session.OFFLINE)
		if not playing.is_empty():
			box.add_child(W.Heading.new("Playing now", str(playing.size())))
			for f in playing:
				box.add_child(_friend_row(f))
		if not idle.is_empty():
			box.add_child(W.Heading.new("Online", str(idle.size())))
			for f in idle:
				box.add_child(_friend_row(f))
		if not outgoing.is_empty():
			box.add_child(W.Heading.new("Asked, not answered yet", str(outgoing.size())))
			for r in outgoing:
				box.add_child(_request_row(r))
		if not away.is_empty():
			box.add_child(W.Heading.new("Offline", str(away.size())))
			for f in away:
				box.add_child(_friend_row(f))
	# ---- the right column ----
	var rx := left_w + gap
	panel_at(Rect2(rx, 0, right_w, size.y), 18.0)
	var col := scroller(Rect2(rx + UI.px(14), UI.px(14), right_w - UI.px(20), size.y - UI.px(28)), 10.0)
	col.add_child(W.Heading.new("Your friend code"))
	var code := String(me.get("friend_code", ""))
	var big := BigText.new()
	big.text = code if code != "" else "- - - -"
	big.note = "Read it out or send it - a friend types it in and you accept." if code != "" else "You get your code as soon as you are online."
	col.add_child(big)
	var copy := W.Btn.new("Copy my code", "copy", "normal")
	copy.key = "copy"
	copy.height = 54.0
	copy.font_size = 19.0
	copy.set_disabled(code == "")
	copy.activated.connect(func() -> void: portal.call("copy_text", code, "Your friend code"))
	col.add_child(copy)
	col.add_child(_spacer(10))
	col.add_child(W.Heading.new("Add a friend"))
	add_field = W.Field.new("Their code, like K7QF-2MXD", 9)
	add_field.upper = true
	add_field.key = "add_code"
	add_field.height = 58.0
	add_field.text = code_typed
	add_field.edited.connect(func(t: String) -> void: code_typed = t)
	add_field.submitted.connect(func(_t: String) -> void: _add())
	add_field.wants_keys.connect(func() -> void:
		ask_text({"title": "A friend's code", "mode": "code", "text": code_typed, "max": 9, "upper": true, "placeholder": "K7QF-2MXD", "done_text": "Add friend",
			"done": func(t: String) -> void:
				code_typed = t
				_add()}))
	col.add_child(add_field)
	var add := W.Btn.new("Add friend", "plus", "primary")
	add.key = "add"
	add.height = 54.0
	add.font_size = 19.0
	add.activated.connect(_add)
	col.add_child(add)
	var recent: Array = s.recent()
	if not recent.is_empty():
		col.add_child(_spacer(10))
		col.add_child(W.Heading.new("Played with lately"))
		for f in recent:
			col.add_child(_recent_row(f))
	var blocked: Array = s.blocked()
	if not blocked.is_empty():
		col.add_child(_spacer(10))
		var bb := W.Btn.new("%d blocked" % blocked.size(), "", "ghost")
		bb.key = "blocked"
		bb.height = 48.0
		bb.font_size = 17.0
		bb.activated.connect(_blocked_menu)
		col.add_child(bb)
	if want_focus == "":
		want_focus = "copy" if nothing else ""


func _spacer(h: float) -> Control:
	var c := Control.new()
	c.custom_minimum_size = Vector2(1, UI.px(h))
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return c


static func nice_level(level: String) -> String:
	# the game's own short name of a level, set with a capital; a readable title comes from the game when it has one
	return level.capitalize() if level != "" else ""


func status_of(f: Dictionary) -> Array:
	# [text, colour]
	match int(f.presence):
		Session.ONLINE:
			return ["Online", UI.GREEN]
		Session.IN_ROOM:
			if bool(f.joinable):
				return ["In a room - you can join (%d of 4)" % int(f.room_players), UI.BLUE]
			return ["In a room", UI.BLUE]
		Session.IN_GAME:
			var where := nice_level(String(f.level))
			var text := "In a game"
			if where != "":
				text += " - " + where
			if int(f.room_players) > 1:
				text += ", %d players" % int(f.room_players)
			return [text, UI.VIOLET]
	var seen := int(f.get("last_seen", 0))
	if seen > 0:
		return ["Offline - seen " + UI.ago(int(Time.get_unix_time_from_system()) - seen), UI.FAINT]
	return ["Offline", UI.FAINT]


func _friend_row(f: Dictionary) -> Control:
	var row := W.Row.new()
	var id := String(f.id)
	row.key = "friend:" + id
	row.who = String(f.name)
	row.seed_key = id
	row.presence = int(f.presence)
	var st := status_of(f)
	row.status = st[0]
	row.status_colour = st[1]
	row.detail = UI.character_line(f.get("character", {}))
	var actions := []
	if bool(f.get("invited_me", false)):
		actions.append({"id": "accept", "text": "Join", "icon": "door"})
	elif int(f.presence) == Session.IN_ROOM and bool(f.joinable):
		actions.append({"id": "join", "text": "Join", "icon": "door"})
	if int(f.presence) != Session.OFFLINE:
		actions.append({"id": "invite", "text": "Invite", "icon": "plus"})
	actions.append({"id": "more", "icon": "dots"})
	row.actions = actions
	row.action.connect(func(what: String) -> void: _friend_action(what, f))
	return row


func _friend_action(what: String, f: Dictionary) -> void:
	var id := String(f.id)
	var name := String(f.name)
	match what:
		"accept":
			portal.call("accept_invite", id)
		"join":
			portal.call("join_friend", id)
		"invite":
			portal.call("invite_friend", id, name)
		"more":
			portal.call("menu", name, [
				{"text": "Remove from friends", "icon": "cross", "run": func() -> void:
					portal.call("confirm", "Remove %s?" % name, "You will no longer see each other in the friends list. They are not told.", "Remove",
						func() -> void: portal.session.friend_remove(id), true)},
				{"text": "Block", "icon": "warn", "run": func() -> void:
					portal.call("confirm", "Block %s?" % name, "They see you as offline and can no longer ask, invite or join you. You can undo it here.", "Block",
						func() -> void: portal.session.block(id), true)},
				{"text": "Cancel", "kind": "ghost"},
			], UI.character_line(f.get("character", {})))


func _request_row(r: Dictionary) -> Control:
	var row := W.Row.new()
	var id := String(r.id)
	row.key = "request:" + id
	row.who = String(r.name)
	row.seed_key = id
	row.height = 76.0
	if bool(r.incoming):
		row.status = "Wants to be your friend"
		row.status_colour = UI.GOLD
		row.detail = String(r.friend_code)
		row.actions = [{"id": "accept", "text": "Accept", "icon": "check"}, {"id": "decline", "text": "No", "icon": "cross"}]
		row.action.connect(func(what: String) -> void:
			if what == "accept":
				portal.session.friend_accept(id)
			else:
				portal.session.friend_decline(id))
	else:
		row.status = "Waiting for their answer"
		row.status_colour = UI.DIM
		row.detail = String(r.friend_code)
		row.focus_mode = Control.FOCUS_NONE
		row.disabled = true
	return row


func _invite_row(v: Dictionary) -> Control:
	var row := W.Row.new()
	var id := String(v.from_id)
	row.key = "invite:" + id
	row.who = String(v.from_name)
	row.seed_key = id
	row.presence = Session.IN_ROOM
	row.status = "Invites you to play (%d in the room)" % int(v.room_players)
	row.status_colour = UI.BLUE
	row.detail = UI.character_line(v.get("character", {}))
	row.actions = [{"id": "join", "text": "Join", "icon": "door"}, {"id": "dismiss", "text": "Not now", "icon": "cross"}]
	row.action.connect(func(what: String) -> void:
		if what == "join":
			portal.call("accept_invite", id)
		else:
			portal.session.invite_dismiss(id))
	return row


func _recent_row(f: Dictionary) -> Control:
	var row := W.Row.new()
	var id := String(f.id)
	row.key = "recent:" + id
	row.who = String(f.name)
	row.seed_key = id
	row.height = 70.0
	row.detail = UI.character_line(f.get("character", {}))
	if bool(f.get("is_friend", false)):
		row.status = "Friend"
		row.status_colour = UI.GREEN
	elif bool(f.get("request_sent", false)):
		row.status = "Asked"
		row.status_colour = UI.DIM
	else:
		row.actions = [{"id": "add", "text": "Add", "icon": "plus"}]
		row.action.connect(func(_what: String) -> void:
			portal.session.friend_add_id(id)
			portal.call("toast", "Asked %s to be friends" % String(f.name), "good"))
	if row.actions.is_empty():
		row.focus_mode = Control.FOCUS_NONE
		row.disabled = true
	return row


func _blocked_menu() -> void:
	var items := []
	for f in portal.session.blocked():
		var id := String(f.id)
		items.append({"text": "Unblock " + String(f.name), "icon": "check", "run": func() -> void: portal.session.unblock(id)})
	items.append({"text": "Close", "kind": "ghost"})
	portal.call("menu", "Blocked players", items, "They see you as offline and cannot ask, invite or join you.")


func _add() -> void:
	var code := code_typed.strip_edges()
	if code == "":
		portal.call("toast", "Type your friend's code first", "info")
		return
	if portal.session.friend_add(code) == 0:
		code_typed = ""
		portal.call("toast", "Asked - they show up here when they accept", "good")
		rebuild()


func shortcut(name: String) -> bool:
	if name == "x":
		var f := get_viewport().gui_get_focus_owner()
		if f != null and String(f.get("key")).begins_with("friend:"):
			var id := String(f.get("key")).substr(7)
			for fr in portal.session.friends():
				if String(fr.id) == id and int(fr.presence) != Session.OFFLINE:
					portal.call("invite_friend", id, String(fr.name))
					return true
	return false


func session_changed(what: String) -> void:
	if what in ["friends", "requests", "invites", "recent", "me", "link"]:
		rebuild()


class BigText extends Control:
	var text := ""
	var note := ""

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _ready() -> void:
		custom_minimum_size = Vector2(UI.px(200), UI.px(118))

	func _draw() -> void:
		var font := UI.spaced(UI.bold(), 5.0)
		var size_px := 46.0
		while size_px > 20.0 and UI.text_width(text, font, size_px) > size.x - UI.px(8):
			size_px -= 2.0
		UI.text(self, Rect2(0, 0, size.x, UI.px(66)), text, font, size_px, UI.GOLD_HI)
		var para := TextParagraph.new()
		para.add_string(note, UI.sans(), UI.fs(16))
		para.width = size.x
		para.draw(get_canvas_item(), Vector2(0, UI.px(68)), UI.DIM)


class Empty extends Control:
	var code := ""
	var offline := false
	var problem := ""

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		UI.panel(self, Rect2(Vector2.ZERO, size), 18.0, 0.7)
		var c := Vector2(size.x * 0.5, size.y * 0.30)
		var m := UI.px(120)
		draw_style_box(UI.box(m * 0.5, Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.08), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.5), maxf(1.5, UI.px(2))), Rect2(c - Vector2(m, m) * 0.5, Vector2(m, m)))
		UI.icon(self, "people", Rect2(c - Vector2(m, m) * 0.28, Vector2(m, m) * 0.56), UI.GOLD_HI)
		var w := minf(size.x - UI.px(80), UI.px(720))
		var x := (size.x - w) * 0.5
		var y := c.y + m * 0.5 + UI.px(30)
		UI.text(self, Rect2(x, y, w, UI.px(50)), "No friends here yet", UI.serif_bold(), 38, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
		y += UI.px(62)
		var lines := ["Read your code out to a friend - or type theirs in on the right.", "Once they accept, they show up here with the character they play,", "and one press joins their game."]
		if offline:
			lines = ["You are offline right now" + (": " + problem if problem != "" else "."), "Playing alone works; friends come back with the connection."]
		for line in lines:
			UI.text(self, Rect2(x, y, w, UI.px(32)), line, UI.sans(), 21, UI.DIM, HORIZONTAL_ALIGNMENT_CENTER)
			y += UI.px(32)
		if code != "" and not offline:
			y += UI.px(26)
			UI.text(self, Rect2(x, y, w, UI.px(24)), "YOUR CODE", UI.spaced(UI.bold(), 2.5), 14, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER)
			y += UI.px(28)
			UI.text(self, Rect2(x, y, w, UI.px(70)), code, UI.spaced(UI.bold(), 6.0), 54, UI.GOLD_HI, HORIZONTAL_ALIGNMENT_CENTER)
