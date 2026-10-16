from typing import Optional

from fastapi import Depends, Request

from core.errors import ApiError
from core.tokens import token_email, verify_token


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    return header[7:] if header.startswith("Bearer ") else header


def admin_token(request: Request) -> str:
    bearer = bearer_token(request)
    if bearer or request.method not in ("GET", "HEAD"):
        return bearer
    return request.query_params.get("token") or ""


def is_admin_request(request: Request) -> bool:
    token = admin_token(request)
    return bool(token) and verify_token(token) == "ADMIN"


def require_admin(request: Request) -> str:
    if not is_admin_request(request):
        raise ApiError(401, "Unauthorized")
    return "ADMIN"


def admin_email(request: Request) -> Optional[str]:
    return token_email(admin_token(request))


def acting_admin_email(request: Request) -> Optional[str]:
    return admin_email(request) or (request.query_params.get("email") or "").strip().lower() or None


def require_permission(permission: str):
    def check(request: Request, _: str = Depends(require_admin)) -> str:
        from services import admin_accounts

        email = admin_email(request)
        if email and not admin_accounts.has_permission(email, permission):
            raise ApiError(403, "You do not have access to this section.")
        return email or "ADMIN"

    return check


def employee_id_from_request(request: Request) -> Optional[str]:
    return verify_token(bearer_token(request))


def require_employee(request: Request) -> dict:
    from services import accounts

    employee_id = employee_id_from_request(request)
    if not employee_id:
        raise ApiError(401, "Unauthorized")
    employee = accounts.get_account(employee_id)
    if not employee:
        raise ApiError(401, "Unauthorized")
    return employee
