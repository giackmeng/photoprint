window.AdminApp = window.AdminApp || {};

window.AdminApp.loadJobs = async function () {
  try {
    const response = await fetch("/admin/jobs");
    const data = await response.json();

    if (!data.success) {
      window.AdminApp.setStatus("Errore caricamento job.");
      return;
    }

    window.AdminApp.state.jobsBody.innerHTML = "";

    data.jobs.forEach(job => {
      const cancelBtn = job.status === "queued"
        ? `<button class="muted" onclick="cancelJob('${job.id}')">Annulla</button>`
        : "";

      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${job.created_at}</td>
        <td>${job.id}</td>
        <td><span class="pill ${job.status}">${job.status}</span></td>
        <td>${job.print_format}</td>
        <td>${job.copies}</td>
        <td>${job.message}</td>
        <td>
          <button onclick="reprintJob('${job.id}')">Ristampa</button>
          ${cancelBtn}
        </td>
      `;
      window.AdminApp.state.jobsBody.appendChild(row);
    });

    window.AdminApp.updateStats(data.stats);
  } catch (e) {
    window.AdminApp.setStatus("Errore di connessione al pannello admin.");
  }
};

window.AdminApp.reprintJob = async function (jobId) {
  const response = await fetch("/admin/reprint/" + jobId, { method: "POST" });
  const data = await response.json();
  window.AdminApp.setStatus(data.message || "Operazione completata.");
  window.AdminApp.loadJobs();
};

window.AdminApp.cancelJob = async function (jobId) {
  const response = await fetch("/admin/cancel/" + jobId, { method: "POST" });
  const data = await response.json();
  window.AdminApp.setStatus(data.message || "Operazione completata.");
  window.AdminApp.loadJobs();
};

window.AdminApp.bindJobs = function () {
  document.getElementById("refreshBtn")?.addEventListener("click", window.AdminApp.loadJobs);

  document.getElementById("reprintLastBtn")?.addEventListener("click", async () => {
    const response = await fetch("/admin/reprint-last", { method: "POST" });
    const data = await response.json();
    window.AdminApp.setStatus(data.message || "Operazione completata.");
    window.AdminApp.loadJobs();
  });

  document.getElementById("cleanupBtn")?.addEventListener("click", async () => {
    const response = await fetch("/admin/cleanup", { method: "POST" });
    const data = await response.json();
    window.AdminApp.setStatus(data.message || "Pulizia completata.");
    window.AdminApp.loadJobs();
  });
};

window.reprintJob = window.AdminApp.reprintJob;
window.cancelJob = window.AdminApp.cancelJob;