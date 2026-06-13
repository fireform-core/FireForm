const STORAGE_TEMPLATES_KEY = "fireform.templates.v1";
const STORAGE_LAST_OUTPUT_KEY = "fireform.lastOutputPath.v1";
// Where uploaded template PDFs are copied. Fixed for now; longer term this
// should be user-configurable behind a Settings button (see note below).
const DEFAULT_TEMPLATE_DIRECTORY = "src/inputs";
const API_BASE_URL = "http://127.0.0.1:8000";

// UI label <-> stored type-string mapping. The stored values stay backward
// compatible with the existing default "string" type.
const FIELD_TYPES = [
  { label: "Text", value: "string" },
  { label: "Long Text", value: "long_text" },
  { label: "Number", value: "number" },
  { label: "Date", value: "date" },
  { label: "Time", value: "time" },
  { label: "Email", value: "email" },
  { label: "Phone", value: "phone" },
  { label: "Signature", value: "signature" },
  { label: "Checkbox", value: "checkbox" },
  { label: "List", value: "list" },
];
const TYPE_VALUE_TO_LABEL = Object.fromEntries(FIELD_TYPES.map((t) => [t.value, t.label]));
const DEFAULT_FIELD_ROWS = [{ name: "", type: "string" }];

const elements = {
  tabs: Array.from(document.querySelectorAll(".tab")),
  panels: Array.from(document.querySelectorAll(".panel")),
  templateForm: document.getElementById("templateForm"),
  templateName: document.getElementById("templateName"),
  templatePdfFile: document.getElementById("templatePdfFile"),
  pdfDropZone: document.getElementById("pdfDropZone"),
  selectedFileMeta: document.getElementById("selectedFileMeta"),
  changePdfBtn: document.getElementById("changePdfBtn"),
  makeFillableBtn: document.getElementById("makeFillableBtn"),
  makeFillableHelpBtn: document.getElementById("makeFillableHelpBtn"),
  makeFillableHelp: document.getElementById("makeFillableHelp"),
  fieldsBuilder: document.getElementById("fieldsBuilder"),
  fieldCountBadge: document.getElementById("fieldCountBadge"),
  addFieldBtn: document.getElementById("addFieldBtn"),
  templateFormMessage: document.getElementById("templateFormMessage"),
  templateFormResponse: document.getElementById("templateFormResponse"),
  fillForm: document.getElementById("fillForm"),
  fillModel: document.getElementById("fillModel"),
  fillTemplateTiles: document.getElementById("fillTemplateTiles"),
  fillSelectionHint: document.getElementById("fillSelectionHint"),
  fillSubmitBtn: document.getElementById("fillSubmitBtn"),
  inputText: document.getElementById("inputText"),
  sttControls: document.getElementById("sttControls"),
  sttRecordBtn: document.getElementById("sttRecordBtn"),
  sttPauseBtn: document.getElementById("sttPauseBtn"),
  sttStopBtn: document.getElementById("sttStopBtn"),
  sttStatus: document.getElementById("sttStatus"),
  fillFormMessage: document.getElementById("fillFormMessage"),
  fillFormResponse: document.getElementById("fillFormResponse"),
  templatesEmpty: document.getElementById("templatesEmpty"),
  templatesList: document.getElementById("templatesList"),
  localPdfFile: document.getElementById("localPdfFile"),
  serverPdfPath: document.getElementById("serverPdfPath"),
  previewPathBtn: document.getElementById("previewPathBtn"),
  previewStatus: document.getElementById("previewStatus"),
  pdfFrame: document.getElementById("pdfFrame"),
};

let templates = loadTemplates();
let activeObjectUrl = null;
let selectedTemplateFile = null;
// Field rows are scratch state for building one template — they start empty
// each session and are not persisted.
let fieldRows = DEFAULT_FIELD_ROWS.map((row) => ({ ...row }));
let dragSourceIndex = null;
let uploadedPath = null;
let uploadedFieldCount = null;
// Template ids currently selected in the Fill Form tab (multi-select).
let selectedFillIds = new Set();

// Speech-to-text recording state. The MediaRecorder captures compressed audio
// in the renderer; on stop we POST it straight to /forms/transcribe (the local
// Whisper service handles decoding).
let mediaRecorder = null;
let recordedChunks = [];
let recordingStream = null;

waitForBackend().then(initialize);

async function waitForBackend() {
  const loadingScreen = document.getElementById("loadingScreen");
  let isReady = false;
  
  while (!isReady) {
    try {
      const response = await fetch(`${API_BASE_URL}/templates`);
      if (response.ok) {
        isReady = true;
      }
    } catch (e) {
      // Ignore error and try again
    }
    
    if (!isReady) {
      await new Promise(r => setTimeout(r, 500));
    }
  }
  
  if (loadingScreen) {
    loadingScreen.classList.add("hidden");
  }
}

async function initialize() {
  bindEvents();
  renderFieldRows();
  renderTemplates();
  renderFillTemplates();
  restorePreviewState();
  updateSelectedFileMeta();
  loadModels();
  await refreshTemplatesFromApi();
}

