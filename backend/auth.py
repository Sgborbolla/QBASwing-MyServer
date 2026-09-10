"""
QBASwing MyServer - usuarios, roles y autenticacion.

Sustituye las credenciales fijas que tenia Freeman Media Hub (ADMIN_USER /
ADMIN_PASS en app.py) por una tabla real de usuarios con contrasenas
encriptadas (hash) y roles verificados SIEMPRE en backend.

Jerarquia de roles (de mayor a menor privilegio):
    owner > administrator > manager > user > guest
"""
from functools import wraps
from datetime import datetime

from flask import session, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash

from backend import db

ROLES = ["owner", "administrator", "manager", "user", "guest"]
ROLE_RANK = {r: i for i, r in enumerate(ROLES)}  # menor numero = mas privilegio


def is_initialized():
    """True si ya existe una instalacion configurada (asistente inicial completado)."""
    return db.get_setting("initialized", "0") == "1"


def role_at_least(role, minimum):
    """True si 'role' tiene privilegios iguales o mayores que 'minimum'."""
    if role not in ROLE_RANK or minimum not in ROLE_RANK:
        return False
    return ROLE_RANK[role] <= ROLE_RANK[minimum]


def create_user(username, password, role="user", full_name="", email="", language="es"):
    conn = db.get_connection()
    try:
        conn.execute(
            """INSERT INTO users (username, password_hash, full_name, email, role, language, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (username.strip(), generate_password_hash(password), full_name.strip(),
             email.strip(), role, language, db.now()),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    finally:
        conn.close()


def get_user_by_username(username):
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users():
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT id, username, full_name, email, role, language, active, created_at FROM users ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def any_owner_exists():
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'owner'").fetchone()
        return row["c"] > 0
    finally:
        conn.close()


def verify_login(username, password):
    """Devuelve el usuario (dict) si las credenciales son validas y la cuenta
    esta activa, o None en caso contrario."""
    user = get_user_by_username(username)
    if not user or not user["active"]:
        return None
    if not check_password_hash(user["password_hash"], password):
        return None
    return user


def update_user(user_id, **fields):
    """Actualiza campos permitidos de un usuario. 'password' (texto plano) se
    convierte automaticamente en password_hash."""
    allowed = {"full_name", "email", "role", "language", "active"}
    sets, values = [], []
    for key, value in fields.items():
        if key == "password" and value:
            sets.append("password_hash = ?")
            values.append(generate_password_hash(value))
        elif key in allowed:
            sets.append(f"{key} = ?")
            values.append(value)
    if not sets:
        return
    sets.append("updated_at = ?")
    values.append(db.now())
    values.append(user_id)
    conn = db.get_connection()
    try:
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def delete_user(user_id):
    conn = db.get_connection()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def set_folder_permissions(user_id, category, can_view=1, can_download=1, can_upload=0, can_delete=0):
    conn = db.get_connection()
    try:
        conn.execute(
            """INSERT INTO user_folder_permissions (user_id, category, can_view, can_download, can_upload, can_delete)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, category) DO UPDATE SET
                 can_view=excluded.can_view, can_download=excluded.can_download,
                 can_upload=excluded.can_upload, can_delete=excluded.can_delete""",
            (user_id, category, int(can_view), int(can_download), int(can_upload), int(can_delete)),
        )
        conn.commit()
    finally:
        conn.close()


def get_folder_permissions(user_id):
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT * FROM user_folder_permissions WHERE user_id = ?", (user_id,)).fetchall()
        return {r["category"]: dict(r) for r in rows}
    finally:
        conn.close()


def can_access_category(user, category, action="view"):
    """Comprobacion de permisos EN BACKEND. owner/administrator/manager
    siempre tienen acceso total. user/guest se restringen segun
    user_folder_permissions: si el usuario no tiene ninguna fila de permisos
    definida, se le permite acceso general (comportamiento por defecto,
    configurable luego por el administrador); si tiene al menos una fila,
    solo se permite lo que esa fila autoriza para esa categoria."""
    if user is None:
        return False
    role = user.get("role")
    if role in ("owner", "administrator", "manager"):
        return True
    perms = get_folder_permissions(user["id"])
    if not perms:
        return True
    entry = perms.get(category)
    if not entry:
        return False
    field = {"view": "can_view", "download": "can_download",
             "upload": "can_upload", "delete": "can_delete"}.get(action, "can_view")
    return bool(entry.get(field))


def log_activity(action, details="", user=None, ip=None):
    conn = db.get_connection()
    try:
        conn.execute(
            "INSERT INTO activity_log (user_id, username, action, details, ip, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user.get("id") if user else None, user.get("username") if user else "sistema",
             action, details, ip, db.now()),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Decoradores de autorizacion para rutas Flask
# ---------------------------------------------------------------------------

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "no_autenticado"}), 401
            from flask import redirect, url_for
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(minimum_role):
    """Exige que el usuario autenticado tenga al menos 'minimum_role' de
    privilegio. La comprobacion ocurre siempre en backend, nunca solo en
    el frontend."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "no_autenticado"}), 401
                from flask import redirect, url_for
                return redirect(url_for("login"))
            if not role_at_least(user["role"], minimum_role):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "permiso_denegado"}), 403
                from flask import redirect, url_for
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped
    return decorator
