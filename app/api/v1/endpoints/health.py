from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from datetime import datetime
import os
import subprocess
import time
from typing import Dict, Any

from app.core.dependencies import get_settings
from app.config.settings import Settings
from app.models.responses import HealthResponse

router = APIRouter(tags=["health"])

# Track service start time for uptime calculation
_service_start_time = time.time()


@router.get("/status", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Basic health check endpoint"""
    try:
        # Check if essential dependencies are available
        dependencies = {
            "ffmpeg": _check_ffmpeg(),
            "ffprobe": _check_ffprobe(),
            "yt_dlp": _check_yt_dlp(),
            "openai_api_key": bool(settings.openai_api_key),
            "zapcap_api_key": bool(settings.zapcap_api_key)
        }
        
        # Check if required directories exist
        directories = {
            "upload_dir": os.path.exists(settings.upload_dir),
            "clips_dir": os.path.exists(settings.clips_dir),
            "temp_dir": os.path.exists(settings.temp_dir),
            "results_dir": os.path.exists(settings.results_dir)
        }
        
        # Determine overall status
        all_dependencies_ok = all(dependencies.values())
        all_directories_ok = all(directories.values())
        overall_status = "healthy" if all_dependencies_ok and all_directories_ok else "unhealthy"
        
        return HealthResponse(
            status=overall_status,
            service="Auto Clipper API",
            version="1.0.0",
            timestamp=datetime.utcnow(),
            dependencies=dependencies,
            directories=directories,
            uptime=time.time() - _service_start_time
        )
        
    except Exception as e:
        return HealthResponse(
            status="error",
            service="Auto Clipper API",
            version="1.0.0",
            timestamp=datetime.utcnow(),
            dependencies={},
            directories={},
            uptime=time.time() - _service_start_time
        )


@router.get("/dependencies")
async def check_dependencies() -> JSONResponse:
    """Check all external dependencies"""
    dependencies = {
        "ffmpeg": _check_ffmpeg(),
        "ffprobe": _check_ffprobe(),
        "yt_dlp": _check_yt_dlp(),
        "python": True,  # If we're running, Python is available
    }
    
    all_ok = all(dependencies.values())
    status_code = 200 if all_ok else 503
    
    return JSONResponse(
        status_code=status_code,
        content={
            "dependencies": dependencies,
            "all_ok": all_ok,
            "message": "All dependencies available" if all_ok else "Some dependencies missing"
        }
    )


@router.get("/directories")
async def check_directories_endpoint(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """Check status of required directories"""
    directories = {
        "upload_dir": os.path.exists(settings.upload_dir),
        "clips_dir": os.path.exists(settings.clips_dir),
        "temp_dir": os.path.exists(settings.temp_dir),
        "results_dir": os.path.exists(settings.results_dir)
    }
    
    all_ok = all(directories.values())
    status_code = 200 if all_ok else 503
    
    return JSONResponse(
        status_code=status_code,
        content={
            "directories": directories,
            "all_ok": all_ok,
            "message": "All directories exist" if all_ok else "Some directories missing"
        }
    )


@router.get("/info")
async def service_info() -> Dict[str, Any]:
    """Get detailed service information"""
    return {
        "service": "Auto Clipper API",
        "version": "1.0.0",
        "description": "AI-powered social media video clipping service",
        "features": [
            "Social media video downloading (TikTok, Instagram)",
            "AI-powered transcript analysis",
            "Automated clip generation",
            "ZapCap caption integration",
            "Multi-format video processing",
            "Batch processing support"
        ],
        "requirements": {
            "python": ">=3.11",
            "ffmpeg": "latest",
            "yt-dlp": "latest",
            "openai_api_key": "required",
            "zapcap_api_key": "optional"
        },
        "supported_platforms": ["TikTok", "Instagram"],
        "supported_formats": {
            "input": ["mp4", "mov", "avi", "mkv", "webm"],
            "output": ["mp4"]
        },
        "aspect_ratios": ["9:16", "16:9", "1:1", "4:5"],
        "endpoints": {
            "clips": "/api/v1/clips/",
            "analysis": "/api/v1/analysis/",
            "health": "/api/v1/health/"
        }
    }


@router.get("/metrics")
async def service_metrics() -> Dict[str, Any]:
    """Get service performance metrics"""
    import psutil
    
    try:
        # Get system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "uptime_seconds": time.time() - _service_start_time,
            "system": {
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": memory.percent,
                "memory_available_mb": memory.available // (1024 * 1024),
                "disk_usage_percent": disk.percent,
                "disk_free_gb": disk.free // (1024 ** 3)
            },
            "service": {
                "status": "running",
                "process_id": os.getpid(),
                "version": "1.0.0"
            }
        }
    except ImportError:
        return {
            "uptime_seconds": time.time() - _service_start_time,
            "system": {
                "message": "psutil not available - system metrics unavailable"
            },
            "service": {
                "status": "running",
                "process_id": os.getpid(),
                "version": "1.0.0"
            }
        }


def _check_ffmpeg() -> bool:
    """Check if FFmpeg is available"""
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      capture_output=True, check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_ffprobe() -> bool:
    """Check if FFprobe is available"""
    try:
        subprocess.run(['ffprobe', '-version'], 
                      capture_output=True, check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_yt_dlp() -> bool:
    """Check if yt-dlp is available"""
    try:
        import yt_dlp
        return True
    except ImportError:
        return False 