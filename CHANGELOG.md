# Changelog — QBASwing MyServer

## QBASwing MyServer 1.0 — Transformación desde Freeman Media Hub

Transformación completa (no un rediseño superficial) sobre la base técnica
real de Freeman Media Hub. Resumen de lo entregado en esta ronda:

### Identidad
- Nuevo nombre en toda la interfaz visible: **QBASwing MyServer**, producto
  de **QBASwing Designer**. Logo oficial integrado (varios tamaños PNG).
  Cero menciones de "Freeman" en interfaz o lógica activa (verificado con
  búsqueda exhaustiva en todo el proyecto).
- Base de datos renombrada (`freeman.db` → `qbaswing_myserver.db`), spec de
  PyInstaller y guía de generación del `.exe` actualizados.
- README y guía de `.exe` reescritos con la nueva identidad y documentación
  real de las funciones nuevas.

### Usuarios y roles (nuevo — no existía en Freeman Media Hub)
- Tabla `users` real con contraseñas hasheadas (`werkzeug.security`),
  reemplazando las credenciales fijas `Freeman/12345678` que vivían en el
  código fuente.
- Cinco roles con jerarquía verificada siempre en backend: Owner >
  Administrator > Manager > User > Guest (`backend/auth.py`:
  `role_required`, `role_at_least`).
- CRUD de cuentas desde el panel (pestaña **Cuentas**): crear, editar rol,
  activar/desactivar, cambiar contraseña, eliminar. Nadie puede crear o
  editar una cuenta con privilegio igual o mayor al propio (salvo el Owner
  sobre sí mismo). El rol Owner nunca se puede asignar manualmente — solo
  existe el creado por el asistente inicial.
- Tabla `user_folder_permissions` + `can_access_category()` para permisos
  finos por categoría (ver/descargar/subir/eliminar) en cuentas User/Guest.
- `activity_log`: registro de login, creación/edición de usuarios, cambios
  de configuración — sin guardar contraseñas ni datos sensibles.
- El acceso de invitado anónimo de Freeman Media Hub (usuario `invitado`,
  sin cuenta) se conservó como opción configurable y desactivable
  (`guest_open_login`), no como comportamiento forzado.

### Primera instalación (nuevo)
- Asistente de configuración inicial (`/setup`, `setup.html` + `setup.js`)
  que solo aparece si el servidor no ha sido inicializado. Crea la cuenta
  Owner, guarda nombre del negocio/servidor e idioma, y marca la
  instalación como completada (`settings.initialized = '1'`). No se puede
  ejecutar dos veces.
- Ya no existe la pantalla "Welcome" antigua de Freeman Media Hub como
  paso obligatorio: tras la primera instalación se entra directo al login.

### Red y acceso (mejorado)
- `backend/network.py` ya detectaba la IP local sin hardcode — se
  conservó y se expuso mejor vía `/api/network-info` (IP, puerto, gateway,
  URL de acceso, recalculado en cada llamada).
- Código QR de acceso LAN nuevo (`/api/network/qr.png`), generado con la
  librería opcional `qrcode[pil]`; si no está instalada, la interfaz
  muestra la URL en texto en vez de romperse.
- Endpoint público `/api/network-info-public` sustituye a la integración
  específica con "Freeman Media Hub Promo" (proyecto hermano eliminado del
  flujo: código muerto de sincronización de `config.json` retirado).

### Multilenguaje (nuevo — no existía en Freeman Media Hub)
- `backend/i18n.py` + `translations/{es,en,fr,de,pt,it}.json`, con las seis
  claves completas y verificadas por script (`assert` de igualdad de
  claves entre idiomas). Aplicado a login, asistente inicial, navegación,
  cuentas y ajustes. Selector de idioma 🌐 en la esquina superior derecha,
  persistente por sesión/cuenta.

### Modo gratuito / comercial internacional (nuevo)
- `settings.distribution_mode` (`free`/`commercial`) configurable desde
  Ajustes. En modo comercial, el flujo precio → solicitud → pago →
  verificación → aprobación se conservó de Freeman Media Hub, pero:
  - Se retiraron las menciones fijas a "Transfermóvil" y "EnZona" del
    HTML, JS y del mensaje de verificación por defecto en `app.py`.
  - `payment_method_label`, `payment_instructions`, `currency_code`,
    `currency_symbol` y `payment_accepts_cash` ahora son configurables
    desde Ajustes, sin asumir país ni moneda.
  - El QR de pago heredado (`QR de tarjeta.jpg`) ya no se sirve por
    defecto a ninguna instalación nueva; solo se muestra si el
    administrador configura explícitamente un archivo propio.

