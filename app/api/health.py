# -*- coding: utf-8 -*-
from fastapi import APIRouter
import httpx
import psutil
from datetime import datetime, timezone

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health_check():
    services = {"wingo": "online"}
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get("http://127.0.0.1:5678/healthz")
            services["n8n"] = "online" if r.status_code < 400 else "offline"
    except:
        services["n8n"] = "offline"

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            services["ollama"] = "online" if r.status_code < 400 else "offline"
    except:
        services["ollama"] = "offline"

    return {
        "status": "ok" if all(v == "online" for v in services.values()) else "degraded",
        "version": "4.0.0",
        "memory_mb": round(psutil.Process().memory_info().rss / 1024 / 1024, 1),
        "services": services,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
