import { PageTransition } from "@/components/motion/page-transition";

/** Route transition for every page inside the app shell: fade + 8 px rise, replayed whenever the path changes. */
export default function AppTemplate({ children }: { children: React.ReactNode }) {
  return <PageTransition className="space-y-6">{children}</PageTransition>;
}
