from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time
from datetime import datetime
from fastapi.staticfiles import StaticFiles

from app.config.settings import Settings
from app.config.logging import setup_logging
from app.core.middleware import error_handler_middleware
from app.core.exceptions import ClipperException
from app.api.v1.api import api_router
from app.models.responses import ErrorResponse

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Get settings
settings = Settings()

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="AI-powered video clipping service with transcription, analysis, and automated caption generation",
    version=settings.app_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
async def request_logging_middleware(request: Request, call_next):
    """Log requests and response times"""
    start_time = time.time()
    
    logger.info(f"Request: {request.method} {request.url}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(f"Response: {response.status_code} - {process_time:.4f}s")
    
    return response


# Add custom middleware
app.middleware("http")(request_logging_middleware)
app.middleware("http")(error_handler_middleware)

# Include API router
app.include_router(
    api_router, 
    prefix="/api/v1",
    responses={
        404: {"description": "Not found"},
        500: {"description": "Internal server error"}
    }
)

# Mount /data as static files
app.mount("/data", StaticFiles(directory="data"), name="data")


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "description": "AI-powered video clipping service",
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "docs_url": "/docs" if settings.debug else "Documentation disabled in production",
        "api_prefix": "/api/v1",
        "endpoints": {
            "clips": "/api/v1/clips",
            "health": "/api/v1/health", 
            "analysis": "/api/v1/analysis"
        }
    }


@app.get("/ping")
async def ping():
    """Simple ping endpoint for basic health checks"""
    return {"message": "pong", "timestamp": datetime.now().isoformat()}


# Global exception handlers
@app.exception_handler(ClipperException)
async def clipper_exception_handler(request: Request, exc: ClipperException):
    """Handle all custom clipper exceptions"""
    logger.error(f"ClipperException: {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=str(exc),
            message=str(exc),
            error_type=exc.__class__.__name__,
            detail="Service error occurred",
            timestamp=datetime.now()
        ).dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            message="An unexpected error occurred",
            error_type="InternalServerError", 
            detail="An unexpected error occurred",
            timestamp=datetime.now()
        ).dict()
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"OpenAI API key configured: {bool(settings.openai_api_key)}")
    logger.info(f"ZapCap API key configured: {bool(settings.zapcap_api_key)}")
    
    # Create data directories if they don't exist
    import os
    directories = [
        settings.upload_dir,
        settings.clips_dir,
        settings.temp_dir,
        settings.results_dir,
        "data/logs"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")
    
    logger.info("Application startup complete")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info(f"Shutting down {settings.app_name}")
    
    # Cleanup temporary files if needed
    import os
    import shutil
    temp_dir = settings.temp_dir
    
    if os.path.exists(temp_dir):
        try:
            # Remove all files in temp directory
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.warning(f"Could not clean up {file_path}: {e}")
            
            logger.info("Temporary files cleaned up")
        except Exception as e:
            logger.warning(f"Error during temp cleanup: {e}")
    
    logger.info("Application shutdown complete")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    ) 