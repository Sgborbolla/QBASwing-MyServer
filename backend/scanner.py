"""
QBASwing MyServer - escaner de archivos multimedia
"""
import os
import time
import shutil
import unicodedata

# Categorias de extension: se usan para elegir la miniatura/reproductor
# adecuado en el cliente (spec "biblioteca universal" -- ya no es solo
# un servidor de videos).
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mpg", ".mpeg", ".mov", ".wmv", ".webm", ".flv", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".svg"}
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".wma", ".opus"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".txt", ".rtf", ".xls", ".xlsx",
                        ".ods", ".csv", ".ppt", ".pptx", ".odp"}
BOOK_EXTENSIONS = {".epub", ".mobi", ".azw", ".azw3", ".fb2", ".djvu"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}
SOFTWARE_EXTENSIONS = {".exe", ".msi", ".apk", ".dmg", ".iso", ".deb", ".appimage", ".bat", ".sh"}

# Union de todo lo anterior: cualquier extension aqui obtiene un icono/
# categoria especifica. Lo que NO esta aqui (y no esta en el denylist de
# abajo) igual se publica como archivo descargable generico -- la
# biblioteca acepta cualquier tipo de contenido, no solo lo listado.
KNOWN_EXTENSIONS = (VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS |
                     DOCUMENT_EXTENSIONS | BOOK_EXTENSIONS | ARCHIVE_EXTENSIONS | SOFTWARE_EXTENSIONS)

# Extensiones/nombres que NUNCA se publican (basura del sistema operativo,
# archivos temporales o parciales), para no ensuciar la biblioteca -- esto
# es un denylist corto, no una lista blanca: todo lo demas SI se publica.
_IGNORED_EXTENSIONS = {".tmp", ".ini", ".log", ".lnk", ".url", ".bak", ".crdownload",
                        ".part", ".ds_store", ".db"}
_IGNORED_FILENAMES = {"thumbs.db", "desktop.ini", ".ds_store"}


def is_publishable_file(filename):
    """True si el archivo debe entrar en la biblioteca. Denylist corto de
    basura de sistema -- todo lo demas se acepta, sea cual sea su
    extension (spec: biblioteca universal, no solo videos)."""
    lower = filename.lower()
    if lower in _IGNORED_FILENAMES or lower.startswith("."):
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext not in _IGNORED_EXTENSIONS


def detect_content_kind(ext):
    """Clasifica una extension para que el cliente elija el reproductor o
    icono correcto: video / audio / image / document / book / archive /
    software / other."""
    ext = ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in BOOK_EXTENSIONS:
        return "book"
    if ext in ARCHIVE_EXTENSIONS:
        return "archive"
    if ext in SOFTWARE_EXTENSIONS:
        return "software"
    return "other"


CATEGORY_KEYWORDS = {
    "peliculas": "Películas",
    "pelicula": "Películas",
    "movies": "Películas",
    "movie": "Películas",
    "series": "Series",
    "serie": "Series",
    "novelas": "Novelas",
    "novela": "Novelas",
    "documentales": "Documentales",
    "documental": "Documentales",
    "documentaries": "Documentales",
    "musica": "Música",
    "music": "Música",
    "audio": "Audio",
    "podcast": "Podcasts",
    "podcasts": "Podcasts",
    "libros": "Libros",
    "books": "Libros",
    "ebooks": "Libros",
    "documentos": "Documentos",
    "documents": "Documentos",
    "docs": "Documentos",
    "imagenes": "Imágenes",
    "images": "Imágenes",
    "fotos": "Imágenes",
    "software": "Software",
    "programas": "Software",
    "juegos": "Software",
    "games": "Software",
}