function bindEvents() {
  elements.tabs.forEach((tab) => {
    tab.addEventListener("click", () => activateSection(tab.dataset.target));
  });

  elements.templateForm.addEventListener("submit", handleTemplateSubmit);
  elements.templatePdfFile.addEventListener("change", handleTemplateFileInput);
  elements.pdfDropZone.addEventListener("click", () => elements.templatePdfFile.click());
  elements.pdfDropZone.addEventListener("keydown", handleDropZoneKeyDown);
  elements.changePdfBtn.addEventListener("click", () => elements.templatePdfFile.click());
  elements.addFieldBtn.addEventListener("click", handleAddFieldClick);
  elements.makeFillableBtn.addEventListener("click", handleMakeFillableClick);
  elements.makeFillableHelpBtn.addEventListener("click", toggleMakeFillableHelp);
  bindDropZoneDragEvents();
  elements.fillForm.addEventListener("submit", handleFillSubmit);
  elements.fillTemplateTiles.addEventListener("click", handleTileClick);
  elements.fillTemplateTiles.addEventListener("keydown", handleTileKeydown);
  elements.sttRecordBtn.addEventListener("click", startRecording);
  elements.sttPauseBtn.addEventListener("click", togglePauseRecording);
  elements.sttStopBtn.addEventListener("click", stopRecording);
  elements.templatesList.addEventListener("click", handleTemplateActionClick);
  elements.localPdfFile.addEventListener("change", handleLocalFilePreview);
  elements.previewPathBtn.addEventListener("click", () =>
    previewFromPath(elements.serverPdfPath.value, { switchToPreview: true })
  );
}

function activateSection(targetId) {
  switchSection(targetId);
}

async function refreshTemplatesFromApi() {
  try {
    const response = await fetch(`${API_BASE_URL}/templates`);
    const body = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(extractErrorMessage(body, response.status));
    }

    if (Array.isArray(body)) {
      templates = body.map((template) => ({
        id: template.id,
        name: template.name || "",
        pdf_path: template.pdf_path || "",
        fields: template.fields || {},
      }));
      saveTemplates();
      // Drop selections for templates that no longer exist.
      const liveIds = new Set(templates.map((t) => Number(t.id)));
      selectedFillIds.forEach((id) => { if (!liveIds.has(id)) selectedFillIds.delete(id); });
      renderTemplates();
      renderFillTemplates();
    }
  } catch (error) {
    setStatus(
      elements.templateFormMessage,
      `Could not refresh templates from API: ${error.message}`,
      "error"
    );
  }
}

function bindDropZoneDragEvents() {
  ["dragenter", "dragover"].forEach((eventName) => {
    elements.pdfDropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      elements.pdfDropZone.classList.add("active");
    });
  });

  ["dragleave", "dragend", "drop"].forEach((eventName) => {
    elements.pdfDropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      elements.pdfDropZone.classList.remove("active");
    });
  });

  elements.pdfDropZone.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    setSelectedTemplateFile(file);
  });
}

function handleDropZoneKeyDown(event) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    elements.templatePdfFile.click();
  }
}

function handleTemplateFileInput(event) {
  const file = event.target.files && event.target.files[0];
  setSelectedTemplateFile(file);
}

function setSelectedTemplateFile(file) {
  if (!file) {
    return;
  }

  if (!isPdfFile(file)) {
    selectedTemplateFile = null;
    uploadedPath = null;
    uploadedFieldCount = null;
    setMakeFillableButtonState();
    renderFieldCountBadge();
    setStatus(elements.templateFormMessage, "Please select a PDF file.", "error");
    updateSelectedFileMeta();
    return;
  }

  selectedTemplateFile = file;
  uploadedPath = null;
  uploadedFieldCount = null;
  setMakeFillableButtonState();
  renderFieldCountBadge();
  clearJson(elements.templateFormResponse);
  setStatus(elements.templateFormMessage, "");
  updateSelectedFileMeta();
  // Eager upload so the user gets a live field-count comparison while building rows.
  uploadSelectedFileSilently();
}

async function uploadSelectedFileSilently() {
  if (!selectedTemplateFile) return;
  const directory = DEFAULT_TEMPLATE_DIRECTORY;

  const fileAtUploadStart = selectedTemplateFile;
  try {
    const upload = await uploadTemplatePdf(fileAtUploadStart, directory);
    // Guard against the user picking a different file mid-upload.
    if (fileAtUploadStart !== selectedTemplateFile) return;
    uploadedPath = upload.pdf_path;
    uploadedFieldCount =
      typeof upload.field_count === "number" ? upload.field_count : null;
    maybeSeedFieldRows(upload.fields);
    renderFieldCountBadge();
  } catch (_error) {
    // Silent failure — the explicit Create / Make Fillable paths surface errors.
  }
}

