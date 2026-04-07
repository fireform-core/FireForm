/**
 * PdfFieldConfigurator
 *
 * Renders a PDF page read-only (via react-pdf / pdf.js), extracts
 * all AcroForm widget annotations, then lays invisible hotspot <div>s
 * perfectly over each form field.  Hovering a hotspot shows a Shadcn
 * Popover with editable config for that field — without touching the
 * file itself.
 */
import * as React from "react"
import { useEffect, useRef, useState, useCallback } from "react"
import { Document, Page, pdfjs } from "react-pdf"
import "react-pdf/dist/Page/AnnotationLayer.css"
import "react-pdf/dist/Page/TextLayer.css"
// Direct dependency so Vite can resolve (react-pdf nests pdfjs-dist, so bare "pdfjs-dist" was missing at client root).
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"

import {
    CheckIcon,
    ChevronLeftIcon,
    ChevronRightIcon,
    Loader2Icon,
    AlertCircleIcon,
    ZoomInIcon,
    ZoomOutIcon,
} from "lucide-react"
import { updateSchemaField, type SchemaField } from "@/lib/api"
import { Button } from "@/components/ui/button"

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl

/* ─── Types ─────────────────────────────────────────────────────── */
interface PdfAnnotation {
    fieldName: string
    rect: [number, number, number, number] // [x1, y1, x2, y2] in PDF space
    subtype: string
}

interface OverlayField {
    annotation: PdfAnnotation
    schemaField: SchemaField | null
    css: {
        left: number
        top: number
        width: number
        height: number
    }
}

/* ─── Props ─────────────────────────────────────────────────────── */
interface PdfFieldConfiguratorProps {
    /** URL of the PDF to render (e.g. from api.templatePdfUrl(id)) */
    pdfUrl: string
    /** Schema fields for this template (used to match annotations) */
    schemaFields: SchemaField[]
    /** All schema fields across all templates (used for canonical name suggestions) */
    allSchemaFields: SchemaField[]
    schemaId: number
    onFieldSaved?: (updated: SchemaField) => void
}

const SCALE_STEP = 0.25
const MIN_SCALE = 0.5
const MAX_SCALE = 3.0