### Pruebas realizadas en esta ronda
Servidor levantado en caliente y probado end-to-end contra la API real
(no simulado): arranque limpio, redirección a `/setup` cuando no está
inicializado, asistente crea Owner correctamente, bloqueo de doble
inicialización, login válido/inválido, `/admin` accesible tras login,
`/api/network-info` con IP real detectada, fallback 501 del QR sin
librería instalada, creación de cuentas con distintos roles, bloqueo de
asignación del rol Owner, jerarquía de permisos (Manager no puede crear
usuarios pero sí listarlos), guardado y lectura de ajustes comerciales,
cambio de idioma (ES/EN/FR verificados por contenido renderizado), y login
de invitado anónimo opcional.

### Pendiente para la siguiente ronda
Backup/restauración desde el panel, descubrimiento automático en LAN
(mDNS/SSDP), niveles de licencia (Free/Business/Professional/Enterprise) y
panel de subida de QR de pago propio. Ver README.md, sección "Pendientes
conocidos".

---

# Changelog — Mejora integral de Freeman Media Hub (historial previo)

## RONDA — Usuario "invitado" sin contraseña, menú de selección reubicado
## (móvil), identificación de dispositivo sin contador, aislamiento real
## entre invitados, velocidad/persistencia de descargas

Cambios quirúrgicos, sin tocar diseño ni lógica no relacionada.

### 1. Usuario invitado sin contraseña
- `app.py`: `CLIENT_USER = "invitado"` (antes "Invitado"). El login acepta
  el usuario "invitado" (sin distinguir mayúsculas/minúsculas) sin exigir
  ninguna contraseña. El administrador "Freeman" no se tocó: sigue
  exigiendo usuario y contraseña exactos.
- `frontend/static/js/login.js`: la validación del formulario ya no
  bloqueaba el envío si el campo contraseña estaba vacío — se corrigió
  para permitirlo específicamente cuando el usuario es "invitado".
- **Probado:** login de "invitado" sin contraseña → OK. "Freeman" sin
  contraseña → rechazado (401). "Freeman" con su contraseña → OK (sin cambios).

### 2. Menú de selección reubicado (vista móvil)
- `frontend/templates/client.html`: el panel de selección se movió en el
  HTML para quedar antes de la biblioteca (sin efecto en escritorio, donde
  sigue flotando igual que antes).
- `frontend/static/css/style.css`: en móvil (`max-width: 639px`) el panel
  deja de ser un elemento flotante superpuesto y pasa a formar parte del
  flujo normal, arriba de la biblioteca — compacto (una sola franja),
  semitransparente, y con `display: none` cuando no hay nada seleccionado
  (no reserva espacio de más). En escritorio no cambió nada.
- **Probado:** con nada seleccionado, el menú no ocupa espacio. Con un
  archivo seleccionado, medí las coordenadas reales: el menú termina en
  286px y el primer vídeo empieza en 355px — sin solaparse. Escritorio
  capturado también, idéntico a como estaba.

### 3. Identificación de invitados sin "Invitado 1/2/3"
- `app.py`: el login ya no asigna un contador (`_next_client_label`,
  eliminado); usa directamente `backend/device.py` (ya existente de una
  ronda anterior) para nombrar la sesión por su dispositivo real
  (ej. "Redmi 9C", "Windows · Chrome", o "Android"/"iPhone" si no hay más
  detalle disponible).
- **Corrección de seguridad necesaria:** como el nombre del dispositivo
  ahora puede repetirse entre invitados distintos (dos teléfonos iguales
  mostrarían el mismo nombre), ya no es seguro usar ese texto para decidir
  permisos. Se agregó la columna `client_uid` a `download_requests`
  (migración automática y no destructiva) y toda la lógica de "esto es
  mío" (`/api/my-requests`, `/api/requests/<id>`, `/api/download/...`)
  ahora compara por ese identificador único de sesión, no por el nombre
  visible.
- **Probado exactamente el caso de riesgo:** dos invitados distintos con
  el mismo modelo de teléfono (ambos "Redmi 9C") — cada uno solo ve sus
  propias solicitudes; uno no pudo ver ni descargar la solicitud aprobada
  del otro (bloqueado con 403 en ambos intentos).

