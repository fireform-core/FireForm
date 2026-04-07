import * as React from "react"
import { useState, useEffect } from "react"
import {
    FileStackIcon,
    Loader2Icon,
    AlertCircleIcon,
    Trash2Icon,
    EyeIcon,
    ChevronLeftIcon,
    XIcon,
    PencilIcon,
    CheckIcon,
} from "lucide-react"
import { listTemplates, listSchemas, deleteTemplate, updateTemplate, templatePdfUrl, type TemplateRecord, type ReportSchema } from "@/lib/api"
import { PdfViewer } from "@/components/pdf-viewer"
import { useAppNavigation } from "@/context/app-navigation-context"
import { Button } from "@/components/ui/button"

export default function TemplatesPanel() {
    const { goWorkspace } = useAppNavigation()
    const [templates, setTemplates] = useState<TemplateRecord[]>([])
    const [schemas, setSchemas] = useState<ReportSchema[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [viewingTemplate, setViewingTemplate] = useState<TemplateRecord | null>(null)
    const [renamingId, setRenamingId] = useState<number | null>(null)
    const [renameValue, setRenameValue] = useState("")
    const [renameSaving, setRenameSaving] = useState(false)

    useEffect(() => {
        Promise.all([listTemplates(), listSchemas()])
            .then(([t, s]) => { setTemplates(t); setSchemas(s) })
            .catch((e: Error) => setError(e.message))
            .finally(() => setLoading(false))
    }, [])

    async function handleRename(id: number) {
        if (!renameValue.trim()) return
        setRenameSaving(true)
        try {
            const updated = await updateTemplate(id, { name: renameValue })
            setTemplates((prev) => prev.map((t) => (t.id === id ? updated : t)))
            setRenamingId(null)
        } catch (err) {
            setError((err as Error).message)
        } finally {
            setRenameSaving(false)
        }
    }

    if (loading) return (
        <div className="flex items-center justify-center py-20">
            <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
        </div>
    )

    if (error) return (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircleIcon className="size-4 shrink-0" />{error}
        </div>
    )

    if (viewingTemplate) {
        return (
            <div className="flex flex-col gap-6">
                <div className="flex items-start gap-3">
                    <Button variant="ghost" size="icon" onClick={() => setViewingTemplate(null)} className="shrink-0 mt-0.5">
                        <ChevronLeftIcon className="size-4" />
                    </Button>
                    <div className="flex flex-col min-w-0 flex-1">
                        <h2 className="text-xl font-semibold">{viewingTemplate.name}</h2>
                        <p className="text-sm text-muted-foreground mt-0.5">PDF Template Preview</p>
                    </div>
                    <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5 shrink-0"
                        onClick={() => setViewingTemplate(null)}
                    >
                        <XIcon className="size-3.5" /> Close
                    </Button>
                </div>
                <div className="max-w-3xl mx-auto w-full">
                    <PdfViewer pdfUrl={templatePdfUrl(viewingTemplate.id)} maxHeight="80vh" />
                </div>
            </div>
        )
    }

    return (
        <div className="flex flex-col gap-6">
            <div>
                <h2 className="text-xl font-semibold">Templates</h2>
                <p className="text-sm text-muted-foreground mt-0.5">
                    All PDF templates in the library. Click "View PDF" to preview a template.
                </p>
            </div>

            {templates.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed py-14 text-center">
                    <FileStackIcon className="size-10 text-muted-foreground/40" />
                    <p className="font-medium text-sm">No templates yet</p>
                    <p className="text-xs text-muted-foreground">
                        Upload a PDF template via the Schemas section.
                    </p>
                </div>
            ) : (
                <div className="flex flex-col gap-2">
                    {templates.map((t) => (
                        <div
                            key={t.id}
                            className="flex items-center gap-3 rounded-lg border bg-card px-4 py-3"
                        >
                            <button
                                type="button"
                                onClick={() => setViewingTemplate(t)}
                                className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 hover:bg-primary/20 transition-colors"
                                title="View PDF"
                            >
                                <FileStackIcon className="size-4 text-primary" />
                            </button>
                            <div className="flex flex-col min-w-0 flex-1">
                                {renamingId === t.id ? (
                                    <form
                                        className="flex items-center gap-2"
                                        onSubmit={(e: React.FormEvent) => { e.preventDefault(); void handleRename(t.id) }}
                                    >
                                        <input
                                            autoFocus
                                            value={renameValue}
                                            onChange={(e) => setRenameValue(e.target.value)}
                                            className="text-sm font-medium border rounded px-2 py-0.5 bg-background text-foreground min-w-0 flex-1"
                                        />
                                        <Button type="submit" size="icon" variant="ghost" className="size-6" disabled={renameSaving || !renameValue.trim()}>
                                            <CheckIcon className="size-3.5" />
                                        </Button>
                                        <Button type="button" size="icon" variant="ghost" className="size-6" onClick={() => setRenamingId(null)}>
                                            <XIcon className="size-3.5" />
                                        </Button>
                                    </form>
                                ) : (
                                    <span className="font-medium text-sm truncate">{t.name}</span>
                                )}
                                <span className="text-xs text-muted-foreground truncate">{t.pdf_path}</span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="gap-1.5 text-xs"
                                    onClick={() => setViewingTemplate(t)}
                                >
                                    <EyeIcon className="size-3.5" /> View PDF
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-7 text-muted-foreground"
                                    title="Rename template"
                                    onClick={() => { setRenamingId(t.id); setRenameValue(t.name) }}
                                >
                                    <PencilIcon className="size-3.5" />
                                </Button>
                                {schemas.length > 0 && (
                                    <select
                                        defaultValue=""
                                        onChange={(e) => {
                                            const id = Number(e.target.value)
                                            if (id) goWorkspace(id)
                                        }}
                                        className="text-xs border rounded px-2 py-1 bg-background text-foreground"
                                        title="Open in schema"
                                    >
                                        <option value="" disabled>Open in schema…</option>
                                        {schemas.map((s) => (
                                            <option key={s.id} value={s.id}>{s.name}</option>
                                        ))}
                                    </select>
                                )}
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-7 text-muted-foreground hover:text-destructive"
                                    title="Delete template"
                                    onClick={async () => {
                                        try {
                                            await deleteTemplate(t.id)
                                            setTemplates((prev) => prev.filter((x) => x.id !== t.id))
                                        } catch (err) {
                                            setError((err as Error).message)
                                        }
                                    }}
                                >
                                    <Trash2Icon className="size-3.5" />
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
