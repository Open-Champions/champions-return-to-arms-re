extends SceneTree
# Authored players/notice callbacks only; call production tick/layout/ownership.
const Hud := preload("res://hud/hud.gd")
const Status := preload("res://hud/status.gd")
const Top := preload("res://hud/top.gd")
const Portal := preload("res://portal/portal.gd")
const Notices := preload("res://portal/notices.gd")
const Notice := preload("res://hud/notice.gd")
var checks := 0
var failures: Array[String] = []

class FakeHud extends Node:
	var players: Array = []
	var me := {}
	var events: Array = []
	var now := 10.0
	var dt := 0.1
	var s := 0.74
	var area := Rect2(13.5,13.5,933,513)
	var layout := 0
	var setting := {"fake_party":0}
	var creatures := PackedFloat32Array()
	var frame := {}
	var ok := true
	var phase := 2
	var show := 1.0
	var own_text := true

class NoticeHud extends CanvasLayer:
	var ok := true
	var phase := 2
	var notices: Array = []
	var notice_piece: Control
	func _process(_delta: float) -> void:
		pass
class Game extends Node:
	var hud_node: Node
class Handover extends Node:
	var game: Node
class Screen extends Control:
	var chrome_on := true
	func chrome() -> bool:
		return chrome_on
class Counter extends RefCounted:
	var count := 0
	func accept() -> void:
		count += 1

func _check(label: String, value: bool) -> void:
	checks += 1
	if not value:
		failures.append(label)

func _player(slot: int, local: bool) -> Dictionary:
	return {"slot":slot,"present":true,"local":local,"name":"Authored%d"%slot,"level":1,"level_ack":1,
		"health":100.0,"health_max":100.0,"health_coming":0.0,"mana":40.0,"mana_max":50.0,"mana_coming":0.0,
		"xp":10,"xp_base":0,"xp_next":100,"alive":true,"status":PackedFloat32Array(),"class_name":"Authored"}

func _hint_envelope(hud: FakeHud) -> Rect2:
	# The existing Souls draw's four-line maximum, including its real minimum
	# font/ascent. Independent of the party's new gap/rectangle implementation.
	var s := hud.s
	var k := 0.9 if hud.layout == Hud.LAYOUT_THIRD else 1.0
	var h := maxf(5.0,7.0*s*k)
	var y := hud.area.end.y-104.0*s*k-16.0*s*k-h
	var cs := int(maxf(9.0,10.0*s))
	var line := float(cs)+3.0*s
	var top := y-6.0*s-4.0*line-ThemeDB.fallback_font.get_ascent(cs)
	var bottom := y-6.0*s-line+ThemeDB.fallback_font.get_descent(cs)
	return Rect2(hud.area.position.x+100.0*s*k,top,380.0*s,bottom-top)

