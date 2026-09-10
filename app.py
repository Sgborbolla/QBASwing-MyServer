import os
try:
    exec(open("/home/sborbolla/qvapay_env.py").read(), globals())
except Exception:
    pass
"""
QBASwing MyServer
Un producto de QBASwing Designer - "Tu servidor digital privado"

Base tecnica heredada de Freeman Media Hub.

Servidor local Flask. Ejecutar con:  python app.py
"""
import os
import sys
import json
import time
import threading
import io
import shutil
import sqlite3
import zipfile
import mimetypes
from datetime import datetime
import uuid
from functools import wraps

from flask import (
    Flask, request, session, redirect, url_for, render_template,
    jsonify, send_file, abort, Response, stream_with_context
)

from backend import db, scanner, pricing, network, auth, i18n, discovery
from backend import device as device_module

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "frontend", "templates"),
    static_folder=os.path.join(BASE_DIR, "frontend", "static"),
    static_url_path="/static",
)
# La clave de sesion se genera una sola vez y se guarda en database/secret.key
# (no queda escrita en el codigo fuente). Si el archivo no existe se crea.
_SECRET_PATH = os.path.join(BASE_DIR, "database", "secret.key")


def _load_or_create_secret():
    os.makedirs(os.path.dirname(_SECRET_PATH), exist_ok=True)
    if os.path.isfile(_SECRET_PATH):
        with open(_SECRET_PATH, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    key = uuid.uuid4().hex + uuid.uuid4().hex
    with open(_SECRET_PATH, "w", encoding="utf-8") as f:
        f.write(key)
    return key


app.secret_key = _load_or_create_secret()
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 dias, para "recordar sesion"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # Limite superior HTTP para importaciones grandes. El QR aplica su propio limite de 20 MB; las descargas de la biblioteca se sirven en streaming.

SERVER_PORT = int(os.environ.get("QBASWING_PORT", "5000"))

# Roles considerados "staff" (equivalentes al antiguo unico rol "admin"):
# conservan acceso total al panel de administracion. La distincion fina
# entre owner/administrator/manager se aplica solo en las rutas que la
# especificacion pide restringir (gestion de usuarios, configuracion
# comercial), via backend.auth.role_required().
STAFF_ROLES = ("owner", "administrator", "manager")

GB = 1024 ** 3


def current_language():
    return session.get("language") or db.get_setting("default_language", "es") or "es"


@app.context_processor
def inject_globals():
    lang = current_language()
    return {
        "T": i18n.get_dict(lang),
        "current_lang": lang,
        "language_options": i18n.language_options(),
        # Identidad FIJA del producto (spec: protegida, el administrador no
        # puede cambiarla). "server_name"/"business_name" son solo
        # informacion secundaria del negocio, nunca reemplazan la marca.
        "app_name": "QBASwing MyServer",
        "app_company": "QBASwing Designer",
        "business_label": db.get_setting("business_name", "") or db.get_setting("server_name", ""),
        "distribution_mode": db.get_setting("distribution_mode", "free"),
    }


def current_price_settings():
    """Lee precio por GB y modo de redondeo actuales desde la base de datos."""
    price_per_gb = float(db.get_setting("price_per_gb", "10") or 10)
    rounding_mode = db.get_setting("rounding_mode", "none") or "none"
    return price_per_gb, rounding_mode


# ---------------------------------------------------------------------------
# Seguimiento de descargas en vivo (para el panel "Descargas" del admin)
# ---------------------------------------------------------------------------
# Estructura en memoria (no persiste en la base de datos: es informacion de
# transferencias EN CURSO). Cada entrada representa un archivo que se esta
# transmitiendo en este momento a un cliente.
LIVE_TRANSFERS = {}
LIVE_LOCK = threading.Lock()
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB por fragmento. OJO: este valor estaba mal
# configurado (1024000*1024000 = ~976 GB), lo que en la practica anulaba el
# streaming por fragmentos -- para casi cualquier archivo, un solo f.read()
# intentaba leer TODO el resto del archivo de una vez a RAM, en vez de ir
# entregando pedazos manejables al socket. Eso explica la lentitud/cuellos de
# botella: nada se enviaba hasta tener el bloque gigante listo en memoria. 8 MB
# es un tamaño de fragmento eficiente para transferencias en red local (WiFi/
# LAN), sin cargar archivos completos en memoria. No hay ningun otro límite de
# velocidad artificial en el proyecto (no hay time.sleep ni throttling).


# ---------------------------------------------------------------------------
# Clientes conectados (para la pestaña "Usuarios" del admin)
# ---------------------------------------------------------------------------
# Cada sesion de invitado se identifica por su dispositivo (ver backend/device.py),
# nunca por un contador "Invitado N". Se registra aqui junto a su IP para saber
# quien sigue conectado ("last_seen" se actualiza en cada llamada autenticada).
CONNECTED_CLIENTS = {}
CLIENTS_LOCK = threading.Lock()
CLIENT_STALE_SECONDS = 90  # sin actividad por mas de esto: se considera desconectado


def _register_client(client_uid, label, ip, user_agent=""):
    device = device_module.identify_device(user_agent, ip)
    with CLIENTS_LOCK:
        CONNECTED_CLIENTS[client_uid] = {
            "label": label,               # etiqueta de sesion (nombre de dispositivo) - se usa para mostrar y para permisos
            "device_label": device["label"],
            "os_family": device["os_family"],
            "ip": ip,
            "first_seen": time.time(),
            "last_seen": time.time(),
        }


def _touch_client(client_uid, ip):
    with CLIENTS_LOCK:
        c = CONNECTED_CLIENTS.get(client_uid)
        if c:
            c["last_seen"] = time.time()
            c["ip"] = ip


def _remove_client(client_uid):
    with CLIENTS_LOCK:
        CONNECTED_CLIENTS.pop(client_uid, None)


def _live_clients():
    now = time.time()
    with CLIENTS_LOCK:
        stale = [uid for uid, c in CONNECTED_CLIENTS.items() if now - c["last_seen"] > CLIENT_STALE_SECONDS]
        for uid in stale:
            CONNECTED_CLIENTS.pop(uid, None)
        clients = [{**c, "seconds_ago": round(now - c["last_seen"])} for c in CONNECTED_CLIENTS.values()]
    clients.sort(key=lambda c: c["first_seen"])
    return clients

def _start_transfer(transfer_id, client_label, request_id, filename, total_bytes, initial_offset=0):
    with LIVE_LOCK:
        LIVE_TRANSFERS[transfer_id] = {
            "id": transfer_id,
            "client_label": client_label,
            "request_id": request_id,
            "filename": filename,
            "bytes_sent": initial_offset,
            "total_bytes": total_bytes,
            "status": "descargando",
            "started_at": time.time(),
        }


def _update_transfer(transfer_id, bytes_sent):
    with LIVE_LOCK:
        t = LIVE_TRANSFERS.get(transfer_id)
        if t:
            t["bytes_sent"] = bytes_sent


def _finish_transfer(transfer_id, status="finalizado"):
    with LIVE_LOCK:
        t = LIVE_TRANSFERS.get(transfer_id)
        if t:
            t["status"] = status
            t["bytes_sent"] = t["total_bytes"]
    # Se deja visible unos segundos como "Finalizado" y luego se limpia,
    # para que el admin alcance a verlo terminar en la lista.
    def _cleanup():
        time.sleep(4)
        with LIVE_LOCK:
            LIVE_TRANSFERS.pop(transfer_id, None)
    threading.Thread(target=_cleanup, daemon=True).start()


# ---------------------------------------------------------------------------
# Utilidades de autenticacion
# ---------------------------------------------------------------------------

def _role_allowed(current, required):
    """'admin' como 'required' acepta cualquier rol de STAFF_ROLES (owner/
    administrator/manager), preservando el comportamiento previo de un
    unico rol admin para todas las rutas del panel administrativo."""
    if required is None:
        return True
    if required == "admin":
        return current in STAFF_ROLES
    return current == required


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "role" not in session:
                return redirect(url_for("login"))
            if not _role_allowed(session["role"], role):
                return redirect(url_for("login"))
            if session["role"] in ("client", "user", "guest") and session.get("client_uid"):
                _touch_client(session["client_uid"], request.remote_addr)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def api_login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "role" not in session:
                return jsonify({"error": "No autenticado"}), 401
            if not _role_allowed(session["role"], role):
                return jsonify({"error": "No autorizado"}), 403
            if session["role"] in ("client", "user", "guest") and session.get("client_uid"):
                _touch_client(session["client_uid"], request.remote_addr)
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# Rutas de vistas
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if not auth.is_initialized():
        return redirect(url_for("setup_wizard"))
    if session.get("role") in STAFF_ROLES:
        return redirect(url_for("admin_panel"))
    if session.get("role") in ("client", "user", "guest"):
        return redirect(url_for("client_library"))
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Asistente de configuracion inicial (solo aparece en la primera instalacion)
# ---------------------------------------------------------------------------

@app.route("/setup", methods=["GET"])
def setup_wizard():
    if auth.is_initialized():
        return redirect(url_for("login"))
    return render_template("setup.html")


@app.route("/api/setup", methods=["POST"])
def api_setup():
    """Completa la configuracion inicial: crea el Owner, guarda la
    configuracion del negocio/servidor y marca la instalacion como
    inicializada. No puede ejecutarse mas de una vez (protegido por el
    flag 'initialized' y por auth.any_owner_exists())."""
    if auth.is_initialized() or auth.any_owner_exists():
        return jsonify({"ok": False, "error": "ya_inicializado"}), 400

    data = request.get_json(force=True, silent=True) or {}
    owner_name = (data.get("owner_name") or "").strip()
    owner_email = (data.get("owner_email") or "").strip()
    owner_username = (data.get("owner_username") or "").strip()
    owner_password = data.get("owner_password") or ""
    owner_password_confirm = data.get("owner_password_confirm") or ""
    language = (data.get("language") or "es").strip()
    business_name = (data.get("business_name") or "").strip()
    # 'server_name' es solo un identificador secundario/interno de esta
    # instalacion (spec: proteccion de marca) -- NUNCA reemplaza la marca
    # fija "QBASwing MyServer", que se calcula siempre en inject_globals()
    # y no depende de ningun setting editable.
    server_name = (data.get("server_name") or "").strip()

    if not all([owner_name, owner_username, owner_password]):
        return jsonify({"ok": False, "error": "campos_requeridos"}), 400
    if owner_password != owner_password_confirm:
        return jsonify({"ok": False, "error": "contrasenas_no_coinciden"}), 400
    if len(owner_password) < 6:
        return jsonify({"ok": False, "error": "contrasena_corta"}), 400
    if language not in i18n.SUPPORTED_LANGUAGES:
        language = "es"

    # La PRIMERA cuenta creada en una instalacion nueva es SIEMPRE Owner.
    # El asistente no permite elegir otro rol: se fuerza aqui en backend.
    auth.create_user(owner_username, owner_password, role="owner",
                      full_name=owner_name, email=owner_email, language=language)

    db.set_setting("business_name", business_name)
    db.set_setting("server_name", server_name)
    db.set_setting("service_name", server_name)
    db.set_setting("default_language", language)
    db.set_setting("initialized", "1")

    auth.log_activity("instalacion_inicializada", f"Owner creado: {owner_username}", ip=request.remote_addr)

    return jsonify({"ok": True, "redirect": url_for("login")})



# === QBASWING DEMO ACCESS ===
@app.route("/demo")
def demo_access():
    if not auth.is_initialized():
        return redirect(url_for("setup_wizard"))

    # Buscar un usuario normal llamado "user".
    demo_user = None
    try:
        for candidate in auth.list_users():
            if str(candidate.get("username", "")).lower() == "user":
                demo_user = candidate
                break
    except Exception:
        pass

    if not demo_user:
        return redirect(url_for("login"))

    session.clear()
    session["user_id"] = demo_user.get("id")
    session["role"] = demo_user.get("role", "user")
    session["language"] = demo_user.get("language", "en")

    return redirect(url_for("client_library"))

@app.route("/login", methods=["GET"])
def login():
    if not auth.is_initialized():
        return redirect(url_for("setup_wizard"))
    if session.get("role") in STAFF_ROLES:
        return redirect(url_for("admin_panel"))
    if session.get("role") in ("client", "user", "guest"):
        return redirect(url_for("client_library"))
    return render_template("login.html")


@app.route("/api/set-language", methods=["POST"])
def api_set_language():
    data = request.get_json(force=True, silent=True) or {}
    lang = (data.get("language") or "es").strip()
    if lang not in i18n.SUPPORTED_LANGUAGES:
        lang = "es"
    session["language"] = lang
    if session.get("user_id"):
        auth.update_user(session["user_id"], language=lang)
    return jsonify({"ok": True, "language": lang})


# Proteccion basica anti fuerza bruta: bloqueo temporal por IP tras varios
# intentos fallidos seguidos. En memoria (no persiste al reiniciar), es
# suficiente para un servidor LAN de un solo proceso.
_LOGIN_ATTEMPTS = {}
_LOGIN_ATTEMPTS_LOCK = threading.Lock()
_LOGIN_MAX_ATTEMPTS = 6
_LOGIN_LOCKOUT_SECONDS = 120


def _login_is_locked(ip):
    with _LOGIN_ATTEMPTS_LOCK:
        entry = _LOGIN_ATTEMPTS.get(ip)
        if not entry:
            return False
        count, locked_until = entry
        if locked_until and time.time() < locked_until:
            return True
        if locked_until and time.time() >= locked_until:
            _LOGIN_ATTEMPTS.pop(ip, None)
        return False


def _register_login_failure(ip):
    with _LOGIN_ATTEMPTS_LOCK:
        count, _ = _LOGIN_ATTEMPTS.get(ip, (0, None))
        count += 1
        locked_until = time.time() + _LOGIN_LOCKOUT_SECONDS if count >= _LOGIN_MAX_ATTEMPTS else None
        _LOGIN_ATTEMPTS[ip] = (count, locked_until)


def _clear_login_failures(ip):
    with _LOGIN_ATTEMPTS_LOCK:
        _LOGIN_ATTEMPTS.pop(ip, None)


@app.route("/api/login", methods=["POST"])
def api_login():
    ip = request.remote_addr or "desconocida"
    if _login_is_locked(ip):
        return jsonify({"ok": False, "error": "demasiados_intentos"}), 429
    if not auth.is_initialized():
        return jsonify({"ok": False, "error": "no_inicializado"}), 400

    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    remember = bool(data.get("remember"))

    # Cuenta real registrada en el sistema de usuarios (Owner/Administrator/
    # Manager/User/Guest). Sustituye las credenciales fijas de Freeman Media
    # Hub: la verificacion de contraseña usa hash (werkzeug), nunca texto
    # plano, y el rol se comprueba siempre en backend.
    user = auth.verify_login(username, password)
    if user:
        _clear_login_failures(ip)
        session.clear()
        session["role"] = user["role"]
        session["username"] = user["username"]
        session["user_id"] = user["id"]
        session["language"] = user["language"] or "es"
        session.permanent = remember
        auth.log_activity("login", user=user, ip=request.remote_addr)

        if user["role"] in STAFF_ROLES:
            return jsonify({"ok": True, "redirect": url_for("admin_panel")})

        # Cuentas "user"/"guest" navegan la biblioteca como clientes, pero
        # con identidad real (no anonima) para que los permisos por carpeta
        # (backend.auth.can_access_category) se apliquen correctamente.
        session["client_uid"] = f"user:{user['id']}"
        _register_client(session["client_uid"], user["username"], request.remote_addr,
                          request.headers.get("User-Agent", ""))
        return jsonify({"ok": True, "redirect": url_for("client_library")})

    existing = auth.get_user_by_username(username)
    if existing and not existing["active"]:
        return jsonify({"ok": False, "error": "cuenta_desactivada"}), 401

    # Acceso de invitado anonimo (sin cuenta), heredado de Freeman Media Hub:
    # solo disponible si el propietario lo mantiene activado en Configuracion.
    guest_open = db.get_setting("guest_open_login", "1") == "1"
    if guest_open and username.lower() == "invitado":
        _clear_login_failures(ip)
        session.clear()
        label = device_module.identify_device(request.headers.get("User-Agent", ""), request.remote_addr)["label"]
        client_uid = db.get_or_create_guest_identity(request.remote_addr, label)
        session["role"] = "client"
        session["username"] = label
        session["client_uid"] = client_uid
        session.permanent = False
        _register_client(client_uid, label, request.remote_addr, request.headers.get("User-Agent", ""))
        auth.log_activity("login_invitado_anonimo", label, ip=request.remote_addr)
        return jsonify({"ok": True, "redirect": url_for("client_library")})

    _register_login_failure(ip)
    return jsonify({"ok": False, "error": "credenciales_invalidas"}), 401


@app.route("/logout")
def logout():
    if session.get("role") in ("client", "user", "guest") and session.get("client_uid"):
        _remove_client(session["client_uid"])
    session.clear()
    return redirect(url_for("login"))


@app.route("/client")
@login_required()
def client_library():
    return render_template("client.html", username=session.get("username"))


@app.route("/admin")
@login_required(role="admin")
def admin_panel():
    return render_template("admin.html", username=session.get("username"), user_role=session.get("role"))


# ---------------------------------------------------------------------------
# API - Usuarios (Owner/Administrator/Manager gestionan cuentas)
# ---------------------------------------------------------------------------

@app.route("/api/admin/users", methods=["GET"])
@auth.role_required("manager")
def api_users_list():
    return jsonify({"users": auth.list_users()})


@app.route("/api/admin/users", methods=["POST"])
@auth.role_required("administrator")
def api_users_create():
    """Solo Owner/Administrator crean cuentas. El rol solicitado nunca
    puede superar el del usuario que lo crea (un Administrator no puede
    crear otro Owner), y solo el asistente inicial puede crear un Owner."""
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip()
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()
    language = (data.get("language") or "es").strip()

    if not username or not password:
        return jsonify({"ok": False, "error": "campos_requeridos"}), 400
    if role not in auth.ROLES or role == "owner":
        return jsonify({"ok": False, "error": "rol_invalido"}), 400
    current = auth.current_user()
    if not auth.role_at_least(current["role"], role):
        return jsonify({"ok": False, "error": "no_puedes_asignar_ese_rol"}), 403
    if auth.get_user_by_username(username):
        return jsonify({"ok": False, "error": "usuario_ya_existe"}), 400

    user_id = auth.create_user(username, password, role=role, full_name=full_name,
                                email=email, language=language or "es")
    auth.log_activity("usuario_creado", f"{username} ({role})", user=current, ip=request.remote_addr)
    return jsonify({"ok": True, "user_id": user_id})


@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@auth.role_required("administrator")
def api_users_update(user_id):
    target = auth.get_user_by_id(user_id)
    if not target:
        abort(404)
    current = auth.current_user()
    # Nadie puede editar a alguien con privilegio igual o mayor al propio,
    # salvo el propio Owner editandose a si mismo.
    if target["id"] != current["id"] and not auth.role_at_least(current["role"], target["role"]):
        return jsonify({"ok": False, "error": "permiso_denegado"}), 403

    data = request.get_json(force=True, silent=True) or {}
    fields = {}
    for key in ("full_name", "email", "language", "password"):
        if key in data and data[key]:
            fields[key] = data[key]
    if "active" in data:
        fields["active"] = int(bool(data["active"]))
    if "role" in data and data["role"]:
        new_role = data["role"]
        if new_role not in auth.ROLES or new_role == "owner":
            return jsonify({"ok": False, "error": "rol_invalido"}), 400
        if not auth.role_at_least(current["role"], new_role):
            return jsonify({"ok": False, "error": "no_puedes_asignar_ese_rol"}), 403
        fields["role"] = new_role

    auth.update_user(user_id, **fields)
    auth.log_activity("usuario_editado", target["username"], user=current, ip=request.remote_addr)
    return jsonify({"ok": True})


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@auth.role_required("administrator")
def api_users_delete(user_id):
    target = auth.get_user_by_id(user_id)
    if not target:
        abort(404)
    current = auth.current_user()
    if target["role"] == "owner":
        return jsonify({"ok": False, "error": "no_se_puede_eliminar_al_propietario"}), 403
    if not auth.role_at_least(current["role"], target["role"]):
        return jsonify({"ok": False, "error": "permiso_denegado"}), 403
    auth.delete_user(user_id)
    auth.log_activity("usuario_eliminado", target["username"], user=current, ip=request.remote_addr)
    return jsonify({"ok": True})


@app.route("/api/admin/media/<int:file_id>/set-free", methods=["POST"])
@api_login_required(role="admin")
def api_media_set_free(file_id):
    """Marca un archivo como gratis o de pago individualmente (spec
    seccion 21/28): funciona incluso si el servidor esta en modo
    comercial -- ese archivo en concreto se descargara sin cobro."""
    if not db.get_media_file(file_id):
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    db.set_media_free(file_id, bool(data.get("is_free")))
    return jsonify({"ok": True})


@app.route("/api/admin/categories")
@auth.role_required("manager")
def api_categories_list():
    return jsonify({"categories": db.list_categories()})


@app.route("/api/admin/users/<int:user_id>/permissions", methods=["GET"])
@auth.role_required("manager")
def api_user_permissions_get(user_id):
    return jsonify({"permissions": auth.get_folder_permissions(user_id)})


@app.route("/api/admin/users/<int:user_id>/permissions", methods=["POST"])
@auth.role_required("administrator")
def api_user_permissions_set(user_id):
    data = request.get_json(force=True, silent=True) or {}
    category = (data.get("category") or "").strip()
    if not category:
        return jsonify({"ok": False, "error": "categoria_requerida"}), 400
    auth.set_folder_permissions(
        user_id, category,
        can_view=data.get("can_view", 1), can_download=data.get("can_download", 1),
        can_upload=data.get("can_upload", 0), can_delete=data.get("can_delete", 0),
    )
    return jsonify({"ok": True})


@app.route("/api/admin/activity-log")
@auth.role_required("administrator")
def api_activity_log():
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT 200").fetchall()
        return jsonify({"log": [dict(r) for r in rows]})
    finally:
        conn.close()





# ---------------------------------------------------------------------------
# API - Biblioteca (cliente)
# ---------------------------------------------------------------------------

def _filter_by_permission(files, action="view"):
    """Aplica los permisos por carpeta/categoria del usuario actual (spec
    seccion 24). Los roles staff (owner/administrator/manager) siempre ven
    todo. Para user/guest, se filtra en backend -- nunca dependiendo de que
    el frontend oculte tarjetas."""
    if session.get("role") in STAFF_ROLES:
        return files
    user = auth.current_user()
    if not user:
        return files
    return [f for f in files if auth.can_access_category(user, f.get("category", "General"), action)]


@app.route("/api/library")
@api_login_required()
def api_library():
    price_per_gb, rounding_mode = current_price_settings()
    files = db.list_media_files(only_visible=True)
    files = _filter_by_permission(files, action="view")
    for f in files:
        f["size_gb"], f["price"] = pricing.compute_price(f["size_bytes"], price_per_gb, rounding_mode)
        if f.get("is_free"):
            f["price"] = 0
        f["has_cover"] = bool(f.get("image_path"))
    return jsonify({"files": files, "price_per_gb": price_per_gb, "rounding_mode": rounding_mode})


@app.route("/api/search")
@api_login_required()
def api_search():
    """Buscador del cliente (Mejora 11/12): SOLO contenido publicado.
    El filtro 'visible=1' lo aplica db.search_media_files() dentro de la
    consulta SQL — el backend nunca entrega filas ocultas, sin depender de
    que el frontend las filtre despues. Ademas se aplican los permisos por
    carpeta/categoria del usuario (spec seccion 24)."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"files": []})
    price_per_gb, rounding_mode = current_price_settings()
    files = db.search_media_files(q, only_visible=True)
    files = _filter_by_permission(files, action="view")
    for f in files:
        f["size_gb"], f["price"] = pricing.compute_price(f["size_bytes"], price_per_gb, rounding_mode)
        if f.get("is_free"):
            f["price"] = 0
        f["has_cover"] = bool(f.get("image_path"))
    return jsonify({"files": files, "query": q})


@app.route("/api/admin/search")
@api_login_required(role="admin")
def api_admin_search():
    """Buscador del administrador (Mejora 10/12): sobre TODO lo detectado
    y registrado, publicado o no. Consulta real contra SQLite, no una
    lista pre-cargada filtrada en el navegador."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"files": []})
    price_per_gb, rounding_mode = current_price_settings()
    files = db.search_media_files(q, only_visible=False)
    for f in files:
        f["size_gb"], f["price"] = pricing.compute_price(f["size_bytes"], price_per_gb, rounding_mode)
        f["has_cover"] = bool(f.get("image_path"))
    return jsonify({"files": files, "query": q})


@app.route("/api/thumbnail/<int:file_id>")
@api_login_required()
def api_thumbnail(file_id):
    media = db.get_media_file(file_id)
    if not media or not media.get("image_path"):
        abort(404)
    # Aplica la misma proteccion de visibilidad/permisos que /api/library:
    # un cliente no deberia poder ver la caratula de un archivo que no
    # deberia ver (staff siempre puede, para poder administrar).
    if session.get("role") not in STAFF_ROLES:
        if not media.get("visible"):
            abort(404)
        user = auth.current_user()
        if user and not auth.can_access_category(user, media.get("category", "General"), "view"):
            abort(403)
    path = media["image_path"]
    if not os.path.isfile(path):
        abort(404)
    return send_file(path)


@app.route("/api/requests", methods=["POST"])
@api_login_required()
def api_create_request():
    data = request.get_json(force=True, silent=True) or {}
    file_ids = data.get("file_ids") or []
    file_ids = [int(i) for i in file_ids]
    files = db.get_media_files_by_ids(file_ids)
    visible_files = [f for f in files if f["visible"]]
    # Proteccion en backend (spec seccion 24): aunque el cliente manipule el
    # request y pida IDs de archivos que nunca vio en su listado, se
    # descartan aqui los que su cuenta no tiene permiso de descargar.
    visible_files = _filter_by_permission(visible_files, action="download")
    if not visible_files:
        return jsonify({"ok": False, "error": "No hay archivos validos seleccionados."}), 400

    price_per_gb, rounding_mode = current_price_settings()
    # Contenido gratis/de pago POR ARCHIVO (spec seccion 21/28): un archivo
    # marcado is_free=1 nunca genera cobro, aunque el resto de la
    # biblioteca este en modo comercial. El precio solo se calcula sobre
    # los archivos que SI son de pago dentro de la seleccion.
    paid_files = [f for f in visible_files if not f.get("is_free")]
    total_size = sum(f["size_bytes"] for f in visible_files)
    paid_size = sum(f["size_bytes"] for f in paid_files)
    total_gb_display, _ = pricing.compute_price(total_size, price_per_gb, rounding_mode)
    _, total_price = pricing.compute_price(paid_size, price_per_gb, rounding_mode)

    # Modo gratuito (spec seccion 20), o seleccion donde TODO lo elegido es
    # gratis (aunque el servidor este en modo comercial): la solicitud se
    # crea directamente aprobada, sin pasar por pago/verificacion.
    # IMPORTANTE: esto se decide por si HAY archivos de pago en la seleccion
    # (paid_files), NUNCA por si el precio calculado redondeo a 0 -- un
    # archivo de pago con un tamaño pequeño o un price_per_gb bajo puede dar
    # total_price=0 sin que eso signifique que deba entregarse gratis.
    distribution_mode = db.get_setting("distribution_mode", "free")
    if distribution_mode == "free" or not paid_files:
        req_id = db.create_request(
            client_label=session.get("username", "invitado"),
            client_uid=session.get("client_uid"),
            file_ids=[f["id"] for f in visible_files],
            total_size_bytes=total_size,
            total_price=0,
            payment_method="gratuito",
            verification_message=None,
            auto_approve=True,
        )
        auth.log_activity("descarga_gratuita_autorizada", f"{len(visible_files)} archivo(s)",
                           user=auth.current_user(), ip=request.remote_addr)
        return jsonify({"ok": True, "request_id": req_id, "total_price": 0,
                        "total_gb": total_gb_display, "status": "approved", "payment_method": "gratuito",
                        "free_mode": True})

    payment_method = data.get("payment_method", "transferencia")
    if payment_method not in ("transferencia", "efectivo"):
        return jsonify({"ok": False, "error": "Método de pago no válido."}), 400

    verification_message = (data.get("verification_message") or "").strip() or None
    if payment_method == "transferencia" and not verification_message:
        # Correccion de seguridad: sin este mensaje, la solicitud NUNCA se crea.
        # Antes se creaba igual y quedaba "pendiente" aprobable sin verificar nada.
        return jsonify({
            "ok": False,
            "error": "Debes completar la verificación del pago (pega el mensaje que recibiste "
                     "tras la transferencia) antes de enviar la solicitud.",
        }), 400

    req_id = db.create_request(
        client_label=session.get("username", "invitado"),
        client_uid=session.get("client_uid"),
        file_ids=[f["id"] for f in visible_files],
        total_size_bytes=total_size,
        total_price=total_price,
        payment_method=payment_method,
        verification_message=verification_message,
    )
    return jsonify({"ok": True, "request_id": req_id, "total_price": total_price,
                    "total_gb": total_gb_display, "status": "pending", "payment_method": payment_method})


def _request_belongs_to_session(req):
    """El administrador puede ver cualquier solicitud; un invitado solo la
    suya. Se compara por 'client_uid' (identificador único de la sesión),
    NUNCA por el nombre de dispositivo mostrado (client_label) — ese nombre
    puede repetirse entre invitados distintos (ej. dos teléfonos "Android"),
    así que ya no es seguro usarlo para permisos."""
    if session.get("role") in STAFF_ROLES:
        return True
    req_uid = req.get("client_uid")
    if req_uid:
        return req_uid == session.get("client_uid")
    # Solicitudes antiguas (creadas antes de existir client_uid): se
    # mantiene la comparación por etiqueta como respaldo, para no romper
    # el acceso a datos ya existentes.
    return req.get("client_label") == session.get("username")


@app.route("/api/requests/<int:request_id>")
@api_login_required()
def api_request_status(request_id):
    req = db.get_request(request_id)
    if not req:
        return jsonify({"error": "No encontrada"}), 404
    if not _request_belongs_to_session(req):
        abort(403)
    progress = db.get_progress_for_request(request_id)
    req["progress"] = {str(fid): progress[fid] for fid in progress}
    return jsonify(req)


@app.route("/api/my-requests")
@api_login_required()
def api_my_requests():
    reqs = db.list_requests(status=None, client_label=session.get("username"), client_uid=session.get("client_uid"))
    for r in reqs:
        r["file_ids"] = json.loads(r["file_ids"])
        # Progreso real persistido (SQLite) por archivo, para poder mostrar
        # "EN CURSO ~20%" y distinguir una solicitud completada (que ya no
        # debe ofrecer descarga) de una recien aprobada (Cambio 1/2/3).
        progress = db.get_progress_for_request(r["id"])
        r["progress"] = {str(fid): progress[fid] for fid in progress}
    return jsonify({"requests": reqs})


@app.route("/api/payment-info")
@api_login_required()
def api_payment_info():
    """Datos de cobro configurables por el administrador (spec seccion 21):
    sin ningun metodo de pago especifico de un pais incrustado por defecto.
    account_number, payment_method_label e payment_instructions se editan
    desde Ajustes > Cobro. qr_image solo se devuelve si el administrador
    subio uno (el archivo 'QR de tarjeta.jpg' heredado de Freeman se
    conserva en disco pero ya no se sirve automaticamente a menos que se
    configure explicitamente, para no asumir un metodo de pago concreto)."""
    account_number = db.get_setting("account_number", "")
    method_label = db.get_setting("payment_method_label", "Transferencia bancaria")
    instructions = db.get_setting("payment_instructions", "")
    currency_symbol = db.get_setting("currency_symbol", "$")
    currency_code = db.get_setting("currency_code", "USD")
    accepts_cash = db.get_setting("payment_accepts_cash", "1") == "1"

    qr_filename = db.get_setting("payment_qr_filename", "")
    qr_image = None
    if qr_filename:
        qr_path = os.path.join(BASE_DIR, "frontend", "static", "img", qr_filename)
        if os.path.isfile(qr_path):
            qr_image = url_for("static", filename=f"img/{qr_filename}")

    default_message = f"He realizado el pago mediante {method_label}."
    if account_number:
        default_message += f" Cuenta/referencia: {account_number}."

    return jsonify({
        "account_number": account_number,
        "account_message": instructions or default_message,
        "qr_image": qr_image,
        "method_label": method_label,
        "currency_symbol": currency_symbol,
        "currency_code": currency_code,
        "accepts_cash": accepts_cash,
    })


@app.route("/api/requests/<int:request_id>/verification", methods=["POST"])
@api_login_required()
def api_submit_verification(request_id):
    req = db.get_request(request_id)
    if not req:
        return jsonify({"ok": False, "error": "Solicitud no encontrada."}), 404
    if not _request_belongs_to_session(req):
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "Pega el mensaje de verificación recibido."}), 400
    db.set_verification_message(request_id, message)
    return jsonify({"ok": True, "payment_status": "verificacion_enviada"})


