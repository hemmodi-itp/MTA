"use client";

import { useState } from "react";
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatusPill } from "@/components/shared/status-pill";
import { EmptyState } from "@/components/shared/empty-state";
import { FlaskConical, Search } from "lucide-react";
import type { TestCase, TestStatus } from "@/lib/types";

/** Status filter options: current statuses first, then the legacy ones older runs still carry. */
export const TEST_STATUS_OPTIONS: { value: TestStatus; label: string }[] = [
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
  { value: "inconclusive", label: "Inconclusive" },
  { value: "not_executed", label: "Not executed" },
  { value: "pending", label: "Pending" },
  { value: "healed", label: "Healed" },
  { value: "skipped", label: "Skipped" },
];

/** Statuses whose errorSummary explains the outcome and is worth showing inline. */
const SHOW_REASON: TestStatus[] = ["failed", "inconclusive", "not_executed"];

const columns: ColumnDef<TestCase>[] = [
  {
    accessorKey: "scenarioTitle",
    header: "Scenario",
    cell: ({ row }) => <span className="font-medium">{row.original.scenarioTitle}</span>,
  },
  { accessorKey: "module", header: "Module" },
  { accessorKey: "variantType", header: "Variant" },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusPill status={row.original.status} />,
  },
  {
    id: "reason",
    header: "Reason",
    cell: ({ row }) =>
      SHOW_REASON.includes(row.original.status) && row.original.errorSummary ? (
        <p className="line-clamp-2 max-w-md text-xs text-muted-foreground" title={row.original.errorSummary}>
          {row.original.errorSummary}
        </p>
      ) : (
        <span className="text-xs text-muted-foreground">—</span>
      ),
  },
  {
    accessorKey: "durationMs",
    header: () => <div className="text-right">Duration</div>,
    cell: ({ row }) => (
      <div className="text-right font-mono text-xs tabular-nums text-muted-foreground">
        {row.original.durationMs ? `${(row.original.durationMs / 1000).toFixed(1)}s` : "—"}
      </div>
    ),
  },
];

export function TestResultTable({ data, initialStatus = "all" }: { data: TestCase[]; initialStatus?: TestStatus | "all" }) {
  const [globalFilter, setGlobalFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<TestStatus | "all">(initialStatus);

  const filtered = data.filter(
    (t) =>
      (statusFilter === "all" || t.status === statusFilter) &&
      t.scenarioTitle.toLowerCase().includes(globalFilter.toLowerCase())
  );

  const table = useReactTable({
    data: filtered,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search scenarios…"
            className="pl-8"
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as TestStatus | "all")}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {TEST_STATUS_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={FlaskConical}
          title="No test cases match"
          description="Try clearing the search or status filter."
        />
      ) : (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id}>
                  {hg.headers.map((h) => (
                    <TableHead key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
