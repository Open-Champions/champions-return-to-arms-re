extends RefCounted
# Presentation-only controller. Inputs are completed GPU work, never FPS or the
# simulation clock. Keep requested quality until sustained pressure, then prefer
# 2x AA at native resolution to resampling the whole picture. If that still does
# not fit, native pixels without MSAA preserve more detail than a scaled image.
const BUDGET_MS := 14.0                 # leave time for handoff/display in a 16.67 ms game frame
const ACUTE := 1.3                     # ema over BUDGET_MS x this: a sudden overload (see update)
const SCALES := [1.0, 0.95, 0.90, 0.85, 0.80, 0.75]
var levels: Array[Vector2] = []         # samples, render scale (relative to requested scale)
var rung := 0
var ema := -1.0
var high_for := 0.0
var low_for := 0.0
var cool_for := 0.0
var between_low_for := 0.0
var between := true

func configure(samples: int) -> void:
	samples = 8 if samples >= 8 else (4 if samples >= 4 else (2 if samples >= 2 else 0))
	levels.clear()
	levels.append(Vector2(samples, 1.0))
	if samples >= 8:
		levels.append(Vector2(4, 1.0))
	if samples >= 4:
		levels.append(Vector2(2, 1.0))
	if samples >= 2:
		levels.append(Vector2(0, 1.0))
	for scale in SCALES.slice(1):
		levels.append(Vector2(0, scale))
	rung = 0
	reset_observations()
	between = true

func reset_observations() -> void:
	ema = -1.0
	high_for = 0.0
	low_for = 0.0
	between_low_for = 0.0
	cool_for = 0.5

# A new level starts from the requested quality again: what the level before could not afford says nothing of this
# one (the steps down are quick, the way back up takes long seconds of headroom)
func new_level() -> bool:
	reset_observations()
	if rung == 0:
		return false
	rung = 0
	return true

func quality() -> Vector2:
	return levels[rung] if not levels.is_empty() else Vector2(4, 1.0)

func _cost_ratio(better: Vector2, current: Vector2) -> float:
	# The repeated Metal trace measured 4x/2x at about 1.17-1.20; allow
	# 1.35 when predicting restoration. Other doublings retain more headroom.
	var aa := 1.0
	var samples := maxi(1, int(current.x))
	while samples < int(better.x):
		aa *= 1.35 if samples == 2 else 1.8
		samples *= 2
	return aa * pow(better.y / current.y, 2.0)

func update(gpu_ms: float, elapsed: float, safe: bool, refresh_ms: float) -> bool:
	if not safe:
		reset_observations()
		return false
	if not is_finite(gpu_ms) or gpu_ms <= 0.0 or levels.is_empty():
		return false                     # unsupported/stale timings are not spare GPU capacity
	var dt := clampf(elapsed, 0.0, 0.1)
	ema = gpu_ms if ema < 0.0 else lerpf(ema, gpu_ms, 1.0 - exp(-dt / 0.25))
	cool_for = maxf(0.0, cool_for - dt)
	# A tween draws the full world again. Reserve that work only when it fits a
	# refresh with 20% headroom; restoring it requires two seconds below 65%.
	if ema > refresh_ms * 0.8:
		between = false
		between_low_for = 0.0
	elif ema < refresh_ms * 0.65:
		between_low_for += dt
		if between_low_for >= 2.0:
			between = true
	else:
		between_low_for = 0.0
	if cool_for > 0.0:
		return false
	high_for = high_for + dt if ema > BUDGET_MS else 0.0
	# Far over budget (a cloud of the game's sprites at the eye, a level's heavy opening): straight to native pixels
	# without MSAA - the rung the steps below would reach anyway - instead of a second and a half at each step
	if high_for >= 0.2 and ema > BUDGET_MS * ACUTE and rung + 1 < levels.size():
		var to := rung + 1
		while to + 1 < levels.size() and levels[to].x > 0.0:
			to += 1
		rung = to
		high_for = 0.0
		low_for = 0.0
		cool_for = 1.0
		return true
	if high_for >= 0.4 and rung + 1 < levels.size():
		rung += 1
		high_for = 0.0
		low_for = 0.0
		cool_for = 1.5                  # discard delayed old-target samples and reallocation transients
		return true
	if rung > 0:
		var current := quality()
		var next := levels[rung - 1]
		var ratio := _cost_ratio(next, current)
		low_for = low_for + dt if ema * ratio < 11.5 else 0.0
		if low_for >= 8.0:
			# A light level should not spend a minute climbing through every scale.
			# After the same long hysteresis, restore the best predicted safe rung
			# in one allocation. The MSAA estimate stays deliberately conservative.
			var restore := rung - 1
			while restore > 0:
				var better := levels[restore - 1]
				var predicted := ema * _cost_ratio(better, current)
				if predicted >= 11.5:
					break
				restore -= 1
			rung = restore
			low_for = 0.0
			high_for = 0.0
			cool_for = 2.0
			return true
	return false
