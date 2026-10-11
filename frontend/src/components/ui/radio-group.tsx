"use client"

import * as React from "react"
import { CheckIcon } from "lucide-react"
import { RadioGroup as RadioGroupPrimitive } from "radix-ui"
import { cn } from "cn"

function RadioGroup({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Root>) {
  return (
    <RadioGroupPrimitive.Root
      data-slot="radio-group"
      className={cn("grid gap-3", className)}
      {...props}
    />
  )
}

function RadioGroupItem({
  className,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Item>) {
  return (
    <RadioGroupPrimitive.Item
      data-slot="radio-group-item"
      className={cn(
        "relative flex aspect-square size-4 shrink-0 items-center justify-center rounded-full border border-input outline-none transition-colors duration-(--dur-fast) focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 data-checked:border-primary-solid data-checked:bg-primary-solid dark:bg-input/30",
        className
      )}
      {...props}
    >
      <RadioGroupPrimitive.Indicator
        data-slot="radio-group-indicator"
        className="size-1.5 rounded-full bg-primary-foreground data-checked:animate-in data-checked:zoom-in-50 data-checked:duration-(--dur-micro) data-checked:ease-enter"
      />
    </RadioGroupPrimitive.Item>
  )
}

/**
 * A whole card as one radio option (title, icon, description). Arrow keys move between cards; the selected card gets
 * the primary border and a check that pops in.
 */
function RadioCard({
  className,
  children,
  ...props
}: React.ComponentProps<typeof RadioGroupPrimitive.Item>) {
  return (
    <RadioGroupPrimitive.Item
      data-slot="radio-card"
      className={cn(
        "group/radio-card relative flex flex-col gap-2 rounded-xl border border-border bg-background/40 p-4 text-left outline-none transition-colors duration-(--dur-micro) ease-enter hover:border-foreground/20 hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 data-checked:border-primary data-checked:bg-primary/5 data-checked:ring-1 data-checked:ring-primary",
        className
      )}
      {...props}
    >
      <span
        aria-hidden
        className="absolute top-3 right-3 flex size-5 items-center justify-center rounded-full border border-input bg-background transition-colors duration-(--dur-micro) group-data-[state=checked]/radio-card:border-primary-solid group-data-[state=checked]/radio-card:bg-primary-solid"
      >
        <RadioGroupPrimitive.Indicator className="text-primary-foreground data-checked:animate-in data-checked:zoom-in-50 data-checked:fade-in-0 data-checked:duration-(--dur-micro) data-checked:ease-enter">
          <CheckIcon className="size-3" strokeWidth={3} />
        </RadioGroupPrimitive.Indicator>
      </span>
      {children}
    </RadioGroupPrimitive.Item>
  )
}

export { RadioGroup, RadioGroupItem, RadioCard }