### Extra necesario para "no ver solicitudes de otros" y evitar duplicados
- Se agregó un resguardo en el cliente para que pulsar "Descargar" dos
  veces sobre la misma solicitud no arranque el proceso de descarga por
  duplicado (reutiliza el panel ya abierto).
- Tamaño de fragmento de descarga aumentado de 256 KB a 1 MB (menos
  sobrecarga por fragmento, mismo streaming real sin cargar el archivo
  completo en memoria; el servidor ya corría en modo `threaded=True`,
  permitiendo varias descargas simultáneas sin bloquearse entre sí).
- Persistencia de la selección del cliente: si la página se refresca por
  accidente, los archivos marcados, el total en GB y el precio se
  restauran automáticamente (guardado en `localStorage` del navegador,
  solo IDs de archivo, nada sensible). Probado recargando la página con
  una selección activa: se restauró exactamente igual.

### Regresión verificada
Flujo completo probado de nuevo tras todos los cambios: transferencia sin
verificación (rechazada), transferencia con verificación (creada),
aprobación y descarga — todo funcionando igual que antes.

### Archivos modificados en esta ronda
`app.py`, `backend/db.py`, `database/schema.sql`,
`frontend/templates/client.html`, `frontend/static/css/style.css`,
`frontend/static/js/client.js`, `frontend/static/js/admin.js`,
`frontend/static/js/login.js`.

## RONDA — Biblioteca visual estilo Netflix para el admin, explorador real
## (raíz→disco→carpeta→archivo con migas de pan), auto-publicación,
## carátulas reales en el explorador, capacidad/tamaño, búsqueda contra
## SQLite real, e identificación de dispositivo en Usuarios conectados

### 1. Auto-publicación al agregar desde el explorador
- `backend/db.py` (`insert_media_file`): nuevo parámetro `visible`. Se
  sigue usando `INSERT OR IGNORE`, así que esto NUNCA reactiva algo que el
  administrador ocultó manualmente — solo aplica a filas realmente nuevas.
- `app.py` (`api_add_selection` y `api_scan_location`): ambas rutas de
  inserción (agregar desde el explorador, y volver a escanear una ubicación
  ya registrada) ahora pasan `visible=True`.
- **Probado:** agregar una carpeta con `add-selection` deja el archivo con
  `visible: 1` de inmediato, sin tocar ningún interruptor.

### 2. Eliminada la opción de agregar ubicación manualmente
- `frontend/templates/admin.html`: se quitó todo el bloque "Agregar
  ubicación manualmente" (campo de ruta, selector de modo, botones
  "Explorar carpetas"/"Guardar ubicación").
- El backend (`/api/admin/locations` POST, `/api/admin/browse`) se dejó
  intacto por compatibilidad, tal como pedías — solo se quitó de la
  interfaz.
- El único flujo visible ahora es: Ubicaciones → Explorador → navegar →
  marcar → "Añadir seleccionados a la biblioteca".

### 3 y 4. Explorador real: navegación hasta la raíz + migas de pan
- **Causa del bug original:** el explorador le pedía al backend "la
  carpeta padre" con `os.path.dirname()`, lo cual falla en los bordes
  (la raíz de una unidad, o rutas de Windows) y podía dejar "Atrás"
  atrapado dentro de la torre.
- **Arreglo:** el nuevo explorador (`admin.js`) mantiene su propia **pila
  de navegación** en el navegador (`navStack`), sin depender del backend
  para saber "adónde volver". Al pulsar "Atrás" o cualquier segmento de la
  miga de pan, simplemente recorta la pila y vuelve a pedir esa ruta.
- **Probado:** navegué 5 niveles de profundidad
  (`/ → tmp → carpeta → Películas → Marvel → Avengers`), confirmé la miga
  de pan completa, y comprobé que "Inicio" vuelve exactamente a la lista
  de unidades (`['/']`), no a la carpeta anterior.

### 5. Carátulas reales en el explorador
- `backend/scanner.py`: nuevas funciones `find_folder_cover()` (busca
  poster/cover/portada o imagen con el nombre de la carpeta) y reutilización
  de `find_cover_image()` (imagen con el mismo nombre que el vídeo) también
  al LISTAR el explorador, no solo al escanear.
- Nuevo endpoint `/api/admin/live-thumbnail?path=...`: sirve esa imagen
  directamente desde el disco (con verificación de extensión, solo
  administrador) para archivos que aún no están en la biblioteca.
