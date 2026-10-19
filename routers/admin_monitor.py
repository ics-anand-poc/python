from fastapi import APIRouter, Depends, Request

from core.auth import require_admin
from core.errors import json_error, public_error
from services import monitor

router = APIRouter(prefix="/api/admin", tags=["monitor"], dependencies=[Depends(require_admin)])


@router.get("/monitor")
def resource_monitor(request: Request):
    target = request.query_params.get("target")
    if target not in monitor.COLLECTORS:
        return json_error(400, "target must be db or vm")
    try:
        return monitor.collect(target)
    except Exception as err:
        return public_error(err, "Monitor collection failed")
