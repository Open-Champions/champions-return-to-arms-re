extends SceneTree
# Execute the real patched production host branch without putting that host in the tree.
# Its _ready/start/render/input paths never run. The native machine remains unstarted.
class DrawerSpy:
	extends RefCounted
	var text: String = ""
	var calls: int = 0
	func figures() -> String:
		calls += 1
		return text

var output: String = ""
var checks: Array = []

func _initialize() -> void:
	_run.call_deferred()

func _check(condition: bool, label: String) -> void:
	checks.append({"passed":condition,"label":label})
	if not condition: printerr("snapshot command FAIL: ",label)

func _state(host: Node) -> Dictionary:
	var names: Array = ["blanks","started","machine_stopped","clock","process_usec","draw_usec","quitting","key_events","input_held","frame_rows","pending_shots","window_shots"]
	var state: Dictionary = {}
	for key in names: state[key]=host.get(key)
	return state.duplicate(true)

func _snapshot(host: Node, path: String) -> Dictionary:
	var before: Dictionary = _state(host)
	host.call("_host_command","drawer-figures "+path)
	_check(_state(host)==before,"snapshot preserves unrelated host state: "+path.get_file())
	_check(FileAccess.file_exists(path),"snapshot file exists: "+path.get_file())
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_check(parsed is Dictionary,"snapshot valid JSON dictionary: "+path.get_file())
	return parsed if parsed is Dictionary else {}

func _run() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size()!=2 or args[0]!="--out":
		printerr("expected --out PRIVATE_DIRECTORY")
		quit(2)
		return
	output=args[1]
	_check(DisplayServer.get_name()=="headless","headless display only")
	var host_script: Script = load("res://main.gd")
	var host: Node = host_script.new()
	_check(not host.is_inside_tree(),"production host never added to tree")
	_check(not bool(host.get("started")),"production machine not started")
	var machine: RtaMachine = RtaMachine.new()
	_check(machine.get_frame_number()==-1,"real native machine unstarted frame is -1")
	var spy: DrawerSpy = DrawerSpy.new()
	spy.text="drawer: 17 lists; big draws written in place 19, made 3; quoted \"fixture\"\nUTF8 é"
	var sentinel: String = output.path_join("null sentinel.json")
	var file: FileAccess = FileAccess.open(sentinel,FileAccess.WRITE)
	file.store_string("unchanged sentinel")
	file.close()
	host.set("drawer",spy)
	host.call("_host_command","drawer-figures "+sentinel)
	_check(FileAccess.get_file_as_string(sentinel)=="unchanged sentinel" and spy.calls==0,"null machine does not open/overwrite file or call formatter")
	host.set("machine",machine)
	host.set("drawer",null)
	var null_drawer_path: String = output.path_join("null drawer.json")
	host.call("_host_command","drawer-figures "+null_drawer_path)
	_check(not FileAccess.file_exists(null_drawer_path),"null drawer creates no file")
	host.set("drawer",spy)
	host.set("blanks",411)
	var first: Dictionary = _snapshot(host,output.path_join("before snapshot with spaces.json"))
	var keys: Array = first.keys()
	keys.sort()
	_check(keys==["current_native_frame","drawer_figures","drawer_instance_id","host_blank","schema"],"exact schema field set")
	_check(first.get("schema")==1 and first.get("host_blank")==411 and first.get("current_native_frame")==-1,"separate host blank/current native metadata")
	_check(first.get("drawer_instance_id")==str(spy.get_instance_id()) and first.get("drawer_instance_id") is String,"exact decimal instance ID string")
	_check(first.get("drawer_figures")==spy.text and spy.calls==1,"raw formatter text preserved and called exactly once")
	spy.text="drawer: 23 lists; big draws written in place 21, made 3"
	host.set("blanks",1019)
	var second: Dictionary = _snapshot(host,output.path_join("after snapshot.json"))
	_check(second.get("drawer_instance_id")==first.get("drawer_instance_id"),"same live drawer preserves instance identity")
	_check(second.get("drawer_figures")==spy.text and second.get("host_blank")==1019 and spy.calls==2,"second snapshot reads current cumulative text only once")
	_check(second.get("current_native_frame")==-1 and machine.get_frame_number()==-1,"snapshot does not step or start machine")
	var relative: Dictionary = _snapshot(host,"drawer-figures relative file with spaces.json")
	_check(relative.get("drawer_figures")==spy.text and relative.get("drawer_instance_id")==str(spy.get_instance_id()) and spy.calls==3,"relative filename starting with command token uses argument tail only")
	var calls_before: int = spy.calls
	host.call("_host_command","drawer-figures "+output.path_join("missing parent/snapshot.json"))
	_check(spy.calls==calls_before and not FileAccess.file_exists(output.path_join("missing parent/snapshot.json")),"failed file open does not call formatter")
	var other: DrawerSpy = DrawerSpy.new()
	other.text=spy.text
	host.set("drawer",other)
	var replaced: Dictionary = _snapshot(host,output.path_join("new drawer.json"))
	_check(replaced.get("drawer_instance_id")==str(other.get_instance_id()) and replaced.get("drawer_instance_id")!=first.get("drawer_instance_id"),"replacement drawer has a distinct identity even with identical figures")
	_check(replaced.get("drawer_figures")==other.text and other.calls==1,"replacement drawer reads its own formatter")
	var previous_rows: int = (host.get("frame_rows") as PackedStringArray).size()
	host.call("_host_command","mark AUTHORED_EXISTING_COMMAND")
	var rows: PackedStringArray = host.get("frame_rows")
	_check(rows.size()==previous_rows+1 and rows[rows.size()-1]=="M,1019,AUTHORED_EXISTING_COMMAND","existing mark command still behaves normally")
	_check(other.calls==1,"unrelated command does not invoke new formatter")
	_check(not host.is_inside_tree() and not bool(host.get("started")),"host and machine remain outside active game flow")
	host.set("drawer",null)
	host.set("machine",null)
	host.free()
	var passed: bool = true
	for check in checks: passed=passed and check.passed
	var result: Dictionary = {"passed":passed,"scope":"Authored headless exercise of real patched main._host_command with fake formatter and real unstarted RtaMachine. No host _ready, game, disc, GPU or renderer path.","checks":checks,"native_frame":machine.get_frame_number(),"first":first,"second":second,"replacement":replaced}
	file=FileAccess.open(output.path_join("authored-result.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(result,"  ")+"\n")
	file.close()
	print("snapshot command ","PASS" if passed else "FAIL"," checks=",checks.size())
	quit(0 if passed else 1)
