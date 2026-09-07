import os
import time
import uuid
from typing import Dict, Any, List, Optional

from backend.app.services.quality_gate import ImageQualityGate
from backend.app.services.field_extraction import FieldExtractor, ExtractedField
from backend.app.services.rule_engine import RuleEngine, RuleResult
from backend.app.services.labelguard_engine import LabelGuardEngine
from backend.app.services.confidence import ConfidenceEngine, ConfidenceResult, DECISION_EMOJI
from backend.app.services.evidence import EvidencePipeline
from backend.app.services.review_actions import build_review_actions
from backend.app.services.compliance_score import compute_compliance_score
from backend.app.services.product_category import classify_product, scope_rules
from backend.app.services.regulation_retrieval import get_retriever
from backend.app.services.report_generator import FIELD_LABELS
from backend.app.services import annotate as annotate_service
from backend.app.services import legal
from backend.app.services import ocr_service

# Frozen response schema version (see tests/test_schema_freeze.py).
#
# 1.0 -> 1.1 (additive only, no key removed or retyped): adds
#   compliance_score, product_category, regulation_citations,
#   annotated_images, disclaimer.
# A 1.0 consumer keeps working - every 1.0 key is still present with the
# same meaning.
RESPONSE_SCHEMA = "labelguard-inspection/1.1"

FIELD_NAMES = [
    "mrp",
    "product_name",
    "brand",
    "net_quantity",
    "manufacturer",
    "packer",
    "importer",
    "manufacturing_date",
    "packing_date",
    "best_before",
    "batch_number",
    "consumer_care",
    "country_of_origin",
]

MAX_SURFACES = 6


