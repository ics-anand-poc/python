import logging
import re

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from core.auth import acting_admin_email, require_permission
from core.errors import json_error, public_error
from core.security import UPLOAD_ALLOWED_EXTS, get_client_ip, inspect_upload, is_rate_limited_any, rate_limited_response
from core.validation import as_email
from services import automation, dashboard_sync, docs_storage, hr_files, portal_roster, resumes
from services.structured_log import write_log

log = logging.getLogger("talentscope")
router = APIRouter(prefix="/api/admin", tags=["admin-ingest"], dependencies=[Depends(require_permission("adminControls"))])

CATEGORY_MAP = {
    "resume": ("Resumes", "candidates"), "jd": ("JD", "requirements"), "br": ("BR", "requirements"),
    "employee": ("Corp Pool", "employees"), "portal-mapping": ("Portal Mapping", "portal-mapping"), "interview": (None, "interviews"),
}


def infer_category(filename: str, selected: str) -> str:
    name = filename.lower()
    collapsed = re.sub(r"\s+", "_", name)
    if selected == "interview":
        return "interview"
    if re.search(r"\d+\s*br\.(docx|doc|pdf|txt|html|htm)$", name, re.I):
        return "jd"
    if re.search(r"\.(xlsx|xls|csv)$", name, re.I) and (re.search(r"\d+\s*br", name, re.I) or re.search(r"br_rawdata", collapsed, re.I)):
        return "br"
    if selected == "br":
        return "br"
    if selected == "jd":
        return "jd"
    if docs_storage.is_portal_mapping_name(filename) or selected == "portal-mapping":
        return "portal-mapping"
    if automation.is_corp_pool_roster_file_name(filename) or name.endswith(".csv"):
        return "employee"
    return selected or "resume"


def _counts(result: dict) -> str:
    parts = []
    for key in ("processed", "processedBRs", "convertedJDs", "incomingBrRows", "duplicates", "loaded", "added", "updated", "skippedDeleted", "count", "stored"):
        value = result.get(key)
        if isinstance(value, (list, dict)):
            value = len(value)
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def _note(kind: str, result: dict, filename: str = "") -> str:
    counts = _counts(result) if isinstance(result, dict) else ""
    lead = f"{filename}: " if filename else ""
    return f"{lead}{kind} finished" + (f" ({counts})" if counts else "")


