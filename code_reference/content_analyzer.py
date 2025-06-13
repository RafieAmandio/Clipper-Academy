import os
import tempfile
import shutil
import subprocess
import base64
import json
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
from openai import OpenAI
import re

class SmartFrameExtractor:
    def __init__(self):
        self.orb = cv2.ORB_create(nfeatures=500)
    def calculate_frame_importance(self, frame):
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
    def detect_scene_changes(self, video_path, threshold=0.3):
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
    def extract_smart_keyframes(self, video_path, max_frames=20, method='hybrid'):
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

class ContentAnalyzer:
    def __init__(self, openai_api_key=None, instagram_username=None, instagram_password=None, output_dir="content_classification"):
        import os
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.instagram_username = instagram_username or os.getenv("INSTAGRAM_USERNAME")
        self.instagram_password = instagram_password or os.getenv("INSTAGRAM_PASSWORD")
        self.output_dir = output_dir
        from openai import OpenAI
        self.client = OpenAI(api_key=self.openai_api_key)
        os.makedirs(self.output_dir, exist_ok=True)

    def check_yt_dlp(self):
        try:
            subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, check=True)
            return True
        except FileNotFoundError:
            return False

    def detect_platform(self, url):
        url = url.lower()
        if 'tiktok.com' in url:
            return 'tiktok'
        elif 'instagram.com' in url:
            return 'instagram'
        else:
            return 'unknown'

    def extract_post_id_from_url(self, url, platform):
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

    def scrape_social_media(self, url, download_dir, download_media=True):
        platform = self.detect_platform(url)
        post_id = self.extract_post_id_from_url(url, platform) or 'unknown'
        post_dir = os.path.join(download_dir, f"{platform}_{post_id}")
        os.makedirs(post_dir, exist_ok=True)
        metrics = None
        if platform == 'tiktok':
            cmd = [
                'yt-dlp', '--dump-json', '--no-download', url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            video_file = None
            if download_media:
                output_template = os.path.abspath(os.path.join(post_dir, f"{post_id}.%(ext)s"))
                cmd_download = [
                    'yt-dlp', '--output', output_template, '--no-playlist', '--format', 'best[height<=720]/best', url
                ]
                subprocess.run(cmd_download, capture_output=True, text=True, check=True)
                for file in os.listdir(post_dir):
                    if file.startswith(post_id) and file.endswith(('.mp4', '.mkv', '.webm')):
                        video_file = os.path.join(post_dir, file)
                        break
            # Save metrics json
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
            self.save_metrics_to_json(metrics, post_dir, platform, post_id)
            return data, video_file, post_dir, platform, post_id, metrics
        elif platform == 'instagram':
            data = None
            try:
                cmd_auth = [
                    'yt-dlp', '--dump-json', '--no-download', '--username', self.instagram_username, '--password', self.instagram_password, url
                ]
                result = subprocess.run(cmd_auth, capture_output=True, text=True, check=True)
                data = json.loads(result.stdout)
            except Exception:
                cmd_fallback = [
                    'yt-dlp', '--dump-json', '--no-download', url
                ]
                result = subprocess.run(cmd_fallback, capture_output=True, text=True, check=True)
                data = json.loads(result.stdout)
            video_file = None
            if download_media:
                output_template = os.path.abspath(os.path.join(post_dir, f"{post_id}.%(ext)s"))
                cmd_download = [
                    'yt-dlp', '--output', output_template, '--no-playlist', url
                ]
                if self.instagram_username and self.instagram_password:
                    cmd_download = [
                        'yt-dlp', '--output', output_template, '--no-playlist', '--username', self.instagram_username, '--password', self.instagram_password, url
                    ]
                subprocess.run(cmd_download, capture_output=True, text=True, check=True)
                for file in os.listdir(post_dir):
                    if file.startswith(post_id) and file.endswith(('.mp4', '.mkv', '.webm')):
                        video_file = os.path.join(post_dir, file)
                        break
            # Save metrics json
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
            self.save_metrics_to_json(metrics, post_dir, platform, post_id)
            return data, video_file, post_dir, platform, post_id, metrics
        else:
            raise Exception('Unsupported platform')

    def save_metrics_to_json(self, metrics, post_dir, platform, post_id):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{platform}_{post_id}_metrics_{timestamp}.json"
        filepath = os.path.join(post_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        return filepath

    def extract_audio(self, video_path, output_dir):
        audio_path = os.path.join(output_dir, 'audio.wav')
        subprocess.run([
            'ffmpeg', '-y', '-i', video_path, '-vn',
            '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
            audio_path
        ], check=True)
        return audio_path

    def transcribe_audio(self, audio_path):
        with open(audio_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
            return transcript.text

    def extract_keyframes_smart(self, video_path, output_dir, max_frames=10, method='hybrid'):
        extractor = SmartFrameExtractor()
        keyframes_data = extractor.extract_smart_keyframes(video_path, max_frames, method)
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

    def summarize_video(self, transcript, visual_contents, language='en'):
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
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        return response.choices[0].message.content

    def analyze(self, url, language='en', download_media=True) -> dict:
        if not self.check_yt_dlp():
            raise RuntimeError('yt-dlp not found')
        with tempfile.TemporaryDirectory() as tmpdir:
            data, video_file, post_dir, platform, post_id, metrics = self.scrape_social_media(url, tmpdir, download_media=download_media)
            if not video_file:
                raise RuntimeError('Video file not found after scraping!')
            audio_path = self.extract_audio(video_file, tmpdir)
            transcript = self.transcribe_audio(audio_path)
            keyframes = self.extract_keyframes_smart(video_file, tmpdir, max_frames=15, method='hybrid')
            summary = self.summarize_video(transcript, keyframes, language=language)
            # Save summary and organize files
            import re
            category_match = re.search(r'Category\s*:\s*(.*)', summary)
            category_display = category_match.group(1).strip().split('\n')[0] if category_match else 'Uncategorized'
            category_code = category_display.lower().replace(' ', '_').replace('/', '_')
            category_code = self.sanitize_windows_filename(category_code)
            post_folder_name = f"{platform}_{post_id}"
            category_post_dir = os.path.join(self.output_dir, category_code, post_folder_name)
            os.makedirs(category_post_dir, exist_ok=True)
            summary_file = os.path.join(category_post_dir, f'{platform}_{post_id}_summary.txt')
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(summary)
            # Move/copy video file
            if video_file:
                dst_video = os.path.join(category_post_dir, os.path.basename(video_file))
                if os.path.abspath(video_file) != os.path.abspath(dst_video):
                    shutil.copy2(video_file, dst_video)
            # Copy all metrics json files matching pattern
            for fname in os.listdir(post_dir):
                if fname.startswith(f'{platform}_{post_id}_metrics') and fname.endswith('.json'):
                    src = os.path.join(post_dir, fname)
                    dst = os.path.join(category_post_dir, fname)
                    if os.path.abspath(src) != os.path.abspath(dst):
                        shutil.copy2(src, dst)
            return {
                'summary': summary,
                'category_name': category_display,  # display name
                'category_code': category_code,  # snake_case code
                'summary_file': summary_file,
                'category_post_dir': category_post_dir,
                'platform': platform,
                'post_id': post_id,
                'video_file': video_file,
                'transcript': transcript,
                'metrics': metrics
            }

    def resummarize(self, category_post_dir: str, language='en') -> dict:
        """
        Re-analyze existing content without re-downloading the media file.
        Args:
            category_post_dir (str): Directory containing the content to re-analyze
            language (str, optional): Language for summary. Defaults to 'en'.
        Returns:
            dict: Analysis results including new summary and category
        """
        # Find video file in the directory
        video_file = None
        platform = None
        post_id = None
        # Extract platform and post_id from directory name
        dir_name = os.path.basename(category_post_dir)
        if '_' in dir_name:
            platform, post_id = dir_name.split('_', 1)
        for file in os.listdir(category_post_dir):
            if file.endswith(('.mp4', '.mkv', '.webm')):
                video_file = os.path.join(category_post_dir, file)
                break
        if not video_file:
            raise RuntimeError('Video file not found in the specified directory!')
        # Find latest metrics file
        metrics = None
        metrics_files = [f for f in os.listdir(category_post_dir) if f.endswith('_metrics.json')]
        if metrics_files:
            latest_metrics_file = max(metrics_files)
            with open(os.path.join(category_post_dir, latest_metrics_file)) as f:
                metrics = json.load(f)
        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate new transcript and keyframes
            audio_path = self.extract_audio(video_file, tmpdir)
            transcript = self.transcribe_audio(audio_path)
            keyframes = self.extract_keyframes_smart(video_file, tmpdir, max_frames=15, method='hybrid')
            # Generate new summary
            summary = self.summarize_video(transcript, keyframes, language=language)
            # Detect category from new summary
            import re
            category_match = re.search(r'Category\s*:\s*(.*)', summary)
            new_category_display = category_match.group(1).strip().split('\n')[0] if category_match else 'Uncategorized'
            new_category_code = new_category_display.lower().replace(' ', '_').replace('/', '_')
            new_category_code = self.sanitize_windows_filename(new_category_code)
            # Determine if content needs to be moved to a new category
            old_category_code = os.path.basename(os.path.dirname(category_post_dir))
            needs_move = new_category_code != old_category_code
            if needs_move:
                # Setup new directory path
                new_post_dir = os.path.join(self.output_dir, new_category_code, f"{platform}_{post_id}")
                os.makedirs(new_post_dir, exist_ok=True)
                # Move all files to new category
                for file in os.listdir(category_post_dir):
                    src = os.path.join(category_post_dir, file)
                    dst = os.path.join(new_post_dir, file)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                # Update category_post_dir to new location
                category_post_dir = new_post_dir
            # Save new summary
            summary_file = os.path.join(category_post_dir, f'{platform}_{post_id}_summary.txt')
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(summary)
            return {
                'summary': summary,
                'old_category': old_category_code,  # old snake_case code
                'old_category_display': None,  # Not tracked, can be looked up if needed
                'new_category': new_category_display,  # display name
                'new_category_code': new_category_code,  # snake_case code
                'category_changed': needs_move,
                'summary_file': summary_file,
                'category_post_dir': category_post_dir,
                'platform': platform,
                'post_id': post_id,
                'video_file': video_file,
                'transcript': transcript,
                'metrics': metrics
            }

    def sanitize_windows_filename(self, name):
        import re
        return re.sub(r'[<>:"/\\|?*]', '_', name)
