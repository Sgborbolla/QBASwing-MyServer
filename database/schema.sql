-- QBASwing MyServer - esquema de base de datos SQLite
-- (Base tecnica heredada de Freeman Media Hub)

-- Usuarios reales del sistema (Owner / Administrator / Manager / User / Guest).
-- Sustituye las credenciales fijas que tenia Freeman Media Hub.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',   -- owner / administrator / manager / user / guest
    language TEXT NOT NULL DEFAULT 'es',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- Permisos de contenido por usuario y carpeta/categoria (para roles User/Guest
-- limitados). Si un usuario con rol administrativo (owner/administrator/
-- manager) no tiene filas aqui, se asume acceso total: los permisos finos
-- solo se usan para restringir a user/guest.
CREATE TABLE IF NOT EXISTS user_folder_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    can_view INTEGER NOT NULL DEFAULT 1,
    can_download INTEGER NOT NULL DEFAULT 1,
    can_upload INTEGER NOT NULL DEFAULT 0,
    can_delete INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, category)
);
CREATE INDEX IF NOT EXISTS idx_permissions_user ON user_folder_permissions(user_id);

-- Registro de actividad (login, usuarios, subidas, descargas, cambios admin).
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    action TEXT NOT NULL,
    details TEXT,
    ip TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at);


CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    label TEXT NOT NULL,
    scan_mode TEXT NOT NULL DEFAULT 'tower',   -- 'tower' (todo recursivo) / 'folder' (subcarpetas elegidas) / 'files' (archivos sueltos elegidos)
    chosen_subfolders TEXT DEFAULT '[]',        -- JSON list, usado si scan_mode = 'folder'
    selected_files TEXT DEFAULT '[]',           -- JSON list de rutas absolutas, usado si scan_mode = 'files'
    added_at TEXT NOT NULL,
    last_scan_at TEXT
);

CREATE TABLE IF NOT EXISTS media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT 'General',
    subfolder TEXT NOT NULL DEFAULT '',         -- ruta relativa dentro de la categoria (ej: "Serie A/Temporada 1")
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    image_path TEXT,                            -- ruta a caratula asociada, si existe
    visible INTEGER NOT NULL DEFAULT 0,          -- publicado (1) u oculto (0)
    is_free INTEGER NOT NULL DEFAULT 0,          -- gratis (1) aunque el resto sea de pago
    content_kind TEXT NOT NULL DEFAULT 'other',  -- video/audio/image/pdf/document/book/archive/software/other
    added_at TEXT NOT NULL,
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS download_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_label TEXT NOT NULL DEFAULT 'invitado',  -- nombre de dispositivo (solo para mostrar; puede repetirse)
    client_uid TEXT,                             -- identificador UNICO de la sesion (permisos/aislamiento real)
    file_ids TEXT NOT NULL,                     -- JSON array de ids de media_files
    total_size_bytes INTEGER NOT NULL DEFAULT 0,
    total_price REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',      -- pending / approved / rejected
    payment_status TEXT NOT NULL DEFAULT 'pendiente', -- pendiente / pendiente_efectivo / verificacion_enviada / aprobado / rechazado
    payment_method TEXT NOT NULL DEFAULT 'transferencia', -- 'transferencia' (QR/cuenta) o 'efectivo'
    verification_code TEXT,                      -- (heredado, sin uso actualmente)
    verification_message TEXT,                   -- texto que el cliente copia y pega tras transferir
    created_at TEXT NOT NULL,
    updated_at TEXT,
    completed_at TEXT                             -- se llena cuando TODOS los archivos de la solicitud terminan de descargarse
);

-- Progreso real de descarga, por archivo, persistido en SQLite (no en RAM
-- ni en la sesion HTTP). Permite que una descarga "en curso" sobreviva a
-- que el invitado cierre sesion o el servidor se reinicie: al volver, se
-- puede saber exactamente cuantos bytes ya se habian recibido de cada
-- archivo, y cuando TODOS los archivos de una solicitud llegan a
-- 'completado', la solicitud completa pasa a status='completed' (ver
-- backend/db.py: mark_request_completed_if_all_done) y deja de aparecer
-- como descarga disponible, sin borrar el registro (queda como historial).
CREATE TABLE IF NOT EXISTS download_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    client_uid TEXT,
    received_bytes INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente / descargando / pausado / completado
    updated_at TEXT NOT NULL,
    UNIQUE(request_id, file_id)
);
CREATE INDEX IF NOT EXISTS idx_progress_request ON download_progress(request_id);

