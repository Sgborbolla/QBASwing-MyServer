/* QBASwing MyServer - panel de administración */

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
document.querySelectorAll(".admin-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".admin-tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".admin-section").forEach((s) => s.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
    if (tab.dataset.tab === "dashboard") loadDashboard();
    if (tab.dataset.tab === "locations") loadLocations();
    if (tab.dataset.tab === "library") loadAdminLibrary();
    if (tab.dataset.tab === "requests") loadRequests();
    if (tab.dataset.tab === "settings") loadSettings();
    if (tab.dataset.tab === "downloads") startLiveDownloadsPolling();
    else stopLiveDownloadsPolling();
    if (tab.dataset.tab === "users") startLiveUsersPolling();
    else stopLiveUsersPolling();
    if (tab.dataset.tab === "accounts") loadAccounts();
    if (tab.dataset.tab === "donations") loadDonationsAdmin();
  });
});

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
async function loadDashboard() {
  const statsRow = document.getElementById("statsRow");
  try {
    const [libData, reqData, locData] = await Promise.all([
      apiFetch("/api/admin/library"),
      apiFetch("/api/admin/requests"),
      apiFetch("/api/admin/locations"),
    ]);
    const files = libData.files;
    const visibleCount = files.filter((f) => f.visible).length;
    const pending = reqData.requests.filter((r) => r.status === "pending").length;
    const cashPendingRequests = reqData.requests.filter((r) => r.status === "pending" && r.payment_method === "efectivo");
    const cashPending = cashPendingRequests.length;
    const cashPendingTotal = cashPendingRequests.reduce((sum, r) => sum + (Number(r.total_price) || 0), 0);

    statsRow.innerHTML = `
      <div class="stat-card"><div class="num">${files.length}</div><div class="lbl">Archivos detectados</div></div>
      <div class="stat-card"><div class="num">${visibleCount}</div><div class="lbl">Publicados</div></div>
      <div class="stat-card"><div class="num">${locData.locations.length}</div><div class="lbl">Ubicaciones</div></div>
      <div class="stat-card"><div class="num">${pending}</div><div class="lbl">Solicitudes pendientes</div></div>
      ${cashPending > 0 ? `<div class="stat-card cash-alert"><div class="num">$${cashPendingTotal.toFixed(2)}</div><div class="lbl">💵 A cobrar en efectivo (${cashPending} cliente${cashPending === 1 ? "" : "s"})</div></div>` : ""}
    `;
  } catch (e) {
    statsRow.innerHTML = `<p class="small-note">No se pudieron cargar las estadísticas.</p>`;
  }
  loadNetworkInfo();
}

async function loadNetworkInfo() {
  const box = document.getElementById("networkInfoBox");
  try {
    const info = await apiFetch("/api/network-info");
    box.innerHTML = `
      <div class="network-item"><span class="lbl">Estado</span><span class="val mono">${info.server_active ? "🟢 Servidor activo" : "🔴 Detenido"}</span></div>
      <div class="network-item"><span class="lbl">IP del servidor</span><span class="val mono">${escapeHtml(info.ip)}</span></div>
      <div class="network-item"><span class="lbl">Puerta de enlace (router)</span><span class="val mono">${escapeHtml(info.gateway || "No detectada")}</span></div>
      <div class="network-item"><span class="lbl">Puerto</span><span class="val mono">${info.port}</span></div>
      <div class="network-item"><span class="lbl">Interfaz</span><span class="val mono">${escapeHtml(info.interface || "LAN/WiFi")}</span></div>
      <div class="network-item"><span class="lbl">URL de acceso</span><span class="val mono">${escapeHtml(info.access_url)}</span></div>
    `;
    loadNetworkQr();
  } catch (e) {
    box.innerHTML = `<p class="small-note">No se pudo detectar la información de red.</p>`;
  }
}

async function loadNetworkQr() {
  const qrBox = document.getElementById("networkQrBox");
  if (!qrBox) return;
  // Se vuelve a pedir cada vez (nunca cacheado) para que el QR refleje la
  // IP actual del servidor si cambio de red.
  const img = new Image();
  img.onload = () => {
    qrBox.innerHTML = "";
    qrBox.appendChild(img);
  };
  img.onerror = async () => {
    qrBox.innerHTML = `<p class="small-note">Instala la librería opcional "qrcode" (pip install qrcode[pil]) para mostrar el QR aquí. Mientras tanto, comparte la URL de acceso mostrada arriba.</p>`;
  };
  img.alt = "Código QR de acceso";
  img.className = "network-qr-img";
  img.src = "/api/network/qr.png?_=" + Date.now();
}

// ---------------------------------------------------------------------------
// EXPLORADOR DE BIBLIOTECA — único método para agregar contenido (Mejora 2).
// Se comporta como un explorador de archivos real: mantiene una PILA de
// navegación propia en el navegador (no depende de que el backend calcule
// "la carpeta padre", que es justo lo que hacía que "Atrás" a veces no
// volviera hasta la raíz — Mejora 3). Selección persistente entre carpetas
// (Mejora 8), migas de pan clicables (Mejora 4), tarjetas grandes con
// carátulas reales/iconos por tipo y tamaño (Mejoras 5, 6, 7).
// ---------------------------------------------------------------------------
const expGrid = document.getElementById("expGrid");
const expBreadcrumb = document.getElementById("expBreadcrumb");
const expBackBtn = document.getElementById("expBackBtn");
const expRootBtn = document.getElementById("expRootBtn");
const libPickerSelectionSummary = document.getElementById("libPickerSelectionSummary");
const addSelectionBtn = document.getElementById("addSelectionBtn");

let libPickerSelection = new Map(); // path -> {path, type, label}  (persiste entre carpetas)
let navStack = [];                   // [{path, label}] — pila real de navegación
function adminT(key, vars = {}) {
  let text = window.I18N?.[key] || key;
  Object.entries(vars).forEach(([k, v]) => {
    text = text.replaceAll(`{${k}}`, String(v));
  });
  return text;
}

const TYPE_ICONS = { dir: "📁", video: "🎬", audio: "🎵", image: "🖼️", other: "📄" };

function joinPath(base, name) {
  const sep = base.includes("\\") ? "\\" : "/";
  return base.replace(/[\\/]+$/, "") + sep + name;
}

function formatBytesHuman(bytes) {
  if (!bytes || bytes <= 0) return "0 GB";
  const gb = bytes / (1024 ** 3);
  if (gb >= 1) return gb.toFixed(gb >= 10 ? 0 : 1) + " GB";
  return (bytes / (1024 ** 2)).toFixed(0) + " MB";
}

function updateLibPickerSummary() {
  const n = libPickerSelection.size;
  libPickerSelectionSummary.textContent = n === 0 ? "0 elementos marcados" : `${n} elemento(s) marcado(s)`;
  addSelectionBtn.disabled = n === 0;
}

