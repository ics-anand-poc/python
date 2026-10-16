import time
from datetime import datetime, timezone

from fastapi import APIRouter

from core.db import get_store
from services import face, laya, llm

router = APIRouter(prefix="/api", tags=["health"])
STARTED = time.time()


@router.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime": time.time() - STARTED,
        "service": "talentscope-api",
        "database": {"up": get_store().ping()},
        "localLlm": {"url": llm.base_url(), "up": llm.is_up(), "model": llm.model_name()},
        "faceMatch": {"url": face.base_url(), "up": face.is_up()},
        "laya": {"url": laya.base_url(), "up": laya.is_up(), "model": laya.model_name()},
    }
