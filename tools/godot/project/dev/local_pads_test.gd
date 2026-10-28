extends SceneTree
# Authored ownership and real Godot InputEvent sampling, no game or device needed.
# Godot --headless --path PROJECT --script res://dev/local_pads_test.gd
const Pads := preload("res://local_pads.gd")
var checks := 0
var failures := 0
var output := []


func start_motor(device: int, weak: float, strong: float) -> void:
	output.append(["start", device, weak, strong])


func stop_motor(device: int) -> void:
	output.append(["stop", device])


func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		printerr("local_pads: FAIL ", label)


func state(bits := 0, sticks := [128, 128, 128, 128], guid := "xbox") -> Dictionary:
	return {"buttons": bits, "sticks": sticks.duplicate(), "guid": guid, "name": "authored pad"}


func _initialize() -> void:
	var pads := Pads.new()
	var devices := {0: state(), 1: state(), 2: state()}
	var result := pads.update(devices)
	check(pads.owners == [-1, -1], "idle virtual devices do not claim ports")
	devices[2] = state(0x4000)
	result = pads.update(devices)
	check(pads.owners == [2, -1] and result[0].buttons == 0x4000, "higher active device becomes P1")
	devices[1] = state(0x2000, [128, 255, 128, 128])
	result = pads.update(devices)
	check(pads.owners == [2, 1], "next active device becomes P2")
	check(result[0].buttons == 0x4000 and result[1].buttons == 0x2000, "buttons stay independent")
	check(result[0].sticks == [128, 128, 128, 128] and result[1].sticks[1] == 255, "sticks stay independent")
	devices[0] = state(0x8000)
	pads.update(devices)
	check(pads.owners == [2, 1], "third device cannot steal either port")
	devices.erase(2)
	devices[0] = state()
	result = pads.update(devices)
	check(pads.owners == [-1, 1] and result[0].buttons == 0 and result[1].buttons == 0x2000, "P2 is not promoted after P1 disconnects")
	devices[2] = state()
	pads.update(devices)
	check(pads.owners == [2, 1], "preferred P1 reconnects without a new press")
	result = pads.update(devices, false)
	check(result[0].buttons == 0 and result[1].buttons == 0 and result[1].sticks == [128, 128, 128, 128], "held/background input releases both ports")
	check(pads.owners == [2, 1], "temporary hold preserves ownership")
	var unclaimed := Pads.new()
	unclaimed.update({7: state(0x4000)}, false)
	check(unclaimed.owners == [-1, -1], "background activity cannot claim a port")
	devices[2] = state(0, [128, 128, 128, 128], "new device")
	pads.update(devices)
	check(pads.owners == [-1, 1], "recycled device ID with another identity is not an idle reconnect")
	devices[2].buttons = 0x4000
	pads.update(devices)
	check(pads.owners == [2, 1], "new identity may claim a vacant port through activity")
	var snapshot := devices.duplicate(true)
	pads.update(devices)
	check(devices == snapshot, "sampling leaves source states untouched")
	# Feed the real Input singleton; test IDs cannot collide with a physical device.
	var event := InputEventJoypadButton.new()
	event.device = Pads.TEST_DEVICES[0]
	event.button_index = JOY_BUTTON_A
	event.pressed = true
	Input.parse_input_event(event.duplicate())
	var motion := InputEventJoypadMotion.new()
	motion.device = Pads.TEST_DEVICES[0]
	motion.axis = JOY_AXIS_LEFT_X
	motion.axis_value = 0.10
	Input.parse_input_event(motion.duplicate())
	Input.flush_buffered_events()
	var sampled := Pads.sample(Pads.TEST_DEVICES[0], {JOY_BUTTON_A: 0x4000}, 0x100, 0x200)
	check(sampled.buttons == 0x4000, "production sampler receives a Godot button event")
	check(sampled.sticks == [128, 128, 128, 128], "small drift stays neutral")
	motion.axis_value = -1.0
	Input.parse_input_event(motion.duplicate())
	Input.flush_buffered_events()
	sampled = Pads.sample(Pads.TEST_DEVICES[0], {JOY_BUTTON_A: 0x4000}, 0x100, 0x200)
	check(sampled.sticks[0] == 0, "left stick endpoint maps through production sampler")
	motion.axis = JOY_AXIS_TRIGGER_RIGHT
	motion.axis_value = 0.8
	Input.parse_input_event(motion.duplicate())
	Input.flush_buffered_events()
	sampled = Pads.sample(Pads.TEST_DEVICES[0], {JOY_BUTTON_A: 0x4000}, 0x100, 0x200)
	check(sampled.buttons == 0x4200, "trigger is independent of face button")
	check(Pads.sample(Pads.TEST_DEVICES[1], {JOY_BUTTON_A: 0x4000}, 0x100, 0x200).buttons == 0, "synthetic ports are isolated in Godot Input")
	event.pressed = false
	Input.parse_input_event(event.duplicate())
	motion.axis_value = 0.0
	Input.parse_input_event(motion.duplicate())
	Input.flush_buffered_events()
	pads.apply_rumble({2: Vector2(1.0, 0.5), 1: Vector2(0.0, 0.25)}, start_motor, stop_motor)
	check(output == [["start", 2, 1.0, 0.5], ["start", 1, 0.0, 0.25]], "both device motors receive independent amplitudes")
	output.clear()
	pads.apply_rumble({2: Vector2(1.0, 0.5), 1: Vector2(0.0, 0.25)}, start_motor, stop_motor)
	check(output.is_empty(), "unchanged infinite-duration motors are not restarted")
	pads.apply_rumble({1: Vector2(0.0, 0.25)}, start_motor, stop_motor)
	check(output == [["stop", 2]], "detaching P1 stops only its output")
	output.clear()
	pads.apply_rumble({}, start_motor, stop_motor)
	check(output == [["stop", 1]] and pads.motors.is_empty(), "focus/hold/shutdown release remaining output")
	output.clear()
	pads.apply_rumble({}, start_motor, stop_motor)
	check(output.is_empty(), "release is idempotent")
	pads.apply_rumble({4: Vector2(-1.0, 2.0)}, start_motor, stop_motor)
	check(output == [["start", 4, 0.0, 1.0]], "output clamps amplitudes")
	print("local_pads: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)
