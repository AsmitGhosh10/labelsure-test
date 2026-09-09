import { useEffect, useState } from "react"
import { BookOpen, Search } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group"
import { Spinner } from "@/components/ui/spinner"
import { api, ApiError } from "@/lib/api"
import type { CorpusStats, RegulationHit } from "@/lib/types"

export function RegulationsPage() {
  const [stats, setStats] = useState<CorpusStats | null>(null)
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<RegulationHit[] | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.corpusStats().then(setStats).catch(() => setStats(null))
  }, [])

  async function search(event?: React.FormEvent) {
    event?.preventDefault()
    if (!query.trim()) return
    setBusy(true)
    try {
      const response = await api.searchRegulations(query, 10)
      setResults(response.results)
      setNote(response.note)
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Could not reach the compliance API",
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Regulation corpus</h1>
        <p className="text-muted-foreground">
          Keyword and lexical-vector search over the indexed clauses. Results are the
          statutory text itself, never a paraphrase.
        </p>
        {stats && (
          <div className="flex flex-wrap gap-2 pt-1">
            <Badge variant="secondary">{stats.chunks} clauses</Badge>
            <Badge variant="outline">{stats.documents.length} documents</Badge>
            <Badge variant="outline">
              {stats.with_page_numbers} with page references
            </Badge>
          </div>
        )}
      </header>

      <form onSubmit={search}>
        <InputGroup>
          <InputGroupAddon>
            <Search />
          </InputGroupAddon>
          <InputGroupInput
            placeholder="net quantity, retail sale price, country of origin…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <InputGroupAddon align="inline-end">
            <InputGroupButton type="submit" disabled={busy || !query.trim()}>
              {busy ? <Spinner data-icon /> : null}
              Search
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
      </form>

      {stats && stats.documents.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Indexed documents</CardTitle>
            <CardDescription>
              Everything a citation in this system can point at.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2 text-sm">
              {stats.documents.map((document) => (
                <li key={document} className="flex items-start gap-2">
                  <BookOpen className="text-muted-foreground mt-0.5 size-4 shrink-0" />
                  {document}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {results !== null && results.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Search />
            </EmptyMedia>
            <EmptyTitle>Nothing retrieved</EmptyTitle>
            <EmptyDescription>
              {note ?? "No clause matched. Manual verification is required."}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {results?.map((hit) => (
        <Card key={hit.chunk_id}>
          <CardHeader>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="font-mono text-base">{hit.rule_reference}</CardTitle>
              <Badge variant="secondary" className="tabular-nums">
                {hit.score.toFixed(2)}
              </Badge>
              <Badge variant="outline">{hit.category}</Badge>
            </div>
            <CardDescription>{hit.title}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <blockquote className="border-l-2 pl-3 text-sm leading-relaxed">
              {hit.text}
            </blockquote>
            <p className="text-muted-foreground text-xs">
              {hit.citation.document}
              {hit.citation.page ? ` · page ${hit.citation.page}` : ""}
              {hit.citation.effective_date ? ` · ${hit.citation.effective_date}` : ""}
              {hit.citation.verified ? " · verified" : " · pending verification"}
            </p>
            <div className="text-muted-foreground flex gap-4 text-xs tabular-nums">
              <span>keyword {hit.keyword_score.toFixed(3)}</span>
              <span>vector {hit.vector_score.toFixed(3)}</span>
            </div>
            {hit.citation.url && (
              <Button variant="link" size="sm" className="w-fit px-0" asChild>
                <a href={hit.citation.url} target="_blank" rel="noreferrer">
                  Open the source document
                </a>
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