/* ─── Main component ─────────────────────────────────────────────── */
export function PdfFieldConfigurator({
    pdfUrl,
    schemaFields,
    allSchemaFields,
    schemaId,
    onFieldSaved,
}: PdfFieldConfiguratorProps) {
    const [numPages, setNumPages] = useState<number>(0)
    const [pageNum, setPageNum] = useState(1)
    const [scale, setScale] = useState(1.0)
    const [pageSize, setPageSize] = useState<{ width: number; height: number } | null>(null)
    const [overlayFields, setOverlayFields] = useState<OverlayField[]>([])
    const [activeField, setActiveField] = useState<OverlayField | null>(null)
    const [loadError, setLoadError] = useState<string | null>(null)
    const containerRef = useRef<HTMLDivElement>(null)

    // Build field name → SchemaField lookup
    const fieldIndex = React.useMemo(() => {
        const map = new Map<string, SchemaField>()
        schemaFields.forEach((f) => map.set(f.field_name, f))
        console.log(map)
        return map
    }, [schemaFields])

    /** Called after react-pdf renders the page successfully.
     *  We get the viewport to do coordinate mapping. */
    const onPageSuccess = useCallback(
        async (page: { getAnnotations: () => Promise<PdfAnnotation[]>; getViewport: (o: { scale: number }) => { width: number; height: number } }) => {
            const viewport = page.getViewport({ scale: 1.0 })
            setPageSize({ width: viewport.width, height: viewport.height })

            const annotations = await page.getAnnotations()
            const widgets = annotations.filter((a) => a.subtype === "Widget" && a.fieldName)

            /**
             * PDF coordinate space: origin bottom-left, y grows upward.
             * CSS coordinate space: origin top-left, y grows downward.
             *
             * rect = [x1, y1, x2, y2]
             * CSS left   = x1 * scale
             * CSS top    = (pageHeight - y2) * scale
             * CSS width  = (x2 - x1) * scale
             * CSS height = (y2 - y1) * scale
             */
            const fields: OverlayField[] = widgets.map((annot) => {
                const [x1, y1, x2, y2] = annot.rect
                console.log(annot.fieldName, fieldIndex.get(annot.fieldName))
                return {
                    annotation: annot,
                    schemaField: fieldIndex.get(annot.fieldName) ?? null,
                    css: {
                        left: x1 * scale,
                        top: (viewport.height - y2) * scale,
                        width: (x2 - x1) * scale,
                        height: (y2 - y1) * scale,
                    },
                }
            })
            setOverlayFields(fields)
            setActiveField(null)
        },
        [scale, fieldIndex]
    )

    // Recalculate overlay positions when scale changes
    useEffect(() => {
        if (!pageSize) return
        setOverlayFields((prev) =>
            prev.map((of) => {
                const [x1, , x2, y2] = of.annotation.rect
                const [, y1b] = of.annotation.rect
                return {
                    ...of,
                    css: {
                        left: x1 * scale,
                        top: (pageSize.height - y2) * scale,
                        width: (x2 - x1) * scale,
                        height: (y2 - y1b) * scale,
                    },
                }
            })
        )
    }, [scale, pageSize])

    return (
        <div className="flex flex-col gap-3">
            {/* Toolbar */}
            <div className="flex items-center gap-2 flex-wrap">
                {/* Page navigation */}
                <div className="flex items-center gap-1 border rounded-lg px-2 py-1 text-sm">
                    <Button
                        variant="ghost" size="icon" className="size-6"
                        disabled={pageNum <= 1}
                        onClick={() => { setPageNum((p) => p - 1); setActiveField(null) }}
                    >
                        <ChevronLeftIcon className="size-3" />
                    </Button>
                    <span className="px-1 text-xs tabular-nums">{pageNum} / {numPages || "…"}</span>
                    <Button
                        variant="ghost" size="icon" className="size-6"
                        disabled={pageNum >= numPages}
                        onClick={() => { setPageNum((p) => p + 1); setActiveField(null) }}
                    >
                        <ChevronRightIcon className="size-3" />
                    </Button>
                </div>

                {/* Zoom */}
                <div className="flex items-center gap-1 border rounded-lg px-2 py-1 text-sm">
                    <Button
                        variant="ghost" size="icon" className="size-6"
                        disabled={scale <= MIN_SCALE}
                        onClick={() => setScale((s) => Math.max(MIN_SCALE, +(s - SCALE_STEP).toFixed(2)))}
                    >
                        <ZoomOutIcon className="size-3" />
                    </Button>
                    <span className="px-1 text-xs tabular-nums w-10 text-center">{Math.round(scale * 100)}%</span>
                    <Button
                        variant="ghost" size="icon" className="size-6"
                        disabled={scale >= MAX_SCALE}
                        onClick={() => setScale((s) => Math.min(MAX_SCALE, +(s + SCALE_STEP).toFixed(2)))}
                    >
                        <ZoomInIcon className="size-3" />
                    </Button>
                </div>

                <span className="text-xs text-muted-foreground ml-auto">
                    {overlayFields.length} field{overlayFields.length !== 1 ? "s" : ""} detected — hover to configure
                </span>
            </div>

            {loadError && (
                <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    <AlertCircleIcon className="size-4 shrink-0" />{loadError}
                </div>
            )}

            {/* PDF + Overlay container */}
            <div className="flex gap-4 items-start">
                {/* PDF canvas area */}
                <div
                    ref={containerRef}
                    className="relative border rounded-lg overflow-auto bg-muted/20 flex-1 min-w-0"
                    style={{ maxHeight: "70vh" }}
                    onClick={() => setActiveField(null)}
                >
                    <Document
                        file={pdfUrl}
                        onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                        onLoadError={(e) => setLoadError(e.message)}
                        loading={
                            <div className="flex items-center justify-center py-20">
                                <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
                            </div>
                        }
                    >
                        <Page
                            pageNumber={pageNum}
                            scale={scale}
                            onLoadSuccess={onPageSuccess as never}
                            renderAnnotationLayer={false}
                            renderTextLayer={false}
                        />
                    </Document>

                    {/* Invisible field hotspots */}
                    {overlayFields.map((of, i) => (
                        <div
                            key={i}
                            onClick={(e) => { e.stopPropagation(); setActiveField(of === activeField ? null : of) }}
                            style={{
                                position: "absolute",
                                left: of.css.left,
                                top: of.css.top,
                                width: Math.max(of.css.width, 20),
                                height: Math.max(of.css.height, 16),
                                cursor: "pointer",
                                zIndex: 10,
                            }}
                            title={of.annotation.fieldName}
                            className={[
                                "rounded border transition-colors",
                                of === activeField
                                    ? "bg-primary/25 border-primary"
                                    : "bg-red-500/20 border-red-500/60 hover:bg-red-500/30",
                            ].join(" ")}
                        />
                    ))}
                </div>

                {/* Config panel — shown when a field is active */}
                {activeField && (
                    <FieldConfigPanel
                        key={activeField.annotation.fieldName}
                        field={activeField}
                        schemaId={schemaId}
                        allSchemaFields={allSchemaFields}
                        onSaved={(updated) => {
                            // Update local overlay
                            setOverlayFields((prev) =>
                                prev.map((of) =>
                                    of.annotation.fieldName === activeField.annotation.fieldName
                                        ? { ...of, schemaField: updated }
                                        : of
                                )
                            )
                            setActiveField((prev) =>
                                prev ? { ...prev, schemaField: updated } : prev
                            )
                            onFieldSaved?.(updated)
                        }}
                        onClose={() => setActiveField(null)}
                    />
                )}
            </div>
        </div>
    )
}

