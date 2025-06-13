"""Custom exceptions for the Auto Clipper application"""


class ClipperException(Exception):
    """Base exception for clipper operations"""
    pass


class ConfigurationError(ClipperException):
    """Error in configuration or setup"""
    pass


class VideoProcessingError(ClipperException):
    """Error during video processing"""
    pass


class TranscriptionError(ClipperException):
    """Error during audio transcription"""
    pass


class DownloadError(ClipperException):
    """Error during video download from social media"""
    pass


class ZapCapError(ClipperException):
    """Error during ZapCap processing"""
    pass


class StorageError(ClipperException):
    """Error during file storage operations"""
    pass


class ValidationError(ClipperException):
    """Error during input validation"""
    pass


class ContentAnalysisError(ClipperException):
    """Error during content analysis"""
    pass 