function renderBreadcrumb() {
  const parts = [`<span class="crumb ${navStack.length === 0 ? "current" : ""}" data-idx="-1">🏠 Inicio</span>`];
  navStack.forEach((entry, i) => {
    parts.push(`<span class="sep">/</span>`);
    const isLast = i === navStack.length - 1;
    parts.push(`<span class="crumb ${isLast ? "current" : ""}" data-idx="${i}">${escapeHtml(entry.label)}</span>`);
  });
  expBreadcrumb.innerHTML = parts.join("");
  expBreadcrumb.querySelectorAll(".crumb").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.idx);
      if (idx === -1) { navStack = []; browseTo(""); return; }
      navStack = navStack.slice(0, idx + 1);
      browseTo(navStack[idx].path);
    });
  });
  expBackBtn.disabled = navStack.length === 0;
}

function goExplorerBack() {
  if (navStack.length === 0) return;
  navStack.pop();
  const target = navStack.length ? navStack[navStack.length - 1].path : "";
  browseTo(target);
}

expBackBtn.addEventListener("click", goExplorerBack);
expRootBtn.addEventListener("click", () => { navStack = []; browseTo(""); });

function enterFolder(path, label) {
  navStack.push({ path, label });
  browseTo(path);
}

async function browseTo(path) {
  expGrid.innerHTML = `<div class="empty-state"><div class="big">⏳</div><div class="title">Cargando...</div></div>`;
  try {
    const data = await apiFetch("/api/admin/browse-full?path=" + encodeURIComponent(path || ""));
    renderExplorerGrid(data);
  } catch (e) {
    expGrid.innerHTML = `<div class="empty-state"><div class="big">⚠️</div><div class="title">No se pudo explorar esa ruta</div><p>${escapeHtml(e.message || "")}</p></div>`;
  }
  renderBreadcrumb();
}

function explorerCardThumb(item, fullPath) {
  if (item.type === "dir") {
    if (item.cover_path) {
      return `<img src="/api/admin/live-thumbnail?path=${encodeURIComponent(item.cover_path)}" loading="lazy">`;
    }
    return `<div class="generic-cover exp-icon">📁</div>`;
  }
  if (item.kind === "image") {
    return `<img src="/api/admin/live-thumbnail?path=${encodeURIComponent(fullPath)}" loading="lazy">`;
  }
  if (item.kind === "video" && item.cover_path) {
    return `<img src="/api/admin/live-thumbnail?path=${encodeURIComponent(item.cover_path)}" loading="lazy">`;
  }
  const icon = TYPE_ICONS[item.kind] || TYPE_ICONS.other;
  return `<div class="generic-cover exp-icon">${icon}</div>`;
}

function renderExplorerGrid(data) {
  if (!data.items.length) {
    expGrid.innerHTML = `<div class="empty-state"><div class="big">📭</div><div class="title">Carpeta vacía</div><p>No hay contenido navegable aquí.</p></div>`;
    return;
  }

  expGrid.innerHTML = data.items.map((item) => {
    const fullPath = data.is_root ? item.name : joinPath(data.path, item.name);
    const displayName = data.is_root && item.label ? item.label : item.name;
    const marked = libPickerSelection.has(fullPath);
    const thumb = explorerCardThumb(item, fullPath);

    let metaLine;
    if (item.type === "dir" && data.is_root && item.disk_usage) {
      const u = item.disk_usage;
      metaLine = `${formatBytesHuman(u.free)} libres / ${formatBytesHuman(u.total)}`;
    } else if (item.type === "dir") {
      metaLine = `<span class="folder-size-btn" data-path="${escapeHtml(fullPath)}">📏 Ver tamaño</span>`;
    } else {
      metaLine = `${formatBytesHuman(item.size_bytes)} · ${escapeHtml((item.extension || "").toUpperCase())}`;
    }

    return `
      <div class="media-card exp-card ${marked ? "selected" : ""}" data-path="${escapeHtml(fullPath)}" data-type="${item.type}" data-name="${escapeHtml(displayName)}">
        <label class="exp-checkbox-wrap" onclick="event.stopPropagation()">
          <input type="checkbox" class="item-checkbox" ${marked ? "checked" : ""}>
        </label>
        <div class="poster">${thumb}${item.type === "dir" && data.is_root ? `<span class="ext-badge">💽</span>` : ""}</div>
        <div class="card-meta">
          <div class="fname" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</div>
          <div class="sub meta-line">${metaLine}</div>
        </div>
      </div>
    `;
  }).join("");

  expGrid.querySelectorAll(".exp-card").forEach((card) => {
    const path = card.dataset.path;
    const type = card.dataset.type;
    const name = card.dataset.name;
    const chk = card.querySelector(".item-checkbox");

    chk.addEventListener("change", () => {
      if (chk.checked) {
        libPickerSelection.set(path, { path, type, label: name });
        card.classList.add("selected");
      } else {
        libPickerSelection.delete(path);
        card.classList.remove("selected");
      }
      updateLibPickerSummary();
    });

    card.addEventListener("click", (e) => {
      if (e.target.closest(".folder-size-btn")) return;
      if (type === "dir") enterFolder(path, name);
    });
  });

  expGrid.querySelectorAll(".folder-size-btn").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const path = btn.dataset.path;
      btn.textContent = adminT("js.calculating");
      try {
        const info = await apiFetch("/api/admin/folder-size?path=" + encodeURIComponent(path));
        btn.textContent = formatBytesHuman(info.size_bytes) + (info.partial ? "+ (parcial)" : "");
      } catch (err) {
        btn.textContent = adminT("js.unavailable");
      }
    });
  });

  updateLibPickerSummary();
}

addSelectionBtn.addEventListener("click", async () => {
  if (libPickerSelection.size === 0) return;
  addSelectionBtn.disabled = true;
  addSelectionBtn.textContent = adminT("js.adding");
  try {
    const result = await apiFetch("/api/admin/add-selection", {
      method: "POST",
      body: JSON.stringify({ items: Array.from(libPickerSelection.values()) }),
    });
    showToast(`Listo y publicado: ${result.locations_created} ubicación(es) nueva(s), ${result.locations_updated} actualizada(s), ${result.files_found} archivo(s) nuevo(s).`);
    libPickerSelection.clear();
    updateLibPickerSummary();
    expGrid.querySelectorAll(".exp-card.selected").forEach((c) => {
      c.classList.remove("selected");
      c.querySelector(".item-checkbox").checked = false;
    });
    loadLocations();
  } catch (e) {
    showToast(e.message || "No se pudo agregar la selección.");
  } finally {
    addSelectionBtn.disabled = libPickerSelection.size === 0;
    addSelectionBtn.textContent = adminT("js.add_selected");
  }
});

browseTo(""); // cargar la raíz (unidades/discos) al abrir el panel

