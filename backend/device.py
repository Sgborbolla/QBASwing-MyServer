"""
QBASwing MyServer - identificacion de dispositivos conectados

Un navegador normal NUNCA entrega el nombre personalizado que alguien le
puso a su telefono ("El Redmi de Sergio"). Lo unico que tenemos de forma
fiable es la cabecera User-Agent (fabricante/modelo/SO cuando el propio
navegador decide incluirlo) y, en raras ocasiones, resolucion inversa de
DNS/hostname si el router la soporta. Por eso esto trabaja por NIVELES,
de mas a menos especifico, y nunca finge saber algo que no sabe.
"""
import re
import socket

# Nivel 1: modelos de Android conocidos que SI suelen aparecer literalmente
# en el User-Agent (ej. "SM-A125F", "Redmi 9C", "Pixel 6"). Esta lista es
# necesariamente incompleta -- cubre los fabricantes/gamas mas comunes.
_SAMSUNG_MODELS = {
    "SM-A125": "Samsung Galaxy A12", "SM-A135": "Samsung Galaxy A13",
    "SM-A155": "Samsung Galaxy A15", "SM-A225": "Samsung Galaxy A22",
    "SM-A325": "Samsung Galaxy A32", "SM-A525": "Samsung Galaxy A52",
    "SM-A536": "Samsung Galaxy A53", "SM-S911": "Samsung Galaxy S23",
    "SM-S916": "Samsung Galaxy S23+", "SM-G991": "Samsung Galaxy S21",
    "SM-N986": "Samsung Galaxy Note20 Ultra",
}


def _match_samsung(model_token):
    for prefix, name in _SAMSUNG_MODELS.items():
        if model_token.startswith(prefix):
            return name
    return None


def _browser_name(ua):
    # El orden importa: varios navegadores incluyen "Chrome" o "Safari" en
    # su propio User-Agent aunque no lo sean.
    if "EdgA" in ua or "Edg/" in ua:
        return "Edge"
    if "SamsungBrowser" in ua:
        return "Samsung Internet"
    if "OPR/" in ua or "Opera" in ua:
        return "Opera"
    if "Firefox" in ua:
        return "Firefox"
    if "CriOS" in ua or ("Chrome" in ua and "Safari" in ua):
        return "Chrome"
    if "Safari" in ua:
        return "Safari"
    return None


def parse_device_label(user_agent):
    """Devuelve una etiqueta legible del dispositivo a partir del
    User-Agent, probando niveles de detalle decrecientes. Nunca devuelve
    "Invitado N" -- eso se maneja aparte, solo como respaldo final."""
    ua = user_agent or ""
    browser = _browser_name(ua)

    # --- iPhone / iPad -----------------------------------------------
    if "iPhone" in ua:
        return "iPhone" + (f" · {browser}" if browser else "")
    if "iPad" in ua:
        return "iPad" + (f" · {browser}" if browser else "")

    # --- Android: intentar extraer el modelo real (Nivel 1) ----------
    android_match = re.search(r"Android\s[\d.]+;\s*([^)]+?)\s*(?:Build/[^)]*)?\)", ua)
    if android_match:
        model_token = android_match.group(1).strip().strip(";").strip()
        # A veces el campo trae idioma/region en vez de modelo (ej. "es-us");
        # se descarta si no parece un modelo real.
        if model_token and not re.match(r"^[a-z]{2}-[a-z]{2}$", model_token, re.IGNORECASE):
            friendly = _match_samsung(model_token)
            if friendly:
                return friendly  # Nivel 1: modelo conocido con nombre amigable
            if re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", model_token):
                return model_token  # Nivel 1(b): modelo crudo tal cual lo reporta el equipo (ej. "Redmi 9C")
        # Nivel 2: no se pudo extraer un modelo util, pero se sabe que es Android
        manufacturer = None
        for brand in ("Xiaomi", "Redmi", "Samsung", "Huawei", "Motorola", "Realme", "OPPO", "Vivo", "OnePlus", "Lenovo", "ZTE"):
            if brand.lower() in ua.lower():
                manufacturer = brand
                break
        if manufacturer:
            return f"{manufacturer} · Android"
        return "Android" + (f" · {browser}" if browser else "")

    # --- Escritorio ----------------------------------------------------
    if "Windows" in ua:
        return "Windows" + (f" · {browser}" if browser else "")
    if "Macintosh" in ua:
        return "Mac" + (f" · {browser}" if browser else "")
    if "Linux" in ua:
        return "Linux" + (f" · {browser}" if browser else "")

    return None  # Nivel 4: no se pudo determinar nada (se resuelve afuera)


def try_reverse_dns(ip, timeout=0.6):
    """Nivel 3: intenta resolver el hostname del dispositivo por DNS
    inverso. En redes domesticas esto casi nunca funciona (la mayoria de
    routers no registran esa informacion por cliente), asi que se trata
    como un dato adicional opcional, nunca como algo garantizado, y con un
    timeout corto para no colgar la respuesta al cliente."""
    if not ip or ip in ("127.0.0.1", "::1"):
        return None
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        hostname, _, _ = socket.gethostbyaddr(ip)
        # Los routers domesticos suelen devolver algo como "192-168-1-25"
        # o el propio texto de la IP -- eso no es informacion util.
        if hostname and hostname.replace(".", "").replace("-", "") != ip.replace(".", ""):
            return hostname.split(".")[0]
    except (socket.herror, socket.gaierror, socket.timeout, OSError):
        pass
    finally:
        socket.setdefaulttimeout(old_timeout)
    return None


def identify_device(user_agent, ip):
    """Combina los niveles de deteccion disponibles. Devuelve un dict:
    {label, os_family} para mostrar en el panel de Usuarios conectados."""
    ua = user_agent or ""
    label = parse_device_label(ua)
    hostname = try_reverse_dns(ip)

    os_family = "Desconocido"
    if "iPhone" in ua or "iPad" in ua or "iOS" in ua:
        os_family = "iOS"
    elif "Android" in ua:
        os_family = "Android"
    elif "Windows" in ua:
        os_family = "Windows"
    elif "Macintosh" in ua:
        os_family = "macOS"
    elif "Linux" in ua:
        os_family = "Linux"

    if not label:
        # Nivel 4: nombre generico honesto, nunca "Invitado N" aqui.
        label = "Dispositivo desconocido"

    # El hostname (Nivel 3), cuando esta disponible, es la pista mas humana
    # que existe (ej. "Sergio-Laptop") y se antepone si se logro obtener.
    if hostname:
        label = hostname

    return {"label": label, "os_family": os_family, "hostname": hostname}
