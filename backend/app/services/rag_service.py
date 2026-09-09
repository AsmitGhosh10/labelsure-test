"""Grounded RAG over the Legal Metrology regulation corpus.

This is the RAG pipeline from ``rag/Multimodal_RAG_Project-main`` adapted to
this codebase: hybrid retrieval -> RRF fusion -> optional cross-encoder
rerank -> answer generation. Three things changed on the way across.

**The corpus is the regulation corpus.** The upstream project ingested
arbitrary uploads into Postgres + FAISS. Here the corpus is already indexed
by :mod:`backend.app.services.regulation_retrieval` - the 31 LM(PC)R 2011
clauses plus anything dropped into the corpus directory - so there is no
second index, no second database and no ingestion step.

**Generation is optional, grounding is not.** With ``GROQ_API_KEY`` set the
answer is written by the configured Groq model, constrained to the retrieved
clauses. Without it the service still answers, extractively, by quoting the
retrieved clauses verbatim. It never runs ungrounded: no retrieval means no
answer, and the caller is told to verify manually (PRD §33).

**No web-search fallback.** The upstream pipeline reached for Tavily when
internal confidence was low. Answering a *statutory* question from an
arbitrary web page is exactly the failure this project exists to avoid, so a
low-confidence retrieval here degrades to "insufficient regulatory basis"
instead. ``used_web_search`` stays in the response shape, always ``False``,
because the frontend contract came across with it.

The heavy optional pieces - Groq for generation, sentence-transformers for
cross-encoder reranking - are imported lazily and degrade to the deterministic
path when absent, so the service works on a bare install.
"""

from __future__ import annotations

import importlib.util
import math
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.services import legal
from backend.app.services.regulation_retrieval import get_retriever

# Retrieval breadth before fusion/rerank. Wider than top_k so the reranker has
# something to reorder.
CANDIDATE_MULTIPLIER = 4

# RRF constant, from the upstream ranker. Larger k flattens the contribution
# of rank position, which is what we want when the two views disagree.
RRF_K = 40

# Below this fused score we refuse to answer rather than generate prose off
# weak retrieval.
MIN_GROUNDING_SCORE = float(os.environ.get("RAG_MIN_GROUNDING_SCORE", "0.08"))

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

# Reasoning models (the gpt-oss family among them) spend part of the token
# budget thinking before they answer, and that thinking is billed against
# max_tokens. Left unbounded it can consume the whole budget and return empty
# content. "low" is ample for answering from a handful of supplied clauses.
GROQ_REASONING_EFFORT = os.environ.get("GROQ_REASONING_EFFORT", "low")

SYSTEM_PROMPT = (
    "You are a compliance research assistant for the Indian Legal Metrology "
    "(Packaged Commodities) Rules, 2011. Answer ONLY from the numbered "
    "regulation extracts provided. Cite the rule reference (for example "
    "'Rule 6(1)(a)') for every statement you make. If the extracts do not "
    "answer the question, say so plainly and do not guess. Never invent a "
    "rule number, a page number or statutory wording."
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;])\s+")


# Inputs that are not questions about the regulation corpus. Answering these
# by retrieval produces two bad outcomes: a greeting gets a page of statutory
# refusal, and a question about the system itself gets answered with whatever
# clauses happened to rank highest - a meta question dressed as a regulatory
# finding. Both are worse than saying what this tool is for.
SMALLTALK = frozenset(
    {
        "hi", "hey", "hello", "yo", "hiya", "howdy", "sup", "hey there",
        "hi there", "hello there", "good morning", "good afternoon",
        "good evening", "namaste", "thanks", "thank you", "thanks a lot",
        "thankyou", "ty", "ok", "okay", "cool", "nice", "great", "bye",
        "goodbye", "see you", "test", "testing", "ping",
    }
)

CAPABILITY_RE = re.compile(
    r"^(what|who|how)\s+(can|do|are|does|should)\s+(you|this|it|i)\b"
    r"|^(help|what is this|whats this|what's this)\b"
    r"|\bwhat can you do\b|\bwho are you\b|\bhow do i use\b",
    re.IGNORECASE,
)

SMALLTALK_REPLY = (
    "This assistant answers questions about the Legal Metrology (Packaged "
    "Commodities) Rules, 2011, using only the indexed regulation corpus.\n\n"
    "Ask it something like:\n"
    "  - What must be declared as the retail sale price?\n"
    "  - How should the month and year of manufacture be shown?\n"
    "  - Which packages are exempt from these rules?"
)