# ---------------------------------------------------------------------------
# API - Administracion
# ---------------------------------------------------------------------------

@app.route("/api/admin/library")
@api_login_required(role="admin")
def api_admin_library():
    price_per_gb, rounding_mode = current_price_settings()
    files = db.list_media_files(only_visible=False)
    for f in files:
        f["size_gb"], f["price"] = pricing.compute_price(f["size_bytes"], price_per_gb, rounding_mode)
        f["has_cover"] = bool(f.get("image_path"))
    return jsonify({"files": files})


@app.route("/api/admin/settings", methods=["GET"])
@api_login_required(role="admin")
def api_get_admin_settings():
    return jsonify({"settings": db.get_settings()})


@app.route("/api/admin/settings", methods=["POST"])
@api_login_required(role="admin")
def api_set_admin_settings():
    data = request.get_json(force=True, silent=True) or {}
    allowed_keys = {
        "price_per_gb", "rounding_mode", "account_number", "service_name",
        "business_name", "distribution_mode", "currency_code", "currency_symbol",
        "payment_method_label", "payment_instructions", "payment_accepts_cash",
        "default_language", "guest_open_login",
    }
    for key, value in data.items():
        if key in allowed_keys:
            db.set_setting(key, value)
    if "service_name" in data:
        db.set_setting("server_name", data["service_name"])
    auth.log_activity("configuracion_actualizada", ", ".join(data.keys()),
                       user=auth.current_user(), ip=request.remote_addr)
    return jsonify({"ok": True, "settings": db.get_settings()})


