"""
GuardianLine Core Application Server.
Mounts:
- Classifier API Router (/tools/classify_caller)
- Family Dashboard Router (/dashboard and /gui)
- Event Ingestion Router (/events/call_finalized)
"""

from fastapi import FastAPI
from app.api.classifier_router import router as classifier_router
from app.core.gui import router as dashboard_router
from app.notify.listener import router as events_router

def create_app() -> FastAPI:
    app = FastAPI(
        title="GuardianLine Telecom Shield",
        description="Autonomous Voice Scam Defense & Elderly Call Screening System",
        version="1.0.0",
    )

    # Mount routers
    app.include_router(classifier_router)
    app.include_router(dashboard_router)
    app.include_router(events_router)

    @app.get("/healthz")
    def health_check():
        return {"status": "healthy", "service": "guardianline"}

    return app

app = create_app()