CAPABILITY_REPLY = (
    "This assistant answers questions about the Legal Metrology (Packaged "
    "Commodities) Rules, 2011. It retrieves the relevant clauses from the "
    "indexed corpus and answers from those clauses only, citing the rule "
    "reference and page for each statement.\n\n"
    "It does not decide compliance. Package screening is a separate, "
    "deterministic pipeline; nothing generated here affects a verdict. When "
    "the corpus does not cover a question, it says so rather than guessing."
)


def classify_intent(query: str) -> str:
    """``smalltalk`` | ``capability`` | ``regulation``.

    Deliberately lexical and conservative. Only a query that is *entirely*
    smalltalk is diverted; anything containing substantive words falls through
    to retrieval, because wrongly diverting a real regulation question is far
    worse than answering a greeting literally.
    """
    normalised = re.sub(r"[^a-z\s']", "", query.lower()).strip()
    if not normalised:
        return "smalltalk"
    if normalised in SMALLTALK:
        return "smalltalk"
    if CAPABILITY_RE.search(query.strip()):
        return "capability"
    return "regulation"


def _rrf_fuse(result_lists: Sequence[Sequence[str]], k: int = RRF_K) -> Dict[str, float]:
    """Reciprocal Rank Fusion over ranked chunk-id lists.

    Ported from ``app/ml/ranking/rrf_ranker.py`` in the RAG project. Each list
    is one retriever's view of the same query; a chunk that ranks well in both
    views beats a chunk that only one view liked.
    """
    scores: Dict[str, float] = {}
    for ranked in result_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


class _CrossEncoderReranker:
    """Lazy cross-encoder rerank; a no-op when the model is unavailable.

    Mirrors the upstream reranker's scoring (sigmoid over the raw margin,
    blended 80/20 with the retrieval score) but never fails a request: if
    ``sentence-transformers`` is not installed or the weights are not cached,
    the candidates come back in their fused order.
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or os.environ.get(
            "RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        self._model: Any = None
        self._unavailable = False

    @property
    def available(self) -> bool:
        """Whether reranking could run at all.

        Checked without importing sentence-transformers, which drags in torch
        and costs seconds. A status call must not pay that, and must not claim
        a reranker that is not installed.
        """
        if self._unavailable:
            return False
        if self._model is not None:
            return True
        return importlib.util.find_spec("sentence_transformers") is not None

    def _load(self) -> Any:
        if self._model is None and not self._unavailable:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self.model_name, max_length=512)
            except Exception:
                # No torch, no weights, no network - all the same to the caller.
                self._unavailable = True
        return self._model

    def rerank(
        self, query: str, candidates: List[Tuple[str, float, str]]
    ) -> Tuple[List[Tuple[str, float, str]], bool]:
        """``[(chunk_id, score, text)]`` -> reordered, plus whether it ran."""
        if not candidates:
            return [], False
        model = self._load()
        if model is None:
            return candidates, False
        try:
            raw = model.predict([(query, text) for _, _, text in candidates])
        except Exception:
            self._unavailable = True
            return candidates, False

        rescored = []
        for (chunk_id, retrieval_score, text), margin in zip(candidates, raw):
            norm_rerank = 1.0 / (1.0 + math.exp(-float(margin)))
            norm_retrieval = max(0.0, min(1.0, float(retrieval_score)))
            rescored.append(
                (chunk_id, 0.80 * norm_rerank + 0.20 * norm_retrieval, text)
            )
        rescored.sort(key=lambda row: row[1], reverse=True)
        return rescored, True


class _GroqGenerator:
    """Lazy Groq client; absent key or package means extractive answers."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY")
        self.model = model or GROQ_MODEL
        self._client: Any = None
        self._unavailable = not self.api_key
        # Why the last generation attempt fell back. Reported by describe():
        # a silent fallback to extractive answers is indistinguishable from
        # "no key configured", which makes a wrong model name impossible to
        # diagnose from outside the process.
        self.last_error: Optional[str] = None

    @property
    def available(self) -> bool:
        return not self._unavailable

    def _load(self) -> Any:
        if self._client is None and not self._unavailable:
            try:
                from groq import Groq

                self._client = Groq(api_key=self.api_key)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
                self._unavailable = True
        return self._client

    def generate(
        self, query: str, context: str, temperature: float, max_tokens: int
    ) -> Optional[str]:
        client = self._load()
        if client is None:
            return None

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Regulation extracts:\n{context}\n\nQuestion: {query}",
            },
        ]
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_effort": GROQ_REASONING_EFFORT,
        }
        try:
            completion = client.chat.completions.create(**kwargs)
        except TypeError:
            # Older SDKs and non-reasoning models reject reasoning_effort.
            kwargs.pop("reasoning_effort")
            try:
                completion = client.chat.completions.create(**kwargs)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
                return None
        except Exception as exc:
            # A generation failure must not lose the retrieved citations, so
            # the caller falls back to the extractive answer - but it has to
            # record why, or a wrong model name looks like no model at all.
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            return None

        choice = completion.choices[0]
        answer = (choice.message.content or "").strip()
        if not answer:
            # Reasoning models can spend the whole budget before writing a
            # word; that is a configuration fault, not an empty answer.
            self.last_error = "the model returned no content" + (
                "; the token budget was spent on reasoning - raise max_tokens "
                "or lower GROQ_REASONING_EFFORT"
                if choice.finish_reason == "length"
                else ""
            )
            return None
        self.last_error = None
        return answer


