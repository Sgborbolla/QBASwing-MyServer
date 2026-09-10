
/* QBASwing PUBLIC LIBRARY I18N */
(function () {
    window.QBASwingLibraryI18n = {
        get: function (key, fallback) {
            try {
                if (window.T && typeof window.T === "object") {
                    var parts = key.split(".");
                    var value = window.T;
                    for (var i = 0; i < parts.length; i++) {
                        value = value && value[parts[i]];
                    }
                    if (typeof value === "string" && value.trim()) {
                        return value;
                    }
                }
            } catch (e) {}
            return fallback;
        },

        placeholder: function () {
            return this.get(
                "library.search_placeholder",
                "Buscar películas, series, novelas, documentales..."
            );
        },

        items: function (n) {
            var text = this.get("library.items", "elemento(s)");
            return String(n) + " " + text;
        }
    };
})();

/* QBASwing MyServer - biblioteca del cliente */

const libraryRoot = document.getElementById("libraryRoot");
const ticketPanel = document.getElementById("ticketPanel");
const selCountEl = document.getElementById("selCount");
const selGbEl = document.getElementById("selGb");
const selPriceEl = document.getElementById("selPrice");
const clearSelBtn = document.getElementById("clearSelBtn");
const downloadBtn = document.getElementById("downloadBtn");

let allFiles = [];
let filesById = {};
let selected = new Set();
let currentPricePerGb = 10;
let currentRoundingMode = "none";

// Estado de navegación: { category: null } = pantalla de inicio (filas por
// categoría). { category: "Novelas", path: ["Serie A"] } = dentro de esa
// carpeta, mostrando su contenido tipo explorador.
let view = { category: null, path: [] };

function categoryOrder(cat) {
  const order = ["Películas", "Series", "Novelas", "Documentales", "General"];
  const idx = order.indexOf(cat);
  return idx === -1 ? order.length : idx;
}

function goHome() {
  view = { category: null, path: [] };
  render();
}

function enterFolder(category, segment) {
  if (view.category === category) {
    view = { category, path: [...view.path, segment] };
  } else {
    view = { category, path: [segment] };
  }
  render();
}

function goToBreadcrumb(index) {
  // index -1 = Inicio, 0 = raíz de la categoría, N = dentro de N subcarpetas
  if (index < 0) { goHome(); return; }
  view = { category: view.category, path: view.path.slice(0, index) };
  render();
}

function goBack() {
  if (view.path.length > 0) {
    view = { category: view.category, path: view.path.slice(0, -1) };
    render();
  } else {
    goHome();
  }
}

let searchQuery = "";
let searchDebounceTimer = null;
let searchResultsCache = [];

function render() {
  if (!allFiles.length && !searchQuery.trim()) {
    libraryRoot.innerHTML = `
      <div class="empty-state">
        <div class="big">🎬</div>
        <div class="title">Aún no hay contenido publicado</div>
        <p>El administrador todavía no ha publicado películas, series, novelas o documentales.</p>
      </div>`;
    return;
  }
  if (searchQuery.trim()) {
    renderSearchResults();
  } else if (view.category === null) {
    renderHome();
  } else {
    renderExplorer();
  }
}

/* ---------------------------------------------------------------------
   Búsqueda (Mejora 11): consulta real a /api/search en el backend, que
   filtra "visible = 1" DENTRO de la propia consulta SQL. El cliente nunca
   recibe ni recorre una lista con contenido oculto — la restricción la
   aplica el servidor, no una condición en este archivo.
   --------------------------------------------------------------------- */
async function runSearch(query) {
  try {
    const data = await apiFetch("/api/search?q=" + encodeURIComponent(query));
    searchResultsCache = data.files;
  } catch (e) {
    searchResultsCache = [];
  }
  if (searchQuery.trim() === query) renderSearchResults();
}

function renderSearchResults() {
  const results = searchResultsCache;
  libraryRoot.innerHTML = `
    <div class="explorer-bar">
      <span class="small-note">${results.length} resultado(s) para "${escapeHtml(searchQuery)}"</span>
    </div>
    ${results.length ? "" : `
      <div class="empty-state">
        <div class="big">🔍</div>
        <div class="title">Sin resultados</div>
        <p>No hay nada publicado que coincida con tu búsqueda.</p>
      </div>`}
    <div class="explorer-grid">
      ${results.map((f) => renderCard(f)).join("")}
    </div>
  `;
  bindLibraryEvents();
}

/* ---------------------------------------------------------------------
   Pantalla de inicio (Cambios 9-11): acordeón por categoría. Las
   categorías principales aparecen siempre (con su conteo), colapsadas por
   defecto; al tocar el encabezado se expanden/contraen mostrando sus
   carpetas/archivos de raíz, con indicador ▶ (cerrado) / ▼ (abierto). La
   navegación más profunda (carpetas dentro de una categoría) sigue usando
   el explorador con migas de pan y "Atrás" que ya existía (renderExplorer),
   sin cambios -- aquí solo cambia cómo se ve la pantalla de inicio.
   --------------------------------------------------------------------- */
const CATEGORY_ICONS = {
  "Películas": "🎬", "Series": "📺", "Novelas": "📖",
  "Animes": "🎌", "Documentales": "🎞️", "General": "📁",
};
function categoryIcon(cat) { return CATEGORY_ICONS[cat] || "📁"; }

// Qué categorías están expandidas ahora mismo. Vive en memoria del cliente
// (no en el servidor): es solo estado de la interfaz, no datos.
let expandedCategories = new Set();

function toggleCategory(cat) {
  if (expandedCategories.has(cat)) expandedCategories.delete(cat);
  else expandedCategories.add(cat);
  render();
}

