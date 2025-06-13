import pytest
import os
import io
from unittest.mock import patch, Mock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app


class TestClipsEndpoints:
    """Integration tests for clips API endpoints"""
    
    def test_upload_endpoint_success(self, client):
        """Test successful video upload processing"""
        # Create a mock video file
        video_content = b"fake video content"
        video_file = ("test_video.mp4", io.BytesIO(video_content), "video/mp4")
        
        with patch('app.core.dependencies.get_auto_clipper_service') as mock_get_service:
            mock_service = Mock()
            mock_service.process_video_upload = AsyncMock(return_value={
                "success": True,
                "message": "Video processed successfully",
                "clips": [
                    {
                        "clip_number": 1,
                        "title": "Test Clip",
                        "description": "A test clip",
                        "start_time": "00:15",
                        "end_time": "01:00",
                        "duration": 45,
                        "file_path": "/path/to/clip.mp4"
                    }
                ]
            })
            mock_get_service.return_value = mock_service
            
            response = client.post(
                "/api/v1/clips/upload",
                files={"video": video_file},
                data={
                    "use_zapcap": "false",
                    "aspect_ratio": "9:16"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "clips" in data
        assert len(data["clips"]) == 1
    
    def test_upload_endpoint_invalid_file_type(self, client):
        """Test upload endpoint with invalid file type"""
        # Create a mock text file
        text_content = b"This is not a video file"
        text_file = ("test.txt", io.BytesIO(text_content), "text/plain")
        
        response = client.post(
            "/api/v1/clips/upload",
            files={"video": text_file},
            data={"aspect_ratio": "9:16"}
        )
        
        assert response.status_code == 400
        assert "Unsupported video format" in response.json()["detail"]
    
    def test_upload_endpoint_invalid_aspect_ratio(self, client):
        """Test upload endpoint with invalid aspect ratio"""
        video_content = b"fake video content"
        video_file = ("test_video.mp4", io.BytesIO(video_content), "video/mp4")
        
        response = client.post(
            "/api/v1/clips/upload",
            files={"video": video_file},
            data={"aspect_ratio": "invalid"}
        )
        
        assert response.status_code == 400
        assert "Invalid aspect ratio" in response.json()["detail"]
    
    def test_upload_endpoint_service_error(self, client):
        """Test upload endpoint when service raises an error"""
        video_content = b"fake video content"
        video_file = ("test_video.mp4", io.BytesIO(video_content), "video/mp4")
        
        with patch('app.core.dependencies.get_auto_clipper_service') as mock_get_service:
            mock_service = Mock()
            mock_service.process_video_upload = AsyncMock(side_effect=Exception("Service error"))
            mock_get_service.return_value = mock_service
            
            response = client.post(
                "/api/v1/clips/upload",
                files={"video": video_file},
                data={"aspect_ratio": "9:16"}
            )
        
        assert response.status_code == 500
        assert "Failed to process video" in response.json()["detail"]
    
    def test_url_endpoint_success(self, client):
        """Test successful URL processing"""
        with patch('app.core.dependencies.get_auto_clipper_service') as mock_get_service:
            mock_service = Mock()
            mock_service.process_video_url = AsyncMock(return_value={
                "success": True,
                "message": "Video processed successfully",
                "clips": [
                    {
                        "clip_number": 1,
                        "title": "URL Clip",
                        "description": "A clip from URL",
                        "start_time": "00:30",
                        "end_time": "01:15",
                        "duration": 45,
                        "file_path": "/path/to/url_clip.mp4"
                    }
                ],
                "source_url": "https://example.com/video.mp4"
            })
            mock_get_service.return_value = mock_service
            
            response = client.post(
                "/api/v1/clips/url",
                data={
                    "url": "https://example.com/video.mp4",
                    "use_zapcap": "false",
                    "aspect_ratio": "16:9"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "clips" in data
        assert data["source_url"] == "https://example.com/video.mp4"
    
    def test_url_endpoint_invalid_url(self, client):
        """Test URL endpoint with invalid URL format"""
        response = client.post(
            "/api/v1/clips/url",
            data={
                "url": "not-a-valid-url",
                "aspect_ratio": "9:16"
            }
        )
        
        assert response.status_code == 400
        assert "Invalid URL format" in response.json()["detail"]
    
    def test_url_endpoint_tiktok_url(self, client):
        """Test URL endpoint with TikTok URL"""
        with patch('app.core.dependencies.get_auto_clipper_service') as mock_get_service:
            mock_service = Mock()
            mock_service.process_video_url = AsyncMock(return_value={
                "success": True,
                "platform": "tiktok",
                "clips": []
            })
            mock_get_service.return_value = mock_service
            
            response = client.post(
                "/api/v1/clips/url",
                data={
                    "url": "https://www.tiktok.com/@user/video/1234567890",
                    "aspect_ratio": "9:16"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["platform"] == "tiktok"
    
    def test_url_endpoint_instagram_url(self, client):
        """Test URL endpoint with Instagram URL"""
        with patch('app.core.dependencies.get_auto_clipper_service') as mock_get_service:
            mock_service = Mock()
            mock_service.process_video_url = AsyncMock(return_value={
                "success": True,
                "platform": "instagram",
                "clips": []
            })
            mock_get_service.return_value = mock_service
            
            response = client.post(
                "/api/v1/clips/url",
                data={
                    "url": "https://www.instagram.com/p/ABC123/",
                    "aspect_ratio": "9:16"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["platform"] == "instagram"
    
    def test_filepath_endpoint_success(self, client, temp_dir):
        """Test successful file path processing"""
        # Create a test video file
        video_path = os.path.join(temp_dir, "test_video.mp4")
        with open(video_path, 'wb') as f:
            f.write(b"fake video content")
        
        with patch('app.core.dependencies.get_auto_clipper_service') as mock_get_service:
            mock_service = Mock()
            mock_service.process_video_file = AsyncMock(return_value={
                "success": True,
                "message": "Video processed successfully",
                "clips": [
                    {
                        "clip_number": 1,
                        "title": "File Clip",
                        "description": "A clip from file",
                        "start_time": "00:45",
                        "end_time": "01:30",
                        "duration": 45,
                        "file_path": "/path/to/file_clip.mp4"
                    }
                ],
                "source_file": video_path
            })
            mock_get_service.return_value = mock_service
            
            response = client.post(
                "/api/v1/clips/filepath",
                data={
                    "file_path": video_path,
                    "use_zapcap": "true",
                    "zapcap_template_id": "custom-template",
                    "aspect_ratio": "1:1"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "clips" in data
        assert data["source_file"] == video_path
    
    def test_filepath_endpoint_missing_file(self, client):
        """Test file path endpoint with missing file"""
        response = client.post(
            "/api/v1/clips/filepath",
            data={
                "file_path": "/path/that/does/not/exist.mp4",
                "aspect_ratio": "9:16"
            }
        )
        
        assert response.status_code == 404
        assert "Video file not found" in response.json()["detail"]
    
    def test_filepath_endpoint_invalid_file_type(self, client, temp_dir):
        """Test file path endpoint with invalid file type"""
        # Create a text file instead of video
        text_path = os.path.join(temp_dir, "test.txt")
        with open(text_path, 'w') as f:
            f.write("This is not a video")
        
        response = client.post(
            "/api/v1/clips/filepath",
            data={
                "file_path": text_path,
                "aspect_ratio": "9:16"
            }
        )
        
        assert response.status_code == 400
        assert "Unsupported video format" in response.json()["detail"]
    
    def test_endpoint_with_zapcap_processing(self, client):
        """Test endpoint with ZapCap processing enabled"""
        video_content = b"fake video content"
        video_file = ("test_video.mp4", io.BytesIO(video_content), "video/mp4")
        
        with patch('app.core.dependencies.get_auto_clipper_service') as mock_get_service:
            mock_service = Mock()
            mock_service.process_video_upload = AsyncMock(return_value={
                "success": True,
                "message": "Video processed with captions",
                "clips": [
                    {
                        "clip_number": 1,
                        "title": "Captioned Clip",
                        "description": "A clip with captions",
                        "start_time": "00:15",
                        "end_time": "01:00",
                        "duration": 45,
                        "file_path": "/path/to/clip.mp4",
                        "zapcap_result": {
                            "video_id": "zapcap-123",
                            "captioned_video_path": "/path/to/captioned_clip.mp4"
                        }
                    }
                ]
            })
            mock_get_service.return_value = mock_service
            
            response = client.post(
                "/api/v1/clips/upload",
                files={"video": video_file},
                data={
                    "use_zapcap": "true",
                    "zapcap_template_id": "custom-template-123",
                    "aspect_ratio": "9:16"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        clip = data["clips"][0]
        assert "zapcap_result" in clip
        assert clip["zapcap_result"]["video_id"] == "zapcap-123"
    
    def test_endpoint_missing_required_parameters(self, client):
        """Test endpoint with missing required parameters"""
        response = client.post("/api/v1/clips/upload")
        
        assert response.status_code == 422  # Validation error
    
    def test_all_aspect_ratios_supported(self, client):
        """Test that all supported aspect ratios work"""
        video_content = b"fake video content"
        
        supported_ratios = ["9:16", "16:9", "1:1", "original"]
        
        for ratio in supported_ratios:
            video_file = ("test_video.mp4", io.BytesIO(video_content), "video/mp4")
            
            with patch('app.core.dependencies.get_auto_clipper_service') as mock_get_service:
                mock_service = Mock()
                mock_service.process_video_upload = AsyncMock(return_value={
                    "success": True,
                    "clips": [],
                    "aspect_ratio": ratio
                })
                mock_get_service.return_value = mock_service
                
                response = client.post(
                    "/api/v1/clips/upload",
                    files={"video": video_file},
                    data={"aspect_ratio": ratio}
                )
            
            assert response.status_code == 200
            data = response.json()
            assert data["aspect_ratio"] == ratio 