async function loadLocations() {
  const tbody = document.getElementById("locationsTableBody");
  try {
    const data = await apiFetch("/api/admin/locations");
    if (!data.locations.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="small-note">Aún no hay ubicaciones registradas.</td></tr>`;
      return;
    }
    tbody.innerHTML = data.locations.map((loc) => `
      <tr>
        <td>${escapeHtml(loc.label)}</td>
        <td style="font-family:var(--font-mono); font-size:12px;">${escapeHtml(loc.path)}</td>
        <td>${loc.scan_mode === "tower" ? "Torre completa" : loc.scan_mode === "files" ? "Archivos sueltos" : "Carpetas específicas"}</td>
        <td>${loc.last_scan_at ? escapeHtml(loc.last_scan_at) : "Nunca"}</td>
        <td style="display:flex; gap:6px;">
          <button class="btn-secondary" style="padding:5px 10px; font-size:11px;" onclick="scanLocation(${loc.id})">Escanear</button>
          <button class="btn-danger" onclick="deleteLocation(${loc.id})">Eliminar</button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="small-note">Error al cargar ubicaciones.</td></tr>`;
  }
}

async function scanLocation(id) {
  showToast("Escaneando...");
  try {
    const data = await apiFetch(`/api/admin/scan/${id}`, { method: "POST" });
    showToast(`Escaneo completo: ${data.new} archivo(s) nuevo(s) publicado(s) (${data.found} en total detectados en esta ubicación).`);
    loadLocations();
  } catch (e) {
    showToast(e.message || "Error al escanear.");
  }
}

async function deleteLocation(id) {
  if (!confirm(adminT("js.delete_location"))) return;
  try {
    await apiFetch(`/api/admin/locations/${id}`, { method: "DELETE" });
    showToast("Ubicación eliminada.");
    loadLocations();
  } catch (e) {
    showToast(e.message || "Error al eliminar.");
  }
}

// ---------------------------------------------------------------------------
// Biblioteca (admin) — misma experiencia visual que el cliente (Mejora 9):
// filas Netflix/Emby en Inicio, explorador de carpetas al entrar a una
// categoría, con el añadido de que aquí SÍ se ve lo no publicado (marcado)
// y se puede alternar visibilidad desde la propia tarjeta.
// ---------------------------------------------------------------------------
let adminAllFiles = [];
let adminView = { category: null, path: [] };
let adminSearchActive = false;

function adminCategoryOrder(cat) {
  const order = ["Películas", "Series", "Novelas", "Documentales", "General"];
  const idx = order.indexOf(cat);
  return idx === -1 ? order.length : idx;
}

async function loadAdminLibrary() {
  try {
    const data = await apiFetch("/api/admin/library");
    adminAllFiles = data.files;
    adminView = { category: null, path: [] };
    renderAdminLibrary();
  } catch (e) {
    document.getElementById("adminLibraryGrid").innerHTML = `<p class="small-note" style="padding:0 22px;">Error al cargar la biblioteca.</p>`;
  }
}

function adminGroupEntries(files, prefix) {
  const folderMap = {};
  const directFiles = [];
  files.forEach((f) => {
    const sub = f.subfolder || "";
    if (sub === prefix) { directFiles.push(f); return; }
    if (prefix && !sub.startsWith(prefix + "/")) return;
    if (!prefix && sub === "") return;
    const rest = prefix ? sub.slice(prefix.length + 1) : sub;
    const nextSeg = rest.split("/")[0];
    if (!folderMap[nextSeg]) folderMap[nextSeg] = { type: "folder", name: nextSeg, count: 0, coverFileId: null };
    folderMap[nextSeg].count++;
    if (!folderMap[nextSeg].coverFileId && f.has_cover) folderMap[nextSeg].coverFileId = f.id;
  });
  const folders = Object.values(folderMap).sort((a, b) => a.name.localeCompare(b.name));
  return [...folders, ...directFiles.map((f) => ({ type: "file", file: f }))];
}

function adminRenderCard(f) {
  const coverHtml = f.has_cover
    ? `<img src="/api/thumbnail/${f.id}" alt="${escapeHtml(f.filename)}" loading="lazy">`
    : `<div class="generic-cover"><div class="icon">🎬</div><div class="brand">${escapeHtml(window.APP_NAME || "QBASwing MyServer")}</div><div class="fname">${escapeHtml(f.filename)}</div></div>`;
  return `
    <div class="media-card admin-media-card" data-id="${f.id}">
      <div class="poster">
        ${coverHtml}
        <span class="ext-badge">${escapeHtml(f.extension.toUpperCase())}</span>
        ${!f.visible ? `<span class="unpub-badge">No publicado</span>` : ""}
      </div>
      <div class="card-meta">
        <div class="fname" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</div>
        <div class="sub">
          <span class="size">${f.size_gb} GB</span>
          <label class="switch" style="transform:scale(0.8); transform-origin:right center;" onclick="event.stopPropagation()" title=${adminT("js.published_title")}>
            <input type="checkbox" class="vis-toggle" data-id="${f.id}" ${f.visible ? "checked" : ""}>
            <span class="slider"></span>
          </label>
        </div>
        <div class="sub" style="margin-top:4px;">
          <span class="small-note" style="font-size:10.5px;">${f.is_free ? adminT("js.free") : adminT("js.paid")}</span>
          <label class="switch" style="transform:scale(0.8); transform-origin:right center;" onclick="event.stopPropagation()" title=${adminT("js.free_commercial_title")}>
            <input type="checkbox" class="free-toggle" data-id="${f.id}" ${f.is_free ? "checked" : ""}>
            <span class="slider"></span>
          </label>
        </div>
      </div>
    </div>
  `;
}

function adminRenderFolderCard(category, entry) {
  const coverHtml = entry.coverFileId
    ? `<img src="/api/thumbnail/${entry.coverFileId}" alt="${escapeHtml(entry.name)}" loading="lazy">`
    : `<div class="folder-icon">📁</div>`;
  return `
    <div class="media-card folder-card admin-folder-card" data-cat="${escapeHtml(category)}" data-seg="${escapeHtml(entry.name)}">
      <div class="poster">${coverHtml}</div>
      <div class="card-meta">
        <div class="fname">📁 ${escapeHtml(entry.name)}</div>
        <div class="sub"><span class="count-note">${entry.count} elemento(s)</span></div>
      </div>
    </div>
  `;
}

function bindAdminLibraryEvents() {
  document.querySelectorAll("#adminLibraryGrid .admin-media-card[data-id]").forEach((card) => {
    card.querySelector(".vis-toggle").addEventListener("change", async (e) => {
      const chk = e.target;
      try {
        await apiFetch("/api/admin/visibility", {
          method: "POST",
          body: JSON.stringify({ file_id: Number(chk.dataset.id), visible: chk.checked }),
        });
        showToast(chk.checked ? "Publicado." : "Ocultado.");
        const f = adminAllFiles.find((x) => x.id === Number(chk.dataset.id));
        if (f) f.visible = chk.checked ? 1 : 0;
        const badge = card.querySelector(".unpub-badge");
        if (chk.checked && badge) badge.remove();
        else if (!chk.checked && !badge) card.querySelector(".poster").insertAdjacentHTML("beforeend", `<span class="unpub-badge">No publicado</span>`);
      } catch (err) {
        chk.checked = !chk.checked;
        showToast(err.message || "No se pudo actualizar.");
      }
    });
    const freeToggle = card.querySelector(".free-toggle");
    if (freeToggle) {
      freeToggle.addEventListener("change", async (e) => {
        const chk = e.target;
        try {
          await apiFetch(`/api/admin/media/${chk.dataset.id}/set-free`, {
            method: "POST",
            body: JSON.stringify({ is_free: chk.checked }),
          });
          showToast(chk.checked ? "Marcado como gratis." : "Marcado como de pago.");
          const f = adminAllFiles.find((x) => x.id === Number(chk.dataset.id));
          if (f) f.is_free = chk.checked ? 1 : 0;
          const label = card.querySelector(".small-note");
          if (label) label.textContent = chk.checked ? adminT("js.free") : adminT("js.paid");
        } catch (err) {
          chk.checked = !chk.checked;
          showToast(err.message || "No se pudo actualizar.");
        }
      });
    }
  });
  document.querySelectorAll("#adminLibraryGrid .admin-folder-card").forEach((card) => {
    card.addEventListener("click", () => {
      const seg = card.dataset.seg;
      if (adminView.category === card.dataset.cat) {
        adminView = { category: card.dataset.cat, path: [...adminView.path, seg] };
      } else {
        adminView = { category: card.dataset.cat, path: [seg] };
      }
      renderAdminLibrary();
    });
  });
  document.querySelectorAll("#adminLibraryGrid .category-title[data-cat]").forEach((el) => {
    el.addEventListener("click", () => {
      adminView = { category: el.dataset.cat, path: [] };
      renderAdminLibrary();
    });
  });
}

function renderAdminLibrary() {
  const grid = document.getElementById("adminLibraryGrid");
  const toolbar = document.getElementById("adminLibToolbar");
  const backBtn = document.getElementById("adminLibBackBtn");
  const breadcrumb = document.getElementById("adminLibBreadcrumb");

  if (!adminAllFiles.length) {
    toolbar.style.display = "none";
    grid.innerHTML = `<p class="small-note" style="padding:0 22px;">Aún no se ha detectado contenido. Ve a "Ubicaciones" y usa el explorador.</p>`;
    return;
  }
  toolbar.style.display = "flex";

  if (adminView.category === null) {
    backBtn.style.display = "none";
    breadcrumb.innerHTML = "";
    const groups = {};
    adminAllFiles.forEach((f) => { (groups[f.category] = groups[f.category] || []).push(f); });
    const cats = Object.keys(groups).sort((a, b) => adminCategoryOrder(a) - adminCategoryOrder(b));
    grid.innerHTML = cats.map((cat) => {
      const entries = adminGroupEntries(groups[cat], "");
      const unpub = groups[cat].filter((f) => !f.visible).length;
      return `
        <div class="category-block">
          <h2 class="category-title" data-cat="${escapeHtml(cat)}">${escapeHtml(cat)}<span class="category-count">${groups[cat].length} elemento(s)${unpub ? ` · ${unpub} sin publicar` : ""}</span></h2>
          <div class="explorer-card-grid">${entries.map((e) => e.type === "folder" ? adminRenderFolderCard(cat, e) : adminRenderCard(e.file)).join("")}</div>
        </div>
      `;
    }).join("");
  } else {
    backBtn.style.display = "inline-block";
    const { category, path } = adminView;
    const prefix = path.join("/");
    const categoryFiles = adminAllFiles.filter((f) => f.category === category);
    const entries = adminGroupEntries(categoryFiles, prefix);

    const crumbs = [`<span class="crumb" data-idx="-1">Biblioteca</span>`, `<span class="sep">/</span>`, `<span class="crumb" data-idx="0">${escapeHtml(category)}</span>`];
    path.forEach((seg, i) => {
      crumbs.push(`<span class="sep">/</span>`);
      crumbs.push(`<span class="crumb ${i === path.length - 1 ? "current" : ""}" data-idx="${i + 1}">${escapeHtml(seg)}</span>`);
    });
    breadcrumb.innerHTML = crumbs.join("");
    breadcrumb.querySelectorAll(".crumb").forEach((el) => {
      el.addEventListener("click", () => {
        const idx = Number(el.dataset.idx);
        if (idx === -1) adminView = { category: null, path: [] };
        else adminView = { category, path: path.slice(0, idx) };
        renderAdminLibrary();
      });
    });
    backBtn.onclick = () => {
      if (path.length > 0) adminView = { category, path: path.slice(0, -1) };
      else adminView = { category: null, path: [] };
      renderAdminLibrary();
    };

    grid.innerHTML = `<div class="explorer-card-grid" style="padding:0 22px 30px;">${entries.map((e) => e.type === "folder" ? adminRenderFolderCard(category, e) : adminRenderCard(e.file)).join("")}</div>`;
  }

  bindAdminLibraryEvents();
}

// --- Búsqueda REAL contra el backend (Mejora 10/12): nunca es un filtro
// sobre una lista ya cargada; cada tecleo consulta /api/admin/search. ---
const adminLibrarySearchInput = document.getElementById("adminLibrarySearch");
const adminSearchCount = document.getElementById("adminSearchCount");
let adminSearchDebounce = null;

adminLibrarySearchInput.addEventListener("input", () => {
  clearTimeout(adminSearchDebounce);
  const q = adminLibrarySearchInput.value.trim();
  if (!q) {
    adminSearchActive = false;
    adminSearchCount.textContent = "";
    renderAdminLibrary();
    return;
  }
  adminSearchDebounce = setTimeout(async () => {
    try {
      const data = await apiFetch("/api/admin/search?q=" + encodeURIComponent(q));
      adminSearchActive = true;
      adminSearchCount.textContent = adminT("js.search_results", {n: data.files.length});
      const grid = document.getElementById("adminLibraryGrid");
      document.getElementById("adminLibToolbar").style.display = "none";
      if (!data.files.length) {
        grid.innerHTML = `<p class="small-note" style="padding:0 22px;">Ningún resultado coincide con la búsqueda.</p>`;
        return;
      }
      grid.innerHTML = `<div class="explorer-card-grid" style="padding:0 22px 30px;">${data.files.map(adminRenderCard).join("")}</div>`;
      bindAdminLibraryEvents();
    } catch (e) {
      showToast("Error al buscar.");
    }
  }, 250);
});

// ---------------------------------------------------------------------------
// Solicitudes
// ---------------------------------------------------------------------------
async function loadRequests() {
  const tbody = document.getElementById("requestsTableBody");
  try {
    const data = await apiFetch("/api/admin/requests");
    if (!data.requests.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="small-note">Aún no hay solicitudes de descarga.</td></tr>`;
      return;
    }
    tbody.innerHTML = data.requests.map((r) => {
      // Regla del Módulo 5: si es transferencia y no hay mensaje de
      // verificación válido, el botón Aprobar queda bloqueado de verdad
      // (disabled), no solo oculto por CSS.
      const canApprove = r.payment_method !== "transferencia" || !!(r.verification_message && r.verification_message.trim());
      const methodBadge = r.payment_method === "efectivo"
        ? `<span class="badge cash">💵 Efectivo</span>`
        : `<span class="badge transfer">📱 Transferencia</span>`;
      return `
      <tr>
        <td>#${r.id}</td>
        <td>${escapeHtml(r.client_label)}</td>
        <td>${r.file_ids.length} archivo(s)</td>
        <td>${(r.total_size_bytes / (1024 ** 3)).toFixed(2)} GB</td>
        <td>$${r.total_price}</td>
        <td><span class="badge ${r.status}">${statusLabel(r.status)}</span></td>
        <td>
          ${methodBadge}<br>
          <span class="small-note">${paymentStatusLabel(r.payment_status)}</span>
          ${r.verification_message ? `<button class="btn-secondary btn-tactile" style="padding:4px 8px; font-size:10px; margin-top:4px;" onclick='viewVerification(${JSON.stringify(r.verification_message)})'>Ver mensaje</button>` : ""}
        </td>
        <td style="font-size:11px;">${escapeHtml(r.created_at)}</td>
        <td style="display:flex; gap:6px;">
          ${r.status === "pending" ? `
            <button class="btn-secondary btn-tactile" style="padding:5px 10px; font-size:11px;" onclick="approveRequest(${r.id})" ${canApprove ? "" : "disabled title=\"Falta la verificación de pago\""}>Aprobar</button>
            <button class="btn-danger btn-tactile" onclick="rejectRequest(${r.id})">Rechazar</button>
          ` : ""}
        </td>
      </tr>
    `;
    }).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" class="small-note">Error al cargar solicitudes.</td></tr>`;
  }
}