function renderHome() {
  const groups = {};
  allFiles.forEach((f) => {
    if (!groups[f.category]) groups[f.category] = [];
    groups[f.category].push(f);
  });

  const categories = Object.keys(groups).sort((a, b) => categoryOrder(a) - categoryOrder(b));

  libraryRoot.innerHTML = `
    <div class="library-title-row">📚 Biblioteca</div>
    <div class="library-accordion">
      ${categories.map((cat) => {
        const isOpen = expandedCategories.has(cat);
        const entries = isOpen ? groupEntries(groups[cat], "") : [];
        return `
        <section class="accordion-section${isOpen ? " open" : ""}">
          <button type="button" class="accordion-header" data-cat="${escapeHtml(cat)}">
            <span class="accordion-icon">${categoryIcon(cat)}</span>
            <span class="accordion-label">${escapeHtml(cat)}</span>
            <span class="category-count">${groups[cat].length} elemento(s)</span>
            <span class="accordion-arrow">${isOpen ? "▼" : "▶"}</span>
          </button>
          ${isOpen ? `
            <div class="accordion-body">
              <div class="explorer-grid">
                ${entries.map((e) => e.type === "folder" ? renderFolderCard(cat, e) : renderCard(e.file)).join("")}
              </div>
            </div>
          ` : ""}
        </section>`;
      }).join("")}
    </div>
  `;

  bindLibraryEvents();
  document.querySelectorAll(".accordion-header[data-cat]").forEach((btn) => {
    btn.addEventListener("click", () => toggleCategory(btn.dataset.cat));
  });
}

/* ---------------------------------------------------------------------
   Vista de explorador: dentro de una categoría/carpeta, con migas de pan,
   botón "Atrás" y cuadrícula (varias columnas en PC, adaptada en móvil).
   --------------------------------------------------------------------- */
function renderExplorer() {
  const { category, path } = view;
  const prefix = path.join("/");
  const categoryFiles = allFiles.filter((f) => f.category === category);
  const entries = groupEntries(categoryFiles, prefix);

  const crumbs = [`<span class="crumb" data-idx="-1">Inicio</span>`,
    `<span class="sep">/</span>`,
    `<span class="crumb" data-idx="0">${escapeHtml(category)}</span>`];
  path.forEach((seg, i) => {
    crumbs.push(`<span class="sep">/</span>`);
    const isLast = i === path.length - 1;
    crumbs.push(`<span class="crumb ${isLast ? "current" : ""}" data-idx="${i + 1}">${escapeHtml(seg)}</span>`);
  });

  const emptyMsg = entries.length ? "" : `
    <div class="empty-state">
      <div class="big">📁</div>
      <div class="title">Esta carpeta está vacía</div>
    </div>`;

  libraryRoot.innerHTML = `
    <div class="explorer-bar">
      <button class="explorer-back btn-tactile" id="explorerBackBtn" type="button">← Atrás</button>
      <div class="explorer-breadcrumb">${crumbs.join("")}</div>
    </div>
    ${emptyMsg}
    <div class="explorer-grid">
      ${entries.map((e) => e.type === "folder" ? renderFolderCard(category, e) : renderCard(e.file)).join("")}
    </div>
  `;

  document.getElementById("explorerBackBtn").addEventListener("click", goBack);
  document.querySelectorAll(".explorer-breadcrumb .crumb").forEach((el) => {
    el.addEventListener("click", () => goToBreadcrumb(Number(el.dataset.idx)));
  });

  bindLibraryEvents();
}

/**
 * Agrupa los archivos de una categoría en "entradas": carpetas (siguiente
 * segmento después de `prefix`) y archivos sueltos que están exactamente en
 * `prefix`. Así se puede reutilizar tanto en Inicio (prefix="") como al
 * navegar dentro de subcarpetas.
 */
function groupEntries(files, prefix) {
  const folderMap = {};
  const directFiles = [];

  files.forEach((f) => {
    const sub = f.subfolder || "";
    if (sub === prefix) {
      directFiles.push(f);
      return;
    }
    if (prefix && !sub.startsWith(prefix + "/")) return;
    if (!prefix && sub === "") return; // ya cubierto arriba

    const rest = prefix ? sub.slice(prefix.length + 1) : sub;
    const nextSegment = rest.split("/")[0];
    if (!folderMap[nextSegment]) {
      folderMap[nextSegment] = { type: "folder", name: nextSegment, count: 0, coverFileId: null };
    }
    folderMap[nextSegment].count++;
    if (!folderMap[nextSegment].coverFileId && f.has_cover) {
      folderMap[nextSegment].coverFileId = f.id;
    }
  });

  const folders = Object.values(folderMap).sort((a, b) => a.name.localeCompare(b.name));
  const files2 = directFiles.map((f) => ({ type: "file", file: f }));
  return [...folders, ...files2];
}

function bindLibraryEvents() {
  document.querySelectorAll(".media-card[data-id]").forEach((card) => {
    card.addEventListener("click", () => toggleSelect(Number(card.dataset.id)));
  });
  document.querySelectorAll(".preview-btn[data-preview-id]").forEach((btn) => {
    btn.addEventListener("click", () => openPreview(Number(btn.dataset.previewId), btn.dataset.previewKind, btn.dataset.previewName));
  });
  document.querySelectorAll(".folder-card").forEach((card) => {
    card.addEventListener("click", () => enterFolder(card.dataset.cat, card.dataset.seg));
  });
  document.querySelectorAll(".category-title[data-cat]").forEach((el) => {
    el.addEventListener("click", () => enterFolderRoot(el.dataset.cat));
  });

  // Flechas de desplazamiento: solo mueven el scroll horizontal, no tocan selección.
  document.querySelectorAll(".row-arrow").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = document.getElementById(btn.dataset.row);
      if (!row) return;
      const amount = Math.max(row.clientWidth * 0.85, 240);
      row.scrollBy({ left: btn.classList.contains("prev") ? -amount : amount, behavior: "smooth" });
    });
  });
}

// Al hacer clic en el título de una categoría en Inicio, "seg" es null:
// entra a la categoría mostrando su raíz (path vacío), no una subcarpeta.
function enterFolderRoot(category) {
  view = { category, path: [] };
  render();
}

