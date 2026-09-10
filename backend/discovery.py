"""
QBASwing MyServer - descubrimiento automatico en la red local (mDNS).

Anuncia el servidor en la LAN via Zeroconf/Bonjour (protocolo estandar,
soportado nativamente por macOS/iOS, y por Android/Windows con apps o
soporte del sistema) para que, en el futuro, un cliente compatible pueda
encontrar "QBASwing MyServer" sin escribir la IP a mano.

Es completamente OPCIONAL: si la libreria 'zeroconf' no esta instalada,
el servidor sigue funcionando exactamente igual, solo que sin anuncio
automatico -- el acceso por IP/QR manual (backend/network.py) sigue
siendo la via principal y nunca depende de esto.
"""
import atexit
import socket

_zeroconf_instance = None
_service_info = None


def start_announcer(server_name, ip, port):
    """Intenta registrar el servicio en la red via mDNS. Devuelve True si
    lo logro, False si la libreria opcional no esta disponible o algo
    fallo (en cuyo caso no se interrumpe el arranque del servidor)."""
    global _zeroconf_instance, _service_info
    try:
        from zeroconf import Zeroconf, ServiceInfo
    except ImportError:
        return False

    try:
        safe_name = "".join(c for c in server_name if c.isalnum() or c in " -_") or "QBASwing MyServer"
        service_type = "_http._tcp.local."
        instance_name = f"{safe_name}._http._tcp.local."

        info = ServiceInfo(
            service_type,
            instance_name,
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties={"product": "QBASwing MyServer", "vendor": "QBASwing Designer"},
            server=f"{safe_name.replace(' ', '-').lower()}.local.",
        )
        zc = Zeroconf()
        zc.register_service(info)
        _zeroconf_instance = zc
        _service_info = info
        atexit.register(stop_announcer)
        return True
    except Exception:
        # Cualquier fallo aqui (permisos, red no compatible, etc.) nunca
        # debe impedir que el servidor principal siga funcionando.
        return False


def stop_announcer():
    global _zeroconf_instance, _service_info
    if _zeroconf_instance and _service_info:
        try:
            _zeroconf_instance.unregister_service(_service_info)
            _zeroconf_instance.close()
        except Exception:
            pass
    _zeroconf_instance = None
    _service_info = None
