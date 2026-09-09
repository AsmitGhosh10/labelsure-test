import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import {
  ArrowRight,
  BookOpenCheck,
  Camera,
  FileSearch,
  Gavel,
  LineChart,
  MessageSquareQuote,
  ScanLine,
  ShieldCheck,
  UserCheck,
} from "lucide-react"

import { Disclaimer, SHORT_DISCLAIMER } from "@/components/disclaimer"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { api } from "@/lib/api"
import type { CorpusStats } from "@/lib/types"

const PIPELINE = [
  {
    Icon: Camera,
    title: "Capture",
    body: "Photograph up to six surfaces of one package. A quality gate rejects blurred, glared or skewed frames before they can produce a false verdict.",
  },
  {
    Icon: FileSearch,
    title: "Read",
    body: "OCR lifts every text line with its confidence and position, then field extraction resolves MRP, net quantity, dates, manufacturer and consumer care.",
  },
  {
    Icon: Gavel,
    title: "Apply the rules",
    body: "A deterministic engine evaluates 31 declarations from the Legal Metrology (Packaged Commodities) Rules, 2011. No model decides compliance.",
  },
  {
    Icon: UserCheck,
    title: "Hand to a human",
    body: "Every verdict carries its confidence, its evidence and its citation, and waits for an inspector to accept, override or escalate it.",
  },
]

const FEATURES = [
  {
    Icon: ShieldCheck,
    title: "Deterministic verdicts",
    body: "Rules are data, not prompts. The same package and the same photographs always produce the same finding, and every finding names the clause it came from.",
  },
  {
    Icon: MessageSquareQuote,
    title: "Grounded answers",
    body: "Ask the regulation corpus a question in plain English. Answers are built from retrieved clauses and cite them; when retrieval is weak the system refuses instead of guessing.",
  },
  {
    Icon: BookOpenCheck,
    title: "Citations, not paraphrase",
    body: "Each retrieved clause carries its document, rule reference, page number and verbatim quote, so a finding can be checked against the Gazette.",
  },
  {
    Icon: LineChart,
    title: "Supervisor view",
    body: "Compliance rate, common violations, override rate and inspector activity across the whole repository, with the citation behind each violation.",
  },
]

export function LandingPage() {
  const [corpus, setCorpus] = useState<CorpusStats | null>(null)

  useEffect(() => {
    api.corpusStats().then(setCorpus).catch(() => setCorpus(null))
  }, [])

  return (
    <div className="flex flex-col">
      <section className="border-b">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-start gap-6 px-4 py-16 md:py-24">
          <Badge variant="outline" className="gap-1.5">
            <ScanLine className="size-3.5" />
            LM(PC)R 2011 · 31 declarations
          </Badge>

          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-balance md:text-6xl">
            Screen packaged-commodity labels against the Legal Metrology rules.
          </h1>

          <p className="text-muted-foreground max-w-2xl text-lg text-pretty">
            Photograph a package. LabelSure reads the declarations, applies the
            packaged-commodities rules clause by clause, and hands an inspector a
            verdict with its evidence, its confidence and the regulation it cites.
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <Button asChild size="lg">
              <Link to="/inspect">
                Inspect a package
                <ArrowRight />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link to="/ask">Ask the rules a question</Link>
            </Button>
          </div>

          <p className="text-muted-foreground text-sm">{SHORT_DISCLAIMER}</p>
        </div>
      </section>

      <section className="border-b">
        <div className="mx-auto grid w-full max-w-6xl grid-cols-2 gap-px px-4 py-10 md:grid-cols-4">
          <Stat label="Rules evaluated" value="31" />
          <Stat label="Regulation chunks indexed" value={corpus ? String(corpus.chunks) : "—"} />
          <Stat
            label="Source documents"
            value={corpus ? String(corpus.documents.length) : "—"}
          />
          <Stat label="Surfaces per package" value="up to 6" />
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 py-16">
        <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">
          How an inspection runs
        </h2>
        <p className="text-muted-foreground mt-2 max-w-2xl">
          Four stages, each of which can stop and say it does not know. A stage that
          cannot do its job reports that rather than passing a guess downstream.
        </p>

        <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {PIPELINE.map((step, index) => (
            <Card key={step.title} className="h-full">
              <CardHeader>
                <div className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-md">
                  <step.Icon className="size-4.5" />
                </div>
                <CardTitle className="mt-3 flex items-center gap-2">
                  <span className="text-muted-foreground text-xs tabular-nums">
                    0{index + 1}
                  </span>
                  {step.title}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground text-sm">
                {step.body}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator />

      <section className="mx-auto w-full max-w-6xl px-4 py-16">
        <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">
          What it will not do
        </h2>
        <p className="text-muted-foreground mt-2 max-w-2xl">
          The constraints matter more than the features. This is a screening aid for a
          statutory process, so its limits are part of the product.
        </p>

        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {FEATURES.map((feature) => (
            <Card key={feature.title}>
              <CardHeader>
                <div className="flex items-center gap-3">
                  <feature.Icon className="text-primary size-5" />
                  <CardTitle>{feature.title}</CardTitle>
                </div>
                <CardDescription className="pt-1">{feature.body}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 pb-16">
        <Card>
          <CardHeader>
            <CardTitle>Start with one package</CardTitle>
            <CardDescription>
              Upload the front and back of a wrapper. The result is a per-rule table,
              annotated photographs and a signed-off report you can export as PDF.
            </CardDescription>
          </CardHeader>
          <CardFooter className="flex flex-wrap gap-3">
            <Button asChild>
              <Link to="/inspect">
                Open the inspector
                <ArrowRight />
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link to="/regulations">Browse the regulation corpus</Link>
            </Button>
          </CardFooter>
        </Card>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 pb-16">
        <Disclaimer />
      </section>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 px-2 py-4">
      <span className="text-3xl font-semibold tabular-nums">{value}</span>
      <span className="text-muted-foreground text-sm">{label}</span>
    </div>
  )
}