function renderFolderCard(category, entry) {
  const coverHtml = entry.coverFileId
    ? `<img src="/api/thumbnail/${entry.coverFileId}" alt="${escapeHtml(entry.name)}" loading="lazy">`
    : `<div class="folder-icon">📁</div>`;
  return `
    <div class="media-card folder-card" data-cat="${escapeHtml(category)}" data-seg="${escapeHtml(entry.name)}">
      <div class="poster">${coverHtml}</div>
      <div class="card-meta">
        <div class="fname" title="${escapeHtml(entry.name)}">📁 ${escapeHtml(entry.name)}</div>
        <div class="sub"><span class="count-note">${entry.count} elemento(s)</span></div>
      </div>
    </div>
  `;
}

function renderCard(f) {
  const coverHtml = f.has_cover
    ? `<img src="/api/thumbnail/${f.id}" alt="${escapeHtml(f.filename)}" loading="lazy">`
    : `<div class="generic-cover">
         <div class="icon">🎬</div>
         <div class="brand">${escapeHtml(window.APP_NAME || "QBASwing MyServer")}</div>
         <div class="fname">${escapeHtml(f.filename)}</div>
       </div>`;

  return `
    <div class="media-card${selected.has(f.id) ? " selected" : ""}" data-id="${f.id}">
      <div class="poster">
        ${coverHtml}
        <span class="ext-badge">${escapeHtml(f.extension.toUpperCase())}</span>
        <span class="check">✓</span>
        ${["video", "audio", "image", "pdf"].includes(f.content_kind) ? `<button class="preview-btn btn-tactile" data-preview-id="${f.id}" data-preview-kind="${f.content_kind}" data-preview-name="${escapeHtml(f.filename)}" onclick="event.stopPropagation()" type="button">▶ Ver</button>` : ""}
      </div>
      <div class="card-meta">
        <div class="fname" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</div>
        <div class="sub">
          <span class="size">${f.size_gb} GB</span>
          <span>${((window.APP_DISTRIBUTION_MODE || "free") === "free" || f.is_free) ? (window.APP_T ? window.APP_T["common.free"] : (window.I18N?.free || "Gratis")) : "$" + f.price}</span>
        </div>
      </div>
    </div>
  `;
}

function toggleSelect(id) {
  if (selected.has(id)) selected.delete(id);
  else selected.add(id);

  const card = document.querySelector(`.media-card[data-id="${id}"]`);
  if (card) card.classList.toggle("selected", selected.has(id));

  persistSelection();
  updateTicket();
}

// Persistencia de la selección (Mejora 6): si el usuario refresca la
// página por accidente, no debe perder los archivos que ya tenía marcados
// ni el cálculo de GB/precio. Solo guarda IDs (nada de datos sensibles).
const SELECTION_STORAGE_KEY = "qbaswing_myserver_selection";

function persistSelection() {
  try {
    localStorage.setItem(SELECTION_STORAGE_KEY, JSON.stringify(Array.from(selected)));
  } catch (e) { /* almacenamiento no disponible: la selección solo vive en memoria */ }
}

function restoreSelection() {
  try {
    const saved = JSON.parse(localStorage.getItem(SELECTION_STORAGE_KEY) || "[]");
    saved.forEach((id) => { if (filesById[id]) selected.add(id); });
  } catch (e) { /* ignorar datos guardados invalidos */ }
}

const GB_BYTES = 1024 ** 3;

// Redondeo comercial: replica exactamente backend/pricing.py (apply_rounding)
// para que el total mostrado en el panel siempre coincida con el que calcula
// el servidor al crear la solicitud.
function applyRounding(value, mode) {
  let step;
  if (mode === "round5") step = 5;
  else if (mode === "round10") step = 10;
  else return value;

  if (value <= 0) return 0;
  const remainder = value % step;
  if (remainder === 0) return value;
  return value - remainder + step;
}

function computePrice(totalBytes) {
  const totalGb = totalBytes / GB_BYTES;
  const rawPrice = totalGb * currentPricePerGb;
  let finalPrice;
  if (currentRoundingMode === "round5" || currentRoundingMode === "round10") {
    finalPrice = applyRounding(Math.round(rawPrice), currentRoundingMode);
  } else {
    finalPrice = Math.round(rawPrice * 100) / 100;
  }
  return { totalGb, finalPrice };
}

function updateTicket() {
  const items = Array.from(selected).map((id) => filesById[id]).filter(Boolean);
  const totalBytes = items.reduce((sum, f) => sum + (f.size_bytes || 0), 0);
  const { totalGb, finalPrice } = computePrice(totalBytes);

  selCountEl.textContent = items.length;
  selGbEl.textContent = totalGb.toFixed(2) + " GB";
  const isFree = (window.APP_DISTRIBUTION_MODE || "free") === "free";

  const pricePerGbRow = document.getElementById("pricePerGbRow");
  const totalPriceRow = document.getElementById("totalPriceRow");
  if (isFree) {
    if (pricePerGbRow) pricePerGbRow.style.display = "none";
    if (totalPriceRow) totalPriceRow.style.display = "none";
  } else {
    if (pricePerGbRow) pricePerGbRow.style.display = "";
    if (totalPriceRow) totalPriceRow.style.display = "";
    selPriceEl.textContent = finalPrice.toFixed(2);
  }

  ticketPanel.classList.toggle("visible", items.length > 0);
}

clearSelBtn.addEventListener("click", () => {
  selected.clear();
  document.querySelectorAll(".media-card.selected").forEach((c) => c.classList.remove("selected"));
  persistSelection();
  updateTicket();
});

downloadBtn.addEventListener("click", async () => {
  if (selected.size === 0) return;
  const distributionMode = window.APP_DISTRIBUTION_MODE || "free";
  if (distributionMode === "free") {
    // Modo gratuito: no hay paso de pago. Se crea la solicitud ya aprobada
    // y arranca la descarga directamente.
    downloadBtn.disabled = true;
    try {
      const data = await submitRequest("gratuito", null);
      showToast("Solicitud #" + data.request_id + " aprobada automáticamente (modo gratuito).");
      if (typeof startDownload === "function") startDownload(data.request_id);
    } catch (e) {
      showToast(e.message || (window.I18N?.request_failed || "No se pudo iniciar la descarga."));
    } finally {
      downloadBtn.disabled = false;
    }
    return;
  }
  openPaymentModal();
});

