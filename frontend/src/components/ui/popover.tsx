"use client"

import * as React from "react"
import { Popover as PopoverPrimitive } from "radix-ui"
import { cn } from "@/lib/utils"

function Popover(props: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  return <PopoverPrimitive.Root data-slot="popover" {...props} />
}

function PopoverTrigger(props: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} />
}

function PopoverContent({
  className,
  align = "end",
  sideOffset = 8,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "z-(--z-popover) w-80 rounded-2xl border border-border bg-popover/95 p-0 text-popover-foreground shadow-popover backdrop-blur-xl outline-none origin-(--radix-popover-content-transform-origin) data-[state=open]:duration-(--dur-micro) data-[state=open]:ease-enter data-[state=closed]:duration-(--dur-exit) data-[state=closed]:ease-exit",
          "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
          "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2",
          className
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  )
}

export { Popover, PopoverTrigger, PopoverContent }
