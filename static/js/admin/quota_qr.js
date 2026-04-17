window.AdminApp = window.AdminApp || {};

window.AdminApp.loadQuotaConfig = async function () {
  try {
    const res = await fetch("/admin/print-quotas");
    const data = await res.json();

    if (!data.success) return;

    document.getElementById("event_code").value = data.event_code;
    document.getElementById("default_limit_per_identity").value = data.default_limit_per_identity;

    window.AdminApp.renderDeviceList(data.records);
  } catch (e) {
    console.error(e);
  }
};

window.AdminApp.renderDeviceList = function (records) {
  const wrap = document.getElementById("quotaDeviceList");
  wrap.innerHTML = "";

  if (!records.length) {
    wrap.innerHTML = "<p class='helper'>Nessun dispositivo registrato.</p>";
    return;
  }

  records.forEach(r => {
    const div = document.createElement("div");
    div.className = "quota-row";
    div.innerHTML = `
      <div class="quota-key">${r.identity_key.substring(0, 28)}...</div>
      <div><b>Usate:</b> ${r.prints_used} | <b>Rimanenti:</b> ${r.remaining}</div>
      <div class="helper">IP: ${r.meta?.ip || "-"} | MAC: ${r.meta?.mac || "-"} | Evento: ${r.meta?.event_code || "-"}</div>
      <button type="button" class="muted" onclick="resetQuota('${r.identity_key}')">Reset</button>
    `;
    wrap.appendChild(div);
  });
};

window.AdminApp.resetQuota = async function (identity_key) {
  const fd = new FormData();
  fd.append("identity_key", identity_key);

  const res = await fetch("/admin/print-quotas/reset", {
    method: "POST",
    body: fd
  });

  const data = await res.json();
  window.AdminApp.setStatus(data.message || "Reset completato");
  window.AdminApp.loadQuotaConfig();
};

window.AdminApp.loadEventQr = async function () {
  try {
    const response = await fetch("/admin/event-qr-info");
    const data = await response.json();

    if (!data.success) {
      window.AdminApp.setStatus(data.message || "Errore caricamento QR.");
      return;
    }

    document.getElementById("qrEventCodeView").value = data.event_code;
    document.getElementById("qrIpView").value = data.ip;
    document.getElementById("qrUrlView").value = data.url;
    document.getElementById("eventQrImg").src = "/admin/event-qr-image?t=" + Date.now();
  } catch (e) {
    window.AdminApp.setStatus("Errore di connessione nel caricamento QR.");
  }
};

window.AdminApp.bindQuotaQr = function () {
  document.getElementById("quotaConfigForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const fd = new FormData(e.target);

    const res = await fetch("/admin/print-quotas/config", {
      method: "POST",
      body: fd
    });

    const data = await res.json();
    window.AdminApp.setStatus(data.message || "Salvato");

    window.AdminApp.loadQuotaConfig();
    window.AdminApp.loadEventQr();
  });
};

window.resetQuota = window.AdminApp.resetQuota;

window.AdminApp.loadWifiQrInfo = async function () {
  try {
    const response = await fetch("/admin/qr-wifi-info");
    const data = await response.json();

    if (!data.success) return;

    document.getElementById("wifi_ssid").value = data.wifi_ssid || "";
    document.getElementById("wifi_password").value = data.wifi_password || "";
    document.getElementById("wifi_security").value = data.wifi_security || "WPA";
  } catch (e) {
    console.error(e);
  }
};

window.AdminApp.loadWifiQr = function () {
  const img = document.getElementById("wifiQrImg");
  if (!img) return;
  img.src = "/admin/qr-wifi-image?t=" + Date.now();
};

window.loadWifiQr = window.AdminApp.loadWifiQr;