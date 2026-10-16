"""Headless Godot technical validator."""

from dataclasses import dataclass, field
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from logic_pipeline.logging_config import get_logger

logger = get_logger("validation.godot")


@dataclass
class HeadlessRunResult:
    executable_found: bool = False
    executable_path: str = ""
    opt_in_enabled: bool = False
    import_success: bool = False
    headless_launch_success: bool = False
    return_code: Optional[int] = None
    output_log: str = ""
    errors: List[str] = field(default_factory=list)


def validate_with_godot_headless(
    project_dir: Path,
    godot_executable: str = "godot4",
    allow_runtime: bool = False,
    timeout_seconds: int = 30,
    temp_sandbox_dir: Optional[Path] = None,
) -> HeadlessRunResult:
    """Safely runs Godot headless in an isolated disposable sandbox directory."""
    result = HeadlessRunResult()

    # 1. Check if executable exists in PATH
    exe_path = shutil.which(godot_executable) or shutil.which("godot")
    if not exe_path:
        result.executable_found = False
        result.errors.append(
            f"Godot executable '{godot_executable}' not found in PATH. "
            "Headless runtime validation skipped (install Godot 4 binary or configure executable path to enable)."
        )
        return result

    result.executable_found = True
    result.executable_path = exe_path

    # 2. Check runtime execution opt-in
    if not allow_runtime:
        result.opt_in_enabled = False
        result.errors.append(
            "Runtime execution is disabled by default for safety. "
            "Set allow_runtime_execution: true in validation_rules.yaml or pass --allow-runtime to enable."
        )
        return result

    result.opt_in_enabled = True

    # 3. Create isolated disposable sandbox
    sandbox = (temp_sandbox_dir or (project_dir / ".godot_sandbox")) / f"run_{project_dir.name}"
    try:
        shutil.rmtree(sandbox, ignore_errors=True)
        shutil.copytree(project_dir, sandbox, ignore=shutil.ignore_patterns(".git*", ".godot*"))

        # Run Godot headless project import/editor check
        cmd = [exe_path, "--headless", "--editor", "--quit", "--path", str(sandbox)]
        logger.info("Executing headless Godot check: %s", " ".join(cmd))

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        result.return_code = proc.returncode
        result.output_log = (proc.stdout + "\n" + proc.stderr).strip()

        if proc.returncode == 0:
            result.import_success = True
            result.headless_launch_success = True
        else:
            result.errors.append(f"Godot process exited with code {proc.returncode}")

    except subprocess.TimeoutExpired:
        result.errors.append(f"Godot headless run timed out after {timeout_seconds} seconds")
    except Exception as e:
        result.errors.append(f"Sandbox execution error: {e}")
    finally:
        # Clean up disposable sandbox
        shutil.rmtree(sandbox, ignore_errors=True)

    return result
