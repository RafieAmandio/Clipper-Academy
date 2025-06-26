from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime
import asyncio
import os
import glob
from pathlib import Path

from app.services.auto_clipper import AutoClipperService
from app.core.dependencies import get_auto_clipper_service, get_settings
from app.models.requests import ClipFromURLRequest, ClipFromFilePathRequest
from app.models.responses import ClipResponse, ErrorResponse
from app.models.tasks import TaskResponse
from app.models.enums import AspectRatio, ZapCapLanguage
from app.core.exceptions import VideoProcessingError, TranscriptionError, ContentAnalysisError, ZapCapError
from app.services.task_manager import task_manager, TaskStatus
from app.config.settings import Settings

logger = logging.getLogger(__name__)
router = APIRouter()

async def process_clip_task(
    task_id: str,
    service: AutoClipperService,
    process_func: callable,
    request: Request = None,
    **kwargs
) -> None:
    """Background task for processing clips"""
    try:
        # Update task status to processing
        await task_manager.update_task(task_id, TaskStatus.PROCESSING)
        
        # Process the clip
        result = await process_func(**kwargs, request=request)
        
        # Update task with result
        await task_manager.update_task(
            task_id,
            TaskStatus.COMPLETED,
            result=result
        )
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        await task_manager.update_task(
            task_id,
            TaskStatus.FAILED,
            error=str(e)
        )

@router.post("/upload", response_model=TaskResponse)
async def create_clips_from_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Video file to process"),
    use_zapcap: bool = Form(False),
    zapcap_template_id: Optional[str] = Form(None),
    zapcap_language: str = Form("en"),
    aspect_ratio: str = Form("9:16"),
    max_clips: int = Form(5),
    service: AutoClipperService = Depends(get_auto_clipper_service),
    request: Request = None
) -> TaskResponse:
    """
    Create clips from uploaded video file (async)
    
    This endpoint accepts a video file upload and starts an asynchronous task
    to process it into short clips suitable for social media platforms.
    https://web2-clipper-academy-be.7b0fqh.easypanel.host/data/clips/clip_1749811681_3_The_Power_of_Dollar_Cost_Averaging.mp4
    Returns a task ID that can be used to check the processing status.
    """
    try:
        logger.info(f"Starting async processing for uploaded file: {file.filename}")
        
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")
            
        if file.content_type and not file.content_type.startswith('video/'):
            raise HTTPException(status_code=400, detail="File must be a video")
        
        # Parse enum values
        try:
            aspect_ratio_enum = AspectRatio(aspect_ratio)
            zapcap_language_enum = ZapCapLanguage(zapcap_language)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(e)}")
        
        # Save the uploaded file to disk before starting the background task
        temp_file_path = await service.video_processing_service.save_upload_file(file)
        
        # Create task
        task_id = await task_manager.create_task(
            "clip_upload",
            metadata={
                "filename": file.filename,
                "use_zapcap": use_zapcap,
                "aspect_ratio": aspect_ratio,
                "max_clips": max_clips
            }
        )
        
        # Start background task using process_video, passing the file path
        background_tasks.add_task(
            process_clip_task,
            task_id=task_id,
            service=service,
            process_func=service.process_video,
            video_input=temp_file_path,
            use_zapcap=use_zapcap,
            zapcap_template_id=zapcap_template_id,
            aspect_ratio=aspect_ratio_enum.value,
            request=request
        )
        
        # Return task information
        task = await task_manager.get_task(task_id)
        return TaskResponse(**task)
        
    except Exception as e:
        logger.error(f"Failed to start clip processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/url", response_model=TaskResponse)
async def create_clips_from_url(
    background_tasks: BackgroundTasks,
    url: str = Form(..., description="URL of the video to process"),
    use_zapcap: bool = Form(False),
    zapcap_template_id: Optional[str] = Form(None),
    zapcap_language: str = Form("en"),
    aspect_ratio: str = Form("9:16"),
    max_clips: int = Form(5),
    service: AutoClipperService = Depends(get_auto_clipper_service),
    request: Request = None
) -> TaskResponse:
    """
    Create clips from social media URL (async)
    
    This endpoint starts an asynchronous task to download and process
    a video from a supported social media platform.
    
    Returns a task ID that can be used to check the processing status.
    """
    # Basic request logging
    print("=== REQUEST RECEIVED ===")
    print(f"Method: {request.method}")
    print(f"URL: {request.url}")
    print(f"Headers: {dict(request.headers)}")
    
    # Log raw request body
    try:
        body = await request.body()
        print(f"Raw body: {body.decode()}")
    except Exception as e:
        print(f"Error reading body: {e}")
    print("======================")
    
    try:
        # Log request details
        logger.info("Received request to create clips from URL")
        logger.info(f"URL: {url}")
        logger.info(f"Content-Type: {request.headers.get('content-type')}")
        logger.info(f"Request headers: {dict(request.headers)}")
        
        logger.info(f"Starting async processing for URL: {url}")
        
        # Parse enum values
        try:
            aspect_ratio_enum = AspectRatio(aspect_ratio)
            zapcap_language_enum = ZapCapLanguage(zapcap_language)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(e)}")
        
        # Create task
        task_id = await task_manager.create_task(
            "clip_url",
            metadata={
                "url": url,
                "use_zapcap": use_zapcap,
                "aspect_ratio": aspect_ratio,
                "max_clips": max_clips
            }
        )
        
        # Start background task
        background_tasks.add_task(
            process_clip_task,
            task_id=task_id,
            service=service,
            process_func=service.process_video,
            video_input=url,
            use_zapcap=use_zapcap,
            zapcap_template_id=zapcap_template_id,
            aspect_ratio=aspect_ratio_enum.value,
            request=request
        )
        
        # Return task information
        task = await task_manager.get_task(task_id)
        return TaskResponse(**task)
        
    except Exception as e:
        logger.error(f"Failed to start URL processing: {e}")
        if hasattr(e, 'errors'):
            logger.error(f"Validation errors: {e.errors()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/file", response_model=TaskResponse)
