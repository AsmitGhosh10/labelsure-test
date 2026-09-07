"""Regulatory retrieval over the Legal Metrology corpus (PRD §8).

What this is
------------
A deterministic, offline retrieval layer over the *regulatory corpus*: the
machine-readable LM(PC)R 2011 ruleset (31 rules extracted from the Gazette
scan, each carrying its rule reference, page number and verbatim source
quote) plus any additional regulation documents dropped into the corpus
directory (amendments, notifications) as ``.json``, ``.md`` or ``.txt``.

Retrieval is hybrid:

* **Keyword (BM25)** over the tokenised clause text - exact statutory wording
  ("net quantity", "retail sale price") must retrieve exactly.
* **Character n-gram vector similarity** - a hashed 3-gram vector per chunk,
  cosine-compared. This tolerates OCR noise and morphology ("declaration" vs
  "declarations") without any model download.

Honest naming, per PRD §36: the n-gram vectors are *lexical* vectors, not
learned neural embeddings. Nothing here understands meaning; it matches
surface form robustly. The seam for a real embedding backend is
:meth:`RegulationRetriever.set_vectorizer` - swap in a sentence-embedding
function and the same hybrid scoring applies.

What it never does
------------------
It never invents regulation text, never paraphrases a clause, and never
decides compliance. It returns *citations* - document, rule, page, verbatim
quote - which the deterministic rule engine and the report cite. When
retrieval fails or returns nothing, callers surface "manual verification
required" (PRD §33) rather than guessing.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parent.parent / "rules" / "labelguard_rules_draft.json"
)
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent.parent / "rules" / "corpus"

TOKEN_RE = re.compile(r"[a-z0-9]+")

# Statutory stopwords: common English + drafting filler that carries no
# retrieval signal in a regulation corpus.
STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "been", "being", "but",
    "by", "for", "from", "has", "have", "in", "into", "is", "it", "its", "may",
    "not", "of", "on", "or", "other", "otherwise", "shall", "should", "such",
    "than", "that", "the", "their", "there", "these", "this", "those", "to",
    "under", "upon", "was", "were", "which", "while", "who", "with", "would",
}

NGRAM_SIZE = 3
VECTOR_DIM = 512

BM25_K1 = 1.5
BM25_B = 0.75


def tokenize(text: str) -> List[str]:
    """Lowercase word tokens with stopwords removed."""
    return [t for t in TOKEN_RE.findall((text or "").lower()) if t not in STOPWORDS]


def ngram_vector(text: str, dim: int = VECTOR_DIM, n: int = NGRAM_SIZE) -> Dict[int, float]:
    """L2-normalised hashed character n-gram vector (sparse dict).

    Deterministic across processes: uses blake2b, not Python's randomised
    ``hash()``.
    """
    normalised = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if not normalised:
        return {}
    vec: Dict[int, float] = {}
    for i in range(max(1, len(normalised) - n + 1)):
        gram = normalised[i : i + n]
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=4).digest()
        bucket = int.from_bytes(digest, "big") % dim
        vec[bucket] = vec.get(bucket, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm == 0:
        return {}
    return {k: v / norm for k, v in vec.items()}


def cosine(a: Dict[int, float], b: Dict[int, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


@dataclass
class RegulationChunk:
    """One retrievable clause with the metadata needed to cite it."""

    chunk_id: str
    document: str
    rule_reference: str
    title: str
    category: str
    text: str
    page: Optional[int] = None
    effective_date: Optional[str] = None
    source_type: str = "ruleset"
    status: str = "DRAFT"
    verified: bool = False
    severity: str = ""
    evidence_text: str = ""
    url: Optional[str] = None
    tokens: List[str] = field(default_factory=list, repr=False)
    vector: Dict[int, float] = field(default_factory=dict, repr=False)

    def citation(self) -> Dict[str, Any]:
        """The citation payload attached to a finding - never paraphrased."""
        return {
            "document": self.document,
            "rule": self.rule_reference,
            "title": self.title,
            "page": self.page,
            "effective_date": self.effective_date,
            "quote": self.evidence_text or self.text[:300],
            "status": self.status,
            "verified": self.verified,
            "url": self.url,
            "chunk_id": self.chunk_id,
        }


class RegulationRetriever:
    """Hybrid BM25 + lexical-vector retrieval over the regulation corpus."""

    def __init__(
        self,
        rules_path: Optional[str] = None,
        corpus_dir: Optional[str] = None,
        chunks: Optional[Sequence[RegulationChunk]] = None,
    ):
        self.chunks: List[RegulationChunk] = []
        self._vectorizer: Callable[[str], Dict[int, float]] = ngram_vector
        self._df: Dict[str, int] = {}
        self._avg_len: float = 0.0
        self.load_errors: List[str] = []

        if chunks is not None:
            self.chunks = list(chunks)
        else:
            self.chunks = self._load_ruleset(rules_path or str(DEFAULT_RULES_PATH))
            self.chunks.extend(
                self._load_corpus_dir(corpus_dir or str(DEFAULT_CORPUS_DIR))
            )
        self._index()

    # ------------------------------------------------------------------
    # Corpus loading (structure-preserving: one chunk per rule/clause)
    # ------------------------------------------------------------------

    def _load_ruleset(self, path: str) -> List[RegulationChunk]:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:  # corpus missing -> retrieval degrades, never crashes
            self.load_errors.append(f"ruleset {path}: {exc}")
            return []

        doc = (data.get("source_document") or {}).get(
            "title", "Legal Metrology (Packaged Commodities) Rules, 2011"
        )
        effective = (data.get("source_document") or {}).get("publication_date")
        chunks: List[RegulationChunk] = []
        for rule in data.get("rules", []):
            source = rule.get("source", {}) or {}
            text_parts = [
                rule.get("title", ""),
                rule.get("requirement", ""),
                rule.get("applicability", ""),
                source.get("evidence_text", ""),
            ]
            chunks.append(
                RegulationChunk(
                    chunk_id=rule.get("rule_id", ""),
                    document=source.get("document", doc),
                    rule_reference=source.get(
                        "rule_reference", rule.get("rule_reference", "")
                    ),
                    title=rule.get("title", ""),
                    category=rule.get("category", ""),
                    text=" ".join(p for p in text_parts if p),
                    page=source.get("source_pdf_page"),
                    effective_date=effective,
                    source_type="ruleset",
                    status=rule.get("status", "DRAFT"),
                    verified=bool(rule.get("verified", False)),
                    severity=rule.get("severity", ""),
                    evidence_text=source.get("evidence_text", ""),
                )
            )
        return chunks

    def _load_corpus_dir(self, directory: str) -> List[RegulationChunk]:
        """Ingest supplementary regulation documents (amendments, notifications).

        Supported: ``.json`` (list of clause objects), ``.md``/``.txt``
        (split into clauses on blank lines, page markers preserved when the
        text carries ``[p.N]`` markers). The directory is optional - an
        absent directory is not an error, it simply means the corpus is the
        ruleset alone.
        """
        chunks: List[RegulationChunk] = []
        base = Path(directory)
        if not base.is_dir():
            return chunks
        for path in sorted(base.iterdir()):
            if path.suffix.lower() == ".json":
                chunks.extend(self._load_corpus_json(path))
            elif path.suffix.lower() in (".md", ".txt"):
                chunks.extend(self._load_corpus_text(path))
        return chunks

    def _load_corpus_json(self, path: Path) -> List[RegulationChunk]:
        try:
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            self.load_errors.append(f"{path.name}: {exc}")
            return []
        entries = payload.get("clauses", payload) if isinstance(payload, dict) else payload
        document = (
            payload.get("document", path.stem) if isinstance(payload, dict) else path.stem
        )
        effective = payload.get("effective_date") if isinstance(payload, dict) else None
        url = payload.get("url") if isinstance(payload, dict) else None
        out = []
        for i, entry in enumerate(entries or []):
            if not isinstance(entry, dict):
                continue
            text = entry.get("text") or entry.get("requirement") or ""
            if not text.strip():
                continue
            out.append(
                RegulationChunk(
                    chunk_id=entry.get("id", f"{path.stem}-{i:03d}"),
                    document=entry.get("document", document),
                    rule_reference=entry.get("rule_reference", entry.get("rule", "")),
                    title=entry.get("title", ""),
                    category=entry.get("category", ""),
                    text=text,
                    page=entry.get("page"),
                    effective_date=entry.get("effective_date", effective),
                    source_type=entry.get("source_type", "amendment"),
                    status=entry.get("status", "PUBLISHED"),
                    verified=bool(entry.get("verified", False)),
                    evidence_text=entry.get("quote", text[:300]),
                    url=entry.get("url", url),
                )
            )
        return out

    def _load_corpus_text(self, path: Path) -> List[RegulationChunk]:
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as exc:
            self.load_errors.append(f"{path.name}: {exc}")
            return []
        out = []
        page = None
        for i, block in enumerate(re.split(r"\n\s*\n", raw)):
            block = block.strip()
            if not block:
                continue
            page_marker = re.search(r"\[p\.\s*(\d+)\]", block)
            if page_marker:
                page = int(page_marker.group(1))
                block = block.replace(page_marker.group(0), "").strip()
            rule_marker = re.match(r"(Rule\s+[\w()\-.]+)", block, re.IGNORECASE)
            out.append(
                RegulationChunk(
                    chunk_id=f"{path.stem}-{i:03d}",
                    document=path.stem.replace("_", " "),
                    rule_reference=rule_marker.group(1) if rule_marker else "",
                    title="",
                    category="",
                    text=block,
                    page=page,
                    source_type="document",
                    status="PUBLISHED",
                    evidence_text=block[:300],
                )
            )
        return out

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def set_vectorizer(self, fn: Callable[[str], Dict[int, float]]) -> None:
        """Swap the vector backend (e.g. a real sentence-embedding model).

        The function must map text -> a sparse ``{index: weight}`` L2-normalised
        vector. Re-indexes the corpus in place.
        """
        self._vectorizer = fn
        self._index()

    def _index(self) -> None:
        self._df = {}
        total_len = 0
        for chunk in self.chunks:
            chunk.tokens = tokenize(chunk.text)
            chunk.vector = self._vectorizer(chunk.text)
            total_len += len(chunk.tokens)
            for term in set(chunk.tokens):
                self._df[term] = self._df.get(term, 0) + 1
        self._avg_len = total_len / len(self.chunks) if self.chunks else 0.0

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _bm25(self, query_tokens: Sequence[str], chunk: RegulationChunk) -> float:
        if not chunk.tokens or not query_tokens:
            return 0.0
        n_docs = len(self.chunks)
        length = len(chunk.tokens)
        counts: Dict[str, int] = {}
        for t in chunk.tokens:
            counts[t] = counts.get(t, 0) + 1
        score = 0.0
        for term in query_tokens:
            tf = counts.get(term, 0)
            if tf == 0:
                continue
            df = self._df.get(term, 0)
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * length / (self._avg_len or 1))
            score += idf * (tf * (BM25_K1 + 1)) / denom
        return score

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
        rule_reference: Optional[str] = None,
        source_type: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Hybrid retrieval with metadata filtering.

        Returns ranked ``{"score", "keyword_score", "vector_score", "chunk",
        "citation"}`` entries. An empty list means *nothing matched* - callers
        must treat that as "manual verification required", never as "no rule
        applies".
        """
        if not query or not self.chunks:
            return []

        query_tokens = tokenize(query)
        query_vector = self._vectorizer(query)

        candidates: Iterable[RegulationChunk] = self.chunks
        if category:
            candidates = [c for c in candidates if c.category == category]
        if rule_reference:
            needle = rule_reference.lower()
            candidates = [c for c in candidates if needle in c.rule_reference.lower()]
        if source_type:
            candidates = [c for c in candidates if c.source_type == source_type]
        candidates = list(candidates)
        if not candidates:
            return []

        scored = []
        raw_keyword = [self._bm25(query_tokens, c) for c in candidates]
        max_kw = max(raw_keyword) if raw_keyword else 0.0
        for chunk, kw in zip(candidates, raw_keyword):
            kw_norm = kw / max_kw if max_kw > 0 else 0.0
            vec = cosine(query_vector, chunk.vector)
            # Keyword dominates: statutory wording must retrieve exactly.
            combined = 0.65 * kw_norm + 0.35 * vec
            if combined <= min_score:
                continue
            scored.append(
                {
                    "score": round(combined, 4),
                    "keyword_score": round(kw_norm, 4),
                    "vector_score": round(vec, 4),
                    "chunk_id": chunk.chunk_id,
                    "rule_reference": chunk.rule_reference,
                    "title": chunk.title,
                    "category": chunk.category,
                    "text": chunk.text,
                    "citation": chunk.citation(),
                }
            )
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:top_k]

    def citation_for_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Exact citation lookup by rule id (no ranking, no ambiguity)."""
        for chunk in self.chunks:
            if chunk.chunk_id == rule_id:
                return chunk.citation()
        return None

    # ------------------------------------------------------------------
    # Pipeline integration
    # ------------------------------------------------------------------

    def cite_findings(
        self, rule_results: Sequence[Dict[str, Any]], top_k: int = 1
    ) -> List[Dict[str, Any]]:
        """Attach source citations to the findings that need them.

        Only FAIL and MANUAL_REVIEW findings are cited - those are the ones an
        inspector must justify. Exact rule-id lookup is preferred; retrieval is
        the fallback when the finding's rule is not in the corpus (e.g. it came
        from an amendment document).
        """
        citations = []
        for rule in rule_results or []:
            if rule.get("status") not in ("FAIL", "MANUAL_REVIEW"):
                continue
            rule_id = rule.get("rule_id", "")
            exact = self.citation_for_rule(rule_id)
            if exact:
                citations.append(
                    {
                        "rule_id": rule_id,
                        "status": rule.get("status"),
                        "retrieval": "exact_rule_id",
                        "citations": [exact],
                    }
                )
                continue
            query = " ".join(
                str(rule.get(k, "")) for k in ("requirement", "reason")
            ).strip()
            hits = self.search(query, top_k=top_k)
            citations.append(
                {
                    "rule_id": rule_id,
                    "status": rule.get("status"),
                    "retrieval": "hybrid_search" if hits else "no_match",
                    "citations": [h["citation"] for h in hits],
                    "note": (
                        None
                        if hits
                        else "No regulation text retrieved - manual verification required"
                    ),
                }
            )
        return citations

    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        documents = sorted({c.document for c in self.chunks})
        return {
            "chunks": len(self.chunks),
            "documents": documents,
            "source_types": sorted({c.source_type for c in self.chunks}),
            "with_page_numbers": sum(1 for c in self.chunks if c.page is not None),
            "vector_dim": VECTOR_DIM,
            "vectorizer": getattr(self._vectorizer, "__name__", "custom"),
            "load_errors": self.load_errors,
        }


_retriever: Optional[RegulationRetriever] = None


def get_retriever() -> RegulationRetriever:
    """Process-wide retriever (the corpus is small and read-only)."""
    global _retriever
    if _retriever is None:
        _retriever = RegulationRetriever()
    return _retriever
