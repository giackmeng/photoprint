window.AdminApp = window.AdminApp || {};

window.AdminApp.bindBasicForms = function () {
  document.getElementById("configForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);

    const response = await fetch("/admin/config", {
      method: "POST",
      body: formData
    });

    const data = await response.json();
    window.AdminApp.setStatus(data.message || "Configurazione aggiornata.");
  });

  document.getElementById("logoForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);

    const response = await fetch("/admin/upload-logo", {
      method: "POST",
      body: formData
    });

    const data = await response.json();
    window.AdminApp.setStatus(data.message || "Logo aggiornato.");
  });
};

window.addEventListener("DOMContentLoaded", () => {
  window.AdminApp.state.jobsBody = document.getElementById("jobsBody");
  window.AdminApp.state.statusBox = document.getElementById("statusBox");

  const savedGroup = localStorage.getItem("admin_section_group");
  const savedSection = localStorage.getItem("admin_section") || "all";

  if (savedGroup) {
    try {
      const ids = JSON.parse(savedGroup);
      window.AdminApp.showSectionGroup(ids);
    } catch (e) {
      window.AdminApp.showSection(savedSection);
    }
  } else {
    window.AdminApp.showSection(savedSection);
  }

  
  window.AdminApp.bindMobileSidebar();
  window.AdminApp.bindBasicForms();
  window.AdminApp.bindJobs();
  window.AdminApp.bindTemplateForms();
  window.AdminApp.attachLivePreviewListeners();
  window.AdminApp.bindTemplateKeyboard();
  window.AdminApp.bindQuotaQr();

  window.AdminApp.loadJobs();
  setInterval(window.AdminApp.loadJobs, 5000);
  window.AdminApp.loadTemplateBoxesSelector();
  window.AdminApp.loadQuotaConfig();
  window.AdminApp.loadEventQr();
  window.AdminApp.bindWifiForm();
  window.AdminApp.loadWifiQrInfo();
  window.AdminApp.loadWifiQr();
  window.AdminApp.loadPrinters();
  window.AdminApp.bindPrinterRefresh?.();
  window.AdminApp.loadCurrentWifi();
});

window.AdminApp.bindMobileSidebar = function () {
  const sidebar = document.getElementById("adminSidebar");
  const toggle = document.getElementById("sidebarToggle");

  if (!sidebar || !toggle) return;

  toggle.addEventListener("click", () => {
    sidebar.classList.toggle("mobile-open");
  });

  document.querySelectorAll(".sidebar .nav-item").forEach(btn => {
    btn.addEventListener("click", () => {
      if (window.innerWidth <= 980) {
        sidebar.classList.remove("mobile-open");
      }
    });
  });
};

window.AdminApp.loadPrinters = async function () {
  const select = document.getElementById("printer_name");
  if (!select) return;

  try {
    const response = await fetch("/admin/printers");
    const data = await response.json();

    if (!data.success) {
      window.AdminApp.setStatus(data.message || "Errore caricamento stampanti");
      select.innerHTML = `<option value="">Nessuna stampante trovata</option>`;
      return;
    }

    select.innerHTML = "";

    if (!data.printers.length) {
      select.innerHTML = `<option value="">Nessuna stampante disponibile</option>`;
      return;
    }

    data.printers.forEach(printer => {
      const opt = document.createElement("option");
      opt.value = printer;
      opt.textContent = printer;

      if (printer === data.current_printer) {
        opt.selected = true;
      }

      select.appendChild(opt);
    });

  } catch (e) {
    select.innerHTML = `<option value="">Errore caricamento stampanti</option>`;
    window.AdminApp.setStatus("Errore di connessione caricando le stampanti CUPS");
  }
};

window.AdminApp.bindPrinterRefresh = function () {
  document.getElementById("refreshPrintersBtn")?.addEventListener("click", () => {
    window.AdminApp.loadPrinters();
  });
};