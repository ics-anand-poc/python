from fastapi import APIRouter, Body, Depends, Request

from core.auth import require_admin
from core.errors import ApiError, json_error, public_error
from core.security import get_client_ip, is_rate_limited, is_rate_limited_any, rate_limited_response
from core.tokens import sign_token
from core.validation import as_email, as_password
from services import admin_accounts, audit

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])


@router.post("/login")
def login(request: Request, body: dict = Body(default_factory=dict)):
    ip = get_client_ip(request)
    ip_limit = is_rate_limited_any([f"auth:ip:{ip}"], 8, 60_000)
    if ip_limit.limited:
        return rate_limited_response(ip_limit, "Too many login attempts. Please try again later.")
    try:
        email = as_email(body.get("email"))
        password = as_password(body.get("password"), allow_empty=True)
        if password is None:
            return json_error(400, "Invalid request")
        if not email or not email.endswith("@infinite.com"):
            audit.add_log(email or "unknown", "ADMIN_LOGIN_FAILURE", "Admin Console", "Unauthorized email domain extension", ip)
            return json_error(400, "Unauthorized domain. Please enter your @infinite.com email.")
        account_limit = is_rate_limited_any([f"auth:acct:{email}"], 5, 60_000)
        if account_limit.limited:
            return rate_limited_response(account_limit, "Too many login attempts. Please try again later.")
        try:
            access = admin_accounts.authenticate(email, password)
        except admin_accounts.AdminPasswordNotSetup:
            audit.add_log(email, "ADMIN_LOGIN_FAILURE", "Admin Console", admin_accounts.ADMIN_PASSWORD_NOT_SETUP, ip)
            return json_error(503, admin_accounts.ADMIN_PASSWORD_NOT_SETUP)
        if not access:
            audit.add_log(email, "ADMIN_LOGIN_FAILURE", "Admin Console", "Invalid password provided", ip)
            return json_error(401, "Invalid Password")
        token = sign_token("admin", 60 * 60 * 1000)
        audit.add_log(
            access["email"], "ADMIN_LOGIN_SUCCESS", "Admin Console",
            "Admin session generated successfully" if access["canViewEmployeePortal"]
            else "Admin session generated without Employee Portal access", ip,
        )
        return {
            "status": "ok",
            "token": token,
            "canViewEmployeePortal": access["canViewEmployeePortal"],
            "canChangePassword": access["canChangePassword"],
        }
    except Exception as err:
        return public_error(err, "Unable to sign in")


@router.get("/validate")
def validate(request: Request, _: str = Depends(require_admin)):
    email = (request.query_params.get("email") or "").strip().lower()
    if not email:
        return {"status": "ok"}
    access = admin_accounts.get_access(email)
    return {"status": "ok", "email": access["email"], "canViewEmployeePortal": access["canViewEmployeePortal"],
            "canChangePassword": access["canChangePassword"]}


@router.post("/change-password")
def change_password(request: Request, body: dict = Body(default_factory=dict), _: str = Depends(require_admin)):
    ip = get_client_ip(request)
    limit = is_rate_limited(f"admin_change_password_{ip}", 5, 60_000)
    if limit.limited:
        return rate_limited_response(limit, "Too many attempts. Please try again later.")
    try:
        email = as_email(body.get("email")) or ""
        current = as_password(body.get("currentPassword") if isinstance(body.get("currentPassword"), str) else "", True)
        new = as_password(body.get("newPassword") if isinstance(body.get("newPassword"), str) else "", True)
        if current is None or new is None:
            return json_error(400, "Invalid request")
        if not admin_accounts.can_change_password(email):
            audit.add_log(email or "unknown", "ADMIN_PASSWORD_CHANGE_DENIED", "Admin Console",
                          "Account is not allowed to change password", ip)
            return json_error(403, "This account cannot change its password here.")
        try:
            ok, error = admin_accounts.change_password(email, current, new)
        except admin_accounts.AdminPasswordNotSetup:
            return json_error(503, admin_accounts.ADMIN_PASSWORD_NOT_SETUP)
        if not ok:
            audit.add_log(email, "ADMIN_PASSWORD_CHANGE_FAILURE", "Admin Console", error, ip)
            return json_error(400, error)
        audit.add_log(email, "ADMIN_PASSWORD_CHANGE_SUCCESS", "Admin Console", "Named admin password updated", ip)
        return {"status": "ok"}
    except Exception as err:
        return public_error(err, "Failed to change password")


@router.post("/verify-supervisor")
def verify_supervisor(request: Request, body: dict = Body(default_factory=dict), _: str = Depends(require_admin)):
    ip = get_client_ip(request)
    limit = is_rate_limited(f"admin_supervisor_auth_{ip}", 10, 60_000)
    if limit.limited:
        return rate_limited_response(limit, "Too many supervisor authorization attempts. Please try again later.")
    password = str(body.get("password") or "").strip()
    if not password:
        return json_error(400, "Supervisor password is required.")
    try:
        if not admin_accounts.verify_supervisor(password):
            audit.add_log("admin@infinite.com", "ADMIN_SUPERVISOR_AUTH_FAILURE", "Admin Console", "Invalid supervisor password provided", ip)
            return json_error(401, "Invalid supervisor password.")
        audit.add_log("admin@infinite.com", "ADMIN_SUPERVISOR_AUTH_SUCCESS", "Admin Console", "Supervisor action authorized", ip)
        return {"status": "ok", "valid": True}
    except admin_accounts.AdminPasswordNotSetup as err:
        return json_error(503, str(err))
    except Exception as err:
        return public_error(err, "Failed to verify supervisor password")