def _strip_accents(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def guess_category(root_path, file_dir):
    """Adivina la categoria (Peliculas/Series/Novelas/Documentales/General)
    revisando los nombres de las carpetas entre root_path y el archivo."""
    try:
        rel = os.path.relpath(file_dir, root_path)
    except ValueError:
        rel = file_dir
    parts = [p for p in rel.split(os.sep) if p not in ("", ".")]
    for part in parts:
        key = _strip_accents(part).lower().strip()
        if key in CATEGORY_KEYWORDS:
            return CATEGORY_KEYWORDS[key]
    return "General"


def guess_category_and_subfolder(root_path, file_dir):
    """Como guess_category, pero ademas devuelve la ruta relativa de
    subcarpetas DESPUES de la carpeta de categoria (para poder mostrar la
    biblioteca como un explorador: Novelas / Serie A / Temporada 1).

    Ejemplos (root_path = "/discos/Peliculas"):
      file_dir == root_path                       -> categoria detectada por el
                                                        nombre de root_path, subfolder=""
      root_path/Novelas/Serie A                    -> categoria="Novelas", subfolder="Serie A"
      root_path/Novelas/Serie A/Temporada 1         -> categoria="Novelas", subfolder="Serie A/Temporada 1"
      root_path/Carpeta sin match/Sub               -> categoria="General", subfolder="Carpeta sin match/Sub"
    """
    try:
        rel = os.path.relpath(file_dir, root_path)
    except ValueError:
        rel = file_dir
    parts = [p for p in rel.split(os.sep) if p not in ("", ".")]

    # Tambien evaluamos el propio nombre de la carpeta raiz de escaneo, por si
    # el usuario eligio escanear directamente una carpeta llamada "Peliculas".
    root_name_key = _strip_accents(os.path.basename(root_path.rstrip("/\\"))).lower().strip()
    if root_name_key in CATEGORY_KEYWORDS and not parts:
        return CATEGORY_KEYWORDS[root_name_key], ""

    for idx, part in enumerate(parts):
        key = _strip_accents(part).lower().strip()
        if key in CATEGORY_KEYWORDS:
            subfolder = "/".join(parts[idx + 1:])
            return CATEGORY_KEYWORDS[key], subfolder

    if root_name_key in CATEGORY_KEYWORDS:
        return CATEGORY_KEYWORDS[root_name_key], "/".join(parts)

    # Ninguna carpeta coincide con una categoria conocida: todo queda en
    # "General" y el camino completo se conserva como subcarpeta.
    return "General", "/".join(parts)


def find_cover_image(file_path):
    """Busca una imagen con el mismo nombre base en la misma carpeta."""
    base, _ = os.path.splitext(file_path)
    for ext in IMAGE_EXTENSIONS:
        candidate = base + ext
        if os.path.isfile(candidate):
            return candidate
        candidate_upper = base + ext.upper()
        if os.path.isfile(candidate_upper):
            return candidate_upper
    return None


def iter_scan_roots(location):
    """Devuelve la lista de carpetas raiz a recorrer segun el modo de escaneo."""
    import json
    path = location["path"]
    if location["scan_mode"] == "folder":
        subfolders = json.loads(location["chosen_subfolders"] or "[]")
        roots = [os.path.join(path, sf) for sf in subfolders]
        return [r for r in roots if os.path.isdir(r)]
    # modo 'tower': se escanea todo lo que hay bajo path
    return [path] if os.path.isdir(path) else []


def scan_location(location):
    """Recorre las carpetas de una ubicacion y devuelve una lista de archivos encontrados.
    Cada elemento: dict(filename, filepath, category, subfolder, extension, size_bytes, image_path)
    """
    if location["scan_mode"] == "files":
        return _scan_selected_files(location)

    results = []
    roots = iter_scan_roots(location)
    base_path = location["path"]

    for root in roots:
        for current_dir, _dirs, files in os.walk(root):
            for fname in files:
                if not is_publishable_file(fname):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                full_path = os.path.join(current_dir, fname)
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    size = 0
                category, subfolder = guess_category_and_subfolder(base_path, current_dir)
                image_path = find_cover_image(full_path)
                results.append({
                    "filename": fname,
                    "filepath": full_path,
                    "category": category,
                    "subfolder": subfolder,
                    "extension": ext.lstrip("."),
                    "size_bytes": size,
                    "image_path": image_path,
                })
    return results


def _scan_selected_files(location):
    """Para ubicaciones creadas seleccionando archivos sueltos (no una carpeta
    completa): solo agrega exactamente esos archivos, sin recorrer nada mas."""
    import json
    results = []
    base_path = location["path"]
    selected = json.loads(location.get("selected_files") or "[]")
    for full_path in selected:
        if not os.path.isfile(full_path):
            continue
        if not is_publishable_file(os.path.basename(full_path)):
            continue
        ext = os.path.splitext(full_path)[1].lower()
        try:
            size = os.path.getsize(full_path)
        except OSError:
            size = 0
        category, subfolder = guess_category_and_subfolder(base_path, os.path.dirname(full_path))
        image_path = find_cover_image(full_path)
        results.append({
            "filename": os.path.basename(full_path),
            "filepath": full_path,
            "category": category,
            "subfolder": subfolder,
            "extension": ext.lstrip("."),
            "size_bytes": size,
            "image_path": image_path,
        })
    return results


def list_subfolders(path):
    """Lista las subcarpetas directas de path (para el selector de carpetas del admin)."""
    entries = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False) and not entry.name.startswith('.'):
                    entries.append(entry.name)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        pass
    return sorted(entries, key=lambda s: s.lower())


def _entry_kind(ext):
    kind = detect_content_kind(ext)
    return kind if kind != "other" else None


def find_folder_cover(folder_path):
    """Busca una imagen de portada dentro de una carpeta: poster/cover/portada,
    o una imagen con el mismo nombre que la carpeta (para el explorador en
    vivo, Mejora 5 — carpetas que representan una pelicula/serie)."""
    if not os.path.isdir(folder_path):
        return None
    candidates = ["poster", "cover", "portada", os.path.basename(folder_path.rstrip("/\\"))]
    try:
        entries = {e.name.lower(): e.path for e in os.scandir(folder_path) if e.is_file()}
    except (OSError, PermissionError):
        return None
    for name in candidates:
        for ext in IMAGE_EXTENSIONS:
            hit = entries.get((name + ext).lower())
            if hit:
                return hit
    return None


