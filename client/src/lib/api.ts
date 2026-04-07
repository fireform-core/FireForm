const API_BASE = import.meta.env.VITE_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000"

export function getApiBase(): string {
  return API_BASE
}

export function templatePdfUrl(templateId: number): string {
  return `${API_BASE}/templates/${templateId}/pdf`
}

async function readDetail(res: Response): Promise<string> {
  try {
    const data: unknown = await res.json()
    if (typeof data === "object" && data !== null && "detail" in data) {
      const d = (data as { detail: unknown }).detail
      if (typeof d === "string") return d
      if (Array.isArray(d)) return JSON.stringify(d)
    }
    return JSON.stringify(data)
  } catch {
    return res.statusText
  }
}

export type Datatype = "string" | "int" | "date" | "enum"

export type ReportSchema = {
  id: number
  name: string
  description: string
  use_case: string
  created_at: string
}

export type TemplateRecord = {
  id: number
  name: string
  pdf_path: string
  fields: Record<string, string>
  created_at?: string
}

export type SchemaField = {
  id: number
  report_schema_id: number
  field_name: string
  source_template_id: number
  description: string
  data_type: Datatype
  word_limit: number | null
  required: boolean
  allowed_values: Record<string, unknown> | null
  canonical_name: string | null
}

export type SchemaFieldUpdate = {
  description?: string
  data_type?: Datatype
  word_limit?: number | null
  required?: boolean
  allowed_values?: Record<string, unknown> | null
  canonical_name?: string | null
}

export type CanonicalFieldEntry = {
  canonical_name: string
  description: string
  data_type: Datatype
  word_limit: number | null
  required: boolean
  allowed_values: Record<string, unknown> | null
  source_fields: SchemaField[]
}

export type CanonicalSchema = {
  report_schema_id: number
  canonical_fields: CanonicalFieldEntry[]
}

export async function listSchemas(): Promise<ReportSchema[]> {
  const res = await fetch(`${API_BASE}/schemas/`)
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<ReportSchema[]>
}

export async function createSchema(body: {
  name: string
  description: string
  use_case: string
}): Promise<ReportSchema> {
  const res = await fetch(`${API_BASE}/schemas/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<ReportSchema>
}

export async function getSchema(schemaId: number): Promise<ReportSchema> {
  const res = await fetch(`${API_BASE}/schemas/${schemaId}`)
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<ReportSchema>
}

export async function listSchemaFields(schemaId: number): Promise<SchemaField[]> {
  const res = await fetch(`${API_BASE}/schemas/${schemaId}/fields`)
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<SchemaField[]>
}

export async function updateSchemaField(
  schemaId: number,
  fieldId: number,
  body: SchemaFieldUpdate
): Promise<SchemaField> {
  const res = await fetch(`${API_BASE}/schemas/${schemaId}/fields/${fieldId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<SchemaField>
}

export async function listTemplates(): Promise<TemplateRecord[]> {
  const res = await fetch(`${API_BASE}/templates/`)
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<TemplateRecord[]>
}

export async function getTemplate(templateId: number): Promise<TemplateRecord> {
  const res = await fetch(`${API_BASE}/templates/${templateId}`)
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<TemplateRecord>
}

export async function createTemplateUpload(name: string, file: File): Promise<TemplateRecord> {
  const fd = new FormData()
  fd.set("name", name)
  fd.set("file", file)
  const res = await fetch(`${API_BASE}/templates/create`, {
    method: "POST",
    body: fd,
  })
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<TemplateRecord>
}

export async function associateTemplate(
  schemaId: number,
  templateId: number
): Promise<SchemaField[]> {
  const res = await fetch(`${API_BASE}/schemas/${schemaId}/templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template_id: templateId }),
  })
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<SchemaField[]>
}

export async function removeTemplateFromSchema(
  schemaId: number,
  templateId: number
): Promise<void> {
  const res = await fetch(`${API_BASE}/schemas/${schemaId}/templates/${templateId}`, {
    method: "DELETE",
  })
  if (!res.ok) throw new Error(await readDetail(res))
}

export async function updateSchema(
  schemaId: number,
  body: { name?: string; description?: string; use_case?: string }
): Promise<ReportSchema> {
  const res = await fetch(`${API_BASE}/schemas/${schemaId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<ReportSchema>
}

export async function deleteSchema(schemaId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/schemas/${schemaId}`, {
    method: "DELETE",
  })
  if (!res.ok) throw new Error(await readDetail(res))
}

export async function updateTemplate(
  templateId: number,
  body: { name?: string; fields?: Record<string, string>; pdf_path?: string }
): Promise<TemplateRecord> {
  const res = await fetch(`${API_BASE}/templates/${templateId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<TemplateRecord>
}

export async function canonizeSchema(schemaId: number): Promise<CanonicalSchema> {
  const res = await fetch(`${API_BASE}/schemas/${schemaId}/canonize`, {
    method: "POST",
  })
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json()
}

export async function deleteTemplate(templateId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/templates/${templateId}`, {
    method: "DELETE",
  })
  if (!res.ok) throw new Error(await readDetail(res))
}


export type ReportFillResponse = {
  schema_id: number
  input_text: string
  output_pdf_paths: string[]
  submission_ids: number[]
}

export type FormSubmission = {
  id: number
  name?: string
  template_id: number
  report_schema_id: number | null
  input_text: string
  output_pdf_path: string
  created_at: string
}

export async function fillSchema(
  schemaId: number,
  inputText: string,
  name?: string
): Promise<ReportFillResponse> {
  const payload: Record<string, unknown> = { input_text: inputText }
  if (name) payload.name = name
  const res = await fetch(`${API_BASE}/schemas/${schemaId}/fill`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<ReportFillResponse>
}

export async function listSubmissions(
  schemaId: number
): Promise<FormSubmission[]> {
  const res = await fetch(`${API_BASE}/schemas/${schemaId}/submissions`)
  if (!res.ok) throw new Error(await readDetail(res))
  return res.json() as Promise<FormSubmission[]>
}

export function submissionPdfUrl(submissionId: number): string {
  return `${API_BASE}/schemas/submissions/${submissionId}/pdf`
}
