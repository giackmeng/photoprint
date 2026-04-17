window.AdminApp = window.AdminApp || {};

window.AdminApp.state = {
  jobsBody: null,
  statusBox: null,
  currentTemplateDetail: null,
  visualBoxesState: [],
  templateScaleX: 1,
  templateScaleY: 1,
  selectedBoxIndex: 0,
  autosaveTimer: null,
  GRID_SIZE: 10
};

window.AdminApp.setStatus = function (msg) {
  if (window.AdminApp.state.statusBox) {
    window.AdminApp.state.statusBox.textContent = msg;
  }
};

window.AdminApp.updateStats = function (stats) {
  document.getElementById("s_total").textContent = stats.total;
  document.getElementById("s_done").textContent = stats.done;
  document.getElementById("s_copies").textContent = stats.total_copies;
  document.getElementById("s_queue").textContent = stats.queued;
  document.getElementById("s_processing").textContent = stats.processing;
  document.getElementById("s_errors").textContent = stats.errors;
};

window.AdminApp.setActiveNav = function (buttonEl) {
  document.querySelectorAll(".nav-item").forEach(btn => btn.classList.remove("active"));
  if (buttonEl) buttonEl.classList.add("active");
};

window.AdminApp.showSection = function (id, buttonEl = null) {
  localStorage.setItem("admin_section", id);
  localStorage.removeItem("admin_section_group");

  const sections = document.querySelectorAll(".admin-section");
  sections.forEach(sec => {
    if (id === "all") {
      sec.style.display = "block";
      return;
    }

    if (sec.id === id || sec.id === "section-dashboard-stats") {
      sec.style.display = "block";
    } else {
      sec.style.display = "none";
    }
  });

  if (buttonEl) {
    window.AdminApp.setActiveNav(buttonEl);
  } else {
    document.querySelectorAll(".nav-item").forEach(btn => btn.classList.remove("active"));
  }

  window.scrollTo({ top: 0, behavior: "smooth" });
};

window.AdminApp.showSectionGroup = function (ids, buttonEl = null) {
  localStorage.setItem("admin_section_group", JSON.stringify(ids));
  localStorage.removeItem("admin_section");

  const sections = document.querySelectorAll(".admin-section");
  sections.forEach(sec => {
    if (sec.id === "section-dashboard-stats") {
      sec.style.display = "block";
      return;
    }
    sec.style.display = ids.includes(sec.id) ? "block" : "none";
  });

  window.AdminApp.setActiveNav(buttonEl);
  window.scrollTo({ top: 0, behavior: "smooth" });
};

window.AdminApp.snapValue = function (value, grid = window.AdminApp.state.GRID_SIZE) {
  return Math.round(value / grid) * grid;
};

window.showSection = window.AdminApp.showSection;
window.showSectionGroup = window.AdminApp.showSectionGroup;

window.AdminApp.loadCurrentWifi = async function () {
  const el = document.getElementById("currentWifiInfo");
  const ssidInput = document.getElementById("wifi_ssid");

  try {
    const response = await fetch("/admin/current-wifi");
    const data = await response.json();

    if (!data.success) {
      if (el) el.textContent = "Rete attuale: errore lettura";
      return;
    }

    if (data.connected && data.ssid) {
      if (el) el.textContent = "Rete attuale: " + data.ssid;

      if (ssidInput && !ssidInput.value.trim()) {
        ssidInput.value = data.ssid;
      }
    } else {
      if (el) el.textContent = "Rete attuale: non connesso";
    }
  } catch (e) {
    if (el) el.textContent = "Rete attuale: errore";
  }
};