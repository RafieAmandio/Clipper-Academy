"""Middleware for error handling and request processing"""

import time
from typing import Callable
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from app.config.logging import get_logger
from app.core.exceptions import (
    ClipperException,
    ConfigurationError,
    VideoProcessingError,
    TranscriptionError,
    DownloadError,
    ZapCapError,
    StorageError,
    ValidationError,
    ContentAnalysisError,
)

logger = get_logger(__name__)


async def error_handler_middleware(request: Request, call_next: Callable) -> Response:
    """Global error handling middleware"""
    try:
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response
    except ClipperException as e:
        logger.error(f"Application error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "type": e.__class__.__name__,
                "detail": "An application error occurred"
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "type": "UnexpectedError",
                "detail": "An unexpected error occurred"
            }
        )


def map_exception_to_http_status(exc: ClipperException) -> int:
    """Map custom exceptions to HTTP status codes"""
    mapping = {
        ConfigurationError: 500,
        VideoProcessingError: 500,
        TranscriptionError: 500,
        DownloadError: 400,
        ZapCapError: 502,
        StorageError: 500,
        ValidationError: 400,
        ContentAnalysisError: 500,
    }
    return mapping.get(type(exc), 500)


async def clipper_exception_handler(request: Request, exc: ClipperException) -> JSONResponse:
    """Handle custom clipper exceptions"""
    status_code = map_exception_to_http_status(exc)
    logger.error(f"Clipper exception: {exc}")
    
    return JSONResponse(
        status_code=status_code,
        content={
            "error": str(exc),
            "type": exc.__class__.__name__,
        }
    ) 