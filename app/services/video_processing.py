import os
import subprocess
import json
import logging
from typing import Dict, Optional
from datetime import datetime

from fastapi import UploadFile

from app.services.base import BaseService
from app.config.settings import Settings
from app.core.exceptions import VideoProcessingError, StorageError
from app.services.object_detection import ObjectDetectionService

logger = logging.getLogger(__name__)

class VideoProcessingService(BaseService):
    """Service for handling video processing operations"""
    
    def __init__(self, settings: Settings):
        """Initialize video processing service
        
        Args:
            settings: Application settings
        """
        super().__init__(settings)
        
        # Initialize object detection service
        self.object_detection_service = ObjectDetectionService(settings)
    
    async def save_upload_file(self, upload_file: UploadFile) -> str:
        """Save uploaded file to uploads directory and never delete it
        Args:
            upload_file: FastAPI UploadFile object
        Returns:
            Path to saved file in uploads dir
        Raises:
            StorageError: If file save fails
        """
        try:
            filename = getattr(upload_file, 'filename', 'video.mp4')
            file_extension = os.path.splitext(filename or "video.mp4")[1]
            if file_extension.lower() not in self.settings.supported_video_formats:
                raise StorageError(f"Unsupported video format: {file_extension}")
            timestamp = int(datetime.now().timestamp())
            # Always save to uploads dir
            upload_file_path = os.path.join(self.settings.upload_dir, f"upload_{timestamp}{file_extension}")
            content = await upload_file.read()
            if len(content) > self.settings.max_file_size:
                raise StorageError(f"File size ({self.format_file_size(len(content))}) exceeds maximum allowed size ({self.format_file_size(self.settings.max_file_size)})")
            with open(upload_file_path, 'wb') as out_file:
                out_file.write(content)
            self.logger.info(f"Uploaded video saved to: {upload_file_path}, size: {self.format_file_size(len(content))}")
            return upload_file_path
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
    
    def calculate_crop_filter(self, video_info: Dict, target_aspect_ratio: str, 
                            crop_params: Optional[Dict] = None, face_layout_mode: str = "crop",
                            grid_background_color: Optional[str] = None) -> str:
        """Calculate FFmpeg filter for aspect ratio conversion with smart face cropping
        
        Args:
            video_info: Video metadata
            target_aspect_ratio: Target aspect ratio (e.g., "9:16", "16:9", "1:1")
            crop_params: Optional crop parameters from object detection
            face_layout_mode: Face layout mode - "crop" (crop around faces), "grid" (grid layout)
            
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
        
        # Use smart cropping if crop parameters are provided
        if crop_params and crop_params.get('object_centered', False):
            if face_layout_mode == "grid" and crop_params.get('layout_type') == 'grid':
                # Use grid layout for multiple faces
                return self._create_grid_layout_filter(crop_params, target_width, target_height, grid_background_color=grid_background_color or 'black')
            else:
                # Use face cropping mode - crop around detected faces
                return self._create_face_crop_filter(crop_params, target_width, target_height, width, height)
        else:
            # Traditional center crop
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
    
    def _create_face_crop_filter(self, crop_params: Dict, target_width: int, target_height: int, 
                                video_width: int, video_height: int) -> str:
        """Create FFmpeg filter for cropping around detected faces, with padding if needed."""
        x_offset = crop_params['x_offset']
        y_offset = crop_params['y_offset']
        crop_width = crop_params['width']
        crop_height = crop_params['height']
        pad_left = crop_params.get('pad_left', 0)
        pad_top = crop_params.get('pad_top', 0)
        pad_right = crop_params.get('pad_right', 0)
        pad_bottom = crop_params.get('pad_bottom', 0)
        # Ensure crop region is within video bounds
        x_offset = max(0, min(x_offset, video_width - crop_width))
        y_offset = max(0, min(y_offset, video_height - crop_height))
        crop_width = (crop_width // 2) * 2
        crop_height = (crop_height // 2) * 2
        crop_filter = f"crop={crop_width}:{crop_height}:{x_offset}:{y_offset}"
        pad_filter = ""
        if pad_left > 0 or pad_top > 0 or pad_right > 0 or pad_bottom > 0:
            pad_w = crop_width + pad_left + pad_right
            pad_h = crop_height + pad_top + pad_bottom
            pad_filter = f",pad={pad_w}:{pad_h}:{pad_left}:{pad_top}:color=black"
        scale_filter = f"scale={target_width}:{target_height}"
        return f"{crop_filter}{pad_filter},{scale_filter}"
    
    def _create_grid_layout_filter(self, crop_params: Dict, target_width: int, target_height: int, grid_background_color: Optional[str] = None) -> str:
        # Ensure all grid cells are the same size and each face is centered in its cell
        # Standardize output resolution and enforce WhatsApp compatibility
        max_faces = crop_params.get('max_faces', 4)
        
        # For a more sophisticated implementation, we would:
        # 1. Detect faces in each frame
        # 2. Calculate optimal grid layout based on face positions
        # 3. Create dynamic crop regions for each face
        # 4. Composite them into a grid
        
        # For now, we'll create a simple grid layout that works well for most cases
        # This creates a video call style layout with proper spacing
        
        if max_faces <= 1:
            # Single face - use center crop with padding
            return f"crop=iw/2:ih/2:iw/4:ih/4,scale={target_width}:{target_height}"
        
        elif max_faces == 2:
            padding = 20
            cell_width = (target_width - 3 * padding) // 2
            cell_height = target_height - 2 * padding
            # Ensure even cell sizes
            cell_width = (cell_width // 2) * 2
            cell_height = (cell_height // 2) * 2
            return (
                f"split=2[face1][face2];"
                f"[face1]crop=iw/2:ih:0:0,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled1];"
                f"[face2]crop=iw/2:ih:iw/2:0,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled2];"
                f"[scaled1][scaled2]hstack=inputs=2:shortest=1,"
                f"pad={target_width}:{target_height}:{padding}:{padding}:color={grid_background_color or 'black'}"
            )
        
        elif max_faces == 3:
            padding = 15
            # Ensure all cells are the same size for all faces
            cell_width = (target_width - 3 * padding) // 2
            cell_height = (target_height - 3 * padding) // 2
            # Use the same cell size for all faces
            cell_width = (cell_width // 2) * 2
            cell_height = (cell_height // 2) * 2
            return (
                f"split=3[face1][face2][face3];"
                f"[face1]crop=iw/2:ih/2:0:0,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled1];"
                f"[face2]crop=iw/2:ih/2:iw/2:0,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled2];"
                f"[face3]crop=iw/2:ih/2:0:ih/2,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled3];"
                f"[scaled1][scaled2]hstack=inputs=2:shortest=1[toprow];"
                f"[toprow][scaled3]vstack=inputs=2:shortest=1,"
                f"pad={target_width}:{target_height}:{padding}:{padding}:color={grid_background_color or 'black'}"
            )
        
        elif max_faces == 4:
            padding = 10
            cell_width = (target_width - 3 * padding) // 2
            cell_height = (target_height - 3 * padding) // 2
            # Ensure even cell sizes
            cell_width = (cell_width // 2) * 2
            cell_height = (cell_height // 2) * 2
            return (
                f"split=4[face1][face2][face3][face4];"
                f"[face1]crop=iw/2:ih/2:0:0,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled1];"
                f"[face2]crop=iw/2:ih/2:iw/2:0,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled2];"
                f"[face3]crop=iw/2:ih/2:0:ih/2,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled3];"
                f"[face4]crop=iw/2:ih/2:iw/2:ih/2,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled4];"
                f"[scaled1][scaled2]hstack=inputs=2:shortest=1[toprow];"
                f"[scaled3][scaled4]hstack=inputs=2:shortest=1[bottomrow];"
                f"[toprow][bottomrow]vstack=inputs=2:shortest=1,"
                f"pad={target_width}:{target_height}:{padding}:{padding}:color={grid_background_color or 'black'}"
            )
        
        elif max_faces <= 6:
            # 5-6 faces - 3x2 grid
            padding = 8
            cell_width = (target_width - 4 * padding) // 3
            cell_height = (target_height - 3 * padding) // 2
            
            # Create 6 cells (some may be empty for 5 faces)
            filter_parts = []
            for i in range(6):
                row = i // 3
                col = i % 3
                filter_parts.append(f"[face{i+1}]crop=iw/3:ih/2:{col}*iw/3:{row}*ih/2,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled{i+1}]")
            
            # Create rows
            row1 = f"[scaled1][scaled2][scaled3]hstack=inputs=3:shortest=1[toprow]"
            row2 = f"[scaled4][scaled5][scaled6]hstack=inputs=3:shortest=1[bottomrow]"
            
            return (
                f"split=6[face1][face2][face3][face4][face5][face6];"
                f"{','.join(filter_parts)};"
                f"{row1};{row2};"
                f"[toprow][bottomrow]vstack=inputs=2:shortest=1,"
                f"pad={target_width}:{target_height}:{padding}:{padding}:color={grid_background_color or 'black'}"
            )
        
        elif max_faces <= 9:
            # 7-9 faces - 3x3 grid
            padding = 5
            cell_width = (target_width - 4 * padding) // 3
            cell_height = (target_height - 4 * padding) // 3
            
            # Create 9 cells
            filter_parts = []
            for i in range(9):
                row = i // 3
                col = i % 3
                filter_parts.append(f"[face{i+1}]crop=iw/3:ih/3:{col}*iw/3:{row}*ih/3,scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled{i+1}]")
            
            # Create rows
            rows = []
            for row in range(3):
                start_idx = row * 3 + 1
                end_idx = start_idx + 2
                row_cells = [f"[scaled{i}]" for i in range(start_idx, end_idx + 1)]
                rows.append(f"{''.join(row_cells)}hstack=inputs=3:shortest=1[row{row}]")
            
            return (
                f"split=9[face1][face2][face3][face4][face5][face6][face7][face8][face9];"
                f"{','.join(filter_parts)};"
                f"{';'.join(rows)};"
                f"[row0][row1][row2]vstack=inputs=3:shortest=1,"
                f"pad={target_width}:{target_height}:{padding}:{padding}:color={grid_background_color or 'black'}"
            )
        
        else:
            # More than 9 faces - use a larger grid
            grid_size = int(max_faces ** 0.5) + 1
            padding = max(3, 20 // grid_size)
            cell_width = (target_width - (grid_size + 1) * padding) // grid_size
            cell_height = (target_height - (grid_size + 1) * padding) // grid_size
            
            # Limit to grid_size * grid_size faces
            max_cells = grid_size * grid_size
            
            # Create cells
            filter_parts = []
            for i in range(max_cells):
                row = i // grid_size
                col = i % grid_size
                filter_parts.append(f"[face{i+1}]crop=iw/{grid_size}:ih/{grid_size}:{col}*iw/{grid_size}:{row}*ih/{grid_size},scale={cell_width}:{cell_height}:force_original_aspect_ratio=increase,crop={cell_width}:{cell_height}[scaled{i+1}]")
            
            # Create rows
            rows = []
            for row in range(grid_size):
                start_idx = row * grid_size + 1
                end_idx = start_idx + grid_size - 1
                row_cells = [f"[scaled{i}]" for i in range(start_idx, end_idx + 1)]
                rows.append(f"{''.join(row_cells)}hstack=inputs={grid_size}:shortest=1[row{row}]")
            
            # Create vstack inputs
            vstack_inputs = [f"[row{i}]" for i in range(grid_size)]
            
            return (
                f"split={max_cells}{''.join(f'[face{i+1}]' for i in range(max_cells))};"
                f"{','.join(filter_parts)};"
                f"{';'.join(rows)};"
                f"{''.join(vstack_inputs)}vstack=inputs={grid_size}:shortest=1,"
                f"pad={target_width}:{target_height}:{padding}:{padding}:color={grid_background_color or 'black'}"
            )
    
    def create_face_grid_video(self, video_path: str, output_path: str, object_detection_service, target_width: int = 1080, target_height: int = 1920, grid_background_color: str = 'black') -> str:
        """
        Scene-based multilayout: For each scene, use the first frame to detect unique persons and their face positions.
        Cluster faces by proximity; each cluster becomes a cell. For each cell, crop a region that includes all faces in the cluster, center the crop on the cluster center, and fit the crop to the cell. No letterboxing.
        """
        import cv2
        import numpy as np
        from math import ceil
        from sklearn.cluster import DBSCAN
        # 1. Get scene layouts
        scene_layouts = object_detection_service.analyze_video_scenes_with_dynamic_layout(
            video_path, target_aspect_ratio=f"{target_width}:{target_height}")
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fourcc = cv2.VideoWriter_fourcc(*'m', 'p', '4', 'v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (target_width, target_height))
        # Build a map of scene start frame -> layout info
        scene_map = {scene['scene_start_frame']: scene for scene in scene_layouts}
        scene_starts = sorted(scene_map.keys())
        current_scene_idx = 0
        current_scene = scene_map[scene_starts[0]] if scene_starts else None
        next_scene_start = scene_starts[1] if len(scene_starts) > 1 else frame_count
        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            # Switch scene if needed
            if frame_idx >= next_scene_start and current_scene_idx + 1 < len(scene_starts):
                current_scene_idx += 1
                current_scene = scene_map[scene_starts[current_scene_idx]]
                next_scene_start = scene_starts[current_scene_idx + 1] if current_scene_idx + 1 < len(scene_starts) else frame_count
            video_h, video_w = frame.shape[:2]
            if current_scene is None:
                # Fallback: center crop
                aspect = target_width / target_height
                if aspect > video_w / video_h:
                    crop_w = video_w
                    crop_h = int(video_w / aspect)
                else:
                    crop_h = video_h
                    crop_w = int(video_h * aspect)
                x0 = (video_w - crop_w) // 2
                y0 = (video_h - crop_h) // 2
                crop = frame[y0:y0+crop_h, x0:x0+crop_w]
                crop = cv2.resize(crop, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
                out.write(crop)
                frame_idx += 1
                continue
            faces = current_scene['faces']
            n = len(faces)
            # Cluster faces by proximity (if more than 1)
            if n == 0:
                # No faces: center crop
                aspect = target_width / target_height
                if aspect > video_w / video_h:
                    crop_w = video_w
                    crop_h = int(video_w / aspect)
                else:
                    crop_h = video_h
                    crop_w = int(video_h * aspect)
                x0 = (video_w - crop_w) // 2
                y0 = (video_h - crop_h) // 2
                crop = frame[y0:y0+crop_h, x0:x0+crop_w]
                crop = cv2.resize(crop, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
                out.write(crop)
            elif n == 1:
                # One person: center crop on face, but use full-body crop (anchor height)
                f = faces[0]
                cx = f['x'] + f['width'] // 2
                cy = f['y'] + f['height'] // 2
                aspect = target_width / target_height
                crop_h = video_h
                crop_w = int(crop_h * aspect)
                if crop_w > video_w:
                    crop_w = video_w
                    crop_h = int(crop_w / aspect)
                crop_x = max(0, min(video_w - crop_w, cx - crop_w // 2))
                crop_y = max(0, min(video_h - crop_h, cy - crop_h // 2))
                crop = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
                crop = cv2.resize(crop, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
                out.write(crop)
            else:
                # Multi-person: cluster faces by proximity
                # Prepare data for clustering
                X = np.array([[f['x'] + f['width'] // 2, f['y'] + f['height'] // 2] for f in faces])
                # Use a reasonable distance threshold (e.g., 1/5 of video width)
                eps = max(40, video_w // 5)
                db = DBSCAN(eps=eps, min_samples=1).fit(X)
                labels = db.labels_
                clusters = {}
                for idx, label in enumerate(labels):
                    clusters.setdefault(label, []).append(faces[idx])
                cluster_list = list(clusters.values())
                n_clusters = len(cluster_list)
                # Layout planning: same as before, but use n_clusters
                aspect = target_width / target_height
                if n_clusters == 2:
                    if aspect < 1:
                        cell_w = target_width // 2
                        cell_h = target_height
                        layout = [(0, 0, cell_w, cell_h), (cell_w, 0, cell_w, cell_h)]
                    else:
                        cell_w = target_width
                        cell_h = target_height // 2
                        layout = [(0, 0, cell_w, cell_h), (0, cell_h, cell_w, cell_h)]
                elif n_clusters == 3:
                    if aspect < 1:
                        cell_w = target_width // 2
                        cell_h = target_height // 2
                        layout = [
                            (0, 0, target_width, cell_h),
                            (0, cell_h, cell_w, cell_h),
                            (cell_w, cell_h, cell_w, cell_h)
                        ]
                    else:
                        cell_w = target_width // 3
                        cell_h = target_height
                        layout = [
                            (0, 0, cell_w, cell_h),
                            (cell_w, 0, cell_w, cell_h),
                            (2*cell_w, 0, cell_w, cell_h)
                        ]
                else:
                    grid_cols = ceil(np.sqrt(n_clusters))
                    grid_rows = ceil(n_clusters / grid_cols)
                    cell_w = target_width // grid_cols
                    cell_h = target_height // grid_rows
                    layout = []
                    for i in range(n_clusters):
                        row = i // grid_cols
                        col = i % grid_cols
                        layout.append((col*cell_w, row*cell_h, cell_w, cell_h))
                # For each cluster, crop from original frame and place in layout
                composed = np.zeros((target_height, target_width, 3), dtype=np.uint8)
                for i, cluster in enumerate(cluster_list):
                    if i >= len(layout):
                        break
                    lx, ly, lw, lh = layout[i]
                    # Compute bounding box for all faces in cluster
                    xs = [f['x'] + f['width'] // 2 for f in cluster]
                    ys = [f['y'] + f['height'] // 2 for f in cluster]
                    cx = int(np.mean(xs))
                    cy = int(np.mean(ys))
                    # Crop region centered on cluster center, fit to cell aspect
                    if lw / lh < video_w / video_h:
                        crop_h = video_h
                        crop_w = int(crop_h * (lw / lh))
                        if crop_w > video_w:
                            crop_w = video_w
                            crop_h = int(crop_w / (lw / lh))
                    else:
                        crop_w = video_w
                        crop_h = int(crop_w / (lw / lh))
                        if crop_h > video_h:
                            crop_h = video_h
                            crop_w = int(crop_h * (lw / lh))
                    crop_x = max(0, min(video_w - crop_w, cx - crop_w // 2))
                    crop_y = max(0, min(video_h - crop_h, cy - crop_h // 2))
                    crop = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
                    crop = cv2.resize(crop, (lw, lh), interpolation=cv2.INTER_LINEAR)
                    composed[ly:ly+lh, lx:lx+lw] = crop
                out.write(composed)
            frame_idx += 1
        cap.release()
        out.release()
        # Mux original audio back in
        import subprocess, os
        temp_output = output_path.replace('.mp4', '_withaudio.mp4')
        cmd = [
            'ffmpeg', '-y',
            '-i', output_path,
            '-i', video_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-shortest', temp_output
        ]
        subprocess.run(cmd, capture_output=True)
        os.replace(temp_output, output_path)
        return output_path
    
    def create_video_clip(self, video_path: str, start_time: float, end_time: float, 
                         output_path: str, aspect_ratio: str = "9:16",
                         enable_object_detection: bool = True,
                         object_detection_type: str = "face",
                         max_detection_frames: int = 10,
                         grid_background_color: str = 'black') -> str:
        logger.info(f"[DEBUG] Entered create_video_clip with video_path={video_path}, start_time={start_time}, end_time={end_time}, output_path={output_path}, aspect_ratio={aspect_ratio}, enable_object_detection={enable_object_detection}, object_detection_type={object_detection_type}, max_detection_frames={max_detection_frames}, grid_background_color={grid_background_color}")
        try:
            clip_duration = end_time - start_time
            if clip_duration < self.settings.min_clip_duration:
                logger.error(f"[DEBUG] Early exit: Clip duration ({clip_duration:.1f}s) is below minimum ({self.settings.min_clip_duration}s)")
                raise VideoProcessingError(f"Clip duration ({clip_duration:.1f}s) is below minimum ({self.settings.min_clip_duration}s)")
            if clip_duration > self.settings.max_clip_duration:
                logger.error(f"[DEBUG] Early exit: Clip duration ({clip_duration:.1f}s) exceeds maximum ({self.settings.max_clip_duration}s)")
                raise VideoProcessingError(f"Clip duration ({clip_duration:.1f}s) exceeds maximum ({self.settings.max_clip_duration}s)")
            video_path_ffmpeg = os.path.abspath(video_path).replace("\\", "/")
            output_path_ffmpeg = os.path.abspath(output_path).replace("\\", "/")
            video_info = self.get_video_info(video_path)
            if not os.path.exists(video_path):
                logger.error(f"[DEBUG] Early exit: Input video file does not exist: {video_path}")
                raise VideoProcessingError(f"Input video file does not exist: {video_path}")
            temp_clip_path = self._create_temp_clip_for_detection(video_path, start_time, end_time, with_audio=True)
            try:
                detection_video_info = self.get_video_info(temp_clip_path)
                # Use new scene-based, stable, full-body multilayout
                grid_output_path = output_path.replace('.mp4', '_grid.mp4')
                if aspect_ratio == "16:9":
                    target_width, target_height = 1920, 1080
                elif aspect_ratio == "1:1":
                    target_width, target_height = 1080, 1080
                else:
                    target_width, target_height = 1080, 1920
                self.create_face_grid_video(
                    temp_clip_path, grid_output_path, self.object_detection_service,
                    target_width=target_width, target_height=target_height,
                    grid_background_color=grid_background_color
                )
                self._cleanup_temp_file(temp_clip_path)
                return grid_output_path
            finally:
                if os.path.exists(temp_clip_path):
                    self._cleanup_temp_file(temp_clip_path)
        except Exception as e:
            logger.error(f"Error creating video clip: {e}")
            raise
    
    def _create_temp_clip_for_detection(self, video_path: str, start_time: float, end_time: float, with_audio: bool = False) -> str:
        """Create a temporary clip for object detection analysis (original ratio, optionally with audio)"""
        try:
            # Create temporary file path
            timestamp = int(datetime.now().timestamp())
            suffix = "audio" if with_audio else ""
            temp_clip_path = os.path.join(self.settings.temp_dir, f"detection_clip_{timestamp}{'_' + suffix if suffix else ''}.mp4")
            # Build FFmpeg command for temporary clip (no crop/scale, keep original ratio)
            cmd = [
                'ffmpeg', '-y', '-i', video_path,
                '-ss', str(start_time), '-to', str(end_time),
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
            ]
            if not with_audio:
                cmd.append('-an')  # No audio for detection
            temp_clip_path = os.path.abspath(temp_clip_path)
            cmd.append(temp_clip_path)
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if not os.path.exists(temp_clip_path):
                raise VideoProcessingError("Temporary detection clip was not created")
            return temp_clip_path
        except Exception as e:
            logger.error(f"Error creating temporary detection clip: {e}")
            raise VideoProcessingError(f"Failed to create temporary detection clip: {e}")
    
    def _cleanup_temp_file(self, temp_path: str):
        """Clean up temporary file with retry logic for Windows"""
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as e:
                logger.warning(f"Could not immediately remove temp file {temp_path}: {e}")
                # On Windows, files might be locked briefly, try again after a short delay
                import time
                time.sleep(0.1)
                try:
                    os.remove(temp_path)
                except OSError:
                    logger.warning(f"Failed to remove temp file {temp_path}, will be cleaned up later")
    
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
            logger.error(f"Video validation failed: {e}")
            return False
    
    def cleanup_temp_file(self, file_path: str) -> None:
        """Clean up a temporary file
        
        Args:
            file_path: Path to file to delete
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up temp file: {file_path}")
        except OSError as e:
            logger.warning(f"Could not clean up temp file {file_path}: {e}")
    
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
    
    def process_dynamic_speaker_highlight(self, video_path: str, output_path: str, aspect_ratio: str = "9:16") -> str:
        """
        Process video to dynamically highlight active speakers in a grid layout.
        Args:
            video_path: Path to input video
            output_path: Path to output video
            aspect_ratio: Target aspect ratio (e.g., "9:16", "16:9", "1:1")
        Returns:
            Path to processed video
        Raises:
            VideoProcessingError: If processing fails or output is not created
        """
        try:
            video_info = self.get_video_info(video_path)
            # Simulate a grid layout for now (use 2x2 grid as placeholder)
            crop_params = {'max_faces': 4, 'layout_type': 'grid', 'object_centered': False}
            video_filter = self.calculate_crop_filter(video_info, aspect_ratio, crop_params, face_layout_mode="grid")
            video_path_ffmpeg = os.path.abspath(video_path).replace("\\", "/")
            output_path_ffmpeg = os.path.abspath(output_path).replace("\\", "/")
            cmd = [
                'ffmpeg', '-y', '-i', video_path_ffmpeg,
                '-vf', video_filter,
                '-c:v', 'libx264',
                '-preset', self.settings.ffmpeg_preset,
                '-crf', str(self.settings.video_quality_crf),
                '-profile:v', 'main',
                '-level', '4.0',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart'
            ]
            if video_info.get('has_audio', False):
                cmd.extend([
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-ar', '44100',
                    '-ac', '2'
                ])
            else:
                cmd.extend(['-an'])
            cmd.append(output_path_ffmpeg)
            # self.logger.info(f"[DynamicSpeaker] FFmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            output_path_check = output_path_ffmpeg.replace("/", os.sep)
            if not os.path.exists(output_path_check):
                # self.logger.error(f"[DynamicSpeaker] FFmpeg stderr: {result.stderr}")
                raise VideoProcessingError(f"Dynamic speaker highlight failed: {result.stderr}")
            # self.logger.info(f"[DynamicSpeaker] Output created: {output_path_ffmpeg}")
            return output_path_ffmpeg
        except Exception as e:
            # self.logger.error(f"[DynamicSpeaker] Error: {e}")
            raise VideoProcessingError(f"Failed to process dynamic speaker highlight: {e}")
    
    def process_single_speaker_highlight(self, video_path: str, output_path: str, aspect_ratio: str = "9:16") -> str:
        """
        Process video to highlight individual speakers by cropping and centering on them.
        This creates a more natural video where each speaker is shown individually.

        Args:
            video_path: Path to input video
            output_path: Path to output video
            aspect_ratio: Target aspect ratio (e.g., "9:16", "16:9", "1:1")
        Returns:
            Path to processed video
        Raises:
            VideoProcessingError: If processing fails or output is not created
        """
        try:
            video_info = self.get_video_info(video_path)
            # Use the same crop filter logic as create_video_clip, but for the whole video
            video_filter = self.calculate_crop_filter(video_info, aspect_ratio)
            video_path_ffmpeg = os.path.abspath(video_path).replace("\\", "/")
            output_path_ffmpeg = os.path.abspath(output_path).replace("\\", "/")
            cmd = [
                'ffmpeg', '-y', '-i', video_path_ffmpeg,
                '-vf', video_filter,
                '-c:v', 'libx264',
                '-preset', self.settings.ffmpeg_preset,
                '-crf', str(self.settings.video_quality_crf),
                '-profile:v', 'main',
                '-level', '4.0',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart'
            ]
            if video_info.get('has_audio', False):
                cmd.extend([
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-ar', '44100',
                    '-ac', '2'
                ])
            else:
                cmd.extend(['-an'])
            cmd.append(output_path_ffmpeg)
            # self.logger.info(f"[SingleSpeaker] FFmpeg command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            output_path_check = output_path_ffmpeg.replace("/", os.sep)
            if not os.path.exists(output_path_check):
                # self.logger.error(f"[SingleSpeaker] FFmpeg stderr: {result.stderr}")
                raise VideoProcessingError(f"Single speaker highlight failed: {result.stderr}")
            # self.logger.info(f"[SingleSpeaker] Output created: {output_path_ffmpeg}")
            return output_path_ffmpeg
        except Exception as e:
            # self.logger.error(f"[SingleSpeaker] Error: {e}")
            raise VideoProcessingError(f"Failed to process single speaker highlight: {e}")