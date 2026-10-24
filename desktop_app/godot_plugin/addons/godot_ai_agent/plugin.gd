@tool
extends EditorPlugin

## Godot AI Agent Connector Plugin
## Automatically registers this active project with the Godot AI Agent Desktop IDE
## through authenticated localhost HTTP endpoint.

const SERVER_URL = "http://127.0.0.1:8000/api/project/register"
const RETRY_INTERVAL = 10.0

var http_client: HTTPRequest
var timer: Timer
var auth_token: String = ""
var is_registered: bool = false


func _enter_tree() -> void:
	print("[Godot AI Agent] Initializing connector plugin...")
	_load_auth_token()

	http_client = HTTPRequest.new()
	http_client.request_completed.connect(_on_request_completed)
	add_child(http_client)

	timer = Timer.new()
	timer.wait_time = RETRY_INTERVAL
	timer.autostart = true
	timer.timeout.connect(_on_timer_timeout)
	add_child(timer)

	# Register immediately on startup
	call_deferred("_register_project")


func _exit_tree() -> void:
	print("[Godot AI Agent] Connector plugin disabled.")
	if timer:
		timer.stop()
		timer.queue_free()
	if http_client:
		http_client.queue_free()


func _load_auth_token() -> void:
	# 1. Check user home folder token
	var home = OS.get_environment("HOME")
	if home.is_empty():
		home = OS.get_environment("USERPROFILE")
	var token_path = home.path_join(".godot_ai_agent").path_join("auth_token.txt")

	if FileAccess.file_exists(token_path):
		var file = FileAccess.open(token_path, FileAccess.READ)
		if file:
			auth_token = file.get_as_text().strip_edges()
			file.close()

	if auth_token.is_empty():
		push_warning("[Godot AI Agent] Auth token not found in " + token_path + ". Run the Desktop IDE to generate one.")


func _register_project() -> void:
	if auth_token.is_empty():
		_load_auth_token()
		if auth_token.is_empty():
			return

	var abs_project_path = ProjectSettings.globalize_path("res://")
	# Clean trailing slash
	if abs_project_path.ends_with("/"):
		abs_project_path = abs_project_path.left(abs_project_path.length() - 1)

	var proj_name = ProjectSettings.get_setting("application/config/name", "")
	if proj_name.is_empty():
		proj_name = abs_project_path.get_file()

	var version_info = Engine.get_version_info()
	var godot_ver = version_info.get("string", "Godot 4.x")
	var godot_exe = OS.get_executable_path()

	var payload = {
		"project_path": abs_project_path,
		"project_name": proj_name,
		"godot_version": godot_ver,
		"godot_executable": godot_exe
	}

	var json_body = JSON.stringify(payload)
	var headers = [
		"Content-Type: application/json",
		"X-Agent-Token: " + auth_token
	]

	var error = http_client.request(SERVER_URL, headers, HTTPClient.METHOD_POST, json_body)
	if error != OK:
		# Server might not be running yet, silent wait
		pass


func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	if response_code == 200:
		if not is_registered:
			is_registered = true
			print("[Godot AI Agent] ✓ Active project successfully registered with AI Desktop IDE!")
	elif response_code == 401:
		push_warning("[Godot AI Agent] Authentication rejected by AI Desktop IDE. Verify ~/.godot_ai_agent/auth_token.txt.")
		is_registered = false
	else:
		is_registered = false


func _on_timer_timeout() -> void:
	# Keep alive & re-register if server restarted
	_register_project()
