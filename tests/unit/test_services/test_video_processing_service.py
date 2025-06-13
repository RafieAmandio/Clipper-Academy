import pytest
import os
import json
from unittest.mock import patch, Mock
from app.services.video_processing import VideoProcessingService
from app.core.exceptions import VideoProcessingError


class TestVideoProcessingService:
    """Test the VideoProcessingService class"""
    
    def test_initialization(self, test_settings):
        """Test that VideoProcessingService initializes correctly"""
        service = VideoProcessingService(test_settings)
        
        assert service.settings == test_settings
        assert service.logger is not None
    
    @patch('subprocess.run')
    def test_get_video_info_success(self, mock_subprocess, video_processing_service, temp_dir):
        """Test successful video info extraction"""
        video_path = os.path.join(temp_dir, "test_video.mp4")
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        mock_output = {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080
                }
            ],
            "format": {
                "duration": "120.5"
            }
        }
        
        mock_subprocess.return_value.stdout = json.dumps(mock_output)
        mock_subprocess.return_value.returncode = 0
        
        info = video_processing_service.get_video_info(video_path)
        
        assert info['duration'] == 120.5
        assert info['width'] == 1920
        assert info['height'] == 1080
        assert info['aspect_ratio'] == 1920 / 1080
        mock_subprocess.assert_called_once()
    
    @patch('subprocess.run')
    def test_get_video_info_no_video_stream(self, mock_subprocess, video_processing_service, temp_dir):
        """Test video info extraction with no video stream"""
        video_path = os.path.join(temp_dir, "test_video.mp4")
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        mock_output = {
            "streams": [
                {
                    "codec_type": "audio"
                }
            ],
            "format": {
                "duration": "120.5"
            }
        }
        
        mock_subprocess.return_value.stdout = json.dumps(mock_output)
        mock_subprocess.return_value.returncode = 0
        
        info = video_processing_service.get_video_info(video_path)
        
        # Should use default values when no video stream
        assert info['width'] == 1920
        assert info['height'] == 1080
    
    @patch('subprocess.run')
    def test_get_video_info_ffprobe_error(self, mock_subprocess, video_processing_service, temp_dir):
        """Test video info extraction with ffprobe error"""
        video_path = os.path.join(temp_dir, "test_video.mp4")
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        mock_subprocess.side_effect = Exception("FFprobe error")
        
        with pytest.raises(VideoProcessingError, match="Failed to get video info"):
            video_processing_service.get_video_info(video_path)
    
    def test_get_video_info_missing_file(self, video_processing_service):
        """Test video info extraction with missing file"""
        with pytest.raises(VideoProcessingError, match="Video file not found"):
            video_processing_service.get_video_info("/nonexistent/file.mp4")
    
    def test_time_to_seconds_formats(self, video_processing_service):
        """Test time string to seconds conversion"""
        assert video_processing_service.time_to_seconds("01:30") == 90.0
        assert video_processing_service.time_to_seconds("1:02:30") == 3750.0
        assert video_processing_service.time_to_seconds("120") == 120.0
        assert video_processing_service.time_to_seconds("invalid") == 0.0
    
    @patch('subprocess.run')
    @patch.object(VideoProcessingService, 'get_video_info')
    def test_create_clip_original_aspect_ratio(self, mock_get_info, mock_subprocess, video_processing_service, temp_dir):
        """Test clip creation with original aspect ratio"""
        video_path = os.path.join(temp_dir, "input_video.mp4")
        output_path = os.path.join(temp_dir, "output_clip.mp4")
        
        # Create dummy input file
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        mock_subprocess.return_value.returncode = 0
        
        # Mock that output file is created
        def create_output_file(*args, **kwargs):
            with open(output_path, 'wb') as f:
                f.write(b"dummy output video")
            return mock_subprocess.return_value
        
        mock_subprocess.side_effect = create_output_file
        
        result = video_processing_service.create_clip(
            video_path, 10.0, 60.0, output_path, "original"
        )
        
        assert result == output_path
        assert os.path.exists(output_path)
        mock_subprocess.assert_called_once()
    
    @patch('subprocess.run')
    @patch.object(VideoProcessingService, 'get_video_info')
    def test_create_clip_9_16_aspect_ratio(self, mock_get_info, mock_subprocess, video_processing_service, temp_dir):
        """Test clip creation with 9:16 aspect ratio"""
        video_path = os.path.join(temp_dir, "input_video.mp4")
        output_path = os.path.join(temp_dir, "output_clip.mp4")
        
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        # Mock video info for wide video (needs cropping)
        mock_get_info.return_value = {
            'width': 1920,
            'height': 1080,
            'aspect_ratio': 1920 / 1080
        }
        
        mock_subprocess.return_value.returncode = 0
        
        def create_output_file(*args, **kwargs):
            with open(output_path, 'wb') as f:
                f.write(b"dummy output video")
            return mock_subprocess.return_value
        
        mock_subprocess.side_effect = create_output_file
        
        result = video_processing_service.create_clip(
            video_path, 10.0, 60.0, output_path, "9:16"
        )
        
        assert result == output_path
        mock_subprocess.assert_called_once()
        
        # Check that crop filter was applied
        call_args = mock_subprocess.call_args[0][0]
        assert '-vf' in call_args
    
    @patch('subprocess.run')
    @patch.object(VideoProcessingService, 'get_video_info')
    def test_create_clip_16_9_aspect_ratio(self, mock_get_info, mock_subprocess, video_processing_service, temp_dir):
        """Test clip creation with 16:9 aspect ratio"""
        video_path = os.path.join(temp_dir, "input_video.mp4")
        output_path = os.path.join(temp_dir, "output_clip.mp4")
        
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        # Mock video info for tall video (needs cropping)
        mock_get_info.return_value = {
            'width': 1080,
            'height': 1920,
            'aspect_ratio': 1080 / 1920
        }
        
        mock_subprocess.return_value.returncode = 0
        
        def create_output_file(*args, **kwargs):
            with open(output_path, 'wb') as f:
                f.write(b"dummy output video")
            return mock_subprocess.return_value
        
        mock_subprocess.side_effect = create_output_file
        
        result = video_processing_service.create_clip(
            video_path, 10.0, 60.0, output_path, "16:9"
        )
        
        assert result == output_path
        mock_subprocess.assert_called_once()
    
    @patch('subprocess.run')
    @patch.object(VideoProcessingService, 'get_video_info')
    def test_create_clip_1_1_aspect_ratio(self, mock_get_info, mock_subprocess, video_processing_service, temp_dir):
        """Test clip creation with 1:1 (square) aspect ratio"""
        video_path = os.path.join(temp_dir, "input_video.mp4")
        output_path = os.path.join(temp_dir, "output_clip.mp4")
        
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        mock_get_info.return_value = {
            'width': 1920,
            'height': 1080,
            'aspect_ratio': 1920 / 1080
        }
        
        mock_subprocess.return_value.returncode = 0
        
        def create_output_file(*args, **kwargs):
            with open(output_path, 'wb') as f:
                f.write(b"dummy output video")
            return mock_subprocess.return_value
        
        mock_subprocess.side_effect = create_output_file
        
        result = video_processing_service.create_clip(
            video_path, 10.0, 60.0, output_path, "1:1"
        )
        
        assert result == output_path
        mock_subprocess.assert_called_once()
    
    def test_create_clip_unsupported_aspect_ratio(self, video_processing_service, temp_dir):
        """Test clip creation with unsupported aspect ratio"""
        video_path = os.path.join(temp_dir, "input_video.mp4")
        output_path = os.path.join(temp_dir, "output_clip.mp4")
        
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        with pytest.raises(ValueError, match="Unsupported aspect ratio"):
            video_processing_service.create_clip(
                video_path, 10.0, 60.0, output_path, "unsupported"
            )
    
    @patch('subprocess.run')
    def test_create_clip_ffmpeg_error(self, mock_subprocess, video_processing_service, temp_dir):
        """Test clip creation with FFmpeg error"""
        video_path = os.path.join(temp_dir, "input_video.mp4")
        output_path = os.path.join(temp_dir, "output_clip.mp4")
        
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        mock_subprocess.side_effect = Exception("FFmpeg error")
        
        with pytest.raises(VideoProcessingError, match="Failed to create clip"):
            video_processing_service.create_clip(
                video_path, 10.0, 60.0, output_path, "original"
            )
    
    @patch('subprocess.run')
    def test_create_clip_output_not_created(self, mock_subprocess, video_processing_service, temp_dir):
        """Test clip creation when output file is not created"""
        video_path = os.path.join(temp_dir, "input_video.mp4")
        output_path = os.path.join(temp_dir, "output_clip.mp4")
        
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        mock_subprocess.return_value.returncode = 0
        # Don't create output file to simulate failure
        
        with pytest.raises(VideoProcessingError, match="Clip file was not created"):
            video_processing_service.create_clip(
                video_path, 10.0, 60.0, output_path, "original"
            )
    
    def test_validate_video_file_valid_formats(self, video_processing_service):
        """Test video file validation with valid formats"""
        valid_files = [
            "video.mp4",
            "movie.mov",
            "clip.avi",
            "content.mkv",
            "stream.webm"
        ]
        
        for filename in valid_files:
            assert video_processing_service.validate_video_file(filename) == True
    
    def test_validate_video_file_invalid_formats(self, video_processing_service):
        """Test video file validation with invalid formats"""
        invalid_files = [
            "document.txt",
            "image.jpg",
            "audio.mp3",
            "archive.zip",
            "no_extension"
        ]
        
        for filename in invalid_files:
            assert video_processing_service.validate_video_file(filename) == False 