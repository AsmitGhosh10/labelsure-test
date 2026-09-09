import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { ClipboardCheck, Lock } from "lucide-react"

import { DecisionBadge } from "@/components/decision-badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
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
import type { Decision, ReviewQueueEntry } from "@/lib/types"

/**
 * The sign-off backlog, least confident first.
 *
 * The ordering is the whole point: an inspector's attention should land on the
 * screenings the system was least sure about, not the newest ones.
 */
export function ReviewQueuePage() {
  const [queue, setQueue] = useState<ReviewQueueEntry[] | null>(null)
  const [error, setError] = useState<{ status: number; message: string } | null>(null)

  useEffect(() => {
    api
      .reviewQueue(50)
      .then((response) => setQueue(response.queue))
      .catch((err) =>
        setError({
          status: err instanceof ApiError ? err.status : 0,
          message:
            err instanceof ApiError ? err.message : "Could not reach the compliance API",
        }),
      )
  }, [])

  if (error) {
    const gated = error.status === 401 || error.status === 403
    return (
      <div className="mx-auto w-full max-w-2xl px-4 py-12">
        <Alert variant={gated ? "default" : "destructive"}>
          {gated ? <Lock /> : null}
          <AlertTitle>{gated ? "Sign in required" : "Could not load the queue"}</AlertTitle>
          <AlertDescription>
            {gated
              ? "The review queue is available to signed-in inspectors. Sign in from the header."
              : error.message}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Review queue</h1>
        <p className="text-muted-foreground">
          Screenings awaiting sign-off, least confident first.
        </p>
      </header>

      {queue === null ? (
        <Skeleton className="h-64 w-full" />
      ) : queue.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ClipboardCheck />
            </EmptyMedia>
            <EmptyTitle>Nothing waiting</EmptyTitle>
            <EmptyDescription>
              Every screening in the repository has been signed off.
            </EmptyDescription>
          </EmptyHeader>
          <Button asChild variant="outline">
            <Link to="/inspect">Inspect a package</Link>
          </Button>
        </Empty>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{queue.length} awaiting sign-off</CardTitle>
            <CardDescription>
              Open a screening to see its evidence and record a decision.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product</TableHead>
                    <TableHead className="w-44">Automated verdict</TableHead>
                    <TableHead className="w-32">Confidence</TableHead>
                    <TableHead className="w-44">Screened</TableHead>
                    <TableHead className="w-24" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {queue.map((entry) => (
                    <TableRow key={entry.inspection_id}>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-medium">
                            {entry.product_name || "Unnamed package"}
                          </span>
                          <span className="text-muted-foreground font-mono text-xs">
                            {entry.inspection_id}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <DecisionBadge decision={entry.decision as Decision | null} />
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {typeof entry.confidence === "number"
                          ? `${Math.round(entry.confidence * 100)}%`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {entry.timestamp ?? "—"}
                      </TableCell>
                      <TableCell>
                        <Button asChild variant="outline" size="sm">
                          <Link to={`/inspections/${entry.inspection_id}`}>Open</Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
