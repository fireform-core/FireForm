import * as React from "react"
import {
  CommandIcon,
  DatabaseIcon,
  FileStackIcon,
  LayoutDashboardIcon,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { useAppNavigation } from "@/context/app-navigation-context"

const navMain = [
  {
    id: "dashboard" as const,
    title: "Dashboard",
    icon: <LayoutDashboardIcon />,
  },
  {
    id: "schemas" as const,
    title: "Schemas",
    icon: <DatabaseIcon />,
  },
  {
    id: "templates" as const,
    title: "Templates",
    icon: <FileStackIcon />,
  },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { panel, wizardView, navigatePanel, goHome, quickCreate } = useAppNavigation()

  const wizardBrowseOnly = wizardView.kind === "browse"

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              className="data-[slot=sidebar-menu-button]:p-1.5!"
              onClick={goHome}
              tooltip="FireForm home"
            >
              <CommandIcon className="size-5!" />
              <span className="text-base font-semibold">FireForm</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <NavMain
          items={navMain}
          activePanel={panel}
          wizardBrowseOnly={wizardBrowseOnly}
          onNavigate={navigatePanel}
          onQuickCreate={quickCreate}
        />
      </SidebarContent>
    </Sidebar>
  )
}
