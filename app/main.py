# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from app.config import settings
from app.database import init_database

from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.projects import router as projects_router
from app.api.chat import router as chat_router
from app.api.preview import router as preview_router
from app.api.websocket import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    app.state.ws_connections = {}
    app.state.running_tasks = {}
    yield
    for task in getattr(app.state, "running_tasks", {}).values():
        if task and not task.done():
            task.cancel()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.debug else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(projects_router)
app.include_router(chat_router)
app.include_router(preview_router)
app.include_router(ws_router)