func _status_tests() -> void:
	var hud := FakeHud.new()
	hud.players=[_player(0,true),_player(1,true)]
	hud.me=hud.players[0]
	var status := Status.new()
	status.hud=hud
	status.tick()
	_check("other local party slot retained",status._party_slots()==PackedInt32Array([1]))
	var rows: Array=status._party_frames()
	_check("other local gets full health+mana row",rows.size()==1 and not rows[0].compact)
	hud.players[1].health=60.0
	hud.now=11.0
	status.tick()
	_check("other local damage does not flash primary",status.hurt_at<0.0)
	_check("other local damage still updates own ghost bar",status.shown[1].hp<1.0 and status.shown[1].ghost>status.shown[1].hp)
	hud.events=[{"kind":7,"slot":1,"amount":2}]
	hud.players[1].level=2
	status.tick()
	_check("other local level does not flash primary",status.level_flash<0.0)
	hud.players[0].health=70.0
	hud.events=[]
	hud.now=12.0
	status.tick()
	_check("primary damage retains feedback",status.hurt_at==12.0)
	hud.players[0].level=2
	hud.events=[{"kind":7,"slot":0,"amount":2}]
	hud.now=13.0
	status.tick()
	_check("primary level retains feedback",status.level_flash==13.0)
	var top := Top.new()
	top.hud=hud
	hud.events=[{"kind":7,"slot":1,"amount":3}]
	top.tick()
	_check("other local level does not replace primary banner",top.levelup_at<0.0)
	hud.events=[{"kind":7,"slot":0,"amount":2}]
	top.tick()
	_check("primary banner retained",top.levelup_at==hud.now and top.levelup_level==2)
	for height in [540.0,1080.0]:
		for scale in [0.5,1.0,2.0]:
			hud.s=maxf(0.74,height/1080.0)*scale
			hud.area=Rect2(height*0.025,height*0.025,height*16.0/9.0-height*0.05,height*0.95)
			for layout in [Hud.LAYOUT_OVERHEAD,Hud.LAYOUT_THIRD]:
				hud.layout=layout
				rows=status._party_frames()
				if rows.is_empty():
					_check("local card missing %s/%s/%s"%[height,scale,layout],false)
					continue
				var r: Rect2=rows[0].rect
				_check("local card clear of Souls hints %s/%s/%s"%[height,scale,layout],not r.intersects(_hint_envelope(hud)))
				_check("local card inside safe area %s/%s/%s"%[height,scale,layout],hud.area.encloses(r))
	# Additional locals retain the existing first-person bottom stack too.
	hud.layout=Hud.LAYOUT_FIRST
	for height in [540.0,1080.0]:
		for scale in [0.5,1.0,2.0]:
			hud.s=maxf(0.74,height/1080.0)*scale
			hud.area=Rect2(height*0.025,height*0.025,height*16.0/9.0-height*0.05,height*0.95)
			rows=status._party_frames()
			if rows.is_empty():
				_check("local first-person missing %s/%s"%[height,scale],false)
				continue
			var r: Rect2=rows[0].rect
			_check("local first-person full row %s/%s"%[height,scale],rows.size()==1 and not rows[0].compact and r.position==Vector2(hud.area.position.x,hud.area.end.y-42.0*hud.s).round())
			_check("local first-person inside game picture %s/%s"%[height,scale],Rect2(0,0,height*16.0/9.0,height).encloses(r))
	# One-local network geometry is unchanged, including first-person placement.
	hud.players=[_player(0,true),_player(1,false),_player(2,false)]
	hud.me=hud.players[0]
	for layout in [Hud.LAYOUT_OVERHEAD,Hud.LAYOUT_THIRD,Hud.LAYOUT_FIRST]:
		hud.layout=layout
		hud.s=0.74
		var k:=0.9 if layout==Hud.LAYOUT_THIRD else 1.0
		var y:=hud.area.end.y-(104.0+62.0)*hud.s*k
		if layout==Hud.LAYOUT_FIRST:
			y=hud.area.end.y+8.0*hud.s
		rows=status._party_frames()
		var same:=rows.size()==2
		for row in rows:
			y-=50.0*hud.s
			same=same and row.rect.position==Vector2(hud.area.position.x,y).round() and not row.compact
			y-=8.0*hud.s
		_check("one-local network layout retained %d"%layout,same)
	hud.players=[]
	for slot in range(8):
		hud.players.append(_player(slot,slot<2))
	hud.me=hud.players[0]
	rows=status._party_frames()
	var local_full:=false
	var remote_compact:=true
	for row in rows:
		if row.slot==1:
			local_full=not row.compact
		else:
			remote_compact=remote_compact and row.compact
	_check("large party retains local mana",local_full)
	_check("large remote rows retain compact style",remote_compact)
	hud.players[3].present=false
	_check("absent slots excluded",not status._party_slots().has(3))
	hud.me=hud.players[1]
	_check("primary identity can be nonzero",not status._party_slots().has(1) and status._party_slots().has(0))
	status.free()
	top.free()
	hud.free()