def estimate_folder_size(path, max_seconds=1.2, max_files=6000):
    """Calcula el tamaño de una carpeta recorriendo su contenido, con un
    límite de tiempo Y de cantidad de archivos (lo que se alcance primero),
    para no dejar la interfaz esperando si la carpeta tiene miles de
    archivos (Mejora 6). Devuelve (bytes_totales, es_parcial, archivos_contados)."""
    start = time.time()
    total = 0
    count = 0
    partial = False
    for current_dir, _dirs, files in os.walk(path):
        for fname in files:
            full = os.path.join(current_dir, fname)
            try:
                total += os.path.getsize(full)
            except OSError:
                continue
            count += 1
            if count >= max_files or (time.time() - start) > max_seconds:
                partial = True
                return total, partial, count
    return total, partial, count


def get_disk_usage(path):
    """Capacidad de una unidad/disco (Mejora 6). shutil.disk_usage es rápido
    siempre (no recorre archivos, lo resuelve el sistema operativo)."""
    try:
        usage = shutil.disk_usage(path)
        return {"total": usage.total, "used": usage.used, "free": usage.free}
    except OSError:
        return None


def list_dir_entries(path):
    """Lista carpetas Y archivos multimedia directos de path, para el nuevo
    explorador tipo Emby del admin (permite marcar carpetas O archivos
    sueltos con casilla, en vez de solo escribir rutas a mano).

    Devuelve una lista de dicts:
      carpetas: {"name":.., "type": "dir", "cover_path": ruta o None}
      archivos: {"name":.., "type": "file", "kind": "video"/"audio"/"image",
                 "extension":.., "size_bytes":.., "cover_path": ruta o None}
    Carpetas primero, despues archivos, ambos ordenados alfabeticamente.

    "cover_path" (Mejora 5) es una ruta absoluta en el disco del propio
    servidor -- el frontend NUNCA la muestra directamente, la usa como
    parametro para pedir la imagen real a /api/admin/live-thumbnail.
    """
    dirs, files = [], []
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        entries = []

    for entry in entries:
        if entry.name.startswith('.'):
            continue
        try:
            if entry.is_dir(follow_symlinks=False):
                dirs.append(entry.name)
                continue
            ext = os.path.splitext(entry.name)[1].lower()
            if not is_publishable_file(entry.name):
                continue  # basura de sistema (thumbs.db, .tmp, etc.)
            kind = _entry_kind(ext) or "other"
            size = entry.stat().st_size
            cover = find_cover_image(entry.path) if kind == "video" else None
            files.append({
                "name": entry.name, "type": "file", "kind": kind,
                "extension": ext.lstrip("."), "size_bytes": size,
                "cover_path": cover,
            })
        except OSError:
            continue

    dirs_sorted = []
    for d in sorted(dirs, key=lambda s: s.lower()):
        dirs_sorted.append({
            "name": d, "type": "dir",
            "cover_path": find_folder_cover(os.path.join(path, d)),
        })
    files_sorted = sorted(files, key=lambda f: f["name"].lower())
    return dirs_sorted + files_sorted


def list_windows_drives():
    """Detecta únicamente las unidades de almacenamiento reales accesibles."""
    import string
    import re

    drives = []

    # Windows: C:\, D:\, E:\, etc.
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = letter + ":\\"
            if os.path.exists(drive):
                drives.append(drive)
        return drives

    seen = set()

    def add(path):
        try:
            real = os.path.realpath(path)
            if os.path.isdir(real) and real not in seen:
                seen.add(real)
                drives.append(real)
        except OSError:
            pass

    # Android: memoria interna.
    add("/storage/emulated/0")

    # /sdcard normalmente apunta a la memoria interna.
    add("/sdcard")

    # Android: volúmenes externos. Android puede impedir listar /storage,
    # pero las rutas de volumen conocidas siguen siendo accesibles.
    if os.path.isdir("/storage"):
        try:
            for entry in os.listdir("/storage"):
                if re.fullmatch(r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}", entry):
                    add(os.path.join("/storage", entry))
        except OSError:
            pass

    # En algunos dispositivos Termux no puede listar /storage, aunque
    # las rutas de los volúmenes montados sean accesibles. Consultamos
    # los puntos de montaje para descubrirlos sin recorrer carpetas.
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as mounts:
            for line in mounts:
                fields = line.split()
                if len(fields) < 2:
                    continue
                mountpoint = fields[1].replace("\\040", " ")
                if re.fullmatch(r"/storage/[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}", mountpoint):
                    add(mountpoint)
    except OSError:
        pass

    # Linux: buscar únicamente puntos de montaje reales.
    if not drives:
        for base in ("/mnt", "/media", "/run/media"):
            if not os.path.isdir(base):
                continue
            try:
                for entry in os.scandir(base):
                    if entry.is_dir(follow_symlinks=False) and os.path.ismount(entry.path):
                        add(entry.path)
            except OSError:
                continue

    return drives