async def create_clips_from_file_path(
    background_tasks: BackgroundTasks,
    request: Request,
    req: ClipFromFilePathRequest,
    service: AutoClipperService = Depends(get_auto_clipper_service)
) -> TaskResponse:
    """
    Create clips from local file path (async)
    
    This endpoint starts an asynchronous task to process a video file
    from a local file path.
    
    Returns a task ID that can be used to check the processing status.
    """
    try:
        logger.info(f"Starting async processing for file: {req.file_path}")
        
        # Create task
        task_id = await task_manager.create_task(
            "clip_file",
            metadata={
                "file_path": req.file_path,
                "use_zapcap": req.use_zapcap,
                "aspect_ratio": req.aspect_ratio.value,
                "max_clips": req.max_clips
            }
        )
        
        # Start background task
        background_tasks.add_task(
            process_clip_task,
            task_id=task_id,
            service=service,
            process_func=service.create_clips_from_file_path,
            file_path=req.file_path,
            use_zapcap=req.use_zapcap,
            zapcap_template_id=req.zapcap_template_id,
            zapcap_language=req.zapcap_language,
            aspect_ratio=req.aspect_ratio,
            max_clips=req.max_clips,
            request=request
        )
        
        # Return task information
        task = await task_manager.get_task(task_id)
        return TaskResponse(**task)
        
    except Exception as e:
        logger.error(f"Failed to start file processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[Dict[str, Any]])
async def list_clips(settings: Settings = Depends(get_settings)):
    """
    List all available clips
    
    Returns a list of clips stored in the results directory.
    """
    try:
        clips = []
        
        # Only check results directory for final clips
        directories = [settings.results_dir]
        
        logger.info(f"Searching for clips in directories: {directories}")
        
        for directory in directories:
            logger.info(f"Checking directory: {directory}")
            if os.path.exists(directory):
                logger.info(f"Directory exists: {directory}")
                # Find all video files
                video_extensions = ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.webm']
                
                for ext in video_extensions:
                    pattern = os.path.join(directory, ext)
                    files = glob.glob(pattern)
                    logger.info(f"Found {len(files)} files with pattern {pattern}")
                    
                    for file_path in files:
                        file_stat = os.stat(file_path)
                        file_name = os.path.basename(file_path)
                        
                        # Create relative URL for accessing the file
                        relative_path = os.path.relpath(file_path, 'data')
                        file_url = f"/data/{relative_path}"
                        
                        clips.append({
                            "id": file_name,
                            "name": file_name,
                            "path": file_path,
                            "url": file_url,
                            "size": file_stat.st_size,
                            "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                            "modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                            "directory": directory
                        })
            else:
                logger.warning(f"Directory does not exist: {directory}")
        
        # Sort by creation time (newest first)
        clips.sort(key=lambda x: x["created_at"], reverse=True)
        
        logger.info(f"Found {len(clips)} clips total")
        return clips
        
    except Exception as e:
        logger.error(f"Failed to list clips: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list clips: {str(e)}")

@router.get("/{clip_id}")
async def get_clip(clip_id: str, settings: Settings = Depends(get_settings)):
    """
    Get information about a specific clip
    
    Returns detailed information about a clip by its ID.
    """
    try:
        # Search for the clip in results directory only
        directories = [settings.results_dir]
        
        for directory in directories:
            if os.path.exists(directory):
                # Look for files that match the clip_id
                video_extensions = ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.webm']
                
                for ext in video_extensions:
                    pattern = os.path.join(directory, f"*{clip_id}*{ext}")
                    files = glob.glob(pattern)
                    
                    if files:
                        file_path = files[0]  # Take the first match
                        file_stat = os.stat(file_path)
                        file_name = os.path.basename(file_path)
                        
                        # Create relative URL for accessing the file
                        relative_path = os.path.relpath(file_path, 'data')
                        file_url = f"/data/{relative_path}"
                        
                        return {
                            "id": clip_id,
                            "name": file_name,
                            "path": file_path,
                            "url": file_url,
                            "size": file_stat.st_size,
                            "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                            "modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                            "directory": directory
                        }
        
        # Clip not found
        raise HTTPException(status_code=404, detail=f"Clip with ID '{clip_id}' not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get clip: {str(e)}") 