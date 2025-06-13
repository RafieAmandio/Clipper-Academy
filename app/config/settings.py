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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False 