import os
from abc import ABC
from typing import List
from app.config.settings import Settings
from app.config.logging import get_logger


class BaseService(ABC):
    """Base service class for all business logic services"""
    
    def __init__(self, settings: Settings):
        """Initialize base service with settings and logger
        
        Args:
            settings: Application settings instance
        """
        self.settings = settings
        self.logger = get_logger(self.__class__.__module__)
        self._setup_directories()
    
    def _setup_directories(self) -> None:
        """Create necessary directories for the service"""
        directories = [
            self.settings.upload_dir,
            self.settings.clips_dir,
            self.settings.temp_dir,
            self.settings.results_dir,
        ]
        
        for directory in directories:
            try:
                os.makedirs(directory, exist_ok=True)
                self.logger.debug(f"Ensured directory exists: {directory}")
            except OSError as e:
                self.logger.warning(f"Could not create directory {directory}: {e}")
    
    def format_timestamp(self, seconds: float) -> str:
        """Convert seconds to MM:SS format
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted time string in MM:SS format
        """
        minutes = int(seconds // 60)
        seconds_part = int(seconds % 60)
        return f"{minutes:02d}:{seconds_part:02d}"
    
    def format_file_size(self, size_bytes: int) -> str:
        """Convert bytes to human readable format
        
        Args:
            size_bytes: File size in bytes
            
        Returns:
            Human readable file size string
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def cleanup_temp_files(self, file_paths: List[str]) -> None:
        """Clean up temporary files
        
        Args:
            file_paths: List of file paths to remove
        """
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    self.logger.debug(f"Cleaned up temp file: {file_path}")
            except OSError as e:
                self.logger.warning(f"Could not remove temp file {file_path}: {e}") 