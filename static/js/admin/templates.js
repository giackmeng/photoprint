window.AdminApp = window.AdminApp || {};

window.AdminApp.previewTimer = null;
window.AdminApp.previewController = null;

window.AdminApp.getOverlayRefs = function () {
  return {
    img: document.getElementById("templatePreviewImage"),
    overlay: document.getElementById("templatePreviewOverlay")
  };
};

window.AdminApp.syncInputsFromVisualState = function () {
  const state = window.AdminApp.state;
  if (!state.currentTemplateDetail) return;

  if (state.currentTemplateDetail.mode === "image_template_multi" || state.currentTemplateDetail.print_format === "strip") {
    const boxes = state.visualBoxesState;

    document.getElementById("box1_x").value = boxes[0]?.x ?? 0;
    document.getElementById("box1_y").value = boxes[0]?.y ?? 0;
    document.getElementById("box1_w").value = boxes[0]?.w ?? 0;
    document.getElementById("box1_h").value = boxes[0]?.h ?? 0;

    document.getElementById("box2_x").value = boxes[1]?.x ?? 0;
    document.getElementById("box2_y").value = boxes[1]?.y ?? 0;
    document.getElementById("box2_w").value = boxes[1]?.w ?? 0;
    document.getElementById("box2_h").value = boxes[1]?.h ?? 0;

    document.getElementById("box3_x").value = boxes[2]?.x ?? 0;
    document.getElementById("box3_y").value = boxes[2]?.y ?? 0;
    document.getElementById("box3_w").value = boxes[2]?.w ?? 0;
    document.getElementById("box3_h").value = boxes[2]?.h ?? 0;
  } else {
    const box = state.visualBoxesState[0] || { x: 0, y: 0, w: 0, h: 0 };
    document.getElementById("photo_x").value = box.x;
    document.getElementById("photo_y").value = box.y;
    document.getElementById("photo_w").value = box.w;
    document.getElementById("photo_h").value = box.h;
  }
};

window.AdminApp.syncVisualStateFromInputs = function () {
  const state = window.AdminApp.state;
  if (!state.currentTemplateDetail) return;

  if (state.currentTemplateDetail.mode === "image_template_multi" || state.currentTemplateDetail.print_format === "strip") {
    state.visualBoxesState = [
      {
        x: parseInt(document.getElementById("box1_x").value || "0", 10),
        y: parseInt(document.getElementById("box1_y").value || "0", 10),
        w: parseInt(document.getElementById("box1_w").value || "0", 10),
        h: parseInt(document.getElementById("box1_h").value || "0", 10)
      },
      {
        x: parseInt(document.getElementById("box2_x").value || "0", 10),
        y: parseInt(document.getElementById("box2_y").value || "0", 10),
        w: parseInt(document.getElementById("box2_w").value || "0", 10),
        h: parseInt(document.getElementById("box2_h").value || "0", 10)
      },
      {
        x: parseInt(document.getElementById("box3_x").value || "0", 10),
        y: parseInt(document.getElementById("box3_y").value || "0", 10),
        w: parseInt(document.getElementById("box3_w").value || "0", 10),
        h: parseInt(document.getElementById("box3_h").value || "0", 10)
      }
    ];
  } else {
    state.visualBoxesState = [{
      x: parseInt(document.getElementById("photo_x").value || "0", 10),
      y: parseInt(document.getElementById("photo_y").value || "0", 10),
      w: parseInt(document.getElementById("photo_w").value || "0", 10),
      h: parseInt(document.getElementById("photo_h").value || "0", 10)
    }];
  }
};

window.AdminApp.clampBox = function (box, maxW, maxH) {
  box.w = Math.max(20, box.w);
  box.h = Math.max(20, box.h);
  box.x = Math.max(0, box.x);
  box.y = Math.max(0, box.y);

  if (box.x + box.w > maxW) box.x = Math.max(0, maxW - box.w);
  if (box.y + box.h > maxH) box.y = Math.max(0, maxH - box.h);

  if (box.x + box.w > maxW) box.w = Math.max(20, maxW - box.x);
  if (box.y + box.h > maxH) box.h = Math.max(20, maxH - box.y);
};

window.AdminApp.scheduleAutosave = function () {
  const state = window.AdminApp.state;
  clearTimeout(state.autosaveTimer);
  state.autosaveTimer = setTimeout(() => {
    window.AdminApp.saveTemplateBoxesSilently();
  }, 900);
};

