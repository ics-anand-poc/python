from fastapi import APIRouter, Body, Depends, Request

from core.auth import admin_email, require_admin
from core.errors import ApiError, json_error, public_error
from core.security import get_client_ip
from services import admin_accounts, audit

router = APIRouter(prefix="/api/admin/admin-accounts", tags=["admin-access"])


def super_admin_only(request: Request, _: str = Depends(require_admin)) -> str:
    email = admin_email(request)
    if not email:
        raise ApiError(403, "Please sign out and sign in again to manage admin access.")
    if not admin_accounts.is_super_admin(email):
        raise ApiError(403, "Only the main admin can manage admin access.")
    return email


def _describe(permissions: dict) -> str:
    allowed = [label for key, label in admin_accounts.PERMISSIONS if permissions.get(key) is True]
    return f"Can see: {'; '.join(allowed)}" if allowed else "No sections ticked"


def _overview(actor: str) -> dict:
    return {"superAdmin": actor, "permissions": [{"key": k, "label": label} for k, label in admin_accounts.PERMISSIONS],
            "admins": admin_accounts.list_named()}


@router.get("")
def list_admins(actor: str = Depends(super_admin_only)):
    return _overview(actor)


@router.post("")
def save_admin(request: Request, body: dict = Body(default_factory=dict), actor: str = Depends(super_admin_only)):
    try:
        email = str(body.get("email") or "").strip().lower()
        permissions = body.get("permissions") if isinstance(body.get("permissions"), dict) else {}
        password = body.get("password") if isinstance(body.get("password"), str) else None
        ok, error, created = admin_accounts.save_named(email, permissions, password)
        if not ok:
            return json_error(400, error)
        audit.add_log(actor, "ADMIN_ACCESS_GRANTED" if created else "ADMIN_ACCESS_UPDATED", email,
                      f"{_describe(permissions)}{' (password reset)' if password and not created else ''}", get_client_ip(request))
        return {"ok": True, "created": created, "admins": admin_accounts.list_named()}
    except Exception as err:
        return public_error(err, "Failed to save admin access")


@router.delete("")
def remove_admin(request: Request, actor: str = Depends(super_admin_only)):
    email = str(request.query_params.get("email") or "").strip().lower()
    if not email:
        return json_error(400, "Email is required.")
    if not admin_accounts.remove_named(email):
        return json_error(404, "That admin was not found.")
    audit.add_log(actor, "ADMIN_ACCESS_REVOKED", email, "Admin panel access removed", get_client_ip(request))
    return {"ok": True, "admins": admin_accounts.list_named()}
