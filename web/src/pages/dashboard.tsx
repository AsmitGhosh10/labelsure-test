import { useEffect, useState } from "react"
import { Lock, TrendingUp } from "lucide-react"

import { Disclaimer } from "@/components/disclaimer"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, ApiError } from "@/lib/api"
import type { Stats, ViolationRow } from "@/lib/types"

export function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [violations, setViolations] = useState<ViolationRow[]>([])
  const [error, setError] = useState<{ status: number; message: string } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.stats(), api.violations(15)])
      .then(([s, v]) => {
        setStats(s)
        setViolations(v.violations)
      })
      .catch((err) =>
        setError({
          status: err instanceof ApiError ? err.status : 0,
          message:
            err instanceof ApiError ? err.message : "Could not reach the compliance API",
        }),
      )
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="mx-auto grid w-full max-w-6xl gap-4 px-4 py-8 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
      </div>
    )
  }

  if (error) {
    const gated = error.status === 401 || error.status === 403
    return (
      <div className="mx-auto w-full max-w-2xl px-4 py-12">
        <Alert variant={gated ? "default" : "destructive"}>
          {gated ? <Lock /> : null}
          <AlertTitle>
            {gated ? "Supervisor access required" : "Could not load the dashboard"}
          </AlertTitle>
          <AlertDescription>
            {gated
              ? "Repository statistics are restricted to supervisor and administrator roles. Sign in from the header."
              : error.message}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  if (!stats) return null

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Across {stats.total_inspections} screening(s) in this repository.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Compliant" value={stats.compliant} />
        <Metric label="Non-compliant" value={stats.non_compliant} />
        <Metric label="Manual review" value={stats.manual_review} />
        {/* The backend reports rates and scores already on a 0-100 scale, and
            confidence as a 0-1 fraction. Mixing them up multiplies by 100. */}
        <Metric label="Compliance rate" value={stats.compliance_rate} format="points" />
        <Metric
          label="Average confidence"
          value={stats.average_confidence}
          format="fraction"
        />
        <Metric
          label="Average compliance score"
          value={stats.average_compliance_score}
          format="points"
        />
        <Metric label="Human reviewed" value={stats.human_reviewed} />
        <Metric label="Override rate" value={stats.override_rate} format="points" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="size-5" />
            Most frequent violations
          </CardTitle>
          <CardDescription>
            The rules breached most often, with the clause each one cites.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {violations.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No violations recorded yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-28">Rule</TableHead>
                    <TableHead>Requirement</TableHead>
                    <TableHead className="w-40">Document</TableHead>
                    <TableHead className="w-20 text-right">Count</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {violations.map((row) => (
                    <TableRow key={row.rule_id}>
                      <TableCell className="font-mono text-xs">
                        {row.rule ?? row.rule_id}
                      </TableCell>
                      <TableCell>{row.title ?? "—"}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {row.document ?? "—"}
                        {row.page ? ` · p.${row.page}` : ""}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {row.count}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {stats.daily_trend?.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Screenings per day</CardTitle>
          </CardHeader>
          <CardContent>
            <BarStrip data={stats.daily_trend} />
          </CardContent>
        </Card>
      )}

      <Disclaimer text={stats.disclaimer} />
    </div>
  )
}

function Metric({
  label,
  value,
  format,
}: {
  label: string
  value: number | null
  /** "fraction" is 0-1, "points" is already 0-100, omitted is a plain count. */
  format?: "fraction" | "points"
}) {
  // Distinguish "nothing to measure yet" from a measured zero.
  const display =
    value === null || value === undefined
      ? "—"
      : format === "fraction"
        ? `${Math.round(value * 100)}%`
        : format === "points"
          ? `${Math.round(value)}%`
          : String(value)
  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-3xl tabular-nums">{display}</CardTitle>
      </CardHeader>
    </Card>
  )
}

/**
 * A minimal bar strip.
 *
 * A charting library would be a dependency for one chart of one series, so this
 * is plain divs. Swap in a real chart when a second series appears.
 */
function BarStrip({ data }: { data: { date: string; count: number }[] }) {
  const max = Math.max(...data.map((d) => d.count), 1)
  return (
    <div className="flex h-40 items-end gap-1.5 overflow-x-auto">
      {data.map((day) => (
        <div key={day.date} className="flex min-w-8 flex-1 flex-col items-center gap-1.5">
          <div
            className="bg-primary/80 w-full rounded-t-sm"
            style={{ height: `${(day.count / max) * 100}%` }}
            title={`${day.date}: ${day.count}`}
          />
          <span className="text-muted-foreground text-[10px] whitespace-nowrap">
            {day.date.slice(5)}
          </span>
        </div>
      ))}
    </div>
  )
}