window.AdminApp.saveTemplateBoxesSilently = async function () {
  const form = document.getElementById("templateBoxesForm");
  if (!form) return;

  const formData = new FormData(form);

  try {
    const response = await fetch("/admin/template-boxes", {
      method: "POST",
      body: formData
    });

    const data = await response.json();

    if (data.success) {
      window.AdminApp.setStatus("Box salvati automaticamente");
    } else {
      window.AdminApp.setStatus(data.message || "Errore autosave");
    }
  } catch (e) {
    window.AdminApp.setStatus("Errore autosave");
  }
};

window.AdminApp.schedulePreviewUpdate = function (delay = 250) {
  clearTimeout(window.AdminApp.previewTimer);
  window.AdminApp.previewTimer = setTimeout(() => {
    window.AdminApp.updateRealPreview();
  }, delay);
};

window.AdminApp.enableBoxInteractions = function (boxEl, index, handleEl) {
  const state = window.AdminApp.state;
  const { img } = window.AdminApp.getOverlayRefs();
  const maxW = img.naturalWidth || 1200;
  const maxH = img.naturalHeight || 1800;

  let mode = null;
  let startX = 0;
  let startY = 0;
  let startBox = null;

  function onPointerMove(e) {
    if (!mode) return;

    const dx = (e.clientX - startX) / state.templateScaleX;
    const dy = (e.clientY - startY) / state.templateScaleY;

    const box = state.visualBoxesState[index];

    if (mode === "move") {
      box.x = window.AdminApp.snapValue(startBox.x + dx);
      box.y = window.AdminApp.snapValue(startBox.y + dy);
    } else if (mode === "resize") {
      box.w = window.AdminApp.snapValue(startBox.w + dx);
      box.h = window.AdminApp.snapValue(startBox.h + dy);
    }

    window.AdminApp.clampBox(box, maxW, maxH);
    window.AdminApp.syncInputsFromVisualState();
    window.AdminApp.renderVisualBoxes();
    window.AdminApp.schedulePreviewUpdate(220);
  }

  function onPointerUp() {
    mode = null;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.AdminApp.schedulePreviewUpdate(50);
    window.AdminApp.scheduleAutosave();
  }

  boxEl.addEventListener("pointerdown", (e) => {
    if (e.target === handleEl) return;
    e.preventDefault();

    state.selectedBoxIndex = index;
    mode = "move";
    startX = e.clientX;
    startY = e.clientY;
    startBox = { ...state.visualBoxesState[index] };

    window.AdminApp.renderVisualBoxes();

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  });

  handleEl.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation();

    state.selectedBoxIndex = index;
    mode = "resize";
    startX = e.clientX;
    startY = e.clientY;
    startBox = { ...state.visualBoxesState[index] };

    window.AdminApp.renderVisualBoxes();

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  });
};

window.AdminApp.renderVisualBoxes = function () {
  const state = window.AdminApp.state;
  const { img, overlay } = window.AdminApp.getOverlayRefs();
  if (!img || !overlay || !state.currentTemplateDetail) return;

  overlay.innerHTML = "";

  const renderedWidth = img.clientWidth;
  const renderedHeight = img.clientHeight;
  const naturalWidth = img.naturalWidth || renderedWidth;
  const naturalHeight = img.naturalHeight || renderedHeight;

  state.templateScaleX = renderedWidth / naturalWidth;
  state.templateScaleY = renderedHeight / naturalHeight;

  state.visualBoxesState.forEach((box, index) => {
    const boxEl = document.createElement("div");
    boxEl.className = "preview-box";
    boxEl.dataset.index = index;

    boxEl.style.left = (box.x * state.templateScaleX) + "px";
    boxEl.style.top = (box.y * state.templateScaleY) + "px";
    boxEl.style.width = (box.w * state.templateScaleX) + "px";
    boxEl.style.height = (box.h * state.templateScaleY) + "px";

    if (index === state.selectedBoxIndex) {
      boxEl.style.borderWidth = "3px";
      boxEl.style.boxShadow = "0 0 0 3px rgba(200,40,40,0.18)";
    }

    const label = document.createElement("div");
    label.className = "preview-box-label";
    label.textContent = state.visualBoxesState.length > 1 ? "Box " + (index + 1) : "Photo Box";

    const handle = document.createElement("div");
    handle.className = "preview-resize-handle";

    boxEl.appendChild(label);
    boxEl.appendChild(handle);
    overlay.appendChild(boxEl);

    window.AdminApp.enableBoxInteractions(boxEl, index, handle);
  });
};

window.AdminApp.loadTemplateImage = function (templateId, callback) {
  const { img } = window.AdminApp.getOverlayRefs();
  img.onload = () => {
    if (callback) callback();
  };
  img.src = "/admin/template-preview-file/" + encodeURIComponent(templateId) + "?t=" + Date.now();
};

