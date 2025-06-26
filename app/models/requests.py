from pydantic import BaseModel, Field, HttpUrl, field_validator, ConfigDict
from typing import Optional, List, Dict, Any
from app.models.enums import AspectRatio, ZapCapLanguage, ClipQuality, ContentCategory
from datetime import datetime


class ClipFromUploadRequest(BaseModel):
    """Request model for creating clips from uploaded file"""
    use_zapcap: bool = Field(False, description="Whether to add captions using ZapCap")
    zapcap_template_id: Optional[str] = Field(None, description="Custom ZapCap template ID")
    zapcap_language: ZapCapLanguage = Field(ZapCapLanguage.ENGLISH, description="Language for captions")
    aspect_ratio: AspectRatio = Field(AspectRatio.NINE_SIXTEEN, description="Target aspect ratio for clips")
    quality: ClipQuality = Field(ClipQuality.HIGH, description="Video quality setting")
    max_clips: int = Field(5, ge=1, le=10, description="Maximum number of clips to generate")
    
    class Config:
        json_schema_extra = {
            "example": {
                "use_zapcap": False,
                "zapcap_template_id": None,
                "zapcap_language": "en",
                "aspect_ratio": "9:16",
                "quality": "high",
                "max_clips": 5
            }
        }


class ClipFromURLRequest(BaseModel):
    """Request model for creating clips from URL"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://www.tiktok.com/@user/video/1234567890",
                "use_zapcap": False,
                "zapcap_template_id": "d2018215-2125-41c1-940e-f13b411fff5c",
                "aspect_ratio": "9:16",
                "max_clips": 5,
                "zapcap_language": "en"
            }
        }
    )
    
    url: HttpUrl = Field(..., description="Social media URL to download and process")
    use_zapcap: bool = Field(False, description="Whether to add captions using ZapCap service")
    zapcap_template_id: Optional[str] = Field(None, description="Custom ZapCap template ID")
    aspect_ratio: AspectRatio = Field(AspectRatio.NINE_SIXTEEN, description="Output aspect ratio")
    max_clips: int = Field(5, ge=1, le=10, description="Maximum number of clips to generate")
    zapcap_language: ZapCapLanguage = Field(ZapCapLanguage.ENGLISH, description="Language for captions")
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        """Validate that URL is from a supported platform"""
        url_str = str(v)
        supported_platforms = ['tiktok.com', 'instagram.com']
        if not any(platform in url_str.lower() for platform in supported_platforms):
            raise ValueError(f'URL must be from a supported platform: {supported_platforms}')
        return v


class ClipFromFilePathRequest(BaseModel):
    """Request model for creating clips from local file path"""
    file_path: str = Field(..., description="Local path to video file")
    use_zapcap: bool = Field(False, description="Whether to add captions using ZapCap")
    zapcap_template_id: Optional[str] = Field(None, description="Custom ZapCap template ID")
    zapcap_language: ZapCapLanguage = Field(ZapCapLanguage.ENGLISH, description="Language for captions")
    aspect_ratio: AspectRatio = Field(AspectRatio.NINE_SIXTEEN, description="Target aspect ratio for clips")
    quality: ClipQuality = Field(ClipQuality.HIGH, description="Video quality setting")
    max_clips: int = Field(5, ge=1, le=10, description="Maximum number of clips to generate")
    
    @field_validator('file_path')
    @classmethod
    def validate_file_path(cls, v):
        """Validate file path format and extension"""
        if not v or not isinstance(v, str):
            raise ValueError('File path must be a non-empty string')
        
        supported_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
        if not any(v.lower().endswith(ext) for ext in supported_extensions):
            raise ValueError(f'File must have a supported extension: {supported_extensions}')
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_path": "/path/to/video.mp4",
                "use_zapcap": False,
                "zapcap_template_id": None,
                "zapcap_language": "en",
                "aspect_ratio": "9:16",
                "quality": "high",
                "max_clips": 5
            }
        }


class TranscribeRequest(BaseModel):
    """Request model for audio transcription"""
    include_timestamps: bool = Field(True, description="Include word-level timestamps")
    language: Optional[str] = Field(None, description="Language code (auto-detect if None)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "include_timestamps": True,
                "language": None
            }
        }


class AnalyzeContentRequest(BaseModel):
    """Request model for content analysis"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://www.tiktok.com/@user/video/1234567890",
                "language": "en",
                "extract_keyframes": True,
                "max_keyframes": 15
            }
        }
    )
    
    url: HttpUrl = Field(..., description="Social media URL to analyze")
    language: str = Field("en", description="Language for analysis (en/id)")
    extract_keyframes: bool = Field(True, description="Whether to extract keyframes")
    max_keyframes: int = Field(15, description="Maximum number of keyframes to extract")


