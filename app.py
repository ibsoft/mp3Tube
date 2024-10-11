from flask import Flask, render_template, request, send_file, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from yt_dlp import YoutubeDL
import os
import re
import math
import logging
from urllib.parse import unquote
import platform

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'downloads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///songs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLite database
db = SQLAlchemy(app)

# Ensure download folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
    logging.debug(f"Created upload folder: {app.config['UPLOAD_FOLDER']}")

# Define Song model
class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    file = db.Column(db.String(200), nullable=False)
    size = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False)

# Create the database and tables
with app.app_context():
    db.create_all()

def sanitize_filename(filename):
    logging.debug(f"Sanitizing filename: {filename}")
    # Replace spaces with underscores and remove special characters
    filename = re.sub(r'\s+', '_', filename)  # Replace spaces with underscores
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)  # Remove specific special characters
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
            original_mp3_path = os.path.join(app.config['UPLOAD_FOLDER'], original_mp3_filename)

            # Get the file size after conversion
            file_size = os.path.getsize(original_mp3_path) / (1024 * 1024)  # Convert to MB
            logging.debug(f"File size after conversion: {file_size} MB")

            return {'title': title, 'file': original_mp3_filename, 'size': file_size, 'status': 'Success'}

    except Exception as e:
        logging.error(f"Error during download: {e}")
        return {'title': None, 'file': None, 'size': 0, 'status': 'Failed'}

@app.route('/', methods=['GET', 'POST'])
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    songs = Song.query.paginate(page=page, per_page=per_page)

    logging.debug(f"Rendering index page: {page}, total pages: {songs.pages}")

    if request.method == 'POST':
        youtube_url = request.form.get('youtube_url')

        if not youtube_url:
            flash('Please enter a YouTube URL', 'danger')  # Flash failure message
            logging.warning("User submitted empty YouTube URL.")
            return redirect(url_for('index'))

        song_data = download_video_as_mp3(youtube_url)

        if song_data['status'] == 'Success':
            new_song = Song(title=song_data['title'], file=song_data['file'], size=song_data['size'], status=song_data['status'])
            db.session.add(new_song)
            db.session.commit()
            flash(f'Successfully converted: {song_data["title"]}', 'success')  # Flash success message
            logging.debug(f"Song data added to database: {song_data}")
        else:
            flash(f'Conversion failed for the provided URL.', 'danger')  # Flash failure message

        return jsonify({'status': song_data['status'], 'file': song_data['file'], 'size': song_data['size']})

    return render_template('index.html', songs=songs.items, page=page, total_pages=songs.pages)


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
            song = Song.query.filter_by(file=decoded_filename).first()
            if song:
                db.session.delete(song)
                db.session.commit()
            flash('MP3 file deleted successfully.', 'success')
            logging.debug(f"Deleted file: {decoded_filename}")
        else:
            flash('MP3 file not found.', 'warning')
            logging.warning(f"File not found: {decoded_filename}")
    except Exception as e:
        flash(f'Error deleting MP3 file: {str(e)}', 'danger')
        logging.error(f"Error deleting file: {e}")

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
