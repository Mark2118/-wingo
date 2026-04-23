# -*- coding: utf-8 -*-
from fastapi import APIRouter
from sqlalchemy import text
from datetime import datetime, timezone
from app.database import engine
import psutil

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health_check():
    services = {"wingo": "online"}

    # PostgreSQL
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            services["postgresql"] = "online"
    except Exception:
        services["postgresql"] = "offline"

    return {
        "status": "ok" if all(v == "online" for v in services.values()) else "degraded",
        "version": "4.0.0",
        "memory_mb": round(psutil.Process().memory_info().rss / 1024 / 1024, 1),
        "services": services,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
