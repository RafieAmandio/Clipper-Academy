from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import logging
from datetime import datetime
import asyncio

from app.services.auto_clipper import AutoClipperService
from app.core.dependencies import get_auto_clipper_service
from app.models.requests import ClipFromURLRequest, ClipFromFilePathRequest
from app.models.responses import ClipResponse, ErrorResponse
from app.models.tasks import TaskResponse
from app.models.enums import AspectRatio, ZapCapLanguage
from app.core.exceptions import VideoProcessingError, TranscriptionError, ContentAnalysisError, ZapCapError
from app.services.task_manager import task_manager, TaskStatus

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
    request: Request,
    req: ClipFromURLRequest,
    service: AutoClipperService = Depends(get_auto_clipper_service)
) -> TaskResponse:
    """
    Create clips from social media URL (async)
    
    This endpoint starts an asynchronous task to download and process
    a video from a supported social media platform.
    
    Returns a task ID that can be used to check the processing status.
    """
    try:
        logger.info(f"Starting async processing for URL: {req.url}")
        
        # Create task
        task_id = await task_manager.create_task(
            "clip_url",
            metadata={
                "url": str(req.url),
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
            process_func=service.create_clips_from_url,
            url=str(req.url),
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
        logger.error(f"Failed to start URL processing: {e}")
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