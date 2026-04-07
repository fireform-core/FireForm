import * as React from "react"
import { useState, useEffect, useCallback, useMemo } from "react"
import {
    DatabaseIcon,
    FileStackIcon,
    PlusIcon,
    ArrowRightIcon,
    ChevronLeftIcon,
    CheckIcon,
    FileIcon,
    TrashIcon,
    SlidersHorizontalIcon,
    Loader2Icon,
    AlertCircleIcon,
    SendIcon,
    ClockIcon,
    ExternalLinkIcon,
    DownloadIcon,
    PencilIcon,
    Trash2Icon,
    SparklesIcon,
    XIcon,
} from "lucide-react"
import { PdfFieldConfigurator } from "@/components/pdf-field-configurator"
import { PdfViewer } from "@/components/pdf-viewer"
import {
    listSchemas,
    createSchema,
    getSchema,
    updateSchema,
    deleteSchema,
    listSchemaFields,
    listTemplates,
    createTemplateUpload,
    associateTemplate,
    removeTemplateFromSchema,
    canonizeSchema,
    fillSchema,
    listSubmissions,
    submissionPdfUrl,
    templatePdfUrl,
    type ReportSchema,
    type SchemaField,
    type TemplateRecord,
    type FormSubmission,
} from "@/lib/api"
import { useAppNavigation } from "@/context/app-navigation-context"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

export default function SchemasPanel() {
    const { wizardView, goBrowse, goCreate, goWorkspace, goConfigure, setWorkspaceHeaderTitle } =
        useAppNavigation()

    useEffect(() => {
        if (wizardView.kind === "browse" || wizardView.kind === "create") {
            setWorkspaceHeaderTitle(null)
        }
    }, [wizardView.kind, setWorkspaceHeaderTitle])

    if (wizardView.kind === "create")
        return <CreateSchemaView onBack={goBrowse} onCreate={(id) => goWorkspace(id)} />

    if (wizardView.kind === "workspace")
        return (
            <WorkspaceView
                schemaId={wizardView.schemaId}
                onBack={goBrowse}
                onConfigure={(tId) => goConfigure(wizardView.schemaId, tId)}
                onTitleLoaded={setWorkspaceHeaderTitle}
            />
        )

    if (wizardView.kind === "fill")
        return (
            <FillSchemaView
                schemaId={wizardView.schemaId}
                onBack={() => goWorkspace(wizardView.schemaId)}
                onTitleLoaded={setWorkspaceHeaderTitle}
            />
        )

    if (wizardView.kind === "submission")
        return (
            <SubmissionView
                schemaId={wizardView.schemaId}
                submissionIds={wizardView.submissionIds}
                onBack={() => goWorkspace(wizardView.schemaId)}
                onTitleLoaded={setWorkspaceHeaderTitle}
            />
        )

    if (wizardView.kind === "configure")
        return (
            <ConfigureView
                schemaId={wizardView.schemaId}
                templateId={wizardView.templateId}
                onBack={() => goWorkspace(wizardView.schemaId)}
                onTitleLoaded={setWorkspaceHeaderTitle}
            />
        )

    return <BrowseView onNew={goCreate} onOpen={(id) => goWorkspace(id)} />
}