window.AdminApp.loadTemplateBoxesSelector = async function () {
  try {
    const response = await fetch("/admin/templates-list");
    const data = await response.json();

    if (!data.success) return;

    const editSelect = document.getElementById("edit_template_id");
    if (!editSelect) return;

    const currentValue = editSelect.value;
    editSelect.innerHTML = "";

    data.templates.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = `${t.label} (${t.id})`;
      editSelect.appendChild(opt);
    });

    if (currentValue && data.templates.some(t => t.id === currentValue)) {
      editSelect.value = currentValue;
      await window.AdminApp.loadTemplateDetail(currentValue);
    } else if (data.templates.length > 0) {
      await window.AdminApp.loadTemplateDetail(data.templates[0].id);
    }
  } catch (e) {
    console.error("Errore caricamento selector box", e);
  }
};

window.AdminApp.loadTemplateDetail = async function (templateId) {
  try {
    const response = await fetch("/admin/template-detail/" + encodeURIComponent(templateId));
    const data = await response.json();

    if (!data.success) {
      window.AdminApp.setStatus(data.message || "Template non trovato.");
      return;
    }

    const tpl = data.template;
    const state = window.AdminApp.state;
    state.currentTemplateDetail = tpl;
    document.getElementById("edit_photo_fit").value = tpl.photo_fit || "cover";

    const singleBoxFields = document.getElementById("singleBoxFields");
    const multiBoxFields = document.getElementById("multiBoxFields");

    if (tpl.mode === "image_template_multi" || tpl.print_format === "strip") {
      singleBoxFields.style.display = "none";
      multiBoxFields.style.display = "block";

      const boxes = tpl.photo_boxes || [[0,0,0,0],[0,0,0,0],[0,0,0,0]];

      document.getElementById("box1_x").value = boxes[0]?.[0] ?? 0;
      document.getElementById("box1_y").value = boxes[0]?.[1] ?? 0;
      document.getElementById("box1_w").value = boxes[0]?.[2] ?? 0;
      document.getElementById("box1_h").value = boxes[0]?.[3] ?? 0;

      document.getElementById("box2_x").value = boxes[1]?.[0] ?? 0;
      document.getElementById("box2_y").value = boxes[1]?.[1] ?? 0;
      document.getElementById("box2_w").value = boxes[1]?.[2] ?? 0;
      document.getElementById("box2_h").value = boxes[1]?.[3] ?? 0;

      document.getElementById("box3_x").value = boxes[2]?.[0] ?? 0;
      document.getElementById("box3_y").value = boxes[2]?.[1] ?? 0;
      document.getElementById("box3_w").value = boxes[2]?.[2] ?? 0;
      document.getElementById("box3_h").value = boxes[2]?.[3] ?? 0;
    } else {
      singleBoxFields.style.display = "block";
      multiBoxFields.style.display = "none";

      const box = tpl.photo_box || [0, 0, 0, 0];
      document.getElementById("photo_x").value = box[0] ?? 0;
      document.getElementById("photo_y").value = box[1] ?? 0;
      document.getElementById("photo_w").value = box[2] ?? 0;
      document.getElementById("photo_h").value = box[3] ?? 0;
    }

    window.AdminApp.syncVisualStateFromInputs();
    window.AdminApp.loadTemplateImage(tpl.id, window.AdminApp.renderVisualBoxes);
    window.AdminApp.schedulePreviewUpdate(120);
  } catch (e) {
    window.AdminApp.setStatus("Errore caricamento dettaglio template.");
  }
};

window.AdminApp.updateRealPreview = async function () {
  const input = document.getElementById("testPhotoInput");
  const previewImg = document.getElementById("renderPreviewImg");
  const templateId = document.getElementById("edit_template_id")?.value;

  if (!input || !input.files.length || !templateId) return;

  if (window.AdminApp.previewController) {
    window.AdminApp.previewController.abort();
  }

  const controller = new AbortController();
  window.AdminApp.previewController = controller;

  const form = document.getElementById("templateBoxesForm");
  const formData = new FormData(form);

  formData.append("template_id", templateId);
  formData.append("photo", input.files[0]);

  try {
    const response = await fetch("/admin/template-render-preview", {
      method: "POST",
      body: formData,
      signal: controller.signal
    });

    const data = await response.json();

    if (data.success) {
      previewImg.src = data.preview;
      previewImg.style.display = "block";
    } else {
      window.AdminApp.setStatus(data.message || "Errore preview reale.");
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      window.AdminApp.setStatus("Errore di connessione nella preview reale.");
    }
  }
};

