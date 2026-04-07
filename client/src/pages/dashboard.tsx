import * as React from "react"
import { useState, useEffect } from "react"
import { DatabaseIcon, FileStackIcon, PlusIcon, ArrowRightIcon, ClockIcon, Loader2Icon } from "lucide-react"
import { listSchemas, listTemplates, type ReportSchema, type TemplateRecord } from "@/lib/api"
import { useAppNavigation } from "@/context/app-navigation-context"
import { Button } from "@/components/ui/button"

export default function DashboardPage() {
    const { quickCreate, navigatePanel, goWorkspace } = useAppNavigation()
    const [schemas, setSchemas] = useState<ReportSchema[]>([])
    const [templates, setTemplates] = useState<TemplateRecord[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        Promise.all([listSchemas(), listTemplates()])
            .then(([s, t]) => { setSchemas(s); setTemplates(t) })
            .catch(() => { /* silent — show empty state */ })
            .finally(() => setLoading(false))
    }, [])

    const recentSchemas = schemas.slice(0, 5)

    return (
        <div className="flex flex-col gap-8">
            {/* Hero */}
            <div className="flex flex-col gap-1">
                <h2 className="text-2xl font-semibold tracking-tight">Welcome to FireForm</h2>
                <p className="text-muted-foreground text-sm">
                    Build report schemas, attach PDF templates, and configure fields — all in one place.
                </p>
            </div>

            <div className="flex flex-wrap gap-3">
                <Button onClick={quickCreate} className="gap-2">
                    <PlusIcon className="size-4" /> New Schema
                </Button>
                <Button variant="outline" onClick={() => navigatePanel("templates")} className="gap-2">
                    <FileStackIcon className="size-4" /> Browse Templates
                </Button>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <StatCard
                    icon={<DatabaseIcon className="size-5 text-primary" />}
                    label="Total Schemas"
                    value={loading ? "…" : String(schemas.length)}
                    sub="active report schemas"
                />
                <StatCard
                    icon={<FileStackIcon className="size-5 text-primary" />}
                    label="Total Templates"
                    value={loading ? "…" : String(templates.length)}
                    sub="PDF templates uploaded"
                />
                <StatCard
                    icon={<ClockIcon className="size-5 text-primary" />}
                    label="Library Status"
                    value={loading ? "…" : schemas.length === 0 ? "Empty" : "Active"}
                    sub={schemas.length === 0 ? "create your first schema" : "data ready to extract"}
                />
            </div>

            <section className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                    <h3 className="font-medium">Recent Schemas</h3>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="gap-1 text-muted-foreground text-xs"
                        onClick={() => navigatePanel("schemas")}
                    >
                        View all <ArrowRightIcon className="size-3" />
                    </Button>
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-8">
                        <Loader2Icon className="size-5 animate-spin text-muted-foreground" />
                    </div>
                ) : recentSchemas.length === 0 ? (
                    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed py-10 text-center">
                        <DatabaseIcon className="size-8 text-muted-foreground/40" />
                        <div>
                            <p className="font-medium text-sm">No schemas yet</p>
                            <p className="text-xs text-muted-foreground mt-1">Create your first schema to get started.</p>
                        </div>
                        <Button size="sm" onClick={quickCreate} className="gap-2"><PlusIcon className="size-4" />New Schema</Button>
                    </div>
                ) : (
                    <div className="flex flex-col gap-2">
                        {recentSchemas.map((s) => (
                            <button
                                key={s.id}
                                type="button"
                                onClick={() => goWorkspace(s.id)}
                                className="flex items-center gap-4 rounded-lg border bg-card text-left px-4 py-3 hover:bg-accent transition-colors"
                            >
                                <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10">
                                    <DatabaseIcon className="size-4 text-primary" />
                                </div>
                                <div className="flex flex-col min-w-0 flex-1">
                                    <span className="font-medium text-sm truncate">{s.name}</span>
                                    <span className="text-muted-foreground text-xs truncate">{s.description ?? "No description"}</span>
                                </div>
                                <ArrowRightIcon className="size-4 text-muted-foreground shrink-0" />
                            </button>
                        ))}
                    </div>
                )}
            </section>
        </div>
    )
}

function StatCard({ icon, label, value, sub }: {
    icon: React.ReactNode; label: string; value: string; sub: string
}) {
    return (
        <div className="rounded-xl border bg-card px-5 py-4 flex flex-col gap-3">
            <div className="flex items-center gap-2">
                <div className="flex size-8 items-center justify-center rounded-md bg-primary/10">{icon}</div>
                <span className="text-sm text-muted-foreground">{label}</span>
            </div>
            <div>
                <p className="text-3xl font-semibold tracking-tight">{value}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>
            </div>
        </div>
    )
}