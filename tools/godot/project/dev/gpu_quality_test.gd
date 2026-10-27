extends SceneTree
const Quality := preload("res://gpu_quality.gd")

func _initialize() -> void:
	var q := Quality.new()
	q.configure(4)
	for k in 180:
		q.update(9.0, 1.0 / 60.0, true, 1000.0 / 120.0)
	assert(q.rung == 0 and not q.between, "Preserve native 4x when 60 fits; hold expensive tweens")
	for k in 90:
		q.update(20.0, 1.0 / 60.0, true, 1000.0 / 120.0)
	assert(q.quality() == Vector2(2, 1), "Reduce AA before resolution")
	var severe := Quality.new()
	severe.configure(4)
	for k in 180:
		severe.update(30.0, 1.0 / 60.0, true, 1000.0 / 120.0)
	assert(severe.quality() == Vector2(0, 1), "Preserve native pixels before the scaling fallback")
	var held := q.rung
	for k in 900:
		q.update(40.0, 1.0 / 60.0, false, 1000.0 / 120.0)
	assert(q.rung == held, "No quality changes during a fade or load")
	for k in 900:
		q.update(0.0, 1.0 / 60.0, true, 1000.0 / 120.0)
	assert(q.rung == held, "Unavailable timestamps cannot restore quality")
	for k in 120:
		q.update(5.0, 1.0 / 60.0, true, 1000.0 / 120.0)
	assert(q.rung == held, "No early rebound")
	for k in 600:
		q.update(5.0, 1.0 / 60.0, true, 1000.0 / 120.0)
	assert(q.rung == 0 and q.between, "Restore quality and tweens with sustained headroom")
	for k in 1800:
		q.update(40.0, 1.0 / 60.0, true, 1000.0 / 120.0)
	assert(q.quality() == Vector2(0, 0.75), "Bound the quality floor")
	q.configure(2)
	assert(q.quality() == Vector2(2, 1), "Honor explicit AA preference")
	for k in 900:
		q.update(NAN, 1.0 / 60.0, true, 1000.0 / 120.0)
	assert(q.rung == 0, "Reject invalid GPU samples")
	q.configure(8)
	for k in 1800:
		q.update(40.0, 1.0 / 60.0, true, 1000.0 / 120.0)
	for k in 600:
		q.update(3.0, 1.0 / 60.0, true, 1000.0 / 120.0)
	assert(q.quality() == Vector2(2, 1), "Restoration must account for every AA doubling from no MSAA")
	print("GPU_QUALITY_TEST PASS: budget, redraws, AA order, fade freeze, invalid samples, hysteresis, restoration, bounds")
	quit(0)