@app.route("/api/admin/locations", methods=["GET"])
@api_login_required(role="admin")
def api_list_locations():
    return jsonify({"locations": db.list_locations()})


@app.route("/api/admin/locations", methods=["POST"])
@api_login_required(role="admin")
def api_add_location():
    data = request.get_json(force=True, silent=True) or {}
    path = (data.get("path") or "").strip()
    label = (data.get("label") or path).strip()
    scan_mode = data.get("scan_mode") or "tower"
    chosen_subfolders = data.get("chosen_subfolders") or []

    if not path or not os.path.isdir(path):
        return jsonify({"ok": False, "error": "La ruta indicada no existe o no es una carpeta."}), 400

    loc_id = db.add_location(path, label, scan_mode, chosen_subfolders)
    return jsonify({"ok": True, "location_id": loc_id})


@app.route("/api/admin/locations/<int:location_id>", methods=["DELETE"])
@api_login_required(role="admin")
def api_delete_location(location_id):
    db.clear_media_for_location(location_id)
    db.delete_location(location_id)
    return jsonify({"ok": True})


@app.route("/api/admin/browse")
@api_login_required(role="admin")
def api_browse():
    path = request.args.get("path", "").strip()
    if not path:
        drives = scanner.list_windows_drives()
        if drives:
            return jsonify({"path": "", "items": drives, "is_root": True})
        # Android/Termux: ofrecer accesos directos al almacenamiento del dispositivo
        android_roots = [p for p in ("/storage/emulated/0", "/sdcard") if os.path.isdir(p)]
        if android_roots:
            return jsonify({"path": "", "items": android_roots, "is_root": True})
        # Sistemas tipo POSIX genéricos
        return jsonify({"path": "", "items": ["/"], "is_root": True})

    if not os.path.isdir(path):
        return jsonify({"error": "Ruta invalida"}), 400

    subfolders = scanner.list_subfolders(path)
    parent = os.path.dirname(path.rstrip("/\\")) or ""
    return jsonify({"path": path, "items": subfolders, "parent": parent, "is_root": False})


