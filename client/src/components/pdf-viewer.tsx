/**
 * PdfViewer — Read-only PDF viewer with page nav and zoom.
 * Reuses the react-pdf setup from PdfFieldConfigurator.
 */
import { useState } from "react"
import { Document, Page, pdfjs } from "react-pdf"
import "react-pdf/dist/Page/AnnotationLayer.css"
import "react-pdf/dist/Page/TextLayer.css"
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"

import {
    ChevronLeftIcon,
    ChevronRightIcon,
    Loader2Icon,
    AlertCircleIcon,
    ZoomInIcon,
    ZoomOutIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl

const SCALE_STEP = 0.25
const MIN_SCALE = 0.5
const MAX_SCALE = 3.0

interface PdfViewerProps {
    pdfUrl: string
    /** Optional max-height CSS value (defaults to 70vh) */
    maxHeight?: string
}

export function PdfViewer({ pdfUrl, maxHeight = "70vh" }: PdfViewerProps) {
    const [numPages, setNumPages] = useState(0)
    const [pageNum, setPageNum] = useState(1)
    const [scale, setScale] = useState(1.0)
    const [loadError, setLoadError] = useState<string | null>(null)

    return (
        <div className="flex flex-col gap-3">
            {/* Toolbar */}
            <div className="flex items-center gap-2 flex-wrap">
                <div className="flex items-center gap-1 border rounded-lg px-2 py-1 text-sm">
                    <Button
                        variant="ghost" size="icon" className="size-6"
                        disabled={pageNum <= 1}
                        onClick={() => setPageNum((p) => p - 1)}
                    >
                        <ChevronLeftIcon className="size-3" />
                    </Button>
                    <span className="px-1 text-xs tabular-nums">{pageNum} / {numPages || "…"}</span>
                    <Button
                        variant="ghost" size="icon" className="size-6"
                        disabled={pageNum >= numPages}
                        onClick={() => setPageNum((p) => p + 1)}
                    >
                        <ChevronRightIcon className="size-3" />
                    </Button>
                </div>

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
            </div>

            {loadError && (
                <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    <AlertCircleIcon className="size-4 shrink-0" />{loadError}
                </div>
            )}

            <div
                className="relative border rounded-lg overflow-auto bg-muted/20"
                style={{ maxHeight }}
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
                        renderAnnotationLayer={false}
                        renderTextLayer={false}
                    />
                </Document>
            </div>
        </div>
    )
}
