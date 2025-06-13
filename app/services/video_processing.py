import os
import subprocess
import json
from datetime import datetime
from typing import Dict, Optional, Union
from pathlib import Path

from fastapi import UploadFile

from app.services.base import BaseService
from app.config.settings import Settings
from app.core.exceptions import VideoProcessingError, StorageError


class VideoProcessingService(BaseService):
    """Service for handling video processing operations"""
    
    def __init__(self, settings: Settings):
        """Initialize video processing service
        
        Args:
            settings: Application settings
        """
        super().__init__(settings)
    
    async def save_upload_file(self, upload_file: UploadFile) -> str:
        """Save uploaded file to temp directory
        
        Args:
            upload_file: FastAPI UploadFile object
            
        Returns:
            Path to saved file
            
        Raises:
            StorageError: If file save fails
        """
        try:
            filename = getattr(upload_file, 'filename', 'video.mp4')
            file_extension = os.path.splitext(filename or "video.mp4")[1]
            
            # Validate file extension
            if file_extension.lower() not in self.settings.supported_video_formats:
                raise StorageError(f"Unsupported video format: {file_extension}")
            
            timestamp = int(datetime.now().timestamp())
            temp_file_path = os.path.join(self.settings.temp_dir, f"upload_{timestamp}{file_extension}")
            
            # Check file size
            content = await upload_file.read()
            if len(content) > self.settings.max_file_size:
                raise StorageError(f"File size ({self.format_file_size(len(content))}) exceeds maximum allowed size ({self.format_file_size(self.settings.max_file_size)})")
            
            with open(temp_file_path, 'wb') as temp_file:
                temp_file.write(content)
            
            self.logger.info(f"File saved to: {temp_file_path}, size: {self.format_file_size(len(content))}")
            return temp_file_path
            
        except Exception as e:
            self.logger.error(f"Error saving upload file: {e}")
            raise StorageError(f"Failed to save uploaded file: {e}")
    
    def get_video_info(self, video_path: str) -> Dict:
        """Get video information using ffprobe
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary containing video metadata
            
        Raises:
            VideoProcessingError: If video info extraction fails
        """
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            video_stream = None
            audio_stream = None
            
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video' and video_stream is None:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and audio_stream is None:
                    audio_stream = stream
            
            if not video_stream:
                raise VideoProcessingError("No video stream found in file")
            
            duration = float(info.get('format', {}).get('duration', 0))
            width = int(video_stream.get('width', 1920))
            height = int(video_stream.get('height', 1080))
            
            video_info = {
                'duration': duration,
                'width': width,
                'height': height,
                'aspect_ratio': width / height if height > 0 else 16/9,
                'fps': eval(video_stream.get('r_frame_rate', '30/1')),
                'codec': video_stream.get('codec_name', 'unknown'),
                'bitrate': int(info.get('format', {}).get('bit_rate', 0)),
                'has_audio': audio_stream is not None,
                'file_size': int(info.get('format', {}).get('size', 0))
            }
            
            self.logger.info(f"Video info extracted: {video_info['duration']:.1f}s, {video_info['width']}x{video_info['height']}, {video_info['codec']}")
            return video_info
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFprobe error: {e.stderr}")
            raise VideoProcessingError(f"Failed to get video info: {e.stderr}")
        except Exception as e:
            self.logger.error(f"Error getting video info: {e}")
            raise VideoProcessingError(f"Failed to get video info: {e}")
    
    def time_to_seconds(self, time_str: str) -> float:
        """Convert time string to seconds
        
        Args:
            time_str: Time in MM:SS or HH:MM:SS format
            
        Returns:
            Time in seconds
        """
        try:
            parts = time_str.split(':')
            if len(parts) == 2:
                minutes, seconds = parts
                return int(minutes) * 60 + float(seconds)
            elif len(parts) == 3:
                hours, minutes, seconds = parts
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            else:
                return float(time_str)
        except Exception:
            self.logger.warning(f"Could not parse time string: {time_str}")
            return 0.0
    
    def calculate_crop_filter(self, video_info: Dict, target_aspect_ratio: str) -> str:
        """Calculate FFmpeg filter for aspect ratio conversion
        
        Args:
            video_info: Video metadata
            target_aspect_ratio: Target aspect ratio (e.g., "9:16", "16:9", "1:1")
            
        Returns:
            FFmpeg filter string
        """
        if target_aspect_ratio == "original":
            return "scale=trunc(iw/2)*2:trunc(ih/2)*2"  # Ensure even dimensions
        
        # Parse target aspect ratio
        if target_aspect_ratio == "9:16":
            target_ratio = 9/16
            target_width, target_height = 1080, 1920
        elif target_aspect_ratio == "16:9":
            target_ratio = 16/9
            target_width, target_height = 1920, 1080
        elif target_aspect_ratio == "1:1":
            target_ratio = 1.0
            target_width, target_height = 1080, 1080
        else:
            raise VideoProcessingError(f"Unsupported aspect ratio: {target_aspect_ratio}")
        
        current_ratio = video_info['aspect_ratio']
        width = video_info['width']
        height = video_info['height']
        
        if abs(current_ratio - target_ratio) < 0.01:
            # Already correct ratio, just scale
            return f"scale={target_width}:{target_height}"
        
        if current_ratio > target_ratio:
            # Video is wider, crop sides
            new_width = int(height * target_ratio)
            x_offset = (width - new_width) // 2
            crop_filter = f"crop={new_width}:{height}:{x_offset}:0"
        else:
            # Video is taller, crop top/bottom
            new_height = int(width / target_ratio)
            y_offset = (height - new_height) // 2
            crop_filter = f"crop={width}:{new_height}:0:{y_offset}"
        
        # Combine crop and scale
        return f"{crop_filter},scale={target_width}:{target_height}"
    
    def create_video_clip(self, video_path: str, start_time: float, end_time: float, 
                         output_path: str, aspect_ratio: str = "9:16") -> str:
        """Create a video clip with specified parameters
        
        Args:
            video_path: Path to source video
            start_time: Start time in seconds
            end_time: End time in seconds
            output_path: Path for output clip
            aspect_ratio: Target aspect ratio
            
        Returns:
            Path to created clip
            
        Raises:
            VideoProcessingError: If clip creation fails
        """
        try:
            # Validate clip duration
            clip_duration = end_time - start_time
            if clip_duration < self.settings.min_clip_duration:
                raise VideoProcessingError(f"Clip duration ({clip_duration:.1f}s) is below minimum ({self.settings.min_clip_duration}s)")
            
            if clip_duration > self.settings.max_clip_duration:
                raise VideoProcessingError(f"Clip duration ({clip_duration:.1f}s) exceeds maximum ({self.settings.max_clip_duration}s)")
            
            # Get video info for filter calculation
            video_info = self.get_video_info(video_path)
            
            # Build FFmpeg command
            cmd = ['ffmpeg', '-y', '-i', video_path]
            
            # Set time range
            cmd.extend(['-ss', str(start_time), '-to', str(end_time)])
            
            # Add video filter for aspect ratio
            if aspect_ratio != "original":
                video_filter = self.calculate_crop_filter(video_info, aspect_ratio)
                cmd.extend(['-vf', video_filter])
            
            # Video encoding settings
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', self.settings.ffmpeg_preset,
                '-crf', str(self.settings.video_quality_crf)
            ])
            
            # Audio encoding settings
            if video_info.get('has_audio', False):
                cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
            else:
                cmd.extend(['-an'])  # No audio
            
            cmd.append(output_path)
            
            self.logger.info(f"Creating clip: {self.format_timestamp(start_time)} - {self.format_timestamp(end_time)} ({aspect_ratio})")
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if not os.path.exists(output_path):
                raise VideoProcessingError("Clip file was not created")
            
            # Get output file size
            output_size = os.path.getsize(output_path)
            self.logger.info(f"Clip created successfully: {output_path} ({self.format_file_size(output_size)})")
            
            return output_path
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg error creating clip: {e.stderr}")
            raise VideoProcessingError(f"Failed to create clip: {e.stderr}")
        except Exception as e:
            self.logger.error(f"Error creating clip: {e}")
            raise VideoProcessingError(f"Failed to create clip: {e}")
    
    def validate_video_file(self, video_path: str) -> bool:
        """Validate that a file is a valid video
        
        Args:
            video_path: Path to video file
            
        Returns:
            True if valid video file
        """
        try:
            if not os.path.exists(video_path):
                return False
            
            # Check file extension
            extension = os.path.splitext(video_path)[1].lower()
            if extension not in self.settings.supported_video_formats:
                return False
            
            # Try to get basic video info
            video_info = self.get_video_info(video_path)
            
            # Basic validation
            if video_info['duration'] <= 0:
                return False
            
            if video_info['width'] <= 0 or video_info['height'] <= 0:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Video validation failed: {e}")
            return False
    
    def cleanup_temp_file(self, file_path: str) -> None:
        """Clean up a temporary file
        
        Args:
            file_path: Path to file to delete
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.debug(f"Cleaned up temp file: {file_path}")
        except OSError as e:
            self.logger.warning(f"Could not clean up temp file {file_path}: {e}")
    
    def get_safe_filename(self, title: str, max_length: int = 50) -> str:
        """Create a safe filename from a title
        
        Args:
            title: Original title
            max_length: Maximum filename length
            
        Returns:
            Safe filename string
        """
        import re
        
        # Remove special characters and replace spaces with underscores
        safe_title = re.sub(r'[^\w\s-]', '', title).strip()
        safe_title = re.sub(r'[-\s]+', '_', safe_title)
        
        # Truncate if too long
        if len(safe_title) > max_length:
            safe_title = safe_title[:max_length]
        
        # Ensure it's not empty
        if not safe_title:
            safe_title = "clip"
        
        return safe_title 