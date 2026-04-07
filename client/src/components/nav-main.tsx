"use client"

import type { ReactNode } from "react"
import { PlusIcon } from "lucide-react"

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import type { AppPanel } from "@/context/app-navigation-context"

export function NavMain({
  items,
  activePanel,
  wizardBrowseOnly,
  onNavigate,
  onQuickCreate,
}: {
  items: {
    id: AppPanel
    title: string
    icon?: ReactNode
  }[]
  activePanel: AppPanel
  wizardBrowseOnly: boolean
  onNavigate: (id: AppPanel) => void
  onQuickCreate: () => void
}) {
  return (
    <SidebarGroup>
      <SidebarGroupContent className="flex flex-col gap-2">
        {/* Quick Create CTA */}
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="New Schema"
              onClick={onQuickCreate}
              className="bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground"
            >
              <PlusIcon />
              <span>New Schema</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>

        {/* Primary nav items */}
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.id}>
              <SidebarMenuButton
                tooltip={item.title}
                isActive={wizardBrowseOnly && activePanel === item.id}
                onClick={() => onNavigate(item.id)}
              >
                {item.icon}
                <span>{item.title}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