function statusLabel(status) {
  return { pending: "Pendiente", approved: "Aprobada", rejected: "Rechazada", completed: "✅ Completada" }[status] || status;
}

function paymentStatusLabel(status) {
  return {
    pendiente: "Pago pendiente",
    pendiente_efectivo: "Pendiente de cobro",
    verificacion_enviada: "Verificación enviada",
    aprobado: "Aprobado",
    rechazado: "Rechazado",
  }[status] || status;
}

function viewVerification(message) {
  document.getElementById("verifyMessageBox").textContent = message;
  document.getElementById("verifyModal").classList.add("show");
}

document.getElementById("closeVerifyModal").addEventListener("click", () => {
  document.getElementById("verifyModal").classList.remove("show");
});

async function approveRequest(id) {
  try {
    await apiFetch(`/api/admin/requests/${id}/approve`, { method: "POST" });
    showToast("Solicitud aprobada.");
    loadRequests();
  } catch (e) {
    showToast(e.message || "Error al aprobar.");
  }
}

async function rejectRequest(id) {
  try {
    await apiFetch(`/api/admin/requests/${id}/reject`, { method: "POST" });
    showToast("Solicitud rechazada.");
    loadRequests();
  } catch (e) {
    showToast(e.message || "Error al rechazar.");
  }
}

