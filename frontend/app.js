const STORAGE_TEMPLATES_KEY = "fireform.templates.v1";
const STORAGE_LAST_OUTPUT_KEY = "fireform.lastOutputPath.v1";
const STORAGE_TEMPLATE_DIR_KEY = "fireform.templateDirectory.v1";
const STORAGE_FIELD_ROWS_KEY = "fireform.fieldRows.v1";
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
  templateDirectory: document.getElementById("templateDirectory"),
  makeFillableBtn: document.getElementById("makeFillableBtn"),
  makeFillableHelpBtn: document.getElementById("makeFillableHelpBtn"),
  makeFillableHelp: document.getElementById("makeFillableHelp"),
  fieldsBuilder: document.getElementById("fieldsBuilder"),
  fieldCountBadge: document.getElementById("fieldCountBadge"),
  addFieldBtn: document.getElementById("addFieldBtn"),
  templateFormMessage: document.getElementById("templateFormMessage"),
  templateFormResponse: document.getElementById("templateFormResponse"),
  fillForm: document.getElementById("fillForm"),
  fillTemplateId: document.getElementById("fillTemplateId"),
  inputText: document.getElementById("inputText"),
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
let fieldRows = loadFieldRows();
let dragSourceIndex = null;
let uploadedPath = null;
let uploadedFieldCount = null;

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
  restoreTemplateDirectory();
  renderFieldRows();
  renderTemplates();
  restorePreviewState();
  updateSelectedFileMeta();
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
  elements.templateDirectory.addEventListener("input", handleTemplateDirectoryInput);
  elements.addFieldBtn.addEventListener("click", handleAddFieldClick);
  elements.makeFillableBtn.addEventListener("click", handleMakeFillableClick);
  elements.makeFillableHelpBtn.addEventListener("click", toggleMakeFillableHelp);
  bindDropZoneDragEvents();
  elements.fillForm.addEventListener("submit", handleFillSubmit);
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
      renderTemplates();
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

function handleTemplateDirectoryInput() {
  const directory = normalizeDirectory(elements.templateDirectory.value);
  localStorage.setItem(STORAGE_TEMPLATE_DIR_KEY, directory);
  updateSelectedFileMeta();
}

function restoreTemplateDirectory() {
  const saved = localStorage.getItem(STORAGE_TEMPLATE_DIR_KEY);
  if (saved) {
    elements.templateDirectory.value = saved;
  }
}

function normalizeDirectory(value) {
  return String(value || "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/\/+$/, "");
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
  const directory = normalizeDirectory(elements.templateDirectory.value);
  if (!directory) return;

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

// Prefill the field rows from the PDF's own form fields, but never overwrite
// rows the user has already started filling in.
function maybeSeedFieldRows(fields) {
  if (!Array.isArray(fields) || !fields.length) return;
  syncFieldRowsFromDom();
  if (!fieldRows.every((row) => !row.name.trim())) return;

  fieldRows = fields.map((f) => ({
    name: f.description || f.name || "",
    type: normalizeFieldType(f.type),
  }));
  saveFieldRows();
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
  if (!selectedTemplateFile) {
    elements.selectedFileMeta.textContent = "No PDF selected.";
    return;
  }

  const directory = normalizeDirectory(elements.templateDirectory.value);
  const destinationPath = directory
    ? `${directory}/${selectedTemplateFile.name}`
    : selectedTemplateFile.name;

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
  const templateDirectory = normalizeDirectory(elements.templateDirectory.value);
  const collected = collectFieldRows();

  if (!name || !templateDirectory || !selectedTemplateFile) {
    setStatus(
      elements.templateFormMessage,
      "Name, PDF file, and template directory are required.",
      "error"
    );
    return;
  }

  if (collected.error) {
    setStatus(elements.templateFormMessage, collected.error, "error");
    return;
  }

  try {
    localStorage.setItem(STORAGE_TEMPLATE_DIR_KEY, templateDirectory);
    saveFieldRows();
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
    await refreshTemplatesFromApi();
    elements.fillTemplateId.value = String(body.id || "");
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

async function handleFillSubmit(event) {
  event.preventDefault();
  clearJson(elements.fillFormResponse);
  setStatus(elements.fillFormMessage, "");

  const templateId = Number(elements.fillTemplateId.value);
  const inputText = elements.inputText.value.trim();

  if (!Number.isInteger(templateId) || templateId < 1) {
    setStatus(elements.fillFormMessage, "Template ID must be a positive integer.", "error");
    return;
  }

  if (!inputText) {
    setStatus(elements.fillFormMessage, "Input text is required.", "error");
    return;
  }

  const payload = {
    template_id: templateId,
    input_text: inputText,
  };

  try {
    setStatus(elements.fillFormMessage, "Submitting form fill request...", "info");
    const response = await fetch(`${API_BASE_URL}/forms/fill`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const body = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(extractErrorMessage(body, response.status));
    }

    if (body.output_pdf_path) {
      localStorage.setItem(STORAGE_LAST_OUTPUT_KEY, body.output_pdf_path);
      elements.serverPdfPath.value = body.output_pdf_path;
      await previewFromPath(body.output_pdf_path, { switchToPreview: true });
    }

    setStatus(
      elements.fillFormMessage,
      `Form filled (submission id: ${body.id}).`,
      "success"
    );
    showJson(elements.fillFormResponse, body);
  } catch (error) {
    setStatus(elements.fillFormMessage, error.message, "error");
  }
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
    elements.fillTemplateId.value = String(template.id);
    activateSection("fillFormSection");
    elements.fillTemplateId.focus();
    setStatus(
      elements.fillFormMessage,
      `Template ${template.id} loaded into Fill Form.`,
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

function loadFieldRows() {
  try {
    const raw = localStorage.getItem(STORAGE_FIELD_ROWS_KEY);
    if (!raw) {
      return DEFAULT_FIELD_ROWS.map((row) => ({ ...row }));
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return DEFAULT_FIELD_ROWS.map((row) => ({ ...row }));
    }
    return parsed
      .filter((item) => item && typeof item === "object")
      .map((item) => ({
        name: typeof item.name === "string" ? item.name : "",
        type: normalizeFieldType(item.type),
      }));
  } catch (_error) {
    return DEFAULT_FIELD_ROWS.map((row) => ({ ...row }));
  }
}

function normalizeFieldType(value) {
  return TYPE_VALUE_TO_LABEL[value] ? value : "string";
}

function saveFieldRows() {
  localStorage.setItem(STORAGE_FIELD_ROWS_KEY, JSON.stringify(fieldRows));
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
    saveFieldRows();
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
    saveFieldRows();
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
    saveFieldRows();
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

  const templateDirectory = normalizeDirectory(elements.templateDirectory.value);
  if (!templateDirectory) {
    setStatus(elements.templateFormMessage, "Template directory is required.", "error");
    return;
  }

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
  saveFieldRows();
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
  saveFieldRows();
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