// Auto-add a row per field the PDF already defines — same as clicking "+ Add
// Field" for each — filling in its description and type so the user can edit.
// If the list already has rows the user typed, warn before replacing them.
function maybeSeedFieldRows(fields) {
  if (!Array.isArray(fields) || !fields.length) return;
  syncFieldRowsFromDom();

  if (fieldRows.some((row) => row.name.trim())) {
    const replace = window.confirm(
      `This PDF has ${fields.length} fillable field${fields.length === 1 ? "" : "s"}.\n\n` +
        "Replace your current form fields with them? Your existing entries will be lost."
    );
    if (!replace) {
      setStatus(elements.templateFormMessage, "Kept your existing form fields.", "info");
      return;
    }
  }

  fieldRows = fields.map((f) => ({
    name: f.description || f.name || "",
    type: normalizeFieldType(f.type),
  }));
  renderFieldRows();
  setStatus(
    elements.templateFormMessage,
    `Loaded ${fieldRows.length} field${fieldRows.length === 1 ? "" : "s"} from the PDF — edit the descriptions as needed.`,
    "info"
  );
}

function setMakeFillableButtonState() {
  if (!elements.makeFillableBtn) return;
  elements.makeFillableBtn.disabled = !selectedTemplateFile;
  elements.makeFillableBtn.textContent = "Make this PDF fillable";
}

function renderFieldCountBadge() {
  const badge = elements.fieldCountBadge;
  if (!badge) return;

  if (!selectedTemplateFile || uploadedFieldCount === null) {
    badge.classList.add("hidden");
    badge.classList.remove("match", "mismatch");
    badge.textContent = "";
    return;
  }

  const expected = uploadedFieldCount;
  const actual = fieldRows.length;
  const noun = (n) => `${n} fillable field${n === 1 ? "" : "s"}`;
  const rowNoun = (n) => `${n} row${n === 1 ? "" : "s"}`;

  badge.classList.remove("hidden", "match", "mismatch");
  if (expected === actual) {
    badge.classList.add("match");
    badge.textContent = `PDF has ${noun(expected)} — your ${rowNoun(actual)} match.`;
  } else {
    badge.classList.add("mismatch");
    badge.textContent = `PDF has ${noun(expected)} — you have ${rowNoun(actual)}.`;
  }
}

function isPdfFile(file) {
  const name = String(file?.name || "").toLowerCase();
  return name.endsWith(".pdf");
}

function updateSelectedFileMeta() {
  // Once a file is chosen, swap the drop zone for a compact "change" control.
  const hasFile = !!selectedTemplateFile;
  elements.pdfDropZone.classList.toggle("hidden", hasFile);
  elements.changePdfBtn.classList.toggle("hidden", !hasFile);

  if (!hasFile) {
    elements.selectedFileMeta.textContent = "No PDF selected.";
    return;
  }

  const destinationPath = `${DEFAULT_TEMPLATE_DIRECTORY}/${selectedTemplateFile.name}`;

  elements.selectedFileMeta.textContent = `Selected: ${selectedTemplateFile.name} (${formatBytes(
    selectedTemplateFile.size
  )}) - destination: ${destinationPath}`;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function switchSection(targetId) {
  elements.panels.forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== targetId);
  });
  elements.tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.target === targetId);
  });
}

function setStatus(target, message, type = "info") {
  target.textContent = message || "";
  target.className = "status";
  if (type) {
    target.classList.add(type);
  }
}

function showJson(preElement, payload) {
  preElement.textContent = JSON.stringify(payload, null, 2);
  preElement.classList.remove("hidden");
}

function clearJson(preElement) {
  preElement.textContent = "";
  preElement.classList.add("hidden");
}

function collectFieldRows() {
  syncFieldRowsFromDom();

  if (fieldRows.length === 0) {
    return { error: "Add at least one field before creating the template." };
  }

  const dict = {};
  const seen = new Set();
  for (const row of fieldRows) {
    const name = row.name.trim();
    if (!name) {
      return { error: "Every field needs a name." };
    }
    const key = name.toLowerCase();
    if (seen.has(key)) {
      return { error: `Field names must be unique ("${name}" appears more than once).` };
    }
    seen.add(key);
    dict[name] = row.type || "string";
  }
  return { value: dict };
}

