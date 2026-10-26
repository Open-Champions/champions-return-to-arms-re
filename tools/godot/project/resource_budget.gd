extends RefCounted
# Main-thread resource uploads share a budget per rendered frame, including when several figures ask for them.
# An engine call cannot be interrupted; after one takes the budget the next waits for another frame.
const USEC := 4000
static var frame := -1
static var spent := 0


static func begin() -> int:
	var now := Engine.get_process_frames()
	if frame != now:
		frame = now
		spent = 0
	return Time.get_ticks_usec() if spent < USEC else -1


static func end(started: int) -> void:
	spent += Time.get_ticks_usec() - started