def _extractive_answer(query: str, sources: List[Dict[str, Any]]) -> str:
    """Answer built only from retrieved clause text - nothing generated.

    Picks the sentences of each top clause that share vocabulary with the
    question, quotes them verbatim, and attributes each to its rule. This is
    what the service returns whenever no LLM is configured, and what it falls
    back to when generation fails.
    """
    query_terms = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2}
    lines: List[str] = []
    for source in sources[:3]:
        text = (source.get("content") or "").strip()
        if not text:
            continue
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
        best = max(
            sentences,
            key=lambda s: len(query_terms & set(re.findall(r"[a-z0-9]+", s.lower()))),
            default=text,
        )
        rule = source.get("metadata", {}).get("rule") or source.get("chunk_id")
        lines.append(f"{rule}: “{best.rstrip('.')}.”")
    if not lines:
        return legal.INSUFFICIENT_BASIS
    return (
        "Retrieved from the regulation corpus (verbatim, not generated):\n\n"
        + "\n\n".join(lines)
    )


class RegulationRAGService:
    """Hybrid retrieval + RRF + optional rerank + optional generation."""

    def __init__(
        self,
        retriever: Any = None,
        reranker: Optional[_CrossEncoderReranker] = None,
        generator: Optional[_GroqGenerator] = None,
    ) -> None:
        self._retriever = retriever
        self.reranker = reranker if reranker is not None else _CrossEncoderReranker()
        self.generator = generator if generator is not None else _GroqGenerator()

    @property
    def retriever(self) -> Any:
        return self._retriever if self._retriever is not None else get_retriever()

    def _retrieve(self, query: str, k: int, category: Optional[str]) -> List[Dict[str, Any]]:
        """Hybrid search, re-fused with RRF over its keyword and vector views.

        ``RegulationRetriever.search`` already returns a linear 0.65/0.35 blend
        plus the two component scores. Ranking those components separately and
        fusing by rank gives the upstream RRF behaviour without a second index:
        rank fusion is scale-free, so a clause that both views rank highly wins
        even when one view's raw score is small.
        """
        hits = self.retriever.search(
            query, top_k=max(k * CANDIDATE_MULTIPLIER, k), category=category
        )
        if not hits:
            return []

        by_keyword = [
            h["chunk_id"]
            for h in sorted(hits, key=lambda r: r.get("keyword_score", 0.0), reverse=True)
        ]
        by_vector = [
            h["chunk_id"]
            for h in sorted(hits, key=lambda r: r.get("vector_score", 0.0), reverse=True)
        ]
        fused = _rrf_fuse([by_keyword, by_vector])

        for hit in hits:
            hit["rrf_score"] = round(fused.get(hit["chunk_id"], 0.0), 6)
        hits.sort(key=lambda r: (r["rrf_score"], r["score"]), reverse=True)
        return hits

    @staticmethod
    def _as_source(hit: Dict[str, Any], score: float) -> Dict[str, Any]:
        citation = hit.get("citation", {})
        return {
            "chunk_id": hit["chunk_id"],
            "content": hit.get("text", ""),
            "score": round(float(score), 4),
            "chunk_type": "regulation",
            "metadata": {
                "rule": hit.get("rule_reference"),
                "title": hit.get("title"),
                "category": hit.get("category"),
                "document": citation.get("document"),
                "page": citation.get("page"),
                "quote": citation.get("quote"),
                "status": citation.get("status"),
                "verified": citation.get("verified"),
                "url": citation.get("url"),
            },
            "scores": {
                "keyword": hit.get("keyword_score"),
                "vector": hit.get("vector_score"),
                "hybrid": hit.get("score"),
                "rrf": hit.get("rrf_score"),
            },
        }

    def ask(
        self,
        query: str,
        k: int = 5,
        use_reranker: bool = True,
        category: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> Dict[str, Any]:
        """Answer a regulation question from the corpus, with citations."""
        query = (query or "").strip()
        if not query:
            raise ValueError("query must not be empty")

        # Not every input is a regulation question. Divert the ones that are
        # not before retrieval, so a greeting does not come back as statutory
        # refusal and a question about this tool does not come back as a rule.
        intent = classify_intent(query)
        if intent != "regulation":
            return {
                "query": query,
                "answer": SMALLTALK_REPLY if intent == "smalltalk" else CAPABILITY_REPLY,
                "sources": [],
                "confidence": 0.0,
                "used_web_search": False,
                "grounded": False,
                "intent": intent,
                "generator": "none",
                "reranked": False,
                "disclaimer": legal.DISCLAIMER,
            }

        hits = self._retrieve(query, k, category)
        if not hits:
            return {
                "query": query,
                "answer": legal.INSUFFICIENT_BASIS,
                "sources": [],
                "confidence": 0.0,
                "used_web_search": False,
                "grounded": False,
                "intent": "regulation",
                "generator": "none",
                "reranked": False,
                "disclaimer": legal.DISCLAIMER,
            }

        reranked, did_rerank = (
            self.reranker.rerank(
                query,
                [(h["chunk_id"], float(h.get("score", 0.0)), h.get("text", "")) for h in hits[: k * 2]],
            )
            if use_reranker
            else ([(h["chunk_id"], float(h.get("score", 0.0)), h.get("text", "")) for h in hits[: k * 2]], False)
        )

        by_id = {h["chunk_id"]: h for h in hits}
        sources = [
            self._as_source(by_id[chunk_id], score)
            for chunk_id, score, _ in reranked[:k]
            if chunk_id in by_id
        ]

        # Confidence: retrieval strength, coverage, and whether a reranker
        # actually looked at the candidates. Deliberately conservative - this
        # number gates whether we answer at all.
        top_hybrid = max((float(h.get("score", 0.0)) for h in hits), default=0.0)
        coverage = min(1.0, len(sources) / float(k)) if k else 0.0
        confidence = 0.65 * top_hybrid + 0.25 * coverage + (0.10 if did_rerank else 0.0)
        confidence = round(max(0.0, min(1.0, confidence)), 4)

        grounded = top_hybrid >= MIN_GROUNDING_SCORE
        if not grounded:
            return {
                "query": query,
                "answer": legal.INSUFFICIENT_BASIS,
                "sources": sources,
                "confidence": confidence,
                "used_web_search": False,
                "grounded": False,
                "intent": "regulation",
                "generator": "none",
                "reranked": did_rerank,
                "disclaimer": legal.DISCLAIMER,
            }

        context = "\n\n".join(
            f"[{i}] {s['metadata'].get('rule') or s['chunk_id']} - "
            f"{s['metadata'].get('title') or ''}\n{s['content']}"
            for i, s in enumerate(sources, start=1)
        )
        answer = self.generator.generate(query, context, temperature, max_tokens)
        generator = "groq" if answer else "extractive"
        if not answer:
            answer = _extractive_answer(query, sources)

        return {
            "query": query,
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "used_web_search": False,
            "grounded": True,
            "intent": "regulation",
            "generator": generator,
            "reranked": did_rerank,
            "disclaimer": legal.DISCLAIMER,
        }

    def describe(self) -> Dict[str, Any]:
        """Which optional pieces are actually live in this deployment."""
        stats = self.retriever.stats()
        return {
            "corpus": stats,
            "generator": "groq" if self.generator.available else "extractive",
            "generation_model": self.generator.model if self.generator.available else None,
            "generation_error": self.generator.last_error,
            # The reranker loads on first use, so this names the model that
            # would run, not one already resident.
            "reranker_model": self.reranker.model_name if self.reranker.available else None,
            "web_search": False,
            "min_grounding_score": MIN_GROUNDING_SCORE,
            "disclaimer": legal.DISCLAIMER,
        }


_service: Optional[RegulationRAGService] = None


def get_rag_service() -> RegulationRAGService:
    """Process-wide singleton - the retriever index is built once."""
    global _service
    if _service is None:
        _service = RegulationRAGService()
    return _service
