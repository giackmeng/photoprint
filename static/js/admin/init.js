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