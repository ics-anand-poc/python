from fastapi import APIRouter, Depends, Request

from core.auth import require_permission
from core.errors import json_error, public_error
from services import monitor

router = APIRouter(prefix="/api/admin", tags=["monitor"], dependencies=[Depends(require_permission("systemMonitor"))])


@router.get("/monitor/db-diff")
def database_diff(request: Request):
    table = str(request.query_params.get("table") or "")
    try:
        return monitor.compare_table_detail(table)
    except ValueError as err:
        return json_error(400, str(err))
    except Exception as err:
        return public_error(err, "Could not compare this table")


@router.get("/monitor")
def resource_monitor(request: Request):
    target = request.query_params.get("target")
    if target not in monitor.COLLECTORS:
        return json_error(400, "target must be db or vm")
    try:
        return monitor.collect(target, monitor.parse_window(request.query_params))
    except Exception as err:
        return public_error(err, "Monitor collection failed")
