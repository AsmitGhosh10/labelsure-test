"""Compliance score (PRD §26).

Turns the rule results into a 0-100 score with a per-category breakdown, so
an inspector sees *how far* a package is from compliant rather than only a
three-state verdict.

Design constraints (PRD §36 - traceability, no fabricated certainty):

- Deterministic: same rule results in, same score out. No model, no tuning
  against a hidden dataset.
- Only rules the engine could actually evaluate are scored. NOT_APPLICABLE
  and UNVERIFIED rules are counted and reported, never silently folded into
  the denominator - a package must not look better because most rules were
  out of scope.
- MANUAL_REVIEW scores half credit: unresolved is neither a pass nor a
  violation.
- The score is a screening aid. It never overrides the verdict and it never
  substitutes for statutory inspection (see backend.app.services.legal).
"""

from typing import Any, Dict, List

from backend.app.services.legal import DISCLAIMER, SYSTEM_ROLE

PASS = "PASS"
FAIL = "FAIL"
MANUAL_REVIEW = "MANUAL_REVIEW"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNVERIFIED = "UNVERIFIED"

# Rule category (from the ruleset JSON) -> PRD §26 reporting bucket
CATEGORY_BUCKETS: Dict[str, str] = {
    # Mandatory declarations - the information that must be on the package
    "package_declarations": "mandatory_declarations",
    "manufacturer_details": "mandatory_declarations",
    "commodity_identity": "mandatory_declarations",
    "net_quantity": "mandatory_declarations",
    "date_declaration": "mandatory_declarations",
    "mrp": "mandatory_declarations",
    "consumer_contact": "mandatory_declarations",
    "container_declaration": "mandatory_declarations",
    "count_declaration": "mandatory_declarations",
    "multi_component_package": "mandatory_declarations",
    "outer_wrapper": "mandatory_declarations",
    "quantity_definition": "mandatory_declarations",
    # Formatting - how a present declaration must be expressed
    "quantity_unit": "formatting",
    "unit_format": "formatting",
    "quantity_language": "formatting",
    "quantity_dimensions": "formatting",
    "language": "formatting",
    "sticker_compliance": "formatting",
    "standard_pack_size": "formatting",
    "dimensions": "formatting",
    # Readability - legibility, size and placement on the package
    "display_legibility": "readability",
    "declaration_location": "readability",
    "declaration_legibility": "readability",
    "declaration_readability": "readability",
    # Not a property of the label itself
    "dealer_sale": "other",
    "wholesale_package": "other",
    "export_package": "other",
    "exemptions": "other",
    "advertisement": "other",
}

BUCKET_LABELS = {
    "mandatory_declarations": "Mandatory declarations",
    "formatting": "Formatting of declarations",
    "readability": "Readability & placement",
    "other": "Other / contextual rules",
}

BUCKET_ORDER = ["mandatory_declarations", "formatting", "readability", "other"]

SEVERITY_WEIGHTS = {"CRITICAL": 3.0, "HIGH": 2.0, "MEDIUM": 1.5, "LOW": 1.0}
DEFAULT_SEVERITY_WEIGHT = 1.0

# Credit awarded per status (of the rule's severity weight)
STATUS_CREDIT = {PASS: 1.0, MANUAL_REVIEW: 0.5, FAIL: 0.0}

SCORED_STATUSES = set(STATUS_CREDIT)

GRADE_BANDS = [
    (90.0, "A", "Substantially compliant on the declarations that could be screened"),
    (75.0, "B", "Minor declaration gaps found"),
    (60.0, "C", "Several declaration gaps found"),
    (40.0, "D", "Major declaration gaps found"),
    (0.0, "E", "Critical declaration gaps found"),
]


def _bucket_for(rule: Dict[str, Any]) -> str:
    category = (rule.get("source") or {}).get("category") or ""
    return CATEGORY_BUCKETS.get(category, "other")


def _weight(rule: Dict[str, Any]) -> float:
    return SEVERITY_WEIGHTS.get(
        str(rule.get("severity", "")).upper(), DEFAULT_SEVERITY_WEIGHT
    )


def _grade(score: float) -> Dict[str, str]:
    for floor, letter, meaning in GRADE_BANDS:
        if score >= floor:
            return {"grade": letter, "meaning": meaning}
    return {"grade": "E", "meaning": GRADE_BANDS[-1][2]}


def compute_compliance_score(rule_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score the rule results 0-100 with a per-category breakdown.

    Returns ``{"score", "grade", "grade_meaning", "scored_rules",
    "not_assessable", "categories": [...], "counts": {...}, "disclaimer"}``.
    ``score`` is ``None`` when no rule could be evaluated at all - a package
    with nothing assessable gets no number, not a zero.
    """
    buckets: Dict[str, Dict[str, Any]] = {
        name: {
            "bucket": name,
            "label": BUCKET_LABELS[name],
            "earned": 0.0,
            "possible": 0.0,
            "pass": 0,
            "fail": 0,
            "manual_review": 0,
            "not_assessable": 0,
        }
        for name in BUCKET_ORDER
    }

    counts = {PASS: 0, FAIL: 0, MANUAL_REVIEW: 0, NOT_APPLICABLE: 0, UNVERIFIED: 0}

    for rule in rule_results or []:
        status = rule.get("status", "")
        bucket = buckets[_bucket_for(rule)]
        if status in counts:
            counts[status] += 1
        if status not in SCORED_STATUSES:
            bucket["not_assessable"] += 1
            continue
        weight = _weight(rule)
        bucket["possible"] += weight
        bucket["earned"] += weight * STATUS_CREDIT[status]
        bucket[status.lower()] += 1

    total_possible = sum(b["possible"] for b in buckets.values())
    total_earned = sum(b["earned"] for b in buckets.values())

    categories = []
    for name in BUCKET_ORDER:
        b = buckets[name]
        scored = b["pass"] + b["fail"] + b["manual_review"]
        categories.append(
            {
                "bucket": name,
                "label": b["label"],
                "score": (
                    round(100.0 * b["earned"] / b["possible"], 1)
                    if b["possible"] > 0
                    else None
                ),
                "rules_scored": scored,
                "pass": b["pass"],
                "fail": b["fail"],
                "manual_review": b["manual_review"],
                "not_assessable": b["not_assessable"],
            }
        )

    score = round(100.0 * total_earned / total_possible, 1) if total_possible > 0 else None
    grade = _grade(score) if score is not None else {"grade": "—", "meaning": "Nothing assessable from the captured imagery"}

    return {
        "score": score,
        "max_score": 100,
        "grade": grade["grade"],
        "grade_meaning": grade["meaning"],
        "scored_rules": counts[PASS] + counts[FAIL] + counts[MANUAL_REVIEW],
        "not_assessable": counts[NOT_APPLICABLE] + counts[UNVERIFIED],
        "counts": {
            "pass": counts[PASS],
            "fail": counts[FAIL],
            "manual_review": counts[MANUAL_REVIEW],
            "not_applicable": counts[NOT_APPLICABLE],
            "unverified": counts[UNVERIFIED],
        },
        "categories": categories,
        "basis": (
            "Weighted by rule severity (CRITICAL 3, HIGH 2, MEDIUM 1.5, LOW 1). "
            "PASS scores full credit, MANUAL REVIEW half, FAIL none. Rules that "
            "could not be evaluated from photographs are excluded from the "
            "denominator and reported separately."
        ),
        "system_role": SYSTEM_ROLE,
        "disclaimer": DISCLAIMER,
    }
