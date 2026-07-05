"""
AIQE API Server.

Runs the FastAPI application using uvicorn.
Called by the CLI 'aiqe serve' command (added in Step 11 extensions)
or directly: python -m aiqe.api.server
"""

from __future__ import annotations

import sys


def run(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
    log_level: str = "info",
    workers: int = 1,
) -> None:
    """
    Start the AIQE API server.

    Args:
        host: Host to bind to.
        port: Port to listen on.
        reload: Enable auto-reload for development.
        log_level: uvicorn log level.
        workers: Number of worker processes (enterprise mode).
    """
    import uvicorn

    uvicorn.run(
        "aiqe.api.app:get_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        workers=workers,
        access_log=False,  # AIQE handles its own request logging
    )


if __name__ == "__main__":
    run()