@app.route("/api/admin/browse-full")
@api_login_required(role="admin")
def api_browse_full():
    """Version ampliada del explorador: devuelve carpetas Y archivos
    multimedia (con tipo/tamaño), para el nuevo selector estilo Emby que
    permite marcar con casilla y agregar todo de una vez a la biblioteca.
    Es un endpoint independiente de /api/admin/browse para no afectar el
    selector de carpetas que ya existía."""
    path = request.args.get("path", "").strip()
    if not path:
        drives = scanner.list_windows_drives()
        if not drives:
            drives = ["/"]
        items = []
        for d in drives:
            usage = scanner.get_disk_usage(d)

            if d == "/storage/emulated/0":
                label = "📱 Memoria interna"
            elif d.startswith("/storage/") and os.path.basename(d) != "emulated":
                label = "💾 SD Card"
            elif os.name == "nt":
                label = "💽 Unidad " + d[:1]
            else:
                label = "💽 Almacenamiento"

            items.append({
                "name": d,
                "label": label,
                "type": "dir",
                "disk_usage": usage
            })

        return jsonify({"path": "", "items": items, "is_root": True})

    if not os.path.isdir(path):
        return jsonify({"error": "Ruta invalida"}), 400

    items = scanner.list_dir_entries(path)
    parent = os.path.dirname(path.rstrip("/\\")) or ""
    return jsonify({"path": path, "items": items, "parent": parent, "is_root": False})


@app.route("/api/admin/live-thumbnail")
@api_login_required(role="admin")
def api_live_thumbnail():
    """Sirve una imagen directamente desde el disco del servidor para el
    explorador (Mejora 5): carátulas reales de archivos que todavía NO están
    en la biblioteca (por eso no se puede usar /api/thumbnail/<id>).
    Solo el administrador puede pedir esto, y solo se sirve si la ruta es
    realmente un archivo de imagen soportado (para no convertir esto en un
    lector de archivos arbitrario)."""
    path = request.args.get("path", "").strip()
    if not path or not os.path.isfile(path):
        abort(404)
    ext = os.path.splitext(path)[1].lower()
    if ext not in scanner.IMAGE_EXTENSIONS:
        abort(403)
    return send_file(path)


@app.route("/api/admin/folder-size")
@api_login_required(role="admin")
def api_folder_size():
    """Tamaño de una carpeta, calculado con un límite de tiempo/cantidad de
    archivos (Mejora 6) para no congelar la interfaz si la carpeta tiene
    miles de archivos. Se pide "a demanda" (un botón por carpeta), no
    automáticamente al listar, precisamente por eso."""
    path = request.args.get("path", "").strip()
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Ruta invalida"}), 400
    total, partial, count = scanner.estimate_folder_size(path)
    return jsonify({"size_bytes": total, "partial": partial, "files_counted": count})


def find_location_by_path(path, scan_mode):
    """Busca si ya existe una ubicación con esa ruta exacta y ese modo,
    para reutilizarla en vez de crear una duplicada (actualización
    incremental: agregar contenido, nunca reemplazar)."""
    for loc in db.list_locations():
        if loc["path"] == path and loc["scan_mode"] == scan_mode:
            return loc
    return None


