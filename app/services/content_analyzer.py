import os
import tempfile
import shutil
import subprocess
import base64
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
from openai import OpenAI

from app.services.base import BaseService
from app.config.settings import Settings
from app.core.exceptions import ContentAnalysisError, DownloadError, ConfigurationError


class SmartFrameExtractor:
    """Utility class for intelligent video frame extraction"""
    
    def __init__(self):
        self.orb = cv2.ORB_create(nfeatures=500)
    
    def calculate_frame_importance(self, frame) -> float:
        """Calculate importance score for a video frame"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges) / (edges.shape[0] * edges.shape[1])
        
        keypoints = self.orb.detect(gray, None)
        feature_count = len(keypoints)
        
        brightness_var = np.var(gray)
        
        importance_score = (
            edge_density * 0.4 + 
            (feature_count / 1000) * 0.4 + 
            (brightness_var / 10000) * 0.2
        )
        return importance_score
    
    def detect_scene_changes(self, video_path: str, threshold: float = 0.3) -> List[Tuple[int, np.ndarray, float]]:
        """Detect scene changes in video"""
        cap = cv2.VideoCapture(video_path)
        scene_changes = []
        prev_frame = None
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            if prev_frame is not None:
                hist1 = cv2.calcHist([prev_frame], [0], None, [256], [0, 256])
                hist2 = cv2.calcHist([gray], [0], None, [256], [0, 256])
                diff = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
                
                if diff < (1 - threshold):
                    importance = self.calculate_frame_importance(frame)
                    scene_changes.append((frame_count, frame, importance))
            
            prev_frame = gray
            frame_count += 1
        
        cap.release()
        return scene_changes
    
    def extract_smart_keyframes(self, video_path: str, max_frames: int = 20, method: str = 'hybrid') -> List[Tuple[int, np.ndarray, float]]:
        """Extract keyframes using smart algorithms"""
        if method == 'scene_change':
            keyframes = self.detect_scene_changes(video_path)
            keyframes.sort(key=lambda x: x[2], reverse=True)
            return keyframes[:max_frames]
        
        elif method == 'uniform_smart':
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_indices = np.linspace(0, total_frames-1, max_frames*2, dtype=int)
            
            candidates = []
            for idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    importance = self.calculate_frame_importance(frame)
                    candidates.append((idx, frame, importance))
            
            cap.release()
            candidates.sort(key=lambda x: x[2], reverse=True)
            return candidates[:max_frames]
        
        elif method == 'hybrid':
            scene_frames = self.detect_scene_changes(video_path, threshold=0.2)
            
            if len(scene_frames) < max_frames:
                cap = cv2.VideoCapture(video_path)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                existing_indices = set([f[0] for f in scene_frames])
                remaining_slots = max_frames - len(scene_frames)
                
                if remaining_slots > 0:
                    all_indices = set(range(0, total_frames, max(1, total_frames // (remaining_slots * 2))))
                    new_indices = list(all_indices - existing_indices)[:remaining_slots]
                    
                    for idx in new_indices:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                        ret, frame = cap.read()
                        if ret:
                            importance = self.calculate_frame_importance(frame)
                            scene_frames.append((idx, frame, importance))
                
                cap.release()
            
            scene_frames.sort(key=lambda x: x[0])
            return scene_frames[:max_frames]
        
        else:
            raise ValueError(f"Unknown extraction method: {method}")


class ContentAnalyzerService(BaseService):
    """Service for content analysis including social media downloads and AI analysis"""
    
    def __init__(self, settings: Settings, openai_client: OpenAI):
        super().__init__(settings)
        self.client = openai_client
        self.frame_extractor = SmartFrameExtractor()
    
    def check_yt_dlp(self) -> bool:
        """Check if yt-dlp is available"""
        try:
            subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
    
    def detect_platform(self, url: str) -> str:
        """Detect social media platform from URL
        
        Args:
            url: Social media URL
            
        Returns:
            Platform name (tiktok, instagram, unknown)
        """
        url = url.lower()
        if 'tiktok.com' in url:
            return 'tiktok'
        elif 'instagram.com' in url:
            return 'instagram'
        else:
            return 'unknown'
    
    def extract_post_id_from_url(self, url: str, platform: str) -> Optional[str]:
        """Extract post ID from social media URL
        
        Args:
            url: Social media URL
            platform: Platform name
            
        Returns:
            Post ID if found
        """
        import re
        
        if platform == 'tiktok':
            match = re.search(r'/video/(\d+)', url)
            if match:
                return match.group(1)
        elif platform == 'instagram':
            match = re.search(r'/(?:p|reel|tv|reels)/([A-Za-z0-9_-]+)', url, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def download_social_media_video(self, url: str, download_dir: str) -> Tuple[Dict, Optional[str], str, str, str, Dict]:
        """Download video from social media URL
        
        Args:
            url: Social media URL
            download_dir: Directory to save downloads
            
        Returns:
            Tuple of (metadata, video_file_path, post_dir, platform, post_id, metrics)
        """
        if not self.check_yt_dlp():
            raise DownloadError('yt-dlp not found. Please install yt-dlp to download from social media.')
        
        platform = self.detect_platform(url)
        post_id = self.extract_post_id_from_url(url, platform) or 'unknown'
        post_dir = os.path.join(download_dir, f"{platform}_{post_id}")
        os.makedirs(post_dir, exist_ok=True)
        
        try:
            if platform == 'tiktok':
                return self._download_tiktok(url, post_dir, post_id)
            elif platform == 'instagram':
                return self._download_instagram(url, post_dir, post_id)
            else:
                raise DownloadError(f'Unsupported platform: {platform}')
                
        except Exception as e:
            self.logger.error(f"Error downloading from {platform}: {e}")
            raise DownloadError(f"Failed to download from {platform}: {e}")
    
    def _download_tiktok(self, url: str, post_dir: str, post_id: str) -> Tuple[Dict, Optional[str], str, str, str, Dict]:
        """Download TikTok video"""
        # Get metadata
        cmd = ['yt-dlp', '--dump-json', '--no-download', url]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        # Download video
        video_file = None
        output_template = os.path.abspath(os.path.join(post_dir, f"{post_id}.%(ext)s"))
        cmd_download = [
            'yt-dlp', '--output', output_template, '--no-playlist', 
            '--format', 'best[height<=720]/best', url
        ]
        subprocess.run(cmd_download, capture_output=True, text=True, check=True)
        
        # Find downloaded file
        for file in os.listdir(post_dir):
            if file.startswith(post_id) and file.endswith(('.mp4', '.mkv', '.webm')):
                video_file = os.path.join(post_dir, file)
                break
        
        # Create metrics
        metrics = {
            'platform': 'tiktok',
            'url': url,
            'post_id': post_id,
            'title': data.get('title', 'N/A'),
            'description': data.get('description', ''),
            'uploader': data.get('uploader', 'N/A'),
            'uploader_id': data.get('uploader_id', 'N/A'),
            'upload_date': data.get('upload_date', 'N/A'),
            'duration': data.get('duration', 'N/A'),
            'view_count': data.get('view_count', 'N/A'),
            'like_count': data.get('like_count', 'N/A'),
            'comment_count': data.get('comment_count', 'N/A'),
            'repost_count': data.get('repost_count', 'N/A'),
            'scraped_at': datetime.now().isoformat(),
            'storage_directory': post_dir,
        }
        
        if video_file:
            metrics['media_file'] = video_file
        
        self.save_metrics_to_json(metrics, post_dir, 'tiktok', post_id)
        return data, video_file, post_dir, 'tiktok', post_id, metrics
    
    def _download_instagram(self, url: str, post_dir: str, post_id: str) -> Tuple[Dict, Optional[str], str, str, str, Dict]:
        """Download Instagram video"""
        data = None
        
        # Try with credentials first, fallback to no auth
        auth_commands = []
        if self.settings.instagram_username and self.settings.instagram_password:
            auth_commands.append([
                'yt-dlp', '--dump-json', '--no-download', 
                '--username', self.settings.instagram_username, 
                '--password', self.settings.instagram_password, url
            ])
        
        auth_commands.append(['yt-dlp', '--dump-json', '--no-download', url])
        
        for cmd in auth_commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                data = json.loads(result.stdout)
                break
            except subprocess.CalledProcessError:
                continue
        
        if not data:
            raise DownloadError("Failed to get Instagram metadata")
        
        # Download video
        video_file = None
        output_template = os.path.abspath(os.path.join(post_dir, f"{post_id}.%(ext)s"))
        
        download_commands = []
        if self.settings.instagram_username and self.settings.instagram_password:
            download_commands.append([
                'yt-dlp', '--output', output_template, '--no-playlist',
                '--username', self.settings.instagram_username,
                '--password', self.settings.instagram_password, url
            ])
        
        download_commands.append([
            'yt-dlp', '--output', output_template, '--no-playlist', url
        ])
        
        for cmd in download_commands:
            try:
                subprocess.run(cmd, capture_output=True, text=True, check=True)
                break
            except subprocess.CalledProcessError:
                continue
        
        # Find downloaded file
        for file in os.listdir(post_dir):
            if file.startswith(post_id) and file.endswith(('.mp4', '.mkv', '.webm')):
                video_file = os.path.join(post_dir, file)
                break
        
        # Create metrics
        metrics = {
            'platform': 'instagram',
            'url': url,
            'post_id': post_id,
            'title': data.get('title') or data.get('fulltitle') or 'N/A',
            'description': data.get('description') or data.get('alt_title') or '',
            'uploader': data.get('uploader') or data.get('channel') or data.get('uploader_id') or 'N/A',
            'uploader_id': data.get('uploader_id') or data.get('channel_id') or 'N/A',
            'upload_date': data.get('upload_date') or data.get('timestamp') or 'N/A',
            'duration': data.get('duration') or 'N/A',
            'view_count': data.get('view_count') or data.get('play_count') or 'N/A',
            'like_count': data.get('like_count') or 'N/A',
            'comment_count': data.get('comment_count') or 'N/A',
            'scraped_at': datetime.now().isoformat(),
            'storage_directory': post_dir,
        }
        
        if video_file:
            metrics['media_file'] = video_file
        
        self.save_metrics_to_json(metrics, post_dir, 'instagram', post_id)
        return data, video_file, post_dir, 'instagram', post_id, metrics
    
    def save_metrics_to_json(self, metrics: Dict, post_dir: str, platform: str, post_id: str) -> str:
        """Save metrics to JSON file
        
        Args:
            metrics: Metrics dictionary
            post_dir: Directory to save in
            platform: Platform name
            post_id: Post ID
            
        Returns:
            Path to saved file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{platform}_{post_id}_metrics_{timestamp}.json"
        filepath = os.path.join(post_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def extract_keyframes_smart(self, video_path: str, output_dir: str, max_frames: int = 10, method: str = 'hybrid') -> List[Dict]:
        """Extract smart keyframes from video
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save frames
            max_frames: Maximum number of frames
            method: Extraction method
            
        Returns:
            List of frame data for AI analysis
        """
        keyframes_data = self.frame_extractor.extract_smart_keyframes(video_path, max_frames, method)
        images = []
        
        for i, (frame_idx, frame, importance) in enumerate(keyframes_data):
            img_path = os.path.join(output_dir, f'smart_frame_{i:03d}.jpg')
            cv2.imwrite(img_path, frame)
            
            with open(img_path, "rb") as img_file:
                b64_img = base64.b64encode(img_file.read()).decode('utf-8')
                images.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_img}"
                    }
                })
        
        return images
    
    def summarize_video_content(self, transcript: str, visual_contents: List[Dict], language: str = 'en') -> str:
        """Generate AI summary of video content
        
        Args:
            transcript: Video transcript
            visual_contents: Visual frame data
            language: Language for summary
            
        Returns:
            AI-generated summary
        """
        if language == 'id':
            prompt = (
                "Berdasarkan transkrip audio dan gambar-gambar dari video berikut, extract:\n"
                "Hook (bagian pembuka yang menarik perhatian): ...\n"
                "Plot (alur utama atau urutan cerita): ...\n"
                "Kategori Konten (misal: edukasi, hiburan, motivasi, dll.): ...\n"
                "Detail Konten: ...\n"
                "Jangan menambah atau mengarang informasi di luar transkrip dan gambar. Jika informasi tidak ada, tulis 'Tidak tersedia'.\n"
                "Kembalikan ringkasan dengan format:\n"
                "Hook: ...\n"
                "Plot: ...\n"
                "Category: ...\n"
                "Details Content: ...\n"
            )
            transcript_label = "TRANSKRIP"
        else:
            prompt = (
                "Based on the audio transcript and the images from the following video, extract:\n"
                "Hook (the attention-grabbing start): ...\n"
                "Plot (the main story or sequence): ...\n"
                "Category Content (e.g., education, entertainment, motivation, etc.): ...\n"
                "Details Content: ...\n"
                "Do not add or make up information that is not present in the transcript or images. If information is not available, write 'Not available.'\n"
                "Return the summary in this format:\n"
                "Hook: ...\n"
                "Plot: ...\n"
                "Category: ...\n"
                "Details Content: ...\n"
            )
            transcript_label = "TRANSCRIPT"
        
        messages = [
            {"role": "system", "content": "You are a video summarization assistant."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                *visual_contents,
                {"type": "text", "text": f"{transcript_label}:\n{transcript}"}
            ]}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"Error generating video summary: {e}")
            raise ContentAnalysisError(f"Failed to generate video summary: {e}")
    
    def sanitize_filename(self, name: str) -> str:
        """Sanitize filename for cross-platform compatibility"""
        import re
        return re.sub(r'[<>:"/\\|?*]', '_', name)
    
    async def analyze_video_from_url(self, url: str, language: str = 'en') -> Dict:
        """Complete video analysis workflow from social media URL
        
        Args:
            url: Social media URL
            language: Language for analysis
            
        Returns:
            Analysis results
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Download video
            data, video_file, post_dir, platform, post_id, metrics = self.download_social_media_video(url, tmpdir)
            
            if not video_file:
                raise ContentAnalysisError('Video file not found after scraping!')
            
            # Extract transcript (this will need transcription service)
            from app.services.transcription import TranscriptionService
            transcription_service = TranscriptionService(self.settings)
            transcript_result = await transcription_service.transcribe_video(video_file)
            transcript = transcript_result.get('text', '')
            
            # Extract keyframes
            keyframes = self.extract_keyframes_smart(video_file, tmpdir, max_frames=15, method='hybrid')
            
            # Generate summary
            summary = self.summarize_video_content(transcript, keyframes, language=language)
            
            # Parse category from summary
            import re
            category_match = re.search(r'Category\s*:\s*(.*)', summary)
            category_display = category_match.group(1).strip().split('\n')[0] if category_match else 'Uncategorized'
            category_code = category_display.lower().replace(' ', '_').replace('/', '_')
            category_code = self.sanitize_filename(category_code)
            
            # Organize results
            post_folder_name = f"{platform}_{post_id}"
            category_post_dir = os.path.join(self.settings.temp_dir, 'content_analysis', category_code, post_folder_name)
            os.makedirs(category_post_dir, exist_ok=True)
            
            # Save summary
            summary_file = os.path.join(category_post_dir, f'{platform}_{post_id}_summary.txt')
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(summary)
            
            # Copy video file if different location
            if video_file:
                dst_video = os.path.join(category_post_dir, os.path.basename(video_file))
                if os.path.abspath(video_file) != os.path.abspath(dst_video):
                    shutil.copy2(video_file, dst_video)
                    video_file = dst_video
            
            return {
                'summary': summary,
                'category_name': category_display,
                'category_code': category_code,
                'summary_file': summary_file,
                'category_post_dir': category_post_dir,
                'platform': platform,
                'post_id': post_id,
                'video_file': video_file,
                'transcript': transcript,
                'metrics': metrics
            } 