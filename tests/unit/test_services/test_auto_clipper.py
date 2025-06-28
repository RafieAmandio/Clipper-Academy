import pytest
from unittest.mock import Mock, patch
from app.services.auto_clipper import AutoClipperService
from app.config.settings import Settings


class TestAutoClipperService:
    """Test cases for AutoClipperService"""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing"""
        settings = Mock(spec=Settings)
        settings.temp_dir = "/tmp"
        settings.clips_dir = "/tmp/clips"
        settings.results_dir = "/tmp/results"
        settings.min_clip_duration = 10
        settings.max_clip_duration = 120
        return settings
    
    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client"""
        return Mock()
    
    @pytest.fixture
    def service(self, mock_settings, mock_openai_client):
        """AutoClipperService instance for testing"""
        return AutoClipperService(mock_settings, mock_openai_client)
    
    def test_detect_language_indonesian(self, service):
        """Test Indonesian language detection"""
        transcript_data = {
            'text': 'Halo teman-teman, gimana kabarnya? Saya mau cerita tentang pengalaman saya kemarin. Jadi gini, saya lagi jalan-jalan di mall terus ketemu teman lama. Wah, seneng banget sih!'
        }
        
        detected_language = service.detect_language_from_transcript(transcript_data)
        assert detected_language == 'id'
    
    def test_detect_language_english(self, service):
        """Test English language detection"""
        transcript_data = {
            'text': 'Hello everyone, how are you doing? I want to tell you about my experience yesterday. So, I was walking in the mall and I met an old friend. Wow, I was so happy!'
        }
        
        detected_language = service.detect_language_from_transcript(transcript_data)
        assert detected_language == 'en'
    
    def test_detect_language_indonesian_slang(self, service):
        """Test Indonesian language detection with slang"""
        transcript_data = {
            'text': 'Gue lagi jalan-jalan terus ketemu lo di situ. Gimana sih? Kok gitu aja?'
        }
        
        detected_language = service.detect_language_from_transcript(transcript_data)
        assert detected_language == 'id'
    
    def test_detect_language_mixed_content(self, service):
        """Test language detection with mixed content (should default to English)"""
        transcript_data = {
            'text': 'Hello, saya mau tell you something. Ini adalah mixed content.'
        }
        
        detected_language = service.detect_language_from_transcript(transcript_data)
        # Should default to English for mixed content
        assert detected_language == 'en'
    
    def test_split_long_clips(self, service):
        """Test splitting long clips into multiple parts"""
        clips_data = [
            {
                'title': 'Test Clip',
                'description': 'A test clip',
                'start_time': '00:00',
                'end_time': '01:00',  # 60 seconds
                'duration': 60,
                'engagement_score': 8.0,
                'viral_score': 8.5,
                'language': 'id'
            }
        ]
        
        video_duration = 120.0
        
        # Mock the time_to_seconds method
        with patch.object(service.video_processing_service, 'time_to_seconds') as mock_time:
            mock_time.side_effect = lambda x: 0 if x == '00:00' else 60
            
            split_clips = service.split_long_clips(clips_data, video_duration)
            
            # Should split into 2 parts
            assert len(split_clips) == 2
            
            # Check first part
            assert split_clips[0]['title'] == 'Test Clip (Bagian 1/2)'
            assert split_clips[0]['duration'] == 30.0
            
            # Check second part
            assert split_clips[1]['title'] == 'Test Clip (Bagian 2/2)'
            assert split_clips[1]['duration'] == 30.0
    
    def test_split_long_clips_english(self, service):
        """Test splitting long clips in English"""
        clips_data = [
            {
                'title': 'Test Clip',
                'description': 'A test clip',
                'start_time': '00:00',
                'end_time': '01:00',  # 60 seconds
                'duration': 60,
                'engagement_score': 8.0,
                'viral_score': 8.5,
                'language': 'en'
            }
        ]
        
        video_duration = 120.0
        
        # Mock the time_to_seconds method
        with patch.object(service.video_processing_service, 'time_to_seconds') as mock_time:
            mock_time.side_effect = lambda x: 0 if x == '00:00' else 60
            
            split_clips = service.split_long_clips(clips_data, video_duration)
            
            # Should split into 2 parts
            assert len(split_clips) == 2
            
            # Check first part
            assert split_clips[0]['title'] == 'Test Clip (Part 1/2)'
            assert split_clips[0]['duration'] == 30.0
            
            # Check second part
            assert split_clips[1]['title'] == 'Test Clip (Part 2/2)'
            assert split_clips[1]['duration'] == 30.0
    
    def test_split_long_clips_short_duration(self, service):
        """Test that short clips are not split"""
        clips_data = [
            {
                'title': 'Short Clip',
                'description': 'A short clip',
                'start_time': '00:00',
                'end_time': '00:30',  # 30 seconds
                'duration': 30,
                'engagement_score': 8.0,
                'viral_score': 8.5,
                'language': 'id'
            }
        ]
        
        video_duration = 120.0
        
        # Mock the time_to_seconds method
        with patch.object(service.video_processing_service, 'time_to_seconds') as mock_time:
            mock_time.side_effect = lambda x: 0 if x == '00:00' else 30
            
            split_clips = service.split_long_clips(clips_data, video_duration)
            
            # Should not split
            assert len(split_clips) == 1
            assert split_clips[0]['title'] == 'Short Clip'
    
    def test_get_language_specific_prompt_indonesian(self, service):
        """Test Indonesian prompt generation"""
        transcript_text = "[00:00-00:10] Halo teman-teman\n[00:10-00:20] Gimana kabarnya?"
        video_duration = 60.0
        
        prompt = service.get_language_specific_prompt('id', transcript_text, video_duration)
        
        # Check that prompt contains Indonesian instructions
        assert 'Kamu adalah ahli strategi konten TikTok' in prompt
        assert 'Indonesia' in prompt
        assert 'Durasi Video' in prompt
        assert 'Transkrip dengan timestamp' in prompt
    
    def test_get_language_specific_prompt_english(self, service):
        """Test English prompt generation"""
        transcript_text = "[00:00-00:10] Hello everyone\n[00:10-00:20] How are you?"
        video_duration = 60.0
        
        prompt = service.get_language_specific_prompt('en', transcript_text, video_duration)
        
        # Check that prompt contains English instructions
        assert 'You are an expert TikTok content strategist' in prompt
        assert 'Video Duration' in prompt
        assert 'Transcript with timestamps' in prompt
    
    def test_get_simple_prompt_indonesian(self, service):
        """Test Indonesian simple prompt generation"""
        transcript_text = "[00:00-00:10] Halo teman-teman\n[00:10-00:20] Gimana kabarnya?"
        video_duration = 60.0
        
        prompt = service.get_simple_prompt('id', transcript_text, video_duration)
        
        # Check that prompt contains Indonesian instructions
        assert 'Analisis transkrip video ini' in prompt
        assert 'Durasi Video' in prompt
        assert 'Hanya JSON' in prompt
    
    def test_get_simple_prompt_english(self, service):
        """Test English simple prompt generation"""
        transcript_text = "[00:00-00:10] Hello everyone\n[00:10-00:20] How are you?"
        video_duration = 60.0
        
        prompt = service.get_simple_prompt('en', transcript_text, video_duration)
        
        # Check that prompt contains English instructions
        assert 'Analyze this video transcript' in prompt
        assert 'Video Duration' in prompt
        assert 'Only JSON' in prompt
    
    def test_extract_clips_manually(self, service):
        """Test manual clip extraction from malformed response"""
        malformed_response = """
        Here are some clips:
        {
            "title": "Test Clip 1",
            "description": "A test clip",
            "start_time": "00:00",
            "end_time": "00:30",
            "duration": 30,
            "engagement_score": 8.0,
            "viral_score": 8.5,
            "hook_type": "shock",
            "target_audience": "general",
            "shareability_factor": "engaging content"
        }
        {
            "title": "Test Clip 2",
            "description": "Another test clip",
            "start_time": "00:30",
            "end_time": "01:00",
            "duration": 30,
            "engagement_score": 7.5,
            "viral_score": 8.0,
            "hook_type": "curiosity",
            "target_audience": "general",
            "shareability_factor": "interesting content"
        }
        """
        
        clips = service.extract_clips_manually(malformed_response)
        
        assert len(clips) == 2
        assert clips[0]['title'] == 'Test Clip 1'
        assert clips[0]['start_time'] == '00:00'
        assert clips[0]['end_time'] == '00:30'
        assert clips[1]['title'] == 'Test Clip 2'
        assert clips[1]['start_time'] == '00:30'
        assert clips[1]['end_time'] == '01:00'
    
    def test_extract_clips_manually_no_valid_clips(self, service):
        """Test manual extraction when no valid clips are found"""
        invalid_response = "This is not a valid response with any clip data."
        
        clips = service.extract_clips_manually(invalid_response)
        
        assert len(clips) == 0 