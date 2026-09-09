import { useCallback, useEffect, useState } from "react"
import { BookOpen, ExternalLink, Search, X } from "lucide-react"
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
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { api, ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { CorpusDocument, CorpusStats, RegulationHit } from "@/lib/types"

export function RegulationsPage() {
  const [stats, setStats] = useState<CorpusStats | null>(null)
  const [documents, setDocuments] = useState<CorpusDocument[] | null>(null)
  const [query, setQuery] = useState("")
  const [scope, setScope] = useState<string | null>(null)
  const [results, setResults] = useState<RegulationHit[] | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [browsing, setBrowsing] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.corpusStats().then(setStats).catch(() => setStats(null))
    api
      .corpusDocuments()
      .then((r) => setDocuments(r.documents))
      .catch(() => setDocuments([]))
  }, [])

  const fail = useCallback((error: unknown) => {
    toast.error(
      error instanceof ApiError ? error.message : "Could not reach the compliance API",
    )
  }, [])

  async function search(event?: React.FormEvent, withScope = scope) {
    event?.preventDefault()
    if (!query.trim()) return
    setBusy(true)
    try {
      const response = await api.searchRegulations(query, 10, withScope ?? undefined)
      setResults(response.results)
      setNote(response.note)
      setBrowsing(false)
    } catch (error) {
      fail(error)
    } finally {
      setBusy(false)
    }
  }

  /** Clicking a document opens it: every clause, in source order. */
  async function openDocument(document: string) {
    setScope(document)
    setBusy(true)
    try {
      if (query.trim()) {
        await search(undefined, document)
        return
      }
      const response = await api.browseDocument(document)
      setResults(response.results)
      setNote(response.note)
      setBrowsing(true)
    } catch (error) {
      fail(error)
    } finally {
      setBusy(false)
    }
  }

  function clearScope() {
    setScope(null)
    setResults(null)
    setNote(null)
    setBrowsing(false)
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Regulation corpus</h1>
        <p className="text-muted-foreground">
          Keyword and lexical-vector search over the indexed clauses, or open a
          document to read it through. Results are the statutory text itself, never
          a paraphrase.
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
              {busy && !browsing ? <Spinner data-icon /> : null}
              Search
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
      </form>

      {scope && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">
            {browsing ? "Reading" : "Searching within"}
          </span>
          <Badge variant="secondary" className="gap-1.5">
            {scope}
            <button
              type="button"
              onClick={clearScope}
              aria-label="Clear the document filter"
              className="hover:text-foreground"
            >
              <X className="size-3" />
            </button>
          </Badge>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Indexed documents</CardTitle>
          <CardDescription>
            Everything a citation in this system can point at. Open one to read its
            clauses.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {documents === null ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-11 w-full" />
              ))}
            </div>
          ) : (
            <ul className="flex flex-col gap-1">
              {documents.map((doc) => (
                <li key={doc.document}>
                  <div
                    className={cn(
                      "hover:bg-accent flex items-center gap-2 rounded-md transition-colors",
                      scope === doc.document && "bg-accent",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => openDocument(doc.document)}
                      className="flex flex-1 items-center gap-3 px-3 py-2.5 text-left text-sm"
                    >
                      <BookOpen className="text-muted-foreground size-4 shrink-0" />
                      <span className="flex-1">{doc.document}</span>
                      <Badge variant="outline" className="shrink-0 tabular-nums">
                        {doc.chunks} {doc.chunks === 1 ? "clause" : "clauses"}
                      </Badge>
                    </button>
                    {doc.url && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="mr-1 size-8 shrink-0"
                        asChild
                      >
                        <a
                          href={doc.url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`Open the source document for ${doc.document}`}
                          title="Open the official source document"
                        >
                          <ExternalLink />
                        </a>
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

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
              {/* A browsed clause was not ranked, so there is no score to show. */}
              {typeof hit.score === "number" && (
                <Badge variant="secondary" className="tabular-nums">
                  {hit.score.toFixed(2)}
                </Badge>
              )}
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
            {typeof hit.keyword_score === "number" &&
              typeof hit.vector_score === "number" && (
                <div className="text-muted-foreground flex gap-4 text-xs tabular-nums">
                  <span>keyword {hit.keyword_score.toFixed(3)}</span>
                  <span>vector {hit.vector_score.toFixed(3)}</span>
                </div>
              )}
            {hit.citation.url && (
              <Button variant="link" size="sm" className="w-fit px-0" asChild>
                <a href={hit.citation.url} target="_blank" rel="noreferrer">
                  Open the source document
                  <ExternalLink />
                </a>
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