@app.route("/api/admin/add-selection", methods=["POST"])
@api_login_required(role="admin")
def api_add_selection():
    """Registra de una vez todo lo que el administrador marcó con casilla en
    el explorador (carpetas completas y/o archivos sueltos, sin escribir
    ninguna ruta a mano). Cada carpeta marcada se vuelve su propia ubicación
    (escaneo completo); los archivos sueltos marcados se agrupan por su
    carpeta contenedora en una ubicación de tipo 'files'.

    Si la carpeta (o el grupo de archivos de esa carpeta) ya estaba
    registrada anteriormente, se REUTILIZA esa misma ubicación y solo se
    agregan los archivos nuevos — nunca se borra ni se reemplaza lo que ya
    existía en la biblioteca."""
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    if not items:
        return jsonify({"ok": False, "error": "No se marcó ningún elemento."}), 400

    locations_created = 0
    locations_updated = 0
    total_new = 0
    files_by_parent = {}

    def scan_and_insert_new(loc_id, location_row):
        found = scanner.scan_location(location_row)
        already = db.get_filepaths_for_location(loc_id)
        new_items = [it for it in found if it["filepath"] not in already]
        for item in new_items:
            db.insert_media_file(
                location_id=loc_id, filename=item["filename"], filepath=item["filepath"],
                category=item["category"], subfolder=item.get("subfolder", ""),
                extension=item["extension"], size_bytes=item["size_bytes"], image_path=item["image_path"],
                visible=True,  # Mejora 1: se agrega desde el explorador -> publicado de inmediato
                content_kind=scanner.detect_content_kind(item["extension"]),
            )
        db.touch_location_scan(loc_id)
        return len(new_items)

    for it in items:
        p = (it.get("path") or "").strip()
        kind = it.get("type")
        if not p:
            continue
        if kind == "dir":
            if not os.path.isdir(p):
                continue
            existing = find_location_by_path(p, "tower")
            if existing:
                total_new += scan_and_insert_new(existing["id"], existing)
                locations_updated += 1
            else:
                label = os.path.basename(p.rstrip("/\\")) or p
                loc_id = db.add_location(p, label, "tower")
                total_new += scan_and_insert_new(loc_id, db.get_location(loc_id))
                locations_created += 1
        elif kind == "file":
            if not os.path.isfile(p):
                continue
            parent = os.path.dirname(p)
            files_by_parent.setdefault(parent, []).append(p)

    for parent, file_paths in files_by_parent.items():
        existing = find_location_by_path(parent, "files")
        if existing:
            # Se fusionan los archivos nuevos con los ya guardados antes para
            # esta misma carpeta, sin perder ninguno de los anteriores.
            import json as _json
            prev_files = set(_json.loads(existing.get("selected_files") or "[]"))
            merged = list(prev_files | set(file_paths))
            db.update_location_selected_files(existing["id"], merged)
            total_new += scan_and_insert_new(existing["id"], db.get_location(existing["id"]))
            locations_updated += 1
        else:
            label = (os.path.basename(parent.rstrip("/\\")) or parent) + " (archivos)"
            loc_id = db.add_location(parent, label, "files", selected_files=file_paths)
            total_new += scan_and_insert_new(loc_id, db.get_location(loc_id))
            locations_created += 1

    return jsonify({
        "ok": True,
        "locations_created": locations_created,
        "locations_updated": locations_updated,
        "files_found": total_new,
    })


@app.route("/api/admin/scan/<int:location_id>", methods=["POST"])
@api_login_required(role="admin")
def api_scan_location(location_id):
    """Escaneo INCREMENTAL: nunca borra ni reinicia lo que ya existe en esta
    ubicación (eso destruiría las decisiones de visibilidad ya tomadas por
    el administrador). Solo agrega los archivos que sean realmente nuevos
    en el disco; los que ya estaban registrados se conservan tal cual,
    publicados u ocultos, sin duplicarse (comparación exacta por filepath).
    Los archivos NUEVOS quedan publicados automáticamente (Mejora 1): esta
    ubicación ya fue elegida antes por el administrador a través del
    explorador, así que su contenido nuevo no debería requerir un paso
    manual adicional."""
    location = db.get_location(location_id)
    if not location:
        return jsonify({"ok": False, "error": "Ubicacion no encontrada"}), 404

    found = scanner.scan_location(location)
    already_registered = db.get_filepaths_for_location(location_id)
    new_items = [item for item in found if item["filepath"] not in already_registered]

    for item in new_items:
        db.insert_media_file(
            location_id=location_id,
            filename=item["filename"],
            filepath=item["filepath"],
            category=item["category"],
            subfolder=item.get("subfolder", ""),
            extension=item["extension"],
            size_bytes=item["size_bytes"],
            image_path=item["image_path"],
            visible=True,
            content_kind=scanner.detect_content_kind(item["extension"]),
        )
    db.touch_location_scan(location_id)
    return jsonify({"ok": True, "found": len(found), "new": len(new_items)})


@app.route("/api/admin/visibility", methods=["POST"])
@api_login_required(role="admin")
def api_set_visibility():
    data = request.get_json(force=True, silent=True) or {}
    file_id = data.get("file_id")
    file_ids = data.get("file_ids")
    visible = bool(data.get("visible"))

    if file_ids:
        db.set_visibility_bulk([int(i) for i in file_ids], visible)
    elif file_id is not None:
        db.set_visibility(int(file_id), visible)
    else:
        return jsonify({"ok": False, "error": "Falta file_id o file_ids"}), 400

    return jsonify({"ok": True})


HISTORY_CLEANUP_HOURS = 24  # Cambio 7: una solicitud completada sale del
# historial del administrador 24h despues de completarse. NO borra la fila
# de la base de datos -- solo deja de incluirse en este listado -- y nunca
# afecta solicitudes pendientes, aprobadas (en curso) o rechazadas.


@app.route("/api/admin/requests")
@api_login_required(role="admin")
def api_admin_requests():
    status = request.args.get("status")
    reqs = db.list_requests(status, hide_completed_older_than_hours=HISTORY_CLEANUP_HOURS)
    for r in reqs:
        r["file_ids"] = json.loads(r["file_ids"])
    return jsonify({"requests": reqs})


@app.route("/api/admin/requests/<int:request_id>/approve", methods=["POST"])
@api_login_required(role="admin")
def api_approve_request(request_id):
    req = db.get_request(request_id)
    if not req:
        return jsonify({"ok": False, "error": "Solicitud no encontrada."}), 404
    # Refuerzo de seguridad (ver Módulo 5): si es pago por transferencia/QR,
    # jamás se puede aprobar sin un mensaje de verificación real. Con el flujo
    # actual esto ya no debería poder ocurrir (la solicitud no se crea sin
    # mensaje), pero se deja esta comprobación como última barrera.
    if req["payment_method"] == "transferencia" and not req.get("verification_message"):
        return jsonify({
            "ok": False,
            "error": "No se puede aprobar: falta la verificación de pago de esta solicitud.",
        }), 400
    db.update_request_status(request_id, "approved")
    return jsonify({"ok": True})


@app.route("/api/admin/requests/<int:request_id>/reject", methods=["POST"])
@api_login_required(role="admin")
def api_reject_request(request_id):
    db.update_request_status(request_id, "rejected")
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# API - Descargas (con progreso)
# ---------------------------------------------------------------------------

@app.route("/api/download/<int:request_id>/<int:file_id>")
@api_login_required()
def api_download_file(request_id, file_id):
    """Sirve un archivo de una solicitud ya aprobada, en streaming por
    fragmentos, CON SOPORTE DE HTTP RANGE (RFC 7233). Esto es lo que hace
    posible una reanudación real: si la descarga se interrumpe habiendo
    recibido, por ejemplo, los primeros 700 MB, el cliente puede volver a
    pedir el archivo con la cabecera 'Range: bytes=700000000-' y este
    endpoint retoma exactamente desde ahí, sin reenviar lo ya recibido.

    Tambien alimenta 'LIVE_TRANSFERS' para el panel de administrador, igual
    que antes, ahora contando el progreso real acumulado (incluyendo lo que
    ya se habia transferido en intentos anteriores)."""
    req = db.get_request(request_id)
    if not req or req["status"] != "approved":
        abort(403)
    if not _request_belongs_to_session(req):
        abort(403)
    allowed_ids = set(json.loads(req["file_ids"]))
    if file_id not in allowed_ids:
        abort(403)
    media = db.get_media_file(file_id)
    if not media or not os.path.isfile(media["filepath"]):
        abort(404)

    filepath = media["filepath"]
    filename = media["filename"]
    total_bytes = os.path.getsize(filepath)
    client_label = req.get("client_label", "invitado")
    client_uid_for_progress = req.get("client_uid") or session.get("client_uid")
    transfer_id = str(uuid.uuid4())

    # --- Analizar cabecera Range (si el cliente esta pidiendo reanudar) ---
    range_header = request.headers.get("Range", "")
    start = 0
    end = total_bytes - 1
    is_partial = False
    if range_header.startswith("bytes="):
        try:
            range_spec = range_header.split("=", 1)[1]
            start_s, _, end_s = range_spec.partition("-")
            if start_s:
                start = int(start_s)
            if end_s:
                end = min(int(end_s), total_bytes - 1)
            if start < 0 or start > end or start >= total_bytes:
                return Response(status=416, headers={"Content-Range": f"bytes */{total_bytes}"})
            is_partial = True
        except ValueError:
            start, end, is_partial = 0, total_bytes - 1, False

    length = end - start + 1
    _start_transfer(transfer_id, client_label, request_id, filename, total_bytes, initial_offset=start)

    def generate():
        sent = start
        try:
            with open(filepath, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    sent += len(chunk)
                    _update_transfer(transfer_id, sent)
                    yield chunk
            _finish_transfer(transfer_id, "finalizado")
            if sent >= total_bytes:
                # Progreso persistente en SQLite (no en RAM): al llegar al
                # final real del archivo, se marca 'completado'. Si con esto
                # TODOS los archivos de la solicitud ya estan completos, la
                # solicitud entera pasa a status='completed' y deja de
                # aparecer como descarga disponible (Cambio 1/2), sin borrar
                # el registro (sigue como historial).
                db.upsert_download_progress(request_id, file_id, client_uid_for_progress, total_bytes, total_bytes, "completado")
                db.mark_request_completed_if_all_done(request_id)
        except (BrokenPipeError, ConnectionResetError):
            _finish_transfer(transfer_id, "interrumpido")
            db.upsert_download_progress(request_id, file_id, client_uid_for_progress, sent, total_bytes, "pausado")
        except Exception:
            _finish_transfer(transfer_id, "error")
            raise

    headers = {
        "Content-Length": str(length),
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Accept-Ranges": "bytes",
    }
    status = 200
    if is_partial:
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total_bytes}"

    return Response(stream_with_context(generate()), status=status,
                     mimetype="application/octet-stream", headers=headers)


def _user_has_approved_access(file_id):
    """True si la sesion actual ya tiene una solicitud aprobada que incluye
    este archivo (mismo criterio de seguridad que la descarga)."""
    client_uid = session.get("client_uid")
    if not client_uid:
        return False
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT file_ids FROM download_requests WHERE status = 'approved' AND client_uid = ?",
            (client_uid,),
        ).fetchall()
        for r in rows:
            if file_id in json.loads(r["file_ids"]):
                return True
        return False
    finally:
        conn.close()