- **Probado:** con `Avengers Endgame.mp4` + `Avengers Endgame.jpg` en la
  misma carpeta, ambos —el vídeo y la propia imagen— se muestran en el
  explorador con la carátula real, no con el ícono genérico.

### 6. Capacidad de disco y tamaño de carpetas
- `backend/scanner.py`: `get_disk_usage()` (usa `shutil.disk_usage`,
  instantáneo) y `estimate_folder_size()` (recorre con un límite de
  **1.2 segundos o 6000 archivos**, lo que ocurra primero, para no
  congelar la interfaz con carpetas enormes).
- Nuevo endpoint `/api/admin/folder-size?path=...`, consultado **a
  demanda** (botón "📏 Ver tamaño" por carpeta), no automáticamente al
  listar — así el explorador nunca se pone lento solo por mostrar una
  carpeta con miles de archivos.
- Las unidades de disco en la raíz muestran espacio libre/total real.

### 7 y 8. Tarjetas grandes con iconos por tipo + selección persistente
- El explorador ahora usa tarjetas grandes (mismo componente visual que la
  biblioteca), con ícono según tipo (📁 🎬 🎵 🖼️ 📄) cuando no hay carátula.
- La selección (`Map` en el navegador) ya persistía correctamente entre
  carpetas desde la ronda anterior; se conservó ese comportamiento y se
  verificó de nuevo: marcar "Películas", entrar a "Marvel", marcar
  "Marvel" también, volver por la miga de pan — ambas siguen marcadas.

### 9 y 10. Biblioteca del administrador con la misma experiencia visual
- Nueva vista en `admin.js`/`admin.html`: la pestaña Biblioteca del
  administrador ahora usa el mismo patrón visual que el cliente (filas por
  categoría, navegación de carpetas con migas de pan, tarjetas grandes),
  mostrando TODO (con "No publicado" marcado en rojo sobre lo oculto) y
  con un interruptor de publicar/ocultar directamente en cada tarjeta.
- **Bug encontrado y corregido durante las pruebas:** al escribir esta
  vista, el clic en una carpeta anidada (ej. entrar a "Marvel" dentro de
  "Películas") volvía incorrectamente a la raíz de la categoría en lugar
  de entrar a esa subcarpeta. Corregido para que acumule el camino
  correctamente (el mismo patrón que ya funcionaba bien en el cliente).
- **Búsqueda real contra SQLite:** nuevos endpoints `/api/admin/search` y
  `/api/search`, con la consulta `LIKE` (case-insensitive) directamente en
  `db.py` — el administrador busca sobre toda la tabla `media_files`; el
  cliente tiene `AND visible = 1` **dentro de la propia consulta SQL**, no
  como un filtro posterior en JavaScript.
- **Probado:** cliente busca "avengers" (publicado) → 1 resultado; admin
  lo oculta; cliente repite la misma búsqueda → 0 resultados; admin la
  sigue viendo. Probado también con mayúsculas ("AVENGERS") con el mismo
  resultado.

### 13, 14 y 15. Identificación de dispositivo en Usuarios conectados
- Nuevo módulo `backend/device.py`: identifica el dispositivo por niveles
  a partir del `User-Agent` (nunca inventa nada):
  - Nivel 1: modelo real cuando el navegador lo reporta (ej. "Redmi 9C",
    o modelos Samsung conocidos traducidos a "Samsung Galaxy A12").
  - Nivel 2: fabricante/plataforma (ej. "Xiaomi · Android", "Windows · Chrome").
  - Nivel 3: hostname por DNS inverso, cuando el router lo soporta (poco
    común en redes domésticas — se documenta esa limitación).
  - Nivel 4: "Dispositivo desconocido" en vez de inventar un nombre.
- La pestaña Usuarios ahora muestra el dispositivo como dato principal,
  con "Invitado N" como referencia secundaria pequeña (se sigue usando
  internamente para permisos de solicitudes/descargas — eso no cambió).
- **Probado** con dos User-Agents reales simulados (Samsung SM-A125F y
  Windows/Chrome): se identificaron correctamente como "Samsung Galaxy
  A12" y "Windows · Chrome".

### Regresión verificada (Mejoras 16 y 17)
Tras todos los cambios anteriores, probé de nuevo el ciclo completo:
crear solicitud (efectivo) → aprobar → descargar → el archivo llega
completo. Pagos, verificación, precios y el sistema de descargas con
Range/pausa/reanudación de la ronda anterior siguen funcionando sin
cambios.

