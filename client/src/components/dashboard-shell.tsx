import * as React from "react"

import { AppSidebar } from "@/components/app-sidebar"
import { SiteHeader } from "@/components/site-header"
import { AppNavigationProvider, useAppNavigation } from "@/context/app-navigation-context"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import DashboardPage from "@/pages/dashboard"
import SchemasPanel from "@/pages/schemas-panel"
import TemplatesPanel from "@/pages/templates-panel"

function PanelRouter() {
  const { panel } = useAppNavigation()

  return (
    <>
      {panel === "dashboard" && <DashboardPage />}
      {panel === "schemas" && <SchemasPanel />}
      {panel === "templates" && <TemplatesPanel />}
    </>
  )
}

export function DashboardShell({ children }: { children?: React.ReactNode }) {
  return (
    <AppNavigationProvider>
      <SidebarProvider
        style={
          {
            "--sidebar-width": "calc(var(--spacing) * 64)",
            "--header-height": "calc(var(--spacing) * 12)",
          } as React.CSSProperties
        }
      >
        <AppSidebar variant="inset" />
        <SidebarInset className="max-h-svh min-h-0 overflow-hidden">
          <SiteHeader />
          <div className="flex min-h-0 flex-1 flex-col overflow-auto">
            <div className="@container/main flex min-h-0 flex-1 flex-col gap-2">
              <div className="flex min-h-0 flex-1 flex-col gap-4 px-4 py-4 md:gap-6 md:py-6 lg:px-6">
                <PanelRouter />
                {children}
              </div>
            </div>
          </div>
        </SidebarInset>
      </SidebarProvider>
    </AppNavigationProvider>
  )
}