@router.post("/upload_unified")
async def upload_unified(request: Request, file: UploadFile = File(None), category: str = Form(""), activeJdId: str = Form(None),
                         actorEmail: str = Form(None), adminEmail: str = Form(None)):
    # actorEmail/adminEmail form fields are ignored — actor comes from the JWT only.
    _ = (actorEmail, adminEmail)
    ip = get_client_ip(request)
    limit = is_rate_limited_any([f"upload:ip:{ip}"], 60, 60 * 60_000)
    if limit.limited:
        return rate_limited_response(limit, "Too many uploads. Please try again later.")
    try:
        if file is None:
            return json_error(400, "No file provided")
        data = await file.read()
        ok, safe = inspect_upload(data, file.filename or "", 25 * 1024 * 1024, UPLOAD_ALLOWED_EXTS)
        if not ok:
            return json_error(400, safe)
        if docs_storage.is_portal_credentials_name(file.filename or "") or docs_storage.is_portal_credentials_name(safe):
            return json_error(400, "Credential workbooks are not uploaded. Use Resource_Question_Mapping.xlsx only.")
        preview = ""
        try:
            if re.search(r"\.(xlsx|xls)$", safe, re.I):
                preview = hr_files.excel_preview(data)
            elif re.search(r"\.(pdf|docx|doc|txt|html|htm)$", safe, re.I):
                preview = str(resumes.extract_text(data, safe) or "")[:6500]
        except Exception:
            preview = ""
        placed = hr_files.place_file(safe, preview)
        selected = category or ""
        chosen = infer_category(safe, selected)
        is_resume_doc = bool(re.search(r"\.(pdf|docx|doc)$", safe, re.I))
        if selected == "resume" and is_resume_doc:
            chosen = "resume"
        elif placed["kind"] != "unknown" and (not selected or placed["category"] == selected or (selected == "jd" and placed["category"] in ("jd", "br"))):
            chosen = placed["category"]
        is_excel = bool(re.search(r"\.(xlsx|xls)$", safe, re.I))
        if chosen != "portal-mapping" and is_excel and portal_roster.mapping_looks_valid(data):
            chosen = "portal-mapping"
        if chosen not in ("employee", "interview", "br", "jd", "portal-mapping") and is_excel and automation.excel_looks_like_corp_pool_roster(data):
            chosen = "employee"
        if chosen not in CATEGORY_MAP:
            return json_error(400, "Invalid upload category")
        doc_category, refresh = CATEGORY_MAP[chosen]
        stored = (automation.sanitize_corp_pool_file_name(safe) if doc_category == "Corp Pool"
                  else docs_storage.PORTAL_MAPPING_STORED_NAME if doc_category == "Portal Mapping" else safe)
        actor = acting_admin_email(request) or ""
        if doc_category:
            docs_storage.write_file(doc_category, stored, data)
        result: dict = {}
        if refresh == "requirements":
            kind_args = ({"incoming_br": [(stored, data)]} if chosen == "br" else {"incoming_jd": [(stored, data)]})
            result = automation.refresh_requirements(**kind_args, actor_email=actor)
            if chosen == "jd" and not result["convertedJDs"]:
                raise ValueError("The JD was stored, but it could not be added to Requirements. Put a BR ID in the filename (for example 51210BR.pdf)."
                                 if preview.strip() else "No readable text in this JD. Use a text PDF, Word, HTML, or TXT, not a scanned image.")
            if chosen == "br" and not result["incomingBrRows"]:
                raise ValueError("The BR file was stored, but no requirement rows were found. Use an Excel with an Auto req ID / BR ID column.")
        elif refresh == "candidates":
            result = automation.refresh_candidates(activeJdId)
        elif refresh == "employees":
            result = automation.refresh_employees(activeJdId, [(stored, data)])
            result.pop("employees", None)
        elif refresh == "portal-mapping":
            portal_roster.invalidate_mapping_cache()
            result = {"stored": stored, "liveSource": "database + uploaded mapping workbook"}
        elif refresh == "interviews":
            result = automation.refresh_interviews()
        dashboard_sync.bump_sync(f"upload_{chosen}")
        write_log("ingestion", "UPLOAD_PROCESSED", "success", _note(chosen, result, safe), actor or None)
        return {"success": True, "category": chosen, "message": f"File uploaded and processed successfully under {chosen}.", "refreshResult": result}
    except ValueError as err:
        write_log("ingestion", "UPLOAD_REJECTED", "failed", str(err), acting_admin_email(request) or None)
        return json_error(400, str(err))
    except Exception as err:
        write_log("ingestion", "UPLOAD_FAILED", "failed", "Upload processing failed", acting_admin_email(request) or None)
        return public_error(err, "Upload processing failed")


@router.post("/refresh")
def refresh(request: Request):
    kind = request.query_params.get("type")
    jd_id = request.query_params.get("activeJdId") or None
    actor = acting_admin_email(request) or ""
    try:
        if kind == "requirements":
            result = automation.refresh_requirements(actor_email=actor)
        elif kind == "sync-selected":
            result = {"synced": False, "message": "Requirements are stored in the database; nothing to sync."}
        elif kind == "candidates":
            result = automation.refresh_candidates(jd_id)
        elif kind == "employees":
            result = automation.refresh_employees(jd_id)
            result.pop("employees", None)
        elif kind == "interviews":
            result = automation.refresh_interviews()
        else:
            write_log("ingestion", "REFRESH_REJECTED", "failed", f"Invalid refresh type: {kind or 'missing'}", actor or None)
            return json_error(400, "Invalid refresh type specified")
        ok = bool(result.get("success", True)) if isinstance(result, dict) else True
        write_log("ingestion", f"REFRESH_{str(kind).upper()}", "success" if ok else "failed", _note(kind, result if isinstance(result, dict) else {}), actor or None)
        dashboard_sync.bump_sync(f"refresh_{kind}")
        return {**result, "success": ok}
    except ValueError as err:
        write_log("ingestion", f"REFRESH_{str(kind or 'UNKNOWN').upper()}_FAILED", "failed", str(err), actor or None)
        return json_error(400, str(err))
    except Exception as err:
        write_log("ingestion", f"REFRESH_{str(kind or 'UNKNOWN').upper()}_FAILED", "failed", "Refresh failed", actor or None)
        return public_error(err, "Refresh failed")
