import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react"

export type AppPanel =
  | "dashboard"
  | "schemas"
  | "templates"

export type WizardView =
  | { kind: "browse" }
  | { kind: "create" }
  | { kind: "workspace"; schemaId: number }
  | { kind: "configure"; schemaId: number; templateId: number }
  | { kind: "fill"; schemaId: number }
  | { kind: "submission"; schemaId: number; submissionIds: number[] }

const PANEL_TITLE: Record<AppPanel, string> = {
  dashboard: "Dashboard",
  schemas: "Schemas",
  templates: "Templates",
}

type AppNavigationValue = {
  panel: AppPanel
  wizardView: WizardView
  navigatePanel: (panel: AppPanel) => void
  goHome: () => void
  quickCreate: () => void
  goBrowse: () => void
  goCreate: () => void
  goWorkspace: (schemaId: number) => void
  goConfigure: (schemaId: number, templateId: number) => void
  goFill: (schemaId: number) => void
  goSubmission: (schemaId: number, submissionIds: number[]) => void
  headerTitle: string
  setWorkspaceHeaderTitle: (title: string | null) => void
}

const AppNavigationContext = createContext<AppNavigationValue | null>(null)

export function AppNavigationProvider({ children }: { children: ReactNode }) {
  const [panel, setPanel] = useState<AppPanel>("dashboard")
  const [wizardView, setWizardView] = useState<WizardView>({ kind: "browse" })
  const [workspaceHeaderTitle, setWorkspaceHeaderTitle] = useState<string | null>(null)

  const navigatePanel = useCallback((next: AppPanel) => {
    setPanel(next)
    setWizardView({ kind: "browse" })
    setWorkspaceHeaderTitle(null)
  }, [])

  const goHome = useCallback(() => {
    setPanel("dashboard")
    setWizardView({ kind: "browse" })
    setWorkspaceHeaderTitle(null)
  }, [])

  const quickCreate = useCallback(() => {
    setPanel("schemas")
    setWizardView({ kind: "create" })
    setWorkspaceHeaderTitle(null)
  }, [])

  const goBrowse = useCallback(() => {
    setWizardView({ kind: "browse" })
    setWorkspaceHeaderTitle(null)
  }, [])

  const goCreate = useCallback(() => {
    setPanel("schemas")
    setWizardView({ kind: "create" })
    setWorkspaceHeaderTitle(null)
  }, [])

  const goWorkspace = useCallback((schemaId: number) => {
    setPanel("schemas")
    setWizardView({ kind: "workspace", schemaId })
    setWorkspaceHeaderTitle(null)
  }, [])

  const goConfigure = useCallback((schemaId: number, templateId: number) => {
    setPanel("schemas")
    setWizardView({ kind: "configure", schemaId, templateId })
    setWorkspaceHeaderTitle(null)
  }, [])

  const goFill = useCallback((schemaId: number) => {
    setPanel("schemas")
    setWizardView({ kind: "fill", schemaId })
    setWorkspaceHeaderTitle(null)
  }, [])

  const goSubmission = useCallback((schemaId: number, submissionIds: number[]) => {
    setPanel("schemas")
    setWizardView({ kind: "submission", schemaId, submissionIds })
    setWorkspaceHeaderTitle(null)
  }, [])

  const headerTitle = useMemo(() => {
    if (wizardView.kind === "create") return "New Report Schema"
    if (wizardView.kind === "workspace") {
      return workspaceHeaderTitle
        ? `Schemas · ${workspaceHeaderTitle}`
        : "Schema Workspace"
    }
    if (wizardView.kind === "configure") {
      return workspaceHeaderTitle
        ? `Configure Fields · ${workspaceHeaderTitle}`
        : "Configure PDF Fields"
    }
    if (wizardView.kind === "fill") {
      return workspaceHeaderTitle
        ? `Fill Schema · ${workspaceHeaderTitle}`
        : "Fill Schema"
    }
    if (wizardView.kind === "submission") {
      return workspaceHeaderTitle
        ? `Submission · ${workspaceHeaderTitle}`
        : "Submission Results"
    }
    return PANEL_TITLE[panel]
  }, [panel, wizardView, workspaceHeaderTitle])

  const value = useMemo(
    () => ({
      panel,
      wizardView,
      navigatePanel,
      goHome,
      quickCreate,
      goBrowse,
      goCreate,
      goWorkspace,
      goConfigure,
      goFill,
      goSubmission,
      headerTitle,
      setWorkspaceHeaderTitle,
    }),
    [panel, wizardView, navigatePanel, goHome, quickCreate, goBrowse, goCreate, goWorkspace, goConfigure, goFill, goSubmission, headerTitle]
  )

  return (
    <AppNavigationContext.Provider value={value}>
      {children}
    </AppNavigationContext.Provider>
  )
}

export function useAppNavigation() {
  const ctx = useContext(AppNavigationContext)
  if (!ctx) throw new Error("useAppNavigation must be used within AppNavigationProvider")
  return ctx
}