// ---------------------------------------------------------------------------
// Ajustes (precio, redondeo, cuenta bancaria, nombre del servicio WiFi)
// ---------------------------------------------------------------------------
async function loadSettings() {
  try {
    const data = await apiFetch("/api/admin/settings");
    const s = data.settings;
    document.getElementById("settingPricePerGb").value = s.price_per_gb || "10";
    document.getElementById("settingRoundingMode").value = s.rounding_mode || "none";
    document.getElementById("settingAccountNumber").value = s.account_number || "";
    document.getElementById("settingServiceName").value = s.service_name || "";
    document.getElementById("settingBusinessName").value = s.business_name || "";
    document.getElementById("settingDistributionMode").value = s.distribution_mode || "free";
    document.getElementById("settingCurrencyCode").value = s.currency_code || "USD";
    document.getElementById("settingCurrencySymbol").value = s.currency_symbol || "$";
    document.getElementById("settingPaymentMethodLabel").value = s.payment_method_label || "";
    document.getElementById("settingPaymentInstructions").value = s.payment_instructions || "";
    document.getElementById("settingAcceptsCash").checked = (s.payment_accepts_cash || "1") === "1";
    document.getElementById("settingDefaultLanguage").value = s.default_language || "es";
    document.getElementById("settingGuestOpenLogin").checked = (s.guest_open_login || "1") === "1";
  } catch (e) {
    showToast("No se pudo cargar la configuración.");
  }
}

document.getElementById("saveSettingsBtn").addEventListener("click", async () => {
  const payload = {
    price_per_gb: document.getElementById("settingPricePerGb").value.trim(),
    rounding_mode: document.getElementById("settingRoundingMode").value,
    account_number: document.getElementById("settingAccountNumber").value.trim(),
    service_name: document.getElementById("settingServiceName").value.trim(),
    business_name: document.getElementById("settingBusinessName").value.trim(),
    distribution_mode: document.getElementById("settingDistributionMode").value,
    currency_code: document.getElementById("settingCurrencyCode").value.trim(),
    currency_symbol: document.getElementById("settingCurrencySymbol").value.trim(),
    payment_method_label: document.getElementById("settingPaymentMethodLabel").value.trim(),
    payment_instructions: document.getElementById("settingPaymentInstructions").value.trim(),
    payment_accepts_cash: document.getElementById("settingAcceptsCash").checked ? "1" : "0",
    default_language: document.getElementById("settingDefaultLanguage").value,
    guest_open_login: document.getElementById("settingGuestOpenLogin").checked ? "1" : "0",
  };
  try {
    await apiFetch("/api/admin/settings", { method: "POST", body: JSON.stringify(payload) });
    showToast("Ajustes guardados correctamente.");
  } catch (e) {
    showToast(e.message || "Error al guardar los ajustes.");
  }
});

// ---------------------------------------------------------------------------
// Cuentas (usuarios reales del sistema: Owner/Administrator/Manager/User/Guest)
// ---------------------------------------------------------------------------
const ROLE_LABELS = {
  owner: "Propietario", administrator: "Administrador", manager: "Gestor",
  user: "Usuario", guest: "Invitado",
};

