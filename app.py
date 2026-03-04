from flask import Flask, render_template, request, jsonify, send_from_directory
import os
from mutagen import File as MutagenFile

app = Flask(__name__)

# 1) лимит на загрузку (поставь сколько нужно)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB

# 2) стабильный путь к папке проекта (важно для хостинга)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

DEFAULT_COVER_URL = "/static/covers/default.jpg"

# 3) создать uploads если её нет
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def safe_join(*parts):
    return os.path.normpath(os.path.join(*parts))


def find_cover_in_dir(dir_path: str, url_prefix: str) -> str:
    """
    Ищем обложку в папке: cover.jpg/png, folder.jpg/png, front.jpg/png, Cover.jpg...
    Возвращаем URL или дефолт.
    """
    if not os.path.isdir(dir_path):
        return DEFAULT_COVER_URL

    candidates = [
        "cover.jpg", "cover.jpeg", "cover.png",
        "folder.jpg", "folder.jpeg", "folder.png",
        "front.jpg", "front.jpeg", "front.png",
        "Cover.jpg", "Cover.png", "Folder.jpg", "Folder.png",
    ]

    existing = set(os.listdir(dir_path))
    for name in candidates:
        if name in existing:
            return f"{url_prefix}/{name}"

    # если вдруг у тебя обложка называется иначе, но это jpg/png — можно попытаться найти первую картинку
    for f in sorted(existing):
        lower = f.lower()
        if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return f"{url_prefix}/{f}"

    return DEFAULT_COVER_URL


def read_id3_title(mp3_path: str) -> str | None:
    """
    Пытаемся достать ID3 title из файла.
    Возвращаем None, если не получилось.
    """
    try:
        audio = MutagenFile(mp3_path, easy=True)
        if not audio:
            return None
        title = audio.get("title")
        if title and isinstance(title, list) and title[0].strip():
            return title[0].strip()
        if isinstance(title, str) and title.strip():
            return title.strip()
    except Exception:
        return None
    return None


def display_name_from_file(mp3_path: str, filename: str) -> str:
    """
    Что показывать в UI:
    1) ID3 title
    2) иначе имя файла без расширения
    """
    t = read_id3_title(mp3_path)
    if t:
        return t
    return os.path.splitext(filename)[0]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    """
    Ожидаем:
    - artist
    - album
    - files[] (mp3)
    """
    artist = (request.form.get("artist") or "Без исполнителя").strip() or "Без исполнителя"
    album = (request.form.get("album") or "Без альбома").strip() or "Без альбома"

    artist_dir = safe_join(UPLOAD_FOLDER, artist)
    album_dir = safe_join(artist_dir, album)
    os.makedirs(album_dir, exist_ok=True)

    files = request.files.getlist("files")
    saved = 0

    for f in files:
        if not f.filename.lower().endswith(".mp3"):
            continue

        filename = f.filename
        base, ext = os.path.splitext(filename)
        counter = 1
        target_path = safe_join(album_dir, filename)

        while os.path.exists(target_path):
            filename = f"{base}_{counter}{ext}"
            counter += 1
            target_path = safe_join(album_dir, filename)

        f.save(target_path)
        saved += 1

    return jsonify({"success": True, "saved": saved})


@app.route("/tracks")
def get_tracks():
    """
    Возвращаем структуру:
    {
      "Artist": {
        "cover": "/uploads/Artist/cover.jpg" (если есть) иначе дефолт,
        "albums": {
          "Album": {
            "cover": "/uploads/Artist/Album/cover.jpg" (если есть) иначе artist cover/def,
            "tracks": [
              {
                "file": "15566.mp3",
                "title": "BBB SLOW",        <-- ВОТ ЭТО ДЛЯ ОТОБРАЖЕНИЯ
                "path": "/uploads/Artist/Album/15566.mp3",
                "cover": "/uploads/Artist/Album/cover.jpg"
              }
            ]
          }
        }
      }
    }
    """
    library = {}

    for artist in sorted(os.listdir(UPLOAD_FOLDER)):
        artist_path = safe_join(UPLOAD_FOLDER, artist)
        if not os.path.isdir(artist_path):
            continue

        artist_url_prefix = f"/uploads/{artist}"
        artist_cover = find_cover_in_dir(artist_path, artist_url_prefix)

        albums_obj = {}

        for album in sorted(os.listdir(artist_path)):
            album_path = safe_join(artist_path, album)
            if not os.path.isdir(album_path):
                continue

            album_url_prefix = f"/uploads/{artist}/{album}"
            album_cover = find_cover_in_dir(album_path, album_url_prefix)
            # если в альбоме нет обложки — используем обложку артиста
            if album_cover == DEFAULT_COVER_URL and artist_cover != DEFAULT_COVER_URL:
                album_cover = artist_cover

            tracks = []
            for filename in sorted(os.listdir(album_path)):
                if not filename.lower().endswith(".mp3"):
                    continue
                mp3_path = safe_join(album_path, filename)
                title = display_name_from_file(mp3_path, filename)

                tracks.append({
                    "file": filename,
                    "title": title,
                    "path": f"/uploads/{artist}/{album}/{filename}",
                    "cover": album_cover
                })

            albums_obj[album] = {
                "cover": album_cover,
                "tracks": tracks
            }

        library[artist] = {
            "cover": artist_cover,
            "albums": albums_obj
        }

    return jsonify(library)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # filename может быть "Artist/Album/file.mp3"
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False)


if __name__ == "__main__":

    app.run(debug=True)
