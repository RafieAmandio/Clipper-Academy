from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import os
import logging
import time
from datetime import datetime

from app.core.dependencies import (
    get_settings, 
    get_content_analyzer_service, 
    get_transcription_service,
    get_zapcap_service
)
from app.config.settings import Settings
from app.services.content_analyzer import ContentAnalyzerService
from app.services.transcription import TranscriptionService
from app.services.zapcap import ZapCapService
from app.models.requests import (
    AnalyzeContentRequest, 
    TranscribeRequest, 
    ZapCapProcessRequest
)
from app.models.responses import (
    AnalysisResponse,
    TranscriptionResponse, 
    ZapCapResponse,
    ErrorResponse
)
from app.core.exceptions import (
    ContentAnalysisError,
    TranscriptionError, 
    ZapCapError,
    VideoProcessingError
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analysis"])


@router.post("/content", response_model=AnalysisResponse)
async def analyze_content(
    request: AnalyzeContentRequest,
    content_service: ContentAnalyzerService = Depends(get_content_analyzer_service)
) -> AnalysisResponse:
    """
    Analyze social media content from URL
    
    Downloads video from supported platforms (TikTok, Instagram) and performs
    AI-powered analysis including transcript generation, content categorization,
    and engagement metrics extraction.
    """
    start_time = time.time()
    
    try:
        logger.info(f"Starting content analysis for URL: {request.url}")
        
        # Download and analyze the content
        analysis_result = await content_service.analyze_content(
            url=str(request.url),
            language=request.language,
            extract_keyframes=request.extract_keyframes,
            max_keyframes=request.max_keyframes
        )
        
        processing_time = time.time() - start_time
        
        return AnalysisResponse(
            success=True,
            message="Content analyzed successfully",
            analysis=analysis_result,
            processing_time=processing_time
        )
        
    except ContentAnalysisError as e:
        logger.error(f"Content analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content analysis failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during content analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    request: TranscribeRequest,
    transcription_service: TranscriptionService = Depends(get_transcription_service)
) -> TranscriptionResponse:
    """
    Transcribe audio from video or audio file
    
    Extracts audio and generates high-quality transcript with optional
    word-level timestamps using OpenAI Whisper API.
    """
    start_time = time.time()
    
    try:
        logger.info(f"Starting transcription for file: {request.file_path}")
        
        # Check if file exists
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {request.file_path}"
            )
        
        # Perform transcription
        transcription_result = await transcription_service.transcribe_audio(
            file_path=request.file_path,
            return_timestamps=request.return_timestamps
        )
        
        processing_time = time.time() - start_time
        
        return TranscriptionResponse(
            success=True,
            message="Audio transcribed successfully",
            transcription=transcription_result,
            processing_time=processing_time
        )
        
    except TranscriptionError as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during transcription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.post("/upload-transcribe", response_model=TranscriptionResponse)
async def transcribe_uploaded_file(
    file: UploadFile = File(..., description="Audio or video file to transcribe"),
    return_timestamps: bool = True,
    transcription_service: TranscriptionService = Depends(get_transcription_service),
    settings: Settings = Depends(get_settings)
) -> TranscriptionResponse:
    """
    Upload and transcribe audio/video file
    
    Accepts file uploads and generates transcripts with optional timestamps.
    Supports various audio and video formats.
    """
    start_time = time.time()
    temp_file_path = None
    
    try:
        logger.info(f"Starting transcription for uploaded file: {file.filename}")
        
        # Validate file type
        if not file.filename or not any(file.filename.lower().endswith(ext) for ext in ['.mp3', '.wav', '.mp4', '.mov', '.avi']):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file format. Please upload audio (mp3, wav) or video (mp4, mov, avi) files."
            )
        
        # Save uploaded file temporarily
        temp_file_path = os.path.join(settings.temp_dir, f"temp_transcribe_{int(time.time())}_{file.filename}")
        
        with open(temp_file_path, "wb") as temp_file:
            content = await file.read()
            temp_file.write(content)
        
        # Perform transcription
        transcription_result = await transcription_service.transcribe_audio(
            file_path=temp_file_path,
            return_timestamps=return_timestamps
        )
        
        processing_time = time.time() - start_time
        
        return TranscriptionResponse(
            success=True,
            message=f"File '{file.filename}' transcribed successfully",
            transcription=transcription_result,
            processing_time=processing_time
        )
        
    except TranscriptionError as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during transcription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")


@router.post("/zapcap", response_model=ZapCapResponse)
async def process_with_zapcap(
    request: ZapCapProcessRequest,
    file: UploadFile = File(..., description="Video file to add captions to"),
    zapcap_service: ZapCapService = Depends(get_zapcap_service),
    settings: Settings = Depends(get_settings)
) -> ZapCapResponse:
    """
    Add captions to video using ZapCap service
    
    Uploads video to ZapCap, processes with specified template and language,
    then downloads the captioned result.
    """
    start_time = time.time()
    temp_file_path = None
    
    try:
        logger.info(f"Starting ZapCap processing for file: {file.filename}")
        
        # Validate file type
        if not file.filename or not file.filename.lower().endswith(('.mp4', '.mov', '.avi')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file format. Please upload video files (mp4, mov, avi)."
            )
        
        # Save uploaded file temporarily
        temp_file_path = os.path.join(settings.temp_dir, f"temp_zapcap_{int(time.time())}_{file.filename}")
        
        with open(temp_file_path, "wb") as temp_file:
            content = await file.read()
            temp_file.write(content)
        
        # Process with ZapCap
        zapcap_result = await zapcap_service.process_video(
            video_path=temp_file_path,
            template_id=request.template_id,
            language=request.language,
            auto_approve=request.auto_approve
        )
        
        processing_time = time.time() - start_time
        
        return ZapCapResponse(
            success=True,
            message=f"Video '{file.filename}' processed successfully with ZapCap",
            zapcap_result=zapcap_result,
            processing_time=processing_time
        )
        
    except ZapCapError as e:
        logger.error(f"ZapCap processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ZapCap processing failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during ZapCap processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")


@router.get("/formats")
async def get_supported_formats() -> Dict[str, Any]:
    """
    Get supported file formats for analysis operations
    
    Returns information about supported input formats for transcription,
    content analysis, and ZapCap processing.
    """
    return {
        "transcription": {
            "audio": [".mp3", ".wav", ".m4a", ".aac"],
            "video": [".mp4", ".mov", ".avi", ".mkv", ".webm"]
        },
        "content_analysis": {
            "platforms": ["tiktok.com", "instagram.com"],
            "video": [".mp4", ".mov", ".avi", ".mkv", ".webm"]
        },
        "zapcap": {
            "video": [".mp4", ".mov", ".avi"],
            "languages": ["en", "id", "es", "fr", "de", "pt", "it", "nl", "ru", "ja", "ko", "zh-CN", "zh-TW"]
        },
        "max_file_size_mb": 500,
        "recommended_duration": "10 seconds to 10 minutes"
    } 