window.AdminApp.attachLivePreviewListeners = function () {
  const ids = [
    "edit_photo_fit",
    "photo_x", "photo_y", "photo_w", "photo_h",
    "box1_x", "box1_y", "box1_w", "box1_h",
    "box2_x", "box2_y", "box2_w", "box2_h",
    "box3_x", "box3_y", "box3_w", "box3_h"
  ];

  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;

    el.addEventListener("input", () => {
      window.AdminApp.syncVisualStateFromInputs();
      window.AdminApp.renderVisualBoxes();
      window.AdminApp.schedulePreviewUpdate(250);
      window.AdminApp.scheduleAutosave();
    });

    el.addEventListener("change", () => {
      window.AdminApp.syncVisualStateFromInputs();
      window.AdminApp.renderVisualBoxes();
      window.AdminApp.schedulePreviewUpdate(250);
      window.AdminApp.scheduleAutosave();
    });
  });
};

window.AdminApp.bindTemplateForms = function () {
  document.getElementById("templatesForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);

    const response = await fetch("/admin/templates", {
      method: "POST",
      body: formData
    });

    const data = await response.json();
    window.AdminApp.setStatus(data.message || "Template aggiornati.");
    await window.AdminApp.loadTemplateBoxesSelector();
  });

  document.getElementById("templateUploadForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);

    const response = await fetch("/admin/upload-template", {
      method: "POST",
      body: formData
    });

    const data = await response.json();
    window.AdminApp.setStatus(data.message || "Operazione completata.");

    if (data.success) {
      e.target.reset();
      window.location.reload();
    }
  });

  document.getElementById("testPhotoInput")?.addEventListener("change", () => {
    window.AdminApp.schedulePreviewUpdate(50);
  });

  document.getElementById("edit_template_id")?.addEventListener("change", function () {
    window.AdminApp.loadTemplateDetail(this.value);
  });

  document.getElementById("templateBoxesForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const formData = new FormData(e.target);

    const response = await fetch("/admin/template-boxes", {
      method: "POST",
      body: formData
    });

    const data = await response.json();
    window.AdminApp.setStatus(data.message || "Box aggiornati.");

    if (data.success) {
      await window.AdminApp.loadTemplateDetail(document.getElementById("edit_template_id").value);
      window.AdminApp.schedulePreviewUpdate(50);
    }
  });
};

window.AdminApp.bindTemplateKeyboard = function () {
  window.addEventListener("keydown", (e) => {
    const state = window.AdminApp.state;
    if (!state.currentTemplateDetail || !state.visualBoxesState.length) return;

    const activeTag = document.activeElement?.tagName?.toLowerCase();
    if (activeTag === "input" || activeTag === "textarea" || activeTag === "select") return;

    const box = state.visualBoxesState[state.selectedBoxIndex];
    if (!box) return;

    let changed = false;
    const step = e.shiftKey ? state.GRID_SIZE * 2 : state.GRID_SIZE;

    if (e.key === "ArrowLeft") {
      box.x -= step;
      changed = true;
    } else if (e.key === "ArrowRight") {
      box.x += step;
      changed = true;
    } else if (e.key === "ArrowUp") {
      box.y -= step;
      changed = true;
    } else if (e.key === "ArrowDown") {
      box.y += step;
      changed = true;
    } else if (e.key === "[") {
      box.w -= step;
      box.h -= step;
      changed = true;
    } else if (e.key === "]") {
      box.w += step;
      box.h += step;
      changed = true;
    } else if (e.key === "Tab") {
      if (state.visualBoxesState.length > 1) {
        e.preventDefault();
        state.selectedBoxIndex = (state.selectedBoxIndex + 1) % state.visualBoxesState.length;
        window.AdminApp.renderVisualBoxes();
      }
      return;
    }

    if (!changed) return;

    e.preventDefault();

    const { img } = window.AdminApp.getOverlayRefs();
    window.AdminApp.clampBox(box, img.naturalWidth || 1200, img.naturalHeight || 1800);

    box.x = window.AdminApp.snapValue(box.x);
    box.y = window.AdminApp.snapValue(box.y);
    box.w = window.AdminApp.snapValue(box.w);
    box.h = window.AdminApp.snapValue(box.h);

    window.AdminApp.syncInputsFromVisualState();
    window.AdminApp.renderVisualBoxes();
    window.AdminApp.schedulePreviewUpdate(120);
    window.AdminApp.scheduleAutosave();
  });
};