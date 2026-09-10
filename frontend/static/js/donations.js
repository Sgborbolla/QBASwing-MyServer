/* QBASwing MyServer - Módulo de Patrocinio y Donaciones (página pública) */

document.addEventListener("DOMContentLoaded", () => {
  const settings = window.DONATION_SETTINGS || {};

  // --- WhatsApp: arma el enlace wa.me a partir del número configurado ---
  const waDigits = String(settings.donation_whatsapp || "+53 58147030").replace(/[^0-9]/g, "");
  const waLink = waDigits ? `https://wa.me/${waDigits}` : "#";
  const waCta = document.getElementById("whatsappCta");
  const waInfoLink = document.getElementById("whatsappInfoLink");
  if (waCta) waCta.href = waLink;
  if (waInfoLink) waInfoLink.href = waLink;

  // --- Pestañas: patrocinador / donación ---
  document.querySelectorAll(".donation-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".donation-tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".donation-form-section").forEach((s) => s.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(tab.dataset.target).classList.add("active");
    });
  });

  // --- Método de donación: muestra la info correspondiente ---
  const methodSelect = document.getElementById("donationMethod");
  function updateMethodInfo() {
    document.querySelectorAll(".donation-method-info").forEach((el) => el.classList.remove("active"));
    const map = { crypto: "cryptoInfo", tropipay: "tropipayInfo", qvapay: "qvapayInfo", whatsapp: "whatsappInfo" };
    const target = document.getElementById(map[methodSelect.value]);
    if (target) target.classList.add("active");
  }
  if (methodSelect) {
    methodSelect.addEventListener("change", updateMethodInfo);
    updateMethodInfo();
  }

  // --- Enviar registro de patrocinador ---
  const sendSponsorBtn = document.getElementById("sendSponsorBtn");
  if (sendSponsorBtn) {
    sendSponsorBtn.addEventListener("click", async () => {
      const name = document.getElementById("sponsorName").value.trim();
      if (!name) { showToast((window.I18N?.name_required || "Escribe tu nombre o el de tu empresa.")); return; }
      sendSponsorBtn.disabled = true;
      try {
        await apiFetch("/api/donaciones/patrocinador", {
          method: "POST",
          body: JSON.stringify({
            name,
            email: document.getElementById("sponsorEmail").value.trim(),
            phone: document.getElementById("sponsorPhone").value.trim(),
            level: document.getElementById("sponsorLevel").value,
            message: document.getElementById("sponsorMessage").value.trim(),
          }),
        });
        showToast((window.I18N?.sponsor_sent || "¡Gracias! Tu registro de patrocinio fue enviado."));
        document.getElementById("sponsorName").value = "";
        document.getElementById("sponsorEmail").value = "";
        document.getElementById("sponsorPhone").value = "";
        document.getElementById("sponsorMessage").value = "";
      } catch (e) {
        showToast(e.message || (window.I18N?.send_failed || "No se pudo enviar el registro."));
      } finally {
        sendSponsorBtn.disabled = false;
      }
    });
  }

  // --- Enviar donación ---
  const sendDonationBtn = document.getElementById("sendDonationBtn");
  if (sendDonationBtn) {
    sendDonationBtn.addEventListener("click", async () => {
      const amount = parseFloat(document.getElementById("donationAmount").value || "0");
      const method = methodSelect ? methodSelect.value : "whatsapp";
      const currency = document.getElementById("donationCurrency").value.trim() || "USD";
      const donorName = document.getElementById("donorName").value.trim();
      const contact = document.getElementById("donorContact").value.trim();
      const message = document.getElementById("donationMessage").value.trim();

      if (!Number.isFinite(amount) || amount <= 0) {
        showToast((window.I18N?.valid_amount || "Introduce un monto válido."));
        return;
      }

      sendDonationBtn.disabled = true;

      try {
        const payload = {
          donor_name: donorName,
          contact,
          amount,
          currency,
          method,
          message,
        };

        if (method === "qvapay") {
          if (currency.toUpperCase() !== "USD") {
            showToast((window.I18N?.qvapay_usd || "QvaPay requiere USD para este pago."));
            return;
          }

          const data = await apiFetch("/api/donaciones/qvapay/create", {
            method: "POST",
            body: JSON.stringify(payload),
          });

          if (!data.payment_url) {
            throw new Error((window.I18N?.qvapay_link || "QvaPay no devolvió el enlace de pago."));
          }

          showToast((window.I18N?.qvapay_created || "Factura QvaPay creada. Abriendo el pago..."));

          window.open(data.payment_url, "_blank", "noopener");

          document.getElementById("donorName").value = "";
          document.getElementById("donorContact").value = "";
          document.getElementById("donationAmount").value = "";
          document.getElementById("donationMessage").value = "";
        } else {
          await apiFetch("/api/donaciones", {
            method: "POST",
            body: JSON.stringify(payload),
          });

          showToast((window.I18N?.donation_sent || "¡Gracias por tu donación! Tu registro fue enviado."));
          document.getElementById("donorName").value = "";
          document.getElementById("donorContact").value = "";
          document.getElementById("donationAmount").value = "";
          document.getElementById("donationMessage").value = "";
        }
      } catch (e) {
        if (e.data && e.data.error === "qvapay_no_configurado") {
          showToast((window.I18N?.qvapay_unconfigured || "QvaPay aún no está configurado."));
        } else if (e.data && e.data.error === "qvapay_requiere_usd") {
          showToast((window.I18N?.qvapay_usd || "QvaPay requiere USD para este pago."));
        } else {
          showToast(e.message || (window.I18N?.donation_failed || "No se pudo procesar la donación."));
        }
      } finally {
        sendDonationBtn.disabled = false;
      }
    });
  }
});
