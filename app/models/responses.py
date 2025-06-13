from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from app.models.enums import AspectRatio, ProcessingStatus, Platform, ContentCategory


class VideoInfo(BaseModel):
    """Video metadata information"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "duration": 120.5,
                "width": 1920,
                "height": 1080,
                "aspect_ratio": 1.78,
                "file_size": 15728640,
                "format": "mp4"
            }
        }
    )
    
    duration: float = Field(..., description="Video duration in seconds")
    width: int = Field(..., description="Video width in pixels")
    height: int = Field(..., description="Video height in pixels")
    aspect_ratio: float = Field(..., description="Video aspect ratio")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    format: Optional[str] = Field(None, description="Video format/codec")


class ClipInfo(BaseModel):
    """Information about a generated clip"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "clip_number": 1,
                "title": "Amazing Hook - Must Watch!",
                "description": "This segment contains an incredible hook that will grab viewers' attention",
                "start_time": "00:15",
                "end_time": "01:00",
                "duration": 45.0,
                "engagement_score": 8.5,
                "file_path": "/app/data/clips/clip_1234567890_1_amazing_hook.mp4",
                "file_name": "clip_1234567890_1_amazing_hook.mp4",
                "aspect_ratio": "9:16",
                "file_size": 5242880
            }
        }
    )
    
    clip_number: int = Field(..., description="Sequential clip number")
    title: str = Field(..., description="AI-generated title for the clip")
    description: str = Field(..., description="Brief description of why this segment is engaging")
    start_time: str = Field(..., description="Start time in MM:SS format")
    end_time: str = Field(..., description="End time in MM:SS format")
    duration: float = Field(..., description="Clip duration in seconds")
    engagement_score: float = Field(..., ge=0, le=10, description="AI engagement score (0-10)")
    file_path: str = Field(..., description="Full path to the generated clip file")
    file_name: str = Field(..., description="Clip filename")
    aspect_ratio: str = Field(..., description="Clip aspect ratio")
    file_size: Optional[int] = Field(None, description="Clip file size in bytes")
    
    # Optional ZapCap results
    zapcap_result: Optional[Dict[str, Any]] = Field(None, description="ZapCap processing results")
    zapcap_error: Optional[str] = Field(None, description="ZapCap processing error if any")


class TranscriptionResult(BaseModel):
    """Audio transcription results"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "Welcome to our amazing video content where we explore incredible topics...",
                "language": "en",
                "duration": 120.5,
                "word_count": 45,
                "segments": [
                    {
                        "start": 0.0,
                        "end": 5.2,
                        "text": "Welcome to our amazing video content"
                    }
                ],
                "confidence": 0.95
            }
        }
    )
    
    text: str = Field(..., description="Full transcribed text")
    language: str = Field(..., description="Detected/specified language")
    duration: float = Field(..., description="Audio duration in seconds")
    word_count: int = Field(..., description="Number of words in transcription")
    segments: List[Dict[str, Any]] = Field(default=[], description="Timestamped segments")
    words: List[Dict[str, Any]] = Field(default=[], description="Word-level timestamps")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="Transcription confidence score")


class ContentAnalysisResult(BaseModel):
    """Content analysis results"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "platform": "tiktok",
                "post_id": "1234567890",
                "summary": "Hook: Amazing opening with...\nPlot: Content flows through...",
                "category": "Entertainment",
                "engagement_metrics": {
                    "like_count": 15420,
                    "view_count": 234567,
                    "comment_count": 892
                },
                "transcript": "Welcome to our amazing content...",
                "keyframes_analyzed": 15
            }
        }
    )
    
    platform: Platform = Field(..., description="Source platform")
    post_id: str = Field(..., description="Post identifier")
    summary: str = Field(..., description="AI-generated content summary")
    category: str = Field(..., description="Content category")
    engagement_metrics: Optional[Dict[str, Any]] = Field(None, description="Social media metrics")
    transcript: str = Field(..., description="Full transcript")
    keyframes_analyzed: int = Field(..., description="Number of keyframes analyzed")
    analysis_time: Optional[float] = Field(None, description="Analysis processing time")


class ZapCapResult(BaseModel):
    """ZapCap processing results"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "video_id": "zapcap_video_123",
                "task_id": "zapcap_task_456",
                "status": "completed",
                "captioned_video_name": "video_captioned_1234567890.mp4",
                "captioned_video_path": "/app/data/results/video_captioned_1234567890.mp4",
                "processing_time": 45.2,
                "template_used": "d2018215-2125-41c1-940e-f13b411fff5c"
            }
        }
    )
    
    video_id: str = Field(..., description="ZapCap video ID")
    task_id: str = Field(..., description="ZapCap task ID")
    status: ProcessingStatus = Field(..., description="Processing status")
    captioned_video_name: Optional[str] = Field(None, description="Name of captioned video file")
    captioned_video_path: Optional[str] = Field(None, description="Path to captioned video file")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")
    template_used: Optional[str] = Field(None, description="ZapCap template ID used")
    error_message: Optional[str] = Field(None, description="Error message if processing failed")


class ProcessingSummary(BaseModel):
    """Summary of video processing results"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "video_duration": 120.5,
                "clips_created": 3,
                "total_clip_duration": 135.0,
                "zapcap_processed": True,
                "aspect_ratio": "9:16",
                "processing_time": 87.3,
                "transcription_time": 23.1,
                "clip_generation_time": 41.8,
                "zapcap_time": 22.4
            }
        }
    )
    
    video_duration: float = Field(..., description="Original video duration")
    clips_created: int = Field(..., description="Number of clips created")
    total_clip_duration: float = Field(..., description="Total duration of all clips")
    zapcap_processed: bool = Field(..., description="Whether ZapCap processing was used")
    aspect_ratio: str = Field(..., description="Target aspect ratio used")
    processing_time: float = Field(..., description="Total processing time")
    transcription_time: Optional[float] = Field(None, description="Time spent on transcription")
    clip_generation_time: Optional[float] = Field(None, description="Time spent generating clips")
    zapcap_time: Optional[float] = Field(None, description="Time spent on ZapCap processing")


