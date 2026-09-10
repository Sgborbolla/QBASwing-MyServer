# QBASwing MyServer

**Un producto de QBASwing Designer** — *"Tu servidor digital privado"*

Servidor digital privado para pequeños y medianos negocios, pensado para
funcionar dentro de la red local (WiFi/LAN) del negocio, sin depender de
internet. Permite compartir, organizar, reproducir y descargar vídeos,
audio, documentos, imágenes, libros y archivos en general, con modo
gratuito o comercial (cobro configurable según el país del negocio).

Construido sobre la base técnica de Freeman Media Hub (Flask + SQLite +
HTML/CSS/JS puro, sin frameworks ni CDNs — funciona 100% sin conexión).

---

## Primera instalación

1. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```
   La librería `qrcode[pil]` es **opcional**: si no la instalas, la app
   funciona igual, solo que en vez del código QR de acceso se muestra la
   URL en texto.

2. Arranca el servidor:
   ```bash
   python app.py
   ```

3. Abre en tu navegador la dirección que muestra la consola, por ejemplo:
   ```
   http://localhost:5000
   ```
   Si usas Termux en Android, abre Chrome en el mismo dispositivo y visita
   esa misma dirección.

4. Como es la **primera vez** que se ejecuta, en vez del login aparece el
   **asistente de configuración inicial**: creas tu cuenta (que se
   convierte automáticamente en **Propietario**, con control total),
   defines el nombre del negocio/servidor e idioma. El asistente no vuelve
   a aparecer en los siguientes arranques.

5. A partir de ahí, entras siempre por el login con tu cuenta.

---

## Roles y cuentas

| Rol            | Puede...                                                        |
|----------------|-------------------------------------------------------------------|
| **Owner**      | Control total. Es quien se crea en el asistente inicial.          |
| **Administrator** | Administra según los permisos que el Owner le habilite; crea/edita/elimina cuentas User/Guest/Manager. |
| **Manager**    | Permisos administrativos limitados (ve el panel, no gestiona cuentas). |
| **User**       | Accede al contenido autorizado, según permisos por carpeta.       |
| **Guest**      | Acceso limitado, si el administrador decide usarlo.                |

Las cuentas se gestionan desde el panel de administración, pestaña
**Cuentas**. Todos los permisos se verifican en el backend (nunca solo
ocultando botones en la interfaz).

También existe, de forma opcional y desactivable desde **Ajustes**, el
acceso de **invitado anónimo** (usuario `invitado`, sin contraseña) —
heredado de Freeman Media Hub para negocios que prefieren no crear una
cuenta por cliente.

---

## Red local y acceso por QR

El servidor **nunca depende de una IP fija**: en cada arranque (y en cada
consulta a `/api/network-info`) se detecta la IP real de la interfaz de
red activa. Si el router asigna una IP distinta tras un reinicio, la app
se adapta sola — no hay nada que reconfigurar a mano.

En el panel de administración, pestaña **Resumen**, verás la IP, el
puerto, la URL de acceso y (si instalaste `qrcode[pil]`) un código QR que
cualquier teléfono en la misma red puede escanear para abrir
QBASwing MyServer directamente.

---

## Idiomas

Español, English, Français, Deutsch, Português e Italiano. El selector de
idioma está en la esquina superior derecha del login (🌐), y también se
puede fijar un idioma predeterminado del servidor desde **Ajustes**. Las
traducciones viven en `translations/*.json` — añadir un idioma nuevo es
crear un archivo más con las mismas claves.

---

## Modo gratuito y modo comercial

Desde **Ajustes → Modelo de distribución** el Owner/Administrator elige:

- **Gratuito**: todo el contenido autorizado se descarga sin cobro.
- **Comercial**: se mantiene el flujo de precio → solicitud → pago →
  verificación → aprobación → descarga, pero **sin ningún método de pago
  específico de un país incrustado**. La moneda, el nombre del método de
  cobro (transferencia, efectivo, el que sea) y las instrucciones que ve
  el cliente se configuran libremente en **Ajustes → Cobro**.

Cada solicitud de descarga se guarda con `status`
(pending/approved/rejected) y `payment_status`
(pendiente/verificacion_enviada/aprobado/rechazado). El cliente copia y
pega el comprobante/mensaje que recibió, y el administrador lo compara con
lo que él mismo recibió antes de aprobar o rechazar desde **Solicitudes**.

El precio por GB y el redondeo comercial (sin redondeo / a 5 / a 10)
también se configuran ahí, sin tocar código.

---

## Estructura del proyecto

```
QBASwing-MyServer/
├── app.py                     Aplicación Flask (rutas de vistas + API)
├── requirements.txt
├── qbaswing_myserver.spec     Spec de PyInstaller
├── translations/              es.json, en.json, fr.json, de.json, pt.json, it.json
├── database/
│   └── schema.sql             Esquema SQLite (se crea qbaswing_myserver.db al arrancar)
├── backend/
│   ├── db.py                  Acceso a datos (SQLite)
│   ├── auth.py                Usuarios, roles, permisos, verificación en backend
│   ├── i18n.py                Sistema multilingüe
│   ├── network.py             Detección de IP/gateway (nunca fija)
│   ├── scanner.py             Escaneo de carpetas, detección de categoría/carátula
│   ├── device.py              Identificación de dispositivos conectados
│   └── pricing.py             Cálculo de precios con redondeo comercial
├── frontend/
│   ├── templates/
│   │   ├── setup.html         Asistente de configuración inicial
│   │   ├── login.html
│   │   ├── client.html
│   │   └── admin.html
│   └── static/
│       ├── css/style.css
│       ├── img/logo-qbaswing-*.png   Logo oficial de QBASwing Designer
│       ├── js/common.js, js/i18n.js, js/setup.js, js/login.js, js/client.js, js/admin.js
└── images/                    Coloca aquí imágenes de marca adicionales (ver el .txt dentro)
```

---

## Generar el ejecutable QBASwing MyServer.exe (Windows)

```bat
pip install pyinstaller
pyinstaller qbaswing_myserver.spec
```

El resultado queda en `dist/QBASwing MyServer/QBASwing MyServer.exe`. Al
abrirlo, arranca el servidor local y abre automáticamente el navegador
(en el asistente inicial la primera vez, o en el login después). Debe
distribuirse copiando toda la carpeta `dist/QBASwing MyServer/`, no solo
el `.exe` suelto — ahí van las plantillas, estilos, traducciones y la base
de datos.

Cada instalación (cada negocio) genera su propia base de datos, su propia
clave de sesión (`database/secret.key`) y su propia configuración de red,
usuarios y contenido — el mismo paquete sirve para distintos negocios sin
tocar código.

---

## Notas técnicas

- Backend: Python + Flask. Sesiones firmadas con una clave generada
  automáticamente en el primer arranque (`database/secret.key`), nunca
  escrita en el código fuente.
- Contraseñas: hasheadas con `werkzeug.security` (nunca en texto plano).
- Base de datos: SQLite (`database/qbaswing_myserver.db`), se crea sola.
- Frontend: HTML5 + CSS3 + JavaScript puro, sin frameworks ni CDNs
  (funciona completamente sin internet).
- Las descargas del cliente se sirven solo si la solicitud fue aprobada
  (o si el modo es gratuito), verificado siempre en el servidor.
- El explorador de carpetas del panel de administrador lee el sistema de
  archivos de la propia máquina donde corre `python app.py`.

---

## Pendientes conocidos (siguiente iteración)

- Backup/restauración de configuración+contenido desde el panel.
- Descubrimiento automático en LAN (mDNS/SSDP) — hoy el acceso es por
  IP/QR manual, que ya es estable y no depende de IPs fijas.
- Niveles de licencia (Free/Business/Professional/Enterprise): la
  arquitectura de roles y permisos ya está preparada para limitarse por
  edición en el futuro, pero no hay ninguna restricción activa todavía.
- Subida de un QR de pago propio desde Ajustes (hoy se configura solo
  texto/número de cuenta; la imagen de QR de pago requiere subir el
  archivo manualmente a `frontend/static/img/` y fijar su nombre en
  `payment_qr_filename` — panel de subida pendiente).
