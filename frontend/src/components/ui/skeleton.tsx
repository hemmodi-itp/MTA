import { cn } from "cn"

/** Loading placeholder; the shimmer is a transform-animated highlight (see .skeleton in globals.css). */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn("skeleton rounded-md", className)}
      {...props}
    />
  )
}

export { Skeleton }
