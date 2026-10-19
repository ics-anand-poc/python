import logging
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import env, env_int, frontend_origins
from core.errors import install_error_handlers
from core.security import install_traffic_controls
from core.tokens import require_secret_in_production
from routers import ROUTERS
from services import storage

log = logging.getLogger("talentscope")
RETENTION_INTERVAL_S = 6 * 3600


def run_retention() -> None:
    days = env_int("RECORDING_RETENTION_DAYS", 0)
    while days > 0:
        try:
            removed = storage.prune_older_than("recordings", days)
            if removed:
                log.info("retention: removed %s recordings older than %s days", removed, days)
        except Exception as err:
            log.warning("retention sweep failed: %s", err)
        time.sleep(RETENTION_INTERVAL_S)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    anyio.to_thread.current_default_thread_limiter().total_tokens = env_int("API_THREADS", 24)
    threading.Thread(target=run_retention, daemon=True, name="retention").start()
    yield


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
require_secret_in_production()

docs_enabled = env("ENABLE_API_DOCS") == "1"
app = FastAPI(title="TalentScope API", version="1.0.0", lifespan=lifespan,
              docs_url="/docs" if docs_enabled else None, redoc_url=None, openapi_url="/openapi.json" if docs_enabled else None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
install_error_handlers(app)
install_traffic_controls(app)


for router in ROUTERS:
    app.include_router(router)