class ClipResponse(BaseModel):
    """Main response for clip generation operations"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Successfully created 3 clips from video",
                "total_clips": 3,
                "clips": [],
                "original_video_info": {},
                "transcript": "Full video transcript...",
                "processing_summary": {},
                "request_id": "req_1234567890"
            }
        }
    )
    
    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Human-readable status message")
    total_clips: int = Field(..., description="Total number of clips created")
    clips: List[ClipInfo] = Field(..., description="List of generated clips")
    original_video_info: VideoInfo = Field(..., description="Original video metadata")
    transcript: str = Field(..., description="Full video transcript")
    processing_summary: ProcessingSummary = Field(..., description="Processing statistics")
    request_id: Optional[str] = Field(None, description="Unique request identifier")
    
    # Optional fields for different input types
    source_url: Optional[str] = Field(None, description="Source URL if processed from URL")
    source_file: Optional[str] = Field(None, description="Source file path if processed from file")
    platform: Optional[Platform] = Field(None, description="Platform if processed from social media")


class TranscriptionResponse(BaseModel):
    """Response for transcription-only operations"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Audio transcribed successfully",
                "transcription": {},
                "processing_time": 23.1
            }
        }
    )
    
    success: bool = Field(..., description="Whether transcription succeeded")
    message: str = Field(..., description="Status message")
    transcription: TranscriptionResult = Field(..., description="Transcription results")
    processing_time: float = Field(..., description="Processing time in seconds")


class AnalysisResponse(BaseModel):
    """Response for content analysis operations"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Content analyzed successfully",
                "analysis": {},
                "processing_time": 34.7
            }
        }
    )
    
    success: bool = Field(..., description="Whether analysis succeeded")
    message: str = Field(..., description="Status message")
    analysis: ContentAnalysisResult = Field(..., description="Analysis results")
    processing_time: float = Field(..., description="Processing time in seconds")


class ZapCapResponse(BaseModel):
    """Response for ZapCap processing operations"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Video captioning completed successfully",
                "zapcap_result": {},
                "processing_time": 45.2
            }
        }
    )
    
    success: bool = Field(..., description="Whether ZapCap processing succeeded")
    message: str = Field(..., description="Status message")
    zapcap_result: ZapCapResult = Field(..., description="ZapCap processing results")
    processing_time: float = Field(..., description="Processing time in seconds")


class ErrorResponse(BaseModel):
    """Error response model"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "error": "VideoProcessingError",
                "message": "Failed to process video: FFmpeg error",
                "details": "FFmpeg command failed with return code 1",
                "timestamp": "2024-01-01T12:00:00Z"
            }
        }
    )
    
    success: bool = Field(False, description="Always false for errors")
    error: str = Field(..., description="Error type/class")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[str] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")


class HealthResponse(BaseModel):
    """Health check response"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "service": "Auto Clipper API",
                "version": "1.0.0",
                "timestamp": "2024-01-01T12:00:00Z",
                "dependencies": {
                    "ffmpeg": True,
                    "ffprobe": True,
                    "yt_dlp": True,
                    "openai_api_key": True,
                    "zapcap_api_key": True
                },
                "directories": {
                    "upload_dir": True,
                    "clips_dir": True,
                    "temp_dir": True,
                    "results_dir": True
                }
            }
        }
    )
    
    status: str = Field(..., description="Overall system status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    dependencies: Dict[str, bool] = Field(..., description="External dependency status")
    directories: Dict[str, bool] = Field(..., description="Required directory status")
    uptime: Optional[float] = Field(None, description="Service uptime in seconds")


class BatchClipResponse(BaseModel):
    """Response for batch clip processing"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Batch processing completed",
                "total_urls": 3,
                "successful": 2,
                "failed": 1,
                "results": [],
                "processing_time": 156.7
            }
        }
    )
    
    success: bool = Field(..., description="Whether batch processing succeeded")
    message: str = Field(..., description="Status message")
    total_urls: int = Field(..., description="Total URLs processed")
    successful: int = Field(..., description="Number of successful processings")
    failed: int = Field(..., description="Number of failed processings")
    results: List[Union[ClipResponse, ErrorResponse]] = Field(..., description="Individual results")
    processing_time: float = Field(..., description="Total batch processing time") 