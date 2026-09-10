/* QBASwing MyServer - selector de idioma compartido (login, setup y resto
   de la interfaz). Los textos en si ya llegan traducidos desde el backend
   via Jinja (T['clave']), asi que este script solo necesita: pintar el
   selector, y al elegir un idioma nuevo, avisar al backend y recargar la
   pagina para que Jinja renderice con el idioma elegido. */

function initLanguageSwitcher(currentLang, options) {
  const wrap = document.getElementById("langSwitcher");
  if (!wrap) return;
  const current = options.find((o) => o.code === currentLang) || options[0];

  wrap.innerHTML = `
    <button class="lang-switcher-btn" id="langSwitcherBtn" type="button">
      <span>${current.flag}</span><span>${current.code.toUpperCase()}</span>
    </button>
    <div class="lang-switcher-menu" id="langSwitcherMenu">
      ${options.map((o) => `<button type="button" data-lang="${o.code}">${o.flag} ${o.label}</button>`).join("")}
    </div>
  `;

  document.getElementById("langSwitcherBtn").addEventListener("click", (e) => {
    e.stopPropagation();
    wrap.classList.toggle("open");
  });
  document.addEventListener("click", () => wrap.classList.remove("open"));

  wrap.querySelectorAll("[data-lang]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const lang = btn.dataset.lang;
      try {
        await fetch("/api/set-language", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ language: lang }),
        });
      } finally {
        window.location.reload();
      }
    });
  });
}
