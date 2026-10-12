from typing import Optional

from fastapi import Request

from core.errors import ApiError
from core.tokens import verify_token


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
