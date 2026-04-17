const form = document.getElementById("uploadForm");
    const photoInput = document.getElementById("photo");
    const filename = document.getElementById("filename");
    const previewGrid = document.getElementById("previewGrid");
    const layoutPreview = document.getElementById("layoutPreview");
    const printBtn = document.getElementById("printBtn");
    const previewBtn = document.getElementById("previewBtn");
    const loader = document.getElementById("loader");
    const statusBox = document.getElementById("status");
    const queueInfo = document.getElementById("queueInfo");

    let sending = false;

    function setStatus(type, message) {
      statusBox.className = "status " + type;
      statusBox.textContent = message;
    }

    function resetStatus() {
      statusBox.className = "status";
      statusBox.textContent = "";
    }

    async function refreshQueueInfo() {
      try {
        const response = await fetch("/queue-info");
        const data = await response.json();

        if (data.processing > 0) {
          queueInfo.textContent = "Stampa in corso · " + data.queued + " job in attesa";
        } else if (data.queued > 0) {
          queueInfo.textContent = data.queued + " job in coda";
        } else {
          queueInfo.textContent = "Nessuna attesa · sistema pronto";
        }
      } catch (e) {
        queueInfo.textContent = "Sistema pronto";
      }
    }

    function clearPreviewGrid() {
      previewGrid.innerHTML = "";
      previewGrid.style.display = "none";
    }

    function renderPreviews(files) {
      clearPreviewGrid();

      if (!files.length) {
        return;
      }

      previewGrid.style.display = "grid";

      Array.from(files).forEach(file => {
        const wrapper = document.createElement("div");
        wrapper.className = "preview-item";

        const img = document.createElement("img");
        img.src = URL.createObjectURL(file);
        img.alt = file.name;

        wrapper.appendChild(img);
        previewGrid.appendChild(wrapper);
      });
    }

    async function loadPreview() {
  const files = Array.from(photoInput.files);
  const printFormat = document.getElementById("print_format").value;

  if (!files.length) {
    setStatus("error", "Seleziona almeno una foto.");
    return;
  }

  const formData = new FormData();

  if (printFormat === "strip") {
    files.slice(0, 3).forEach(file => {
      formData.append("photos", file);
    });
  } else {
    formData.append("photos", files[0]);
  }

  formData.append("print_format", printFormat);

  previewBtn.disabled = true;
  setStatus("info", "Generazione anteprima in corso...");

  try {
    const response = await fetch("/preview-multiple", {
      method: "POST",
      body: formData
    });

    const result = await response.json();

    if (result.success) {
      layoutPreview.src = result.preview;
      layoutPreview.style.display = "block";

      if (printFormat === "strip") {
        setStatus("success", "Anteprima strip aggiornata.");
      } else {
        setStatus("success", "Anteprima layout aggiornata sulla prima foto.");
      }
    } else {
      setStatus("error", result.message || "Errore generazione anteprima.");
    }
  } catch (e) {
    setStatus("error", "Errore di connessione durante l'anteprima.");
  } finally {
    previewBtn.disabled = false;
  }
}
    photoInput.addEventListener("change", function () {
      resetStatus();

      const files = this.files;

      if (!files.length) {
        filename.textContent = "";
        clearPreviewGrid();
        layoutPreview.style.display = "none";
        layoutPreview.src = "";
        printBtn.disabled = true;
        previewBtn.disabled = true;
        return;
      }

       // 🔥 LIMITE 3 FOTO
  if (files.length > 3) {
    setStatus("error", "Puoi selezionare massimo 3 foto.");
    
    this.value = ""; // reset input
    filename.textContent = "";
    clearPreviewGrid();
    printBtn.disabled = true;
    previewBtn.disabled = true;
    return;
  }

  filename.textContent = files.length === 1
    ? files[0].name
    : `${files.length} foto selezionate`;

  renderPreviews(files);

  layoutPreview.style.display = "none";
  layoutPreview.src = "";

  printBtn.disabled = false;
  previewBtn.disabled = false;
    });

    document.getElementById("print_format").addEventListener("change", function () {
      layoutPreview.style.display = "none";
      layoutPreview.src = "";
    });

    previewBtn.addEventListener("click", loadPreview);

    form.addEventListener("submit", async function (e) {
      e.preventDefault();

      if (sending) return;

      const files = photoInput.files;

      if (!files.length) {
        setStatus("error", "Seleziona almeno una foto.");
        return;
      }

      sending = true;
      printBtn.disabled = true;
      previewBtn.disabled = true;
      loader.classList.add("show");
      setStatus("info", "Invio delle foto alla coda di stampa...");

      const formData = new FormData();

      Array.from(files).forEach(file => {
        formData.append("photos", file);
      });

      formData.append("print_format", document.getElementById("print_format").value);
      formData.append("copies", document.getElementById("copies").value);

      try {
        const response = await fetch("/print-multiple", {
          method: "POST",
          body: formData
        });

        const result = await response.json();

        if (result.success) {
          setStatus("success", result.message || "Foto inviate correttamente.");

          form.reset();
          filename.textContent = "";
          clearPreviewGrid();
          layoutPreview.style.display = "none";
          layoutPreview.src = "";
          printBtn.disabled = true;
          previewBtn.disabled = true;
        } else {
          setStatus("error", result.message || "Errore durante l'invio.");
        }
      } catch (error) {
        setStatus("error", "Errore di connessione al server.");
      } finally {
        sending = false;
        loader.classList.remove("show");
        refreshQueueInfo();
      }
    });

    refreshQueueInfo();
    setInterval(refreshQueueInfo, 4000);

    async function loadEventInfo() {
      const res = await fetch("/event-info");
      const data = await res.json();

      if (data.success) {
        document.getElementById("eventCodeLabel").innerText = data.event_code;
      }
    }

    loadEventInfo();