### Lo que NO se pudo probar (honestamente, según lo pedido)
- **Windows real:** las rutas tipo `C:\`, `D:\` y la detección de unidades
  con `list_windows_drives()` no se probaron en una máquina Windows real
  (este entorno es Linux). La lógica usa `os.path.exists()` sobre las 26
  letras de unidad, que es la forma estándar y debería funcionar en
  Windows, pero no hay confirmación con hardware real.
- **Android físico por WiFi real:** la identificación de dispositivo se
  probó con User-Agents de Android *simulados* en el navegador de
  pruebas, no con un teléfono físico conectado a una red WiFi real.
- **Capacidad de disco en unidades reales grandes** (TB): `shutil.disk_usage`
  es una API estándar de Python probada y confiable, pero no se verificó
  contra un disco físico de varios terabytes.

### Archivos modificados en esta ronda
`app.py`, `backend/db.py`, `backend/scanner.py`, `backend/device.py`
(nuevo), `frontend/templates/admin.html`, `frontend/static/js/admin.js`,
`frontend/static/js/client.js`, `frontend/static/css/style.css`,
`README.md`.

## RONDA — Slogan, buscador, biblioteca persistente, escaneo incremental y
## descargas robustas (pausa/reanudación real por Range requests)

Todos los cambios son incrementales sobre el ZIP anterior. Nada se
reconstruyó desde cero; Flask + SQLite se mantienen intactos.

### 1. Slogan
- Cambiado en los 9 lugares donde aparecía: `app.py`, `run.bat`, `run.sh`,
  `README.md`, `COMO_GENERAR_EL_EXE.txt`, `style.css`, `login.html`,
  `client.html`, `welcome.html`.
- Nuevo: **"En cuestión de segundos"**.

### 2. Corrección crítica: el escaneo YA NO borra la biblioteca
- **Bug real encontrado y corregido:** `api_scan_location` (en `app.py`)
  llamaba a `db.clear_media_for_location()` antes de volver a insertar todo
  lo encontrado. Esto significaba que **cada vez que se re-escaneaba una
  ubicación, se perdían todas las decisiones de visibilidad** (todo volvía
  a quedar oculto), aunque los archivos en sí no se perdían.
- **Arreglo:** ahora se compara contra `db.get_filepaths_for_location()`
  (nueva función) y solo se insertan los archivos realmente nuevos. Los que
  ya existían no se tocan — conservan su estado de publicado/oculto tal cual.
- **Probado:** escaneé una carpeta con 3 archivos, publiqué 1, agregué un
  4º archivo físicamente y re-escaneé → resultado `{"found": 4, "new": 1}`,
  los 3 anteriores sin duplicarse y con su visibilidad intacta.

### 3. Actualización incremental al agregar por el explorador
- `api_add_selection` ahora reutiliza una ubicación existente (misma ruta)
  en vez de crear una duplicada cada vez que se vuelve a marcar la misma
  carpeta. Para archivos sueltos, la lista `selected_files` se **fusiona**
  con la anterior en vez de reemplazarla.
- **Probado:** seleccionar la misma carpeta dos veces → la segunda vez
  `locations_created: 0, locations_updated: 1`, sin archivos duplicados.

### 4. Buscador con lupa 🔍 (administrador y cliente)
- **Administrador** (pestaña Biblioteca): busca por nombre, categoría,
  subcarpeta, extensión, y también por la etiqueta/ruta de la ubicación
  registrada — sobre TODO lo detectado, publicado o no. Cada resultado no
  publicado muestra la etiqueta "Detectado, no publicado".
- **Cliente** (barra superior): busca por nombre, categoría, subcarpeta y
  extensión, pero **solo dentro de los datos que ya le entregó
  `/api/library`** — que de por sí nunca incluye archivos ocultos. No hay
  ninguna llamada nueva al servidor que pueda filtrar contenido no
  publicado: la búsqueda del cliente es un filtro en el navegador sobre
  datos que ya eran seguros de por sí.
- **Probado:** con 6 archivos (3 publicados, 3 ocultos), buscar "pelicula"
  mostró los 6 al administrador y exactamente 3 al cliente.

### 5. Descargas robustas: HTTP Range, pausa, reanudación y reintento
- **Backend** (`app.py`, `/api/download/<req>/<file>`): ahora entiende la
  cabecera `Range` (RFC 7233). Responde `206 Partial Content` con
  `Content-Range`/`Accept-Ranges` cuando corresponde, y `416` si el rango
  pedido no es válido. Verificado byte a byte: una descarga parcial desde
  la mitad del archivo coincide exactamente con el archivo original.
- **Cliente** (`client.js`): cada archivo de una solicitud tiene ahora
  botones reales de ⏸ Pausar / ▶ Reanudar / ✕ Cancelar / ↻ Reintentar.
  Pausar aborta la descarga en curso sin perder lo ya recibido; reanudar
  vuelve a pedir el archivo con `Range: bytes=<recibido>-`, retomando
  exactamente donde quedó. Si una descarga falla a mitad de camino,
  reintenta automáticamente (hasta 4 veces, con espera creciente) también
  usando Range, sin reiniciar desde cero.
- Estados honestos por archivo: Pendiente / Descargando / Pausado /
  Finalizado / Cancelado / Error — nunca queda marcado "Descargando" algo
  que en realidad ya se cortó (una conexión perdida se refleja como
  "interrumpido" en el panel admin y como error/pausado en el cliente).
- **Probado con throttling real:** pausado a los 5.2 MB de un archivo de
  80 MB, confirmado que NO avanzó nada en los siguientes 2 segundos
  estando pausado, reanudado, y terminó en 83,886,080 / 83,886,080 bytes
  (100% exacto) sin reiniciar desde cero.
- El panel admin de "Descargas" (`LIVE_TRANSFERS`) sigue funcionando igual
  que antes — no depende de que `/admin` esté abierto, porque el contador
  de progreso vive dentro de la conexión de descarga del cliente, no del
  panel.

### 6. Corrección de seguridad adicional (relacionada con el punto 20)
Durante las pruebas encontré que un cliente podía, adivinando números de
solicitud, ver o descargar datos de OTRO cliente. Corregido:
- `/api/requests/<id>`, `/api/requests/<id>/verification` y
  `/api/download/<req>/<file>` ahora verifican que la solicitud pertenezca
  a la sesión que la pide (comparando la etiqueta única "Invitado N"), o
  que quien pregunta sea el administrador.
- `/api/thumbnail/<id>` ahora exige sesión iniciada (antes no pedía login).
- **Probado:** Cliente A crea y descarga su propia solicitud (funciona);
  Cliente B (otra sesión) intenta ver/descargar la de A → bloqueado con
  403 en ambos casos; el administrador sigue viendo cualquier solicitud
  sin restricción.

### Archivos modificados en esta ronda
`app.py`, `backend/db.py`, `frontend/templates/admin.html`,
`frontend/templates/client.html`, `frontend/static/js/admin.js`,
`frontend/static/js/client.js`, `frontend/static/css/style.css`,
`README.md`, y el slogan en `run.bat`/`run.sh`/`COMO_GENERAR_EL_EXE.txt`.

Todos los cambios son **incrementales**: no se eliminó ninguna función existente
(login, escaneo, biblioteca por categorías, solicitudes, pagos, ajustes). Se
agregaron capas nuevas encima.

## 1. Módulo administrador "Descargas" + "Usuarios"
- **Nuevo:** pestaña "Descargas" en el panel admin (`admin.html`, `admin.js`).
- Muestra clientes conectados, archivo en transferencia, barra de progreso y
  porcentaje, actualizado automáticamente cada 2 segundos.
- **Backend:** `/api/download/...` ahora transmite el archivo en fragmentos
  (antes usaba `send_file` de una sola vez) y actualiza un registro en
  memoria (`LIVE_TRANSFERS` en `app.py`) que alimenta `/api/admin/downloads/live`.
- **Nuevo (a partir de tu siguiente pedido):** pestaña "Usuarios", que
  muestra cada sesión de cliente conectada con un nombre único asignado
  automáticamente (Invitado 1, Invitado 2, Invitado 3...) y su dirección IP.
  Antes todos los clientes se veían igual ("Invitado"); ahora cada
  dispositivo que entra recibe su propio número, y ese mismo nombre aparece
  también en "Solicitudes" y "Descargas" para poder distinguirlos ahí.
- **Cómo probarlo:** aprueba una solicitud de un archivo grande, descárgalo
  desde el cliente, y mientras se descarga abre "Descargas" en el admin.
  Para "Usuarios", entra como cliente desde dos navegadores/dispositivos
  distintos y revisa la pestaña "Usuarios" del admin.

## 2. Sistema de descargas del cliente (barra general + individual)
- Ya existía de una mejora anterior; se mantiene igual, sin cambios de lógica.

## 3. Biblioteca tipo explorador (selección del administrador)
- Ya existía (explorador visual con flechas y casillas por carpeta/unidad,
  de una mejora anterior). Se revisó y confirmó que ya cumple lo solicitado:
  ver discos/unidades, entrar en subcarpetas, marcar con casilla, y agregar
  varias ubicaciones distintas.

## 4, 5 y 6. Organización visual + navegación + cuadrícula (biblioteca del cliente)
- **Nuevo:** las categorías con subcarpetas (ej. `Novelas/Serie A/Temporada 1`)
  se muestran como carpetas grandes; al entrar, aparece una ruta de migas de
  pan ("Inicio / Novelas / Serie A") y un botón "← Atrás".
- La pantalla de Inicio conserva las filas horizontales estilo Netflix/Emby
  ya existentes; **dentro** de una carpeta se usa una cuadrícula (varias
  columnas en PC, menos en móvil, con scroll vertical).
- **Backend:** se agregó la columna `subfolder` a `media_files` (migración
  automática y no destructiva) y el escáner (`scanner.py`) ahora calcula esa
  ruta relativa al escanear.
- **Cómo probarlo:** crea subcarpetas dentro de una carpeta de categoría
  (ej. `Novelas/Serie A/Cap1.mp4`), escanea de nuevo, y entra a "Novelas"
  como cliente.

## 7. Selección del cliente
- Sin cambios de lógica: seleccionar/deseleccionar ya funcionaba así y no
  reproduce archivos automáticamente. Se mantiene igual.

## 8. Ventana de cálculo de precio
- **Movida** de abajo-derecha a **arriba-derecha**, y agrandada para leerse
  con claridad (archivos, GB, precio).
- **Corrección de un error real:** el cálculo en el navegador usaba un precio
  fijo de $10/GB sin redondeo, ignorando lo configurado en Ajustes. Ahora
  replica exactamente la fórmula del backend (`backend/pricing.py`), así que
  el total mostrado siempre coincide con el que se guarda al enviar la
  solicitud (verificado con precio $4000/GB y redondeo a 5: ambos dieron $160).

## 9. Freeman Media Hub Promo (IP automática)
- **Nuevo:** `backend/network.py` con `sync_promo_config()`. Al arrancar
  `Freeman Media Hub.exe` (o `python app.py`), si encuentra una carpeta
  hermana llamada `Freeman-Media-Hub-Promo` (o variantes similares), escribe
  su IP actual en el `config.json` de Promo automáticamente.
- También hay un botón manual **"Sincronizar Promo ahora"** en Ajustes, por
  si prefieres no reiniciar el servidor para actualizarla.
- Los proyectos siguen siendo independientes: Promo no depende de que el
  Hub esté corriendo para mostrarse, solo lee su `config.json`.
- **Cómo probarlo:** coloca ambas carpetas dentro de una misma carpeta padre,
  arranca `python app.py` y revisa la consola, o entra a Ajustes → "Sincronizar
  Promo ahora".

## 10. Red y router
- **Nuevo:** sección "Red local" en el Resumen del admin, con IP del
  servidor, puerta de enlace (router) y puerto — detectados automáticamente
  (`backend/network.py`, mejor esfuerzo, sin dependencias externas).
- La configuración del portal cautivo depende del router (fuera del alcance
  de esta aplicación), pero ahora Freeman siempre muestra la dirección
  correcta y actualizada para compartir manualmente o vía Promo/QR.

## 13. Explorador de biblioteca tipo Emby (sin escribir rutas)
- **Nuevo:** flecha desplegable (▾) junto al campo "Ruta base" en Ubicaciones.
  Al tocarla, se abre un árbol de carpetas y archivos debajo.
- Cada carpeta y cada archivo tiene su propia casilla. Tocar el **nombre**
  navega (si es carpeta); tocar la **casilla** selecciona/deselecciona.
- Se pueden marcar unidades completas, carpetas, subcarpetas y archivos
  sueltos, todo mezclado, y agregar todo de una vez con el botón
  "Añadir seleccionados a la biblioteca" — sin escribir ninguna ruta a mano.
- El explorador manual anterior ("Explorar carpetas" + Modo + Guardar
  ubicación) se dejó **intacto** como opción avanzada, usando un endpoint
  separado (`/api/admin/browse`) para no arriesgar nada que ya funcionaba.
- **Backend nuevo:** `/api/admin/browse-full` (lista carpetas + archivos con
  tipo/tamaño) y `/api/admin/add-selection` (crea ubicaciones y escanea todo
  de inmediato). Nuevo modo de ubicación `'files'` para archivos sueltos
  elegidos a mano, y columna `selected_files` en `locations`.
- **Cómo probarlo:** pestaña Ubicaciones → toca la flecha → navega y marca
  con casilla → "Añadir seleccionados a la biblioteca".

## 14. Vista de administrador más profesional
- Iconos por tipo en el explorador nuevo: 📁 carpetas, 🎬 vídeo, 🎵 audio,
  🖼️ imágenes (el tamaño en MB se muestra junto a cada archivo).
- La tabla de "Biblioteca" del admin ahora muestra 🎬 antes de cada nombre
  de archivo, la subcarpeta debajo (si tiene), y 🖼️ cuando hay carátula real.

## 15. Métodos de pago: Transferencia/QR o Efectivo
- **Nuevo paso 1** en el modal de pago del cliente: elegir entre
  "📱 Transferencia / QR" o "💵 Efectivo" antes de cualquier otra cosa.
- Efectivo: se envía la solicitud de inmediato, sin pedir verificación;
  queda marcada "Pendiente de cobro en efectivo" para que el administrador
  se acerque a cobrar y apruebe cuando quiera.
- Transferencia/QR: se mantiene el número de cuenta y el QR como
  alternativas (no se exige usar ambos), y ahora el botón se llama
  "Enviar solicitud" en vez de "Enviar verificación" — porque, con la
  corrección del punto 16, es literalmente el mismo paso.

## 16. Corrección de seguridad: solicitudes sin verificar
- **El error real que reportaste:** antes, `POST /api/requests` creaba la
  solicitud de inmediato (quedaba "pendiente" y aprobable) sin pedir ningún
  comprobante; la verificación era un paso aparte y opcional.
- **Arreglo:** ahora, si el método es "transferencia", el servidor
  **rechaza crear la solicitud** (HTTP 400) a menos que venga un mensaje de
  verificación no vacío en la misma petición. Sin mensaje, la solicitud
  sencillamente no existe — no hay nada que el administrador pueda ver ni
  aprobar por error.
- **Segunda barrera:** aunque lo anterior ya lo impide, el endpoint de
  aprobar (`/api/admin/requests/<id>/approve`) también verifica esto por su
  cuenta y devuelve error si detecta una solicitud de transferencia sin
  mensaje válido. Probé esto manipulando la base de datos a mano para
  simular una solicitud "corrupta", y quedó bloqueada igual.
- En el admin, el botón "Aprobar" además queda deshabilitado (atributo
  `disabled`, no solo oculto) cuando corresponda.
- **Cómo probarlo:** en el cliente, elige "Transferencia/QR" y toca
  "Enviar solicitud" sin escribir nada — debe rechazarlo con un aviso
  ("Debes completar la verificación..."). Con Efectivo, en cambio, se
  envía sin pedir nada, como corresponde.

## 17. Aviso de pagos en efectivo pendientes
- Nueva tarjeta destacada (verde) en el Resumen del admin:
  "💵 N clientes esperando cobro en efectivo", visible solo cuando hay
  al menos una solicitud de ese tipo pendiente.
- Cada solicitud en la tabla "Solicitudes" muestra su método con una
  etiqueta de color (📱 azul para transferencia, 💵 verde para efectivo).

## Archivos modificados en esta ronda
`database/schema.sql`, `backend/db.py`, `backend/scanner.py`, `app.py`,
`frontend/templates/admin.html`, `frontend/templates/client.html`,
`frontend/static/js/admin.js`, `frontend/static/js/client.js`,
`frontend/static/css/style.css`. Nada se eliminó; todo lo anterior sigue
funcionando (verificado con pruebas automatizadas end-to-end antes de
entregar este ZIP).
- Archivos **nuevos**: `backend/network.py`, `CHANGELOG.md`.
- Archivos **modificados**: `app.py`, `backend/db.py`, `backend/scanner.py`,
  `database/schema.sql`, `frontend/templates/admin.html`,
  `frontend/templates/client.html`, `frontend/static/js/admin.js`,
  `frontend/static/js/client.js`, `frontend/static/css/style.css`.
- Nada se eliminó; todo lo anterior (login, pagos, ajustes, solicitudes)
  sigue funcionando igual que antes.