-- Identidad persistente de invitados: en una red local, la MISMA IP se
-- trata como el MISMO invitado (y una IP distinta como un invitado
-- distinto). Esto sobrevive a reinicios del servidor y a que el invitado
-- pierda su cookie de sesion (cierre de navegador, celular reiniciado,
-- etc.), porque al volver a entrar se recupera el mismo client_uid a
-- partir de su IP en vez de generar uno nuevo al azar.
CREATE TABLE IF NOT EXISTS guest_identities (
    ip TEXT PRIMARY KEY,
    client_uid TEXT NOT NULL UNIQUE,
    label TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

-- Configuracion general de la aplicacion (clave/valor)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

INSERT OR IGNORE INTO settings (key, value) VALUES ('price_per_gb', '10');
INSERT OR IGNORE INTO settings (key, value) VALUES ('rounding_mode', 'none');       -- none / round5 / round10
INSERT OR IGNORE INTO settings (key, value) VALUES ('account_number', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('service_name', 'QBASwing MyServer');

-- Identidad / instalacion --------------------------------------------------
INSERT OR IGNORE INTO settings (key, value) VALUES ('initialized', '0');            -- '1' tras completar el asistente inicial
INSERT OR IGNORE INTO settings (key, value) VALUES ('business_name', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('server_name', 'QBASwing MyServer');
INSERT OR IGNORE INTO settings (key, value) VALUES ('default_language', 'es');

-- Modelo de distribucion / cobro internacional -----------------------------
INSERT OR IGNORE INTO settings (key, value) VALUES ('distribution_mode', 'free');   -- free / commercial
INSERT OR IGNORE INTO settings (key, value) VALUES ('currency_code', 'USD');
INSERT OR IGNORE INTO settings (key, value) VALUES ('currency_symbol', '$');
INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_method_label', 'Transferencia bancaria');
INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_instructions', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_accepts_cash', '1');

CREATE INDEX IF NOT EXISTS idx_media_visible ON media_files(visible);
CREATE INDEX IF NOT EXISTS idx_media_category ON media_files(category);
CREATE INDEX IF NOT EXISTS idx_requests_status ON download_requests(status);

-- ---------------------------------------------------------------------------
-- Modulo de Patrocinio y Donaciones (100% local, sin servicios en la nube)
-- ---------------------------------------------------------------------------

-- Registro de patrocinadores (empresas/personas que se ofrecen como
-- patrocinadores del proyecto/servidor, no un pago puntual sino una
-- relacion de patrocinio).
CREATE TABLE IF NOT EXISTS sponsors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL DEFAULT 'bronce',   -- bronce / plata / oro / personalizado
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente / aprobado / rechazado
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sponsors_status ON sponsors(status);

-- Formularios de donacion enviados por clientes/visitantes. El pago en si
-- ocurre FUERA del servidor (billetera cripto, QvaPay o WhatsApp) -- aqui
-- solo se guarda el registro/intencion de donacion para que el propietario
-- lo verifique manualmente, igual que las solicitudes de descarga.
CREATE TABLE IF NOT EXISTS donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_name TEXT NOT NULL DEFAULT 'Anónimo',
    contact TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    method TEXT NOT NULL DEFAULT 'whatsapp',   -- crypto / qvapay / whatsapp
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente / confirmada / rechazada
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_donations_status ON donations(status);


CREATE TABLE IF NOT EXISTS qvapay_payments (
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
);
CREATE INDEX IF NOT EXISTS idx_qvapay_payments_donation_id ON qvapay_payments(donation_id);
CREATE INDEX IF NOT EXISTS idx_qvapay_payments_status ON qvapay_payments(status);

-- Configuracion del modulo de patrocinio/donaciones (meta de recaudacion y
-- datos de contacto/cobro). Todo editable desde el panel de administracion.
INSERT OR IGNORE INTO settings (key, value) VALUES ('donation_goal_label', 'Meta de recaudación');
INSERT OR IGNORE INTO settings (key, value) VALUES ('donation_goal_amount', '0');
INSERT OR IGNORE INTO settings (key, value) VALUES ('donation_currency', 'USD');
INSERT OR IGNORE INTO settings (key, value) VALUES ('donation_intro_text', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('donation_crypto_info', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('donation_qvapay_info', '');
INSERT OR IGNORE INTO settings (key, value) VALUES ('donation_whatsapp', '+53 58147030');
INSERT OR IGNORE INTO settings (key, value) VALUES ('donation_module_enabled', '1');