async function handleTemplateSubmit(event) {
  event.preventDefault();
  clearJson(elements.templateFormResponse);
  setStatus(elements.templateFormMessage, "");

  const name = elements.templateName.value.trim();
  const templateDirectory = DEFAULT_TEMPLATE_DIRECTORY;
  const collected = collectFieldRows();

  if (!name || !selectedTemplateFile) {
    setStatus(
      elements.templateFormMessage,
      "Name and PDF file are required.",
      "error"
    );
    return;
  }

  if (collected.error) {
    setStatus(elements.templateFormMessage, collected.error, "error");
    return;
  }

  try {
    let activePdfPath = uploadedPath;
    if (!activePdfPath) {
      setStatus(elements.templateFormMessage, "Copying PDF into project directory...", "info");
      const upload = await uploadTemplatePdf(selectedTemplateFile, templateDirectory);
      activePdfPath = upload.pdf_path;
      uploadedPath = upload.pdf_path;
    }

    const payload = {
      name,
      pdf_path: activePdfPath,
      fields: collected.value,
    };

    setStatus(elements.templateFormMessage, "Creating template...", "info");
    const response = await fetch(`${API_BASE_URL}/templates/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const body = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(extractErrorMessage(body, response.status));
    }

    upsertTemplate(body);
    if (body.id != null) {
      selectedFillIds.add(Number(body.id));
    }
    await refreshTemplatesFromApi();
    elements.serverPdfPath.value = body.pdf_path || "";

    const expected = body.field_count;
    const actual = Object.keys(collected.value).length;
    let mismatchNote = "";
    let statusLevel = "success";
    if (typeof expected === "number" && expected !== actual) {
      mismatchNote = ` Heads up — the PDF has ${expected} fillable field${expected === 1 ? "" : "s"}, but you added ${actual} row${actual === 1 ? "" : "s"}. Fills may be incomplete or misaligned.`;
      statusLevel = "error";
    }

    setStatus(
      elements.templateFormMessage,
      `Template created (id: ${body.id}). PDF saved at ${activePdfPath}.${mismatchNote}`,
      statusLevel
    );
    showJson(elements.templateFormResponse, body);
    uploadedPath = null;
    uploadedFieldCount = null;
    setMakeFillableButtonState();
    renderFieldCountBadge();
  } catch (error) {
    setStatus(elements.templateFormMessage, error.message, "error");
  }
}

async function uploadTemplatePdf(file, directory) {
  const formData = new FormData();
  formData.append("file", file, file.name);
  formData.append("directory", directory);

  const response = await fetch(`${API_BASE_URL}/templates/upload`, {
    method: "POST",
    body: formData,
  });

  const body = await parseJsonResponse(response);
  if (!response.ok) {
    throw new Error(extractErrorMessage(body, response.status));
  }

  return body;
}

// ───────────────────────── Fill Form: model + template tiles ──────────────

// "1 field" / "3 forms" — keeps the count-and-label logic in one place.
function pluralize(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

// Look up a template by id (ids may arrive as strings from dataset attributes).
function findTemplate(id) {
  return templates.find((template) => Number(template.id) === Number(id));
}

// Populate the model picker from the local Ollama models the API reports.
async function loadModels() {
  const select = elements.fillModel;
  try {
    const response = await fetch(`${API_BASE_URL}/forms/models`);
    const body = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(extractErrorMessage(body, response.status));
    }

    select.innerHTML = "";
    const models = body.models || [];
    models.forEach((name) => {
      const isDefault = name === body.default;
      const option = document.createElement("option");
      option.value = name;
      option.textContent = isDefault ? `${name} (default)` : name;
      option.selected = isDefault;
      select.append(option);
    });
  } catch (_error) {
    // Ollama unreachable — leave one placeholder so the picker isn't empty.
    if (!select.options.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "(default model)";
      select.append(option);
    }
  }
}

// Build one selectable tile. Whether it's selected is shown purely through the
// tile's highlighted styling (.selected) — there's no separate checkbox.
function createTemplateTile(template) {
  const id = Number(template.id);
  const selected = selectedFillIds.has(id);

  const tile = document.createElement("div");
  tile.className = selected ? "template-tile selected" : "template-tile";
  tile.dataset.templateId = String(id);
  // Behaves like a toggle button for keyboard and screen-reader users.
  tile.setAttribute("role", "button");
  tile.setAttribute("tabindex", "0");
  tile.setAttribute("aria-pressed", String(selected));

  const title = document.createElement("span");
  title.className = "tile-title";
  title.textContent = template.name || "Untitled";

  const fieldCount = template.fields ? Object.keys(template.fields).length : 0;
  const meta = document.createElement("span");
  meta.className = "tile-meta";
  meta.textContent = pluralize(fieldCount, "field");

  const body = document.createElement("div");
  body.className = "tile-body";
  body.append(title, meta);

  // Preview must not toggle selection, so it carries its own id and the click
  // handler stops the event from bubbling up to the tile.
  const previewButton = document.createElement("button");
  previewButton.type = "button";
  previewButton.className = "tile-preview-btn";
  previewButton.dataset.previewId = String(id);
  previewButton.textContent = "Preview";

  tile.append(body, previewButton);
  return tile;
}

function renderFillTemplates() {
  const container = elements.fillTemplateTiles;
  container.innerHTML = "";

  if (!templates.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No templates yet — create one in the Create Template tab.";
    container.append(empty);
    updateFillButtonState();
    return;
  }

  templates.forEach((template) => container.append(createTemplateTile(template)));
  updateFillButtonState();
}

function handleTileClick(event) {
  // A click on the Preview button previews the PDF without toggling selection.
  const previewButton = event.target.closest(".tile-preview-btn");
  if (previewButton) {
    event.stopPropagation();
    const template = findTemplate(previewButton.dataset.previewId);
    if (template) {
      elements.serverPdfPath.value = template.pdf_path || "";
      previewFromPath(template.pdf_path || "", { switchToPreview: true });
    }
    return;
  }

  // A click anywhere else on the tile toggles it on/off for filling.
  const tile = event.target.closest(".template-tile");
  if (tile) {
    toggleFillSelection(Number(tile.dataset.templateId));
  }
}

function handleTileKeydown(event) {
  // Enter/Space activate the focused tile, matching its role="button".
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  const tile = event.target.closest(".template-tile");
  if (tile) {
    event.preventDefault();
    toggleFillSelection(Number(tile.dataset.templateId));
  }
}

function toggleFillSelection(id) {
  if (selectedFillIds.has(id)) {
    selectedFillIds.delete(id);
  } else {
    selectedFillIds.add(id);
  }
  renderFillTemplates();
}

function updateFillButtonState() {
  const count = selectedFillIds.size;
  const nothingSelected = count === 0;

  // Greyed out (but still clickable) until at least one form is chosen.
  elements.fillSubmitBtn.classList.toggle("is-disabled", nothingSelected);
  elements.fillSubmitBtn.textContent = count > 1 ? `Fill ${count} Forms` : "Fill Form";

  elements.fillSelectionHint.classList.remove("error");
  elements.fillSelectionHint.textContent = nothingSelected
    ? "Select one or more forms to fill."
    : `${pluralize(count, "form")} selected.`;
}

// A human-readable label for a template, used in the success/error summary.
function templateLabel(id) {
  const template = findTemplate(id);
  return template && template.name ? template.name : `id ${id}`;
}

// Fill a single template and return its submission. Throws on failure so the
// caller can note which form failed and still continue with the others.
async function fillOneTemplate(id, inputText, model) {
  const response = await fetch(`${API_BASE_URL}/forms/fill`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template_id: id, input_text: inputText, model }),
  });
  const body = await parseJsonResponse(response);
  if (!response.ok) {
    throw new Error(extractErrorMessage(body, response.status));
  }
  return body;
}

// Summarize "N filled, M failed" into the status line, choosing the right tone:
// all-good = success, some failed but some worked = info, nothing worked = error.
function reportFillOutcome(results, errors) {
  const parts = [];
  if (results.length) parts.push(`${results.length} filled`);
  if (errors.length) parts.push(`${errors.length} failed`);

  let level = "success";
  if (errors.length) {
    level = results.length ? "info" : "error";
  }

  const detail = errors.length ? ` ${errors.join("; ")}` : "";
  setStatus(elements.fillFormMessage, `${parts.join(", ")}.${detail}`, level);
}

async function handleFillSubmit(event) {
  event.preventDefault();
  clearJson(elements.fillFormResponse);
  setStatus(elements.fillFormMessage, "");

  const ids = Array.from(selectedFillIds);
  if (!ids.length) {
    // The button looks disabled but stays clickable, so prompt the user here.
    elements.fillSelectionHint.classList.add("error");
    elements.fillSelectionHint.textContent = "Select at least one form to fill.";
    setStatus(elements.fillFormMessage, "Select at least one form to fill.", "error");
    return;
  }

  const inputText = elements.inputText.value.trim();
  if (!inputText) {
    setStatus(elements.fillFormMessage, "Input text is required.", "error");
    return;
  }

  // An empty picker value means "let the server use its default model".
  const model = elements.fillModel.value || undefined;
  setStatus(elements.fillFormMessage, `Filling ${pluralize(ids.length, "form")}…`, "info");

  // Fill each selected form independently so one failure doesn't stop the rest.
  const results = [];
  const errors = [];
  for (const id of ids) {
    try {
      results.push(await fillOneTemplate(id, inputText, model));
    } catch (error) {
      errors.push(`${templateLabel(id)}: ${error.message}`);
    }
  }

  const lastResult = results[results.length - 1];
  if (lastResult) {
    showJson(elements.fillFormResponse, results.length === 1 ? lastResult : results);
    if (lastResult.output_pdf_path) {
      localStorage.setItem(STORAGE_LAST_OUTPUT_KEY, lastResult.output_pdf_path);
      elements.serverPdfPath.value = lastResult.output_pdf_path;
    }
  }

  reportFillOutcome(results, errors);

  // Preview the most recently filled PDF.
  if (lastResult && lastResult.output_pdf_path) {
    await previewFromPath(lastResult.output_pdf_path, { switchToPreview: true });
  }
}

// ───────────────────────── Speech-to-text (local Whisper) ─────────────────

function setSttStatus(message) {
  if (elements.sttStatus) {
    elements.sttStatus.textContent = message || "";
  }
}

async function startRecording() {
  if (mediaRecorder) {
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setSttStatus("Microphone capture is not available in this environment.");
    return;
  }

  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (error) {
    setSttStatus("Microphone permission denied.");
    return;
  }

  recordedChunks = [];
  mediaRecorder = new MediaRecorder(recordingStream);
  mediaRecorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size > 0) {
      recordedChunks.push(event.data);
    }
  });
  mediaRecorder.addEventListener("stop", handleRecordingStop);
  mediaRecorder.start();

  elements.sttControls.classList.add("is-recording");
  elements.sttControls.classList.remove("is-paused");
  elements.sttRecordBtn.disabled = true;
  elements.sttPauseBtn.disabled = false;
  elements.sttStopBtn.disabled = false;
  elements.sttPauseBtn.textContent = "Pause";
  setSttStatus("Recording…");
}

function togglePauseRecording() {
  if (!mediaRecorder) {
    return;
  }
  if (mediaRecorder.state === "recording") {
    mediaRecorder.pause();
    elements.sttControls.classList.add("is-paused");
    elements.sttControls.classList.remove("is-recording");
    elements.sttPauseBtn.textContent = "Resume";
    setSttStatus("Paused.");
  } else if (mediaRecorder.state === "paused") {
    mediaRecorder.resume();
    elements.sttControls.classList.add("is-recording");
    elements.sttControls.classList.remove("is-paused");
    elements.sttPauseBtn.textContent = "Pause";
    setSttStatus("Recording…");
  }
}

function stopRecording() {
  if (!mediaRecorder) {
    return;
  }
  // Lock the controls while we finalize capture and transcribe.
  elements.sttPauseBtn.disabled = true;
  elements.sttStopBtn.disabled = true;
  setSttStatus("Finishing capture…");
  mediaRecorder.stop();
}

async function handleRecordingStop() {
  elements.sttControls.classList.remove("is-recording", "is-paused");
  stopRecordingStream();

  const chunks = recordedChunks;
  const recorder = mediaRecorder;
  recordedChunks = [];
  mediaRecorder = null;

  const blob = new Blob(chunks, { type: (recorder && recorder.mimeType) || "audio/webm" });
  if (!blob.size) {
    resetSttControls();
    setSttStatus("Nothing was recorded.");
    return;
  }

  try {
    setSttStatus("Transcribing…");
    const text = await transcribeAudio(blob);
    appendTranscribedText(text);
    setSttStatus(text ? "Transcription added." : "No speech detected.");
  } catch (error) {
    setSttStatus(`Transcription failed: ${error.message}`);
  } finally {
    resetSttControls();
  }
}

function resetSttControls() {
  elements.sttRecordBtn.disabled = false;
  elements.sttPauseBtn.disabled = true;
  elements.sttStopBtn.disabled = true;
  elements.sttPauseBtn.textContent = "Pause";
  elements.sttControls.classList.remove("is-recording", "is-paused");
}

function stopRecordingStream() {
  if (recordingStream) {
    recordingStream.getTracks().forEach((track) => track.stop());
    recordingStream = null;
  }
}

function appendTranscribedText(text) {
  if (!text) {
    return;
  }
  const existing = elements.inputText.value.trim();
  elements.inputText.value = existing ? `${existing} ${text}` : text;
  // Let any listeners (and the required-field check) see the new value.
  elements.inputText.dispatchEvent(new Event("input"));
}

// "audio/webm;codecs=opus" -> "webm". Just gives the upload a sensible filename;
// the server decodes by content, not extension.
function audioExtension(mimeType) {
  const subtype = (mimeType || "").split("/")[1] || "";
  const withoutCodecs = subtype.split(";")[0].trim();
  return withoutCodecs || "webm";
}

// The Whisper ASR service decodes audio with ffmpeg, so we post the recording
// as-is (typically webm/opus) — no client-side transcoding needed.
async function transcribeAudio(blob) {
  const formData = new FormData();
  formData.append("audio", blob, `recording.${audioExtension(blob.type)}`);

  const response = await fetch(`${API_BASE_URL}/forms/transcribe`, {
    method: "POST",
    body: formData,
  });
  const body = await parseJsonResponse(response);
  if (!response.ok) {
    throw new Error(extractErrorMessage(body, response.status));
  }
  return (body.text || "").trim();
}

function handleTemplateActionClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }

  const id = Number(button.dataset.templateId);
  const template = templates.find((item) => Number(item.id) === id);
  if (!template) {
    return;
  }

  if (button.dataset.action === "preview") {
    elements.serverPdfPath.value = template.pdf_path || "";
    previewFromPath(template.pdf_path || "", { switchToPreview: true });
    return;
  }

  if (button.dataset.action === "use-fill") {
    selectedFillIds.add(Number(template.id));
    renderFillTemplates();
    activateSection("fillFormSection");
    setStatus(
      elements.fillFormMessage,
      `"${template.name || "Template"}" selected for filling.`,
      "info"
    );
  }
}

function handleLocalFilePreview(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }

  if (activeObjectUrl) {
    URL.revokeObjectURL(activeObjectUrl);
  }

  activeObjectUrl = URL.createObjectURL(file);
  elements.pdfFrame.src = activeObjectUrl;
  switchSection("pdfPreviewerSection");
  setStatus(elements.previewStatus, `Previewing local file: ${file.name}`, "success");
}

function resolvePreviewCandidates(pathInput) {
  const raw = String(pathInput || "").trim();
  if (!raw) {
    return [];
  }

  if (/^https?:\/\//i.test(raw)) {
    return [raw];
  }

  return [`${API_BASE_URL}/templates/preview?path=${encodeURIComponent(raw)}`];
}

async function previewFromPath(pathInput, options = {}) {
  if (options.switchToPreview) {
    switchSection("pdfPreviewerSection");
  }

  const raw = String(pathInput || "").trim();
  if (!raw) {
    setStatus(elements.previewStatus, "Enter a PDF path or URL first.", "error");
    return false;
  }

  const candidates = resolvePreviewCandidates(raw);
  if (!candidates.length) {
    setStatus(elements.previewStatus, "Unable to parse preview path.", "error");
    return false;
  }

  setStatus(elements.previewStatus, "Attempting to preview path...", "info");
  let lastReason = "unknown error";

  for (const candidate of candidates) {
    try {
      const response = await fetch(candidate, { method: "HEAD" });
      if (response.ok || response.status === 405) {
        elements.pdfFrame.src = candidate;
        setStatus(elements.previewStatus, `Previewing path: ${candidate}`, "success");
        return true;
      }
      lastReason = `${response.status} ${response.statusText}`.trim();
    } catch (error) {
      lastReason = error.message;
    }
  }

  const likelyServerLocal =
    !/^https?:\/\//i.test(raw) && !raw.startsWith("/");

  if (likelyServerLocal) {
    setStatus(
      elements.previewStatus,
      `Could not preview "${raw}". It looks like a server-local path and may not be web-accessible.`,
      "error"
    );
  } else {
    setStatus(
      elements.previewStatus,
      `Could not preview path. Last error: ${lastReason}`,
      "error"
    );
  }

  return false;
}

function renderTemplates() {
  elements.templatesList.innerHTML = "";

  if (!templates.length) {
    elements.templatesEmpty.classList.remove("hidden");
    return;
  }

  elements.templatesEmpty.classList.add("hidden");
  templates.forEach((template) => {
    const card = document.createElement("article");
    card.className = "template-card";

    const title = document.createElement("h3");
    title.textContent = `${template.name || "Untitled"} (id: ${template.id ?? "n/a"})`;

    const path = document.createElement("p");
    path.className = "template-meta";
    path.textContent = `pdf_path: ${template.pdf_path || ""}`;

    const fields = buildFieldsTable(template.fields || {});

    const actions = document.createElement("div");
    actions.className = "card-actions";

    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.dataset.action = "preview";
    previewButton.dataset.templateId = String(template.id);
    previewButton.textContent = "Preview This Template";

    const useFillButton = document.createElement("button");
    useFillButton.type = "button";
    useFillButton.dataset.action = "use-fill";
    useFillButton.dataset.templateId = String(template.id);
    useFillButton.textContent = "Use in Fill Form";

    actions.append(previewButton, useFillButton);
    card.append(title, path, fields, actions);
    elements.templatesList.append(card);
  });
}

function buildFieldsTable(fieldsDict) {
  const table = document.createElement("table");
  table.className = "fields-table";

  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Field</th><th>Type</th></tr>";
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  const entries = Object.entries(fieldsDict || {});
  if (!entries.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 2;
    cell.textContent = "No fields.";
    row.appendChild(cell);
    tbody.appendChild(row);
  } else {
    for (const [name, type] of entries) {
      const row = document.createElement("tr");
      const nameCell = document.createElement("td");
      nameCell.textContent = name;
      const typeCell = document.createElement("td");
      typeCell.textContent = TYPE_VALUE_TO_LABEL[type] || "Text";
      row.append(nameCell, typeCell);
      tbody.appendChild(row);
    }
  }
  table.appendChild(tbody);
  return table;
}

function normalizeFieldType(value) {
  return TYPE_VALUE_TO_LABEL[value] ? value : "string";
}

function syncFieldRowsFromDom() {
  const rowEls = Array.from(elements.fieldsBuilder.querySelectorAll(".field-row"));
  fieldRows = rowEls.map((rowEl) => ({
    name: rowEl.querySelector(".field-name").value,
    type: rowEl.querySelector(".field-type").value,
  }));
}

function renderFieldRows() {
  const fragment = document.createDocumentFragment();
  fieldRows.forEach((row, index) => {
    fragment.appendChild(buildFieldRow(row, index));
  });
  elements.fieldsBuilder.innerHTML = "";
  elements.fieldsBuilder.appendChild(fragment);
  renderFieldCountBadge();
}

function buildFieldRow(row, index) {
  const rowEl = document.createElement("div");
  rowEl.className = "field-row";
  rowEl.draggable = true;
  rowEl.dataset.index = String(index);

  const handle = document.createElement("span");
  handle.className = "field-drag-handle";
  handle.setAttribute("aria-hidden", "true");
  handle.textContent = "⋮⋮"; // two-column dots — reads as a grip handle

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.className = "field-name";
  nameInput.placeholder = "Give description here";
  nameInput.value = row.name || "";
  nameInput.addEventListener("input", () => {
    syncFieldRowsFromDom();
  });

  const typeSelect = document.createElement("select");
  typeSelect.className = "field-type";
  FIELD_TYPES.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t.value;
    opt.textContent = t.label;
    typeSelect.appendChild(opt);
  });
  typeSelect.value = normalizeFieldType(row.type);
  typeSelect.addEventListener("change", () => {
    syncFieldRowsFromDom();
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "field-delete-btn";
  deleteBtn.setAttribute("aria-label", "Remove field");
  deleteBtn.textContent = "✕"; // ✕
  deleteBtn.addEventListener("click", () => {
    syncFieldRowsFromDom();
    const rowIndex = Number(rowEl.dataset.index);
    fieldRows.splice(rowIndex, 1);
    renderFieldRows();
  });

  rowEl.addEventListener("dragstart", handleRowDragStart);
  rowEl.addEventListener("dragover", handleRowDragOver);
  rowEl.addEventListener("dragleave", handleRowDragLeave);
  rowEl.addEventListener("drop", handleRowDrop);
  rowEl.addEventListener("dragend", handleRowDragEnd);

  rowEl.append(handle, nameInput, typeSelect, deleteBtn);
  return rowEl;
}

function toggleMakeFillableHelp() {
  const willShow = elements.makeFillableHelp.classList.contains("hidden");
  elements.makeFillableHelp.classList.toggle("hidden", !willShow);
  elements.makeFillableHelpBtn.setAttribute("aria-expanded", String(willShow));
}

async function handleMakeFillableClick() {
  if (!selectedTemplateFile) {
    setStatus(elements.templateFormMessage, "Select a PDF first.", "error");
    return;
  }

  const templateDirectory = DEFAULT_TEMPLATE_DIRECTORY;

  elements.makeFillableBtn.disabled = true;
  const previousLabel = elements.makeFillableBtn.textContent;
  elements.makeFillableBtn.textContent = "Working...";
  setStatus(
    elements.templateFormMessage,
    "Uploading PDF and running fillable-field detection (this can take a minute)...",
    "info"
  );

  try {
    if (!uploadedPath) {
      const upload = await uploadTemplatePdf(selectedTemplateFile, templateDirectory);
      uploadedPath = upload.pdf_path;
    }

    const response = await fetch(`${API_BASE_URL}/templates/make-fillable`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pdf_path: uploadedPath }),
    });
    const body = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(extractErrorMessage(body, response.status));
    }

    uploadedPath = body.pdf_path;
    const count = typeof body.field_count === "number" ? body.field_count : null;
    uploadedFieldCount = count;
    renderFieldCountBadge();
    setStatus(
      elements.templateFormMessage,
      count !== null
        ? `Fillable PDF created — ${count} field${count === 1 ? "" : "s"} detected.`
        : "Fillable PDF created.",
      "success"
    );
    elements.makeFillableBtn.textContent = "Re-detect fields";
    elements.makeFillableBtn.disabled = false;
  } catch (error) {
    setStatus(elements.templateFormMessage, error.message, "error");
    elements.makeFillableBtn.textContent = previousLabel;
    elements.makeFillableBtn.disabled = false;
  }
}

function handleAddFieldClick() {
  syncFieldRowsFromDom();
  fieldRows.push({ name: "", type: "string" });
  renderFieldRows();
  const rows = elements.fieldsBuilder.querySelectorAll(".field-row .field-name");
  if (rows.length) {
    rows[rows.length - 1].focus();
  }
}

function handleRowDragStart(event) {
  const rowEl = event.currentTarget;
  dragSourceIndex = Number(rowEl.dataset.index);
  rowEl.classList.add("is-dragging");
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(dragSourceIndex));
  }
}

function handleRowDragOver(event) {
  event.preventDefault();
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = "move";
  }
  event.currentTarget.classList.add("drag-over");
}

function handleRowDragLeave(event) {
  event.currentTarget.classList.remove("drag-over");
}

function handleRowDrop(event) {
  event.preventDefault();
  const rowEl = event.currentTarget;
  rowEl.classList.remove("drag-over");
  const targetIndex = Number(rowEl.dataset.index);
  if (dragSourceIndex === null || dragSourceIndex === targetIndex) {
    return;
  }
  syncFieldRowsFromDom();
  const [moved] = fieldRows.splice(dragSourceIndex, 1);
  fieldRows.splice(targetIndex, 0, moved);
  dragSourceIndex = null;
  renderFieldRows();
}

function handleRowDragEnd(event) {
  event.currentTarget.classList.remove("is-dragging");
  elements.fieldsBuilder
    .querySelectorAll(".field-row.drag-over")
    .forEach((el) => el.classList.remove("drag-over"));
  dragSourceIndex = null;
}

function loadTemplates() {
  try {
    const raw = localStorage.getItem(STORAGE_TEMPLATES_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_error) {
    return [];
  }
}

function saveTemplates() {
  localStorage.setItem(STORAGE_TEMPLATES_KEY, JSON.stringify(templates));
}

function upsertTemplate(template) {
  const normalized = {
    id: template.id,
    name: template.name || "",
    pdf_path: template.pdf_path || "",
    fields: template.fields || {},
  };

  const index = templates.findIndex((item) => Number(item.id) === Number(template.id));
  if (index >= 0) {
    templates[index] = normalized;
  } else {
    templates.unshift(normalized);
  }

  saveTemplates();
}

function restorePreviewState() {
  const lastPath = localStorage.getItem(STORAGE_LAST_OUTPUT_KEY);
  if (lastPath) {
    elements.serverPdfPath.value = lastPath;
  }
}

async function parseJsonResponse(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch (_error) {
    return { raw: text };
  }
}

function extractErrorMessage(responseBody, statusCode) {
  if (responseBody && typeof responseBody === "object") {
    if (typeof responseBody.error === "string") {
      return responseBody.error;
    }
    if (Array.isArray(responseBody.detail)) {
      const first = responseBody.detail[0];
      if (first && typeof first.msg === "string") {
        return first.msg;
      }
    }
    if (typeof responseBody.detail === "string") {
      return responseBody.detail;
    }
    if (typeof responseBody.raw === "string") {
      return responseBody.raw;
    }
  }
  return `Request failed with status ${statusCode}.`;
}
