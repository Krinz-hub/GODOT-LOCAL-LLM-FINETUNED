"""Data models for Autonomous Godot AI Agent Orchestrator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class TaskItem:
    id: str
    description: str
    target_files: List[str]
    dependencies: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    diagnostics: List[str] = field(default_factory=list)
    checkpoint_ref: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    output_diff: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskItem:
        d = dict(data)
        d["status"] = TaskStatus(d.get("status", "pending"))
        return cls(**d)


@dataclass
class ProjectPlan:
    plan_id: str
    user_request: str
    project_path: str
    is_complex: bool
    tasks: List[TaskItem]
    status: str = "planning"  # planning, executing, completed, blocked
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    execution_log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "user_request": self.user_request,
            "project_path": self.project_path,
            "is_complex": self.is_complex,
            "tasks": [t.to_dict() for t in self.tasks],
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "execution_log": self.execution_log,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProjectPlan:
        tasks = [TaskItem.from_dict(t) for t in data.get("tasks", [])]
        return cls(
            plan_id=data["plan_id"],
            user_request=data["user_request"],
            project_path=data["project_path"],
            is_complex=data.get("is_complex", False),
            tasks=tasks,
            status=data.get("status", "planning"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            execution_log=data.get("execution_log", []),
        )

    def save_to_disk(self, file_path: Path) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load_from_disk(cls, file_path: Path) -> Optional[ProjectPlan]:
        if not file_path.exists():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            return None
