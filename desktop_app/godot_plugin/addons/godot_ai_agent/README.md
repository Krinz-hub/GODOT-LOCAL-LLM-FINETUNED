# Godot AI Agent Connector Plugin (Godot 4)

This plugin connects your active Godot 4 editor project directly to the **Godot AI Agent Desktop IDE**.

## Features
- **Automatic Project Detection:** As soon as you open your project in Godot, the Desktop IDE detects and switches to it.
- **Localhost Only & Secure:** Communicates over `http://127.0.0.1:8000` using a local authentication token (`~/.godot_ai_agent/auth_token.txt`).
- **Zero Source Transmission:** Only transmits the project root directory and Godot engine version metadata, never raw source code over the network.
- **Heartbeat & Reconnection:** Automatically reconnects if the AI Desktop IDE is launched or restarted.

## Installation in Godot 4

1. Copy the `addons/godot_ai_agent` directory into your Godot project's `res://addons/` directory:
   ```bash
   cp -r desktop_app/godot_plugin/addons/godot_ai_agent /path/to/your/project/addons/
   ```
2. Open your project in Godot 4.
3. Go to **Project** -> **Project Settings...** -> **Plugins**.
4. Find **Godot AI Agent Connector** in the list and check the **Enable** box.
5. In the Godot Output panel at the bottom, you will see:
   ```
   [Godot AI Agent] ✓ Active project successfully registered with AI Desktop IDE!
   ```
6. The Desktop IDE will instantly show your project as connected.
