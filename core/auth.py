from typing import Optional

from fastapi import Depends, Request

from core.errors import ApiError
from core.tokens import token_email, verify_token


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    return header[7:] if header.startswith("Bearer ") else header


def admin_token(request: Request) -> str:
    bearer = bearer_token(request)
    if bearer:
        return bearer
    # <video src> cannot send Authorization; allow ?token= only for GET/HEAD media.
    if request.method in ("GET", "HEAD") and request.url.path.rstrip("/").endswith("/video"):
        return request.query_params.get("token") or ""
    return ""


def is_admin_request(request: Request) -> bool:
    token = admin_token(request)
    return bool(token) and verify_token(token) == "ADMIN"


def require_admin(request: Request) -> str:
    if not is_admin_request(request):
        raise ApiError(401, "Unauthorized")
    email = admin_email(request)
    if not email:
        raise ApiError(401, "Unauthorized")
    return email


def admin_email(request: Request) -> Optional[str]:
    return token_email(admin_token(request))


def acting_admin_email(request: Request) -> Optional[str]:
    # Authz/audit actor must come from the JWT only — never body/?email=.
    return admin_email(request)


def require_permission(permission: str):
    def check(request: Request, email: str = Depends(require_admin)) -> str:
        from services import admin_accounts

        if not admin_accounts.has_permission(email, permission):
            raise ApiError(403, "You do not have access to this section.")
        return email

    return check


def require_any_permission(*permissions: str):
    def check(request: Request, email: str = Depends(require_admin)) -> str:
        from services import admin_accounts

        if not any(admin_accounts.has_permission(email, p) for p in permissions):
            raise ApiError(403, "You do not have access to this section.")
        return email

    return check


def employee_id_from_request(request: Request) -> Optional[str]:
    return verify_token(bearer_token(request))


def require_employee(request: Request) -> dict:
    from services import accounts

    employee_id = employee_id_from_request(request)
    if not employee_id or employee_id == "ADMIN" or employee_id == "INTERVIEW":
        raise ApiError(401, "Unauthorized")
    employee = accounts.get_account(employee_id)
    if not employee:
        raise ApiError(401, "Unauthorized")
    return employee