async function loadLibrary() {
  try {
    const data = await apiFetch("/api/library");
    currentPricePerGb = data.price_per_gb || 10;
    currentRoundingMode = data.rounding_mode || "none";
    const gbLabel = document.getElementById("selPriceGb");
    if (gbLabel) gbLabel.textContent = "$" + currentPricePerGb;

    allFiles = data.files;
    filesById = {};
    allFiles.forEach((f) => { filesById[f.id] = f; });
    restoreSelection();
    render();
    updateTicket();
  } catch (e) {
    libraryRoot.innerHTML = `
      <div class="empty-state">
        <div class="big">⚠️</div>
        <div class="title">No se pudo cargar la biblioteca</div>
        <p>${escapeHtml(e.message || "")}</p>
      </div>`;
  }
}

loadLibrary();

// El nombre de la marca en la barra superior también funciona como botón
// (window.I18N?.home || "Inicio") para volver desde la vista de explorador.
const brandHomeLink = document.querySelector(".topbar .brand .name");
if (brandHomeLink) {
  brandHomeLink.style.cursor = "pointer";
  brandHomeLink.addEventListener("click", goHome);
}

// ---------------------------------------------------------------------------
// Buscador del cliente (solo sobre contenido publicado, ver renderSearchResults)
// ---------------------------------------------------------------------------
const clientSearchInput = document.getElementById("clientSearchInput");
const clientSearchClear = document.getElementById("clientSearchClear");

clientSearchInput.addEventListener("input", () => {
  searchQuery = clientSearchInput.value;
  clientSearchClear.style.display = searchQuery.trim() ? "inline-flex" : "none";
  clearTimeout(searchDebounceTimer);
  if (!searchQuery.trim()) { render(); return; }
  searchDebounceTimer = setTimeout(() => runSearch(searchQuery.trim()), 250);
});

clientSearchClear.addEventListener("click", () => {
  searchQuery = "";
  clientSearchInput.value = "";
  clientSearchClear.style.display = "none";
  render();
});

// Latido periódico: mantiene esta sesión visible en "Usuarios conectados"
// del panel de administrador mientras la pestaña siga abierta.
setInterval(() => {
  apiFetch("/api/ping").catch(() => {});
}, 20000);

// ---------------------------------------------------------------------------
// Modal de pago: Paso 1 elegir método -> Paso 2 completar (efectivo o
// transferencia con verificación obligatoria) -> SOLO ENTONCES se crea la
// solicitud. Antes se creaba la solicitud de inmediato y quedaba "pendiente"
// aprobable aunque el cliente nunca completara la verificación; eso ya no
// puede pasar porque ahora la solicitud no existe hasta este paso.
// ---------------------------------------------------------------------------
const paymentModal = document.getElementById("paymentModal");
const closePaymentModal = document.getElementById("closePaymentModal");
const paymentMethodStep = document.getElementById("paymentMethodStep");
const paymentTransferStep = document.getElementById("paymentTransferStep");
const paymentCashStep = document.getElementById("paymentCashStep");
const methodStepCount = document.getElementById("methodStepCount");
const methodStepPrice = document.getElementById("methodStepPrice");
const chooseTransferBtn = document.getElementById("chooseTransferBtn");
const chooseCashBtn = document.getElementById("chooseCashBtn");
const backToMethodBtn = document.getElementById("backToMethodBtn");
const backToMethodBtn2 = document.getElementById("backToMethodBtn2");
const confirmCashBtn = document.getElementById("confirmCashBtn");
const accountNumberText = document.getElementById("accountNumberText");
const accountMessageText = document.getElementById("accountMessageText");
const copyAccountBtn = document.getElementById("copyAccountBtn");
const qrImage = document.getElementById("qrImage");
const verificationText = document.getElementById("verificationText");
const sendVerificationBtn = document.getElementById("sendVerificationBtn");

function showPaymentStep(step) {
  paymentMethodStep.style.display = step === "method" ? "block" : "none";
  paymentTransferStep.style.display = step === "transfer" ? "block" : "none";
  paymentCashStep.style.display = step === "cash" ? "block" : "none";
}

function openPaymentModal() {
  const items = Array.from(selected).map((id) => filesById[id]).filter(Boolean);
  const totalBytes = items.reduce((sum, f) => sum + (f.size_bytes || 0), 0);
  const { finalPrice } = computePrice(totalBytes);
  methodStepCount.textContent = items.length;
  methodStepPrice.textContent = "$" + finalPrice.toFixed(2);
  verificationText.value = "";
  showPaymentStep("method");
  paymentModal.classList.add("show");
}

closePaymentModal.addEventListener("click", () => paymentModal.classList.remove("show"));
backToMethodBtn.addEventListener("click", () => showPaymentStep("method"));
backToMethodBtn2.addEventListener("click", () => showPaymentStep("method"));

chooseTransferBtn.addEventListener("click", async () => {
  showPaymentStep("transfer");
  try {
    const info = await apiFetch("/api/payment-info");
    accountNumberText.textContent = info.account_number || "—";
    accountMessageText.textContent = info.account_message;
    const qrWrap = qrImage.closest(".pay-option");
    if (info.qr_image) {
      qrImage.src = info.qr_image;
      if (qrWrap) qrWrap.style.display = "";
    } else if (qrWrap) {
      qrWrap.style.display = "none";
    }
    const verifyIntro = document.getElementById("verifyIntroText");
    if (verifyIntro) {
      verifyIntro.textContent = `Después de pagar mediante ${info.method_label}, copia y pega aquí el mensaje o comprobante recibido.`;
    }
  } catch (e) {
    showToast("No se pudo cargar la información de pago.");
  }
});

chooseCashBtn.addEventListener("click", () => showPaymentStep("cash"));

copyAccountBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(accountNumberText.textContent.trim());
    showToast((window.I18N?.account_copied || "Número de cuenta copiado."));
  } catch (e) {
    showToast((window.I18N?.copy_failed || "No se pudo copiar. Selecciona el número manualmente."));
  }
});

