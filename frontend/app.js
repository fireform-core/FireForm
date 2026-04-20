const STORAGE_TEMPLATES_KEY = "fireform.templates.v1";
const STORAGE_LAST_OUTPUT_KEY = "fireform.lastOutputPath.v1";
const STORAGE_TEMPLATE_DIR_KEY = "fireform.templateDirectory.v1";
const API_BASE_URL = "http://127.0.0.1:8000";

const elements = {
  tabs: Array.from(document.querySelectorAll(".tab")),
  panels: Array.from(document.querySelectorAll(".panel")),
  templateForm: document.getElementById("templateForm"),
  templateName: document.getElementById("templateName"),
  templatePdfFile: document.getElementById("templatePdfFile"),
  pdfDropZone: document.getElementById("pdfDropZone"),
  selectedFileMeta: document.getElementById("selectedFileMeta"),
  templateDirectory: document.getElementById("templateDirectory"),
  templateFields: document.getElementById("templateFields"),
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

initialize();

async function initialize() {
  bindEvents();
  restoreTemplateDirectory();
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
    setStatus(elements.templateFormMessage, "Please select a PDF file.", "error");
    updateSelectedFileMeta();
    return;
  }

  selectedTemplateFile = file;
  clearJson(elements.templateFormResponse);
  setStatus(elements.templateFormMessage, "");
  updateSelectedFileMeta();
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

function normalizeFields(rawFields) {
  try {
    const parsed = JSON.parse(rawFields);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: "Fields must be a JSON object." };
    }
    return { value: parsed };
  } catch (_error) {
    return { error: "Fields JSON is invalid. Fix syntax and try again." };
  }
}

async function handleTemplateSubmit(event) {
  event.preventDefault();
  clearJson(elements.templateFormResponse);
  setStatus(elements.templateFormMessage, "");

  const name = elements.templateName.value.trim();
  const templateDirectory = normalizeDirectory(elements.templateDirectory.value);
  const normalized = normalizeFields(elements.templateFields.value.trim());

  if (!name || !templateDirectory || !selectedTemplateFile) {
    setStatus(
      elements.templateFormMessage,
      "Name, PDF file, and template directory are required.",
      "error"
    );
    return;
  }

  if (normalized.error) {
    setStatus(elements.templateFormMessage, normalized.error, "error");
    return;
  }

  try {
    localStorage.setItem(STORAGE_TEMPLATE_DIR_KEY, templateDirectory);
    setStatus(elements.templateFormMessage, "Copying PDF into project directory...", "info");

    const upload = await uploadTemplatePdf(selectedTemplateFile, templateDirectory);

    const payload = {
      name,
      pdf_path: upload.pdf_path,
      fields: normalized.value,
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

    setStatus(
      elements.templateFormMessage,
      `Template created (id: ${body.id}). PDF saved at ${upload.pdf_path}.`,
      "success"
    );
    showJson(elements.templateFormResponse, body);
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

  if (inputText.length > 10_000) {
    setStatus(elements.fillFormMessage, "Input text is too long (max 10,000 characters).", "error");
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

    const fields = document.createElement("pre");
    fields.className = "json-output";
    fields.textContent = JSON.stringify(template.fields || {}, null, 2);

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
