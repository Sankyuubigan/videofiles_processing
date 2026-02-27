import subprocess
import json
import os
import logging
from typing import List, Dict

class FFmpegProbeMixin:
    def get_gpu_info(self) -> str:
        try:
            cmd = [self.ffmpeg_path, "-hide_banner", "-encoders"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode == 0:
                encoders = result.stdout
                gpu_encoders =[]
                if "h264_nvenc" in encoders: gpu_encoders.append("NVIDIA NVENC (H.264)")
                if "hevc_nvenc" in encoders: gpu_encoders.append("NVIDIA NVENC (HEVC)")
                if "h265_nvenc" in encoders: gpu_encoders.append("NVIDIA NVENC (HEVC)")
                if "h264_amf" in encoders: gpu_encoders.append("AMD AMF (H.264)")
                if "hevc_amf" in encoders: gpu_encoders.append("AMD AMF (HEVC)")
                if "h264_qsv" in encoders: gpu_encoders.append("Intel QSV (H.264)")
                if "hevc_qsv" in encoders: gpu_encoders.append("Intel QSV (HEVC)")
                return f"Доступные GPU: {', '.join(gpu_encoders)}" if gpu_encoders else "GPU не обнаружены"
            return "Не удалось получить инфо о GPU"
        except Exception:
            return "Ошибка при получении инфо о GPU"
    
    def get_audio_tracks(self, input_path: str) -> List[Dict]:
        cmd =[self.ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_streams", input_path]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode == 0:
                output_text = result.stdout.decode('utf-8', errors='replace')
                data = json.loads(output_text)
                return[
                    {
                        "index": s.get("index", i),
                        "codec": s.get("codec_name", "n/a"),
                        "language": s.get("tags", {}).get("language", "und"),
                        "title": s.get("tags", {}).get("title", f"Audio {i+1}"),
                        "channels": s.get("channels", 0),
                        "sample_rate": s.get("sample_rate", "n/a"),
                        "bit_rate": s.get("bit_rate", "n/a"),
                    }
                    for i, s in enumerate(data.get("streams", [])) if s.get("codec_type") == "audio"
                ]
            return[]
        except Exception:
            return[]
    
    def get_video_info(self, input_path: str) -> dict:
        cmd =[self.ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_path]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30, startupinfo=self._get_platform_specific_startupinfo())
            if result.returncode != 0: 
                return {"error": "Ошибка ffprobe при чтении файла"}
            
            output_text = result.stdout.decode('utf-8', errors='replace')
            data = json.loads(output_text)
            video_stream = next((s for s in data.get("streams",[]) if s.get("codec_type") == "video"), None)
            audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
            
            if not video_stream and not audio_streams:
                return {"error": "Медиапотоки не найдены"}
            
            format_info = data.get("format", {})
            duration = float(format_info.get("duration", 0))
            
            try:
                size_bytes = os.path.getsize(input_path)
            except Exception:
                size_bytes = int(format_info.get("size", 0))
            
            size_mb = size_bytes / (1024 * 1024)

            if not video_stream:
                width = height = video_bitrate = fps = 0
                needs_vfr_fix = is_hevc = is_10bit = False
                video_codec = pixel_format = "unknown"
            else:
                width = int(video_stream.get("width", 0))
                height = int(video_stream.get("height", 0))
                total_bitrate = int(format_info.get("bit_rate", 0))
                if total_bitrate == 0 and duration > 0:
                    total_bitrate = int((size_bytes * 8) / duration)
                video_bitrate = int(video_stream.get("bit_rate", 0))
                if video_bitrate == 0:
                    audio_bitrate = sum(int(s.get("bit_rate", 128000)) for s in audio_streams) if audio_streams else 128000
                    video_bitrate = max(0, total_bitrate - audio_bitrate)
                
                fps_str = video_stream.get("avg_frame_rate", "0/1")
                try:
                    fps_parts = fps_str.split("/")
                    fps = int(fps_parts[0]) / int(fps_parts[1]) if len(fps_parts) == 2 and int(fps_parts[1]) != 0 else 0
                except:
                    fps = 0
                needs_vfr_fix = video_stream.get("r_frame_rate") in ["1000/1", "0/0"] or fps_str == "0/0"
                is_hevc = video_stream.get("codec_name", "").lower() in ["hevc", "h265"]
                is_10bit = video_stream.get("pix_fmt", "").endswith("10le") or video_stream.get("pix_fmt", "").endswith("10be")
                video_codec = video_stream.get("codec_name", "unknown")
                pixel_format = video_stream.get("pix_fmt", "unknown")

            audio_bitrate = sum(int(s.get("bit_rate", 128000)) for s in audio_streams) if audio_streams else 128000
            subtitle_streams =[s for s in data.get("streams", []) if s.get("codec_type") == "subtitle"]
            
            return {
                "path": input_path,
                "duration": duration,
                "size_mb": size_mb,
                "video_bitrate": video_bitrate,
                "audio_bitrate": audio_bitrate,
                "width": width,
                "height": height,
                "fps": fps,
                "needs_vfr_fix": needs_vfr_fix,
                "is_hevc": is_hevc,
                "is_10bit": is_10bit,
                "video_codec": video_codec,
                "pixel_format": pixel_format,
                "has_subtitles": len(subtitle_streams) > 0,
                "audio_tracks": self.get_audio_tracks(input_path)
            }
        except Exception as e:
            return {"error": f"Исключение при получении информации: {str(e)}"}