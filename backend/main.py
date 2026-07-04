import asyncio
import sys

# Playwright's async API spawns Chromium as a subprocess, which
# SelectorEventLoop (uvicorn's default on Windows) cannot do. Must be set
# before uvicorn (or anything else) creates an event loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import execute, generate

app = FastAPI(title="Requirements-to-CodeEngine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router)
app.include_router(execute.router)

if __name__ == "__main__":
    # Run as `python main.py`, not `uvicorn main:app --reload`.
    # The CLI form creates uvicorn's event loop before it ever imports this
    # module (the "main:app" string is loaded lazily inside the already-running
    # loop), so the Proactor policy set above would be applied too late.
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
