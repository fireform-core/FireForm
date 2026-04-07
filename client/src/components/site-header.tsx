import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { useAppNavigation } from "@/context/app-navigation-context"
import { PlusIcon } from "lucide-react"

export function SiteHeader() {
  const { headerTitle, quickCreate } = useAppNavigation()

  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full min-w-0 items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1 shrink-0" />
        <Separator orientation="vertical" className="mx-2 data-[orientation=vertical]:h-4" />
        <h1 className="text-base font-medium truncate">{headerTitle}</h1>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <Button
            size="sm"
            type="button"
            onClick={quickCreate}
            className="hidden sm:flex gap-1.5"
          >
            <PlusIcon className="size-4" />
            New Schema
          </Button>
        </div>
      </div>
    </header>
  )
}
