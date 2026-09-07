"""Commodity category classification (PRD §23).

Determines the commodity type of the inspected package from the extracted
declarations and the raw OCR text, and reports which conditional rules that
category brings into scope.

Deliberate boundary (PRD §22/§36): classification **never overrides a rule
verdict**. The deterministic engine owns PASS/FAIL/MANUAL_REVIEW. What the
category does is tell the inspector *which* conditional rules are worth a
physical check on this kind of package - a "declaration on each component"
rule matters for a multi-component cosmetics carton and not for a single
sealed can. Turning a category guess into a legal verdict would be exactly
the fabrication the PRD forbids.

Classification is keyword-evidence based and reports the evidence that drove
it, so an inspector can disagree with one glance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

UNKNOWN = "unknown"

# category -> (label, weighted keyword patterns)
CATEGORY_KEYWORDS: Dict[str, Dict[str, Any]] = {
    "food": {
        "label": "Packaged food",
        "strong": [
            r"\bfssai\b", r"\blic\.?\s*no\b.*\d{14}", r"\bnutrition(al)?\s*(information|facts)\b",
            r"\bingredients?\b", r"\bveg\b|\bnon[- ]?veg\b", r"\ballergen",
            r"\benergy\s*\(?k?cal", r"\bbest\s*before\b.*\bconsum",
        ],
        "weak": [
            r"\bsnack|biscuit|namkeen|bhujia|chips|wafer|noodle|pasta|atta|flour",
            r"\bspice|masala|pickle|jam|honey|sauce|ketchup|chocolate|candy",
            r"\brice\b|\bdal\b|\bpulse|\bsugar\b|\bsalt\b|\btea\b|\bcoffee\b",
            r"\bprotein|carbohydrate|saturated\s*fat|trans\s*fat|sodium",
        ],
    },
    "beverage": {
        "label": "Packaged beverage",
        "strong": [
            r"\bcarbonated\b", r"\bpacked?\s*drinking\s*water\b", r"\bmineral\s*water\b",
            r"\bfruit\s*(juice|drink|beverage)\b", r"\bready\s*to\s*(drink|serve)\b",
        ],
        "weak": [
            r"\bjuice\b|\bdrink\b|\bbeverage\b|\bsoda\b|\bcola\b|\bwater\b",
            r"\bserve\s*chilled\b|\bshake\s*well\b|\bnot?\s*added\s*sugar\b",
            r"\b\d+\s*ml\b|\b\d+(\.\d+)?\s*l(itre|tr)?\b",
        ],
    },
    "cosmetic": {
        "label": "Cosmetic / personal care",
        "strong": [
            r"\bfor\s*external\s*use\s*only\b", r"\bcosmetic\b",
            r"\bmfg\.?\s*lic(ence|ense)?\s*no\b", r"\bdrugs?\s*(and|&)\s*cosmetics?\s*act\b",
        ],
        "weak": [
            r"\bshampoo|soap|lotion|cream\b|\bmoisturis|conditioner|deodorant",
            r"\bperfume|talc|face\s*wash|hair\s*oil|toothpaste|sunscreen|spf\b",
        ],
    },
    "drug": {
        "label": "Drug / medicinal product",
        "strong": [
            r"\bschedule\s*h1?\b", r"\bprescription\s*only\b",
            r"\bto\s*be\s*sold\s*by\s*retail\s*on\s*the\s*prescription\b",
            r"\bdrugs?\s*(and|&)\s*cosmetics?\s*rules?\b",
        ],
        "weak": [
            r"\btablet|capsule|syrup|ointment|dosage|mg\b\s*/\s*ml|\bip\b|\bbp\b",
            r"\bstore\s*below\s*\d+\s*c\b|\bkeep\s*out\s*of\s*reach\s*of\s*children\b",
        ],
    },
    "household": {
        "label": "Household / cleaning product",
        "strong": [r"\bnot\s*for\s*human\s*consumption\b", r"\bharmful\s*if\s*swallowed\b"],
        "weak": [
            r"\bdetergent|bleach|disinfect|floor\s*clean|dishwash|toilet\s*clean",
            r"\bphenyl|insecticid|repellent|freshener|polish\b",
        ],
    },
    "textile": {
        "label": "Textile / garment",
        "strong": [r"\bcotton\s*\d{1,3}\s*%", r"\bmachine\s*wash\b", r"\bdo\s*not\s*bleach\b"],
        "weak": [r"\bpolyester|viscose|fabric|garment|size\s*:\s*(s|m|l|xl|xxl)\b"],
    },
    "electrical": {
        "label": "Electrical / electronic goods",
        "strong": [r"\bbis\s*registration\b", r"\be-?waste\b", r"\b\d{2,3}\s*v\s*[~/]\s*\d{2}\s*hz\b"],
        "weak": [r"\bwatt\b|\bvoltage\b|\bwarranty\b|\bmodel\s*no\b|\bserial\s*no\b|\bisi\b"],
    },
}

# Which conditional rules a category brings into scope for a physical check.
# Keyed by ruleset category (rule["category"]) so the map survives rule id
# renumbering. Absence from this map means "always in scope".
CATEGORY_RULE_SCOPE: Dict[str, List[str]] = {
    "multi_component_package": ["cosmetic", "food", "household", "electrical"],
    "container_declaration": ["food", "beverage", "household"],
    "count_declaration": ["food", "household", "electrical", "textile"],
    "quantity_dimensions": ["textile", "household"],
    "dimensions": ["textile", "household", "electrical"],
    "outer_wrapper": ["food", "cosmetic", "electrical"],
    "standard_pack_size": ["food", "beverage", "household"],
}

STRONG_WEIGHT = 3.0
WEAK_WEIGHT = 1.0
# Below this, the category is reported but explicitly marked low confidence
CONFIDENT_SCORE = 3.0


def _text_corpus(
    extracted_fields: Optional[Dict[str, Any]],
    ocr_texts: Optional[Sequence[str]],
    product_name: Optional[str],
) -> str:
    parts: List[str] = []
    if product_name:
        parts.append(product_name)
    for f in (extracted_fields or {}).values():
        if isinstance(f, dict):
            if f.get("value"):
                parts.append(str(f["value"]))
            if f.get("ocr_text"):
                parts.append(str(f["ocr_text"]))
    parts.extend(str(t) for t in (ocr_texts or []))
    return "\n".join(parts).lower()


def classify_product(
    extracted_fields: Optional[Dict[str, Any]] = None,
    ocr_texts: Optional[Sequence[str]] = None,
    product_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Classify the commodity category.

    Returns ``{"category", "label", "confidence", "confident", "evidence",
    "scores", "basis"}``. ``category`` is ``"unknown"`` when nothing matched -
    an unknown category is reported honestly rather than defaulted to food.
    """
    corpus = _text_corpus(extracted_fields, ocr_texts, product_name)
    scores: Dict[str, float] = {}
    evidence: Dict[str, List[str]] = {}

    if corpus.strip():
        for category, spec in CATEGORY_KEYWORDS.items():
            score = 0.0
            hits: List[str] = []
            for pattern in spec["strong"]:
                match = re.search(pattern, corpus, re.IGNORECASE)
                if match:
                    score += STRONG_WEIGHT
                    hits.append(match.group(0).strip())
            for pattern in spec["weak"]:
                match = re.search(pattern, corpus, re.IGNORECASE)
                if match:
                    score += WEAK_WEIGHT
                    hits.append(match.group(0).strip())
            if score > 0:
                scores[category] = score
                evidence[category] = hits[:6]

    if not scores:
        return {
            "category": UNKNOWN,
            "label": "Unknown commodity type",
            "confidence": 0.0,
            "confident": False,
            "evidence": [],
            "scores": {},
            "basis": (
                "No commodity-type keywords found on the captured surfaces - "
                "category not inferred"
            ),
        }

    best = max(scores, key=lambda c: scores[c])
    best_score = scores[best]
    runner_up = max((s for c, s in scores.items() if c != best), default=0.0)
    # Confidence: how decisive the win is, capped - keyword matching is
    # evidence, not certainty.
    margin = (best_score - runner_up) / best_score if best_score else 0.0
    confidence = round(min(0.85, 0.35 + 0.5 * margin), 4)

    return {
        "category": best,
        "label": CATEGORY_KEYWORDS[best]["label"],
        "confidence": confidence,
        "confident": bool(best_score >= CONFIDENT_SCORE and runner_up < best_score),
        "evidence": evidence.get(best, []),
        "scores": {c: round(s, 2) for c, s in sorted(scores.items(), key=lambda kv: -kv[1])},
        "basis": (
            "Keyword evidence on the captured surfaces. Classification scopes "
            "which conditional rules deserve a physical check; it never changes "
            "a rule verdict."
        ),
    }


def scope_rules(
    rule_results: Sequence[Dict[str, Any]], category: str
) -> Dict[str, Any]:
    """Split rules into those the detected category makes relevant and those
    it does not.

    Rules whose ruleset category is not in :data:`CATEGORY_RULE_SCOPE` are
    always in scope. When the commodity type is unknown, everything stays in
    scope - an unclassified package is never given a narrower rulebook.
    """
    in_scope: List[str] = []
    out_of_scope: List[Dict[str, str]] = []
    for rule in rule_results or []:
        rule_category = (rule.get("source") or {}).get("category") or ""
        allowed = CATEGORY_RULE_SCOPE.get(rule_category)
        if not allowed or category == UNKNOWN or category in allowed:
            in_scope.append(rule.get("rule_id", ""))
        else:
            out_of_scope.append(
                {
                    "rule_id": rule.get("rule_id", ""),
                    "category": rule_category,
                    "reason": (
                        f"Rule concerns {', '.join(allowed)} packages; this package "
                        f"was classified as {category}"
                    ),
                }
            )
    return {
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "note": (
            "Scoping is advisory. Every rule was still evaluated by the "
            "deterministic engine and every verdict stands as reported."
        ),
    }
