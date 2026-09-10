/* QBASwing MyServer - utilidades compartidas */

async function apiFetch(url, options = {}) {
  const opts = Object.assign({}, options);
  if (!(opts.body instanceof FormData)) {
    opts.headers = Object.assign(
      { "Content-Type": "application/json" },
      opts.headers || {}
    );
  }
  const res = await fetch(url, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) {
    const err = new Error((data && data.error) || "Error de red");
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function formatBytes(bytes) {
  const gb = bytes / (1024 ** 3);
  if (gb >= 1) return gb.toFixed(2) + " GB";
  const mb = bytes / (1024 ** 2);
  return mb.toFixed(1) + " MB";
}

function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => toast.classList.remove("show"), 2800);
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
