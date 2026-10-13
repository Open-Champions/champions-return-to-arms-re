extends Node
# portal_stub.gd - a stand-in for the portal's node (group "portal"), for trying the HUD's notice card without the
# portal and without a network: the same signals and calls the real one documents (portal/portal.gd).  Test only;
# what it sends is marked as test data.

signal notice(d: Dictionary)
signal notice_gone(id: String)
signal shown_changed(is_shown: bool)

var draw_notices_in_game := true
var answered: Array = []


func _ready() -> void:
	add_to_group("portal")


func test_notice(kind: String) -> void:
	if kind == "request":
		notice.emit({"id": "request:test", "kind": "request", "who": "TEST DATA", "title": "TEST DATA wants to be your friend", "text": "made up by the test", "accept_text": "Accept"})
	else:
		notice.emit({"id": "invite:test", "kind": "invite", "who": "TEST DATA", "title": "TEST DATA invites you to play", "text": "Room made up by the test", "accept_text": "Join"})


func notice_answer(id: String, accept: bool) -> void:
	answered.append([id, accept])
	print("portal stub: notice %s answered: %s" % [id, "accepted" if accept else "declined"])
	notice_gone.emit(id)
