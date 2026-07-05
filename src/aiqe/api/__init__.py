"""
AIQE FastAPI Layer.

REST API for enterprise and GitHub Action modes.
Provides the same capabilities as the CLI through HTTP endpoints.

Public API:
    create_app  — factory function for the FastAPI app
    get_app     — singleton accessor used by uvicorn
    run         — start the uvicorn server

Route prefix: /api/v1
Docs:         /docs (Swagger UI)
ReDoc:        /redoc
OpenAPI:      /openapi.json
"""

from aiqe.api.app import create_app, get_app
from aiqe.api.server import run

__all__ = ["create_app", "get_app", "run"]
