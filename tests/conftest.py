import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.config.settings import Settings
from app.services.base import BaseService
from app.services.transcription import TranscriptionService
from app.services.video_processing import VideoProcessingService
from app.services.zapcap import ZapCapService
from app.services.content_analyzer import ContentAnalyzerService
from app.services.auto_clipper import AutoClipperService


@pytest.fixture
def test_settings():
    """Test settings with safe defaults"""
    return Settings(
        app_name="Test Auto Clipper API",
        app_version="1.0.0-test",
        debug=True,
        openai_api_key="test-openai-key",
        zapcap_api_key="test-zapcap-key",
        upload_dir="test_data/uploads",
        clips_dir="test_data/clips",
        temp_dir="test_data/temp",
        results_dir="test_data/results"
    )


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing"""
    with patch('openai.OpenAI') as mock_client:
        # Mock transcription response
        mock_response = Mock()
        mock_response.model_dump.return_value = {
            'text': 'This is a test transcription',
            'segments': [],
            'words': [],
            'language': 'en'
        }
        
        mock_client.return_value.audio.transcriptions.create.return_value = mock_response
        
        # Mock chat completion response
        mock_chat_response = Mock()
        mock_chat_response.choices = [Mock()]
        mock_chat_response.choices[0].message.content = '''[
            {
                "title": "Test Clip",
                "description": "A test clip segment",
                "start_time": "00:15",
                "end_time": "01:00",
                "duration": 45,
                "engagement_score": 8.5
            }
        ]'''
        
        mock_client.return_value.chat.completions.create.return_value = mock_chat_response
        
        yield mock_client


@pytest.fixture
def base_service(test_settings):
    """Base service instance for testing"""
    return BaseService(test_settings)


@pytest.fixture
def transcription_service(test_settings, mock_openai_client):
    """Transcription service instance for testing"""
    return TranscriptionService(test_settings)


@pytest.fixture
def video_processing_service(test_settings):
    """Video processing service instance for testing"""
    return VideoProcessingService(test_settings)


@pytest.fixture
def zapcap_service(test_settings):
    """ZapCap service instance for testing"""
    return ZapCapService(test_settings)


@pytest.fixture
def content_analyzer_service(test_settings, mock_openai_client):
    """Content analyzer service instance for testing"""
    return ContentAnalyzerService(test_settings)


@pytest.fixture
def auto_clipper_service(test_settings, mock_openai_client):
    """Auto clipper service instance for testing"""
    return AutoClipperService(test_settings)


@pytest.fixture
def client():
    """Test client for API testing"""
    return TestClient(app)


@pytest.fixture
def sample_video_file():
    """Create a minimal test video file"""
    # This would create a minimal valid video file for testing
    # For now, we'll mock this
    return "test_video.mp4"


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for ffmpeg commands"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"format": {"duration": "120.5"}}'
        mock_run.return_value.stderr = ''
        yield mock_run


@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Automatically clean up test files after each test"""
    yield
    # Clean up any test files created during testing
    test_dirs = ["test_data", "test_clips", "test_temp"]
    for test_dir in test_dirs:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir, ignore_errors=True) 