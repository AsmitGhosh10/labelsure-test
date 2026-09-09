"""Grounded regulation RAG (retrieval -> fusion -> rerank -> answer)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend.app.services import legal
from backend.app.services.rag_service import (
    RegulationRAGService,
    classify_intent,
    _CrossEncoderReranker,
    _extractive_answer,
    _GroqGenerator,
    _parse_envelope,
    _retrieval_query,
    _rrf_fuse,
    get_rag_service,
)


class _StubRetriever:
    """A retriever with a fixed, hand-scored corpus."""

    def __init__(self, hits=None):
        self._hits = hits if hits is not None else self._default_hits()

    @staticmethod
    def _default_hits():
        return [
            {
                "chunk_id": "R6E",
                "score": 0.90,
                "keyword_score": 0.95,
                "vector_score": 0.40,
                "rule_reference": "Rule 6(1)(e)",
                "title": "Retail sale price",
                "category": "mrp",
                "text": "Declare the retail sale price of the package.",
                "citation": {
                    "document": "LM(PC)R 2011",
                    "page": 12,
                    "quote": "retail sale price",
                    "status": "VERIFIED",
                    "verified": True,
                    "url": None,
                },
            },
            {
                "chunk_id": "R6A",
                "score": 0.40,
                "keyword_score": 0.20,
                "vector_score": 0.90,
                "rule_reference": "Rule 6(1)(a)",
                "title": "Manufacturer name",
                "category": "manufacturer",
                "text": "Declare the name and address of the manufacturer.",
                "citation": {"document": "LM(PC)R 2011", "page": 11, "quote": "name"},
            },
        ]

    def search(self, query, top_k=5, category=None, **kwargs):
        hits = self._hits
        if category:
            hits = [h for h in hits if h.get("category") == category]
        return [dict(h) for h in hits[:top_k]]

    def stats(self):
        return {"chunks": len(self._hits)}


class _StubGenerator(_GroqGenerator):
    """A generator that returns a fixed classification and reply."""

    def __init__(self, kind, answer):
        super().__init__(api_key="stub")
        self._kind = kind
        self._answer = answer
        self.seen_history = None

    @property
    def available(self):
        return True

    def converse(self, query, context, history, temperature, max_tokens):
        self.seen_history = history
        self.seen_context = context
        return self._kind, self._answer


def _service(**kwargs):
    kwargs.setdefault("retriever", _StubRetriever())
    kwargs.setdefault("generator", _GroqGenerator(api_key=None))
    return RegulationRAGService(**kwargs)


class TestRRFFusion:
    def test_a_chunk_ranked_well_by_both_views_wins(self):
        fused = _rrf_fuse([["a", "b", "c"], ["a", "c", "b"]])
        assert fused["a"] > fused["b"]
        assert fused["a"] > fused["c"]

    def test_a_chunk_seen_by_one_view_only_scores_once(self):
        fused = _rrf_fuse([["a"], ["b"]])
        assert fused["a"] == pytest.approx(fused["b"])
        assert fused["a"] == pytest.approx(1.0 / 41)

    def test_no_lists_is_empty_not_an_error(self):
        assert _rrf_fuse([]) == {}


class TestGrounding:
    def test_an_answer_carries_its_sources(self):
        result = _service().ask("retail sale price", k=2)
        assert result["grounded"] is True
        assert result["sources"]
        assert result["sources"][0]["metadata"]["rule"] == "Rule 6(1)(e)"

    def test_nothing_retrieved_refuses_instead_of_guessing(self):
        result = RegulationRAGService(
            retriever=_StubRetriever(hits=[]), generator=_GroqGenerator(api_key=None)
        ).ask("what colour should the box be")
        assert result["grounded"] is False
        assert result["answer"] == legal.INSUFFICIENT_BASIS
        assert result["sources"] == []
        assert result["confidence"] == 0.0

    def test_weak_retrieval_refuses_but_still_shows_what_it_found(self, monkeypatch):
        """A near-miss must not become generated statutory prose."""
        monkeypatch.setattr(
            "backend.app.services.rag_service.MIN_GROUNDING_SCORE", 0.99
        )
        result = _service().ask("retail sale price", k=2)
        assert result["grounded"] is False
        assert result["answer"] == legal.INSUFFICIENT_BASIS
        assert result["sources"], "the citations are still shown for inspection"

    def test_empty_query_is_rejected(self):
        with pytest.raises(ValueError):
            _service().ask("   ")

    def test_every_answer_carries_the_disclaimer(self):
        assert _service().ask("retail sale price")["disclaimer"] == legal.DISCLAIMER

    def test_web_search_is_never_used(self):
        assert _service().ask("retail sale price")["used_web_search"] is False


class TestExtractiveFallback:
    def test_no_llm_means_verbatim_quotes(self):
        result = _service().ask("retail sale price", k=2)
        assert result["generator"] == "extractive"
        assert "Rule 6(1)(e)" in result["answer"]
        assert "retail sale price" in result["answer"].lower()

    def test_the_quote_comes_from_the_corpus_not_the_model(self):
        sources = [
            {
                "chunk_id": "R6E",
                "content": "Declare the retail sale price. Declare the net quantity.",
                "metadata": {"rule": "Rule 6(1)(e)"},
            }
        ]
        answer = _extractive_answer("what is the retail sale price rule", sources)
        assert "retail sale price" in answer
        assert "Rule 6(1)(e)" in answer

    def test_blank_sources_fall_back_to_the_refusal(self):
        assert _extractive_answer("anything", [{"content": ""}]) == legal.INSUFFICIENT_BASIS


class TestGeneration:
    def test_a_working_generator_is_used_and_labelled(self):
        result = _service(
            generator=_StubGenerator("regulation", "Rule 6(1)(e) requires the price.")
        ).ask("retail sale price")
        assert result["generator"] == "groq"
        assert result["answer"].startswith("Rule 6(1)(e)")
        assert result["intent"] == "regulation"

    def test_a_failing_generator_falls_back_without_losing_citations(self):
        class _Broken(_GroqGenerator):
            @property
            def available(self):
                return True

            def converse(self, *a, **k):
                return None

        result = _service(generator=_Broken(api_key="x")).ask("retail sale price")
        assert result["generator"] == "extractive"
        assert result["sources"], "a generation failure must not drop the sources"

    def test_no_api_key_means_no_client(self):
        assert _GroqGenerator(api_key=None).available is False
        assert _GroqGenerator(api_key=None).generate("q", "c", 0.2, 100) is None


class TestReranker:
    def test_an_unavailable_model_leaves_the_order_alone(self):
        reranker = _CrossEncoderReranker()
        reranker._unavailable = True
        candidates = [("a", 0.9, "text a"), ("b", 0.1, "text b")]
        ranked, ran = reranker.rerank("q", candidates)
        assert ran is False
        assert ranked == candidates

    def test_no_candidates_is_empty_not_an_error(self):
        assert _CrossEncoderReranker().rerank("q", []) == ([], False)

    def test_a_working_model_reorders_and_is_reported(self):
        class _Stub(_CrossEncoderReranker):
            def _load(self):
                class _M:
                    @staticmethod
                    def predict(pairs):
                        # Second candidate scores far higher on the margin.
                        return [-4.0, 4.0]

                return _M()

        ranked, ran = _Stub().rerank("q", [("a", 0.9, "ta"), ("b", 0.1, "tb")])
        assert ran is True
        assert ranked[0][0] == "b"

    def test_rerank_raises_nothing_when_predict_explodes(self):
        class _Boom(_CrossEncoderReranker):
            def _load(self):
                class _M:
                    @staticmethod
                    def predict(pairs):
                        raise RuntimeError("no weights")

                return _M()

        ranked, ran = _Boom().rerank("q", [("a", 0.9, "ta")])
        assert ran is False and ranked == [("a", 0.9, "ta")]


class TestFilteringAndShape:
    def test_category_filter_narrows_the_corpus(self):
        result = _service().ask("declaration", k=5, category="manufacturer")
        assert [s["metadata"]["rule"] for s in result["sources"]] == ["Rule 6(1)(a)"]

    def test_sources_expose_the_component_scores(self):
        source = _service().ask("retail sale price")["sources"][0]
        assert set(source["scores"]) == {"keyword", "vector", "hybrid", "rrf"}
        assert source["chunk_type"] == "regulation"

    def test_confidence_is_a_probability(self):
        assert 0.0 <= _service().ask("retail sale price")["confidence"] <= 1.0

    def test_k_caps_the_number_of_sources(self):
        assert len(_service().ask("declaration", k=1)["sources"]) == 1


class TestDescribeAndSingleton:
    def test_describe_reports_the_live_backends(self):
        described = _service().describe()
        assert described["generator"] == "extractive"
        assert described["web_search"] is False
        assert described["corpus"]["chunks"] == 2

    def test_the_real_corpus_answers_a_real_question(self):
        """End to end against the shipped LM(PC)R corpus, no stubs."""
        result = get_rag_service().ask("retail sale price declaration", k=3)
        assert result["sources"], "the shipped corpus must retrieve something"
        assert any(
            "6(1)" in (s["metadata"]["rule"] or "") for s in result["sources"]
        ), "a price question must reach the Rule 6 declarations"

    def test_get_rag_service_is_a_singleton(self):
        assert get_rag_service() is get_rag_service()


class TestRerankerAvailability:
    def test_availability_does_not_claim_an_uninstalled_reranker(self, monkeypatch):
        """A status call must not advertise a reranker that cannot run."""
        monkeypatch.setattr(
            "backend.app.services.rag_service.importlib.util.find_spec",
            lambda name: None,
        )
        assert _CrossEncoderReranker().available is False

    def test_availability_is_true_when_the_package_is_present(self, monkeypatch):
        monkeypatch.setattr(
            "backend.app.services.rag_service.importlib.util.find_spec",
            lambda name: object(),
        )
        assert _CrossEncoderReranker().available is True

    def test_a_failed_load_is_remembered(self):
        reranker = _CrossEncoderReranker()
        reranker._unavailable = True
        assert reranker.available is False


class TestGenerationDiagnostics:
    """A silent fallback to extractive answers hides configuration faults."""

    class _Choice:
        def __init__(self, content, finish_reason="stop"):
            self.message = type("M", (), {"content": content})()
            self.finish_reason = finish_reason

    def _client(self, choice=None, raises=None):
        outer = self

        class _Completions:
            @staticmethod
            def create(**kwargs):
                if raises:
                    raise raises
                outer.seen = kwargs
                return type("R", (), {"choices": [choice]})()

        return type(
            "C", (), {"chat": type("Chat", (), {"completions": _Completions})()}
        )()

    def _generator(self, client):
        generator = _GroqGenerator(api_key="k")
        generator._client = client
        return generator

    def test_an_api_error_is_recorded_not_swallowed(self):
        generator = self._generator(
            self._client(raises=RuntimeError("model_not_found"))
        )
        assert generator.generate("q", "c", 0.2, 100) is None
        assert "model_not_found" in generator.last_error

    def test_empty_content_from_a_reasoning_model_explains_itself(self):
        generator = self._generator(
            self._client(choice=self._Choice("", finish_reason="length"))
        )
        assert generator.generate("q", "c", 0.2, 10) is None
        assert "reasoning" in generator.last_error

    def test_a_successful_generation_clears_the_error(self):
        generator = self._generator(self._client(choice=self._Choice("An answer")))
        generator.last_error = "stale"
        assert generator.generate("q", "c", 0.2, 100) == "An answer"
        assert generator.last_error is None

    def test_reasoning_effort_is_sent(self):
        generator = self._generator(self._client(choice=self._Choice("ok")))
        generator.generate("q", "c", 0.2, 100)
        assert self.seen["reasoning_effort"]

    def test_an_sdk_that_rejects_reasoning_effort_still_works(self):
        """Older SDKs raise TypeError on the unknown keyword."""
        calls = []

        class _Completions:
            @staticmethod
            def create(**kwargs):
                calls.append(kwargs)
                if "reasoning_effort" in kwargs:
                    raise TypeError("unexpected keyword argument")
                return type(
                    "R",
                    (),
                    {"choices": [TestGenerationDiagnostics._Choice("fallback ok")]},
                )()

        client = type(
            "C", (), {"chat": type("Chat", (), {"completions": _Completions})()}
        )()
        generator = self._generator(client)
        assert generator.generate("q", "c", 0.2, 100) == "fallback ok"
        assert len(calls) == 2

    def test_describe_surfaces_the_generation_error(self):
        service = _service()
        service.generator.last_error = "NotFoundError: no such model"
        assert service.describe()["generation_error"] == "NotFoundError: no such model"


class TestIntentClassification:
    """Not every input is a regulation question."""

    @pytest.mark.parametrize(
        "query", ["hey", "Hello!", "hi there", "thanks", "good morning", "ok", "   "]
    )
    def test_smalltalk_is_recognised(self, query):
        assert classify_intent(query) == "smalltalk"

    @pytest.mark.parametrize(
        "query", ["what can you do", "who are you", "help", "how do i use this"]
    )
    def test_capability_questions_are_recognised(self, query):
        assert classify_intent(query) == "capability"

    @pytest.mark.parametrize(
        "query",
        [
            "What must be declared as the retail sale price?",
            "net quantity",
            "hey what is the rule for net quantity",
            "hello, which packages are exempt?",
            "thanks, but what about imported packages",
        ],
    )
    def test_a_real_question_is_never_diverted(self, query):
        """Diverting a genuine question is far worse than answering a greeting."""
        assert classify_intent(query) == "regulation"

    def test_a_greeting_gets_guidance_not_a_statutory_refusal(self):
        """With no model configured, the lexical fallback still diverts."""
        result = _service().ask("hey")
        assert result["intent"] == "conversation"
        assert result["answer"] != legal.INSUFFICIENT_BASIS
        assert "retail sale price" in result["answer"]
        assert result["sources"] == []

    def test_a_capability_question_is_not_answered_from_the_corpus(self):
        """'What can you do' must not come back as a quantity-declaration rule."""
        result = _service().ask("what can you do")
        assert result["intent"] == "conversation"
        assert result["sources"] == []
        assert result["generator"] == "none"
        assert "does not decide compliance" in result["answer"]

    def test_diverted_answers_still_carry_the_disclaimer(self):
        assert _service().ask("hey")["disclaimer"] == legal.DISCLAIMER

    def test_every_answer_reports_an_intent(self):
        for query in ("hey", "what can you do", "retail sale price"):
            assert _service().ask(query)["intent"] in {
                "conversation",
                "out_of_scope",
                "regulation",
            }


class TestConversationalMode:
    """With a model configured, one call classifies and replies."""

    def test_conversation_carries_no_citations(self):
        service = _service(
            generator=_StubGenerator("conversation", "Hello. Ask me about labelling.")
        )
        result = service.ask("hey")
        assert result["intent"] == "conversation"
        assert result["sources"] == []
        assert result["confidence"] == 0.0
        assert result["answer"].startswith("Hello")

    def test_out_of_scope_is_reported_as_such(self):
        service = _service(
            generator=_StubGenerator("out_of_scope", "I don't write code.")
        )
        result = service.ask("write me a python web scraper")
        assert result["intent"] == "out_of_scope"
        assert result["sources"] == []
        assert result["grounded"] is False

    def test_a_regulation_reply_keeps_its_citations(self):
        service = _service(
            generator=_StubGenerator("regulation", "Rule 6(1)(e) requires the price.")
        )
        result = service.ask("retail sale price")
        assert result["grounded"] is True
        assert result["sources"]
        assert result["confidence"] > 0

    def test_weak_retrieval_discards_the_model_reply(self, monkeypatch):
        """The model must not talk its way past the grounding gate."""
        monkeypatch.setattr(
            "backend.app.services.rag_service.MIN_GROUNDING_SCORE", 0.99
        )
        service = _service(
            generator=_StubGenerator("regulation", "Rule 99 says whatever I like.")
        )
        result = service.ask("retail sale price")
        assert result["grounded"] is False
        assert result["answer"] == legal.INSUFFICIENT_BASIS
        assert "Rule 99" not in result["answer"]

    def test_conversation_is_not_gated_by_retrieval(self, monkeypatch):
        """A greeting must not be refused for lack of a matching clause."""
        monkeypatch.setattr(
            "backend.app.services.rag_service.MIN_GROUNDING_SCORE", 0.99
        )
        result = _service(generator=_StubGenerator("conversation", "Hi there.")).ask(
            "hey"
        )
        assert result["answer"] == "Hi there."

    def test_history_reaches_the_model(self):
        generator = _StubGenerator("conversation", "Yes.")
        history = [
            {"role": "user", "content": "what is the price rule"},
            {"role": "assistant", "content": "Rule 6(1)(e)."},
        ]
        _service(generator=generator).ask("and for imports?", history=history)
        assert generator.seen_history == history

    def test_retrieved_clauses_reach_the_model(self):
        generator = _StubGenerator("regulation", "answer")
        _service(generator=generator).ask("retail sale price")
        assert "Rule 6(1)(e)" in generator.seen_context

    def test_every_reply_carries_the_disclaimer(self):
        for kind in ("regulation", "conversation", "out_of_scope"):
            result = _service(generator=_StubGenerator(kind, "text")).ask("anything")
            assert result["disclaimer"] == legal.DISCLAIMER


class TestEnvelopeParsing:
    def test_a_clean_envelope_parses(self):
        assert _parse_envelope('{"kind": "conversation", "answer": "hi"}') == (
            "conversation",
            "hi",
        )

    def test_an_envelope_wrapped_in_a_code_fence_parses(self):
        raw = 'Here you go:\n```json\n{"kind": "out_of_scope", "answer": "no"}\n```'
        assert _parse_envelope(raw) == ("out_of_scope", "no")

    def test_prose_falls_back_to_the_strictest_kind(self):
        """Failing to the grounded path is the safe direction."""
        assert _parse_envelope("Rule 6 requires a price.") == (
            "regulation",
            "Rule 6 requires a price.",
        )

    def test_an_unknown_kind_falls_back(self):
        kind, _ = _parse_envelope('{"kind": "banana", "answer": "x"}')
        assert kind == "regulation"

    def test_an_empty_answer_falls_back(self):
        kind, answer = _parse_envelope('{"kind": "conversation", "answer": ""}')
        assert kind == "regulation"
        assert answer


class TestFollowUpRetrieval:
    """A follow-up carries its subject in the previous turn."""

    def test_no_history_leaves_the_query_alone(self):
        assert _retrieval_query("net quantity", None) == "net quantity"
        assert _retrieval_query("net quantity", []) == "net quantity"

    def test_recent_user_turns_are_appended(self):
        history = [
            {"role": "user", "content": "what is the retail sale price rule"},
            {"role": "assistant", "content": "Rule 6(1)(e)."},
        ]
        expanded = _retrieval_query("and for imports?", history)
        assert expanded.startswith("and for imports?"), "the live question leads"
        assert "retail sale price" in expanded

    def test_assistant_turns_are_not_searched(self):
        """Searching our own prose would retrieve what we already said."""
        history = [{"role": "assistant", "content": "zzzunique"}]
        assert _retrieval_query("q", history) == "q"

    def test_only_the_most_recent_turns_are_used(self):
        history = [
            {"role": "user", "content": "oldest"},
            {"role": "user", "content": "middle"},
            {"role": "user", "content": "newest"},
        ]
        expanded = _retrieval_query("now", history)
        assert "oldest" not in expanded
        assert "middle" in expanded and "newest" in expanded

    def test_blank_turns_are_skipped(self):
        history = [{"role": "user", "content": "   "}]
        assert _retrieval_query("q", history) == "q"

    def test_the_expanded_query_is_what_gets_searched(self):
        class _Recording(_StubRetriever):
            def search(self, query, **kwargs):
                self.seen = query
                return super().search(query, **kwargs)

        retriever = _Recording()
        RegulationRAGService(
            retriever=retriever, generator=_GroqGenerator(api_key=None)
        ).ask(
            "and for imports?",
            history=[{"role": "user", "content": "retail sale price"}],
        )
        assert "retail sale price" in retriever.seen
