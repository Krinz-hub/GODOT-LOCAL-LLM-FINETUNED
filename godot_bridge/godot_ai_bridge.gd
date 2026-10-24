# Godot AI Agent Bridge (godot_ai_bridge.gd)
# Attach this script to a Node in your Godot project to interact with the local AI Agent.
class_name GodotAIBridge
extends Node

signal action_received(action)
signal action_applied(success, path)
signal chat_completed(response)
signal scene_created(success, path, details)
signal scene_edited(success, path, details)
signal scene_deleted(success, path, details)
signal scene_read(success, path, content)
signal request_failed(error_message)

export var server_url: String = "http://127.0.0.1:8000"
export var auto_apply_actions: bool = false
export var session_id: String = "godot_editor_session"


func _ready() -> void:
	pass


## Creates a new Godot scene (.tscn) through the local AI Agent server
func create_scene(
	scene_path: String,
	root_node_type: String = "Node2D",
	root_node_name: String = "",
	content: String = "",
	script_path: String = "",
	overwrite: bool = false,
	project_path: String = ""
) -> void:
	var proj_path = project_path if not project_path.empty() else ProjectSettings.globalize_path("res://")
	var payload = {
		"project_path": proj_path,
		"file_path": scene_path,
		"root_node_type": root_node_type,
		"root_node_name": root_node_name,
		"content": content,
		"script_path": script_path,
		"overwrite": overwrite,
		"session_id": session_id
	}
	_post_json("/v1/scene/create", payload, "scene_create")


## Edits an existing Godot scene (.tscn) with raw content or structured modifications
func edit_scene(
	scene_path: String,
	content: String = "",
	add_nodes: Array = [],
	remove_nodes: Array = [],
	attach_script: Dictionary = {},
	project_path: String = ""
) -> void:
	var proj_path = project_path if not project_path.empty() else ProjectSettings.globalize_path("res://")
	var payload = {
		"project_path": proj_path,
		"file_path": scene_path,
		"content": content,
		"add_nodes": add_nodes,
		"remove_nodes": remove_nodes,
		"attach_script": attach_script,
		"session_id": session_id
	}
	_post_json("/v1/scene/edit", payload, "scene_edit")


## Safely deletes a Godot scene (.tscn) from the project
func delete_scene(scene_path: String, project_path: String = "") -> void:
	var proj_path = project_path if not project_path.empty() else ProjectSettings.globalize_path("res://")
	var payload = {
		"project_path": proj_path,
		"file_path": scene_path,
		"session_id": session_id
	}
	_post_json("/v1/scene/delete", payload, "scene_delete")


## Reads and retrieves a Godot scene (.tscn) content from the project
func get_scene(scene_path: String, project_path: String = "") -> void:
	var proj_path = project_path if not project_path.empty() else ProjectSettings.globalize_path("res://")
	var endpoint = "/v1/scene?file_path=" + scene_path.http_escape() + "&project_path=" + proj_path.http_escape()
	_get_json(endpoint, "scene_read")


## Send a natural language prompt to the local AI to decide and execute a Godot action
func request_action(prompt: String, project_context: String = "") -> void:
	var payload = {
		"prompt": prompt,
		"project_context": project_context,
		"session_id": session_id
	}
	_post_json("/v1/action", payload, "action")


## Send a regular chat request to get code advice, explanation, or planning
func request_chat(prompt: String) -> void:
	var payload = {
		"prompt": prompt,
		"session_id": session_id
	}
	_post_json("/v1/chat", payload, "chat")


## Applies an action received from the local AI agent to the local Godot project files (res://)
func apply_action(action: Dictionary) -> bool:
	var action_type = action.get("action_type", "")
	var params = action.get("parameters", {})

	if action_type in ["create_or_update_script", "create_or_update_scene", "create_scene", "edit_scene"]:
		var rel_path = params.get("file_path", "")
		var content = params.get("content", "")

		if rel_path.empty():
			push_error("[GodotAIBridge] Action missing 'file_path'")
			emit_signal("action_applied", false, "")
			return false

		var full_path = "res://" + rel_path.trim_prefix("res://")

		# If creating a scene without explicit content, synthesize basic Godot 3 scene
		if content.empty() and (action_type == "create_scene" or rel_path.ends_with(".tscn")):
			var root_type = params.get("root_node_type", "Node2D")
			var root_name = params.get("root_node_name", rel_path.get_file().get_basename())
			if root_name.empty():
				root_name = "Root"
			content = "[gd_scene format=2]\n\n[node name=\"%s\" type=\"%s\"]\n" % [root_name, root_type]

		# Ensure target directory exists
		var dir_path = full_path.get_base_dir()
		var dir = Directory.new()
		if not dir.dir_exists(dir_path):
			dir.make_dir_recursive(dir_path)

		var file = File.new()
		var err = file.open(full_path, File.WRITE)
		if err != OK:
			push_error("[GodotAIBridge] Could not write file: %s (Error: %d)" % [full_path, err])
			emit_signal("action_applied", false, full_path)
			return false

		file.store_string(content)
		file.close()
		print("[GodotAIBridge] Successfully wrote: ", full_path)
		emit_signal("action_applied", true, full_path)

		if action_type == "create_scene":
			emit_signal("scene_created", true, full_path, action)
		elif action_type == "edit_scene":
			emit_signal("scene_edited", true, full_path, action)
		return true

	elif action_type == "delete_scene":
		var rel_path = params.get("file_path", "")
		if rel_path.empty():
			push_error("[GodotAIBridge] Action missing 'file_path'")
			emit_signal("action_applied", false, "")
			return false

		var full_path = "res://" + rel_path.trim_prefix("res://")
		var dir = Directory.new()
		if not dir.file_exists(full_path):
			push_error("[GodotAIBridge] Scene file does not exist: " + full_path)
			emit_signal("action_applied", false, full_path)
			return false

		var err = dir.remove(full_path)
		if err != OK:
			push_error("[GodotAIBridge] Failed to delete scene: %s (Error: %d)" % [full_path, err])
			emit_signal("action_applied", false, full_path)
			return false

		print("[GodotAIBridge] Successfully deleted: ", full_path)
		emit_signal("action_applied", true, full_path)
		emit_signal("scene_deleted", true, full_path, action)
		return true

	elif action_type == "chat_response":
		var msg = params.get("message", "")
		print("[GodotAIBridge] Assistant: ", msg)
		emit_signal("chat_completed", msg)
		return true

	push_warning("[GodotAIBridge] Unhandled local action_type: " + action_type)
	return false


