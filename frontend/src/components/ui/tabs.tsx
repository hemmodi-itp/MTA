"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Tabs as TabsPrimitive } from "radix-ui"
import { Indicator, IndicatorGroup } from "@/components/motion/sliding-indicator"

// The active value and list variant, so the active trigger can host the sliding indicator.
const TabsValueContext = React.createContext<string | undefined>(undefined)
const TabsVariantContext = React.createContext<"default" | "line">("default")

function Tabs({
  className,
  orientation = "horizontal",
  value,
  defaultValue,
  onValueChange,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  const [uncontrolled, setUncontrolled] = React.useState(defaultValue)
  return (
    <TabsValueContext.Provider value={value ?? uncontrolled}>
      <TabsPrimitive.Root
        data-slot="tabs"
        data-orientation={orientation}
        orientation={orientation}
        value={value}
        defaultValue={defaultValue}
        onValueChange={(next) => {
          setUncontrolled(next)
          onValueChange?.(next)
        }}
        className={cn(
          "group/tabs flex gap-2 data-horizontal:flex-col",
          className
        )}
        {...props}
      />
    </TabsValueContext.Provider>
  )
}

const tabsListVariants = cva(
  "group/tabs-list relative inline-flex w-fit items-center justify-center rounded-lg p-[3px] text-muted-foreground group-data-horizontal/tabs:h-9 group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col data-[variant=line]:rounded-none",
  {
    variants: {
      variant: {
        default: "bg-muted",
        line: "gap-1 bg-transparent",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function TabsList({
  className,
  variant = "default",
  children,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List> &
  VariantProps<typeof tabsListVariants>) {
  const active = React.useContext(TabsValueContext)
  return (
    <TabsVariantContext.Provider value={variant ?? "default"}>
      <TabsPrimitive.List
        data-slot="tabs-list"
        data-variant={variant}
        className={cn(tabsListVariants({ variant }), className)}
        {...props}
      >
        <IndicatorGroup activeKey={active}>{children}</IndicatorGroup>
      </TabsPrimitive.List>
    </TabsVariantContext.Provider>
  )
}

function TabsTrigger({
  className,
  value,
  children,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  const active = React.useContext(TabsValueContext) === value
  const variant = React.useContext(TabsVariantContext)
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      value={value}
      className={cn(
        "relative inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2.5 py-0.5 text-sm font-medium whitespace-nowrap text-muted-foreground transition-colors duration-(--dur-micro) group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 has-data-[icon=inline-end]:pr-1 has-data-[icon=inline-start]:pl-1 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        "data-active:text-foreground",
        className
      )}
      {...props}
    >
      {active && (
        <Indicator
          className={
            variant === "line"
              ? "top-auto -bottom-[3px] h-0.5 rounded-full bg-primary"
              : "rounded-md bg-background shadow-control ring-1 ring-border dark:bg-input/50"
          }
        />
      )}
      <span className="relative inline-flex items-center gap-1.5">{children}</span>
    </TabsPrimitive.Trigger>
  )
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn(
        "flex-1 rounded-xl text-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring data-[state=active]:animate-in data-[state=active]:fade-in-0 data-[state=active]:duration-(--dur-panel) data-[state=active]:ease-enter",
        className
      )}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants }
