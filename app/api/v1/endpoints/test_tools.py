from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Request, Query
from app.config.settings import Settings
from app.core.dependencies import get_settings, get_auto_clipper_service, get_video_processing_service
from typing import List, Optional
import os
import json
import time
from app.services.auto_clipper import AutoClipperService
from app.services.video_processing import VideoProcessingService
import logging
import shutil
import glob

router = APIRouter(tags=["test-tools"])

# Dependency to ensure test mode is enabled
def require_test_mode(settings: Settings = Depends(get_settings)):
    if not getattr(settings, "TEST_MODE", False):
        raise HTTPException(status_code=403, detail="Test endpoints are disabled.")
    return settings

ARTIFACTS_BASE_DIR = "data/test_artifacts"

@router.post("/artifacts/upload", summary="[TEST ONLY] Upload test artifacts for a video")
async def upload_artifacts(
    video_id: str,
    transcript: Optional[UploadFile] = File(None),
    analyzed_transcript: Optional[UploadFile] = File(None),
    timestamped_transcript: Optional[UploadFile] = File(None),
    settings: Settings = Depends(require_test_mode)
):
    """
    [TEST ONLY] Upload one or more artifacts (transcript, analyzed transcript, timestamped transcript) for a video.
    Artifacts are saved under a test-only directory for later retrieval and testing.
    """
    os.makedirs(os.path.join(ARTIFACTS_BASE_DIR, video_id), exist_ok=True)
    saved = []
    for name, file in [("transcript.txt", transcript), ("analyzed.json", analyzed_transcript), ("timestamped.json", timestamped_transcript)]:
        if file:
            dest = os.path.join(ARTIFACTS_BASE_DIR, video_id, name)
            with open(dest, "wb") as f:
                f.write(await file.read())
            saved.append(name)
    if not saved:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    return {"success": True, "saved": saved}

@router.get("/artifacts/{video_id}", summary="[TEST ONLY] List available artifacts for a video")
async def list_artifacts(
    video_id: str,
    settings: Settings = Depends(require_test_mode)
):
    """
    [TEST ONLY] List available artifacts for a given video ID.
    """
    dir_path = os.path.join(ARTIFACTS_BASE_DIR, video_id)
    if not os.path.exists(dir_path):
        return {"artifacts": []}
    return {"artifacts": os.listdir(dir_path)}

@router.get("/artifacts/{video_id}/{artifact_name}", summary="[TEST ONLY] Download a specific artifact for a video")
async def get_artifact(
    video_id: str,
    artifact_name: str,
    settings: Settings = Depends(require_test_mode)
):
    """
    [TEST ONLY] Download a specific artifact file for a video.
    """
    file_path = os.path.join(ARTIFACTS_BASE_DIR, video_id, artifact_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Artifact not found.")
    from fastapi.responses import FileResponse
    return FileResponse(file_path, filename=artifact_name)

@router.post("/clip-from-analysis", summary="[TEST ONLY] Generate clips from analyzed transcript (object detection only)")
async def clip_from_analysis(
    video_id: str,
    analyzed_name: str = "analyzed.json",
    aspect_ratio: str = "9:16",
    settings: Settings = Depends(require_test_mode),
    auto_clipper: AutoClipperService = Depends(get_auto_clipper_service),
    video_processing: VideoProcessingService = Depends(get_video_processing_service),
):
    """
    [TEST ONLY] Generate clips using a saved analyzed transcript for a video. This runs only the object detection and clipping logic, skipping external APIs.
    Also saves the transcript to the results directory if available.
    """
    logger = logging.getLogger("test_tools")
    file_path = os.path.join(ARTIFACTS_BASE_DIR, video_id, analyzed_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Analyzed transcript not found.")
    # Load analyzed transcript (should be a JSON array of segments)
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            segments = json.load(f)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid analyzed transcript JSON: {e}")
    # Save transcript if available
    transcript_saved_path = None
    transcript_src_path = os.path.join(ARTIFACTS_BASE_DIR, video_id, "transcript.txt")
    if os.path.exists(transcript_src_path):
        transcript_dst_path = os.path.join(settings.results_dir, f"{video_id}_transcript.txt")
        shutil.copyfile(transcript_src_path, transcript_dst_path)
        logger.info(f"Transcript saved to: {transcript_dst_path}")
        transcript_saved_path = transcript_dst_path
    else:
        # Check if transcript is embedded in analyzed transcript (as a field)
        if isinstance(segments, dict) and 'transcript' in segments:
            transcript_dst_path = os.path.join(settings.results_dir, f"{video_id}_transcript.json")
            with open(transcript_dst_path, "w", encoding="utf-8") as tf:
                json.dump(segments['transcript'], tf, ensure_ascii=False, indent=2)
            logger.info(f"Transcript (from JSON) saved to: {transcript_dst_path}")
            transcript_saved_path = transcript_dst_path
    # Save a copy of the analyzed transcript to the results directory for reuse
    analyzed_saved_path = os.path.join(settings.results_dir, f"{video_id}_analyzed.json")
    shutil.copyfile(file_path, analyzed_saved_path)
    logger.info(f"Analyzed transcript saved to: {analyzed_saved_path}")
    # Find the original video file (assume it's in uploads dir)
    video_path = os.path.join(settings.upload_dir, f"{video_id}.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Original video file not found.")
    # Get video info
    video_info = video_processing.get_video_info(video_path)
    results = []
    timestamp = int(time.time())
    for i, segment in enumerate(segments if isinstance(segments, list) else []):
        start_seconds = video_processing.time_to_seconds(segment['start_time'])
        end_seconds = video_processing.time_to_seconds(segment['end_time'])
        clip_duration = end_seconds - start_seconds
        if clip_duration < settings.min_clip_duration or clip_duration > settings.max_clip_duration:
            results.append({
                'clip_number': i + 1,
                'title': segment.get('title', f'Clip {i+1}'),
                'start_time': segment['start_time'],
                'end_time': segment['end_time'],
                'duration': clip_duration,
                'success': False,
                'error': f'Clip duration {clip_duration}s out of range',
            })
            continue
        safe_title = video_processing.get_safe_filename(segment.get('title', f'clip_{i+1}'))
        clip_filename = f"clip_{timestamp}_{i+1}_{safe_title}.mp4"
        clip_path = os.path.join(settings.results_dir, clip_filename)
        logger.info(f"Creating clip: {clip_path} ({start_seconds}-{end_seconds})")
        try:
            result = video_processing.create_video_clip(
                video_path,
                start_seconds,
                end_seconds,
                clip_path,
                aspect_ratio=aspect_ratio,
                enable_object_detection=True,
                object_detection_type=settings.object_detection_type,
                max_detection_frames=settings.max_detection_frames,
            )
            logger.info(f"[DEBUG] create_video_clip returned: {result}")
        except Exception as e:
            logger.error(f"[DEBUG] Exception in create_video_clip: {e}")
            results.append({
                'clip_number': i + 1,
                'title': segment.get('title', f'Clip {i+1}'),
                'start_time': segment['start_time'],
                'end_time': segment['end_time'],
                'duration': clip_duration,
                'file_name': clip_filename,
                'file_path': clip_path,
                'success': False,
                'error': str(e),
            })
            continue
        # Check for standard or grid file
        output_clip_path = clip_path
        if not os.path.exists(output_clip_path):
            grid_clip_path = clip_path.replace('.mp4', '_grid.mp4')
            if os.path.exists(grid_clip_path):
                output_clip_path = grid_clip_path
            else:
                logger.error(f"Clip file was not created: {clip_path} or {grid_clip_path}")
                results.append({
                    'clip_number': i + 1,
                    'title': segment.get('title', f'Clip {i+1}'),
                    'start_time': segment['start_time'],
                    'end_time': segment['end_time'],
                    'duration': clip_duration,
                    'file_name': clip_filename,
                    'file_path': clip_path,
                    'success': False,
                    'error': 'Clip file was not created',
                })
                continue
        rel_path = os.path.relpath(output_clip_path, settings.results_dir)
        clip_url = f"/data/results/{os.path.basename(output_clip_path)}"
        logger.info(f"Clip created: {output_clip_path}")
        results.append({
            'clip_number': i + 1,
            'title': segment.get('title', f'Clip {i+1}'),
            'start_time': segment['start_time'],
            'end_time': segment['end_time'],
            'duration': clip_duration,
            'file_name': os.path.basename(output_clip_path),
            'file_path': output_clip_path,
            'url': clip_url,
            'success': True,
            'error': None,
        })
    return {
        "success": any(r['success'] for r in results),
        "message": f"Attempted to create {len(results)} clips from analyzed transcript.",
        "results": results,
        "transcript_saved_path": transcript_saved_path,
        "analyzed_saved_path": analyzed_saved_path
    }

@router.get("/available-videos", summary="[TEST ONLY] List available processed videos for object detection testing")
async def list_available_videos(
    settings: Settings = Depends(require_test_mode),
):
    """
    [TEST ONLY] List all processed videos that have both a video file and an analyzed transcript JSON.
    """
    results_dir = settings.results_dir
    upload_dir = settings.upload_dir
    # Find all *_analyzed.json files in results_dir
    analyzed_files = glob.glob(os.path.join(results_dir, "*_analyzed.json"))
    available = []
    for analyzed_path in analyzed_files:
        video_id = os.path.basename(analyzed_path).replace("_analyzed.json", "")
        video_path = os.path.join(upload_dir, f"{video_id}.mp4")
        if os.path.exists(video_path):
            available.append({
                "video_id": video_id,
                "analyzed_path": analyzed_path,
                "video_path": video_path
            })
    return {"videos": available}

@router.post("/rerun-object-detection", summary="[TEST ONLY] Rerun object detection and clip generation for a processed video")
async def rerun_object_detection(
    video_id: str = Query(..., description="ID of the processed video to test"),
    aspect_ratio: str = Query("9:16", description="Aspect ratio for output clips"),
    enable_object_detection: bool = Query(True, description="Enable object detection for smart cropping"),
    object_detection_type: str = Query("face", description="Object detection type: face, none"),
    max_detection_frames: int = Query(10, ge=5, le=30, description="Maximum frames to analyze for object detection"),
    smart_cropping_mode: str = Query("auto", description="Smart cropping mode: object_centered, center_crop, auto"),
    max_clips: int = Query(5, ge=1, le=20, description="Maximum number of clips to generate"),
    use_zapcap: bool = Query(False, description="Use ZapCap for AI captions"),
    zapcap_language: str = Query("en", description="ZapCap caption language"),
    settings: Settings = Depends(require_test_mode),
    auto_clipper: AutoClipperService = Depends(get_auto_clipper_service),
    video_processing: VideoProcessingService = Depends(get_video_processing_service),
):
    """
    [TEST ONLY] Rerun object detection and clip generation for a processed video using saved video and analyzed transcript.
    All processing options can be customized via query parameters.
    """
    import json
    import time
    import logging
    logger = logging.getLogger("test_tools")
    analyzed_path = os.path.join(settings.results_dir, f"{video_id}_analyzed.json")
    video_path = os.path.join(settings.upload_dir, f"{video_id}.mp4")
    if not os.path.exists(analyzed_path):
        raise HTTPException(status_code=404, detail="Analyzed transcript not found.")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Original video file not found.")
    with open(analyzed_path, "r", encoding="utf-8") as f:
        try:
            segments = json.load(f)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid analyzed transcript JSON: {e}")
    results = []
    timestamp = int(time.time())
    for i, segment in enumerate(segments if isinstance(segments, list) else []):
        start_seconds = video_processing.time_to_seconds(segment['start_time'])
        end_seconds = video_processing.time_to_seconds(segment['end_time'])
        clip_duration = end_seconds - start_seconds
        if clip_duration < settings.min_clip_duration or clip_duration > settings.max_clip_duration:
            results.append({
                'clip_number': i + 1,
                'title': segment.get('title', f'Clip {i+1}'),
                'start_time': segment['start_time'],
                'end_time': segment['end_time'],
                'duration': clip_duration,
                'success': False,
                'error': f'Clip duration {clip_duration}s out of range',
            })
            continue
        safe_title = video_processing.get_safe_filename(segment.get('title', f'clip_{i+1}'))
        clip_filename = f"clip_{timestamp}_{i+1}_{safe_title}.mp4"
        clip_path = os.path.join(settings.results_dir, clip_filename)
        logger.info(f"Creating clip: {clip_path} ({start_seconds}-{end_seconds})")
        try:
            result = video_processing.create_video_clip(
                video_path,
                start_seconds,
                end_seconds,
                clip_path,
                aspect_ratio=aspect_ratio,
                enable_object_detection=True,
                object_detection_type=settings.object_detection_type,
                max_detection_frames=settings.max_detection_frames,
            )
            logger.info(f"[DEBUG] create_video_clip returned: {result}")
        except Exception as e:
            logger.error(f"[DEBUG] Exception in create_video_clip: {e}")
            results.append({
                'clip_number': i + 1,
                'title': segment.get('title', f'Clip {i+1}'),
                'start_time': segment['start_time'],
                'end_time': segment['end_time'],
                'duration': clip_duration,
                'file_name': clip_filename,
                'file_path': clip_path,
                'success': False,
                'error': str(e),
            })
            continue
        # Check for standard or grid file
        output_clip_path = clip_path
        if not os.path.exists(output_clip_path):
            grid_clip_path = clip_path.replace('.mp4', '_grid.mp4')
            if os.path.exists(grid_clip_path):
                output_clip_path = grid_clip_path
            else:
                logger.error(f"Clip file was not created: {clip_path} or {grid_clip_path}")
                results.append({
                    'clip_number': i + 1,
                    'title': segment.get('title', f'Clip {i+1}'),
                    'start_time': segment['start_time'],
                    'end_time': segment['end_time'],
                    'duration': clip_duration,
                    'file_name': clip_filename,
                    'file_path': clip_path,
                    'success': False,
                    'error': 'Clip file was not created',
                })
                continue
        rel_path = os.path.relpath(output_clip_path, settings.results_dir)
        clip_url = f"/data/results/{os.path.basename(output_clip_path)}"
        logger.info(f"Clip created: {output_clip_path}")
        results.append({
            'clip_number': i + 1,
            'title': segment.get('title', f'Clip {i+1}'),
            'start_time': segment['start_time'],
            'end_time': segment['end_time'],
            'duration': clip_duration,
            'file_name': os.path.basename(output_clip_path),
            'file_path': output_clip_path,
            'url': clip_url,
            'success': True,
            'error': None,
        })
    return {
        "success": any(r['success'] for r in results),
        "message": f"Attempted to create {len(results)} clips from analyzed transcript.",
        "results": results
    } 