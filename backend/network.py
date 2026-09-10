"""
QBASwing MyServer - utilidades de red

Detecta la IP local del servidor y la puerta de enlace del router (mejor
esfuerzo, sin dependencias externas). Nunca usa una IP fija: cada llamada
recalcula la direccion real de la interfaz de red activa, para que el
servidor siga funcionando aunque cambie de router o de red.
"""
import os
import socket
import subprocess

# Deteccion automatica de la IP local del Hub. Antes se probo con una IP
# fija (192.168.1.5), pero eso rompe la red apenas la PC tiene otra IP real
# (cambia de red, DHCP reasigna, etc.): Freeman anunciaba una direccion que
# no era la de la PC, y el celular no podia conectarse a nada ahi. Se
# vuelve al metodo automatico: abre un socket UDP hacia una IP publica sin
# enviar datos, solo para que el sistema operativo elija la interfaz de
# salida real (la misma que usa la PC en su red WiFi/LAN), y lee esa IP.
# 'localhost' sigue funcionando aparte (Flask escucha en 0.0.0.0).
def get_local_ip():
    """Devuelve la IP local real de la PC en la red (la que usarian los
    clientes -celular u otra PC- para conectarse). No necesita internet:
    solo abre un socket UDP hacia una IP publica sin enviar datos, para que
    el sistema operativo elija la interfaz de salida correcta.

    Si por algun motivo se obtiene una IP de auto-configuracion invalida
    (169.254.x.x, cuando la interfaz aun no tiene IP real asignada por el
    router), se intenta un segundo metodo antes de rendirse."""
    def _is_valid(ip):
        return bool(ip) and not ip.startswith("169.254.") and ip != "0.0.0.0"

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ip = None
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = None
    finally:
        s.close()

    if not _is_valid(ip):
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = None

    return ip if _is_valid(ip) else "127.0.0.1"


def get_gateway():
    """Intenta detectar la puerta de enlace (IP del router). Mejor esfuerzo:
    si no se puede determinar, devuelve None en vez de fallar."""
    try:
        if os.name == "nt":
            out = subprocess.check_output(["ipconfig"], text=True, errors="ignore", timeout=3)
            for line in out.splitlines():
                if "Puerta de enlace" in line or "Default Gateway" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        candidate = parts[-1].strip()
                        if candidate and candidate not in ("", "0.0.0.0"):
                            return candidate
        else:
            # Linux / Termux / Android
            try:
                out = subprocess.check_output(["ip", "route"], text=True, errors="ignore", timeout=3)
                for line in out.splitlines():
                    if line.startswith("default"):
                        parts = line.split()
                        if "via" in parts:
                            return parts[parts.index("via") + 1]
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass
            # Fallback: leer /proc/net/route (no requiere binarios externos)
            try:
                with open("/proc/net/route") as f:
                    for line in f.readlines()[1:]:
                        fields = line.strip().split()
                        if len(fields) >= 3 and fields[1] == "00000000":
                            gw_hex = fields[2]
                            gw = socket.inet_ntoa(bytes.fromhex(gw_hex)[::-1])
                            return gw
            except (FileNotFoundError, OSError, ValueError):
                pass
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        pass
    return None
