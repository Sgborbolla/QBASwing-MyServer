/* QBASwing MyServer - login */

const usernameEl = document.getElementById("username");
const passwordEl = document.getElementById("password");
const rememberEl = document.getElementById("remember");
const loginBtn = document.getElementById("loginBtn");
const errorEl = document.getElementById("loginError");

const ERROR_MESSAGES = {
  credenciales_invalidas: window.APP_T["login.error.invalid"],
  cuenta_desactivada: window.APP_T["login.error.inactive"],
  no_inicializado: "Este servidor todavía no ha sido configurado.",
  demasiados_intentos: "Demasiados intentos fallidos. Espera 2 minutos antes de volver a intentarlo.",
};

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.classList.add("show");
}

async function doLogin() {
  const username = usernameEl.value.trim();
  const password = passwordEl.value;
  errorEl.classList.remove("show");

  if (!username || (!password && username.toLowerCase() !== "invitado")) {
    showError(window.APP_T["setup.error.required"]);
    return;
  }

  loginBtn.disabled = true;
  loginBtn.textContent = window.APP_T["common.loading"];

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, remember: rememberEl.checked }),
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      window.location.href = data.redirect;
    } else {
      showError(ERROR_MESSAGES[data.error] || window.APP_T["login.error.invalid"]);
    }
  } catch (e) {
    showError("Error de conexión con el servidor.");
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = window.APP_T["login.submit"];
  }
}

loginBtn.addEventListener("click", doLogin);
passwordEl.addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
usernameEl.addEventListener("keydown", (e) => { if (e.key === "Enter") passwordEl.focus(); });

// ---------------------------------------------------------------------------
// Carrusel promocional (elegante, ligero, no depende de CDNs externos)
// ---------------------------------------------------------------------------
(function initPromoCarousel() {
  const track = document.getElementById("loginPromoTrack");
  const dots = document.querySelectorAll("#loginPromoDots span");
  if (!track || !dots.length) return;
  let index = 0;
  setInterval(() => {
    index = (index + 1) % dots.length;
    track.style.transform = `translateX(-${index * 100}%)`;
    dots.forEach((d, i) => d.classList.toggle("active", i === index));
  }, 3500);
})();
