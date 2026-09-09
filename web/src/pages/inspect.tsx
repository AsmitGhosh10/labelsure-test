import { useCallback, useRef, useState } from "react"
import {
  Download,
  FileText,
  ImageUp,
  ScanLine,
  Trash2,
  TriangleAlert,
} from "lucide-react"
import { toast } from "sonner"

import { InspectionReport } from "@/components/inspection-report"
import { Disclaimer } from "@/components/disclaimer"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { api, ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { Inspection } from "@/lib/types"

const MAX_SURFACES = 6

type Surface = { file: File; preview: string }

export function InspectPage() {
  const [surfaces, setSurfaces] = useState<Surface[]>([])
  const [productName, setProductName] = useState("")
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Inspection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const images = Array.from(incoming).filter((f) => f.type.startsWith("image/"))
    if (images.length === 0) {
      toast.error("Only image files can be inspected")
      return
    }
    setSurfaces((current) => {
      const room = MAX_SURFACES - current.length
      if (room <= 0) {
        toast.error(`At most ${MAX_SURFACES} surfaces per package`)
        return current
      }
      if (images.length > room) {
        toast.warning(`Only the first ${room} image(s) were added`)
      }
      return [
        ...current,
        ...images.slice(0, room).map((file) => ({
          file,
          preview: URL.createObjectURL(file),
        })),
      ]
    })
  }, [])

  function removeSurface(index: number) {
    setSurfaces((current) => {
      URL.revokeObjectURL(current[index].preview)
      return current.filter((_, i) => i !== index)
    })
  }

  function reset() {
    surfaces.forEach((s) => URL.revokeObjectURL(s.preview))
    setSurfaces([])
    setResult(null)
    setError(null)
    setProductName("")
  }

  async function run() {
    if (surfaces.length === 0) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const inspection = await api.inspect(
        surfaces.map((s) => s.file),
        productName,
      )
      setResult(inspection)
      toast.success(`Inspection ${inspection.inspection_id} complete`)
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 401
            ? "Sign in to run an inspection."
            : err.message
          : "Could not reach the compliance API. Is the backend running?"
      setError(message)
      toast.error(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Inspect a package</h1>
        <p className="text-muted-foreground">
          Upload one to {MAX_SURFACES} photographs of the same package. More surfaces
          means more declarations found, and fewer findings that fall to manual review.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Package surfaces</CardTitle>
          <CardDescription>
            Front, back, sides, top, bottom — or a single flat label image.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="product-name">Product name (optional)</FieldLabel>
              <Input
                id="product-name"
                placeholder="e.g. Crispy Potato Chips 100 g"
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
              />
              <FieldDescription>
                Used to label the report. The rule engine reads the name off the
                package regardless.
              </FieldDescription>
            </Field>

            <Field>
              <FieldLabel htmlFor="surface-input">Photographs</FieldLabel>
              <div
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragging(false)
                  addFiles(e.dataTransfer.files)
                }}
                className={cn(
                  "border-input flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-10 text-center transition-colors",
                  dragging && "border-primary bg-primary/5",
                )}
              >
                <ImageUp className="text-muted-foreground size-8" />
                <div className="flex flex-col gap-1">
                  <p className="text-sm font-medium">Drop photographs here</p>
                  <p className="text-muted-foreground text-sm">
                    JPEG, PNG, WebP, BMP or TIFF, up to 20 MB each
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => inputRef.current?.click()}
                >
                  Choose files
                </Button>
                <input
                  id="surface-input"
                  ref={inputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  className="sr-only"
                  onChange={(e) => {
                    if (e.target.files) addFiles(e.target.files)
                    e.target.value = ""
                  }}
                />
              </div>
            </Field>
          </FieldGroup>

          {surfaces.length > 0 && (
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {surfaces.map((surface, index) => (
                <figure
                  key={surface.preview}
                  className="group relative overflow-hidden rounded-md border"
                >
                  <img
                    src={surface.preview}
                    alt={surface.file.name}
                    className="aspect-square w-full object-cover"
                  />
                  <Button
                    type="button"
                    variant="destructive"
                    size="icon"
                    aria-label={`Remove ${surface.file.name}`}
                    className="absolute top-1.5 right-1.5 size-7 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                    onClick={() => removeSurface(index)}
                  >
                    <Trash2 />
                  </Button>
                  <figcaption className="text-muted-foreground truncate px-2 py-1.5 text-xs">
                    {surface.file.name}
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
        </CardContent>
        <CardFooter className="flex flex-wrap gap-3">
          <Button onClick={run} disabled={busy || surfaces.length === 0}>
            {busy ? <Spinner data-icon /> : <ScanLine />}
            {busy ? "Screening…" : `Run inspection (${surfaces.length})`}
          </Button>
          <Button variant="ghost" onClick={reset} disabled={busy}>
            Clear
          </Button>
          {result && (
            <>
              <Button variant="outline" asChild>
                <a href={api.pdfUrl(result.inspection_id)} target="_blank" rel="noreferrer">
                  <Download />
                  PDF report
                </a>
              </Button>
              <Button variant="outline" asChild>
                <a href={api.reportUrl(result.inspection_id)} target="_blank" rel="noreferrer">
                  <FileText />
                  Markdown
                </a>
              </Button>
            </>
          )}
        </CardFooter>
      </Card>

      {error && (
        <Alert variant="destructive">
          <TriangleAlert />
          <AlertTitle>Inspection failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {busy && (
        <Card>
          <CardContent className="text-muted-foreground flex items-center gap-3 py-8 text-sm">
            <Spinner />
            Reading {surfaces.length} surface(s). First run loads the OCR models, which
            can take a minute.
          </CardContent>
        </Card>
      )}

      {result ? <InspectionReport inspection={result} /> : <Disclaimer />}
    </div>
  )
}