const DATATYPES = ["string", "int", "date", "enum"] as const

function FieldConfigPanel({
    field,
    schemaId,
    allSchemaFields,
    onSaved,
    onClose,
}: {
    field: OverlayField
    schemaId: number
    allSchemaFields: SchemaField[]
    onSaved: (updated: SchemaField) => void
    onClose: () => void
}) {
    const sf = field.schemaField
    const [description, setDescription] = useState(sf?.description ?? "")
    const [dataType, setDataType] = useState(sf?.data_type ?? "string")
    const [required, setRequired] = useState(sf?.required ?? false)
    const [wordLimit, setWordLimit] = useState<string>(sf?.word_limit != null ? String(sf.word_limit) : "")
    const [canonicalName, setCanonicalName] = useState(sf?.canonical_name ?? "")
    const [allowedValues, setAllowedValues] = useState(
        sf?.allowed_values && "values" in sf.allowed_values
            ? (sf.allowed_values.values as string[]).join(", ")
            : ""
    )
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const existingCanonicalNames = React.useMemo(() => {
        const names = new Set<string>()
        allSchemaFields.forEach((f) => {
            if (f.canonical_name) names.add(f.canonical_name)
        })
        return [...names].sort()
    }, [allSchemaFields])

    async function handleSave(e: React.FormEvent) {
        e.preventDefault()
        if (!sf) return
        setSaving(true)
        setError(null)
        try {
            const updated = await updateSchemaField(schemaId, sf.id, {
                description,
                data_type: dataType as "string" | "int" | "date" | "enum",
                required,
                word_limit: dataType === "string" && wordLimit !== "" ? Number(wordLimit) : null,
                canonical_name: canonicalName.trim() || null,
                allowed_values: dataType === "enum" && allowedValues.trim()
                    ? { values: allowedValues.split(",").map((v) => v.trim()).filter(Boolean) }
                    : null,
            })
            onSaved(updated)
        } catch (err) {
            setError((err as Error).message)
        } finally {
            setSaving(false)
        }
    }

    return (
        <div className="w-72 shrink-0 rounded-xl border bg-card shadow-lg flex flex-col max-h-[70vh] overflow-y-auto">
            {/* Header */}
            <div className="flex items-start justify-between px-4 pt-4 pb-3 border-b gap-2 sticky top-0 bg-card z-10">
                <div className="min-w-0">
                    <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium mb-0.5">PDF field</p>
                    <p className="font-mono text-sm font-semibold truncate" title={field.annotation.fieldName}>
                        {field.annotation.fieldName}
                    </p>
                </div>
                <button
                    type="button"
                    onClick={onClose}
                    className="text-muted-foreground hover:text-foreground text-xs shrink-0 mt-0.5"
                >
                    ✕
                </button>
            </div>

            {!sf ? (
                <div className="px-4 py-4 text-xs text-muted-foreground">
                    This field isn't mapped to any schema field yet. Add it via "Add Template" to configure it.
                </div>
            ) : (
                <form onSubmit={handleSave} className="flex flex-col gap-3 px-4 py-4">
                    {error && (
                        <p className="text-xs text-destructive flex items-center gap-1">
                            <AlertCircleIcon className="size-3 shrink-0" />{error}
                        </p>
                    )}

                    {/* Read-only native field name */}
                    <div className="flex flex-col gap-1">
                        <label className="text-xs font-medium text-muted-foreground">Native field name</label>
                        <div className="ff-input-sm font-mono text-xs text-muted-foreground bg-muted/50 select-text">
                            {sf.field_name}
                        </div>
                    </div>

                    {/* Canonical name */}
                    <div className="flex flex-col gap-1">
                        <label htmlFor="cfg-canonical" className="text-xs font-medium text-muted-foreground">Canonical name</label>
                        <input
                            id="cfg-canonical"
                            list="canonical-options"
                            value={canonicalName}
                            onChange={(e) => setCanonicalName(e.target.value)}
                            placeholder="Select or type a name…"
                            className="ff-input-sm"
                        />
                        <datalist id="canonical-options">
                            {existingCanonicalNames.map((n) => (
                                <option key={n} value={n} />
                            ))}
                        </datalist>
                    </div>

                    {/* Data type */}
                    <div className="flex flex-col gap-1">
                        <label htmlFor="cfg-type" className="text-xs font-medium text-muted-foreground">Type</label>
                        <select
                            id="cfg-type"
                            value={dataType}
                            onChange={(e) => setDataType(e.target.value as typeof DATATYPES[number])}
                            className="ff-input-sm"
                        >
                            {DATATYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                        </select>
                    </div>

                    {/* Description */}
                    <div className="flex flex-col gap-1">
                        <label htmlFor="cfg-desc" className="text-xs font-medium text-muted-foreground">Description</label>
                        <input
                            id="cfg-desc"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="What does this field capture?"
                            className="ff-input-sm"
                        />
                    </div>

                    {/* Word limit — only for string type */}
                    {dataType === "string" && (
                        <div className="flex flex-col gap-1">
                            <label htmlFor="cfg-wl" className="text-xs font-medium text-muted-foreground">Word limit</label>
                            <input
                                id="cfg-wl"
                                type="number"
                                min={0}
                                value={wordLimit}
                                onChange={(e) => setWordLimit(e.target.value)}
                                placeholder="None"
                                className="ff-input-sm"
                            />
                        </div>
                    )}

                    {/* Allowed values — only for enum type */}
                    {dataType === "enum" && (
                        <div className="flex flex-col gap-1">
                            <label htmlFor="cfg-av" className="text-xs font-medium text-muted-foreground">Allowed values</label>
                            <input
                                id="cfg-av"
                                value={allowedValues}
                                onChange={(e) => setAllowedValues(e.target.value)}
                                placeholder="comma-separated, e.g. Yes, No"
                                className="ff-input-sm"
                            />
                        </div>
                    )}

                    {/* Required */}
                    <label className="flex items-center gap-2 cursor-pointer text-xs">
                        <input
                            type="checkbox"
                            checked={required}
                            onChange={(e) => setRequired(e.target.checked)}
                            className="accent-primary"
                        />
                        <span>Required</span>
                    </label>

                    <Button type="submit" size="sm" disabled={saving} className="mt-1 gap-1.5">
                        {saving
                            ? <><Loader2Icon className="size-3.5 animate-spin" />Saving…</>
                            : <><CheckIcon className="size-3.5" />Save Changes</>
                        }
                    </Button>
                </form>
            )}

            <style>{`
        .ff-input-sm {
          width: 100%;
          border-radius: var(--radius-sm);
          border: 1px solid var(--border);
          background: var(--background);
          color: var(--foreground);
          font: inherit;
          font-size: 0.8125rem;
          padding: 5px 9px;
          outline: none;
          transition: border-color 0.15s;
          box-sizing: border-box;
        }
        .ff-input-sm:focus {
          border-color: var(--primary);
          box-shadow: 0 0 0 2px oklch(0.78 0.17 65 / 20%);
        }
      `}</style>
        </div>
    )
}
