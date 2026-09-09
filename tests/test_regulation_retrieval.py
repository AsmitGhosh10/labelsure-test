"""Regulatory retrieval (PRD §8)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend.app.services.regulation_retrieval import (
    RegulationChunk,
    RegulationRetriever,
    cosine,
    get_retriever,
    ngram_vector,
    tokenize,
)


@pytest.fixture(scope="module")
def retriever():
    return RegulationRetriever()


class TestCorpus:
    def test_corpus_loads_every_rule(self, retriever):
        assert len(retriever.chunks) >= 31
        assert not retriever.load_errors

    def test_every_chunk_carries_a_citable_source(self, retriever):
        """PRD §7: a rule without document + page cannot be cited."""
        for chunk in retriever.chunks:
            citation = chunk.citation()
            assert citation["document"], chunk.chunk_id
            assert citation["rule"], chunk.chunk_id
            assert citation["page"] is not None, chunk.chunk_id
            assert citation["quote"], chunk.chunk_id

    def test_effective_date_is_preserved(self, retriever):
        assert all(c.effective_date is not None for c in retriever.chunks)

    def test_stats_report_the_corpus_honestly(self, retriever):
        stats = retriever.stats()
        assert stats["chunks"] >= 31
        assert stats["with_page_numbers"] >= 31
        assert "ruleset" in stats["source_types"]


class TestRetrieval:
    def test_statutory_wording_retrieves_the_right_rule(self, retriever):
        hits = retriever.search("retail sale price inclusive of all taxes", top_k=5)
        assert hits
        assert any("6(1)(e)" in h["rule_reference"] for h in hits)

    def test_net_quantity_query(self, retriever):
        hits = retriever.search("net quantity declaration standard units", top_k=3)
        assert "6(1)(c)" in hits[0]["rule_reference"]

    def test_results_are_ranked_descending(self, retriever):
        hits = retriever.search("manufacturer name and address", top_k=5)
        scores = [h["score"] for h in hits]
        assert scores == sorted(scores, reverse=True)

    def test_metadata_filter_by_rule_reference(self, retriever):
        hits = retriever.search("declaration", rule_reference="Rule 6", top_k=10)
        assert hits
        assert all("rule 6" in h["rule_reference"].lower() for h in hits)

    def test_metadata_filter_with_no_matches_returns_empty(self, retriever):
        assert retriever.search("declaration", category="not_a_category") == []

    def test_empty_query_returns_nothing(self, retriever):
        assert retriever.search("") == []

    def test_exact_rule_id_lookup(self, retriever):
        citation = retriever.citation_for_rule("PC2011-R04-001")
        assert citation["rule"] == "Rule 4"
        assert citation["page"] == 42

    def test_unknown_rule_id_returns_none(self, retriever):
        assert retriever.citation_for_rule("NOT-A-RULE") is None

    def test_retrieval_is_deterministic(self):
        """Two independent retrievers must rank identically - the hashed
        vectors may not depend on process-random hashing."""
        a = RegulationRetriever().search("mrp declaration", top_k=5)
        b = RegulationRetriever().search("mrp declaration", top_k=5)
        assert [h["chunk_id"] for h in a] == [h["chunk_id"] for h in b]
        assert [h["score"] for h in a] == [h["score"] for h in b]

    def test_vector_similarity_tolerates_ocr_noise(self):
        """Character n-grams must survive a mangled word."""
        clean = ngram_vector("net quantity declaration")
        noisy = ngram_vector("net quantlty declaratlon")
        unrelated = ngram_vector("advertisement of packaged commodities")
        assert cosine(clean, noisy) > cosine(clean, unrelated)

    def test_tokenizer_strips_stopwords(self):
        assert "the" not in tokenize("the net quantity of the package")
        assert "quantity" in tokenize("the net quantity of the package")


class TestCiteFindings:
    def test_only_actionable_findings_are_cited(self, retriever):
        rules = [
            {"rule_id": "PC2011-R04-001", "status": "PASS"},
            {"rule_id": "PC2011-R06-C-001", "status": "FAIL"},
            {"rule_id": "PC2011-R24-001", "status": "NOT_APPLICABLE"},
            {"rule_id": "PC2011-R06-E-001", "status": "MANUAL_REVIEW"},
        ]
        cited = retriever.cite_findings(rules)
        assert {c["rule_id"] for c in cited} == {
            "PC2011-R06-C-001",
            "PC2011-R06-E-001",
        }

    def test_citation_carries_page_and_verbatim_quote(self, retriever):
        cited = retriever.cite_findings(
            [{"rule_id": "PC2011-R06-C-001", "status": "FAIL"}]
        )
        citation = cited[0]["citations"][0]
        assert cited[0]["retrieval"] == "exact_rule_id"
        assert citation["page"]
        assert citation["quote"]

    def test_unknown_rule_falls_back_to_search(self, retriever):
        cited = retriever.cite_findings(
            [
                {
                    "rule_id": "AMENDMENT-999",
                    "status": "FAIL",
                    "requirement": "The package shall declare the net quantity",
                    "reason": "net quantity not declared",
                }
            ]
        )
        assert cited[0]["retrieval"] == "hybrid_search"
        assert cited[0]["citations"]

    def test_no_match_says_manual_verification_required(self):
        """PRD §33: a retrieval miss must never look like 'no rule applies'."""
        empty = RegulationRetriever(chunks=[])
        cited = empty.cite_findings(
            [{"rule_id": "X", "status": "FAIL", "requirement": "anything"}]
        )
        assert cited[0]["retrieval"] == "no_match"
        assert "manual verification required" in cited[0]["note"].lower()


class TestCorpusIngestion:
    def test_amendment_json_is_ingested_with_its_metadata(self, tmp_path):
        (tmp_path / "amendment.json").write_text(
            json.dumps(
                {
                    "document": "LM(PC) Amendment Rules, 2022",
                    "effective_date": "2022-10-01",
                    "url": "https://example.gov/amendment",
                    "clauses": [
                        {
                            "id": "AMD-2022-01",
                            "rule_reference": "Rule 6(1)(e)",
                            "title": "Unit sale price",
                            "text": "Every package shall declare the unit sale price.",
                            "page": 3,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        retriever = RegulationRetriever(corpus_dir=str(tmp_path))
        amendment = [c for c in retriever.chunks if c.source_type == "amendment"]
        assert len(amendment) == 1
        citation = amendment[0].citation()
        assert citation["effective_date"] == "2022-10-01"
        assert citation["page"] == 3
        assert citation["url"] == "https://example.gov/amendment"

    def test_text_document_page_markers_are_preserved(self, tmp_path):
        (tmp_path / "notification.txt").write_text(
            "[p. 12]\nRule 9. Declarations shall be legible.\n\n"
            "Rule 10. The package shall bear the name of the packer.\n",
            encoding="utf-8",
        )
        retriever = RegulationRetriever(corpus_dir=str(tmp_path))
        docs = [c for c in retriever.chunks if c.source_type == "document"]
        assert len(docs) == 2
        assert docs[0].page == 12
        assert docs[0].rule_reference.lower().startswith("rule 9")

    def test_missing_corpus_dir_is_not_an_error(self, tmp_path):
        retriever = RegulationRetriever(corpus_dir=str(tmp_path / "nope"))
        assert len(retriever.chunks) == 31
        assert not retriever.load_errors

    def test_missing_ruleset_degrades_instead_of_crashing(self, tmp_path):
        retriever = RegulationRetriever(
            rules_path=str(tmp_path / "absent.json"), corpus_dir=str(tmp_path / "empty")
        )
        assert retriever.chunks == []
        assert retriever.load_errors
        assert retriever.search("anything") == []


class TestCorpusIngestionAmendments:
    def test_loads_corpus_directory_amendments(self):
        retriever = RegulationRetriever()
        assert len(retriever.chunks) > 31
        amendment_chunks = [c for c in retriever.chunks if c.source_type != "ruleset"]
        assert len(amendment_chunks) >= 6
        assert any("E-Commerce" in c.title for c in amendment_chunks)
        assert any("Unit Sale Price" in c.title for c in amendment_chunks)


class TestVectorizerSeam:
    def test_a_custom_vectorizer_can_be_swapped_in(self, retriever):
        """The embedding backend is replaceable without touching callers."""
        calls = []

        def fake_vectorizer(text):
            calls.append(text)
            return ngram_vector(text, dim=64)

        r = RegulationRetriever(
            chunks=[
                RegulationChunk(
                    chunk_id="X",
                    document="D",
                    rule_reference="Rule 1",
                    title="t",
                    category="c",
                    text="net quantity declaration",
                )
            ]
        )
        r.set_vectorizer(fake_vectorizer)
        assert calls  # re-indexed through the new backend
        assert r.search("net quantity")


def test_module_level_singleton_is_shared():
    assert get_retriever() is get_retriever()
