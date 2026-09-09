import { useState } from "react"
import { BookOpen, CircleAlert, ImageOff, ServerCrash } from "lucide-react"

import { DecisionBadge, RuleStatusBadge, SeverityBadge } from "@/components/decision-badge"
import { Disclaimer } from "@/components/disclaimer"
import { SignOffCard } from "@/components/sign-off-card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { Inspection, RuleResult, SurfaceQuality } from "@/lib/types"

const FIELD_LABELS: Record<string, string> = {
  mrp: "Retail sale price",
  net_quantity: "Net quantity",
  manufacturer: "Manufacturer / packer",
  brand: "Brand",
  product_name: "Product name",
  manufacturing_date: "Manufacturing date",
  packing_date: "Packing date",
  expiry_date: "Expiry / best before",
  consumer_care: "Consumer care",
  country_of_origin: "Country of origin",
  best_before: "Best before",
  batch_number: "Batch number",
  importer: "Importer",
  packer: "Packer",
}

/** A system fault reads differently from a bad photograph, so say which it is. */
function isSystemFault(inspection: Inspection) {
  return inspection.images.some((image) => image.ocr_error)
}

export function InspectionReport({ inspection }: { inspection: Inspection }) {
  const violations = inspection.rule_results.filter((r) => r.status === "FAIL")
  const review = inspection.rule_results.filter((r) => r.status === "MANUAL_REVIEW")

  return (
    <div className="flex flex-col gap-6">
      <VerdictCard inspection={inspection} />

      {isSystemFault(inspection) && (
        <Alert variant="destructive">
          <ServerCrash />
          <AlertTitle>The text reader failed on at least one surface</AlertTitle>
          <AlertDescription>
            This is a fault in the system, not a problem with the photograph.
            Recapturing the package will not help. The affected surfaces are listed
            under Surfaces.
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="rules">
        <TabsList>
          <TabsTrigger value="rules">
            Rules
            <Badge variant="secondary">{inspection.rule_results.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="fields">Declarations</TabsTrigger>
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
          <TabsTrigger value="surfaces">Surfaces</TabsTrigger>
          <TabsTrigger value="signoff">Sign-off</TabsTrigger>
        </TabsList>

        <TabsContent value="rules" className="flex flex-col gap-4">
          {violations.length > 0 && (
            <RuleTable
              title="Violations"
              description="Declarations the rule engine found missing or non-conforming."
              rules={violations}
            />
          )}
          {review.length > 0 && (
            <RuleTable
              title="Needs manual review"
              description="Could not be resolved from the captured imagery alone."
              rules={review}
            />
          )}
          <RuleTable
            title="All rules evaluated"
            description="Every clause the engine considered, including those that did not apply."
            rules={inspection.rule_results}
          />
        </TabsContent>

        <TabsContent value="fields">
          <DeclarationsCard inspection={inspection} />
        </TabsContent>

        <TabsContent value="evidence">
          <EvidenceCard inspection={inspection} />
        </TabsContent>

        <TabsContent value="surfaces">
          <SurfacesCard inspection={inspection} />
        </TabsContent>

        <TabsContent value="signoff">
          <SignOffCard inspection={inspection} />
        </TabsContent>
      </Tabs>

      <Disclaimer text={inspection.disclaimer?.text} />
    </div>
  )
}

function VerdictCard({ inspection }: { inspection: Inspection }) {
  const confidence = inspection.confidence
  const score = inspection.compliance_score

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-3">
          <CardTitle className="text-2xl">
            {inspection.product_name || "Unnamed package"}
          </CardTitle>
          <DecisionBadge decision={inspection.decision} />
          {inspection.product_category && (
            <Badge variant="secondary">
              {inspection.product_category.label}
              {inspection.product_category.confident ? "" : " (uncertain)"}
            </Badge>
          )}
        </div>
        <CardDescription>
          {inspection.inspection_id} · {inspection.timestamp} ·{" "}
          {inspection.coverage.surfaces_usable} of {inspection.coverage.surfaces_total}{" "}
          surface(s) usable
          {inspection.processing_time_sec !== null &&
            ` · ${inspection.processing_time_sec}s`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {inspection.decision_downgraded_from && (
          <Alert>
            <CircleAlert />
            <AlertTitle>
              Downgraded from {inspection.decision_downgraded_from}
            </AlertTitle>
            <AlertDescription>
              The engine reduced its own verdict because the evidence did not support
              the stronger one.
            </AlertDescription>
          </Alert>
        )}

        {inspection.decision_reasons && inspection.decision_reasons.length > 0 && (
          <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm">
            {inspection.decision_reasons.map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
          </ul>
        )}

        <div className="grid gap-6 sm:grid-cols-2">
          <Metric
            label="Decision confidence"
            percent={confidence ? confidence.overall * 100 : null}
            hint="Fused from image quality, text-reading confidence, field extraction and rule coverage."
          />
          <Metric
            label={`Compliance score${score?.grade ? ` — grade ${score.grade}` : ""}`}
            percent={score?.score ?? null}
            hint={
              score
                ? `${score.scored_rules} rule(s) scored, ${score.not_assessable} could not be assessed from photographs and are excluded.`
                : "Not scored."
            }
          />
        </div>

        {confidence && Object.keys(confidence.components).length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-medium">What the confidence is made of</h3>
            <dl className="text-muted-foreground grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
              {Object.entries(confidence.components).map(([name, value]) => (
                <div key={name} className="flex justify-between gap-2">
                  <dt className="capitalize">{name.replace(/_/g, " ")}</dt>
                  <dd className="tabular-nums">{Math.round(value * 100)}%</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        {score && score.categories.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-medium">By category</h3>
            <dl className="text-muted-foreground grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
              {score.categories.map((category) => (
                <div key={category.bucket} className="flex justify-between gap-2">
                  <dt>{category.label}</dt>
                  <dd className="tabular-nums">
                    {category.score === null
                      ? "not assessable"
                      : `${Math.round(category.score)}% of ${category.rules_scored}`}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="text-muted-foreground mt-2 text-xs">{score.basis}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function Metric({
  label,
  percent,
  hint,
}: {
  label: string
  /** Already on a 0-100 scale. `null` means not assessed. */
  percent: number | null
  hint: string
}) {
  // "Not assessed" and "assessed as zero" are different findings, so a missing
  // value must never render as 0%.
  const assessed = typeof percent === "number"
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-2xl font-semibold tabular-nums">
          {assessed ? `${Math.round(percent)}%` : "not assessed"}
        </span>
      </div>
      <Progress value={assessed ? percent : 0} />
      <p className="text-muted-foreground text-xs">{hint}</p>
    </div>
  )
}

function RuleTable({
  title,
  description,
  rules,
}: {
  title: string
  description: string
  rules: RuleResult[]
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-28">Rule</TableHead>
                <TableHead>Requirement</TableHead>
                <TableHead className="w-40">Status</TableHead>
                <TableHead className="w-28">Severity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((rule, index) => (
                <TableRow key={`${rule.rule_id}-${index}`}>
                  <TableCell className="font-mono text-xs">
                    {rule.source?.rule ?? rule.rule_id ?? "—"}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      <span className="font-medium">{rule.requirement || "—"}</span>
                      {rule.reason && (
                        <span className="text-muted-foreground text-sm">
                          {rule.reason}
                        </span>
                      )}
                      {rule.source?.evidence_text && (
                        <span className="text-muted-foreground border-l-2 pl-2 text-xs italic">
                          “{rule.source.evidence_text}”
                          {rule.source.page ? ` — page ${rule.source.page}` : ""}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <RuleStatusBadge status={rule.status} />
                  </TableCell>
                  <TableCell>
                    <SeverityBadge severity={rule.severity} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function DeclarationsCard({ inspection }: { inspection: Inspection }) {
  const entries = Object.entries(inspection.extracted_fields)
  if (entries.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ImageOff />
          </EmptyMedia>
          <EmptyTitle>No declarations extracted</EmptyTitle>
          <EmptyDescription>
            Nothing on the captured surfaces could be resolved into a declaration.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Extracted declarations</CardTitle>
        <CardDescription>
          What was read off the package, with the raw text it came from.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-52">Declaration</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Read from</TableHead>
                <TableHead className="w-32">Confidence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map(([name, field]) => (
                <TableRow key={name}>
                  <TableCell className="font-medium">
                    {FIELD_LABELS[name] ?? name}
                  </TableCell>
                  <TableCell>{field.value ?? "—"}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {field.ocr_text ?? "—"}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {/* A declaration that was never found has no confidence to
                        report; 0% would read as a measurement of it. */}
                    {field.value === null || field.value === "" ? (
                      <span className="text-muted-foreground">not found</span>
                    ) : (
                      <>
                        {typeof field.extraction_confidence === "number"
                          ? `${Math.round(field.extraction_confidence * 100)}%`
                          : "—"}
                        {field.confidence_level ? (
                          <span className="text-muted-foreground ml-1 text-xs">
                            {field.confidence_level}
                          </span>
                        ) : null}
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function EvidenceCard({ inspection }: { inspection: Inspection }) {
  const [broken, setBroken] = useState<Record<number, boolean>>({})

  if (inspection.annotated_images.length === 0 && inspection.regulation_citations.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ImageOff />
          </EmptyMedia>
          <EmptyTitle>No visual evidence</EmptyTitle>
          <EmptyDescription>
            No declaration could be located on a surface precisely enough to highlight.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {inspection.annotated_images.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Where each declaration was found</CardTitle>
            <CardDescription>
              The captured surfaces with the located declarations outlined.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            {inspection.annotated_images.map((image, index) =>
              broken[index] ? null : (
                <figure key={image.path} className="flex flex-col gap-2">
                  <img
                    src={api.annotatedUrl(inspection.inspection_id, index)}
                    alt={`Annotated ${image.name}`}
                    className="w-full rounded-md border"
                    onError={() => setBroken((b) => ({ ...b, [index]: true }))}
                  />
                  <figcaption className="text-muted-foreground text-sm">
                    {image.name}
                  </figcaption>
                </figure>
              ),
            )}
          </CardContent>
        </Card>
      )}

      {inspection.regulation_citations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Regulation cited</CardTitle>
            <CardDescription>
              The clauses behind this verdict, quoted verbatim.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Accordion type="multiple">
              {inspection.regulation_citations.map((citation, index) => (
                <AccordionItem key={index} value={`citation-${index}`}>
                  <AccordionTrigger>
                    <span className="flex items-center gap-2">
                      <BookOpen className="size-4" />
                      {citation.rule ?? "Clause"} — {citation.title ?? citation.document}
                    </span>
                  </AccordionTrigger>
                  <AccordionContent className="flex flex-col gap-2">
                    <blockquote className="border-l-2 pl-3 text-sm italic">
                      {citation.quote}
                    </blockquote>
                    <p className="text-muted-foreground text-xs">
                      {citation.document}
                      {citation.page ? ` · page ${citation.page}` : ""}
                      {citation.effective_date ? ` · ${citation.effective_date}` : ""}
                    </p>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function SurfacesCard({ inspection }: { inspection: Inspection }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Captured surfaces</CardTitle>
        <CardDescription>
          Whether each photograph was usable, and what the text reader made of it.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {inspection.images.map((image) => (
          <div key={image.index} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{image.name}</span>
              <Badge variant={image.usable ? "secondary" : "destructive"}>
                {image.usable ? "usable" : "not usable"}
              </Badge>
              <span className="text-muted-foreground text-sm">
                {image.num_lines} line(s) read
                {typeof image.ocr_avg_confidence === "number" &&
                  ` · ${Math.round(image.ocr_avg_confidence * 100)}% average confidence`}
              </span>
            </div>
            {image.ocr_error && (
              <Alert variant="destructive">
                <ServerCrash />
                <AlertTitle>The text reader could not run on this surface</AlertTitle>
                <AlertDescription>{image.ocr_error}</AlertDescription>
              </Alert>
            )}
            {image.quality?.checks && <QualityChecks quality={image.quality} />}
            <Separator />
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

/**
 * The quality gate's own numbers for one surface.
 *
 * Failing checks come first and are named with their threshold, because "too
 * blurred, 42 against a threshold of 100" tells an inspector how to recapture
 * the package; "unusable" does not.
 */
function QualityChecks({ quality }: { quality: SurfaceQuality }) {
  const checks = Object.entries(quality.checks ?? {})
  if (checks.length === 0) return null
  const ordered = [...checks].sort(
    (a, b) => Number(a[1].pass) - Number(b[1].pass),
  )

  return (
    <dl className="text-muted-foreground grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
      {ordered.map(([name, check]) => (
        <div key={name} className="flex justify-between gap-2">
          <dt className={cn("capitalize", !check.pass && "text-destructive font-medium")}>
            {name}
          </dt>
          <dd className="tabular-nums">
            {check.value}
            {check.pass ? "" : ` (limit ${check.threshold ?? `${check.min}–${check.max}`})`}
          </dd>
        </div>
      ))}
    </dl>
  )
}
