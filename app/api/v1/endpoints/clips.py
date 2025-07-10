from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from typing import Callable, Optional, Dict, Any, List
import logging
from datetime import datetime
import asyncio
import os
import glob
from pathlib import Path
import json

from app.services.auto_clipper import AutoClipperService
from app.core.dependencies import get_auto_clipper_service, get_settings
from app.models.requests import ClipFromURLRequest, ClipFromFilePathRequest
from app.models.responses import ClipResponse, ErrorResponse
from app.models.tasks import TaskResponse
from app.models.enums import AspectRatio, ZapCapLanguage, ObjectDetectionType, SmartCroppingMode
from app.core.exceptions import VideoProcessingError, TranscriptionError, ContentAnalysisError, ZapCapError
from app.services.task_manager import task_manager, TaskStatus
from app.config.settings import Settings

logger = logging.getLogger(__name__)
router = APIRouter()

async def process_clip_task(
    task_id: str,
    service: AutoClipperService,
    process_func: Callable,
    request: Request,
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

@router.post("/upload", response_model=TaskResponse, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def create_clips_from_upload(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(..., description="Video file to process"),
    use_zapcap: bool = Form(False),
    zapcap_template_id: Optional[str] = Form(None),
    zapcap_language: str = Form("en"),
    aspect_ratio: str = Form("9:16"),
    max_clips: int = Form(5),
    enable_object_detection: bool = Form(True, description="Enable object detection for smart cropping"),
    object_detection_type: str = Form("face", description="Object detection type: face, none"),
    smart_cropping_mode: str = Form("auto", description="Smart cropping mode: object_centered, center_crop, auto"),
    max_detection_frames: int = Form(10, ge=5, le=30, description="Maximum frames to analyze for object detection"),
    service: AutoClipperService = Depends(get_auto_clipper_service)
) -> TaskResponse:
    """
    Create clips from uploaded video file (async) with optional object detection
    
    This endpoint accepts a video file upload and starts an asynchronous task
    to process it into short clips suitable for social media platforms.
    Optionally uses face detection to center the talking person in clips.
    Supports grid layout for multiple faces (video call style).
    
    Returns a task ID that can be used to check the processing status.
    """
    try:
        safe_filename = file.filename.encode('utf-8', 'replace').decode('utf-8') if file.filename else ''
        logger.info(f"Starting async processing for uploaded file: {safe_filename}")
        
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")
            
        if file.content_type and not file.content_type.startswith('video/'):
            raise HTTPException(status_code=400, detail="File must be a video")
        
        # Parse enum values
        try:
            aspect_ratio_enum = AspectRatio(aspect_ratio)
            zapcap_language_enum = ZapCapLanguage(zapcap_language)
            object_detection_enum = ObjectDetectionType(object_detection_type)
            smart_cropping_enum = SmartCroppingMode(smart_cropping_mode)
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
                "max_clips": max_clips,
                "enable_object_detection": enable_object_detection,
                "object_detection_type": object_detection_type,
                "smart_cropping_mode": smart_cropping_mode,
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
            max_clips=max_clips,
            enable_object_detection=enable_object_detection,
            object_detection_type=object_detection_enum.value,
            smart_cropping_mode=smart_cropping_enum.value,
            max_detection_frames=max_detection_frames,
            request=request
        )
        
        # Return task information
        task = await task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=500, detail="Task not found after creation.")
        return TaskResponse(
            id=task['id'],
            type=task['type'],
            status=task['status'],
            created_at=task['created_at'],
            updated_at=task['updated_at'],
            metadata=task.get('metadata', {}),
            result=task.get('result'),
            error=task.get('error')
        )
        
    except Exception as e:
        logger.error(f"Failed to start clip processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/url", response_model=TaskResponse, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def create_clips_from_url(
    background_tasks: BackgroundTasks,
    request: Request,
    url: str = Form(..., description="URL of the video to process"),
    use_zapcap: bool = Form(False),
    zapcap_template_id: Optional[str] = Form(None),
    zapcap_language: str = Form("en"),
    aspect_ratio: str = Form("9:16"),
    max_clips: int = Form(5),
    enable_object_detection: bool = Form(True, description="Enable object detection for smart cropping"),
    object_detection_type: str = Form("face", description="Object detection type: face, none"),
    smart_cropping_mode: str = Form("auto", description="Smart cropping mode: object_centered, center_crop, auto"),
    max_detection_frames: int = Form(10, ge=5, le=30, description="Maximum frames to analyze for object detection"),
    service: AutoClipperService = Depends(get_auto_clipper_service)
) -> TaskResponse:
    """
    Create clips from social media URL (async) with optional object detection
    
    This endpoint starts an asynchronous task to download and process
    a video from a supported social media platform.
    Optionally uses face detection to center the talking person in clips.
    Supports grid layout for multiple faces (video call style).
    
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
            object_detection_enum = ObjectDetectionType(object_detection_type)
            smart_cropping_enum = SmartCroppingMode(smart_cropping_mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(e)}")
        
        # Create task
        task_id = await task_manager.create_task(
            "clip_url",
            metadata={
                "url": url,
                "use_zapcap": use_zapcap,
                "aspect_ratio": aspect_ratio,
                "max_clips": max_clips,
                "enable_object_detection": enable_object_detection,
                "object_detection_type": object_detection_type,
                "smart_cropping_mode": smart_cropping_mode,
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
            max_clips=max_clips,
            enable_object_detection=enable_object_detection,
            object_detection_type=object_detection_enum.value,
            smart_cropping_mode=smart_cropping_enum.value,
            max_detection_frames=max_detection_frames,
            request=request
        )
        
        # Return task information
        task = await task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=500, detail="Task not found after creation.")
        return TaskResponse(
            id=task['id'],
            type=task['type'],
            status=task['status'],
            created_at=task['created_at'],
            updated_at=task['updated_at'],
            metadata=task.get('metadata', {}),
            result=task.get('result'),
            error=task.get('error')
        )
        
    except Exception as e:
        logger.error(f"Failed to start URL processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/file", response_model=TaskResponse, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def create_clips_from_file_path(
    background_tasks: BackgroundTasks,
    request: Request,
    req: ClipFromFilePathRequest,
    service: AutoClipperService = Depends(get_auto_clipper_service)
) -> TaskResponse:
    """
    Create clips from local file path (async) with optional object detection
    
    This endpoint starts an asynchronous task to process a video file
    from a local file path.
    Optionally uses object detection to center the talking person in clips.
    
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
                "max_clips": req.max_clips,
                "enable_object_detection": req.enable_object_detection,
                "object_detection_type": req.object_detection_type.value,
                "smart_cropping_mode": req.smart_cropping_mode.value
            }
        )
        
        # Start background task
        background_tasks.add_task(
            process_clip_task,
            task_id=task_id,
            service=service,
            process_func=service.process_video,
            video_input=req.file_path,
            use_zapcap=req.use_zapcap,
            zapcap_template_id=req.zapcap_template_id,
            aspect_ratio=req.aspect_ratio.value,
            max_clips=req.max_clips,
            enable_object_detection=req.enable_object_detection,
            object_detection_type=req.object_detection_type.value,
            smart_cropping_mode=req.smart_cropping_mode.value,
            max_detection_frames=req.max_detection_frames,
            request=request
        )
        
        # Return task information
        task = await task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=500, detail="Task not found after creation.")
        return TaskResponse(
            id=task['id'],
            type=task['type'],
            status=task['status'],
            created_at=task['created_at'],
            updated_at=task['updated_at'],
            metadata=task.get('metadata', {}),
            result=task.get('result'),
            error=task.get('error')
        )
        
    except Exception as e:
        logger.error(f"Failed to start file processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metadata", response_model=List[Dict[str, Any]])
