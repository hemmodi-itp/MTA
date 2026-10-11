"use client"

import * as React from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ThemeProvider } from "next-themes"
import { MotionProvider } from "@/components/motion/motion-provider"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            refetchOnWindowFocus: false,
          },
        },
      })
  )

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        {/* LazyMotion (small feature bundle) + MotionConfig: every animation honours the OS "reduce motion" setting */}
        <MotionProvider>
          <TooltipProvider delayDuration={200}>
            {children}
            <Toaster richColors position="top-right" />
          </TooltipProvider>
        </MotionProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
