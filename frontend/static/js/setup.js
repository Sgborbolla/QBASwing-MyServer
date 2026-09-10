/* QBASwing MyServer - asistente de configuración inicial */

const steps = Array.from(document.querySelectorAll(".setup-step-panel"));
const stepDots = Array.from(document.querySelectorAll(".setup-steps .step"));
const errorEl = document.getElementById("setupError");
let currentStep = 0;

function showStep(index) {
  steps.forEach((el, i) => el.classList.toggle("active", i === index));
  stepDots.forEach((el, i) => {
    el.classList.toggle("active", i === index);
    el.classList.toggle("done", i < index);
  });
  currentStep = index;
  errorEl.classList.remove("show");
}

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.classList.add("show");
}

document.querySelectorAll("[data-next]").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (currentStep === 0) {
      const name = document.getElementById("ownerName").value.trim();
      const username = document.getElementById("ownerUsername").value.trim();
      const pass = document.getElementById("ownerPassword").value;
      const confirm = document.getElementById("ownerPasswordConfirm").value;
      if (!name || !username || !pass) { showError(window.APP_T["setup.error.required"]); return; }
      if (pass !== confirm) { showError(window.APP_T["setup.error.passwords_mismatch"]); return; }
      if (pass.length < 6) { showError((window.I18N?.setup_password_min || "La contraseña debe tener al menos 6 caracteres.")); return; }
    }
    if (currentStep < steps.length - 1) showStep(currentStep + 1);
  });
});

document.querySelectorAll("[data-back]").forEach((btn) => {
  btn.addEventListener("click", () => { if (currentStep > 0) showStep(currentStep - 1); });
});

document.getElementById("finishSetupBtn").addEventListener("click", async () => {
  const payload = {
    owner_name: document.getElementById("ownerName").value.trim(),
    owner_email: document.getElementById("ownerEmail").value.trim(),
    owner_username: document.getElementById("ownerUsername").value.trim(),
    owner_password: document.getElementById("ownerPassword").value,
    owner_password_confirm: document.getElementById("ownerPasswordConfirm").value,
    language: document.getElementById("setupLanguage").value,
    business_name: document.getElementById("businessName").value.trim(),
    server_name: document.getElementById("serverName").value.trim(),
  };

  const finishBtn = document.getElementById("finishSetupBtn");
  finishBtn.disabled = true;
  finishBtn.textContent = window.APP_T["common.loading"];

  try {
    const res = await fetch("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      window.location.href = data.redirect;
    } else {
      showStep(0);
      const messages = {
        campos_requeridos: window.APP_T["setup.error.required"],
        contrasenas_no_coinciden: window.APP_T["setup.error.passwords_mismatch"],
        contrasena_corta: (window.I18N?.setup_password_min || "La contraseña debe tener al menos 6 caracteres."),
        ya_inicializado: (window.I18N?.setup_initialized || "Este servidor ya fue configurado."),
      };
      showError(messages[data.error] || (window.I18N?.setup_failed || "No se pudo completar la configuración."));
    }
  } catch (e) {
    showError((window.I18N?.connection_error || "Error de conexión con el servidor."));
  } finally {
    finishBtn.disabled = false;
    finishBtn.textContent = window.APP_T["setup.finish"];
  }
});

showStep(0);