function BrowseView({ onNew, onOpen }: { onNew: () => void; onOpen: (id: number) => void }) {
    const [schemas, setSchemas] = useState<ReportSchema[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        listSchemas()
            .then(setSchemas)
            .catch((e: Error) => setError(e.message))
            .finally(() => setLoading(false))
    }, [])

    async function handleDelete(id: number) {
        try {
            await deleteSchema(id)
            setSchemas((prev) => prev.filter((s) => s.id !== id))
        } catch (err) {
            setError((err as Error).message)
        }
    }

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-semibold">Report Schemas</h2>
                    <p className="text-sm text-muted-foreground mt-0.5">
                        Create and manage schemas that define how fields are extracted from PDFs.
                    </p>
                </div>
                <Button onClick={onNew} className="gap-2 shrink-0">
                    <PlusIcon className="size-4" /> New Schema
                </Button>
            </div>

            {loading && <LoadingSpinner />}
            {error && <ErrorBanner message={error} />}
            {!loading && !error && schemas.length === 0 && (
                <EmptyState
                    icon={<DatabaseIcon className="size-10 text-muted-foreground/40" />}
                    title="No schemas yet"
                    description="Create your first report schema to get started."
                    action={<Button onClick={onNew} className="gap-2"><PlusIcon className="size-4" />New Schema</Button>}
                />
            )}
            {!loading && !error && schemas.length > 0 && (
                <div className="grid gap-3 sm:grid-cols-2">
                    {schemas.map((s) => (
                        <div
                            key={s.id}
                            className="flex items-start gap-4 rounded-xl border bg-card text-left px-5 py-4 hover:bg-accent transition-colors group"
                        >
                            <button
                                type="button"
                                onClick={() => onOpen(s.id)}
                                className="flex items-start gap-4 min-w-0 flex-1 text-left"
                            >
                                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                                    <DatabaseIcon className="size-5 text-primary" />
                                </div>
                                <div className="flex flex-col min-w-0 flex-1">
                                    <span className="font-medium text-sm">{s.name}</span>
                                    <span className="text-muted-foreground text-xs mt-0.5 line-clamp-2">{s.description}</span>
                                </div>
                                <ArrowRightIcon className="size-4 text-muted-foreground shrink-0 mt-0.5" />
                            </button>
                            <Button
                                size="icon"
                                variant="ghost"
                                className="size-7 shrink-0 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                                title="Delete schema"
                                onClick={(e) => { e.stopPropagation(); void handleDelete(s.id) }}
                            >
                                <Trash2Icon className="size-3.5" />
                            </Button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

function CreateSchemaView({ onBack, onCreate }: { onBack: () => void; onCreate: (id: number) => void }) {
    const [name, setName] = useState("")
    const [description, setDescription] = useState("")
    const [useCase, setUseCase] = useState("")
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault()
        setLoading(true)
        setError(null)
        try {
            const schema = await createSchema({ name, description, use_case: useCase })
            onCreate(schema.id)
        } catch (err) {
            setError((err as Error).message)
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="flex flex-col gap-6 max-w-xl">
            <div className="flex items-center gap-3">
                <Button variant="ghost" size="icon" onClick={onBack}><ChevronLeftIcon className="size-4" /></Button>
                <div>
                    <h2 className="text-xl font-semibold">New Report Schema</h2>
                    <p className="text-sm text-muted-foreground">Enter a name, description and use case for the new schema.</p>
                </div>
            </div>

            {error && <ErrorBanner message={error} />}

            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <FormField label="Name" htmlFor="schema-name" required>
                    <input
                        id="schema-name"
                        required
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="e.g. Business Permit Application"
                        className="ff-input"
                    />
                </FormField>
                <FormField label="Description" htmlFor="schema-desc">
                    <input
                        id="schema-desc"
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Short description of what this schema covers"
                        className="ff-input"
                    />
                </FormField>
                <FormField label="Use Case" htmlFor="schema-usecase">
                    <textarea
                        id="schema-usecase"
                        value={useCase}
                        onChange={(e) => setUseCase(e.target.value)}
                        rows={3}
                        placeholder="Describe the extraction goal (e.g. 'Extract owner name, TIN, and permit year.')"
                        className="ff-input resize-none"
                    />
                </FormField>
                <Button type="submit" disabled={loading || !name.trim()} className="self-start gap-2">
                    {loading ? <><Loader2Icon className="size-4 animate-spin" />Creating…</> : <><CheckIcon className="size-4" />Create Schema</>}
                </Button>
            </form>

            <InputStyles />
        </div>
    )
}

type SubmissionGroup = {
    key: string
    name: string | undefined
    inputText: string
    createdAt: string
    submissions: FormSubmission[]
}

function groupSubmissions(subs: FormSubmission[]): SubmissionGroup[] {
    const sorted = [...subs].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )
    const groups: SubmissionGroup[] = []
    for (const sub of sorted) {
        const ts = new Date(sub.created_at)
        const bucket = Math.floor(ts.getTime() / 60_000)
        const key = `${sub.name ?? ""}|${sub.input_text}|${bucket}`
        const existing = groups.find((g) => g.key === key)
        if (existing) {
            existing.submissions.push(sub)
        } else {
            groups.push({
                key,
                name: sub.name,
                inputText: sub.input_text,
                createdAt: sub.created_at,
                submissions: [sub],
            })
        }
    }
    return groups
}

function WorkspaceView({
    schemaId,
    onBack,
    onConfigure,
    onTitleLoaded,
}: {
    schemaId: number
    onBack: () => void
    onConfigure: (templateId: number) => void
    onTitleLoaded: (t: string | null) => void
}) {
    const { goFill, goSubmission } = useAppNavigation()
    const [schema, setSchema] = useState<ReportSchema | null>(null)
    const [allTemplates, setAllTemplates] = useState<TemplateRecord[]>([])
    const [schemaTemplateIds, setSchemaTemplateIds] = useState<Set<number>>(new Set())
    const [fields, setFields] = useState<SchemaField[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const [editing, setEditing] = useState(false)
    const [editName, setEditName] = useState("")
    const [editDesc, setEditDesc] = useState("")
    const [editUseCase, setEditUseCase] = useState("")
    const [editSaving, setEditSaving] = useState(false)

    const [canonizing, setCanonizing] = useState(false)

    const [showAddForm, setShowAddForm] = useState(false)
    const [addTemplateTab, setAddTemplateTab] = useState<"upload" | "existing">("upload")
    const [tName, setTName] = useState("")
    const [tFile, setTFile] = useState<File | null>(null)
    const [existingPickId, setExistingPickId] = useState("")
    const [uploading, setUploading] = useState(false)
    const [uploadError, setUploadError] = useState<string | null>(null)

    const [submissions, setSubmissions] = useState<FormSubmission[]>([])
    const [subsLoading, setSubsLoading] = useState(false)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            const [schemas, templates, schemaFields] = await Promise.all([
                listSchemas(),
                listTemplates(),
                listSchemaFields(schemaId),
            ])
            const s = schemas.find((x) => x.id === schemaId)
            if (!s) throw new Error("Schema not found")
            setSchema(s)
            onTitleLoaded(s.name)
            setAllTemplates(templates)
            const tIds = new Set(schemaFields.map((f) => f.source_template_id))
            setSchemaTemplateIds(tIds)
            setFields(schemaFields)
        } catch (e) {
            setError((e as Error).message)
        } finally {
            setLoading(false)
        }
    }, [schemaId, onTitleLoaded])

    useEffect(() => { void load() }, [load])

    async function handleUploadTemplate(e: React.FormEvent) {
        e.preventDefault()
        if (!tFile) return
        setUploading(true)
        setUploadError(null)
        try {
            const tpl = await createTemplateUpload(tName || tFile.name, tFile)
            const allFields = await associateTemplate(schemaId, tpl.id)
            setSchemaTemplateIds((prev) => new Set([...prev, tpl.id]))
            setAllTemplates((prev) => [...prev, tpl])
            setFields(allFields)
            setShowAddForm(false)
            setTName("")
            setTFile(null)
            setAddTemplateTab("upload")
            setExistingPickId("")
        } catch (err) {
            setUploadError((err as Error).message)
        } finally {
            setUploading(false)
        }
    }

    async function handleRemoveTemplate(templateId: number) {
        try {
            await removeTemplateFromSchema(schemaId, templateId)
            setSchemaTemplateIds((prev) => { const s = new Set(prev); s.delete(templateId); return s })
            setFields((prev) => prev.filter((f) => f.source_template_id !== templateId))
        } catch (err) {
            setError((err as Error).message)
        }
    }

    async function handleAddExistingTemplate() {
        const id = Number(existingPickId)
        if (!Number.isFinite(id) || id <= 0) return
        setUploading(true)
        setUploadError(null)
        try {
            const allFields = await associateTemplate(schemaId, id)
            setSchemaTemplateIds((prev) => new Set([...prev, id]))
            setFields(allFields)
            setShowAddForm(false)
            setExistingPickId("")
            setAddTemplateTab("upload")
        } catch (err) {
            setUploadError((err as Error).message)
        } finally {
            setUploading(false)
        }
    }

    function startEditing() {
        if (!schema) return
        setEditName(schema.name)
        setEditDesc(schema.description)
        setEditUseCase(schema.use_case)
        setEditing(true)
    }

    async function handleSaveEdit(e: React.FormEvent) {
        e.preventDefault()
        setEditSaving(true)
        setError(null)
        try {
            const updated = await updateSchema(schemaId, {
                name: editName,
                description: editDesc,
                use_case: editUseCase,
            })
            setSchema(updated)
            onTitleLoaded(updated.name)
            setEditing(false)
        } catch (err) {
            setError((err as Error).message)
        } finally {
            setEditSaving(false)
        }
    }

    async function handleDeleteSchema() {
        setError(null)
        try {
            await deleteSchema(schemaId)
            onBack()
        } catch (err) {
            setError((err as Error).message)
        }
    }

    async function handleCanonize() {
        setCanonizing(true)
        setError(null)
        try {
            await canonizeSchema(schemaId)
            const refreshed = await listSchemaFields(schemaId)
            setFields(refreshed)
        } catch (err) {
            setError((err as Error).message)
        } finally {
            setCanonizing(false)
        }
    }

    const loadSubmissions = useCallback(async () => {
        setSubsLoading(true)
        try {
            const subs = await listSubmissions(schemaId)
            setSubmissions(subs)
        } catch {
            // silently ignore
        } finally {
            setSubsLoading(false)
        }
    }, [schemaId])

    useEffect(() => { void loadSubmissions() }, [loadSubmissions])

    const linkedTemplates = allTemplates.filter((t) => schemaTemplateIds.has(t.id))
    const templatesAvailableToLink = allTemplates.filter((t) => !schemaTemplateIds.has(t.id))

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-start gap-3">
                <Button variant="ghost" size="icon" onClick={onBack} className="shrink-0 mt-0.5">
                    <ChevronLeftIcon className="size-4" />
                </Button>
                <div className="flex flex-col min-w-0 flex-1">
                    <h2 className="text-xl font-semibold">{schema?.name ?? "Loading…"}</h2>
                    {schema?.description && <p className="text-sm text-muted-foreground mt-0.5">{schema.description}</p>}
                    {schema?.use_case && <p className="text-xs text-muted-foreground mt-1 italic">Use case: {schema.use_case}</p>}
                </div>
                <div className="flex gap-2 shrink-0">
                    {!loading && !error && schema && (
                        <>
                            <Button variant="outline" size="icon" className="size-8" title="Edit schema" onClick={startEditing}>
                                <PencilIcon className="size-3.5" />
                            </Button>
                            <Button variant="outline" size="icon" className="size-8 text-muted-foreground hover:text-destructive" title="Delete schema" onClick={() => void handleDeleteSchema()}>
                                <Trash2Icon className="size-3.5" />
                            </Button>
                        </>
                    )}
                    {!loading && !error && linkedTemplates.length > 0 && (
                        <Button onClick={() => goFill(schemaId)} className="gap-2">
                            <SendIcon className="size-4" />
                            Fill Schema
                        </Button>
                    )}
                </div>
            </div>

            {editing && (
                <form onSubmit={handleSaveEdit} className="flex flex-col gap-3 border rounded-lg px-4 py-3 bg-card">
                    <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">Edit Schema</span>
                        <Button type="button" variant="ghost" size="icon" className="size-7" onClick={() => setEditing(false)}>
                            <XIcon className="size-3.5" />
                        </Button>
                    </div>
                    <FormField label="Name" htmlFor="edit-name" required>
                        <input id="edit-name" required value={editName} onChange={(e) => setEditName(e.target.value)} className="ff-input" />
                    </FormField>
                    <FormField label="Description" htmlFor="edit-desc">
                        <input id="edit-desc" value={editDesc} onChange={(e) => setEditDesc(e.target.value)} className="ff-input" />
                    </FormField>
                    <FormField label="Use Case" htmlFor="edit-usecase">
                        <textarea id="edit-usecase" value={editUseCase} onChange={(e) => setEditUseCase(e.target.value)} rows={2} className="ff-input resize-none" />
                    </FormField>
                    <div className="flex gap-2">
                        <Button type="submit" size="sm" disabled={editSaving || !editName.trim()} className="gap-1.5">
                            {editSaving ? <><Loader2Icon className="size-3.5 animate-spin" />Saving…</> : <><CheckIcon className="size-3.5" />Save</>}
                        </Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                    </div>
                </form>
            )}

            {loading && <LoadingSpinner />}
            {error && <ErrorBanner message={error} />}

            {!loading && !error && (
                <section className="flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                        <h3 className="font-medium text-sm">Templates</h3>
                        <div className="flex gap-2">
                            {linkedTemplates.length > 0 && (
                                <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={canonizing}
                                    onClick={() => void handleCanonize()}
                                    className="gap-1.5"
                                >
                                    {canonizing
                                        ? <><Loader2Icon className="size-3.5 animate-spin" />Canonizing…</>
                                        : <><SparklesIcon className="size-3.5" />Canonize Fields</>
                                    }
                                </Button>
                            )}
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                                setShowAddForm((v) => {
                                    const next = !v
                                    if (next) {
                                        setAddTemplateTab("upload")
                                        setExistingPickId("")
                                        setUploadError(null)
                                        setTName("")
                                        setTFile(null)
                                    }
                                    return next
                                })
                            }
                            className="gap-1.5"
                        >
                            <PlusIcon className="size-3.5" /> Add Template
                        </Button>
                        </div>
                    </div>

                    {showAddForm && (
                        <div className="flex flex-col gap-3 border rounded-lg px-4 py-3 bg-card">
                            {uploadError && <ErrorBanner message={uploadError} />}
                            <Tabs value={addTemplateTab} onValueChange={(v) => setAddTemplateTab(v as "upload" | "existing")}>
                                <TabsList className="w-full sm:w-auto">
                                    <TabsTrigger value="upload" className="gap-1.5">
                                        <FileIcon className="size-3.5" /> Upload PDF
                                    </TabsTrigger>
                                    <TabsTrigger value="existing" className="gap-1.5">
                                        <FileStackIcon className="size-3.5" /> From library
                                    </TabsTrigger>
                                </TabsList>
                                <TabsContent value="upload" className="mt-3 flex flex-col gap-3">
                                    <form onSubmit={handleUploadTemplate} className="flex flex-col gap-3">
                                        <FormField label="Name" htmlFor="tpl-name">
                                            <input
                                                id="tpl-name"
                                                value={tName}
                                                onChange={(e) => setTName(e.target.value)}
                                                placeholder="Template name (optional, falls back to file name)"
                                                className="ff-input"
                                            />
                                        </FormField>
                                        <FormField label="PDF File" htmlFor="tpl-file" required>
                                            <input
                                                id="tpl-file"
                                                type="file"
                                                accept=".pdf"
                                                required
                                                onChange={(e) => setTFile(e.target.files?.[0] ?? null)}
                                                className="ff-input"
                                            />
                                        </FormField>
                                        <div className="flex gap-2">
                                            <Button type="submit" size="sm" disabled={uploading || !tFile} className="gap-1.5">
                                                {uploading ? <><Loader2Icon className="size-3.5 animate-spin" />Uploading…</> : "Upload & Add"}
                                            </Button>
                                            <Button
                                                type="button"
                                                size="sm"
                                                variant="ghost"
                                                onClick={() => {
                                                    setShowAddForm(false)
                                                    setUploadError(null)
                                                }}
                                            >
                                                Cancel
                                            </Button>
                                        </div>
                                    </form>
                                </TabsContent>
                                <TabsContent value="existing" className="mt-3 flex flex-col gap-3">
                                    {templatesAvailableToLink.length === 0 ? (
                                        <p className="text-sm text-muted-foreground">
                                            Every template in the library is already linked to this schema, or there are no templates yet. Upload a new PDF in the other tab.
                                        </p>
                                    ) : (
                                        <FormField label="Template" htmlFor="tpl-existing">
                                            <select
                                                id="tpl-existing"
                                                value={existingPickId}
                                                onChange={(e) => setExistingPickId(e.target.value)}
                                                className="ff-input"
                                            >
                                                <option value="">Select a template…</option>
                                                {templatesAvailableToLink.map((t) => (
                                                    <option key={t.id} value={String(t.id)}>{t.name}</option>
                                                ))}
                                            </select>
                                        </FormField>
                                    )}
                                    <div className="flex gap-2">
                                        <Button
                                            type="button"
                                            size="sm"
                                            disabled={
                                                uploading ||
                                                templatesAvailableToLink.length === 0 ||
                                                !existingPickId
                                            }
                                            className="gap-1.5"
                                            onClick={() => void handleAddExistingTemplate()}
                                        >
                                            {uploading ? <><Loader2Icon className="size-3.5 animate-spin" />Adding…</> : "Add to schema"}
                                        </Button>
                                        <Button
                                            type="button"
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => {
                                                setShowAddForm(false)
                                                setUploadError(null)
                                            }}
                                        >
                                            Cancel
                                        </Button>
                                    </div>
                                </TabsContent>
                            </Tabs>
                        </div>
                    )}

                    {linkedTemplates.length === 0 && !showAddForm ? (
                        <EmptyState
                            icon={<FileStackIcon className="size-8 text-muted-foreground/40" />}
                            title="No templates yet"
                            description='Click "Add Template" to upload a new PDF or choose an existing template from the library.'
                        />
                    ) : (
                        <div className="flex flex-col gap-2">
                            {linkedTemplates.map((t) => {
                                const tFields = fields.filter((f) => f.source_template_id === t.id)
                                return (
                                    <div key={t.id} className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3">
                                        <a
                                            href={templatePdfUrl(t.id)}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 hover:bg-primary/20 transition-colors"
                                            title="Preview PDF"
                                        >
                                            <FileIcon className="size-4 text-primary" />
                                        </a>
                                        <div className="flex flex-col min-w-0 flex-1">
                                            <span className="font-medium text-sm truncate">{t.name}</span>
                                            <span className="text-xs text-muted-foreground">
                                                {tFields.length} detected field{tFields.length !== 1 ? "s" : ""}
                                            </span>
                                        </div>
                                        <div className="flex gap-2 shrink-0">
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="gap-1.5 text-xs"
                                                onClick={() => onConfigure(t.id)}
                                            >
                                                <SlidersHorizontalIcon className="size-3.5" /> Configure Fields
                                            </Button>
                                            <Button
                                                size="icon"
                                                variant="ghost"
                                                className="size-8 text-muted-foreground hover:text-destructive"
                                                onClick={() => handleRemoveTemplate(t.id)}
                                            >
                                                <TrashIcon className="size-3.5" />
                                            </Button>
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </section>
            )}

            {!loading && !error && (() => {
                const groups = groupSubmissions(submissions)
                return (
                    <section className="flex flex-col gap-3">
                        <h3 className="font-medium text-sm">Past Submissions</h3>
                        {subsLoading && <LoadingSpinner />}
                        {!subsLoading && groups.length === 0 && (
                            <p className="text-sm text-muted-foreground py-4 text-center">
                                No submissions yet for this schema.
                            </p>
                        )}
                        {!subsLoading && groups.length > 0 && (
                            <div className="flex flex-col gap-2">
                                {groups.map((group) => (
                                    <div
                                        key={group.key}
                                        className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3"
                                    >
                                        <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10">
                                            <ClockIcon className="size-4 text-primary" />
                                        </div>
                                        <div className="flex flex-col min-w-0 flex-1">
                                            <span className="font-medium text-sm truncate">
                                                {group.name || `Submission #${group.submissions[0].id}`}
                                            </span>
                                            <span className="text-xs text-muted-foreground">
                                                {new Date(group.createdAt).toLocaleString()}
                                                {group.submissions.length > 1 && (
                                                    <> · {group.submissions.length} documents</>
                                                )}
                                            </span>
                                        </div>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="gap-1.5 text-xs"
                                            onClick={() => goSubmission(schemaId, group.submissions.map((s) => s.id))}
                                        >
                                            <FileIcon className="size-3.5" /> View Results
                                        </Button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>
                )
            })()}
            <InputStyles />
        </div>
    )
}

function FillSchemaView({
    schemaId,
    onBack,
    onTitleLoaded,
}: {
    schemaId: number
    onBack: () => void
    onTitleLoaded: (t: string | null) => void
}) {
    const { goSubmission } = useAppNavigation()
    const [schema, setSchema] = useState<ReportSchema | null>(null)
    const [submissionName, setSubmissionName] = useState("")
    const [inputText, setInputText] = useState("")
    const [filling, setFilling] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        getSchema(schemaId)
            .then((s) => {
                setSchema(s)
                onTitleLoaded(s.name)
            })
            .catch((e: Error) => setError(e.message))
            .finally(() => setLoading(false))
    }, [schemaId, onTitleLoaded])

    async function handleFill(e: React.FormEvent) {
        e.preventDefault()
        if (!inputText.trim()) return
        setFilling(true)
        setError(null)
        try {
            const result = await fillSchema(schemaId, inputText, submissionName || undefined)
            if (result.submission_ids.length > 0) {
                goSubmission(schemaId, result.submission_ids)
            }
        } catch (err) {
            setError((err as Error).message)
        } finally {
            setFilling(false)
        }
    }

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-start gap-3">
                <Button variant="ghost" size="icon" onClick={onBack} className="shrink-0 mt-0.5">
                    <ChevronLeftIcon className="size-4" />
                </Button>
                <div className="flex flex-col min-w-0">
                    <h2 className="text-xl font-semibold">Fill Schema</h2>
                    <p className="text-sm text-muted-foreground mt-0.5">
                        {loading ? "Loading…" : schema ? schema.name : "Unknown schema"}
                    </p>
                    {schema?.use_case && (
                        <p className="text-xs text-muted-foreground mt-1 italic">Use case: {schema.use_case}</p>
                    )}
                </div>
            </div>

            {error && <ErrorBanner message={error} />}

            <form onSubmit={handleFill} className="flex flex-col gap-4">
                <FormField label="Submission Name" htmlFor="fill-name">
                    <input
                        id="fill-name"
                        value={submissionName}
                        onChange={(e) => setSubmissionName(e.target.value)}
                        placeholder="e.g. John Doe - Business Permit (optional)"
                        className="ff-input"
                        disabled={filling}
                    />
                </FormField>
                <FormField label="Input Text" htmlFor="fill-input" required>
                    <textarea
                        id="fill-input"
                        required
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        rows={14}
                        placeholder="Paste or type the source text that should be extracted into PDF form fields…"
                        className="ff-input resize-y"
                        disabled={filling}
                    />
                </FormField>
                <p className="text-xs text-muted-foreground -mt-2">
                    The system will extract relevant data from this text and fill the associated PDF templates.
                </p>
                <Button type="submit" disabled={filling || !inputText.trim()} className="self-start gap-2">
                    {filling ? (
                        <><Loader2Icon className="size-4 animate-spin" />Filling…</>
                    ) : (
                        <><SendIcon className="size-4" />Fill Schema</>
                    )}
                </Button>
            </form>

            <InputStyles />
        </div>
    )
}

function SubmissionView({
    schemaId,
    submissionIds,
    onBack,
    onTitleLoaded,
}: {
    schemaId: number
    submissionIds: number[]
    onBack: () => void
    onTitleLoaded: (t: string | null) => void
}) {
    const [submissions, setSubmissions] = useState<FormSubmission[]>([])
    const [templateNames, setTemplateNames] = useState<Record<number, string>>({})
    const [activeIdx, setActiveIdx] = useState(0)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const idSet = useMemo(() => new Set(submissionIds), [submissionIds])

    useEffect(() => {
        setLoading(true)
        Promise.all([getSchema(schemaId), listSubmissions(schemaId), listTemplates()])
            .then(([schema, allSubs, templates]) => {
                onTitleLoaded(schema.name)
                const matched = allSubs.filter((s) => idSet.has(s.id))
                if (matched.length === 0) throw new Error("Submissions not found")
                setSubmissions(matched)
                const names: Record<number, string> = {}
                for (const t of templates) names[t.id] = t.name
                setTemplateNames(names)
            })
            .catch((e: Error) => setError(e.message))
            .finally(() => setLoading(false))
    }, [schemaId, idSet, onTitleLoaded])

    const activeSub = submissions[activeIdx] ?? null
    const pdfUrl = activeSub ? submissionPdfUrl(activeSub.id) : null
    const groupName = submissions[0]?.name
    const groupDate = submissions[0]?.created_at

    function handleDownload() {
        if (!pdfUrl || !activeSub) return
        const a = document.createElement("a")
        a.href = pdfUrl
        a.download = `submission-${activeSub.id}.pdf`
        a.target = "_blank"
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
    }

    function handleDownloadAll() {
        for (const sub of submissions) {
            const a = document.createElement("a")
            a.href = submissionPdfUrl(sub.id)
            a.download = `submission-${sub.id}.pdf`
            a.target = "_blank"
            document.body.appendChild(a)
            a.click()
            document.body.removeChild(a)
        }
    }

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-start gap-3">
                <Button variant="ghost" size="icon" onClick={onBack} className="shrink-0 mt-0.5">
                    <ChevronLeftIcon className="size-4" />
                </Button>
                <div className="flex flex-col min-w-0 flex-1">
                    <h2 className="text-xl font-semibold">Submission Results</h2>
                    {groupDate && (
                        <p className="text-sm text-muted-foreground mt-0.5">
                            {groupName || `Submission #${submissions[0]?.id}`}
                            {" · "}
                            {new Date(groupDate).toLocaleString()}
                            {submissions.length > 1 && (
                                <> · {submissions.length} documents</>
                            )}
                        </p>
                    )}
                </div>
                <div className="flex gap-2 shrink-0">
                    {submissions.length > 1 && (
                        <Button variant="outline" onClick={handleDownloadAll} className="gap-2">
                            <DownloadIcon className="size-4" />
                            Download All
                        </Button>
                    )}
                    <Button onClick={handleDownload} className="gap-2">
                        <DownloadIcon className="size-4" />
                        Download{submissions.length > 1 ? " Current" : " PDF"}
                    </Button>
                </div>
            </div>

            {loading && <LoadingSpinner />}
            {error && <ErrorBanner message={error} />}

            {!loading && !error && submissions.length > 0 && (
                <div className="flex flex-col gap-6">
                    {/* Document tabs (only if multiple) */}
                    {submissions.length > 1 && (
                        <div className="flex gap-2 flex-wrap">
                            {submissions.map((sub, idx) => {
                                const label = templateNames[sub.template_id] || `Document ${idx + 1}`
                                const isActive = idx === activeIdx
                                return (
                                    <button
                                        key={sub.id}
                                        type="button"
                                        onClick={() => setActiveIdx(idx)}
                                        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                                            isActive
                                                ? "bg-primary text-primary-foreground"
                                                : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground"
                                        }`}
                                    >
                                        {label}
                                    </button>
                                )
                            })}
                        </div>
                    )}

                    {pdfUrl && (
                        <section className="flex flex-col items-center gap-3">
                            <div className="flex items-center gap-3 self-end">
                                <a
                                    href={pdfUrl}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
                                >
                                    <ExternalLinkIcon className="size-3" /> Open in new tab
                                </a>
                            </div>
                            <div className="w-full max-w-3xl mx-auto">
                                <PdfViewer pdfUrl={pdfUrl} maxHeight="75vh" />
                            </div>
                        </section>
                    )}

                    {activeSub?.input_text && (
                        <section className="flex flex-col gap-2">
                            <h3 className="font-medium text-sm">Input Text</h3>
                            <div className="rounded-lg border bg-muted/30 px-4 py-3 text-sm whitespace-pre-wrap max-h-48 overflow-auto">
                                {activeSub.input_text}
                            </div>
                        </section>
                    )}
                </div>
            )}
        </div>
    )
}

function ConfigureView({
    schemaId,
    templateId,
    onBack,
    onTitleLoaded,
}: {
    schemaId: number
    templateId: number
    onBack: () => void
    onTitleLoaded: (t: string | null) => void
}) {
    const [fields, setFields] = useState<SchemaField[]>([])
    const [allSchemaFields, setAllSchemaFields] = useState<SchemaField[]>([])
    const [templateName, setTemplateName] = useState("")
    const [pdfUrl, setPdfUrl] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        Promise.all([listSchemaFields(schemaId), listTemplates()])
            .then(([fetchedFields, templates]) => {
                setAllSchemaFields(fetchedFields)
                const tplFields = fetchedFields.filter((f) => f.source_template_id === templateId)
                setFields(tplFields)
                const tpl = templates.find((t) => t.id === templateId)
                const name = tpl?.name ?? `Template #${templateId}`
                setTemplateName(name)
                onTitleLoaded(name)
                setPdfUrl(templatePdfUrl(templateId))
            })
            .catch((e: Error) => setError(e.message))
            .finally(() => setLoading(false))
    }, [schemaId, templateId, onTitleLoaded])

    return (
        <div className="flex flex-col gap-4">
            <div className="flex items-start gap-3">
                <Button variant="ghost" size="icon" onClick={onBack} className="shrink-0 mt-0.5">
                    <ChevronLeftIcon className="size-4" />
                </Button>
                <div>
                    <h2 className="text-xl font-semibold">Configure Fields</h2>
                    <p className="text-sm text-muted-foreground mt-0.5">
                        {templateName} — hover a field on the PDF to configure it
                    </p>
                </div>
            </div>

            {error && <ErrorBanner message={error} />}
            {loading && <LoadingSpinner />}

            {!loading && !error && pdfUrl && (
                <PdfFieldConfigurator
                    pdfUrl={pdfUrl}
                    schemaFields={fields}
                    allSchemaFields={allSchemaFields}
                    schemaId={schemaId}
                    onFieldSaved={(updated) => {
                        setFields((prev) => prev.map((f) => (f.id === updated.id ? updated : f)))
                        setAllSchemaFields((prev) => prev.map((f) => (f.id === updated.id ? updated : f)))
                    }}
                />
            )}

            {!loading && !error && !pdfUrl && (
                <EmptyState
                    icon={<SlidersHorizontalIcon className="size-8 text-muted-foreground/40" />}
                    title="PDF not available"
                    description="The PDF for this template could not be loaded."
                />
            )}
        </div>
    )
}

function FormField({
    label,
    htmlFor,
    required,
    children,
}: {
    label: string
    htmlFor: string
    required?: boolean
    children: React.ReactNode
}) {
    return (
        <div className="flex flex-col gap-1">
            <label htmlFor={htmlFor} className="text-sm font-medium">
                {label}{required && <span className="text-destructive ml-0.5">*</span>}
            </label>
            {children}
        </div>
    )
}

function EmptyState({ icon, title, description, action }: {
    icon: React.ReactNode; title: string; description: string; action?: React.ReactNode
}) {
    return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed py-14 text-center">
            {icon}
            <div>
                <p className="font-medium text-sm">{title}</p>
                <p className="text-xs text-muted-foreground mt-1 max-w-xs">{description}</p>
            </div>
            {action}
        </div>
    )
}

function LoadingSpinner() {
    return (
        <div className="flex items-center justify-center py-12">
            <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
        </div>
    )
}

function ErrorBanner({ message }: { message: string }) {
    return (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircleIcon className="size-4 shrink-0" />
            {message}
        </div>
    )
}

function InputStyles() {
    return (
        <style>{`
      .ff-input {
        width: 100%;
        border-radius: var(--radius-md);
        border: 1px solid var(--border);
        background: var(--background);
        color: var(--foreground);
        font: inherit;
        font-size: 0.875rem;
        padding: 7px 11px;
        outline: none;
        transition: border-color 0.15s;
        box-sizing: border-box;
      }
      .ff-input:focus {
        border-color: var(--primary);
        box-shadow: 0 0 0 3px oklch(0.78 0.17 65 / 20%);
      }
    `}</style>
    )
}
