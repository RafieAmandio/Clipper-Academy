import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app


class TestHealthEndpoints:
    """Integration tests for health check endpoints"""
    
    def test_health_check_endpoint(self, client):
        """Test the main health check endpoint"""
        response = client.get("/api/v1/health/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data
        assert "dependencies" in data
        assert "directories" in data
        
        assert data["service"] == "Auto Clipper API"
        assert data["version"] == "1.0.0"
        
        # Check dependencies structure
        deps = data["dependencies"]
        assert "ffmpeg" in deps
        assert "ffprobe" in deps
        assert "yt_dlp" in deps
        assert "openai_api_key" in deps
        assert "zapcap_api_key" in deps
        
        # Check directories structure
        dirs = data["directories"]
        assert "upload_dir" in dirs
        assert "clips_dir" in dirs
        assert "temp_dir" in dirs
        assert "results_dir" in dirs
    
    def test_dependencies_endpoint(self, client):
        """Test the dependencies check endpoint"""
        response = client.get("/api/v1/health/dependencies")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have all required dependencies
        required_deps = ["ffmpeg", "ffprobe", "yt_dlp", "openai_api_key", "zapcap_api_key"]
        for dep in required_deps:
            assert dep in data
            assert isinstance(data[dep], bool)
    
    def test_directories_endpoint(self, client):
        """Test the directories check endpoint"""
        response = client.get("/api/v1/health/directories")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have all required directories
        required_dirs = ["upload_dir", "clips_dir", "temp_dir", "results_dir"]
        for dir_name in required_dirs:
            assert dir_name in data
            assert isinstance(data[dir_name], bool)
    
    def test_service_info_endpoint(self, client):
        """Test the service info endpoint"""
        response = client.get("/api/v1/health/info")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check main info fields
        assert data["service"] == "Auto Clipper API"
        assert data["version"] == "1.0.0"
        assert "description" in data
        assert "features" in data
        assert "requirements" in data
        assert "performance" in data
        assert "supported_formats" in data
        
        # Check features list
        features = data["features"]
        assert isinstance(features, list)
        assert len(features) > 0
        
        # Check requirements
        requirements = data["requirements"]
        assert "openai_api_key" in requirements
        assert "ffmpeg" in requirements
        
        # Check supported formats
        formats = data["supported_formats"]
        assert "video" in formats
        assert "audio" in formats
        assert "aspect_ratios" in formats
    
    def test_status_endpoint(self, client):
        """Test the quick status endpoint"""
        response = client.get("/api/v1/health/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "online"
        assert "timestamp" in data
        assert "uptime" in data
    
    @patch('app.api.v1.endpoints.health.check_ffmpeg')
    def test_health_check_with_missing_dependency(self, mock_check_ffmpeg, client):
        """Test health check when a critical dependency is missing"""
        mock_check_ffmpeg.return_value = False
        
        response = client.get("/api/v1/health/")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should still return 200 but status should be unhealthy
        assert data["status"] == "unhealthy"
        assert data["dependencies"]["ffmpeg"] == False
    
    def test_health_check_error_handling(self, client):
        """Test that health check handles errors gracefully"""
        with patch('app.api.v1.endpoints.health.check_ffmpeg', side_effect=Exception("Test error")):
            response = client.get("/api/v1/health/")
            
            # Should still return a response even if there's an error
            assert response.status_code == 200
            data = response.json()
            assert "status" in data 