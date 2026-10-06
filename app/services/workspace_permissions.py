"""Central workspace role and permission helpers.

Roles are ranked so new permissions can be added without rewriting models.
Higher rank includes lower-rank abilities unless a permission is owner-only.
"""

from app.models.workspace import (
    WORKSPACE_ROLE_ADMIN,
    WORKSPACE_ROLE_MEMBER,
    WORKSPACE_ROLE_OWNER,
)

ROLE_RANK = {
    WORKSPACE_ROLE_MEMBER: 1,
    WORKSPACE_ROLE_ADMIN: 2,
    WORKSPACE_ROLE_OWNER: 3,
}

# Minimum role rank required for each permission key.
PERMISSIONS = {
    "workspace:read": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "workspace:update": ROLE_RANK[WORKSPACE_ROLE_ADMIN],
    "workspace:delete": ROLE_RANK[WORKSPACE_ROLE_OWNER],
    "members:read": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "members:invite": ROLE_RANK[WORKSPACE_ROLE_ADMIN],
    "members:manage": ROLE_RANK[WORKSPACE_ROLE_ADMIN],
    "members:remove": ROLE_RANK[WORKSPACE_ROLE_ADMIN],
    "resources:read": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "resources:write": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "knowledge:read": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "knowledge:write": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "knowledge:admin": ROLE_RANK[WORKSPACE_ROLE_ADMIN],
    "conversations:read": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "conversations:write": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "agents:read": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "agents:manage": ROLE_RANK[WORKSPACE_ROLE_ADMIN],
    "tools:use": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "integrations:read": ROLE_RANK[WORKSPACE_ROLE_MEMBER],
    "integrations:manage": ROLE_RANK[WORKSPACE_ROLE_ADMIN],
}


def normalize_role(role: str) -> str:
    value = (role or "").strip().lower()
    if value not in ROLE_RANK:
        raise ValueError(f"Invalid workspace role: {role}")
    return value


def role_rank(role: str) -> int:
    return ROLE_RANK[normalize_role(role)]


def has_permission(role: str, permission: str) -> bool:
    required = PERMISSIONS.get(permission)
    if required is None:
        return False
    return role_rank(role) >= required


def can_assign_role(actor_role: str, target_role: str) -> bool:
    """Admins may assign member/admin; only owners may assign owner."""
    actor = normalize_role(actor_role)
    target = normalize_role(target_role)
    if target == WORKSPACE_ROLE_OWNER:
        return actor == WORKSPACE_ROLE_OWNER
    return role_rank(actor) >= ROLE_RANK[WORKSPACE_ROLE_ADMIN]


def can_manage_member(actor_role: str, target_role: str) -> bool:
    """Actors cannot manage members with a strictly higher role."""
    actor = normalize_role(actor_role)
    target = normalize_role(target_role)
    if target == WORKSPACE_ROLE_OWNER and actor != WORKSPACE_ROLE_OWNER:
        return False
    return role_rank(actor) >= ROLE_RANK[WORKSPACE_ROLE_ADMIN] and role_rank(actor) >= role_rank(
        target
    )