async def get_clips_metadata(settings: Settings = Depends(get_settings)):
    """
    Get clips metadata from JSON files
    
    Returns the contents of all clips_metadata_*.json files in the results directory.
    This provides the full clip information including titles, descriptions, scores, and URLs.
    """
    try:
        all_clips = []
        
        # Find all clips_metadata_*.json files in results directory
        pattern = os.path.join(settings.results_dir, "clips_metadata_*.json")
        metadata_files = glob.glob(pattern)
        
        logger.info(f"Found {len(metadata_files)} metadata files: {metadata_files}")
        
        for metadata_file in metadata_files:
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    clips_data = json.load(f)
                    if isinstance(clips_data, list):
                        all_clips.extend(clips_data)
                    else:
                        all_clips.append(clips_data)
                logger.info(f"Loaded {len(clips_data) if isinstance(clips_data, list) else 1} clips from {metadata_file}")
            except Exception as e:
                logger.error(f"Error loading metadata file {metadata_file}: {e}")
                continue
        
        # Sort by creation time (newest first) - use clip_number as fallback
        all_clips.sort(key=lambda x: x.get("clip_number", 0), reverse=True)
        
        logger.info(f"Returning {len(all_clips)} total clips from metadata")
        return all_clips
        
    except Exception as e:
        logger.error(f"Failed to get clips metadata: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get clips metadata: {str(e)}")

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