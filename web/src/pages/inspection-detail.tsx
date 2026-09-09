import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft, Download, FileText } from "lucide-react"

import { InspectionReport } from "@/components/inspection-report"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { api, ApiError } from "@/lib/api"
import type { Inspection } from "@/lib/types"

export function InspectionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [inspection, setInspection] = useState<Inspection | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setInspection(null)
    setError(null)
    api
      .getInspection(id)
      .then(setInspection)
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Could not reach the compliance API",
        ),
      )
  }, [id])

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/queue">
            <ArrowLeft />
            Back to the queue
          </Link>
        </Button>
        {id && inspection && (
          <>
            <Button variant="outline" size="sm" asChild>
              <a href={api.pdfUrl(id)} target="_blank" rel="noreferrer">
                <Download />
                PDF report
              </a>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <a href={api.reportUrl(id)} target="_blank" rel="noreferrer">
                <FileText />
                Markdown
              </a>
            </Button>
          </>
        )}
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load this screening</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : inspection ? (
        <InspectionReport inspection={inspection} />
      ) : (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}
    </div>
  )
}
