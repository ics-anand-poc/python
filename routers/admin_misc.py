import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse, Response

from core.auth import acting_admin_email, require_admin, require_permission
from core.db import get_store
from core.errors import json_error, public_error
from core.security import get_client_ip
from services import admin_accounts, audit, reset_logs, settings, structured_log
from services.dashboard_sync import bump_sync, read_sync
from services.structured_log import write_log

log = logging.getLogger("talentscope")
public = APIRouter(prefix="/api", tags=["portal"])
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])



@public.get("/portal_settings")
def portal_settings():
    try:
        return settings.get_portal_features()
    except Exception as err:
        return public_error(err, "Failed to get settings")


@router.post("/portal_settings")
def update_portal_settings(request: Request, body: dict = Body(default_factory=dict)):
    new_settings = body.get("settings")
    if not isinstance(new_settings, dict):
        return json_error(400, "Invalid settings object")
    try:
        updated = settings.update_portal_features(new_settings)
        details = f"Updated portal settings: SystemLogsViewer={updated['showSystemLogsViewer']}"
        audit.add_log(body.get("adminEmail") or "admin@infinite.com", "ADMIN_UPDATE_PORTAL_SETTINGS", "portal-settings", details, get_client_ip(request))
        write_log("employee", "UPDATE_PORTAL_SETTINGS", "success", details)
        return {"success": True, "settings": updated}
    except Exception as err:
        write_log("employee", "UPDATE_PORTAL_SETTINGS_FAILED", "failed", str(err))
        return public_error(err, "Failed to update settings")


@router.get("/interview_defaults")
def interview_defaults():
    return settings.get_interview_defaults()


@router.post("/interview_defaults")
def update_interview_defaults(request: Request, body: dict = Body(default_factory=dict)):
    try:
        updated = settings.update_interview_defaults(body)
        details = f"Default interview duration set to {updated['durationMinutes']} minutes"
        audit.add_log(body.get("adminEmail") or "admin@infinite.com", "ADMIN_UPDATE_INTERVIEW_DEFAULTS", "interview-defaults",
                      details, get_client_ip(request))
        write_log("audit", "UPDATE_INTERVIEW_DEFAULTS", "success", details)
        return {"success": True, **updated}
    except Exception as err:
        return public_error(err, "Failed to update interview defaults")


@router.get("/sync")
def sync():
    return read_sync()


def _display_log(entry: dict) -> dict:
    status = str(entry.get("status") or "success").lower()
    if status not in ("success", "failed", "error", "warning"):
        status = "success"
    timestamp = str(entry.get("timestamp") or "")
    if timestamp in ("", "None"):
        timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "timestamp": timestamp,
        "module": str(entry.get("module") or "audit"),
        "action": str(entry.get("action") or "UNKNOWN"),
        "status": status,
        "details": str(entry.get("details") or ""),
        "actor": str(entry.get("actor") or ""),
        "ip": str(entry.get("ip") or ""),
    }


@router.get("/logs", dependencies=[Depends(require_permission("systemLogs"))])
def get_logs(request: Request):
    module = request.query_params.get("module") or "all"
    status = request.query_params.get("status") or "all"
    search = (request.query_params.get("search") or "").lower()
    if request.query_params.get("download") == "true":
        if module != "all" and not structured_log.MODULE_RE.match(module):
            return json_error(404, "Log file not found")
        entries = [_display_log(entry) for entry in structured_log.merged_logs(module)]
        content = "\n".join(__import__("json").dumps(entry) for entry in entries)
        name = "system_logs.log" if module == "all" else f"{module}.log"
        return Response(content, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{name}"'})
    entries = [_display_log(entry) for entry in structured_log.merged_logs(module)]
    if status != "all":
        entries = [e for e in entries if e["status"] == status.lower()]
    if search:
        fields = ("action", "details", "module", "actor", "ip")
        entries = [e for e in entries if any(search in str(e.get(f) or "").lower() for f in fields)]
    return {"logs": entries[:1500], "total": len(entries)}


@router.delete("/logs", dependencies=[Depends(require_permission("systemLogs"))])
def clear_logs():
    structured_log.clear_all()
    audit.clear_logs()
    write_log("audit", "CLEAR_SYSTEM_LOGS", "success", "Cleared system and audit logs")
    return {"success": True}


@router.get("/reset_logs")
def get_reset_logs():
    return {"logs": reset_logs.get_logs()}


@router.delete("/reset_logs")
def clear_reset_logs():
    reset_logs.clear_logs()
    write_log("candidate-processing", "CLEAR_RESET_LOGS", "success", "Cleared all candidate reset logs")
    return {"success": True, "logs": []}


def _map_email(row: dict) -> dict:
    return {"id": row["id"], "to": row.get("candidate_email"), "fullName": row.get("full_name") or "", "subject": row.get("subject") or "",
            "htmlBody": row.get("body") or "", "dispatchedAt": row.get("created_at") or datetime.now(timezone.utc).isoformat(),
            "status": row.get("status") or "simulated", "rmEmail": row.get("rm_email")}


def _emails_for(email: str | None) -> list[dict]:
    rows = [_map_email(r) for r in get_store().select("simulated_emails")]
    if email and not admin_accounts.can_view_org_screening_data(email):
        rows = [r for r in rows if str(r.get("rmEmail") or "").lower().strip() == email]
    return sorted(rows, key=lambda r: r["dispatchedAt"], reverse=True)


@router.get("/emails", dependencies=[Depends(require_permission("emailOutbox"))])
def get_emails(request: Request):
    try:
        email = acting_admin_email(request)
        return {"emails": _emails_for(email)}
    except Exception as err:
        log.error("Failed to read emails outbox: %s", err)
        return json_error(500, "Failed to read Outbox Logs")


@router.delete("/emails", dependencies=[Depends(require_permission("emailOutbox"))])
async def delete_emails(request: Request):
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}
        query_ids = request.query_params.get("ids")
        raw = body.get("ids") if isinstance(body, dict) and isinstance(body.get("ids"), list) else (
            [i.strip() for i in query_ids.split(",") if i.strip()] if query_ids else None)
        ids = list(dict.fromkeys(str(i).strip() for i in raw if str(i).strip())) if raw else None
        store = get_store()
        if not ids:
            store.delete("simulated_emails", None)
            write_log("email", "CLEAR_EMAIL_LOGS", "success", "Cleared all email outbox logs")
            return {"success": True, "emails": [], "deletedCount": None}
        store.delete("simulated_emails", {"id": ids})
        write_log("email", "DELETE_EMAIL_LOGS", "success", f"Deleted email logs for IDs: {', '.join(ids)}")
        email = acting_admin_email(request)
        return {"success": True, "emails": _emails_for(email), "deletedCount": len(ids)}
    except Exception as err:
        write_log("email", "DELETE_EMAIL_LOGS_FAILED", "failed", str(err))
        return public_error(err, "Failed to clear Outbox Logs")