class InspectionPipeline:
    """Full inspection flow: quality gate -> OCR -> field extraction -> rules ->
    confidence fusion -> decision."""

    def __init__(
        self,
        rules_path: Optional[str] = None,
        engine: str = "labelguard",
        evidence_dir: str = "reports/inspections/evidence",
        annotate: bool = True,
    ):
        self.quality_gate = ImageQualityGate()
        self.evidence_dir = evidence_dir
        self.annotate = annotate
        self.field_extractor = FieldExtractor()
        if engine == "legacy":
            self.rule_engine = RuleEngine(rules_path=rules_path)
        else:
            self.rule_engine = LabelGuardEngine(rules_path=rules_path)
        self.confidence_engine = ConfidenceEngine()
        self.evidence_pipeline = EvidencePipeline()

    def _ruleset_info(self) -> Dict[str, Any]:
        meta = getattr(self.rule_engine, "meta", None) or {}
        if meta:
            src = meta.get("source_document", {}) or {}
            return {
                "id": meta.get("name", "labelguard"),
                "version": meta.get("schema_version", ""),
                "verified": bool(getattr(self.rule_engine, "ruleset_verified", False)),
                "enforce_verification": bool(
                    getattr(self.rule_engine, "enforce_verification", False)
                ),
                "legal_status": src.get("legal_status", ""),
                "source_title": src.get("title", ""),
            }
        legacy = getattr(self.rule_engine, "ruleset_meta", {}) or {}
        return {
            "id": legacy.get("ruleset_id", "custom"),
            "version": legacy.get("version", ""),
            "verified": bool(getattr(self.rule_engine, "ruleset_verified", False)),
            "enforce_verification": bool(
                getattr(self.rule_engine, "enforce_verification", False)
            ),
        }

    # ------------------------------------------------------------------
    # Steps (exposed individually for the API)
    # ------------------------------------------------------------------

    def assess_quality(self, image_path: str) -> Dict[str, Any]:
        return self.quality_gate.assess(image_path)

    def ocr(self, image_path: str) -> Dict[str, Any]:
        return ocr_service.run_ocr(image_path)

    def extract_fields(
        self, texts, confidences, bounding_boxes
    ) -> Dict[str, ExtractedField]:
        return self.field_extractor.extract_all(texts, confidences, bounding_boxes)

    def evaluate_rules(
        self,
        extracted_fields: Dict[str, Any],
        image_quality: Optional[Dict[str, Any]] = None,
        pointers: Optional[List[Dict[str, Any]]] = None,
    ):
        rule_results = self.rule_engine.evaluate(
            extracted_fields, image_quality, pointers=pointers
        )
        decision = self.rule_engine.fuse(rule_results)
        return rule_results, decision

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def run(self, image_path: str, image_name: Optional[str] = None) -> Dict[str, Any]:
        started = time.time()
        inspection_id = str(uuid.uuid4())

        result: Dict[str, Any] = {
            "inspection_id": inspection_id,
            "image": image_name or image_path,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ruleset": self._ruleset_info(),
            "quality": None,
            "ocr": None,
            "extracted_fields": {},
            "rule_results": [],
            "compliance_decision": None,
            "confidence": None,
            "decision": None,
            "processing_time_sec": None,
        }

        # Step 1: quality gate
        quality = self.assess_quality(image_path)
        result["quality"] = quality

        if not quality.get("usable", False):
            result["decision"] = "MANUAL_REVIEW"
            result["decision_reasons"] = [
                f"Image quality below usable threshold (score {quality.get('score', 0):.0f}/100) - "
                "compliance cannot be assessed automatically"
            ]
            result["decision_emoji"] = DECISION_EMOJI["MANUAL_REVIEW"]
            result["processing_time_sec"] = round(time.time() - started, 2)
            return result

        # Step 2: OCR
        ocr_result = self.ocr(image_path)
        result["ocr"] = {
            "avg_confidence": ocr_result["avg_confidence"],
            "num_lines": len(ocr_result["texts"]),
            "texts": ocr_result["texts"],
            "confidences": ocr_result["confidences"],
            "bounding_boxes": ocr_result["bounding_boxes"],
        }

        # Step 3: field extraction
        fields = self.extract_fields(
            ocr_result["texts"], ocr_result["confidences"], ocr_result["bounding_boxes"]
        )
        serializable_fields = {}
        for key, f in fields.items():
            serializable_fields[key] = {
                "field_name": f.field_name,
                "value": f.value,
                "ocr_text": f.ocr_text,
                "ocr_confidence": f.ocr_confidence,
                "extraction_confidence": f.extraction_confidence,
                "confidence_level": f.confidence_level,
                "bbox": f.bbox,
                "reason": f.reason,
                "line_index": f.line_index,
            }
        result["extracted_fields"] = serializable_fields

        if ocr_result["avg_confidence"] == 0.0 or not ocr_result["texts"]:
            result["decision"] = "MANUAL_REVIEW"
            result["decision_reasons"] = ["No text detected by OCR - cannot assess compliance"]
            result["decision_emoji"] = DECISION_EMOJI["MANUAL_REVIEW"]
            result["processing_time_sec"] = round(time.time() - started, 2)
            return result

        # Step 4: rule evaluation
        rule_results, compliance = self.evaluate_rules(serializable_fields, quality)
        result["rule_results"] = [r.to_dict() if isinstance(r, RuleResult) else r for r in rule_results]
        result["compliance_decision"] = compliance.to_dict()

        # Step 5: confidence fusion
        confidence: ConfidenceResult = self.confidence_engine.compute(
            ocr_result, serializable_fields, quality, rule_results
        )
        confidence = self.confidence_engine.fuse_decision(confidence, compliance)

        result["confidence"] = confidence.to_dict()
        result["decision"] = confidence.decision
        result["decision_reasons"] = confidence.decision_reasons
        result["decision_downgraded_from"] = confidence.downgraded_from
        result["decision_emoji"] = DECISION_EMOJI.get(confidence.decision, "🟡")
        result["processing_time_sec"] = round(time.time() - started, 2)
        return result

    # ------------------------------------------------------------------
    # Multi-image inspection (one package, several captured surfaces)
    # ------------------------------------------------------------------

    def run_multi(
        self,
        image_paths: List[str],
        image_names: Optional[List[str]] = None,
        product_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Inspect one package from 1..MAX_SURFACES captured surfaces.

        Fields are merged across surfaces (best-confidence detection wins and
        remembers its source image). Absence-based FAIL fires only when the
        field is missing on every surface AND every surface is usable - any
        unreadable surface routes absence findings to MANUAL_REVIEW.
        """
        started = time.time()
        inspection_id = str(uuid.uuid4())
        n = len(image_paths)
        if n == 0:
            raise ValueError("At least one image is required")
        if n > MAX_SURFACES:
            raise ValueError(f"At most {MAX_SURFACES} surfaces supported, got {n}")
        names = list(image_names) if image_names else [os.path.basename(p) for p in image_paths]

        per_image = []
        for idx, path in enumerate(image_paths):
            quality = self.assess_quality(path)
            gate_usable = bool(quality.get("usable", False))
            entry = {
                "idx": idx,
                "name": names[idx],
                "gate_usable": gate_usable,
                "usable": gate_usable,
                "usability_basis": "quality_gate" if gate_usable else "none",
                "quality": quality,
                "ocr": None,
                "ocr_error": None,
                "fields": {},
            }
            # Always run OCR: readable evidence must never be wasted just
            # because a synthetic blur metric disagreed with reality.
            try:
                ocr_result = self.ocr(path)
            except Exception as exc:
                # An engine that cannot run is a deployment fault, not an
                # unreadable photograph. Keep the distinction: telling an
                # inspector to recapture a perfectly good pack because
                # PaddleOCR is missing wastes their time and hides the bug.
                ocr_result = None
                entry["ocr_error"] = f"{type(exc).__name__}: {exc}"[:300]
            if ocr_result and ocr_result["texts"]:
                entry["ocr"] = ocr_result
                ocr_readable = (
                    len(ocr_result["texts"]) >= 2
                    and float(ocr_result["avg_confidence"]) >= 0.90
                )
                if ocr_readable and not gate_usable:
                    # OCR evidence overrides the quality gate: the surface is
                    # readable, so its text is trustworthy evidence
                    entry["usable"] = True
                    entry["usability_basis"] = "ocr_evidence"
                if entry["usable"]:
                    fields = self.extract_fields(
                        ocr_result["texts"],
                        ocr_result["confidences"],
                        ocr_result["bounding_boxes"],
                    )
                    entry["fields"] = {
                        key: {
                            "field_name": f.field_name,
                            "value": f.value,
                            "ocr_text": f.ocr_text,
                            "ocr_confidence": f.ocr_confidence,
                            "extraction_confidence": f.extraction_confidence,
                            "confidence_level": f.confidence_level,
                            "bbox": f.bbox,
                            "reason": f.reason,
                            "line_index": f.line_index,
                        }
                        for key, f in fields.items()
                    }
            per_image.append(entry)

        result: Dict[str, Any] = {
            "inspection_id": inspection_id,
            "response_schema": RESPONSE_SCHEMA,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "product_name": product_name,
            "ruleset": self._ruleset_info(),
            "images": [
                {
                    "index": e["idx"],
                    "name": e["name"],
                    "usable": e["usable"],
                    "gate_usable": e["gate_usable"],
                    "usability_basis": e["usability_basis"],
                    "quality": e["quality"],
                    "ocr_avg_confidence": (
                        e["ocr"]["avg_confidence"] if e["ocr"] else None
                    ),
                    "num_lines": len(e["ocr"]["texts"]) if e["ocr"] else 0,
                    "ocr_error": e["ocr_error"],
                }
                for e in per_image
            ],
            "coverage": {
                 "surfaces_total": n,
                 "surfaces_usable": sum(1 for e in per_image if e["usable"]),
             },
            "extracted_fields": {},
            "reference_pointers": [],
            "unclaimed_evidence": [],
            "evidence_pool_size": 0,
            "cylindrical_package": False,
            "rule_results": [],
            "compliance_decision": None,
            "confidence": None,
            "decision": None,
            "decision_reasons": None,
            "decision_downgraded_from": None,
            "decision_emoji": None,
            "review_actions": [],
            "compliance_score": None,
            "product_category": None,
            "regulation_citations": [],
            "annotated_images": [],
            "disclaimer": {
                "system_role": legal.SYSTEM_ROLE,
                "text": legal.DISCLAIMER,
                "short": legal.SHORT_DISCLAIMER,
            },
            "processing_time_sec": None,
        }

        ocr_errors = [e for e in per_image if e["ocr_error"]]

        usable = [e for e in per_image if e["usable"]]
        if not usable:
            if len(ocr_errors) == n:
                # Every surface failed for the same reason: the engine.
                reasons = [
                    "The OCR engine could not run, so no text could be read from "
                    "any surface. This is a system fault, not an image problem - "
                    "recapturing the package will not help.",
                    f"Error on '{ocr_errors[0]['name']}': {ocr_errors[0]['ocr_error']}",
                ]
            else:
                reasons = [
                    "No usable image of the package - compliance cannot be "
                    "assessed automatically"
                ]
                if ocr_errors:
                    reasons.append(
                        f"{len(ocr_errors)} surface(s) also failed OCR with a "
                        f"system error: {ocr_errors[0]['ocr_error']}"
                    )
            result["decision"] = "MANUAL_REVIEW"
            result["decision_reasons"] = reasons
            result["decision_emoji"] = DECISION_EMOJI["MANUAL_REVIEW"]
            result["processing_time_sec"] = round(time.time() - started, 2)
            return result

        merged_ocr = self._merged_ocr(usable)
        if not merged_ocr["texts"]:
            reasons = [
                "No text detected on any captured surface - cannot assess compliance"
            ]
            if len(ocr_errors) == n:
                reasons = [
                    "The OCR engine could not run, so no text could be read "
                    "from any surface. This is a system fault, not an image "
                    "problem - recapturing the package will not help.",
                    f"Error on '{ocr_errors[0]['name']}': "
                    f"{ocr_errors[0]['ocr_error']}",
                ]
            elif ocr_errors:
                reasons.append(
                    "The OCR engine failed on "
                    f"{len(ocr_errors)} of {n} surface(s) - this is a system "
                    f"fault, not an image problem: {ocr_errors[0]['ocr_error']}"
                )
            result["decision"] = "MANUAL_REVIEW"
            result["decision_reasons"] = reasons
            result["decision_emoji"] = DECISION_EMOJI["MANUAL_REVIEW"]
            result["processing_time_sec"] = round(time.time() - started, 2)
            return result

        # Evidence-preserving merge: pool every OCR element from every surface,
        # merge labelled detections, associate unlabelled candidates across
        # surfaces/pointers, retain everything else as unclaimed evidence.
        # Rules run ONLY after all available evidence has been merged.
        evidence = self.evidence_pipeline.run(per_image)
        merged_fields = evidence["fields"]
        result["extracted_fields"] = merged_fields
        result["reference_pointers"] = evidence["pointers"]
        result["unclaimed_evidence"] = evidence["unclaimed_evidence"]
        result["evidence_pool_size"] = evidence["pool_size"]
        result["cylindrical_package"] = evidence["cylindrical_package"]

        merged_quality = self._merged_quality(per_image)
        rule_results, compliance = self.evaluate_rules(
            merged_fields, merged_quality, pointers=evidence["pointers"]
        )
        result["rule_results"] = [
            r.to_dict() if isinstance(r, RuleResult) else r for r in rule_results
        ]
        result["compliance_decision"] = compliance.to_dict()

        confidence: ConfidenceResult = self.confidence_engine.compute(
            merged_ocr, merged_fields, merged_quality, rule_results
        )
        confidence = self.confidence_engine.fuse_decision(confidence, compliance)

        result["confidence"] = confidence.to_dict()
        result["decision"] = confidence.decision
        result["decision_reasons"] = confidence.decision_reasons
        result["decision_downgraded_from"] = confidence.downgraded_from
        result["decision_emoji"] = DECISION_EMOJI.get(confidence.decision, "🟡")

        # Targeted review actions (post-processing only - rules/OCR untouched)
        result["review_actions"] = build_review_actions(
            rule_results,
            merged_fields,
            evidence["pointers"],
            result["images"],
            confidence.overall,
        )

        # Compliance score (PRD 26): 0-100 with a per-category breakdown
        result["compliance_score"] = compute_compliance_score(result["rule_results"])

        # Commodity classification (PRD 23): advisory scoping only - it never
        # changes a rule verdict
        category = classify_product(
            merged_fields, merged_ocr.get("texts"), product_name
        )
        category["rule_scope"] = scope_rules(
            result["rule_results"], category["category"]
        )
        result["product_category"] = category

        # Regulation citations (PRD 8): every FAIL/MANUAL_REVIEW finding is
        # traced back to document + rule + page + verbatim quote
        try:
            result["regulation_citations"] = get_retriever().cite_findings(
                result["rule_results"]
            )
        except Exception as exc:  # retrieval must never fail an inspection
            result["regulation_citations"] = [
                {
                    "rule_id": None,
                    "status": "MANUAL_REVIEW",
                    "retrieval": "error",
                    "citations": [],
                    "note": (
                        f"Regulation retrieval unavailable ({exc}) - manual "
                        "verification required"
                    ),
                }
            ]

        # Visual evidence (PRD 20): highlighted regions on the actual photos
        if self.annotate:
            try:
                result["annotated_images"] = annotate_service.annotate_images(
                    image_paths,
                    names,
                    merged_fields,
                    result["rule_results"],
                    output_dir=self.evidence_dir,
                    field_labels=FIELD_LABELS,
                    inspection_id=inspection_id,
                )
            except Exception:
                result["annotated_images"] = []

        result["processing_time_sec"] = round(time.time() - started, 2)
        return result

    # ------------------------------------------------------------------
    # Merge helpers (pure logic, unit-testable)
    # ------------------------------------------------------------------

    def _merge_fields(self, per_image: List[Dict[str, Any]]) -> Dict[str, Any]:
        """For each field, keep the best-confidence detection across surfaces.

        Selection key: (extraction_confidence, ocr_confidence, earlier image).
        The merged field records which surface it came from. Fields found on
        no surface keep a MISSING stub with source_image None.
        """
        merged = {}
        for name in FIELD_NAMES:
            best_key = None
            best_field = None
            best_source = None
            for e in per_image:
                f = e["fields"].get(name)
                if not f or f.get("value") is None:
                    continue
                key = (
                    float(f.get("extraction_confidence", 0.0)),
                    float(f.get("ocr_confidence", 0.0)),
                    -e["idx"],
                )
                if best_key is None or key > best_key:
                    best_key = key
                    best_field = dict(f)
                    best_source = e["name"]
            if best_field is not None:
                best_field["source_image"] = best_source
                merged[name] = best_field
            else:
                stub_source = next((e for e in per_image if e["fields"]), None)
                stub = (
                    dict(stub_source["fields"].get(name, {}))
                    if stub_source
                    else {}
                )
                stub.setdefault("field_name", name)
                stub.setdefault("value", None)
                stub.setdefault("ocr_text", "")
                stub.setdefault("ocr_confidence", 0.0)
                stub.setdefault("extraction_confidence", 0.0)
                stub.setdefault("confidence_level", "MISSING")
                stub.setdefault("bbox", [])
                stub.setdefault("reason", "Not found on any captured surface")
                stub.setdefault("line_index", -1)
                stub["source_image"] = None
                merged[name] = stub
        return merged

    @staticmethod
    def _merged_quality(per_image: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merged quality context for the rule engine.

        usable = every surface usable (one blurry surface makes absence
        untrustworthy). score = mean across surfaces (confidence signal).
        """
        usable_flags = [bool(e.get("usable")) for e in per_image]
        scores = [
            float(e.get("quality", {}).get("score", 0.0)) for e in per_image
        ]
        return {
            "usable": all(usable_flags),
            "score": sum(scores) / len(scores) if scores else 0.0,
            "multi_surface": True,
            "surfaces_total": len(per_image),
            "surfaces_usable": sum(1 for u in usable_flags if u),
            "per_surface": [
                {
                    "name": e.get("name"),
                    "usable": bool(e.get("usable")),
                    "score": float(e.get("quality", {}).get("score", 0.0)),
                }
                for e in per_image
            ],
        }

    @staticmethod
    def _merged_ocr(usable_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Line-count-weighted OCR confidence across usable surfaces."""
        total_lines = sum(len(e["ocr"]["texts"]) for e in usable_entries if e["ocr"])
        if total_lines == 0:
            return {"avg_confidence": 0.0, "texts": []}
        weighted = (
            sum(
                e["ocr"]["avg_confidence"] * len(e["ocr"]["texts"])
                for e in usable_entries
                if e["ocr"]
            )
            / total_lines
        )
        texts = []
        for e in usable_entries:
            if e["ocr"]:
                texts.extend(e["ocr"]["texts"])
        return {"avg_confidence": weighted, "texts": texts}
