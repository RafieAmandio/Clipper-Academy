import pytest
import os
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from app.services.transcription import TranscriptionService
from app.core.exceptions import TranscriptionError


class TestTranscriptionService:
    """Test the TranscriptionService class"""
    
    def test_initialization(self, test_settings, mock_openai_client):
        """Test that TranscriptionService initializes correctly"""
        service = TranscriptionService(test_settings)
        
        assert service.settings == test_settings
        assert service.logger is not None
        assert hasattr(service, 'client')
    
    def test_initialization_without_api_key(self, test_settings):
        """Test initialization without OpenAI API key"""
        test_settings.openai_api_key = ""
        
        with pytest.raises(ValueError, match="OpenAI API key is required"):
            TranscriptionService(test_settings)
    
    @patch('subprocess.run')
    def test_extract_audio_success(self, mock_subprocess, transcription_service, temp_dir):
        """Test successful audio extraction"""
        video_path = os.path.join(temp_dir, "test_video.mp4")
        # Create dummy video file
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        mock_subprocess.return_value.returncode = 0
        
        audio_path = transcription_service.extract_audio(video_path)
        
        assert audio_path.endswith('.wav')
        assert temp_dir in audio_path
        mock_subprocess.assert_called_once()
    
    @patch('subprocess.run')
    def test_extract_audio_ffmpeg_error(self, mock_subprocess, transcription_service, temp_dir):
        """Test audio extraction with FFmpeg error"""
        video_path = os.path.join(temp_dir, "test_video.mp4")
        with open(video_path, 'wb') as f:
            f.write(b"dummy video content")
        
        mock_subprocess.side_effect = Exception("FFmpeg error")
        
        with pytest.raises(TranscriptionError, match="Failed to extract audio"):
            transcription_service.extract_audio(video_path)
    
    def test_extract_audio_missing_file(self, transcription_service):
        """Test audio extraction with missing video file"""
        with pytest.raises(TranscriptionError, match="Video file not found"):
            transcription_service.extract_audio("/nonexistent/file.mp4")
    
    @patch('subprocess.run')
    def test_get_audio_duration_success(self, mock_subprocess, transcription_service, temp_dir):
        """Test successful audio duration retrieval"""
        audio_path = os.path.join(temp_dir, "test_audio.wav")
        with open(audio_path, 'wb') as f:
            f.write(b"dummy audio content")
        
        mock_subprocess.return_value.stdout = '{"format": {"duration": "120.5"}}'
        mock_subprocess.return_value.returncode = 0
        
        duration = transcription_service.get_audio_duration(audio_path)
        
        assert duration == 120.5
        mock_subprocess.assert_called_once()
    
    def test_split_audio_small_file(self, transcription_service, temp_dir):
        """Test that small audio files are not split"""
        audio_path = os.path.join(temp_dir, "small_audio.wav")
        with open(audio_path, 'wb') as f:
            f.write(b"small audio content")  # Under 20MB
        
        chunks = transcription_service.split_audio_for_transcription(audio_path)
        
        assert len(chunks) == 1
        assert chunks[0] == audio_path
    
    @patch.object(TranscriptionService, 'get_audio_duration')
    def test_split_audio_large_file(self, mock_duration, transcription_service, temp_dir):
        """Test that large audio files are split into chunks"""
        audio_path = os.path.join(temp_dir, "large_audio.wav")
        # Create a file larger than the chunk size
        large_content = b"x" * (25 * 1024 * 1024)  # 25MB
        with open(audio_path, 'wb') as f:
            f.write(large_content)
        
        mock_duration.return_value = 300.0  # 5 minutes
        
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value.returncode = 0
            chunks = transcription_service.split_audio_for_transcription(audio_path)
        
        assert len(chunks) > 1
        assert all(chunk.endswith('.wav') for chunk in chunks)
    
    async def test_transcribe_single_file_success(self, transcription_service, temp_dir, mock_openai_client):
        """Test successful transcription of a single file"""
        audio_path = os.path.join(temp_dir, "test_audio.wav")
        with open(audio_path, 'wb') as f:
            f.write(b"dummy audio content")
        
        # Mock the split function to return single file
        with patch.object(transcription_service, 'split_audio_for_transcription') as mock_split:
            mock_split.return_value = [audio_path]
            
            result = await transcription_service.transcribe_with_timestamps(audio_path)
        
        assert 'text' in result
        assert 'segments' in result
        assert 'words' in result
        assert result['text'] == 'This is a test transcription'
    
    async def test_transcribe_multiple_chunks(self, transcription_service, temp_dir, mock_openai_client):
        """Test transcription of multiple chunks"""
        audio_path = os.path.join(temp_dir, "test_audio.wav")
        chunk_paths = [
            os.path.join(temp_dir, "chunk_0.wav"),
            os.path.join(temp_dir, "chunk_1.wav")
        ]
        
        # Create dummy files
        for path in [audio_path] + chunk_paths:
            with open(path, 'wb') as f:
                f.write(b"dummy audio content")
        
        with patch.object(transcription_service, 'split_audio_for_transcription') as mock_split:
            mock_split.return_value = chunk_paths
            
            with patch.object(transcription_service, 'get_audio_duration') as mock_duration:
                mock_duration.return_value = 60.0
                
                result = await transcription_service.transcribe_with_timestamps(audio_path)
        
        assert 'text' in result
        assert 'segments' in result
        assert 'words' in result
    
    async def test_transcribe_api_error(self, transcription_service, temp_dir, mock_openai_client):
        """Test transcription with OpenAI API error"""
        audio_path = os.path.join(temp_dir, "test_audio.wav")
        with open(audio_path, 'wb') as f:
            f.write(b"dummy audio content")
        
        # Mock API error
        mock_openai_client.return_value.audio.transcriptions.create.side_effect = Exception("API Error")
        
        with patch.object(transcription_service, 'split_audio_for_transcription') as mock_split:
            mock_split.return_value = [audio_path]
            
            with pytest.raises(TranscriptionError, match="Failed to transcribe audio"):
                await transcription_service.transcribe_with_timestamps(audio_path)
    
    def test_transcribe_chunk_sync_success(self, transcription_service, temp_dir, mock_openai_client):
        """Test synchronous chunk transcription"""
        chunk_path = os.path.join(temp_dir, "chunk.wav")
        with open(chunk_path, 'wb') as f:
            f.write(b"dummy audio content")
        
        result = transcription_service.transcribe_chunk_sync(chunk_path, 0, 0.0)
        
        assert result['success'] == True
        assert result['chunk_index'] == 0
        assert 'text' in result
        assert 'segments' in result
        assert 'words' in result
    
    def test_transcribe_chunk_sync_error(self, transcription_service, temp_dir, mock_openai_client):
        """Test synchronous chunk transcription with error"""
        chunk_path = os.path.join(temp_dir, "chunk.wav")
        with open(chunk_path, 'wb') as f:
            f.write(b"dummy audio content")
        
        mock_openai_client.return_value.audio.transcriptions.create.side_effect = Exception("Chunk error")
        
        result = transcription_service.transcribe_chunk_sync(chunk_path, 0, 0.0)
        
        assert result['success'] == False
        assert 'error' in result
    
    async def test_transcribe_chunks_parallel(self, transcription_service, temp_dir, mock_openai_client):
        """Test parallel chunk transcription"""
        chunk_info = [
            {'path': os.path.join(temp_dir, 'chunk_0.wav'), 'start_offset': 0.0, 'duration': 60.0},
            {'path': os.path.join(temp_dir, 'chunk_1.wav'), 'start_offset': 60.0, 'duration': 60.0}
        ]
        
        # Create dummy chunk files
        for info in chunk_info:
            with open(info['path'], 'wb') as f:
                f.write(b"dummy audio content")
        
        results = await transcription_service.transcribe_chunks_parallel(chunk_info)
        
        assert len(results) == 2
        for result in results:
            assert result['success'] == True 