class ZapCapProcessRequest(BaseModel):
    """Request model for ZapCap caption processing"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "template_id": "d2018215-2125-41c1-940e-f13b411fff5c",
                "language": "en",
                "auto_approve": True
            }
        }
    )
    
    template_id: Optional[str] = Field(None, description="ZapCap template ID")
    language: ZapCapLanguage = Field(ZapCapLanguage.ENGLISH, description="Caption language")
    auto_approve: bool = Field(True, description="Whether to auto-approve captions")


class BatchProcessRequest(BaseModel):
    """Request model for batch processing multiple videos"""
    urls: List[HttpUrl] = Field(..., min_items=1, max_items=10, description="List of video URLs")
    use_zapcap: bool = Field(False, description="Whether to add captions using ZapCap")
    zapcap_template_id: Optional[str] = Field(None, description="Custom ZapCap template ID")
    zapcap_language: ZapCapLanguage = Field(ZapCapLanguage.ENGLISH, description="Language for captions")
    aspect_ratio: AspectRatio = Field(AspectRatio.NINE_SIXTEEN, description="Target aspect ratio for clips")
    quality: ClipQuality = Field(ClipQuality.HIGH, description="Video quality setting")
    max_clips_per_video: int = Field(3, ge=1, le=5, description="Maximum clips per video")
    
    class Config:
        json_schema_extra = {
            "example": {
                "urls": [
                    "https://www.tiktok.com/@user/video/1234567890",
                    "https://www.instagram.com/p/ABCDEFGHIJ/"
                ],
                "use_zapcap": False,
                "zapcap_template_id": None,
                "zapcap_language": "en",
                "aspect_ratio": "9:16",
                "quality": "high",
                "max_clips_per_video": 3
            }
        }


class ClipSegmentRequest(BaseModel):
    """Request model for custom clip segments"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_path": "/path/to/video.mp4",
                "segments": [
                    {
                        "start_time": "00:15",
                        "end_time": "01:00",
                        "title": "Custom Clip 1"
                    },
                    {
                        "start_time": "02:30",
                        "end_time": "03:15",
                        "title": "Custom Clip 2"
                    }
                ],
                "aspect_ratio": "9:16"
            }
        }
    )
    
    file_path: str = Field(..., description="Path to source video file")
    segments: List[dict] = Field(..., min_length=1, max_length=10, description="Custom clip segments")
    aspect_ratio: AspectRatio = Field(AspectRatio.NINE_SIXTEEN, description="Output aspect ratio")
    use_zapcap: bool = Field(False, description="Whether to add captions using ZapCap service")


class SocialMediaPostRequest(BaseModel):
    """Request model for social media posting"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "platform": "tiktok",
                "video_path": "data/clips/example_clip.mp4",
                "caption": "Check out this amazing clip! #viral",
                "hashtags": ["viral", "trending", "fyp"],
                "scheduled_time": "2024-03-20T15:00:00Z",
                "metadata": {
                    "category": "entertainment",
                    "tags": ["funny", "comedy"]
                }
            }
        }
    )
    
    platform: str = Field(..., description="Target social media platform (tiktok, instagram, youtube)")
    video_path: str = Field(..., description="Path to the video file to post")
    caption: str = Field(..., description="Post caption text")
    hashtags: List[str] = Field(default_factory=list, description="List of hashtags to include")
    scheduled_time: Optional[datetime] = Field(None, description="Optional scheduled posting time")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata for the post")


class OAuthInitiateRequest(BaseModel):
    """Request model for initiating OAuth flow"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "platform": "youtube",
                "redirect_uri": "http://localhost:8000/api/v1/oauth/youtube/callback"
            }
        }
    )
    
    platform: str = Field(..., description="Social media platform (youtube, instagram, tiktok)")
    redirect_uri: Optional[str] = Field(None, description="Custom redirect URI (optional, will use default if not provided)")


class SocialMediaUploadRequest(BaseModel):
    """Request model for uploading clips to social media"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "clip_id": "clip_1234567890",
                "platform": "youtube",
                "title": "Amazing Video Clip",
                "description": "Check out this incredible moment!",
                "tags": ["viral", "trending"],
                "privacy_status": "public",
                "category_id": "22",
                "made_for_kids": False,
                "upload_as_shorts": True
            }
        }
    )
    
    clip_id: str = Field(..., description="ID of the clip from the app's backend")
    platform: str = Field(..., description="Target social media platform")
    
    # YouTube-specific fields
    title: Optional[str] = Field(None, description="Video title (YouTube)")
    description: Optional[str] = Field(None, description="Video description (YouTube)")
    tags: List[str] = Field(default_factory=list, description="Video tags (YouTube)")
    privacy_status: str = Field("public", description="Privacy status: public, private, unlisted (YouTube)")
    category_id: Optional[str] = Field(None, description="Video category ID (YouTube)")
    made_for_kids: bool = Field(False, description="Whether the video is made for kids (YouTube)")
    upload_as_shorts: bool = Field(True, description="Whether to upload as YouTube Shorts (YouTube)")
    
    # Instagram-specific fields
    caption: Optional[str] = Field(None, description="Post caption (Instagram)")
    hashtags: List[str] = Field(default_factory=list, description="Hashtags (Instagram)")
    
    # TikTok-specific fields
    visibility: str = Field("public", description="Video visibility: public, private (TikTok)")


class ConnectionStatusRequest(BaseModel):
    """Request model for checking connection status"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "platform": "youtube"
            }
        }
    )
    
    platform: str = Field(..., description="Social media platform to check")


class StoreTokenRequest(BaseModel):
    """Request model for storing OAuth token from frontend OAuth flow"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "platform": "youtube",
                "access_token": "ya29.a0AfH6SMC...",
                "expires_in": "3600"
            }
        }
    )
    
    platform: str = Field(..., description="Social media platform (youtube, instagram, tiktok)")
    access_token: str = Field(..., description="OAuth access token received from the platform")
    expires_in: Optional[str] = Field(None, description="Token expiration time in seconds") 