func _notice_tests() -> void:
	var portal:=Portal.new()
	var notices:=Notices.new()
	notices.set_process(false)
	var screen:=Screen.new()
	var handover:=Handover.new()
	var game:=Game.new()
	var hud:=NoticeHud.new()
	var piece:=Control.new()
	var fade_root:=Control.new()
	hud.notice_piece=piece
	fade_root.add_child(piece)
	hud.add_child(fade_root)
	get_root().add_child(hud)
	hud.set_process(true)
	handover.game=game
	game.hud_node=hud
	portal.handover=handover
	portal.screen=screen
	portal.notices=notices
	portal.shown=false
	var count:=Counter.new()
	notices.push({"id":"older","title":"Authored older","seconds":20.0,"on_accept":count.accept})
	notices.push({"id":"seed","title":"Authored","text":"Authored","seconds":10.0,"on_accept":count.accept})
	notices._process(3.0)
	portal.draw_notices_in_game=false
	portal._update_notice_visibility()
	_check("seed before claim stays in Portal",notices.visible)
	_check("claim preserves current backlog order",notices.current().id=="seed" and notices.items.size()==2 and notices.items[0].id=="seed" and notices.items[1].id=="older")
	_check("claim preserves existing ages/deadlines",notices.items[0].age==3.0 and notices.items[0].seconds==10.0 and notices.items[1].age==3.0 and notices.items[1].seconds==20.0)
	_check("visibility does not accept callback",count.count==0)
	hud.notices=[{"id":"different"}]
	portal._update_notice_visibility()
	_check("different HUD notice does not hide current Portal card",notices.visible)
	hud.notices=[{"id":"seed"}]
	portal._update_notice_visibility()
	_check("matching current visible owner removes duplicate",not notices.visible)
	_check("matching ownership preserves backlog order/age",notices.current().id=="seed" and notices.items.size()==2 and notices.items[0].id=="seed" and notices.items[0].age==3.0 and notices.items[1].id=="older" and notices.items[1].age==3.0)
	var notice:=Notice.new()
	notice.hud=hud
	hud.phase=Hud.PH_LEVEL|Hud.PH_PAUSE_MENU
	notice.tick()
	piece.visible=notice.visible
	portal._update_notice_visibility()
	_check("production covered notice falls back to Portal",not notice.visible and notices.visible)
	_check("covered ownership preserves current card/deadline",notices.current().id=="seed" and notices.items[0].age==3.0 and notices.items[0].seconds==10.0 and notices.items[1].age==3.0)
	hud.phase=Hud.PH_LEVEL
	notice.tick()
	piece.visible=notice.visible
	portal._update_notice_visibility()
	_check("production uncovered notice owns same ID",notice.visible and not notices.visible)
	notice.free()
	piece.self_modulate.a=0.0
	portal._update_notice_visibility()
	_check("transparent piece self modulation falls back",notices.visible)
	piece.self_modulate.a=1.0
	piece.modulate.a=0.0
	portal._update_notice_visibility()
	_check("transparent piece modulation falls back",notices.visible)
	piece.modulate.a=1.0
	fade_root.modulate.a=0.0
	portal._update_notice_visibility()
	_check("transparent inherited root falls back",notices.visible)
	piece.set_as_top_level(true)
	portal._update_notice_visibility()
	_check("top-level notice does not inherit parent alpha",not notices.visible)
	piece.set_as_top_level(false)
	fade_root.modulate.a=1.0
	fade_root.self_modulate.a=0.0
	portal._update_notice_visibility()
	_check("parent self modulation does not hide child owner",not notices.visible)
	fade_root.self_modulate.a=1.0
	fade_root.modulate.a=0.5
	piece.modulate.a=0.5
	piece.self_modulate.a=0.5
	portal._update_notice_visibility()
	_check("positive effective notice alpha retains owner",not notices.visible)
	fade_root.modulate.a=1.0
	piece.modulate.a=1.0
	piece.self_modulate.a=1.0
	portal.draw_notices_in_game=true
	portal._update_notice_visibility()
	_check("explicit Portal renderer preserved",notices.visible)
	portal.draw_notices_in_game=false
	piece.visible=false
	portal._update_notice_visibility()
	_check("hidden HUD notice piece falls back to Portal",notices.visible)
	piece.visible=true
	hud.visible=false
	portal._update_notice_visibility()
	_check("hidden HUD layer falls back to Portal",notices.visible)
	hud.visible=true
	hud.set_process(false)
	portal._update_notice_visibility()
	_check("nonprocessing HUD falls back to Portal",notices.visible)
	hud.set_process(true)
	hud.process_mode=Node.PROCESS_MODE_DISABLED
	portal._update_notice_visibility()
	_check("disabled HUD falls back to Portal",notices.visible)
	hud.process_mode=Node.PROCESS_MODE_INHERIT
	portal.shown=true
	portal._update_notice_visibility()
	_check("shown Portal retains notice",notices.visible)
	screen.chrome_on=false
	portal._update_notice_visibility()
	_check("first question remains uninterrupted",not notices.visible)
	screen.chrome_on=true
	portal.shown=false
	game.hud_node=null
	portal._update_notice_visibility()
	_check("missing HUD falls back to Portal",notices.visible)
	game.hud_node=hud
	handover.game=null
	portal._update_notice_visibility()
	_check("missing game falls back to Portal",notices.visible)
	handover.game=game
	portal.handover=null
	portal._update_notice_visibility()
	_check("missing handover falls back to Portal",notices.visible)
	portal.handover=handover
	hud.queue_free()
	portal._update_notice_visibility()
	_check("queued HUD removal falls back to Portal",notices.visible)
	await process_frame
	await process_frame
	portal._update_notice_visibility()
	_check("freed HUD falls back without access error",not is_instance_valid(hud) and notices.visible)
	_check("accept callback identity retained",notices.accept_current() and count.count==1)
	notices._process(0.2)
	_check("accepted current removes only its card",notices.items.size()==1 and notices.current().id=="older" and count.count==1)
	_check("backlog original age/deadline retained",is_equal_approx(float(notices.items[0].age),3.2) and notices.items[0].seconds==20.0)
	_check("backlog dismiss preserves accept callback",notices.dismiss_current() and count.count==1)
	notices._process(0.2)
	_check("backlog dismissed once",notices.items.is_empty() and count.count==1)
	notices.push({"id":"expires","title":"Authored","seconds":4.0,"on_accept":count.accept})
	notices._process(3.0)
	portal._update_notice_visibility()
	_check("pending unowned card visible before expiry",notices.visible and notices.items[0].age==3.0)
	notices._process(1.01)
	notices._process(0.2)
	_check("original expiry and no callback retained",notices.items.is_empty() and count.count==1)
	var dismissed:=Counter.new()
	notices.push({"id":"dismiss","title":"Authored","on_accept":count.accept,"on_dismiss":dismissed.accept})
	portal._update_notice_visibility()
	_check("dismiss callback identity retained",notices.dismiss_current() and dismissed.count==1 and count.count==1)
	notices._process(0.2)
	_check("dismissed notice removed once",notices.items.is_empty() and dismissed.count==1)
	portal.free()
	notices.free()
	screen.free()
	handover.free()
	game.free()

func _initialize() -> void:
	_run.call_deferred()
func _run() -> void:
	_status_tests()
	await _notice_tests()
	print("HUD_PARTY_NOTICE_TEST ","PASS" if failures.is_empty() else "FAIL",": ",checks," checks; failures ",failures)
	quit(0 if failures.is_empty() else 1)
