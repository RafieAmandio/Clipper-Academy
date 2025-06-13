from functools import lru_cache
from typing import Generator
from fastapi import Depends
from openai import OpenAI

from app.config.settings import Settings
from app.services.transcription import TranscriptionService
from app.services.video_processing import VideoProcessingService
from app.services.zapcap import ZapCapService
from app.services.content_analyzer import ContentAnalyzerService
from app.services.auto_clipper import AutoClipperService


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


@lru_cache()
def get_openai_client(settings: Settings = None) -> OpenAI:
    if settings is None:
        settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key)


def get_transcription_service(
    settings: Settings = Depends(get_settings),
    openai_client: OpenAI = Depends(get_openai_client)
) -> TranscriptionService:
    """Get transcription service instance"""
    return TranscriptionService(settings, openai_client)


def get_video_processing_service(settings: Settings = Depends(get_settings)) -> VideoProcessingService:
    """Get video processing service instance"""
    return VideoProcessingService(settings)


def get_zapcap_service(settings: Settings = Depends(get_settings)) -> ZapCapService:
    """Get ZapCap service instance"""
    return ZapCapService(settings)


def get_content_analyzer_service(
    settings: Settings = Depends(get_settings),
    openai_client: OpenAI = Depends(get_openai_client)
) -> ContentAnalyzerService:
    """Get content analyzer service instance"""
    return ContentAnalyzerService(settings, openai_client)


def get_auto_clipper_service(
    settings: Settings = Depends(get_settings),
    openai_client: OpenAI = Depends(get_openai_client)
) -> AutoClipperService:
    """Get auto clipper service instance"""
    return AutoClipperService(settings, openai_client) 