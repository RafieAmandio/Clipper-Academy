import pytest
import numpy as np
import cv2
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from app.services.object_detection import ObjectDetectionService, FaceLayoutResult
from app.config.settings import Settings
from app.core.exceptions import VideoProcessingError


class TestObjectDetectionService:
    """Test cases for ObjectDetectionService"""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing"""
        settings = Mock(spec=Settings)
        settings.enable_object_detection = True
        settings.object_detection_type = "face"
        settings.max_detection_frames = 10
        settings.min_detection_confidence = 0.3
        settings.smart_cropping_enabled = True
        settings.temp_dir = "/tmp"
        settings.clips_dir = "/tmp/clips"
        settings.results_dir = "/tmp/results"
        return settings
    
    @pytest.fixture
    def service(self, mock_settings):
        """Create ObjectDetectionService instance for testing"""
        with patch('app.services.object_detection.cv2.CascadeClassifier') as mock_cascade:
            mock_cascade.return_value = Mock()
            service = ObjectDetectionService(mock_settings)
            return service
    
    @pytest.fixture
    def sample_frame(self):
        """Create a sample frame for testing"""
        # Create a 640x480 frame with a simple face-like region
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        # Add a face-like region in the center
        cv2.rectangle(frame, (250, 150), (390, 330), (255, 255, 255), -1)
        return frame
    
    @pytest.fixture
    def sample_faces(self):
        # Create sample face detections
        return [
            {'x': 100, 'y': 100, 'width': 80, 'height': 80, 'confidence': 0.8},
            {'x': 300, 'y': 120, 'width': 90, 'height': 90, 'confidence': 0.7},
            {'x': 500, 'y': 150, 'width': 70, 'height': 70, 'confidence': 0.6}
        ]
    
    def test_init_with_haar_cascade(self, mock_settings):
        """Test initialization with Haar cascade available"""
        with patch('app.services.object_detection.cv2.CascadeClassifier') as mock_cascade:
            mock_cascade_instance = Mock()
            mock_cascade_instance.empty.return_value = False
            mock_cascade.return_value = mock_cascade_instance
            
            service = ObjectDetectionService(mock_settings)
            
            assert service.haar_cascade is not None
    
    def test_init_without_haar_cascade(self, mock_settings):
        """Test initialization when Haar cascade is not available"""
        with patch('app.services.object_detection.cv2.CascadeClassifier') as mock_cascade:
            mock_cascade_instance = Mock()
            mock_cascade_instance.empty.return_value = True
            mock_cascade.return_value = mock_cascade_instance
            
            service = ObjectDetectionService(mock_settings)
            
            assert service.haar_cascade is None
    
    def test_detect_faces_with_detections(self, service, sample_frame):
        """Test face detection when faces are detected"""
        # Mock the cascade to return face detections
        mock_faces = np.array([[250, 150, 140, 180]])  # x, y, w, h
        service.haar_cascade.detectMultiScale.return_value = mock_faces
        
        detections = service.detect_faces(sample_frame)
        
        assert len(detections) == 1
        assert detections[0]['x'] == 250
        assert detections[0]['y'] == 150
        assert detections[0]['width'] == 140
        assert detections[0]['height'] == 180
        assert detections[0]['confidence'] == 0.8  # Default confidence for Haar cascade
    
    def test_detect_faces_no_detections(self, service, sample_frame):
        """Test face detection when no faces are detected"""
        # Mock the cascade to return no detections
        service.haar_cascade.detectMultiScale.return_value = np.array([])
        
        detections = service.detect_faces(sample_frame)
        
        assert len(detections) == 0
    
    def test_detect_faces_without_cascade(self, mock_settings):
        """Test face detection when cascade is not loaded"""
        with patch('app.services.object_detection.cv2.CascadeClassifier') as mock_cascade:
            with patch('app.services.object_detection.os.path.exists', return_value=False):
                service = ObjectDetectionService(mock_settings)
                service.haar_cascade = None
                
                detections = service.detect_faces(sample_frame)
                assert len(detections) == 0
    
    def test_detect_objects_in_frame_face_type(self, service, sample_frame):
        """Test object detection with face type"""
        mock_faces = np.array([[250, 150, 140, 180]])
        service.haar_cascade.detectMultiScale.return_value = mock_faces
        
        detections = service.detect_objects_in_frame(sample_frame, "face")
        
        assert len(detections) == 1
        assert detections[0]['x'] == 250
        assert detections[0]['y'] == 150
        assert detections[0]['width'] == 140
        assert detections[0]['height'] == 180
    
    def test_detect_objects_in_frame_none_type(self, service, sample_frame):
        """Test object detection with none type"""
        detections = service.detect_objects_in_frame(sample_frame, "none")
        
        assert len(detections) == 0
    
    def test_detect_objects_in_frame_unsupported_type(self, service, sample_frame):
        """Test object detection with unsupported type"""
        mock_faces = np.array([[250, 150, 140, 180]])
        service.haar_cascade.detectMultiScale.return_value = mock_faces
        
        detections = service.detect_objects_in_frame(sample_frame, "unsupported")
        
        # Should default to face detection
        assert len(detections) == 1
        assert detections[0]['x'] == 250
        assert detections[0]['y'] == 150
    
    @patch('app.services.object_detection.cv2.VideoCapture')
    def test_extract_frames_for_detection_success(self, mock_video_capture, service):
        """Test successful frame extraction"""
        # Mock video properties
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_COUNT: 100,
            cv2.CAP_PROP_FPS: 30
        }.get(prop, 0)
        mock_cap.read.return_value = (True, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8))
        mock_video_capture.return_value = mock_cap
        
        frames = service.extract_frames_for_detection("test_video.mp4", max_frames=5)
        
        assert len(frames) == 5
        assert all(isinstance(frame[0], float) for frame in frames)  # timestamp
        assert all(isinstance(frame[1], np.ndarray) for frame in frames)  # frame data
    
    @patch('app.services.object_detection.cv2.VideoCapture')
    def test_extract_frames_for_detection_video_not_opened(self, mock_video_capture, service):
        """Test frame extraction when video cannot be opened"""
        mock_cap = Mock()
        mock_cap.isOpened.return_value = False
        mock_video_capture.return_value = mock_cap
        
        with pytest.raises(VideoProcessingError, match="Could not open video"):
            service.extract_frames_for_detection("test_video.mp4")
    
    @patch('app.services.object_detection.cv2.VideoCapture')
    def test_extract_frames_for_detection_read_error(self, mock_video_capture, service):
        """Test frame extraction when frame reading fails"""
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_COUNT: 100,
            cv2.CAP_PROP_FPS: 30
        }.get(prop, 0)
        mock_cap.read.return_value = (False, None)
        mock_video_capture.return_value = mock_cap
        
        frames = service.extract_frames_for_detection("test_video.mp4", max_frames=5)
        
        assert len(frames) == 0
    
    @patch('app.services.object_detection.ObjectDetectionService.extract_frames_for_detection')
    def test_analyze_video_objects_with_detections(self, mock_extract_frames, service, sample_frame):
        """Test video analysis when objects are detected"""
        # Mock frame extraction
        mock_extract_frames.return_value = [
            (0.0, sample_frame),
            (1.0, sample_frame),
            (2.0, sample_frame)
        ]
        
        # Mock face detection
        mock_faces = np.array([[250, 150, 140, 180]])
        service.haar_cascade.detectMultiScale.return_value = mock_faces
        
        analysis = service.analyze_video_objects("test_video.mp4", "face", max_frames=3)
        
        assert analysis['total_detections'] == 3
        assert analysis['frames_analyzed'] == 3
        assert analysis['most_common_object'] == "face"
        assert 'frame_analysis' in analysis
        assert len(analysis['frame_analysis']) == 3
    
    @patch('app.services.object_detection.ObjectDetectionService.extract_frames_for_detection')
    def test_analyze_video_objects_no_detections(self, mock_extract_frames, service, sample_frame):
        """Test video analysis when no objects are detected"""
        # Mock frame extraction
        mock_extract_frames.return_value = [
            (0.0, sample_frame),
            (1.0, sample_frame)
        ]
        
        # Mock no face detections
        service.haar_cascade.detectMultiScale.return_value = np.array([])
        
        analysis = service.analyze_video_objects("test_video.mp4", "face", max_frames=2)
        
        assert analysis['total_detections'] == 0
        assert analysis['frames_analyzed'] == 2
        assert analysis['most_common_object'] == "none"
        assert analysis['average_confidence'] == 0.0
    
    def test_calculate_optimal_crop_region_with_detections(self, service):
        """Test crop calculation when objects are detected"""
        video_info = {"width": 1920, "height": 1080}
        object_analysis = {
            "total_detections": 5,
            "average_center_x": 960,  # Center of 1920
            "average_center_y": 540,  # Center of 1080
            "average_confidence": 0.8
        }
        
        crop_params = service.calculate_optimal_crop_region(
            video_info, object_analysis, "9:16"
        )
        
        assert crop_params['target_aspect_ratio'] == "9:16"
        assert crop_params['object_centered'] is True
        assert crop_params['detection_confidence'] == 0.8
        assert crop_params['width'] > 0
        assert crop_params['height'] > 0
        assert crop_params['x_offset'] >= 0
        assert crop_params['y_offset'] >= 0
    
    def test_calculate_optimal_crop_region_no_detections(self, service):
        """Test crop calculation when no objects are detected"""
        video_info = {"width": 1920, "height": 1080}
        object_analysis = {
            "total_detections": 0,
            "average_center_x": 0,
            "average_center_y": 0,
            "average_confidence": 0.0
        }
        
        crop_params = service.calculate_optimal_crop_region(
            video_info, object_analysis, "9:16"
        )
        
        assert crop_params['target_aspect_ratio'] == "9:16"
        assert crop_params['object_centered'] is False
        assert crop_params['detection_confidence'] == 0.0
        assert crop_params['width'] > 0
        assert crop_params['height'] > 0
    
    def test_calculate_optimal_crop_region_different_aspect_ratios(self, service):
        """Test crop calculation with different aspect ratios"""
        video_info = {"width": 1920, "height": 1080}
        object_analysis = {
            "total_detections": 3,
            "average_center_x": 960,
            "average_center_y": 540,
            "average_confidence": 0.7
        }
        
        # Test 16:9 aspect ratio
        crop_16_9 = service.calculate_optimal_crop_region(
            video_info, object_analysis, "16:9"
        )
        assert crop_16_9['target_aspect_ratio'] == "16:9"
        
        # Test 1:1 aspect ratio
        crop_1_1 = service.calculate_optimal_crop_region(
            video_info, object_analysis, "1:1"
        )
        assert crop_1_1['target_aspect_ratio'] == "1:1"
    
    def test_calculate_center_crop(self, service):
        """Test center crop calculation"""
        crop_params = service._calculate_center_crop(1920, 1080, 9/16)
        
        assert crop_params['x_offset'] == 240  # (1920 - 1080 * 9/16) / 2
        assert crop_params['y_offset'] == 0
        assert crop_params['width'] == 1080 * 9/16
        assert crop_params['height'] == 1080
        assert crop_params['object_centered'] is False
        assert crop_params['detection_confidence'] == 0.0
    
    @patch('app.services.object_detection.ObjectDetectionService.extract_frames_for_detection')
    def test_analyze_video_objects_exception_handling(self, mock_extract_frames, service):
        """Test exception handling in video analysis"""
        mock_extract_frames.side_effect = Exception("Test error")
        
        with pytest.raises(VideoProcessingError, match="Failed to analyze video objects"):
            service.analyze_video_objects("test_video.mp4", "face")
    
    def test_calculate_optimal_crop_region_exception_handling(self, service):
        """Test exception handling in crop calculation"""
        video_info = {"width": 1920, "height": 1080}
        object_analysis = {
            "total_detections": 3,
            "average_center_x": 960,
            "average_center_y": 540,
            "average_confidence": 0.7
        }
        
        # Test with invalid aspect ratio
        with pytest.raises(VideoProcessingError, match="Unsupported aspect ratio"):
            service.calculate_optimal_crop_region(video_info, object_analysis, "invalid")
    
    def test_confidence_calculation_edge_cases(self, service, sample_frame):
        """Test confidence calculation in edge cases"""
        # Test with face at center
        mock_faces = np.array([[300, 200, 100, 100]])  # Center of 640x480
        service.haar_cascade.detectMultiScale.return_value = mock_faces
        
        detections = service.detect_faces(sample_frame)
        assert len(detections) == 1
        assert detections[0]['confidence'] > 0.5  # Should have high confidence for center face
        
        # Test with face at edge
        mock_faces = np.array([[0, 0, 50, 50]])  # Top-left corner
        service.haar_cascade.detectMultiScale.return_value = mock_faces
        
        detections = service.detect_faces(sample_frame)
        assert len(detections) == 1
        assert detections[0]['confidence'] < 0.5  # Should have lower confidence for edge face 
    
    def test_calculate_face_layout_single_face(self, service):
        """Test face layout calculation for single face"""
        faces = [
            {'x': 100, 'y': 100, 'width': 80, 'height': 80, 'confidence': 0.8}
        ]
        
        result = service.calculate_face_layout(faces, 1080, 1920, "single")
        
        assert result.total_faces == 1
        assert result.layout_type == "single"
        assert result.grid_rows == 1
        assert result.grid_cols == 1
        assert result.cell_width == 1080
        assert result.cell_height == 1920
    
    def test_calculate_face_layout_grid_two_faces(self, service):
        """Test face layout calculation for two faces in grid mode"""
        faces = [
            {'x': 100, 'y': 100, 'width': 80, 'height': 80, 'confidence': 0.8},
            {'x': 300, 'y': 120, 'width': 90, 'height': 90, 'confidence': 0.7}
        ]
        
        result = service.calculate_face_layout(faces, 1080, 1920, "grid")
        
        assert result.total_faces == 2
        assert result.layout_type == "grid"
        assert result.grid_rows == 1
        assert result.grid_cols == 2
        assert result.cell_width > 0
        assert result.cell_height > 0
    
    def test_calculate_face_layout_grid_four_faces(self, service):
        """Test face layout calculation for four faces in grid mode"""
        faces = [
            {'x': 100, 'y': 100, 'width': 80, 'height': 80, 'confidence': 0.8},
            {'x': 300, 'y': 120, 'width': 90, 'height': 90, 'confidence': 0.7},
            {'x': 500, 'y': 150, 'width': 70, 'height': 70, 'confidence': 0.6},
            {'x': 200, 'y': 300, 'width': 85, 'height': 85, 'confidence': 0.75}
        ]
        
        result = service.calculate_face_layout(faces, 1080, 1920, "grid")
        
        assert result.total_faces == 4
        assert result.layout_type == "grid"
        assert result.grid_rows == 2
        assert result.grid_cols == 2
        assert result.cell_width > 0
        assert result.cell_height > 0
    
    def test_calculate_face_layout_no_faces(self, service):
        """Test face layout calculation with no faces"""
        result = service.calculate_face_layout([], 1080, 1920, "grid")
        
        assert result.total_faces == 0
        assert result.layout_type == "none"
        assert result.grid_rows == 0
        assert result.grid_cols == 0
    
    def test_calculate_face_layout_single_mode(self, service, sample_faces):
        """Test face layout calculation in single mode with multiple faces"""
        result = service.calculate_face_layout(sample_faces, 1080, 1920, "single")
        
        assert result.total_faces == 1
        assert result.layout_type == "single"
        # Should select the face with highest confidence
        assert result.faces[0]['confidence'] == 0.8
    
    @patch('cv2.CascadeClassifier')
    def test_detect_faces_with_cascade(self, mock_cascade, service, sample_frame):
        """Test face detection with Haar Cascade"""
        # Mock the cascade classifier
        mock_cascade_instance = Mock()
        mock_cascade.return_value = mock_cascade_instance
        mock_cascade_instance.detectMultiScale.return_value = [
            (100, 100, 80, 80),
            (300, 120, 90, 90)
        ]
        
        # Set the cascade in the service
        service.haar_cascade = mock_cascade_instance
        
        results = service.detect_faces(sample_frame)
        
        assert len(results) == 2
        assert all(isinstance(r, dict) for r in results)
        assert all('x' in r and 'y' in r and 'width' in r and 'height' in r for r in results)
        assert all(0.8 == r['confidence'] for r in results)  # Default confidence for Haar cascade
    
    def test_detect_faces_no_cascade(self, service, sample_frame):
        """Test face detection when cascade is not loaded"""
        service.haar_cascade = None
        
        results = service.detect_faces(sample_frame)
        
        assert len(results) == 0
    
    def test_detect_objects_in_frame_face(self, service, sample_frame):
        """Test object detection in frame with face type"""
        with patch.object(service, 'detect_faces') as mock_detect:
            mock_detect.return_value = [
                {'x': 100, 'y': 100, 'width': 80, 'height': 80, 'confidence': 0.8}
            ]
            
            results = service.detect_objects_in_frame(sample_frame, "face")
            
            assert len(results) == 1
            assert results[0]['x'] == 100
            assert results[0]['y'] == 100
    
    def test_detect_objects_in_frame_none(self, service, sample_frame):
        """Test object detection in frame with none type"""
        results = service.detect_objects_in_frame(sample_frame, "none")
        
        assert len(results) == 0
    
    def test_detect_objects_in_frame_unknown(self, service, sample_frame):
        """Test object detection in frame with unknown type (should default to face)"""
        with patch.object(service, 'detect_faces') as mock_detect:
            mock_detect.return_value = []
            
            results = service.detect_objects_in_frame(sample_frame, "unknown")
            
            mock_detect.assert_called_once_with(sample_frame)
    
    @patch('app.services.object_detection.ObjectDetectionService.extract_frames_for_detection')
    @patch('app.services.object_detection.ObjectDetectionService.detect_objects_in_frame')
    def test_analyze_video_objects(self, mock_detect, mock_extract, service):
        """Test video object analysis"""
        # Mock frame extraction
        mock_extract.return_value = [
            (0.0, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)),
            (1.0, np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8))
        ]
        
        # Mock object detection
        mock_detect.side_effect = [
            [{'x': 100, 'y': 100, 'width': 80, 'height': 80, 'confidence': 0.8}],
            [{'x': 120, 'y': 110, 'width': 85, 'height': 85, 'confidence': 0.7}]
        ]
        
        analysis = service.analyze_video_objects("test_video.mp4", "face", 2, "grid")
        
        assert analysis['total_detections'] == 2
        assert analysis['frames_analyzed'] == 2
        assert analysis['max_faces_in_frame'] == 1
    
    def test_calculate_optimal_crop_region_single_face(self, service):
        """Test optimal crop region calculation for single face"""
        video_info = {"width": 1920, "height": 1080}
        object_analysis = {
            "total_detections": 1,
            "average_center_x": 960,
            "average_center_y": 540,
            "average_confidence": 0.8,
            "max_faces_in_frame": 1
        }
        
        crop_params = service.calculate_optimal_crop_region(
            video_info, object_analysis, "9:16", "single"
        )
        
        assert crop_params['object_centered'] == True
        assert crop_params['layout_type'] == "single"
        assert crop_params['detection_confidence'] == 0.8
    
    def test_calculate_optimal_crop_region_grid(self, service):
        """Test optimal crop region calculation for grid layout"""
        video_info = {"width": 1920, "height": 1080}
        object_analysis = {
            "total_detections": 4,
            "average_center_x": 960,
            "average_center_y": 540,
            "average_confidence": 0.7,
            "max_faces_in_frame": 4
        }
        
        crop_params = service.calculate_optimal_crop_region(
            video_info, object_analysis, "9:16", "grid"
        )
        
        assert crop_params['object_centered'] == True
        assert crop_params['layout_type'] == "grid"
        assert crop_params['max_faces'] == 4
    
    def test_calculate_optimal_crop_region_no_detections(self, service):
        """Test optimal crop region calculation with no detections"""
        video_info = {"width": 1920, "height": 1080}
        object_analysis = {
            "total_detections": 0,
            "average_center_x": 0,
            "average_center_y": 0,
            "average_confidence": 0,
            "max_faces_in_frame": 0
        }
        
        crop_params = service.calculate_optimal_crop_region(
            video_info, object_analysis, "9:16", "grid"
        )
        
        assert crop_params['object_centered'] == False
        assert crop_params['layout_type'] == "center"
        assert crop_params['detection_confidence'] == 0.0
    
    def test_calculate_optimal_crop_region_different_aspect_ratios(self, service):
        """Test optimal crop region calculation with different aspect ratios"""
        video_info = {"width": 1920, "height": 1080}
        object_analysis = {
            "total_detections": 1,
            "average_center_x": 960,
            "average_center_y": 540,
            "average_confidence": 0.8,
            "max_faces_in_frame": 1
        }
        
        # Test 16:9 aspect ratio
        crop_params_16_9 = service.calculate_optimal_crop_region(
            video_info, object_analysis, "16:9", "single"
        )
        assert crop_params_16_9['target_aspect_ratio'] == "1600:100"
        
        # Test 1:1 aspect ratio
        crop_params_1_1 = service.calculate_optimal_crop_region(
            video_info, object_analysis, "1:1", "single"
        )
        assert crop_params_1_1['target_aspect_ratio'] == "100:100"
    
    def test_face_layout_result_creation(self):
        """Test FaceLayoutResult creation"""
        faces = [
            {'x': 100, 'y': 100, 'width': 80, 'height': 80, 'confidence': 0.8}
        ]
        
        result = FaceLayoutResult(
            faces=faces,
            grid_rows=1,
            grid_cols=1,
            cell_width=1080,
            cell_height=1920,
            total_faces=1,
            layout_type="single"
        )
        
        assert result.faces == faces
        assert result.grid_rows == 1
        assert result.grid_cols == 1
        assert result.cell_width == 1080
        assert result.cell_height == 1920
        assert result.total_faces == 1
        assert result.layout_type == "single" 