async function loadAccounts() {
  const body = document.getElementById("accountsTableBody");
  try {
    const data = await apiFetch("/api/admin/users");
    if (!data.users.length) {
      body.innerHTML = `<tr><td colspan="6" class="small-note">Sin cuentas todavía.</td></tr>`;
      return;
    }
    body.innerHTML = data.users.map((u) => `
      <tr>
        <td>${escapeHtml(u.username)}</td>
        <td>${escapeHtml(u.full_name || "—")}</td>
        <td>${ROLE_LABELS[u.role] || u.role}</td>
        <td>${(u.language || "es").toUpperCase()}</td>
        <td>${u.active ? "✅ Activo" : "🚫 Inactivo"}</td>
        <td>
          ${u.role !== "owner" ? `
            <button class="btn-secondary btn-tactile" data-edit-account="${u.id}" type="button">Editar</button>
            ${(u.role === "user" || u.role === "guest") ? `<button class="btn-secondary btn-tactile" data-perms-account="${u.id}" type="button">Permisos</button>` : ""}
            <button class="btn-secondary btn-tactile" data-delete-account="${u.id}" type="button">Eliminar</button>
          ` : `<span class="small-note">—</span>`}
        </td>
      </tr>
    `).join("");

    body.querySelectorAll("[data-delete-account]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm(adminT("js.delete_account"))) return;
        try {
          await apiFetch(`/api/admin/users/${btn.dataset.deleteAccount}`, { method: "DELETE" });
          showToast("Cuenta eliminada.");
          loadAccounts();
        } catch (e) {
          showToast(e.message || "No se pudo eliminar la cuenta.");
        }
      });
    });
    body.querySelectorAll("[data-edit-account]").forEach((btn) => {
      btn.addEventListener("click", () => openAccountModal(Number(btn.dataset.editAccount), data.users));
    });
    body.querySelectorAll("[data-perms-account]").forEach((btn) => {
      btn.addEventListener("click", () => openPermissionsModal(Number(btn.dataset.permsAccount)));
    });
  } catch (e) {
    body.innerHTML = `<tr><td colspan="6" class="small-note">No se pudieron cargar las cuentas.</td></tr>`;
  }
}

function openAccountModal(userId, users) {
  const existing = userId ? users.find((u) => u.id === userId) : null;
  const username = prompt("Nombre de usuario:", existing ? existing.username : "");
  if (username === null) return;
  const isNew = !existing;
  let password = "";
  if (isNew) {
    password = prompt("Contraseña para la nueva cuenta:", "") || "";
    if (!password) { showToast("Se necesita una contraseña."); return; }
  }
  const role = prompt("Rol (administrator / manager / user / guest):", existing ? existing.role : "user");
  if (!role || !["administrator", "manager", "user", "guest"].includes(role)) {
    showToast("Rol inválido.");
    return;
  }
  const fullName = prompt("Nombre completo:", existing ? existing.full_name || "" : "") || "";

  const run = async () => {
    try {
      if (isNew) {
        await apiFetch("/api/admin/users", {
          method: "POST",
          body: JSON.stringify({ username, password, role, full_name: fullName }),
        });
      } else {
        await apiFetch(`/api/admin/users/${existing.id}`, {
          method: "PUT",
          body: JSON.stringify({ role, full_name: fullName }),
        });
      }
      showToast("Cuenta guardada.");
      loadAccounts();
    } catch (e) {
      showToast(e.message || "No se pudo guardar la cuenta.");
    }
  };
  run();
}

document.getElementById("newAccountBtn")?.addEventListener("click", () => openAccountModal(null, []));

// ---------------------------------------------------------------------------
// Backup y restauración
// ---------------------------------------------------------------------------
document.getElementById("downloadBackupBtn")?.addEventListener("click", () => {
  window.location.href = "/api/admin/backup";
});

document.getElementById("uploadPaymentQrBtn")?.addEventListener("click", async () => {
  const input = document.getElementById("paymentQrInput");
  const statusEl = document.getElementById("paymentQrStatus");
  const file = input.files[0];
  if (!file) { showToast("Selecciona primero una imagen."); return; }
  const formData = new FormData();
  formData.append("qr_file", file);
  try {
    const res = await fetch("/api/admin/upload-payment-qr", { method: "POST", body: formData });
    const data = await res.json();
    if (res.ok && data.ok) {
      statusEl.textContent = "✓ QR de pago actualizado (" + data.filename + ")";
      showToast("QR de pago subido correctamente.");
    } else {
      statusEl.textContent = data.error === "formato_no_soportado" ? adminT("js.qr_format_error") : adminT("js.qr_upload_error");
    }
  } catch (e) {
    statusEl.textContent = adminT("js.qr_connection_error");
  }
});

document.getElementById("restoreBackupBtn")?.addEventListener("click", async () => {
  const input = document.getElementById("restoreFileInput");
  const file = input.files[0];
  if (!file) { showToast("Selecciona primero un archivo de copia de seguridad."); return; }
  if (!confirm("Esto reemplaza TODA la base de datos actual (usuarios, permisos, catálogo, ajustes). ¿Continuar?")) return;

  const formData = new FormData();
  formData.append("backup_file", file);
  try {
    const res = await fetch("/api/admin/restore", { method: "POST", body: formData });
    const data = await res.json();
    if (res.ok && data.ok) {
      showToast("Restauración completada. Vuelve a iniciar sesión.");
      setTimeout(() => { window.location.href = "/login"; }, 1500);
    } else {
      const messages = {
        archivo_requerido: "Selecciona un archivo.",
        backup_invalido: "El archivo no contiene una base de datos válida.",
        archivo_no_es_zip: "El archivo debe ser el .zip generado por 'Descargar copia de seguridad'.",
        base_de_datos_no_compatible: "La base de datos del archivo no es compatible con QBASwing MyServer.",
      };
      showToast(messages[data.error] || "No se pudo restaurar la copia de seguridad.");
    }
  } catch (e) {
    showToast("Error de conexión al restaurar.");
  }
});

async function openPermissionsModal(userId) {
  let categories = [];
  let current = {};
  try {
    const [catsData, permsData] = await Promise.all([
      apiFetch("/api/admin/categories"),
      apiFetch(`/api/admin/users/${userId}/permissions`),
    ]);
    categories = catsData.categories;
    current = permsData.permissions;
  } catch (e) {
    showToast("No se pudieron cargar los permisos.");
    return;
  }
  if (!categories.length) {
    showToast("Todavía no hay categorías de contenido en la biblioteca.");
    return;
  }
  const summary = categories.map((c) => {
    const entry = current[c];
    return `${c}: ${entry ? (entry.can_view ? "✅ ver" : "🚫 ver") + (entry.can_download ? " ✅ descargar" : " 🚫 descargar") : "sin restricción (acceso total)"}`;
  }).join("\n");
  const chosen = prompt(
    `Categorías disponibles:\n${categories.join(", ")}\n\nPermisos actuales:\n${summary}\n\n` +
    `Escribe el nombre de la categoría a configurar para este usuario:`
  );
  if (!chosen || !categories.includes(chosen)) return;
  const canView = confirm(`¿Puede VER la categoría "${chosen}"? (Aceptar = sí, Cancelar = no)`);
  const canDownload = canView ? confirm(`¿Puede DESCARGAR de "${chosen}"? (Aceptar = sí, Cancelar = no)`) : false;
  try {
    await apiFetch(`/api/admin/users/${userId}/permissions`, {
      method: "POST",
      body: JSON.stringify({ category: chosen, can_view: canView ? 1 : 0, can_download: canDownload ? 1 : 0 }),
    });
    showToast(`Permiso de "${chosen}" actualizado. Nota: en cuanto configuras la primera categoría para este usuario, el acceso pasa a ser SOLO lo explícitamente permitido (las demás categorías quedan bloqueadas hasta que también las configures).`);
  } catch (e) {
    showToast(e.message || "No se pudo guardar el permiso.");
  }
}