async function submitRequest(paymentMethod, verificationMessage) {
  const data = await apiFetch("/api/requests", {
    method: "POST",
    body: JSON.stringify({
      file_ids: Array.from(selected),
      payment_method: paymentMethod,
      verification_message: verificationMessage || undefined,
    }),
  });
  selected.clear();
  document.querySelectorAll(".media-card.selected").forEach((c) => c.classList.remove("selected"));
  persistSelection();
  updateTicket();
  paymentModal.classList.remove("show");
  return data;
}

sendVerificationBtn.addEventListener("click", async () => {
  const message = verificationText.value.trim();
  if (!message) {
    // Regla del Módulo 5: sin mensaje de verificación, la solicitud NUNCA se
    // envía. No basta con avisar y dejar seguir; aquí se detiene de verdad.
    showToast((window.I18N?.verification_required || "Debes pegar el mensaje de verificación antes de enviar la solicitud."));
    return;
  }
  sendVerificationBtn.disabled = true;
  sendVerificationBtn.textContent = "Enviando...";
  try {
    const data = await submitRequest("transferencia", message);
    showToast(`Solicitud #${data.request_id} enviada con tu verificación. Esperando aprobación.`);
  } catch (e) {
    showToast(e.message || "No se pudo enviar la solicitud.");
  } finally {
    sendVerificationBtn.disabled = false;
    sendVerificationBtn.textContent = "Enviar solicitud";
  }
});

confirmCashBtn.addEventListener("click", async () => {
  confirmCashBtn.disabled = true;
  confirmCashBtn.textContent = "Enviando...";
  try {
    const data = await submitRequest("efectivo", null);
    showToast(`Solicitud #${data.request_id} enviada. Pendiente de cobro en efectivo.`);
  } catch (e) {
    showToast(e.message || "No se pudo enviar la solicitud.");
  } finally {
    confirmCashBtn.disabled = false;
    confirmCashBtn.textContent = "Confirmar solicitud en efectivo";
  }
});

// ---------------------------------------------------------------------------
// Modal "Mis solicitudes"
// ---------------------------------------------------------------------------
const requestsModal = document.getElementById("requestsModal");
const myRequestsBtn = document.getElementById("myRequestsBtn");
const closeRequestsModal = document.getElementById("closeRequestsModal");
const myRequestsList = document.getElementById("myRequestsList");

function paymentStatusLabel(status) {
  return {
    pendiente: "Pendiente de pago",
    pendiente_efectivo: "💵 Pendiente de cobro en efectivo",
    verificacion_enviada: "Verificación enviada",
    aprobado: "Aprobado",
    rechazado: "Rechazado",
  }[status] || status;
}

function statusBadgeClass(status) {
  return { pending: "pending", approved: "approved", rejected: "rejected", completed: "completed" }[status] || "pending";
}

function requestStatusLabel(status) {
  return { pending: "Pendiente", approved: "Aprobada", rejected: "Rechazada", completed: "✅ Completada" }[status] || status;
}

// Cambio 1/2/3: una solicitud 'approved' puede tener progreso ya iniciado
// (persistido en SQLite, no inventado). Esto decide si el botón dice
// "Descargar" (nunca empezada) o "Continuar descarga" (ya en curso), y
// nunca vuelve a ofrecer una solicitud ya 'completed'.
function progressSummary(r) {
  const progress = r.progress || {};
  const entries = r.file_ids.map((id) => progress[String(id)]).filter(Boolean);
  if (!entries.length) return { started: false, pct: 0 };
  const received = entries.reduce((sum, p) => sum + (p.received_bytes || 0), 0);
  const total = r.total_size_bytes || entries.reduce((sum, p) => sum + (p.total_bytes || 0), 0) || 1;
  const anyStarted = entries.some((p) => (p.received_bytes || 0) > 0);
  return { started: anyStarted, pct: Math.min(100, Math.round((received / total) * 100)) };
}

async function loadMyRequests() {
  myRequestsList.innerHTML = `<p class="small-note">Cargando...</p>`;
  try {
    const data = await apiFetch("/api/my-requests");
    if (!data.requests.length) {
      myRequestsList.innerHTML = `<p class="small-note">Aún no has hecho ninguna solicitud.</p>`;
      return;
    }
    myRequestsList.innerHTML = data.requests.map((r) => {
      const prog = progressSummary(r);
      let actionHtml = "";
      if (r.status === "approved") {
        actionHtml = prog.started
          ? `<div class="small-note" style="margin-top:6px;">🔄 En curso (~${prog.pct}%)</div>
             <button class="btn-primary btn-tactile" style="margin-top:8px;" onclick="startDownload(${r.id})">Continuar descarga</button>`
          : `<button class="btn-primary btn-tactile" style="margin-top:8px;" onclick="startDownload(${r.id})">Descargar</button>`;
      }
      return `
      <div class="req-card">
        <div class="top">
          <strong>#${r.id}</strong>
          <span class="badge ${statusBadgeClass(r.status)}">${requestStatusLabel(r.status)}</span>
        </div>
        <div class="small-note">${r.file_ids.length} archivo(s) · ${(r.total_size_bytes / (1024 ** 3)).toFixed(2)} GB${(window.APP_DISTRIBUTION_MODE || "free") === "free" ? "" : " · $" + r.total_price}</div>
        <div class="small-note">${r.payment_method === "efectivo" ? "💵 Efectivo" : "📱 Transferencia/QR"} · ${paymentStatusLabel(r.payment_status)}</div>
        ${actionHtml}
      </div>
    `;
    }).join("");
  } catch (e) {
    myRequestsList.innerHTML = `<p class="small-note">Error al cargar tus solicitudes.</p>`;
  }
}

myRequestsBtn.addEventListener("click", () => {
  requestsModal.classList.add("show");
  loadMyRequests();
});
closeRequestsModal.addEventListener("click", () => requestsModal.classList.remove("show"));

