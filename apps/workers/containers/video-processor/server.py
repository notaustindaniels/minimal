#!/usr/bin/env python3
"""
Video Processor Container Server
Uses AssemblyAI for transcription (much lighter than Whisper)
"""

import os
import json
import subprocess
import tempfile
import requests
import assemblyai as aai
from flask import Flask, request, jsonify

app = Flask(__name__)

# Config from environment
ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "")
MAX_VIDEO_LENGTH = int(os.environ.get("MAX_VIDEO_LENGTH", 3600))
DEPLOYMENT_ID = os.environ.get("CLOUDFLARE_DEPLOYMENT_ID", "unknown")

# Configure AssemblyAI
if ASSEMBLYAI_API_KEY:
    aai.settings.api_key = ASSEMBLYAI_API_KEY


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "deployment_id": DEPLOYMENT_ID,
        "assemblyai_configured": bool(ASSEMBLYAI_API_KEY),
        "max_video_length": MAX_VIDEO_LENGTH,
        "ffmpeg_version": get_ffmpeg_version(),
    })


@app.route("/download", methods=["POST"])
def download_video():
    """Download video from URL using yt-dlp"""
    data = request.json or {}
    url = data.get("url")
    
    if not url:
        return jsonify({"error": "URL required"}), 400
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "video.mp4")
            
            result = subprocess.run([
                "yt-dlp",
                "-f", "best[ext=mp4]/best",
                "--max-filesize", "500M",
                "-o", output_path,
                url
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                return jsonify({
                    "error": "Download failed",
                    "details": result.stderr
                }), 500
            
            file_size = os.path.getsize(output_path)
            
            return jsonify({
                "success": True,
                "file_size": file_size,
            })
            
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Download timed out"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/transcribe", methods=["POST"])
def transcribe():
    """Transcribe audio using AssemblyAI"""
    data = request.json or {}
    audio_url = data.get("audio_url")
    
    if not audio_url:
        return jsonify({"error": "audio_url required"}), 400
    
    if not ASSEMBLYAI_API_KEY:
        return jsonify({"error": "ASSEMBLYAI_API_KEY not configured"}), 500
    
    try:
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(audio_url)
        
        if transcript.status == aai.TranscriptStatus.error:
            return jsonify({
                "error": "Transcription failed",
                "details": transcript.error
            }), 500
        
        return jsonify({
            "success": True,
            "text": transcript.text,
            "words": [
                {"text": w.text, "start": w.start, "end": w.end}
                for w in (transcript.words or [])
            ],
            "confidence": transcript.confidence,
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/extract-audio", methods=["POST"])
def extract_audio():
    """Extract audio from video using FFmpeg"""
    data = request.json or {}
    video_url = data.get("video_url")
    
    if not video_url:
        return jsonify({"error": "video_url required"}), 400
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            audio_path = os.path.join(tmpdir, "audio.mp3")
            
            subprocess.run([
                "curl", "-L", "-o", video_path, video_url
            ], check=True, timeout=120)
            
            result = subprocess.run([
                "ffmpeg",
                "-i", video_path,
                "-vn",
                "-acodec", "libmp3lame",
                "-ab", "128k",
                "-y",
                audio_path
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                return jsonify({
                    "error": "Audio extraction failed",
                    "details": result.stderr
                }), 500
            
            audio_size = os.path.getsize(audio_path)
            
            return jsonify({
                "success": True,
                "audio_size": audio_size,
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/clip", methods=["POST"])
def create_clip():
    """Create a clip from video using FFmpeg"""
    data = request.json or {}
    video_url = data.get("video_url")
    start_time = data.get("start", 0)
    duration = data.get("duration", 30)
    
    if not video_url:
        return jsonify({"error": "video_url required"}), 400
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.mp4")
            output_path = os.path.join(tmpdir, "clip.mp4")
            
            subprocess.run([
                "curl", "-L", "-o", input_path, video_url
            ], check=True, timeout=120)
            
            result = subprocess.run([
                "ffmpeg",
                "-i", input_path,
                "-ss", str(start_time),
                "-t", str(duration),
                "-c:v", "libx264",
                "-c:a", "aac",
                "-y",
                output_path
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                return jsonify({
                    "error": "Clip creation failed",
                    "details": result.stderr
                }), 500
            
            clip_size = os.path.getsize(output_path)
            
            return jsonify({
                "success": True,
                "clip_size": clip_size,
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def get_ffmpeg_version():
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.stdout.split("\n")[0]
    except:
        return "unknown"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting server on port {port}")
    app.run(host="0.0.0.0", port=port)