// ---------------------------------------------------------------------------
// Descargas en vivo (clientes conectados, progreso por archivo)
// ---------------------------------------------------------------------------
let liveDownloadsTimer = null;

function startLiveDownloadsPolling() {
  loadLiveDownloads();
  stopLiveDownloadsPolling();
  liveDownloadsTimer = setInterval(loadLiveDownloads, 2000);
}

function stopLiveDownloadsPolling() {
  if (liveDownloadsTimer) {
    clearInterval(liveDownloadsTimer);
    liveDownloadsTimer = null;
  }
}

function formatBytes(bytes) {
  const gb = bytes / (1024 ** 3);
  if (gb >= 1) return gb.toFixed(2) + " GB";
  return (bytes / (1024 ** 2)).toFixed(1) + " MB";
}

async function loadLiveDownloads() {
  const list = document.getElementById("liveDownloadsList");
  try {
    const data = await apiFetch("/api/admin/downloads/live");
    if (!data.transfers.length) {
      list.innerHTML = `<p class="small-note" style="margin-top:14px;">No hay descargas en curso en este momento.</p>`;
      return;
    }
    list.innerHTML = data.transfers.map((t) => `
      <div class="download-client-row">
        <div class="top">
          <span class="client-name">${escapeHtml(t.client_label)} <span class="small-note">· solicitud #${t.request_id}</span></span>
          <span class="pct mono">${t.pct}%</span>
        </div>
        <div class="bar"><div class="fill ${t.status === "finalizado" ? "done" : ""}" style="width:${t.pct}%;"></div></div>
        <div class="bottom small-note">
          <span title="${escapeHtml(t.filename)}">${escapeHtml(t.filename)}</span>
          <span>${formatBytes(t.bytes_sent)} / ${formatBytes(t.total_bytes)} · ${t.status === "finalizado" ? "✓ Finalizado" : t.status === "error" || t.status === "interrumpido" ? "⚠ " + t.status : "Descargando..."}</span>
        </div>
      </div>
    `).join("");
  } catch (e) {
    list.innerHTML = `<p class="small-note">Error al cargar las descargas activas.</p>`;
  }
}

// ---------------------------------------------------------------------------
// Usuarios conectados (nombre asignado + IP)
// ---------------------------------------------------------------------------
let liveUsersTimer = null;

function startLiveUsersPolling() {
  loadLiveUsers();
  stopLiveUsersPolling();
  liveUsersTimer = setInterval(loadLiveUsers, 2000);
}

function stopLiveUsersPolling() {
  if (liveUsersTimer) {
    clearInterval(liveUsersTimer);
    liveUsersTimer = null;
  }
}

function formatDuration(seconds) {
  if (seconds < 60) return seconds + "s";
  const min = Math.floor(seconds / 60);
  if (min < 60) return min + " min";
  const hrs = Math.floor(min / 60);
  return hrs + " h " + (min % 60) + " min";
}