@app.route("/api/preview/<int:file_id>")
@api_login_required()
def api_preview_file(file_id):
    """Reproduccion/visualizacion EN NAVEGADOR (spec: no obligar a
    descargar contenido que el navegador puede reproducir/mostrar
    directamente): video, audio, imagenes y PDF se sirven inline con
    soporte de HTTP Range (para que el reproductor de video/audio pueda
    saltar a cualquier punto sin descargar el archivo completo).

    Autorizacion: requiere permiso de VER la categoria del archivo, y
    ademas que el contenido sea accesible sin pago pendiente -- staff,
    modo gratuito, archivo marcado como gratis, o una solicitud ya
    aprobada que lo incluya. Igual que la descarga: nunca por saber la
    URL/ID a secas."""
    media = db.get_media_file(file_id)
    if not media or not media.get("visible") or not os.path.isfile(media["filepath"]):
        abort(404)

    kind = media.get("content_kind", "other")
    if kind not in ("video", "audio", "image", "pdf"):
        abort(404)  # tipos no reproducibles en navegador: solo descarga

    is_staff = session.get("role") in STAFF_ROLES
    if not is_staff:
        user = auth.current_user()
        if user and not auth.can_access_category(user, media.get("category", "General"), "view"):
            abort(403)
        distribution_mode = db.get_setting("distribution_mode", "free")
        authorized = (distribution_mode == "free" or media.get("is_free") or
                      _user_has_approved_access(file_id))
        if not authorized:
            abort(403)

    filepath = media["filepath"]
    total_bytes = os.path.getsize(filepath)
    mime = {
        "video": mimetypes.guess_type(filepath)[0] or "video/mp4",
        "audio": mimetypes.guess_type(filepath)[0] or "audio/mpeg",
        "image": mimetypes.guess_type(filepath)[0] or "image/jpeg",
        "pdf": "application/pdf",
    }[kind]

    range_header = request.headers.get("Range", "")
    start, end = 0, total_bytes - 1
    is_partial = False
    if range_header.startswith("bytes="):
        try:
            range_spec = range_header.split("=", 1)[1]
            start_s, _, end_s = range_spec.partition("-")
            if start_s:
                start = int(start_s)
            if end_s:
                end = min(int(end_s), total_bytes - 1)
            if start < 0 or start > end or start >= total_bytes:
                return Response(status=416, headers={"Content-Range": f"bytes */{total_bytes}"})
            is_partial = True
        except ValueError:
            start, end, is_partial = 0, total_bytes - 1, False

    length = end - start + 1

    def generate():
        with open(filepath, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {"Content-Length": str(length), "Accept-Ranges": "bytes"}
    status = 200
    if is_partial:
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total_bytes}"
    return Response(stream_with_context(generate()), status=status, mimetype=mime, headers=headers)


@app.route("/api/download-progress", methods=["POST"])
@api_login_required()
def api_download_progress():
    """Checkpoint de progreso real, enviado periodicamente por el cliente
    (y al pausar/cancelar) mientras descarga. Se guarda en SQLite -- no en
    RAM ni en la sesion -- para que 'Mis solicitudes' pueda mostrar
    'EN CURSO ~20%' y ofrecer continuar, incluso si el invitado cierra
    sesion o el servidor se reinicia entretanto (Cambio 3/4)."""
    data = request.get_json(force=True, silent=True) or {}
    request_id = data.get("request_id")
    file_id = data.get("file_id")
    received_bytes = data.get("received_bytes")
    total_bytes = data.get("total_bytes")
    status = data.get("status")
    if not request_id or not file_id or status not in ("descargando", "pausado", "completado"):
        return jsonify({"ok": False, "error": "Datos de progreso invalidos."}), 400

    req = db.get_request(int(request_id))
    if not req or not _request_belongs_to_session(req):
        abort(403)

    client_uid = req.get("client_uid") or session.get("client_uid")
    db.upsert_download_progress(
        int(request_id), int(file_id), client_uid,
        int(received_bytes or 0), int(total_bytes or 0), status,
    )
    if status == "completado":
        db.mark_request_completed_if_all_done(int(request_id))
    return jsonify({"ok": True})


@app.route("/api/admin/downloads/live")
@api_login_required(role="admin")
def api_admin_downloads_live():
    """Lista de transferencias activas en este momento, para la pestaña
    'Descargas' del panel de administrador."""
    with LIVE_LOCK:
        transfers = []
        for t in LIVE_TRANSFERS.values():
            pct = round((t["bytes_sent"] / t["total_bytes"]) * 100) if t["total_bytes"] else 0
            transfers.append({**t, "pct": min(100, pct)})
        transfers.sort(key=lambda t: t["started_at"], reverse=True)
    return jsonify({"transfers": transfers})


@app.route("/api/ping")
@api_login_required()
def api_ping():
    """Latido periódico del cliente, para que el admin vea quién sigue
    conectado en la pestaña 'Usuarios' (ver api_login_required, que ya
    actualiza last_seen en cada llamada autenticada)."""
    return jsonify({"ok": True})


@app.route("/api/admin/users/live")
@api_login_required(role="admin")
def api_admin_users_live():
    """Clientes conectados en este momento: nombre asignado (Invitado 1,
    Invitado 2...) e IP de su teléfono/laptop."""
    return jsonify({"clients": _live_clients()})


# ---------------------------------------------------------------------------
# API - Red (IP local, puerta de enlace, sincronizacion con Promo)
# ---------------------------------------------------------------------------

@app.route("/api/network-info")
@api_login_required(role="admin")
def api_network_info_v2():
    """Endpoint principal de deteccion de red de QBASwing MyServer (spec
    seccion 9). Nunca depende de una IP fija: se recalcula en cada llamada,
    asi que si el servidor cambia de red (router distinto, reinicio, DHCP)
    la respuesta se actualiza sola."""
    ip = network.get_local_ip()
    gateway = network.get_gateway()
    access_url = f"http://{ip}:{SERVER_PORT}"
    return jsonify({
        "server_active": True,
        "ip": ip,
        "port": SERVER_PORT,
        "gateway": gateway,
        "access_url": access_url,
        "interface": "LAN/WiFi",
    })