func _post_json(endpoint: String, data: Dictionary, request_type: String) -> void:
	var http_req = HTTPRequest.new()
	add_child(http_req)
	http_req.connect("request_completed", self, "_on_http_completed", [http_req, request_type])

	var url = server_url + endpoint
	var json_str = JSON.print(data)
	var headers = PoolStringArray([
		"Content-Type: application/json",
		"X-Request-Type: " + request_type
	])

	var err = http_req.request(url, headers, true, HTTPClient.METHOD_POST, json_str)
	if err != OK:
		var err_msg = "HTTP POST failed to start for %s: Error code %d" % [request_type, err]
		push_error("[GodotAIBridge] " + err_msg)
		emit_signal("request_failed", err_msg)
		http_req.queue_free()


func _get_json(endpoint: String, request_type: String) -> void:
	var http_req = HTTPRequest.new()
	add_child(http_req)
	http_req.connect("request_completed", self, "_on_http_completed", [http_req, request_type])

	var url = server_url + endpoint
	var headers = PoolStringArray([
		"Accept: application/json",
		"X-Request-Type: " + request_type
	])

	var err = http_req.request(url, headers, true, HTTPClient.METHOD_GET)
	if err != OK:
		var err_msg = "HTTP GET failed to start for %s: Error code %d" % [request_type, err]
		push_error("[GodotAIBridge] " + err_msg)
		emit_signal("request_failed", err_msg)
		http_req.queue_free()


func _on_http_completed(_result: int, response_code: int, _headers: PoolStringArray, body: PoolByteArray, http_req: HTTPRequest, request_type: String) -> void:
	http_req.queue_free()
	var body_str = body.get_string_from_utf8()

	if response_code < 200 or response_code >= 300:
		var err_msg = "Server returned HTTP status %d for %s: %s" % [response_code, request_type, body_str]
		push_error("[GodotAIBridge] " + err_msg)
		emit_signal("request_failed", err_msg)
		return

	var parse_result = JSON.parse(body_str)
	if parse_result.error != OK:
		var err_msg = "Failed to parse server JSON response for " + request_type
		push_error("[GodotAIBridge] " + err_msg)
		emit_signal("request_failed", err_msg)
		return

	var data = parse_result.result
	if not data is Dictionary:
		return

	match request_type:
		"scene_create":
			var success = data.get("success", false)
			var file_path = data.get("file_path", "")
			print("[GodotAIBridge] Scene created: ", file_path)
			emit_signal("scene_created", success, file_path, data)

		"scene_edit":
			var success = data.get("success", false)
			var file_path = data.get("file_path", "")
			print("[GodotAIBridge] Scene edited: ", file_path)
			emit_signal("scene_edited", success, file_path, data)

		"scene_delete":
			var success = data.get("success", false)
			var file_path = data.get("file_path", "")
			print("[GodotAIBridge] Scene deleted: ", file_path)
			emit_signal("scene_deleted", success, file_path, data)

		"scene_read":
			var success = data.get("success", false)
			var file_path = data.get("file_path", "")
			var content = data.get("content", "")
			emit_signal("scene_read", success, file_path, content)

		"action":
			if data.has("action"):
				var action = data["action"]
				print("[GodotAIBridge] Received Action: ", action.get("action_type", ""))
				if action.has("thought"):
					print("[GodotAIBridge] AI Thought: ", action["thought"])
				emit_signal("action_received", action)

				if auto_apply_actions:
					apply_action(action)

		"chat":
			if data.has("response"):
				emit_signal("chat_completed", data["response"])
