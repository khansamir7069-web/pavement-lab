"""Collaboration governance models supporting RBAC authorization, auditing, and annotations."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass
class User:
    """Represents a platform user."""
    user_id: str
    username: str
    email: str
    role: str  # ADMIN, ENGINEER, VIEWER


@dataclass
class Organization:
    """Represents an enterprise tenant organization."""
    org_id: str
    name: str


@dataclass
class ProjectPermission:
    """Maps access rights for a user onto a pavement project."""
    user_id: str
    project_id: str
    access_level: str  # READ, WRITE, ADMIN


@dataclass
class AuditLogRecord:
    """Represents an immutable record of system changes or solver runs."""
    timestamp: float
    user_id: str
    action: str  # run_solver, update_thickness, approve_design, modify_rates
    target_id: str
    details: str


@dataclass
class Annotation:
    """Stores a user comment or engineering review note on a specific section."""
    annotation_id: str
    section_id: str
    user_id: str
    comment: str
    timestamp: float = field(default_factory=time.time)


class CollaborationManager:
    """Governs role authorizations, permission lookups, and audit logging."""

    def __init__(self) -> None:
        self.permissions: list[ProjectPermission] = []
        self.audit_log: list[AuditLogRecord] = []
        self.annotations: list[Annotation] = []

    def grant_permission(self, user_id: str, project_id: str, access_level: str) -> None:
        """Add access permission for a user."""
        self.permissions.append(ProjectPermission(user_id, project_id, access_level))

    def check_authorized(self, user_id: str, project_id: str, required_level: str) -> bool:
        """Validate if a user is authorized for the required operations."""
        levels = ["READ", "WRITE", "ADMIN"]
        if required_level not in levels:
            return False
            
        req_idx = levels.index(required_level)
        for perm in self.permissions:
            if perm.user_id == user_id and perm.project_id == project_id:
                has_idx = levels.index(perm.access_level)
                return has_idx >= req_idx
        return False

    def log_activity(self, user_id: str, action: str, target_id: str, details: str) -> None:
        """Append a record to the enterprise audit log."""
        self.audit_log.append(AuditLogRecord(
            timestamp=time.time(),
            user_id=user_id,
            action=action,
            target_id=target_id,
            details=details
        ))

    def add_annotation(self, section_id: str, user_id: str, comment: str) -> Annotation:
        """Add a design annotation or review note."""
        import uuid
        ann = Annotation(
            annotation_id=str(uuid.uuid4()),
            section_id=section_id,
            user_id=user_id,
            comment=comment
        )
        self.annotations.append(ann)
        return ann
