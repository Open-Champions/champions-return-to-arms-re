extends RefCounted
# Two local controller owners. Idle virtual devices do not reserve a player;
# the first active device claims P1, the next claims P2. Keyboard is also P1.
# Keep P2 on its port while P1 disconnects, and reconnect a known device first.

const PORTS := 2
const TEST_DEVICES := [1001, 1002]
var owners := [-1, -1]
var preferred := [{}, {}]
var motors := {}


static func neutral(device := -1) -> Dictionary:
	return {"device": device, "buttons": 0, "sticks": [128, 128, 128, 128]}


static func sample(device: int, button_bits: Dictionary, l2: int, r2: int, dead_zone := 0.15, trigger_threshold := 0.30) -> Dictionary:
	var state := neutral(device)
	for button in button_bits:
		if Input.is_joy_button_pressed(device, button):
			state.buttons |= int(button_bits[button])
	if Input.get_joy_axis(device, JOY_AXIS_TRIGGER_LEFT) > trigger_threshold:
		state.buttons |= l2
	if Input.get_joy_axis(device, JOY_AXIS_TRIGGER_RIGHT) > trigger_threshold:
		state.buttons |= r2
	for stick in range(2):
		var axis_x: int = JOY_AXIS_LEFT_X if stick == 0 else JOY_AXIS_RIGHT_X
		var axis_y: int = JOY_AXIS_LEFT_Y if stick == 0 else JOY_AXIS_RIGHT_Y
		var value := Vector2(Input.get_joy_axis(device, axis_x), Input.get_joy_axis(device, axis_y))
		if value.length() > dead_zone:
			state.sticks[stick * 2] = clampi(int(round(128.0 + value.x * (128.0 if value.x < 0.0 else 127.0))), 0, 255)
			state.sticks[stick * 2 + 1] = clampi(int(round(128.0 + value.y * (128.0 if value.y < 0.0 else 127.0))), 0, 255)
	var connected := Input.get_connected_joypads().has(device)
	state["guid"] = Input.get_joy_guid(device) if connected else "scripted:%d" % device
	state["name"] = Input.get_joy_name(device) if connected else "scripted controller"
	return state


static func active(state: Dictionary) -> bool:
	return int(state.get("buttons", 0)) != 0 or state.get("sticks", [128, 128, 128, 128]) != [128, 128, 128, 128]


func _same_device(device: int, state: Dictionary, pin: Dictionary) -> bool:
	return device == int(pin.get("device", -1)) and String(state.get("guid", "")) == String(pin.get("guid", "")) \
		and String(state.get("name", "")) == String(pin.get("name", ""))


func _attach(port: int, device: int, state: Dictionary) -> void:
	owners[port] = device
	preferred[port] = {"device": device, "guid": String(state.get("guid", "")), "name": String(state.get("name", ""))}


func update(devices: Dictionary, enabled := true) -> Array:
	for port in range(PORTS):
		var device: int = owners[port]
		if device >= 0 and (not devices.has(device) or not _same_device(device, devices[device], preferred[port])):
			owners[port] = -1
	# Preferred reconnects precede new claims, so an idle returning P1 is not
	# replaced by a different active device in the same sample.
	for port in range(PORTS):
		var device := int(preferred[port].get("device", -1))
		if owners[port] < 0 and devices.has(device) and not owners.has(device) and _same_device(device, devices[device], preferred[port]):
			_attach(port, device, devices[device])
	if enabled:
		var ids: Array = devices.keys()
		ids.sort()
		for device in ids:
			if owners.has(device) or not active(devices[device]):
				continue
			var port := owners.find(-1)
			if port >= 0:
				_attach(port, device, devices[device])
	var result := []
	for port in range(PORTS):
		var device: int = owners[port]
		var state: Dictionary = devices[device].duplicate(true) if enabled and devices.has(device) else neutral(device)
		state["device"] = device
		result.append(state)
	return result


func apply_rumble(requested: Dictionary, start: Callable, stop: Callable) -> void:
	var next := {}
	for device in requested:
		var value := Vector2(requested[device]).clamp(Vector2.ZERO, Vector2.ONE)
		if value != Vector2.ZERO:
			next[device] = value
	for device in motors:
		if not next.has(device):
			stop.call(device)
	for device in next:
		if not motors.has(device) or motors[device] != next[device]:
			start.call(device, next[device].x, next[device].y)
	motors = next
