import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings and configuration"""
    
    # API Configuration
    app_name: str = "Auto Clipper API"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    app_url: str = Field("http://localhost:8000", description="Base URL of the application for OAuth callbacks")
    frontend_url: str = Field("http://localhost:3000", description="Frontend URL for OAuth redirects")
    
    # OpenAI Configuration
    openai_api_key: str = Field(..., description="OpenAI API key for transcription and AI analysis")
    
    # ZapCap Configuration
    zapcap_api_key: Optional[str] = Field(None, description="ZapCap API key for automated captioning")
    zapcap_template_id: Optional[str] = Field(None, description="Default ZapCap template ID")
    zapcap_api_base: str = "https://api.zapcap.ai"
    
    # Storage Configuration
    upload_dir: str = "data/uploads"
    clips_dir: str = "data/clips"
    temp_dir: str = "data/temp"
    results_dir: str = "data/results"
    
    # Processing Configuration
    max_file_size: int = 500 * 1024 * 1024  # 500MB
    max_clip_duration: int = 120  # seconds
    min_clip_duration: int = 10   # seconds
    max_transcription_chunk_size: int = 20 * 1024 * 1024  # 20MB
    max_concurrent_chunks: int = 5
    max_chunk_size_mb: int = 25  # MB - for chunking large files
    
    # Video Processing Configuration
    default_aspect_ratio: str = "9:16"
    supported_video_formats: list[str] = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
    ffmpeg_preset: str = "fast"
    video_quality_crf: int = 23
    
    # Instagram Configuration (for content analyzer)
    instagram_username: Optional[str] = None
    instagram_password: Optional[str] = None
    
    # Social Media OAuth Configuration
    
    # YouTube OAuth Configuration
    youtube_client_id: Optional[str] = Field(None, description="YouTube OAuth client ID")
    youtube_client_secret: Optional[str] = Field(None, description="YouTube OAuth client secret")
    youtube_redirect_uri: str = Field("http://localhost:8000/api/v1/oauth/youtube/callback", description="YouTube OAuth redirect URI")
    youtube_scopes: list[str] = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly"
    ]
    
    # Instagram OAuth Configuration
    instagram_client_id: Optional[str] = Field(None, description="Instagram OAuth client ID")
    instagram_client_secret: Optional[str] = Field(None, description="Instagram OAuth client secret")
    instagram_redirect_uri: str = Field("http://localhost:8000/api/v1/oauth/instagram/callback", description="Instagram OAuth redirect URI")
    instagram_scopes: list[str] = [
        "instagram_content_publish",
        "pages_show_list",
        "user_profile",
        "user_media"
    ]
    
    # TikTok OAuth Configuration
    tiktok_client_key: Optional[str] = Field(None, description="TikTok OAuth client key")
    tiktok_client_secret: Optional[str] = Field(None, description="TikTok OAuth client secret")
    tiktok_redirect_uri: str = Field("http://localhost:8000/api/v1/oauth/tiktok/callback", description="TikTok OAuth redirect URI")
    tiktok_scopes: list[str] = [
        "user.info.basic",
        "video.list",
        "video.upload"
    ]
    
    # Legacy API keys (for backward compatibility)
    tiktok_api_key: Optional[str] = Field(None, description="TikTok API key (legacy)")
    tiktok_api_secret: Optional[str] = Field(None, description="TikTok API secret (legacy)")
    tiktok_access_token: Optional[str] = Field(None, description="TikTok access token (legacy)")
    
    instagram_api_key: Optional[str] = Field(None, description="Instagram Graph API key (legacy)")
    instagram_api_secret: Optional[str] = Field(None, description="Instagram Graph API secret (legacy)")
    instagram_access_token: Optional[str] = Field(None, description="Instagram access token (legacy)")
    
    youtube_api_key: Optional[str] = Field(None, description="YouTube Data API key (legacy)")
    youtube_refresh_token: Optional[str] = Field(None, description="YouTube OAuth refresh token (legacy)")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False 