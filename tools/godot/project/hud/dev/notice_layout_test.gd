extends SceneTree
# Authored dimensions/state only: test the exact rectangle used by draw_notice.
const Top := preload("res://hud/top.gd")
const Hud := preload("res://hud/hud.gd")
var checks := 0
var failures: Array[String] = []

class FakeHud extends Node:
	var s := 1.0
	var picture := Rect2(0, 0, 1920, 1080)
	var area := Rect2(27, 27, 1866, 1026)
	var layout := 0
	var setting := {"mode": "original", "radar": true}
	var show := 0.0
	var ok := true
	var phase := 2
	var frame := {"player_count": 2}

func _check(label: String, value: bool) -> void:
	checks += 1
	if not value:
		failures.append(label)

func _native_panel(picture: Rect2) -> Rect2:
	# Independent conservative envelope of the native top-right player panel:
	# right30% of the picture, y4%-18%. It is unrelated to custom HUD/font scale.
	return Rect2(picture.position + Vector2(0.70 * picture.size.x, 0.04 * picture.size.y), Vector2(0.30 * picture.size.x, 0.14 * picture.size.y))

func _initialize() -> void:
	var hud := FakeHud.new()
	for height in [540.0, 1080.0]:
		for picture in [Rect2(0, 0, height*16.0/9.0, height),
			Rect2(height*2.0/9.0, 0, height*4.0/3.0, height),
			Rect2(0, height*0.125, height*16.0/9.0, height*0.75)]:
			hud.picture=picture
			var margin := maxf(12.0, 0.025*picture.size.y)
			var content_w := minf(picture.size.x, picture.size.y*2.0)
			hud.area=Rect2(picture.position+Vector2((picture.size.x-content_w)*0.5+margin,margin),Vector2(content_w-2.0*margin,picture.size.y-2.0*margin))
			for scale in [0.5, 1.0, 2.0]:
				hud.s=maxf(0.74, picture.size.y/1080.0)*scale
				for age in [0.0, 0.15, 0.5]:
					var rect := Top.notice_rect(hud, age)
					var label := "%s/%s/%s/%s" % [height, picture, scale, age]
					_check("native panel remains clear " + label, not rect.intersects(_native_panel(picture)))
					if age == 0.5:
						_check("settled card inside game picture " + label, picture.encloses(rect))
	# Exact pre-change placements: right entrance (40px, then5px, then0)
	# and166px overhead radar reserve at design scale1. Original one-player,
	# the new HUD, and both-mode retain those same coordinates.
	hud.picture=Rect2(0, 0, 1920, 1080)
	hud.area=Rect2(27, 27, 1866, 1026)
	hud.s=1.0
	var ages := [0.0, 0.15, 0.5]
	var old_x := [1583.0, 1548.0, 1543.0]
	for mode in ["new", "both", "original"]:
		hud.setting.mode=mode
		hud.frame={"player_count":1 if mode=="original" else 2}
		for layout in [Hud.LAYOUT_OVERHEAD, Hud.LAYOUT_THIRD, Hud.LAYOUT_FIRST]:
			hud.layout=layout
			for radar in [false, true]:
				hud.setting.radar=radar
				for show in [0.0, 1.0]:
					hud.show=show
					var y := 193.0 if layout==Hud.LAYOUT_OVERHEAD and radar and show>0.0 else 27.0
					for index in range(ages.size()):
						_check("prior entrance/radar %s/%s/%s/%s/%s" % [mode, layout, radar, show, index], Top.notice_rect(hud, ages[index]) == Rect2(old_x[index], y, 350, 86))
	# Native reserve has precise mode/state/count boundaries, independent of show0.
	hud.setting={"mode":"original", "radar":false}
	hud.layout=Hud.LAYOUT_OVERHEAD
	hud.show=0.0
	hud.frame={"player_count":2}
	_check("Classic two-player show0 reserves native HUD", Top.notice_rect(hud, 0.5)==Rect2(1543,216,350,86))
	hud.frame={"player_count":4}
	_check("Classic larger party keeps native reserve", Top.notice_rect(hud, 0.5)==Rect2(1543,216,350,86))
	for count in [0, 1]:
		hud.frame={"player_count":count}
		_check("count boundary %d"%count, Top.notice_rect(hud,0.5)==Rect2(1543,27,350,86))
	hud.frame={}
	_check("unknown player count retains prior layout", Top.notice_rect(hud,0.5)==Rect2(1543,27,350,86))
	hud.frame={"player_count":2}
	hud.ok=false
	_check("no live state retains prior layout", Top.notice_rect(hud,0.5)==Rect2(1543,27,350,86))
	hud.ok=true
	for phase in [0,Hud.PH_FRONTEND,Hud.PH_LOADING]:
		hud.phase=phase
		_check("outside level phase %d"%phase, Top.notice_rect(hud,0.5)==Rect2(1543,27,350,86))
	hud.free()
	print("HUD_NOTICE_LAYOUT_TEST ", "PASS" if failures.is_empty() else "FAIL", ": ", checks, " checks; failures ", failures)
	quit(0 if failures.is_empty() else 1)
