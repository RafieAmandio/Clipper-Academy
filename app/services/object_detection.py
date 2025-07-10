import cv2
import numpy as np
import logging
from typing import List, Dict, Optional, Tuple, NamedTuple
from app.services.base import BaseService
from app.config.settings import Settings
from app.core.exceptions import VideoProcessingError
import math
import subprocess
import ffmpeg
import torch
from pathlib import Path
from ultralytics import YOLO
from ultralytics.utils import LOGGER
import sys
import contextlib
import os
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_distances

logger = logging.getLogger(__name__)

LOGGER.setLevel("WARNING")

# Context manager to suppress stdout/stderr
@contextlib.contextmanager
def suppress_stdout_stderr():
    with open(os.devnull, 'w') as devnull:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = devnull, devnull
        try:
            yield
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr

class FaceLayoutResult(NamedTuple):
    """Result of face layout calculation for grid display"""
    faces: List[Dict]
    grid_rows: int
    grid_cols: int
    cell_width: int
    cell_height: int
    total_faces: int
    layout_type: str  # "grid", "single", "none"


class ObjectDetectionService(BaseService):
    """Service for object detection in video frames using YOLOv8 (Ultralytics) [Upgraded from YOLOv5-face]"""
    
    def __init__(self, settings: Settings):
        """Initialize object detection service
        
        Args:
            settings: Application settings
        """
        super().__init__(settings)
        self.yolo_model = None
        self._initialize_yolo_face_detector()
    
    def _initialize_yolo_face_detector(self):
        """Load YOLOv8 model for face detection using Ultralytics package"""
        try:
            # You can use a custom face model or a general model (e.g., yolov8n.pt)
            # For face detection, you may want to use a custom-trained YOLOv8 model
            model_path = getattr(self.settings, 'YOLOV8_FACE_WEIGHTS', None)
            if not model_path:
                model_path = 'yolov8n.pt'
            self.yolo_model = YOLO(str(model_path))
            self.logger.info(f"YOLOv8 model loaded successfully from {model_path}.")
        except Exception as e:
            self.logger.error(f"Failed to load YOLOv8 model: {e}")
            self.yolo_model = None
    
    def detect_faces(self, frame: np.ndarray, method: str = "yolo") -> List[Dict]:
        """Detect faces using YOLOv8
        
        Args:
            frame: Input frame as numpy array
            method: Detection method (only 'yolo' is supported)
            
        Returns:
            List of detected faces with coordinates and confidence
        """
        if frame is None:
            return []
        if self.yolo_model is None:
            return []
        try:
            # YOLOv8 expects RGB images
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            with suppress_stdout_stderr():
                results = self.yolo_model(rgb_frame)
            faces = []
            for result in results:
                # Each result.boxes contains all detections for the image
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    conf = float(box.conf[0])
                    faces.append({
                        'x': x1,
                        'y': y1,
                        'width': x2 - x1,
                        'height': y2 - y1,
                        'confidence': conf
                    })
            return faces
        except Exception as e:
            self.logger.error(f"Error in YOLOv8 face detection: {e}")
            return []
    
    def calculate_face_layout(self, faces: List[Dict], target_width: int, target_height: int, 
                            layout_mode: str = "grid") -> FaceLayoutResult:
        """Calculate optimal layout for displaying multiple faces
        
        Args:
            faces: List of detected faces
            target_width: Target output width
            target_height: Target output height
            layout_mode: Layout mode ("grid", "single", "auto")
            
        Returns:
            FaceLayoutResult with layout information
        """
        if not faces:
            return FaceLayoutResult([], 0, 0, 0, 0, 0, "none")
        
        if layout_mode == "single":
            # Single face mode - use the most confident face
            best_face = max(faces, key=lambda f: f['confidence'])
            return FaceLayoutResult([best_face], 1, 1, target_width, target_height, 1, "single")
        
        # Grid layout mode
        total_faces = len(faces)
        
        if total_faces == 1:
            # Single face - use full frame
            return FaceLayoutResult(faces, 1, 1, target_width, target_height, 1, "single")
        
        # Calculate optimal grid dimensions
        grid_cols = math.ceil(math.sqrt(total_faces))
        grid_rows = math.ceil(total_faces / grid_cols)
        
        # Calculate cell dimensions with padding
        padding = 10  # pixels between cells
        cell_width = (target_width - (padding * (grid_cols + 1))) // grid_cols
        cell_height = (target_height - (padding * (grid_rows + 1))) // grid_rows
        
        # Ensure minimum cell size
        min_cell_size = 100
        if cell_width < min_cell_size or cell_height < min_cell_size:
            # Recalculate with fewer columns if cells are too small
            grid_cols = max(1, math.floor(math.sqrt(total_faces * target_width / target_height)))
            grid_rows = math.ceil(total_faces / grid_cols)
            cell_width = (target_width - (padding * (grid_cols + 1))) // grid_cols
            cell_height = (target_height - (padding * (grid_rows + 1))) // grid_rows
        
        return FaceLayoutResult(
            faces=faces,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            cell_width=cell_width,
            cell_height=cell_height,
            total_faces=total_faces,
            layout_type="grid"
        )
    
    def detect_objects_in_frame(self, frame: np.ndarray, detection_type: str = "face") -> List[Dict]:
        """Detect objects in a single frame
        
        Args:
            frame: Input frame as numpy array
            detection_type: Type of detection (currently only "face" is supported)
            
        Returns:
            List of detected objects
        """
        if detection_type == "face":
            return self.detect_faces(frame, method="yolo")
        elif detection_type == "none":
            return []
        else:
            # For any other type, default to face detection
            logger.warning(f"Detection type '{detection_type}' not supported, using face detection")
            return self.detect_faces(frame, method="yolo")
    
    def extract_frames_for_detection(self, video_path: str, max_frames: int = 10) -> List[Tuple[float, np.ndarray]]:
        """Extract frames from video for object detection
        
        Args:
            video_path: Path to video file
            max_frames: Maximum number of frames to extract
            
        Returns:
            List of (timestamp, frame) tuples
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise VideoProcessingError(f"Could not open video: {video_path}")
            
            # Get video properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            # Calculate frame intervals
            if total_frames <= max_frames:
                frame_indices = list(range(total_frames))
            else:
                frame_indices = [int(i * total_frames / max_frames) for i in range(max_frames)]
            
            frames = []
            for frame_idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if ret:
                    timestamp = frame_idx / fps
                    frames.append((timestamp, frame))
            
            cap.release()
            return frames
            
        except Exception as e:
            logger.error(f"Error extracting frames: {e}")
            raise VideoProcessingError(f"Failed to extract frames: {e}")
    
    def group_similar_faces_batched(self, frames: List[np.ndarray], all_faces: List[Dict], batch_size: int = 32, threshold: float = 0.5) -> List[Dict]:
        """
        Group similar faces across all frames using DeepFace embeddings (batched for performance).
        Uses DBSCAN clustering with cosine distance for robust grouping.
        Adds a 'face_id' field to each face dict.
        Args:
            frames: List of frames (np.ndarray) in the same order as detections
            all_faces: List of face dicts (must include 'x','y','width','height','frame_idx')
            batch_size: Batch size for embedding extraction
            threshold: Cosine distance threshold for DBSCAN
        Returns:
            List of face dicts with 'face_id' field
        """
        try:
            from deepface import DeepFace
            import cv2
            import numpy as np
        except ImportError:
            self.logger.warning('DeepFace or scikit-learn not installed, skipping face grouping. Returning original faces.')
            for face in all_faces:
                face['face_id'] = -1
            return all_faces
        # Crop all faces and keep mapping to original face dict
        face_imgs = []
        face_indices = []
        for idx, face in enumerate(all_faces):
            frame_idx = face.get('frame_idx', 0)
            frame = frames[frame_idx]
            x, y, w, h = face['x'], face['y'], face['width'], face['height']
            x, y = max(0, x), max(0, y)
            w, h = max(1, w), max(1, h)
            face_img = frame[y:y+h, x:x+w]
            if face_img.size == 0 or len(face_img.shape) != 3 or face_img.shape[2] != 3:
                # self.logger.warning(f"Invalid face crop at idx={idx}, frame_idx={frame_idx}, shape={face_img.shape if hasattr(face_img, 'shape') else 'N/A'}, dtype={face_img.dtype if hasattr(face_img, 'dtype') else 'N/A'}; skipping.")
                continue
            face_img_rgb = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
            face_imgs.append(face_img_rgb)
            face_indices.append(idx)
        if not face_imgs:
            self.logger.error("All face crops were invalid. Returning original detections with face_id=-1.")
            for face in all_faces:
                face['face_id'] = -1
            return all_faces
        # Batch embedding extraction
        embeddings = []
        for i in range(0, len(face_imgs), batch_size):
            batch = face_imgs[i:i+batch_size]
            try:
                for img in batch:
                    try:
                        embed_result = DeepFace.represent(img, model_name='Facenet', enforce_detection=False)
                        if embed_result and isinstance(embed_result, list):
                            embeddings.append(np.array(embed_result[0]['embedding']))
                        else:
                            # self.logger.warning("DeepFace embedding result was empty or not a list; using zeros.")
                            embeddings.append(np.zeros(128))
                    except Exception as e:
                        # self.logger.error(f"DeepFace embedding failed for one image: {e}")
                        embeddings.append(np.zeros(128))
            except Exception as e:
                # self.logger.error(f"DeepFace batch embedding failed: {e}")
                for _ in batch:
                    embeddings.append(np.zeros(128))
        # self.logger.info(f"Extracted {len(embeddings)} embeddings for {len(face_imgs)} valid face crops out of {len(all_faces)} total detections.")
        # DBSCAN clustering with cosine distance
        if len(embeddings) == 0:
            self.logger.error("No embeddings extracted. Returning original detections with face_id=-1.")
            for face in all_faces:
                face['face_id'] = -1
            return all_faces
        emb_array = np.stack(embeddings)
        # DBSCAN expects a distance matrix if metric='precomputed', or feature matrix if metric='cosine'
        db = DBSCAN(eps=threshold, min_samples=1, metric='cosine').fit(emb_array)
        labels = db.labels_
        # Assign face_id to each face (by mapping back to all_faces)
        for idx, face in enumerate(all_faces):
            if idx in face_indices:
                emb_idx = face_indices.index(idx)
                face['face_id'] = int(labels[emb_idx])
            else:
                face['face_id'] = -1
        unique_face_ids = set(f['face_id'] for f in all_faces)
        self.logger.info(f"[DEBUG] Unique face_ids assigned: {unique_face_ids}")
        if len(unique_face_ids) == 1:
            self.logger.warning("[DEBUG] All faces assigned the same face_id. Grouping may not be working as intended.")
        return all_faces

    def analyze_video_objects(self, video_path: str, detection_type: str = "face", 
                            max_frames: int = 10, layout_mode: str = "crop") -> Dict:
        """Analyze objects in video frames to determine optimal cropping
        
        Args:
            video_path: Path to video file
            detection_type: Type of objects to detect ("face", "person", etc.)
            max_frames: Maximum number of frames to analyze
            layout_mode: Layout mode for multiple faces
            
        Returns:
            Dictionary with analysis results
        """
        try:
            # Extract frames for analysis
            frames = self.extract_frames_for_detection(video_path, max_frames)
            if not frames:
                return {
                    "total_detections": 0,
                    "average_confidence": 0.0,
                    "average_center_x": 0,
                    "average_center_y": 0,
                    "max_faces_in_frame": 0,
                    "detected_faces": []
                }
            all_detections = []
            max_faces_in_frame = 0
            total_center_x = 0
            total_center_y = 0
            total_confidence = 0
            total_detections = 0
            max_face_width = 0
            max_face_height = 0
            # Analyze each frame
            for frame_idx, (timestamp, frame) in enumerate(frames):
                detections = self.detect_objects_in_frame(frame, detection_type)
                # Add frame_idx to each detection for grouping
                for d in detections:
                    d['frame_idx'] = frame_idx
                all_detections.extend(detections)
                # Track maximum faces in a single frame
                max_faces_in_frame = max(max_faces_in_frame, len(detections))
                # Calculate statistics
                for detection in detections:
                    total_center_x += detection['x'] + detection['width'] // 2
                    total_center_y += detection['y'] + detection['height'] // 2
                    total_confidence += detection['confidence']
                    total_detections += 1
                    # Track maximum face dimensions
                    max_face_width = max(max_face_width, detection['width'])
                    max_face_height = max(max_face_height, detection['height'])
            # Group similar faces across all frames (if any detections)
            if all_detections:
                # Only pass the frames (not timestamps)
                frame_imgs = [f[1] for f in frames]
                all_detections = self.group_similar_faces_batched(frame_imgs, all_detections)
            # Calculate averages
            average_center_x = total_center_x / total_detections if total_detections > 0 else 0
            average_center_y = total_center_y / total_detections if total_detections > 0 else 0
            average_confidence = total_confidence / total_detections if total_detections > 0 else 0
            logger.info(f"Object analysis complete: {total_detections} detections across {len(frames)} frames")
            logger.info(f"Max faces in frame: {max_faces_in_frame}, Average confidence: {average_confidence:.2f}")
            return {
                "total_detections": total_detections,
                "average_confidence": average_confidence,
                "average_center_x": average_center_x,
                "average_center_y": average_center_y,
                "max_faces_in_frame": max_faces_in_frame,
                "max_face_width": max_face_width,
                "max_face_height": max_face_height,
                "detected_faces": all_detections,
                "frames_analyzed": len(frames)
            }
        except Exception as e:
            logger.error(f"Error analyzing video objects: {e}")
            return {
                "total_detections": 0,
                "average_confidence": 0.0,
                "average_center_x": 0,
                "average_center_y": 0,
                "max_faces_in_frame": 0,
                "max_face_width": 0,
                "max_face_height": 0,
                "detected_faces": [],
                "frames_analyzed": 0
            }
    
    def get_most_central_face(self, faces: list, frame_width: int, frame_height: int) -> dict:
        """Select the face closest to the center of the frame."""
        center_x = frame_width // 2
        center_y = frame_height // 2
        def dist(face):
            fx = face['x'] + face['width'] // 2
            fy = face['y'] + face['height'] // 2
            return (fx - center_x) ** 2 + (fy - center_y) ** 2
        return min(faces, key=dist)

    def get_most_active_face(self, frame: Optional[np.ndarray], faces: list) -> dict:
        """Select the most active face using emotion/activity detection (DeepFace). If frame is None, fallback to most confident face."""
        if frame is None:
            return max(faces, key=lambda f: f.get('confidence', 0))
        active_faces = self.get_active_faces(frame, faces)
        if active_faces:
            # Return the most confident among active faces
            return max(active_faces, key=lambda f: f.get('confidence', 0))
        # Fallback to most confident face
        return max(faces, key=lambda f: f.get('confidence', 0))

    def calculate_optimal_crop_region(self, video_info: Dict, object_analysis: Dict, 
                                    target_aspect_ratio: str, layout_mode: str = "crop", frame: np.ndarray = np.array([]), use_active_face: bool = False) -> Dict:
        """Calculate optimal crop region to center detected objects
        Args:
            video_info: Video metadata
            object_analysis: Object detection analysis results
            target_aspect_ratio: Target aspect ratio
            layout_mode: Layout mode for multiple faces ("crop", "grid", "single", "merged", "centered")
            frame: Optional frame for active face detection
            use_active_face: If True, use emotion/activity to select main face
        Returns:
            Dictionary with crop parameters
        """
        try:
            video_width = video_info['width']
            video_height = video_info['height']
            # Parse target aspect ratio
            if target_aspect_ratio == "9:16":
                target_ratio = 9/16
            elif target_aspect_ratio == "16:9":
                target_ratio = 16/9
            elif target_aspect_ratio == "1:1":
                target_ratio = 1.0
            else:
                raise VideoProcessingError(f"Unsupported aspect ratio: {target_aspect_ratio}")
            if object_analysis['total_detections'] == 0:
                # No objects detected, use center crop
                return self._calculate_center_crop(video_width, video_height, target_ratio)
            max_faces = object_analysis['max_faces_in_frame']
            faces = object_analysis.get('detected_faces', [])
            # --- Enhanced face selection logic ---
            if layout_mode == "grid" and max_faces > 1:
                return self._calculate_grid_crop(video_width, video_height, target_ratio, object_analysis)
            elif layout_mode in ("single", "centered") or (layout_mode == "crop" and max_faces == 1):
                if faces:
                    if use_active_face and frame is not None:
                        best_face = self.get_most_active_face(frame, faces)
                    else:
                        # If frame is None or not using active face, fallback to most central face
                        best_face = self.get_most_central_face(faces, video_width, video_height)
                    return self._calculate_single_face_crop_from_detection(video_width, video_height, target_ratio, best_face)
                else:
                    return self._calculate_center_crop(video_width, video_height, target_ratio)
            elif layout_mode == "crop":
                if faces:
                    best_face = max(faces, key=lambda f: f['confidence'])
                    return self._calculate_single_face_crop_from_detection(video_width, video_height, target_ratio, best_face)
                else:
                    return self._calculate_center_crop(video_width, video_height, target_ratio)
            else:
                return self._calculate_merged_faces_crop(video_width, video_height, target_ratio, object_analysis)
        except Exception as e:
            logger.error(f"Error calculating optimal crop: {e}")
            return self._calculate_center_crop(video_info['width'], video_info['height'], target_ratio)
    
    def _calculate_single_face_crop_from_detection(self, video_width: int, video_height: int, target_ratio: float, face) -> Dict:
        """Calculate crop for a single detected face (DetectionResult). Always center the face, pad with black if needed. Crop size matches output size/aspect ratio."""
        # Determine output crop size based on target aspect ratio and video height/width
        if target_ratio < video_width / video_height:
            crop_width = int(video_height * target_ratio)
            crop_height = video_height
        else:
            crop_width = video_width
            crop_height = int(video_width / target_ratio)
        crop_width = (crop_width // 2) * 2
        crop_height = (crop_height // 2) * 2
        # Center of the detected face
        center_x = face['x'] + face['width'] // 2
        center_y = face['y'] + face['height'] // 2
        # Calculate crop offsets to center on the face
        x_offset = center_x - crop_width // 2
        y_offset = center_y - crop_height // 2
        # Clamp offsets so crop stays within video bounds
        x_offset = max(0, min(x_offset, video_width - crop_width))
        y_offset = max(0, min(y_offset, video_height - crop_height))
        # Calculate padding if crop goes out of bounds (should be rare with clamping)
        pad_left = max(0, -x_offset)
        pad_top = max(0, -y_offset)
        pad_right = max(0, x_offset + crop_width - video_width)
        pad_bottom = max(0, y_offset + crop_height - video_height)
        x_offset = max(0, x_offset)
        y_offset = max(0, y_offset)
        return {
            "x_offset": int(x_offset),
            "y_offset": int(y_offset),
            "width": crop_width,
            "height": crop_height,
            "target_aspect_ratio": f"{int(target_ratio * 100)}:{100}",
            "object_centered": True,
            "detection_confidence": face['confidence'],
            "layout_type": "single",
            "pad_left": int(pad_left),
            "pad_top": int(pad_top),
            "pad_right": int(pad_right),
            "pad_bottom": int(pad_bottom)
        }
    
    def _calculate_grid_crop(self, video_width: int, video_height: int, target_ratio: float, object_analysis: Dict) -> Dict:
        """Calculate crop for grid layout of multiple faces"""
        # For grid layout, crop to standard aspect ratio and center
        if target_ratio < video_width / video_height:
            crop_width = int(video_height * target_ratio)
            crop_height = video_height
            x_offset = (video_width - crop_width) // 2
            y_offset = 0
        else:
            crop_width = video_width
            crop_height = int(video_width / target_ratio)
            x_offset = 0
            y_offset = (video_height - crop_height) // 2
        crop_width = (crop_width // 2) * 2
        crop_height = (crop_height // 2) * 2
        self.logger.debug(f"Grid crop: x_offset={x_offset}, y_offset={y_offset}, width={crop_width}, height={crop_height}")
        return {
            "x_offset": x_offset,
            "y_offset": y_offset,
            "width": crop_width,
            "height": crop_height,
            "target_aspect_ratio": f"{int(target_ratio * 100)}:{100}",
            "object_centered": True,
            "detection_confidence": object_analysis['average_confidence'],
            "layout_type": "grid",
            "max_faces": object_analysis['max_faces_in_frame']
        }
    
    def _calculate_center_crop(self, video_width: int, video_height: int, target_ratio: float) -> Dict:
        """Calculate center crop when no objects are detected
        
        Args:
            video_width: Video width
            video_height: Video height
            target_ratio: Target aspect ratio
            
        Returns:
            Dictionary with center crop parameters
        """
        if target_ratio < video_width / video_height:
            # Target is taller, crop width
            crop_width = int(video_height * target_ratio)
            crop_height = video_height
            x_offset = (video_width - crop_width) // 2
            y_offset = 0
        else:
            # Target is wider, crop height
            crop_width = video_width
            crop_height = int(video_width / target_ratio)
            x_offset = 0
            y_offset = (video_height - crop_height) // 2
        
        return {
            "x_offset": x_offset,
            "y_offset": y_offset,
            "width": crop_width,
            "height": crop_height,
            "target_aspect_ratio": f"{int(target_ratio * 100)}:{100}",
            "object_centered": False,
            "detection_confidence": 0.0,
            "layout_type": "center"
        }
    
    def _calculate_merged_faces_crop(self, video_width: int, video_height: int, target_ratio: float, 
                                   object_analysis: Dict) -> Dict:
        """Calculate crop for multiple faces by merging their bounding boxes and centering the crop on all faces."""
        faces = object_analysis.get('detected_faces', [])
        if not faces:
            return self._calculate_center_crop(video_width, video_height, target_ratio)
        # Calculate merged bounding box that includes all faces
        min_x = video_width
        min_y = video_height
        max_x = 0
        max_y = 0
        for face in faces:
            expansion_factor = 0.5
            expanded_width = int(face['width'] * (1 + expansion_factor))
            expanded_height = int(face['height'] * (1 + expansion_factor))
            expanded_x = max(0, face['x'] - (expanded_width - face['width']) // 2)
            expanded_y = max(0, face['y'] - (expanded_height - face['height']) // 2)
            expanded_x2 = min(video_width, expanded_x + expanded_width)
            expanded_y2 = min(video_height, expanded_y + expanded_height)
            min_x = min(min_x, expanded_x)
            min_y = min(min_y, expanded_y)
            max_x = max(max_x, expanded_x2)
            max_y = max(max_y, expanded_y2)
        # Center of merged bounding box
        center_x = (min_x + max_x) // 2
        center_y = (min_y + max_y) // 2
        # Calculate crop dimensions to maintain target aspect ratio
        if target_ratio < video_width / video_height:
            crop_width = int(video_height * target_ratio)
            crop_height = video_height
        else:
            crop_width = video_width
            crop_height = int(video_width / target_ratio)
        crop_width = (crop_width // 2) * 2
        crop_height = (crop_height // 2) * 2
        # Center crop on merged bounding box center
        x_offset = center_x - crop_width // 2
        y_offset = center_y - crop_height // 2
        # Clamp offsets so crop stays within video bounds
        x_offset = max(0, min(x_offset, video_width - crop_width))
        y_offset = max(0, min(y_offset, video_height - crop_height))
        # If merged bounding box doesn't fit, expand crop to fit all faces
        if min_x < x_offset:
            x_offset = min_x
        if max_x > x_offset + crop_width:
            x_offset = max(0, max_x - crop_width)
        if min_y < y_offset:
            y_offset = min_y
        if max_y > y_offset + crop_height:
            y_offset = max(0, max_y - crop_height)
        return {
            "x_offset": int(x_offset),
            "y_offset": int(y_offset),
            "width": crop_width,
            "height": crop_height,
            "target_aspect_ratio": f"{int(target_ratio * 100)}:{100}",
            "object_centered": True,
            "detection_confidence": object_analysis['average_confidence'],
            "layout_type": "merged"
        }

    def has_stream(self, file_path, stream_type):
        # Use ffprobe to check for stream existence
        cmd = [
            'ffprobe', '-v', 'error', '-select_streams', stream_type,
            '-show_entries', 'stream=index', '-of', 'csv=p=0', file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return bool(result.stdout.strip())

    def combine_videos(self, temp_video_path: str, video_path: str, output_path: str):
        # Before combining:
        if not self.has_stream(temp_video_path, 'v:0'):
            logger.error(f"Temp video {temp_video_path} has no video stream!")
            # Fallback or raise error
        if not self.has_stream(video_path, 'a:0'):
            logger.warning(f"Original video {video_path} has no audio stream, will copy video only.")
            # Adjust command to not map audio

        # When building the FFmpeg command:
        cmd = [
            'ffmpeg', '-y',
            '-i', temp_video_path,
            '-i', video_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-map', '0:v:0?',
            '-map', '1:a:0?',
            output_path
        ]

        # Execute the command
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg command failed with output: {result.stdout}")
            raise VideoProcessingError(f"FFmpeg command failed: {result.stdout}")

        # logger.info("Videos combined successfully")

    def get_active_faces(self, frame: Optional[np.ndarray], faces: list) -> list:
        """
        Determine the most 'active' faces in the frame using emotion/activity detection.
        Args:
            frame: Input frame as numpy array or None
            faces: List of detected face bounding boxes
        Returns:
            List of active face dicts (could be one or more)
        """
        if frame is None:
            return faces
        try:
            from deepface import DeepFace
            active_faces = []
            for face in faces:
                x, y, w, h = face['x'], face['y'], face['width'], face['height']
                face_img = frame[y:y+h, x:x+w]
                # DeepFace expects RGB
                import cv2
                face_img_rgb = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
                # Analyze emotion (can be slow, consider batching or sampling)
                result = DeepFace.analyze(face_img_rgb, actions=['emotion'], enforce_detection=False)  # type: ignore
                dominant_emotion = result['dominant_emotion']  # type: ignore
                face['emotion'] = dominant_emotion  # type: ignore
                face['emotion_score'] = result['emotion'][dominant_emotion]  # type: ignore
                # Mark as active if emotion is strong (e.g., happy, surprised, angry, etc.)
                if face['emotion_score'] > 0.5:
                    active_faces.append(face)
            # If no strong emotion, fallback to all faces
            if not active_faces:
                return faces
            return active_faces
        except ImportError:
            self.logger.warning('DeepFace not installed, skipping emotion detection. Returning all faces.')
            return faces
        except Exception as e:
            self.logger.error(f'Error in emotion/activity detection: {e}')
            return faces

    def analyze_video_scenes_with_dynamic_layout(self, video_path: str, target_aspect_ratio: str = "9:16", face_group_threshold: float = 0.5) -> List[Dict]:
        """
        Analyze video by scenes and determine dynamic layout (single/grid) for each scene.
        Args:
            video_path: Path to video file
            target_aspect_ratio: Target aspect ratio for cropping (e.g., "9:16")
            face_group_threshold: Threshold for grouping similar faces
        Returns:
            List of dicts: [{
                'scene_start_frame': int,
                'scene_frame_idx': int,
                'layout_type': str,  # 'single' or 'grid'
                'unique_face_count': int,
                'crop_info': dict,   # crop parameters for this scene
                'faces': List[Dict], # detected faces with face_id
            }, ...]
        """
        from app.services.content_analyzer import SmartFrameExtractor
        scene_extractor = SmartFrameExtractor()
        scene_frames = scene_extractor.detect_scene_changes(video_path)
        results = []
        video_info = self._get_video_info(video_path)
        for scene in scene_frames:
            frame_idx, frame, _ = scene
            # Detect faces in this scene frame
            faces = self.detect_faces(frame)
            # Group similar faces (if more than 1 face)
            if faces:
                faces = [dict(f) for f in faces]  # ensure mutable
                for f in faces:
                    f['frame_idx'] = 0  # only one frame here
                faces = self.group_similar_faces_batched([frame], faces, threshold=face_group_threshold)
                unique_face_ids = set(f['face_id'] for f in faces if 'face_id' in f and f['face_id'] != -1)
                unique_face_count = len(unique_face_ids)
            else:
                unique_face_count = 0
            # Decide layout
            if unique_face_count <= 1:
                layout_type = 'single'
                crop_info = self._calculate_single_face_crop_from_detection(
                    video_info['width'], video_info['height'],
                    self._parse_aspect_ratio(target_aspect_ratio),
                    faces[0] if faces else {'x': video_info['width']//4, 'y': video_info['height']//4, 'width': video_info['width']//2, 'height': video_info['height']//2, 'confidence': 0.0}
                )
            else:
                layout_type = 'grid'
                # For grid, use all faces in this scene
                crop_info = self._calculate_grid_crop(
                    video_info['width'], video_info['height'],
                    self._parse_aspect_ratio(target_aspect_ratio),
                    {'average_confidence': sum(f['confidence'] for f in faces)/len(faces) if faces else 0.0,
                     'max_faces_in_frame': unique_face_count}
                )
            results.append({
                'scene_start_frame': frame_idx,
                'scene_frame_idx': frame_idx,
                'layout_type': layout_type,
                'unique_face_count': unique_face_count,
                'crop_info': crop_info,
                'faces': faces,
            })
        return results

    def _get_video_info(self, video_path: str) -> Dict:
        """Get video width and height."""
        cap = cv2.VideoCapture(video_path)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return {'width': width, 'height': height}

    def _parse_aspect_ratio(self, aspect: str) -> float:
        """Parse aspect ratio string like '9:16' to float."""
        if aspect == "9:16":
            return 9/16
        elif aspect == "16:9":
            return 16/9
        elif aspect == "1:1":
            return 1.0
        else:
            try:
                w, h = aspect.split(":")
                return float(w)/float(h)
            except Exception:
                return 9/16 