@app.route("/api/network/qr.png")
@api_login_required(role="admin")
def api_network_qr():
    """Genera el codigo QR de acceso LAN como imagen PNG, apuntando siempre
    a la IP actual del servidor (nunca una IP fija). Requiere la libreria
    opcional 'qrcode' (con soporte PIL) instalada -- ver requirements.txt.
    Si no esta instalada, responde 501 para que el frontend muestre la URL
    en texto en su lugar, en vez de romper la pagina."""
    try:
        import qrcode
        import io
    except ImportError:
        return jsonify({"error": "qrcode_no_instalado",
                         "hint": "pip install qrcode[pil]"}), 501

    ip = network.get_local_ip()
    url = f"http://{ip}:{SERVER_PORT}"
    img = qrcode.make(url, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ---------------------------------------------------------------------------
# API - Backup y restauracion (spec seccion 28)
# ---------------------------------------------------------------------------

@app.route("/api/admin/upload-payment-qr", methods=["POST"])
@api_login_required(role="admin")
def api_upload_payment_qr():
    """Permite al administrador subir su propio código QR de pago (spec
    seccion 21/22): ya no se asume ningún QR fijo por defecto."""
    uploaded = request.files.get("qr_file")
    if not uploaded or not uploaded.filename:
        return jsonify({"ok": False, "error": "archivo_requerido"}), 400

    # El QR es una subida pequeña y conserva su limite propio.
    uploaded.stream.seek(0, os.SEEK_END)
    qr_size = uploaded.stream.tell()
    uploaded.stream.seek(0)
    if qr_size > 20 * 1024 * 1024:
        return jsonify({"ok": False, "error": "archivo_demasiado_grande"}), 413
    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        return jsonify({"ok": False, "error": "formato_no_soportado"}), 400

    filename = "payment-qr" + ext
    dest = os.path.join(BASE_DIR, "frontend", "static", "img", filename)
    uploaded.save(dest)
    db.set_setting("payment_qr_filename", filename)
    auth.log_activity("qr_pago_actualizado", filename, user=auth.current_user(), ip=request.remote_addr)
    return jsonify({"ok": True, "filename": filename})



@app.route("/api/admin/import-files", methods=["POST"])
@api_login_required(role="admin")
def api_admin_import_files():
    """Importa archivos enviados por el selector nativo del dispositivo."""
    files = request.files.getlist("files")
    if not files:
        return jsonify({"ok": False, "error": "No se recibieron archivos."}), 400

    from werkzeug.utils import secure_filename
    from uuid import uuid4

    import_root = os.path.join(BASE_DIR, "library_imports")
    batch_dir = os.path.join(import_root, uuid4().hex)
    os.makedirs(batch_dir, exist_ok=True)

    saved = 0
    skipped = 0
    total_bytes = 0

    def safe_relative_path(name):
        name = (name or "").replace("\\", "/")
        parts = []
        for part in name.split("/"):
            clean = secure_filename(part)
            if clean and clean not in (".", ".."):
                parts.append(clean)
        return parts

    for uploaded in files:
        original = uploaded.filename or ""
        parts = safe_relative_path(original)
        if not parts:
            skipped += 1
            continue

        filename = parts[-1]
        if not scanner.is_publishable_file(filename):
            skipped += 1
            continue

        relative_dirs = parts[:-1]
        target_dir = os.path.join(batch_dir, *relative_dirs)
        os.makedirs(target_dir, exist_ok=True)

        target = os.path.join(target_dir, filename)

        if os.path.exists(target):
            stem, ext = os.path.splitext(filename)
            n = 2
            while True:
                candidate = os.path.join(target_dir, f"{stem} ({n}){ext}")
                if not os.path.exists(candidate):
                    target = candidate
                    break
                n += 1

        uploaded.save(target)
        try:
            total_bytes += os.path.getsize(target)
        except OSError:
            pass
        saved += 1

    if saved == 0:
        shutil.rmtree(batch_dir, ignore_errors=True)
        return jsonify({
            "ok": False,
            "error": "No se encontró ningún archivo publicable."
        }), 400

    label = "Importación " + os.path.basename(batch_dir)
    loc_id = db.add_location(batch_dir, label, "tower")
    location = db.get_location(loc_id)

    found = scanner.scan_location(location)
    already = db.get_filepaths_for_location(loc_id)
    new_items = [it for it in found if it["filepath"] not in already]

    for item in new_items:
        db.insert_media_file(
            location_id=loc_id,
            filename=item["filename"],
            filepath=item["filepath"],
            category=item["category"],
            subfolder=item.get("subfolder", ""),
            extension=item["extension"],
            size_bytes=item["size_bytes"],
            image_path=item["image_path"],
            visible=True,
            content_kind=scanner.detect_content_kind(item["extension"]),
        )

    db.touch_location_scan(loc_id)

    return jsonify({
        "ok": True,
        "files_received": len(files),
        "files_saved": saved,
        "files_skipped": skipped,
        "files_published": len(new_items),
        "bytes_saved": total_bytes,
        "location_id": loc_id,
    })


@app.route("/api/admin/backup")
@auth.role_required("administrator")
def api_backup():
    """Genera una copia de seguridad descargable con la base de datos
    completa (usuarios, roles, permisos, configuracion, catalogo de
    contenido). No incluye los archivos multimedia en si -- esos se quedan
    donde ya estan en el disco; el backup solo cubre lo que representa
    trabajo de configuracion dificil de rehacer a mano."""
    if not os.path.isfile(db.DB_PATH):
        return jsonify({"ok": False, "error": "sin_base_de_datos"}), 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db.DB_PATH, arcname="qbaswing_myserver.db")
        manifest = {
            "product": "QBASwing MyServer",
            "backup_created_at": datetime.now().isoformat(timespec="seconds"),
            "server_name": db.get_setting("server_name", "QBASwing MyServer"),
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    buf.seek(0)

    auth.log_activity("backup_generado", user=auth.current_user(), ip=request.remote_addr)
    filename = f"qbaswing-myserver-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=filename)


@app.route("/api/admin/restore", methods=["POST"])
@auth.role_required("owner")
def api_restore():
    """Restaura una copia de seguridad generada por /api/admin/backup.
    Accion destructiva: reemplaza la base de datos actual. Solo el Owner
    puede ejecutarla. Antes de sobrescribir, guarda automaticamente la base
    de datos actual como .bak por si algo sale mal."""
    uploaded = request.files.get("backup_file")
    if not uploaded:
        return jsonify({"ok": False, "error": "archivo_requerido"}), 400

    tmp_path = db.DB_PATH + ".restore_tmp"
    try:
        with zipfile.ZipFile(uploaded.stream) as zf:
            names = zf.namelist()
            db_entry = next((n for n in names if n.endswith(".db")), None)
            if not db_entry:
                return jsonify({"ok": False, "error": "backup_invalido"}), 400
            with zf.open(db_entry) as src, open(tmp_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
    except zipfile.BadZipFile:
        return jsonify({"ok": False, "error": "archivo_no_es_zip"}), 400

    # Validar que el archivo restaurado es realmente una base de datos
    # SQLite compatible antes de reemplazar la actual.
    try:
        test_conn = sqlite3.connect(tmp_path)
        test_conn.execute("SELECT COUNT(*) FROM users")
        test_conn.close()
    except sqlite3.Error:
        os.remove(tmp_path)
        return jsonify({"ok": False, "error": "base_de_datos_no_compatible"}), 400

    backup_of_current = db.DB_PATH + f".bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if os.path.isfile(db.DB_PATH):
        shutil.copy2(db.DB_PATH, backup_of_current)
    shutil.move(tmp_path, db.DB_PATH)

    session.clear()  # las sesiones activas ya no son validas contra la BD restaurada
    return jsonify({"ok": True, "previous_db_saved_as": os.path.basename(backup_of_current)})


# ---------------------------------------------------------------------------
# Modulo de Patrocinio y Donaciones (100% local, SQLite, sin nube)
# ---------------------------------------------------------------------------
# Pagina publica (sin login, accesible para cualquier visitante en la red
# local) para registrarse como patrocinador o dejar una donacion. El pago
# real ocurre FUERA del servidor (billetera cripto, QvaPay o WhatsApp del
# propietario) -- aqui solo se guarda el registro para que el propietario lo
# verifique y confirme manualmente desde el panel de administracion, igual
# que ya se hace con las solicitudes de descarga.


QVAPAY_API_BASE = os.environ.get("QVAPAY_API_BASE", "https://api.qvapay.com").rstrip("/")
QVAPAY_APP_ID = os.environ.get("QVAPAY_APP_ID", "").strip()
QVAPAY_APP_SECRET = os.environ.get("QVAPAY_APP_SECRET", "").strip()
QVAPAY_WEBHOOK_URL = os.environ.get(
    "QVAPAY_WEBHOOK_URL",
    "https://sborbolla.pythonanywhere.com/api/donaciones/qvapay/webhook",
).strip()


def _qvapay_request(path, payload):
    """Realiza una petición JSON autenticada contra la API v2 de QvaPay."""
    import urllib.request
    import urllib.error

    if not QVAPAY_APP_ID or not QVAPAY_APP_SECRET:
        raise RuntimeError("QvaPay no está configurado: faltan QVAPAY_APP_ID/QVAPAY_APP_SECRET")

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        QVAPAY_API_BASE + path,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
            "app-id": QVAPAY_APP_ID,
            "app-secret": QVAPAY_APP_SECRET,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {"error": raw}
        return exc.code, data


def _qvapay_verify_webhook(raw_body):
    """Verifica firma y timestamp del webhook QvaPay."""
    import hashlib
    import hmac

    if not QVAPAY_APP_SECRET:
        return False

    signature = (request.headers.get("x-qvapay-signature") or "").strip()
    timestamp = (request.headers.get("x-qvapay-timestamp") or "").strip()

    if not signature or not timestamp or not signature.startswith("sha256="):
        return False

    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        return False

    if abs(int(time.time()) - timestamp_value) > 300:
        return False

    provided = signature[len("sha256="):]
    expected = hmac.new(
        QVAPAY_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(provided, expected)


def _qvapay_create_invoice(donation_id, amount, description):
    """Crea una factura QvaPay asociada a una donación existente."""
    remote_id = f"qba-donation-{donation_id}-{uuid.uuid4().hex}"

    status_code, data = _qvapay_request(
        "/v2/create_invoice",
        {
            "amount": float(amount),
            "description": description[:255],
            "remote_id": remote_id,
            "webhook": QVAPAY_WEBHOOK_URL,
        },
    )

    if status_code != 200:
        raise RuntimeError(
            f"QvaPay devolvió HTTP {status_code}: {json.dumps(data, ensure_ascii=False)}"
        )

    transaction_uuid = data.get("transaction_uuid")
    payment_url = data.get("url")

    if not transaction_uuid or not payment_url:
        raise RuntimeError("Respuesta de QvaPay sin transaction_uuid o url")

    conn = db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO qvapay_payments
            (donation_id, transaction_uuid, remote_id, amount, currency,
             status, payment_url, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                donation_id,
                transaction_uuid,
                remote_id,
                float(amount),
                db.get_setting("donation_currency", "USD"),
                payment_url,
                db.now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "transaction_uuid": transaction_uuid,
        "remote_id": remote_id,
        "payment_url": payment_url,
    }


@app.route("/api/donaciones/qvapay/create", methods=["POST"])
def api_create_qvapay_invoice():
    data = request.get_json(force=True, silent=True) or {}

    donor_name = (data.get("donor_name") or "").strip() or "Anónimo"
    contact = (data.get("contact") or "").strip()
    message = (data.get("message") or "").strip()
    currency = (data.get("currency") or db.get_setting("donation_currency", "USD")).strip()

    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "monto_invalido"}), 400

    if amount <= 0:
        return jsonify({"ok": False, "error": "monto_invalido"}), 400

    if currency.upper() != "USD":
        return jsonify({
            "ok": False,
            "error": "qvapay_requiere_usd",
            "message": "Las facturas QvaPay de esta integración se crean en USD.",
        }), 400

    if not QVAPAY_APP_ID or not QVAPAY_APP_SECRET:
        return jsonify({
            "ok": False,
            "error": "qvapay_no_configurado",
        }), 503

    donation_id = db.add_donation(
        donor_name,
        contact,
        amount,
        currency,
        "qvapay",
        message,
    )

    try:
        invoice = _qvapay_create_invoice(
            donation_id,
            amount,
            f"Donación QBASwing - {donor_name}",
        )
    except Exception as exc:
        db.update_donation_status(donation_id, "rechazada")
        auth.log_activity(
            "qvapay_error",
            f"Donación {donation_id}: {exc}",
            ip=request.remote_addr,
        )
        return jsonify({
            "ok": False,
            "error": "qvapay_invoice_error",
        }), 502

    auth.log_activity(
        "qvapay_factura_creada",
        f"Donación {donation_id}: {invoice['transaction_uuid']}",
        ip=request.remote_addr,
    )

    return jsonify({
        "ok": True,
        "donation_id": donation_id,
        "transaction_uuid": invoice["transaction_uuid"],
        "payment_url": invoice["payment_url"],
    })


@app.route("/api/donaciones/qvapay/webhook", methods=["POST"])
def api_qvapay_webhook():
    raw_body = request.get_data(cache=True)

    if not _qvapay_verify_webhook(raw_body):
        return jsonify({"ok": False, "error": "firma_invalida"}), 401

    data = request.get_json(silent=True) or {}

    transaction_uuid = (data.get("transaction_uuid") or data.get("uuid") or "").strip()
    remote_id = (data.get("remote_id") or "").strip()
    status = (data.get("status") or "").strip().lower()

    if not transaction_uuid and not remote_id:
        return jsonify({"ok": False, "error": "identificador_faltante"}), 400

    conn = db.get_connection()

    try:
        if transaction_uuid:
            row = conn.execute(
                "SELECT * FROM qvapay_payments WHERE transaction_uuid = ?",
                (transaction_uuid,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM qvapay_payments WHERE remote_id = ?",
                (remote_id,),
            ).fetchone()

        if not row:
            return jsonify({"ok": False, "error": "pago_no_encontrado"}), 404

        payment = dict(row)

        if payment["status"] == "paid":
            return jsonify({"ok": True, "already_processed": True})

        if status != "paid":
            conn.execute(
                "UPDATE qvapay_payments SET status = ?, updated_at = ? WHERE id = ?",
                (status or "unknown", db.now(), payment["id"]),
            )
            conn.commit()
            return jsonify({"ok": True, "processed": False})

        conn.execute(
            """
            UPDATE qvapay_payments
            SET status = 'paid', updated_at = ?
            WHERE id = ?
            """,
            (db.now(), payment["id"]),
        )

        conn.execute(
            """
            UPDATE donations
            SET status = 'confirmada', updated_at = ?
            WHERE id = ? AND status != 'confirmada'
            """,
            (db.now(), payment["donation_id"]),
        )

        conn.commit()

    finally:
        conn.close()

    auth.log_activity(
        "qvapay_pago_confirmado",
        f"Donación {payment['donation_id']}: {transaction_uuid or remote_id}",
        ip=request.remote_addr,
    )

    return jsonify({"ok": True, "confirmed": True})


DONATION_METHODS = ("crypto", "usdt", "pyusd", "tropipay", "qvapay", "whatsapp")
SPONSOR_LEVELS = ("bronce", "plata", "oro", "personalizado")


def _donation_settings():
    keys = ("donation_goal_label", "donation_goal_amount", "donation_currency",
            "donation_intro_text", "donation_crypto_info", "donation_qvapay_info",
            "donation_whatsapp", "donation_module_enabled")
    values = {k: db.get_setting(k, "") for k in keys}
    totals = db.donation_totals()
    currency = values.get("donation_currency") or "USD"
    try:
        goal = float(values.get("donation_goal_amount") or 0)
    except ValueError:
        goal = 0
    raised = float(totals["by_currency"].get(currency, 0) or 0)
    values["donation_goal_amount"] = goal
    values["raised_amount"] = raised
    values["raised_percent"] = min(100, round((raised / goal) * 100)) if goal > 0 else 0
    values["approved_sponsors"] = totals["approved_sponsors"]
    return values


@app.route("/patrocinadores")
def public_sponsors():
    sponsors = []
    try:
        conn = db.get_connection()
        try:
            rows = conn.execute("SELECT * FROM sponsors").fetchall()
            sponsors = [dict(row) for row in rows]
        finally:
            conn.close()
    except Exception:
        sponsors = []
    return render_template("sponsors.html", sponsors=sponsors)

@app.route("/donaciones")
def donations_page():
    settings = _donation_settings()
    if settings.get("donation_module_enabled", "1") == "0":
        return _error_page(404, "No disponible", "El módulo de patrocinio y donaciones no está activo en este momento.")
    return render_template("donations.html", settings=settings)


@app.route("/api/donaciones/info")
def api_donations_info():
    return jsonify({"ok": True, "settings": _donation_settings()})


@app.route("/api/donaciones/patrocinador", methods=["POST"])
def api_create_sponsor():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    level = (data.get("level") or "bronce").strip()
    message = (data.get("message") or "").strip()

    if not name:
        return jsonify({"ok": False, "error": "nombre_requerido"}), 400
    if level not in SPONSOR_LEVELS:
        level = "bronce"

    sponsor_id = db.add_sponsor(name, email, phone, level, message)
    auth.log_activity("patrocinador_registrado", f"{name} ({level})", ip=request.remote_addr)
    return jsonify({"ok": True, "id": sponsor_id})


@app.route("/api/donaciones", methods=["POST"])
def api_create_donation():
    data = request.get_json(force=True, silent=True) or {}
    donor_name = (data.get("donor_name") or "").strip() or "Anónimo"
    contact = (data.get("contact") or "").strip()
    method = (data.get("method") or "whatsapp").strip()
    message = (data.get("message") or "").strip()
    currency = (data.get("currency") or db.get_setting("donation_currency", "USD")).strip()

    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount < 0:
        amount = 0
    if method not in DONATION_METHODS:
        method = "whatsapp"

    donation_id = db.add_donation(donor_name, contact, amount, currency, method, message)
    auth.log_activity("donacion_registrada", f"{donor_name}: {amount} {currency} via {method}", ip=request.remote_addr)
    return jsonify({"ok": True, "id": donation_id})


# --- Administracion del modulo ----------------------------------------------

@app.route("/api/admin/patrocinadores", methods=["GET"])
@auth.role_required("manager")
def api_admin_list_sponsors():
    return jsonify({"ok": True, "sponsors": db.list_sponsors()})


@app.route("/api/admin/patrocinadores/<int:sponsor_id>", methods=["PUT"])
@auth.role_required("manager")
def api_admin_update_sponsor(sponsor_id):
    data = request.get_json(force=True, silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in ("pendiente", "aprobado", "rechazado"):
        return jsonify({"ok": False, "error": "estado_invalido"}), 400
    db.update_sponsor_status(sponsor_id, status)
    return jsonify({"ok": True})


@app.route("/api/admin/patrocinadores/<int:sponsor_id>", methods=["DELETE"])
@auth.role_required("manager")
def api_admin_delete_sponsor(sponsor_id):
    db.delete_sponsor(sponsor_id)
    return jsonify({"ok": True})


@app.route("/api/admin/donaciones", methods=["GET"])
@auth.role_required("manager")
def api_admin_list_donations():
    return jsonify({"ok": True, "donations": db.list_donations(), "totals": db.donation_totals()})


@app.route("/api/admin/donaciones/<int:donation_id>", methods=["PUT"])
@auth.role_required("manager")
def api_admin_update_donation(donation_id):
    data = request.get_json(force=True, silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in ("pendiente", "confirmada", "rechazada"):
        return jsonify({"ok": False, "error": "estado_invalido"}), 400
    db.update_donation_status(donation_id, status)
    return jsonify({"ok": True})


@app.route("/api/admin/donaciones/<int:donation_id>", methods=["DELETE"])
@auth.role_required("manager")
def api_admin_delete_donation(donation_id):
    db.delete_donation(donation_id)
    return jsonify({"ok": True})


@app.route("/api/admin/donaciones/settings", methods=["POST"])
@auth.role_required("manager")
def api_admin_save_donation_settings():
    data = request.get_json(force=True, silent=True) or {}
    allowed = ("donation_goal_label", "donation_goal_amount", "donation_currency",
               "donation_intro_text", "donation_crypto_info", "donation_qvapay_info",
               "donation_whatsapp", "donation_module_enabled")
    for key in allowed:
        if key in data:
            db.set_setting(key, data[key])
    return jsonify({"ok": True})


@app.route("/api/network-info-public")
def api_public_network_info():
    """Version PUBLICA (sin login) de la IP local del servidor. No expone
    nada sensible: es la misma IP de red local que cualquier dispositivo ya
    ve al conectarse. CORS abierto por si se integra con una pantalla de
    bienvenida servida aparte."""
    ip = network.get_local_ip()
    resp = jsonify({
        "ip": ip,
        "port": SERVER_PORT,
        "access_url": f"http://{ip}:{SERVER_PORT}",
    })
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Manejo de errores (spec seccion 39): nunca mostrar trazas de Python al
# usuario final. Las peticiones a /api/* reciben JSON; el resto, una pagina
# simple con la identidad de QBASwing MyServer. Los detalles tecnicos van al
# log de la consola (Flask ya lo hace por defecto), nunca a la respuesta.
# ---------------------------------------------------------------------------

def _wants_json():
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def _error_page(code, title, message):
    if _wants_json():
        return jsonify({"ok": False, "error": title, "message": message}), code
    return render_template("error.html", code=code, title=title, message=message), code


@app.errorhandler(401)
def handle_401(e):
    return _error_page(401, "No autenticado", "Necesitas iniciar sesión para acceder a esto.")


@app.errorhandler(403)
def handle_403(e):
    return _error_page(403, "Acceso no autorizado", "Tu cuenta no tiene permiso para acceder a esto.")


@app.errorhandler(404)
def handle_404(e):
    return _error_page(404, "No encontrado", "Lo que buscas no existe o fue movido.")


@app.errorhandler(409)
def handle_409(e):
    return _error_page(409, "Conflicto", "Esta operación entra en conflicto con el estado actual.")


@app.errorhandler(413)
def handle_413(e):
    return _error_page(413, "Archivo demasiado grande", "El archivo enviado supera el límite permitido.")


@app.errorhandler(500)
def handle_500(e):
    return _error_page(500, "Error del servidor", "Ocurrió un problema inesperado. Intenta de nuevo en unos segundos.")


if __name__ == "__main__":
    db.init_db()
    print("=" * 60)
    print("  QBASwing MyServer")
    print("  Un producto de QBASwing Designer")
    print('  "Tu servidor digital privado"')
    print("=" * 60)
    local_ip = network.get_local_ip()
    gateway_ip = network.get_gateway()
    print(f"  Servidor iniciado en: http://localhost:{SERVER_PORT}")
    print(f"  Direccion en tu red WiFi: http://{local_ip}:{SERVER_PORT}")
    if gateway_ip:
        print(f"  Puerta de enlace (router): {gateway_ip}")
    if not auth.is_initialized():
        print("  Primera instalacion: abre la URL de arriba para completar el asistente de configuracion.")
    else:
        print("  Inicia sesion con tu cuenta de usuario (Owner/Administrator/Manager/User/Guest).")

    server_display_name = db.get_setting("business_name", "") or db.get_setting("server_name", "")
    mdns_label = "QBASwing MyServer" if not server_display_name else f"QBASwing MyServer ({server_display_name})"
    if discovery.start_announcer(mdns_label, local_ip, SERVER_PORT):
        print(f"  Descubrimiento en red (mDNS) activo como '{mdns_label}'.")
    else:
        print("  Descubrimiento automatico en red no disponible (opcional: pip install zeroconf).")
        print("  El acceso por IP/QR manual funciona igual, sin depender de esto.")
    print("=" * 60)

    # Al ejecutarse como .exe (PyInstaller define sys.frozen), abrimos el
    # navegador automaticamente.
    if getattr(sys, "frozen", False):
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{SERVER_PORT}")).start()
    # debug=False y use_reloader=False son intencionales: la base de datos SQLite
    # vive dentro de la carpeta del proyecto, y el recargador automático de Flask
    # reiniciaría el servidor cada vez que se escribe en ella.
    app.run(host="0.0.0.0", port=SERVER_PORT, debug=False, use_reloader=False, threaded=True)


# QBASWING_DONATIONS_COMPAT_V1
# Compatibilidad de configuración para el módulo público de Donaciones.
def _qbaswing_donation_public_settings():
    import sqlite3
    from pathlib import Path

    db = Path("database/qbaswing_myserver.db")
    result = {}

    if db.exists():
        con = sqlite3.connect(str(db))
        try:
            rows = con.execute(
                "SELECT key,value FROM settings WHERE key LIKE 'donation_%' "
                "OR key LIKE 'payment_%'"
            ).fetchall()
            for k,v in rows:
                result[k] = v or ""
        finally:
            con.close()

    return result
