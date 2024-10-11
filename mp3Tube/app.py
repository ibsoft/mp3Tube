from flask import Flask, render_template, request, send_file, redirect, url_for, flash, jsonify
from yt_dlp import YoutubeDL
import os
import re
import math
import logging
import json
from urllib.parse import unquote
import platform

# Configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'downloads'

# Ensure download folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    logging.debug(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")

# Path to the JSON file for storing song metadata
METADATA_FILE = 'songs_metadata.json'


def load_songs_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    return []


def save_songs_metadata():
    with open(METADATA_FILE, 'w') as f:
        json.dump(downloaded_songs, f)


# Load downloaded songs metadata on startup
downloaded_songs = load_songs_metadata()


def sanitize_filename(filename):
    logging.debug(f"Sanitizing filename: {filename}")
    # Replace spaces with underscores and remove special characters
    filename = re.sub(r'\s+', '_', filename)  # Replace spaces with underscores
    # Remove specific special characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    logging.debug(f"Sanitized filename: {filename}")
    return filename


def download_video_as_mp3(youtube_url):
    logging.debug(f"Starting download for URL: {youtube_url}")

    # Detect the operating system
    current_os = platform.system()

    # Set ffmpeg location based on the operating system
    if current_os == "Linux":
        ffmpeg_path = "/usr/bin/ffmpeg"  # Default path for Linux
    elif current_os == "Windows":
        # Replace with actual path on Windows
        ffmpeg_path = r"C:\Program Files\FFmpeg\bin\ffmpeg.exe"
    else:
        ffmpeg_path = None  # Default to None if no custom location is needed

    try:
        # Set options for yt-dlp to extract audio only
        ydl_opts = {
            'format': 'bestaudio/best',
            # Use a template
            'outtmpl': os.path.join(app.config['UPLOAD_FOLDER'], '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'noplaylist': True,  # Don't download playlists
        }

        # Add ffmpeg location if it's specified
        if ffmpeg_path:
            ydl_opts['ffmpeg_location'] = ffmpeg_path

        with YoutubeDL(ydl_opts) as ydl:
            # Download the video and extract audio
            info = ydl.extract_info(youtube_url, download=True)
            title = info.get('title', None)

            if not title:
                raise Exception("No title found in video info.")

            logging.debug(f"Downloaded title: {title}")
            # Original MP3 filename after conversion
            original_mp3_filename = f"{title}.mp3"
            original_mp3_path = os.path.join(
                app.config['UPLOAD_FOLDER'], original_mp3_filename)

            # Get the file size after conversion
            file_size = os.path.getsize(
                original_mp3_path) / (1024 * 1024)  # Convert to MB
            logging.debug(f"File size after conversion: {file_size} MB")

            return {'title': title, 'file': original_mp3_filename, 'size': file_size, 'status': 'Success'}

    except Exception as e:
        logging.error(f"Error during download: {e}")
        return {'title': None, 'file': None, 'size': 0, 'status': 'Failed'}


@app.route('/', methods=['GET', 'POST'])
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    start = (page - 1) * per_page
    end = start + per_page
    paginated_songs = downloaded_songs[start:end]
    total_pages = math.ceil(len(downloaded_songs) / per_page)

    logging.debug(f"Rendering index page: {page}, total pages: {total_pages}")

    if request.method == 'POST':
        youtube_url = request.form.get('youtube_url')

        if not youtube_url:
            flash('Please enter a YouTube URL', 'danger')
            logging.warning("User submitted empty YouTube URL.")
            return redirect(url_for('index'))

        song_data = download_video_as_mp3(youtube_url)
        if song_data['status'] == 'Success':
            downloaded_songs.append(song_data)
            save_songs_metadata()  # Save the updated metadata
            logging.debug(f"Song data added: {song_data}")

        return jsonify({'status': song_data['status'], 'file': song_data['file'], 'size': song_data['size']})

    return render_template('index.html', songs=paginated_songs, page=page, total_pages=total_pages)


@app.route('/download/<filename>')
def download(filename):
    logging.debug(f"Initiating download for file: {filename}")
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)


@app.route('/delete/<path:filename>', methods=['POST'])
def delete(filename):
    # Decode the filename to handle URL-encoded characters
    decoded_filename = unquote(filename)
    logging.debug(f"Attempting to delete file: {decoded_filename}")

    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], decoded_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            downloaded_songs[:] = [
                s for s in downloaded_songs if s['file'] != decoded_filename]
            save_songs_metadata()  # Save the updated metadata
            flash('File deleted successfully.', 'success')
            logging.debug(f"Deleted file: {decoded_filename}")
        else:
            flash('File not found.', 'warning')
            logging.warning(f"File not found: {decoded_filename}")
    except Exception as e:
        flash(f'Error deleting file: {str(e)}', 'danger')
        logging.error(f"Error deleting file: {e}")

    return redirect(url_for('index'))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=False)