async function loadLiveUsers() {
  const tbody = document.getElementById("usersTableBody");
  try {
    const data = await apiFetch("/api/admin/users/live");
    if (!data.clients.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="small-note">No hay clientes conectados en este momento.</td></tr>`;
      return;
    }
    const now = Date.now() / 1000;
    tbody.innerHTML = data.clients.map((c) => `
      <tr>
        <td>${escapeHtml(c.device_label || "Dispositivo desconocido")}</td>
        <td class="mono">${escapeHtml(c.ip)}</td>
        <td>${escapeHtml(c.os_family || "—")}</td>
        <td>${formatDuration(Math.round(now - c.first_seen))}</td>
        <td>${c.seconds_ago < 5 ? "En línea ahora" : "hace " + formatDuration(c.seconds_ago)}</td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="small-note">Error al cargar los usuarios conectados.</td></tr>`;
  }
}

// ---------------------------------------------------------------------------
// Patrocinio y Donaciones
// ---------------------------------------------------------------------------
function sponsorLevelLabel(level) {
  return { bronce: "Bronce", plata: "Plata", oro: "Oro", personalizado: "Personalizado" }[level] || level;
}

function donationStatusLabel(status) {
  return { pendiente: "Pendiente", confirmada: "Confirmada", rechazada: "Rechazada", aprobado: "Aprobado" }[status] || status;
}

async function loadDonationsAdmin() {
  await Promise.all([loadDonationSettingsIntoForm(), loadSponsorsTable(), loadDonationsTable()]);
}

async function loadDonationSettingsIntoForm() {
  try {
    const data = await apiFetch("/api/donaciones/info");
    const s = data.settings;
    document.getElementById("donGoalLabel").value = s.donation_goal_label || "";
    document.getElementById("donGoalAmount").value = s.donation_goal_amount || 0;
    document.getElementById("donCurrency").value = s.donation_currency || "USD";
    document.getElementById("donIntroText").value = s.donation_intro_text || "";
    document.getElementById("donWhatsapp").value = s.donation_whatsapp || "";
    document.getElementById("donCryptoInfo").value = s.donation_crypto_info || "";
    document.getElementById("donUsdtInfo").value = s.donation_usdt_info || "";
    document.getElementById("donPyusdInfo").value = s.donation_pyusd_info || "";
    document.getElementById("donTropipayInfo").value = s.donation_tropipay_info || "";
    /* QvaPay info legacy: no se usa con la API */
    document.getElementById("donModuleEnabled").checked = s.donation_module_enabled !== "0";
  } catch (e) {
  }
}

document.getElementById("saveDonationSettingsBtn").addEventListener("click", async () => {
  try {
    await apiFetch("/api/admin/donaciones/settings", {
      method: "POST",
      body: JSON.stringify({
        donation_goal_label: document.getElementById("donGoalLabel").value.trim(),
        donation_goal_amount: document.getElementById("donGoalAmount").value || "0",
        donation_currency: document.getElementById("donCurrency").value.trim() || "USD",
        donation_intro_text: document.getElementById("donIntroText").value.trim(),
        donation_whatsapp: document.getElementById("donWhatsapp").value.trim(),
        donation_crypto_info: "",
        donation_usdt_info: document.getElementById("donUsdtInfo").value.trim(),
        donation_pyusd_info: document.getElementById("donPyusdInfo").value.trim(),
        donation_tropipay_info: document.getElementById("donTropipayInfo").value.trim(),
        donation_qvapay_info: "",
        donation_module_enabled: document.getElementById("donModuleEnabled").checked ? "1" : "0",
      }),
    });
    showToast("Configuración de donaciones guardada.");
  } catch (e) {
    showToast(e.message || "Error al guardar.");
  }
});

async function loadSponsorsTable() {
  const tbody = document.getElementById("sponsorsTableBody");
  try {
    const data = await apiFetch("/api/admin/patrocinadores");
    if (!data.sponsors.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="small-note">Aún no hay patrocinadores registrados.</td></tr>`;
      return;
    }
    tbody.innerHTML = data.sponsors.map((s) => `
      <tr>
        <td>${escapeHtml(s.name)}</td>
        <td>${sponsorLevelLabel(s.level)}</td>
        <td style="font-size:11px;">${escapeHtml(s.email || "")}${s.email && s.phone ? " · " : ""}${escapeHtml(s.phone || "")}</td>
        <td style="font-size:11px; max-width:220px;">${escapeHtml(s.message || "—")}</td>
        <td><span class="badge ${s.status === "aprobado" ? "approved" : s.status === "rechazado" ? "rejected" : "pending"}">${donationStatusLabel(s.status)}</span></td>
        <td style="font-size:11px;">${escapeHtml(s.created_at)}</td>
        <td style="display:flex; gap:6px;">
          ${s.status !== "aprobado" ? `<button class="btn-secondary btn-tactile" style="padding:5px 10px; font-size:11px;" onclick="setSponsorStatus(${s.id}, 'aprobado')">Aprobar</button>` : ""}
          ${s.status !== "rechazado" ? `<button class="btn-danger btn-tactile" onclick="setSponsorStatus(${s.id}, 'rechazado')">Rechazar</button>` : ""}
          <button class="btn-danger btn-tactile" onclick="deleteSponsorRow(${s.id})">Eliminar</button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="small-note">Error al cargar patrocinadores.</td></tr>`;
  }
}

async function setSponsorStatus(id, status) {
  try {
    await apiFetch(`/api/admin/patrocinadores/${id}`, { method: "PUT", body: JSON.stringify({ status }) });
    showToast("Patrocinador actualizado.");
    loadSponsorsTable();
  } catch (e) {
    showToast(e.message || "Error al actualizar.");
  }
}

async function deleteSponsorRow(id) {
  if (!confirm(adminT("js.delete_sponsor"))) return;
  try {
    await apiFetch(`/api/admin/patrocinadores/${id}`, { method: "DELETE" });
    showToast("Patrocinador eliminado.");
    loadSponsorsTable();
  } catch (e) {
    showToast(e.message || "Error al eliminar.");
  }
}

async function loadDonationsTable() {
  const tbody = document.getElementById("donationsTableBody");
  try {
    const data = await apiFetch("/api/admin/donaciones");
    if (!data.donations.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="small-note">Aún no hay donaciones registradas.</td></tr>`;
      return;
    }
    const methodLabel = { crypto: "🪙 Cripto", qvapay: "💳 QvaPay", whatsapp: "📲 WhatsApp" };
    tbody.innerHTML = data.donations.map((d) => `
      <tr>
        <td>${escapeHtml(d.donor_name)}</td>
        <td>${d.amount} ${escapeHtml(d.currency)}</td>
        <td>${methodLabel[d.method] || escapeHtml(d.method)}</td>
        <td style="font-size:11px;">${escapeHtml(d.contact || "—")}</td>
        <td><span class="badge ${d.status === "confirmada" ? "approved" : d.status === "rechazada" ? "rejected" : "pending"}">${donationStatusLabel(d.status)}</span></td>
        <td style="font-size:11px;">${escapeHtml(d.created_at)}</td>
        <td style="display:flex; gap:6px;">
          ${d.status !== "confirmada" ? `<button class="btn-secondary btn-tactile" style="padding:5px 10px; font-size:11px;" onclick="setDonationStatus(${d.id}, 'confirmada')">Confirmar</button>` : ""}
          ${d.status !== "rechazada" ? `<button class="btn-danger btn-tactile" onclick="setDonationStatus(${d.id}, 'rechazada')">Rechazar</button>` : ""}
          <button class="btn-danger btn-tactile" onclick="deleteDonationRow(${d.id})">Eliminar</button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="small-note">Error al cargar donaciones.</td></tr>`;
  }
}

async function setDonationStatus(id, status) {
  try {
    await apiFetch(`/api/admin/donaciones/${id}`, { method: "PUT", body: JSON.stringify({ status }) });
    showToast("Donación actualizada.");
    loadDonationsTable();
  } catch (e) {
    showToast(e.message || "Error al actualizar.");
  }
}

async function deleteDonationRow(id) {
  if (!confirm(adminT("js.delete_donation"))) return;
  try {
    await apiFetch(`/api/admin/donaciones/${id}`, { method: "DELETE" });
    showToast("Donación eliminada.");
    loadDonationsTable();
  } catch (e) {
    showToast(e.message || "Error al eliminar.");
  }
}

// ---------------------------------------------------------------------------
// Inicio
// ---------------------------------------------------------------------------
loadDashboard();

/* -------------------------------------------------------------------------
   IMPORTACION DESDE EL DISPOSITIVO
   ------------------------------------------------------------------------- */
(function initDeviceImport() {
  const filesBtn = document.getElementById("deviceFilesBtn");
  const folderBtn = document.getElementById("deviceFolderBtn");
  const filesInput = document.getElementById("deviceFilesInput");
  const folderInput = document.getElementById("deviceFolderInput");
  const status = document.getElementById("deviceImportStatus");

  if (!filesBtn || !folderBtn || !filesInput || !folderInput) return;

  async function importDeviceFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    if (status) {
      status.textContent = adminT("js.import_preparing", {n: files.length});
    }

    const form = new FormData();

    files.forEach((file) => {
      form.append("files", file, file.webkitRelativePath || file.name);
    });

    try {
      if (status) status.textContent = adminT("js.import_uploading", {n: files.length});

      const result = await apiFetch("/api/admin/import-files", {
        method: "POST",
        body: form,
      });

      if (status) {
        status.textContent =
          `Importación completa: ${result.files_published || 0} archivo(s) publicado(s).`;
      }

      showToast(
        `Importados ${result.files_published || 0} archivo(s) correctamente.`
      );

      filesInput.value = "";
      folderInput.value = "";

      if (typeof loadLocations === "function") {
        loadLocations();
      }
      if (typeof loadAdminLibrary === "function") {
        loadAdminLibrary();
      }
    } catch (e) {
      if (status) {
        status.textContent = e.message || adminT("js.import_error");
      }
      showToast(e.message || adminT("js.import_error"));
    }
  }

  filesBtn.addEventListener("click", () => filesInput.click());
  folderBtn.addEventListener("click", () => folderInput.click());

  filesInput.addEventListener("change", () => {
    importDeviceFiles(filesInput.files);
  });

  folderInput.addEventListener("change", () => {
    importDeviceFiles(folderInput.files);
  });
})();
