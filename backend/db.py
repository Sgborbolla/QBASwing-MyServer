"""
QBASwing MyServer - capa de acceso a datos (SQLite)
"""
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "qbaswing_myserver.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_names(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(conn):
    """Agrega columnas nuevas a bases de datos ya existentes, sin borrar nada."""
    cols = _column_names(conn, "download_requests")
    if "verification_message" not in cols:
        conn.execute("ALTER TABLE download_requests ADD COLUMN verification_message TEXT")
    if "payment_status" not in cols:
        conn.execute("ALTER TABLE download_requests ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'pendiente'")
    if "payment_method" not in cols:
        conn.execute("ALTER TABLE download_requests ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'transferencia'")
    if "client_uid" not in cols:
        conn.execute("ALTER TABLE download_requests ADD COLUMN client_uid TEXT")
    if "completed_at" not in cols:
        conn.execute("ALTER TABLE download_requests ADD COLUMN completed_at TEXT")

    media_cols = _column_names(conn, "media_files")
    if "subfolder" not in media_cols:
        conn.execute("ALTER TABLE media_files ADD COLUMN subfolder TEXT NOT NULL DEFAULT ''")
    if "is_free" not in media_cols:
        # Contenido gratis/de pago POR ARCHIVO (spec: "cada contenido puede
        # ser gratis o de pago"), independiente del modo de distribucion
        # global. En modo comercial, un archivo marcado is_free=1 se
        # descarga sin cobro aunque el resto de la biblioteca sea de pago.
        conn.execute("ALTER TABLE media_files ADD COLUMN is_free INTEGER NOT NULL DEFAULT 0")
    if "content_kind" not in media_cols:
        # video/audio/image/pdf/document/book/archive/software/other -- se
        # calcula al escanear (backend.scanner.detect_content_kind) y se
        # usa para elegir reproductor/visor en el cliente.
        conn.execute("ALTER TABLE media_files ADD COLUMN content_kind TEXT NOT NULL DEFAULT 'other'")

    location_cols = _column_names(conn, "locations")
    if "selected_files" not in location_cols:
        conn.execute("ALTER TABLE locations ADD COLUMN selected_files TEXT DEFAULT '[]'")

    # Modulo de Patrocinio y Donaciones: crea las tablas nuevas y siembra la
    # configuracion por defecto en instalaciones que ya existian ANTES de
    # este modulo (una instalacion nueva ya las crea via schema.sql).
    tables = {row["name"] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "sponsors" not in tables:
        conn.execute("""
            CREATE TABLE sponsors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                level TEXT NOT NULL DEFAULT 'bronce',
                message TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pendiente',
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sponsors_status ON sponsors(status)")
    if "donations" not in tables:
        conn.execute("""
            CREATE TABLE donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                donor_name TEXT NOT NULL DEFAULT 'Anónimo',
                contact TEXT NOT NULL DEFAULT '',
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                method TEXT NOT NULL DEFAULT 'whatsapp',
                message TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pendiente',
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_donations_status ON donations(status)")
    if "qvapay_payments" not in tables:
        conn.execute("""
            CREATE TABLE qvapay_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                donation_id INTEGER NOT NULL,
                transaction_uuid TEXT UNIQUE,
                remote_id TEXT UNIQUE NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                status TEXT NOT NULL DEFAULT 'pending',
                payment_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (donation_id) REFERENCES donations(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qvapay_payments_donation_id ON qvapay_payments(donation_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qvapay_payments_status ON qvapay_payments(status)")

    donation_defaults = {
        "donation_goal_label": "Meta de recaudación",
        "donation_goal_amount": "0",
        "donation_currency": "USD",
        "donation_intro_text": "",
        "donation_crypto_info": "",
        "donation_qvapay_info": "",
        "donation_whatsapp": "+53 58147030",
        "donation_module_enabled": "1",
    }
    for key, value in donation_defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    conn.commit()


def init_db():
    """Crea la base de datos y las tablas si no existen, y migra las que ya existan."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    _migrate(conn)
    conn.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

def add_location(path, label, scan_mode, chosen_subfolders=None, selected_files=None):
    import json
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO locations (path, label, scan_mode, chosen_subfolders, selected_files, added_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (path, label, scan_mode, json.dumps(chosen_subfolders or []), json.dumps(selected_files or []), now()),
    )
    conn.commit()
    loc_id = cur.lastrowid
    conn.close()
    return loc_id


def list_locations():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM locations ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_location(location_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_location(location_id):
    conn = get_connection()
    conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
    conn.commit()
    conn.close()


def touch_location_scan(location_id):
    conn = get_connection()
    conn.execute("UPDATE locations SET last_scan_at = ? WHERE id = ?", (now(), location_id))
    conn.commit()
    conn.close()


def update_location_selected_files(location_id, file_paths):
    """Actualiza la lista de archivos sueltos de una ubicación tipo 'files'
    (usado para fusionar selecciones nuevas con las que ya existían, sin
    perder ninguna)."""
    import json
    conn = get_connection()
    conn.execute(
        "UPDATE locations SET selected_files = ? WHERE id = ?",
        (json.dumps(file_paths), location_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Media files
# ---------------------------------------------------------------------------

def get_filepaths_for_location(location_id):
    """Devuelve el conjunto de filepaths ya registrados para una ubicación
    (para poder escanear de forma incremental: solo agregar lo nuevo, sin
    tocar lo que ya existe ni sus decisiones de visibilidad)."""
    conn = get_connection()
    rows = conn.execute("SELECT filepath FROM media_files WHERE location_id = ?", (location_id,)).fetchall()
    conn.close()
    return {r["filepath"] for r in rows}


def clear_media_for_location(location_id):
    conn = get_connection()
    conn.execute("DELETE FROM media_files WHERE location_id = ?", (location_id,))
    conn.commit()
    conn.close()


def insert_media_file(location_id, filename, filepath, category, subfolder, extension, size_bytes, image_path, visible=0, content_kind="other"):
    """visible=1 cuando el archivo se agrega desde el explorador automático
    (Mejora 1): queda publicado de inmediato, sin que el administrador tenga
    que volver a activarlo a mano. Solo aplica a inserciones NUEVAS —
    INSERT OR IGNORE nunca modifica un archivo que ya existiera, así que
    jamás revierte una decisión manual de ocultar algo."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO media_files "
            "(location_id, filename, filepath, category, subfolder, extension, size_bytes, image_path, visible, content_kind, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (location_id, filename, filepath, category, subfolder, extension, size_bytes, image_path, 1 if visible else 0, content_kind, now()),
        )
        conn.commit()
    finally:
        conn.close()


def set_media_free(file_id, is_free):
    conn = get_connection()
    try:
        conn.execute("UPDATE media_files SET is_free = ? WHERE id = ?", (1 if is_free else 0, file_id))
        conn.commit()
    finally:
        conn.close()


def list_categories():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT DISTINCT category FROM media_files ORDER BY category ASC").fetchall()
        return [r["category"] for r in rows]
    finally:
        conn.close()


def list_media_files(only_visible=False):
    conn = get_connection()
    if only_visible:
        rows = conn.execute(
            "SELECT * FROM media_files WHERE visible = 1 ORDER BY category, filename"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM media_files ORDER BY category, filename"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _escape_like(text):
    """Escapa % y _ para que una búsqueda literal no se comporte como comodín."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_media_files(query, only_visible=False):
    """Búsqueda REAL contra SQLite (Mejoras 10/11/12): nombre, categoría,
    subcarpeta, extensión y también la etiqueta/ruta de la ubicación de
    origen. Case-insensitive (LOWER en ambos lados).

    Cuando only_visible=True (buscador del cliente), el filtro
    'visible = 1' se aplica DENTRO de la propia consulta SQL — el backend
    es quien decide qué filas existen para el cliente; nunca se le entrega
    una lista completa para que JavaScript la recorte después."""
    conn = get_connection()
    like = f"%{_escape_like(query)}%"
    sql = """
        SELECT m.*, l.label AS location_label, l.path AS location_path
        FROM media_files m
        LEFT JOIN locations l ON l.id = m.location_id
        WHERE (
            LOWER(m.filename) LIKE LOWER(?) ESCAPE '\\'
            OR LOWER(m.category) LIKE LOWER(?) ESCAPE '\\'
            OR LOWER(m.subfolder) LIKE LOWER(?) ESCAPE '\\'
            OR LOWER(m.extension) LIKE LOWER(?) ESCAPE '\\'
            OR LOWER(COALESCE(l.label, '')) LIKE LOWER(?) ESCAPE '\\'
            OR LOWER(COALESCE(l.path, '')) LIKE LOWER(?) ESCAPE '\\'
        )
    """
    params = [like] * 6
    if only_visible:
        sql += " AND m.visible = 1"
    sql += " ORDER BY m.category, m.filename"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_media_file(file_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM media_files WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_media_files_by_ids(ids):
    if not ids:
        return []
    conn = get_connection()
    q_marks = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT * FROM media_files WHERE id IN ({q_marks})", ids
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_visibility(file_id, visible):
    conn = get_connection()
    conn.execute("UPDATE media_files SET visible = ? WHERE id = ?", (1 if visible else 0, file_id))
    conn.commit()
    conn.close()


def set_visibility_bulk(file_ids, visible):
    if not file_ids:
        return
    conn = get_connection()
    q_marks = ",".join("?" for _ in file_ids)
    conn.execute(
        f"UPDATE media_files SET visible = ? WHERE id IN ({q_marks})",
        [1 if visible else 0] + file_ids,
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Identidad persistente de invitados (misma IP = mismo invitado)
# ---------------------------------------------------------------------------

def get_or_create_guest_identity(ip, label=None):
    """Devuelve el client_uid persistente asociado a esta IP en la red
    local. Si la IP ya tiene una identidad registrada (de esta sesion o de
    una anterior, incluso antes de un reinicio del servidor), se reutiliza
    el mismo client_uid -- asi el invitado conserva sus solicitudes y
    descargas. Si es una IP nueva, se crea una identidad nueva.

    'label' es solo informativo (ultima etiqueta de dispositivo detectada,
    para mostrar en el panel de admin) y NUNCA se usa para identificar --
    la identidad depende unicamente de la IP."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM guest_identities WHERE ip = ?", (ip,)).fetchone()
    if row:
        conn.execute(
            "UPDATE guest_identities SET last_seen_at = ?, label = COALESCE(?, label) WHERE ip = ?",
            (now(), label, ip),
        )
        conn.commit()
        client_uid = row["client_uid"]
        conn.close()
        return client_uid

    import uuid
    client_uid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO guest_identities (ip, client_uid, label, created_at, last_seen_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ip, client_uid, label, now(), now()),
    )
    conn.commit()
    conn.close()
    return client_uid


# ---------------------------------------------------------------------------
# Configuracion (settings)
# ---------------------------------------------------------------------------

def get_setting(key, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def get_settings():
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_setting(key, value):
    conn = get_connection()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Download requests
# ---------------------------------------------------------------------------

def create_request(client_label, file_ids, total_size_bytes, total_price, payment_method="transferencia", verification_message=None, client_uid=None, auto_approve=False):
    import json
    conn = get_connection()
    if auto_approve:
        status = "approved"
        payment_status = "gratuito"
    else:
        status = "pending"
        if payment_method == "efectivo":
            payment_status = "pendiente_efectivo"
        elif verification_message:
            payment_status = "verificacion_enviada"
        else:
            payment_status = "pendiente"  # no deberia ocurrir: app.py exige verificacion para 'transferencia'
    cur = conn.execute(
        "INSERT INTO download_requests "
        "(client_label, client_uid, file_ids, total_size_bytes, total_price, status, payment_status, payment_method, verification_message, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (client_label, client_uid, json.dumps(file_ids), total_size_bytes, total_price, status, payment_status, payment_method, verification_message, now()),
    )
    conn.commit()
    req_id = cur.lastrowid
    conn.close()
    return req_id


def set_verification_message(request_id, message):
    conn = get_connection()
    conn.execute(
        "UPDATE download_requests SET verification_message = ?, payment_status = 'verificacion_enviada', "
        "updated_at = ? WHERE id = ?",
        (message, now(), request_id),
    )
    conn.commit()
    conn.close()


def list_requests(status=None, client_label=None, client_uid=None, hide_completed_older_than_hours=None):
    """'hide_completed_older_than_hours' implementa la limpieza automatica
    del historial del administrador (Cambio 7): una solicitud 'completed'
    con mas de N horas desde completed_at se excluye del listado. NO borra
    la fila -- solo deja de incluirse en esta consulta -- y nunca afecta
    solicitudes pendientes, aprobadas (en curso) o rechazadas, sea cual sea
    su antiguedad."""
    conn = get_connection()
    query = "SELECT * FROM download_requests WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if client_uid:
        query += " AND client_uid = ?"
        params.append(client_uid)
    elif client_label:
        query += " AND client_label = ?"
        params.append(client_label)
    if hide_completed_older_than_hours is not None:
        query += (
            " AND NOT (status = 'completed' AND completed_at IS NOT NULL "
            "AND datetime(completed_at) < datetime('now', 'localtime', ?))"
        )
        params.append(f"-{int(hide_completed_older_than_hours)} hours")
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_request(request_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM download_requests WHERE id = ?", (request_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_request_status(request_id, status):
    payment_status = "aprobado" if status == "approved" else ("rechazado" if status == "rejected" else "pendiente")
    conn = get_connection()
    conn.execute(
        "UPDATE download_requests SET status = ?, payment_status = ?, updated_at = ? WHERE id = ?",
        (status, payment_status, now(), request_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Progreso persistente de descargas (SQLite, no RAM/sesion) y separacion
# entre "descarga disponible" y "descarga completada"
# ---------------------------------------------------------------------------

def upsert_download_progress(request_id, file_id, client_uid, received_bytes, total_bytes, status):
    """Guarda/actualiza el progreso real (bytes) de UN archivo dentro de una
    solicitud. 'status' es 'pendiente' / 'descargando' / 'pausado' /
    'completado'. Esto es lo que permite recuperar una descarga 'en curso'
    tras cerrar sesion o reiniciar el servidor -- el offset queda en disco
    (SQLite), no en memoria."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO download_progress (request_id, file_id, client_uid, received_bytes, total_bytes, status, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(request_id, file_id) DO UPDATE SET "
        "received_bytes = excluded.received_bytes, total_bytes = excluded.total_bytes, "
        "status = excluded.status, updated_at = excluded.updated_at, "
        "client_uid = COALESCE(excluded.client_uid, download_progress.client_uid)",
        (request_id, file_id, client_uid, received_bytes, total_bytes, status, now()),
    )
    conn.commit()
    conn.close()


def get_progress_for_request(request_id):
    """Progreso persistido de cada archivo de una solicitud: {file_id: row}."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM download_progress WHERE request_id = ?", (request_id,)
    ).fetchall()
    conn.close()
    return {r["file_id"]: dict(r) for r in rows}


def mark_request_completed_if_all_done(request_id):
    """Si TODOS los archivos de una solicitud (approved) ya estan marcados
    como 'completado' en download_progress, la solicitud completa pasa a
    status='completed' (con completed_at). El registro NUNCA se borra --
    sigue existiendo como historial -- pero deja de ser una 'descarga
    disponible' (ya no pasa el filtro status == 'approved')."""
    import json
    req = get_request(request_id)
    if not req or req["status"] != "approved":
        return False
    file_ids = json.loads(req["file_ids"])
    if not file_ids:
        return False
    progress = get_progress_for_request(request_id)
    all_done = all(progress.get(fid, {}).get("status") == "completado" for fid in file_ids)
    if not all_done:
        return False
    conn = get_connection()
    conn.execute(
        "UPDATE download_requests SET status = 'completed', updated_at = ?, completed_at = ? WHERE id = ?",
        (now(), now(), request_id),
    )
    conn.commit()
    conn.close()
    return True


# ---------------------------------------------------------------------------
# Modulo de Patrocinio y Donaciones
# ---------------------------------------------------------------------------

def add_sponsor(name, email="", phone="", level="bronce", message=""):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO sponsors (name, email, phone, level, message, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'pendiente', ?)",
        (name, email, phone, level, message, now()),
    )
    conn.commit()
    sponsor_id = cur.lastrowid
    conn.close()
    return sponsor_id


def list_sponsors(status=None):
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM sponsors WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM sponsors ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_sponsor_status(sponsor_id, status):
    conn = get_connection()
    conn.execute(
        "UPDATE sponsors SET status = ?, updated_at = ? WHERE id = ?",
        (status, now(), sponsor_id),
    )
    conn.commit()
    conn.close()


def delete_sponsor(sponsor_id):
    conn = get_connection()
    conn.execute("DELETE FROM sponsors WHERE id = ?", (sponsor_id,))
    conn.commit()
    conn.close()


def add_donation(donor_name="Anónimo", contact="", amount=0, currency="USD",
                  method="whatsapp", message=""):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO donations (donor_name, contact, amount, currency, method, message, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pendiente', ?)",
        (donor_name or "Anónimo", contact, float(amount or 0), currency, method, message, now()),
    )
    conn.commit()
    donation_id = cur.lastrowid
    conn.close()
    return donation_id


def list_donations(status=None):
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM donations WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM donations ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_donation_status(donation_id, status):
    conn = get_connection()
    conn.execute(
        "UPDATE donations SET status = ?, updated_at = ? WHERE id = ?",
        (status, now(), donation_id),
    )
    conn.commit()
    conn.close()


def delete_donation(donation_id):
    conn = get_connection()
    conn.execute("DELETE FROM donations WHERE id = ?", (donation_id,))
    conn.commit()
    conn.close()


def donation_totals():
    """Suma de donaciones confirmadas, agrupada por moneda, mas el conteo
    de patrocinadores aprobados. Usado para la barra de progreso de la
    meta de recaudacion (solo cuenta lo confirmado por el administrador,
    nunca lo pendiente)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT currency, SUM(amount) AS total FROM donations WHERE status = 'confirmada' GROUP BY currency"
    ).fetchall()
    sponsor_count = conn.execute(
        "SELECT COUNT(*) AS c FROM sponsors WHERE status = 'aprobado'"
    ).fetchone()["c"]
    conn.close()
    by_currency = {r["currency"]: (r["total"] or 0) for r in rows}
    return {"by_currency": by_currency, "approved_sponsors": sponsor_count}