// ---------------------------------------------------------------------------
// Descarga con progreso (barra individual + barra general)
// ---------------------------------------------------------------------------
const downloadOverlay = document.getElementById("downloadOverlay");
const generalFill = document.getElementById("generalFill");
const generalPct = document.getElementById("generalPct");
const generalGb = document.getElementById("generalGb");
const fileProgressList = document.getElementById("fileProgressList");
const closeDownloadOverlay = document.getElementById("closeDownloadOverlay");

closeDownloadOverlay.addEventListener("click", () => downloadOverlay.classList.remove("show"));

// ---------------------------------------------------------------------------
// Descarga con progreso, PAUSA, REANUDACIÓN (real, por rangos de bytes) y
// CANCELACIÓN. Cada archivo mantiene su propio estado; reanudar vuelve a
// pedir el archivo con la cabecera "Range: bytes=<recibidos>-" para no
// reenviar lo que ya se tenía, aprovechando el soporte de Range del server.
// ---------------------------------------------------------------------------
const MAX_RETRIES = 4;
let fileStates = {}; // id -> { filename, status, receivedBytes, totalBytes, chunks, controller }
let activeRequestId = null;
let totalRequestedBytes = 1;

function statusLabelFor(status) {
  return {
    pendiente: "⏳ Pendiente",
    descargando: "🔄 Descargando...",
    pausado: "⏸ Pausado",
    finalizado: "✅ Finalizado",
    cancelado: "❌ Cancelado",
    error: "❌ Error de conexión",
  }[status] || status;
}

function updateGeneralProgress(totalRequested) {
  const totalLoaded = Object.values(fileStates).reduce((sum, s) => sum + s.receivedBytes, 0);
  const pct = totalRequested ? Math.min(100, Math.round((totalLoaded / totalRequested) * 100)) : 0;
  generalFill.style.width = pct + "%";
  generalPct.textContent = pct + "%";
  generalGb.textContent = (totalLoaded / (1024 ** 3)).toFixed(2) + " / " + (totalRequested / (1024 ** 3)).toFixed(2) + " GB";
  const allDone = Object.values(fileStates).every((s) => s.status === "finalizado" || s.status === "cancelado");
  if (allDone) {
    document.querySelector(".download-box h3").textContent = "✓ Listo";
    closeDownloadOverlay.style.display = "inline-block";
  }
}

function renderFileRow(id) {
  const row = document.getElementById("file-row-" + id);
  if (!row) return;
  const s = fileStates[id];
  const pct = s.totalBytes ? Math.min(100, Math.round((s.receivedBytes / s.totalBytes) * 100)) : 0;
  row.querySelector(".fname").textContent = s.filename;
  row.querySelector(".pct").textContent = pct + "%";
  row.querySelector(".fill").style.width = pct + "%";
  row.querySelector(".status").textContent = statusLabelFor(s.status);
  row.classList.toggle("done", s.status === "finalizado");
  row.classList.toggle("error", s.status === "error");

  // Los botones solo se reconstruyen cuando el ESTADO cambia (pendiente ->
  // descargando -> pausado, etc.), no en cada fragmento recibido. Antes se
  // regeneraba el HTML de los botones en cada actualización de progreso
  // (varias veces por segundo), lo que podía hacer que un clic llegara justo
  // cuando el botón se estaba re-creando.
  const actions = row.querySelector(".file-actions");
  if (actions.dataset.renderedStatus === s.status) {
    updateGeneralProgress(totalRequestedBytes);
    return;
  }
  actions.dataset.renderedStatus = s.status;

  const buttons = [];
  if (s.status === "descargando") {
    buttons.push(`<button class="btn-secondary btn-tactile" data-action="pause" data-id="${id}">⏸ Pausar</button>`);
    buttons.push(`<button class="btn-secondary btn-tactile" data-action="cancel" data-id="${id}">✕ Cancelar</button>`);
  } else if (s.status === "pausado") {
    buttons.push(`<button class="btn-secondary btn-tactile" data-action="resume" data-id="${id}">▶ Reanudar</button>`);
    buttons.push(`<button class="btn-secondary btn-tactile" data-action="cancel" data-id="${id}">✕ Cancelar</button>`);
  } else if (s.status === "error") {
    buttons.push(`<button class="btn-secondary btn-tactile" data-action="resume" data-id="${id}">↻ Reintentar</button>`);
  }
  actions.innerHTML = buttons.join("");
  actions.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => handleFileAction(btn.dataset.action, Number(btn.dataset.id)));
  });

  updateGeneralProgress(totalRequestedBytes);
}

function handleFileAction(action, id) {
  const s = fileStates[id];
  if (!s) return;
  if (action === "pause") {
    s.status = "pausado";
    if (s.controller) s.controller.abort();
    reportProgress(activeRequestId, id, "pausado");
    renderFileRow(id);
  } else if (action === "cancel") {
    s.status = "cancelado";
    if (s.controller) s.controller.abort();
    s.chunks = [];
    renderFileRow(id);
  } else if (action === "resume") {
    s.status = "descargando";
    renderFileRow(id);
    downloadOneFile(activeRequestId, id).catch(() => {});
  }
}

function parseFilenameFromResponse(res, id) {
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  return match ? match[1] : ("archivo_" + id);
}

// ---------------------------------------------------------------------------
// Persistencia REAL en disco (Cambio 3/4/5): cuando el navegador soporta la
// File System Access API (Chrome/Edge en Android y Windows -- exactamente lo
// que se usa para probar este proyecto), los bytes se escriben directo al
// archivo elegido por el usuario a medida que llegan. El archivo en disco ES
// el estado persistido: si se cierra la pestaña/sesión a mitad de descarga,
// al volver se retoma desde el tamaño real ya escrito, sin inventar nada.
//
// Si el navegador no soporta esta API, o el usuario cancela el selector, o
// el permiso no se puede reobtener, se usa automáticamente el método
// anterior (acumular en memoria y entregar el archivo al terminar) —
// EXACTAMENTE como funcionaba antes, sin ningún cambio de comportamiento.
// Cualquier error inesperado en la ruta de disco también cae de vuelta a
// este método, nunca deja una descarga a medias sin manejar.
// ---------------------------------------------------------------------------
const FS_ACCESS_SUPPORTED = typeof window.showSaveFilePicker === "function";

function openHandleDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("qbaswing_myserver_fs_handles_db", 1);
    req.onupgradeneeded = () => { req.result.createObjectStore("handles"); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function saveFileHandle(key, handle) {
  try {
    const idb = await openHandleDB();
    await new Promise((resolve, reject) => {
      const tx = idb.transaction("handles", "readwrite");
      tx.objectStore("handles").put(handle, key);
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  } catch (e) { /* IndexedDB no disponible: no rompe la descarga actual */ }
}

async function loadFileHandle(key) {
  try {
    const idb = await openHandleDB();
    return await new Promise((resolve, reject) => {
      const tx = idb.transaction("handles", "readonly");
      const req = tx.objectStore("handles").get(key);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  } catch (e) { return null; }
}

// Intenta obtener (o crear) el archivo real en disco para request+file, y
// devuelve cuántos bytes ya tiene escritos de verdad -- la única fuente de
// verdad para reanudar, no una barra visual ni un número guardado a ciegas.
async function acquireDiskHandle(requestId, id, suggestedName) {
  if (!FS_ACCESS_SUPPORTED) return null;
  const key = requestId + ":" + id;
  try {
    let handle = await loadFileHandle(key);
    if (handle) {
      let perm = await handle.queryPermission({ mode: "readwrite" });
      if (perm !== "granted") perm = await handle.requestPermission({ mode: "readwrite" });
      if (perm !== "granted") handle = null;
    }
    if (!handle) {
      handle = await window.showSaveFilePicker({ suggestedName });
      await saveFileHandle(key, handle);
    }
    const file = await handle.getFile();
    return { handle, diskBytes: file.size };
  } catch (e) {
    return null; // cancelado, sin permiso, o no soportado realmente: se usa el método de memoria
  }
}

async function closeDiskWritable(s) {
  if (s.diskWritable) {
    try { await s.diskWritable.close(); } catch (e) { /* ya cerrado o inválido */ }
    s.diskWritable = null;
  }
}

// ---------------------------------------------------------------------------
// Checkpoint de progreso persistido en SQLite (Cambio 3/4): se reporta al
// servidor periódicamente y en cada cambio de estado, para que "Mis
// solicitudes" pueda mostrar "EN CURSO ~20%" incluso después de cerrar
// sesión o reiniciar el servidor.
// ---------------------------------------------------------------------------
function reportProgress(requestId, id, status) {
  const s = fileStates[id];
  if (!s) return;
  apiFetch("/api/download-progress", {
    method: "POST",
    body: JSON.stringify({
      request_id: requestId, file_id: id,
      received_bytes: s.receivedBytes, total_bytes: s.totalBytes, status,
    }),
  }).catch(() => {});
}

async function downloadOneFile(requestId, id) {
  const s = fileStates[id];
  let attempt = 0;

  // Solo se intenta una vez por invocación (pausar/reanudar vuelve a llamar
  // a downloadOneFile, así que esto se reevalúa en cada reanudación real).
  if (FS_ACCESS_SUPPORTED && s.diskInfo === undefined) {
    s.diskInfo = await acquireDiskHandle(requestId, id, s.filename !== ("Archivo #" + id) ? s.filename : undefined);
    if (s.diskInfo && s.diskInfo.diskBytes > s.receivedBytes) {
      // El archivo en disco ya tiene más bytes que lo que recordábamos en
      // memoria (ej. se retoma tras cerrar sesión): el disco manda.
      s.receivedBytes = s.diskInfo.diskBytes;
    }
  }

  let checkpointTimer = setInterval(() => {
    if (s.status === "descargando") reportProgress(requestId, id, "descargando");
  }, 3000);

  const cleanupTimer = () => { clearInterval(checkpointTimer); checkpointTimer = null; };

  while (attempt <= MAX_RETRIES) {
    if (s.status === "pausado" || s.status === "cancelado") {
      cleanupTimer();
      await closeDiskWritable(s);
      reportProgress(requestId, id, s.status === "pausado" ? "pausado" : "pausado");
      return;
    }
    const controller = new AbortController();
    s.controller = controller;
    try {
      const headers = s.receivedBytes > 0 ? { Range: `bytes=${s.receivedBytes}-` } : {};
      const res = await fetch(`/api/download/${requestId}/${id}`, { signal: controller.signal, headers });
      if (!res.ok && res.status !== 206) throw new Error("HTTP " + res.status);

      s.filename = parseFilenameFromResponse(res, id);
      if (s.totalBytes === 0) {
        const range = res.headers.get("Content-Range"); // "bytes start-end/total"
        if (range && range.includes("/")) {
          s.totalBytes = Number(range.split("/")[1]) || 0;
        } else {
          s.totalBytes = Number(res.headers.get("Content-Length")) || 0;
        }
      }

      if (s.diskInfo && !s.diskWritable) {
        try {
          s.diskWritable = await s.diskInfo.handle.createWritable({ keepExistingData: true });
        } catch (e) {
          s.diskInfo = null; // no se pudo abrir para escritura: cae al método de memoria
        }
      }

      const writeStart = s.receivedBytes;
      let writePos = writeStart;
      const reader = res.body.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (s.status === "pausado" || s.status === "cancelado") {
          cleanupTimer();
          await closeDiskWritable(s);
          reportProgress(requestId, id, "pausado");
          return;
        }
        if (s.diskWritable) {
          try {
            await s.diskWritable.write({ type: "write", position: writePos, data: value });
            writePos += value.length;
          } catch (e) {
            // Falla inesperada escribiendo a disco: se cae al método de
            // memoria para el resto de ESTE archivo, sin perder lo ya
            // recibido en este intento (no rompe la descarga).
            s.diskWritable = null;
            s.diskInfo = null;
            s.chunks.push(value);
          }
        } else {
          s.chunks.push(value);
        }
        s.receivedBytes += value.length;
        renderFileRow(id);
      }

      if (s.diskWritable) {
        // El archivo ya se escribió directo al disco elegido por el
        // usuario: no hace falta armar un Blob ni disparar otra descarga.
        await closeDiskWritable(s);
      } else {
        // Método anterior, sin cambios: entregar el archivo al navegador.
        const blob = new Blob(s.chunks);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = s.filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        s.chunks = []; // liberar memoria
      }

      cleanupTimer();
      s.status = "finalizado";
      renderFileRow(id);
      reportProgress(requestId, id, "completado");
      return;
    } catch (err) {
      if (s.status === "pausado" || s.status === "cancelado") {
        cleanupTimer();
        await closeDiskWritable(s);
        if (s.status === "pausado") reportProgress(requestId, id, "pausado");
        return;
      }
      await closeDiskWritable(s);
      attempt += 1;
      if (attempt > MAX_RETRIES) {
        cleanupTimer();
        s.status = "error";
        renderFileRow(id);
        reportProgress(requestId, id, "pausado");
        showToast(`No se pudo completar "${s.filename}" tras varios intentos.`);
        return;
      }
      // Reintento con espera creciente; la próxima vuelta reanuda desde
      // s.receivedBytes gracias a la cabecera Range, no desde cero.
      await new Promise((r) => setTimeout(r, 800 * attempt));
    }
  }
  cleanupTimer();
}

async function startDownload(requestId) {
  // Evita duplicar el proceso de descarga si ya hay uno en curso para esta
  // misma solicitud (ej. doble clic en "Descargar"): simplemente vuelve a
  // mostrar el panel existente en vez de arrancar todo de nuevo.
  if (activeRequestId === requestId && Object.values(fileStates).some((s) => s.status === "descargando" || s.status === "pausado")) {
    requestsModal.classList.remove("show");
    downloadOverlay.classList.add("show");
    return;
  }
  requestsModal.classList.remove("show");
  let req;
  try {
    req = await apiFetch(`/api/requests/${requestId}`);
  } catch (e) {
    showToast("No se pudo obtener la solicitud.");
    return;
  }
  const fileIds = JSON.parse(req.file_ids) || [];
  if (!fileIds.length) return;

  activeRequestId = requestId;
  fileStates = {};
  totalRequestedBytes = req.total_size_bytes || 1;

  downloadOverlay.classList.add("show");
  closeDownloadOverlay.style.display = "none";
  document.querySelector(".download-box h3").textContent = "Descargando...";
  fileProgressList.innerHTML = "";
  generalFill.style.width = "0%";
  generalPct.textContent = "0%";

  // Progreso persistido en SQLite (Cambio 3/4): si ya se había avanzado
  // algo de este archivo antes (incluso en una sesión anterior), se parte
  // de ese punto en vez de mostrar "Pendiente" como si fuera nuevo.
  const persistedProgress = req.progress || {};

  fileIds.forEach((id) => {
    const p = persistedProgress[String(id)];
    const alreadyDone = p && p.status === "completado";
    const startBytes = p && p.status !== "completado" ? (p.received_bytes || 0) : 0;
    fileStates[id] = {
      filename: "Archivo #" + id, status: alreadyDone ? "finalizado" : "pendiente",
      receivedBytes: alreadyDone ? (p.total_bytes || 0) : startBytes,
      totalBytes: (p && p.total_bytes) || 0,
      chunks: [], controller: null, diskInfo: undefined, diskWritable: null,
    };
    const startPct = fileStates[id].totalBytes
      ? Math.min(100, Math.round((fileStates[id].receivedBytes / fileStates[id].totalBytes) * 100)) : 0;
    const row = document.createElement("div");
    row.className = "file-progress-row";
    row.id = "file-row-" + id;
    row.innerHTML = `
      <div class="top"><span class="fname">Archivo #${id}</span><span class="pct">${startPct}%</span></div>
      <div class="bar"><div class="fill" style="width:${startPct}%;"></div></div>
      <div class="status">${startBytes > 0 ? "En curso, retomando..." : "Pendiente..."}</div>
      <div class="file-actions"></div>
    `;
    fileProgressList.appendChild(row);
  });

  for (const id of fileIds) {
    if (fileStates[id].status === "cancelado" || fileStates[id].status === "finalizado") {
      renderFileRow(id);
      continue;
    }
    fileStates[id].status = "descargando";
    renderFileRow(id);
    await downloadOneFile(requestId, id);
  }

  updateGeneralProgress(totalRequestedBytes);
}

// ---------------------------------------------------------------------------
// Reproductor / visor en navegador (video, audio, imagen, PDF)
// ---------------------------------------------------------------------------
const previewOverlay = document.getElementById("previewOverlay");
const previewContent = document.getElementById("previewContent");
const previewTitle = document.getElementById("previewTitle");
const closePreviewBtn = document.getElementById("closePreviewOverlay");

function openPreview(id, kind, name) {
  if (!previewOverlay) return;
  previewTitle.textContent = name || "";
  const src = `/api/preview/${id}`;
  let html = "";
  if (kind === "video") {
    html = `<video src="${src}" controls autoplay style="max-width:100%; max-height:70vh; border-radius:8px;"></video>`;
  } else if (kind === "audio") {
    html = `<audio src="${src}" controls autoplay style="width:100%;"></audio>`;
  } else if (kind === "image") {
    html = `<img src="${src}" alt="${escapeHtml(name || "")}" style="max-width:100%; max-height:70vh; border-radius:8px;">`;
  } else if (kind === "pdf") {
    html = `<iframe src="${src}" style="width:100%; height:70vh; border:none; border-radius:8px; background:#fff;"></iframe>`;
  } else {
    html = `<p class="small-note">Este tipo de archivo no se puede previsualizar en el navegador.</p>`;
  }
  previewContent.innerHTML = html;
  previewOverlay.classList.add("show");
}

function closePreview() {
  if (!previewOverlay) return;
  previewOverlay.classList.remove("show");
  previewContent.innerHTML = ""; // detiene la reproducción de video/audio al cerrar
}

closePreviewBtn?.addEventListener("click", closePreview);
previewOverlay?.addEventListener("click", (e) => {
  if (e.target === previewOverlay) closePreview();
});
