"""Evidence-preserving extraction pipeline.

Every OCR text element from every captured surface is retained (with its
confidence, bounding box, source image and preprocessing variant). Generic
candidates (currency values, quantities, dates, phones, emails, addresses,
entity names, codes) are detected even when no label is adjacent, and are
associated with fields via same-line matching, spatial proximity, reading
order, cross-image evidence and package reference pointers ("see base of
can"). Anything not associated is surfaced as unclaimed evidence instead of
being discarded.

No LLM/VLM is involved - this is deterministic pattern + geometry logic.
"""

import re
from dataclasses import dataclass, field as dc_field
from typing import List, Dict, Any, Optional, Tuple

from backend.app.services.field_extraction import FieldExtractor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIELD_KINDS = {
    "mrp": "currency",
    "net_quantity": "quantity",
    "manufacturing_date": "date",
    "packing_date": "date",
    "best_before": "date",
    "batch_number": "code",
    "consumer_care": "contact",
    "manufacturer": "entity",
    "packer": "entity",
    "importer": "entity",
    "country_of_origin": "country",
}

# Fields typically carried on the base/lid of cylindrical packages
BASE_CARRIED_FIELDS = {
    "mrp",
    "batch_number",
    "manufacturing_date",
    "packing_date",
    "best_before",
}

# Fields whose unlabelled cross-image association additionally requires a
# matching label anchor somewhere in the pool (prevents false positives,
# e.g. 'India' inside an address line becoming country of origin)
ANCHOR_REQUIRED_FIELDS = {
    "consumer_care",
    "manufacturer",
    "packer",
    "importer",
    "country_of_origin",
}

LABEL_ANCHORS = {
    "mrp": re.compile(r"m\.?r\.?p|max\s*retail|retail\s*price|unit\s*sale|all\s*taxes", re.I),
    "net_quantity": re.compile(r"net\s*(wt|weight|qty|quantity)|quantity\s*when\s*packed", re.I),
    "manufacturing_date": re.compile(r"mfg|mfd|manufactur", re.I),
    "packing_date": re.compile(r"packing|packed\s*on|pkd", re.I),
    "best_before": re.compile(r"best\s*before|use\s*by|exp", re.I),
    "batch_number": re.compile(r"batch|lot|b\.?\s*no", re.I),
    "consumer_care": re.compile(
        r"care|helpline|toll\s*free|call\s*us|relations\s*representative|contact"
        r"|quer|feedback|complaint",
        re.I,
    ),
    "manufacturer": re.compile(r"manufactur|mfg\.?\s*by|marketed\s*by|brand\s*owned", re.I),
    "packer": re.compile(r"pack(?:ed|er)|pkd", re.I),
    "importer": re.compile(r"import", re.I),
    "country_of_origin": re.compile(r"country\s*of\s*origin|product\s*of|made\s*in|origin", re.I),
}

CURRENCY_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*\.?\s*:?\s*(\d{1,5}(?:\.\d{1,2})?)", re.IGNORECASE
)
QUANTITY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|g|gm|grams?|ml|l|litres?|liters?|pcs?|pieces?)\b",
    re.IGNORECASE,
)
DATE_RES = [
    # no leading \b: dates embedded in tokens ('USEBY12/04/27') must match
    re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}[A-Za-z]{3}\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b"),
    re.compile(
        r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]*\d{2,4})\b",
        re.IGNORECASE,
    ),
]
PHONE_RE = re.compile(
    r"(?:\+?91[-\s]?)?(?:\d{5}[-\s]?\d{5}|\d{4}[-\s]?\d{3}[-\s]?\d{4}"
    r"|\d{3}[-\s]?\d{4}[-\s]?\d{4}|\d{3}[-\s]?\d{3}[-\s]?\d{4}"
    r"|\d{4}[-\s]?\d{2}[-\s]?\d{4})"
)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Strong address signals are unambiguous; weak ones (city/state/country names)
# need at least two distinct hits before a line counts as an address
ADDRESS_STRONG_RE = re.compile(
    r"\b(road|street|plot\b|survey\b|gidc|industrial|estate|district|dist\b"
    r"|village|taluka|mandal|state\b|pin\b|\d{6}\b|p\.?o\.?\s*box)",
    re.IGNORECASE,
)
ADDRESS_WEAK_RE = re.compile(
    r"\b(maharashtra|gujarat|haryana|karnataka|tamil\s*nadu|kerala|andhra"
    r"|telangana|west\s*bengal|rajasthan|punjab|uttar\s*pradesh|madhya"
    r"|bihar|odisha|assam|delhi|mumbai|chennai|kolkata|hyderabad|bangalore"
    r"|bengaluru|ahmedabad|surat|jaipur|lucknow|indore|nagpur|gurugram"
    r"|india\b)",
    re.IGNORECASE,
)
ADDRESS_RE = ADDRESS_STRONG_RE
COMPANY_INDICATOR_RE = re.compile(
    r"\b(ltd|pvt|private|limited|corp|corporation|inc|llc|foods|beverages"
    r"|industries|enterprise)",
    re.IGNORECASE,
)
# Batch/lot codes: must contain at least one digit (pure-alpha uppercase
# strings are OCR'd words like 'PREGN' / 'CAFFEINE', not codes)
CODE_RE = re.compile(r"^(?=[A-Z0-9\-/]*\d)[A-Z0-9\-/]{3,12}$")
LIC_RE = re.compile(r"lic|fssai|licence|license", re.IGNORECASE)
NUTRITION_CONTEXT_RE = re.compile(
    r"(total\s*(fat|protein|cholesterol|carbohydrate|sugar|fiber)|saturated|trans"
    r"|sodium|potassium|calcium|iron|vitamin|energy|calories|nutritional|per\s*100"
    r"|serving|kcal|carbohydrate|rda)",
    re.IGNORECASE,
)

DATE_TEXT_USEBY_RE = re.compile(r"use\s*by|useby|exp\.?\b|expiry|best\s*before", re.IGNORECASE)
DATE_TEXT_MFG_RE = re.compile(r"mfg|mfd|manufactur|pkd|packed|packing", re.IGNORECASE)

COUNTRIES = [
    "india", "usa", "united states", "uk", "united kingdom", "germany",
    "thailand", "malaysia", "china", "japan", "korea", "australia", "canada",
    "uae", "dubai", "singapore", "indonesia", "vietnam", "sri lanka",
    "bangladesh", "nepal", "bhutan", "pakistan", "russia", "italy", "france",
    "spain", "switzerland", "netherlands", "denmark", "new zealand", "brazil",
    "mexico", "turkey", "israel", "ireland", "poland", "belgium", "sweden",
    "norway", "finland", "greece", "portugal", "south africa", "nigeria",
    "kenya", "egypt", "philippines", "taiwan", "hong kong",
]

# "see base of can" style reference pointers
POINTER_RE = re.compile(
    r"see\s+(?:the\s+)?(?:first\s+)?(?:letter|character|no\.?|number|code|date)?"
    r"[\s\S]{0,40}?(base|bottom|lid|cap|neck|back|front|top)\s+of\s+(?:the\s+)?"
    r"(can|bottle|pack|package|carton|tin|jar)",
    re.IGNORECASE,
)
# "SEE NECK FOR BATCH NO." style (no 'of <container>' preposition)
POINTER_LOCATION_RE = re.compile(
    r"see\s+(?:the\s+)?(neck|base|bottom|lid|cap|top|back|front)\b",
    re.IGNORECASE,
)
ON_LOCATION_RE = re.compile(
    r"\b(?:on|at)\s+the\s+(base|bottom|lid|cap|neck)\s+of\s+(?:the\s+)?"
    r"(can|bottle|pack|package|carton|tin|jar)",
    re.IGNORECASE,
)
POINTER_FIELD_HINTS = [
    (re.compile(r"expir|use\s*by|useby|best\s*before", re.I), ["best_before"]),
    (re.compile(r"mfg|mfd|manufactur", re.I), ["manufacturing_date"]),
    (re.compile(r"batch|lot|no\.,", re.I), ["batch_number"]),
    (re.compile(r"unit\s*sale|mrp|price|taxes|usp", re.I), ["mrp"]),
    (re.compile(r"net\s*quant", re.I), ["net_quantity"]),
    (re.compile(r"lic", re.I), []),
]


def level_from_conf(conf: float) -> str:
    if conf >= 0.85:
        return "HIGH"
    if conf >= 0.70:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvidenceElement:
    """A single OCR text element - the atomic unit of evidence. Nothing is
    ever dropped from the pool."""
    image_index: int
    image_name: str
    variant: str  # OCR preprocessing variant: 'base', 'rot180', ...
    text: str
    confidence: float
    bbox: List[List[int]]
    surface_usable: bool = True
    claimed_by: Optional[str] = None

    @property
    def y_min(self) -> float:
        return min(p[1] for p in self.bbox) if self.bbox else 0.0

    @property
    def y_max(self) -> float:
        return max(p[1] for p in self.bbox) if self.bbox else 0.0

    @property
    def x_min(self) -> float:
        return min(p[0] for p in self.bbox) if self.bbox else 0.0

    @property
    def x_max(self) -> float:
        return max(p[0] for p in self.bbox) if self.bbox else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_index": self.image_index,
            "image_name": self.image_name,
            "variant": self.variant,
            "text": self.text,
            "confidence": round(self.confidence, 3),
            "bbox": self.bbox,
            "surface_usable": self.surface_usable,
            "claimed_by": self.claimed_by,
        }


@dataclass
class Candidate:
    """A generic value detected in the evidence pool, independent of labels."""
    kind: str  # currency, quantity, date, phone, email, address, entity, code, country, pointer
    value: str
    element: EvidenceElement
    hint: str = ""
    in_base_region: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "text": self.element.text,
            "image": self.element.image_name,
            "image_index": self.element.image_index,
            "confidence": round(self.element.confidence, 3),
            "bbox": self.element.bbox,
            "hint": self.hint,
            "in_base_region": self.in_base_region,
            "surface_usable": self.element.surface_usable,
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class EvidencePipeline:
    """Pool every OCR element, detect generic candidates, associate them with
    fields across surfaces, and surface everything unclaimed as evidence."""

    BASE_REGION_FRACTION = 0.70  # bottom 30% of a surface = base region

    def __init__(self, field_extractor: Optional[FieldExtractor] = None):
        self.extractor = field_extractor or FieldExtractor()

    # ------------------------------------------------------------------
    # Pool construction
    # ------------------------------------------------------------------

    def build_pool(self, per_image: List[Dict[str, Any]]) -> List[EvidenceElement]:
        """per_image entries: {idx, name, usable, ocr: {texts, confidences,
        bounding_boxes} or None}. Retains EVERY element, including from
        unusable surfaces (flagged, used as hints only)."""
        pool = []
        for e in per_image:
            ocr = e.get("ocr")
            if not ocr or not ocr.get("texts"):
                continue
            for text, conf, bbox in zip(
                ocr["texts"], ocr["confidences"], ocr["bounding_boxes"]
            ):
                pool.append(
                    EvidenceElement(
                        image_index=e["idx"],
                        image_name=e["name"],
                        variant="base",
                        text=str(text),
                        confidence=float(conf),
                        bbox=bbox if bbox else [],
                        surface_usable=bool(e.get("usable", True)),
                    )
                )
        return pool

    # ------------------------------------------------------------------
    # Candidate detection
    # ------------------------------------------------------------------

    def detect_candidates(self, pool: List[EvidenceElement]) -> List[Candidate]:
        surface_heights = self._surface_heights(pool)
        candidates: List[Candidate] = []

        for el in pool:
            text = el.text.strip()
            if not text:
                continue
            base_region = self._in_base_region(el, surface_heights)
            nutrition_ctx = self._nutrition_context(el, pool)

            for m in CURRENCY_RE.finditer(text):
                candidates.append(Candidate("currency", m.group(0), el, in_base_region=base_region))

            for m in QUANTITY_RE.finditer(text):
                hint = "nutrition context" if nutrition_ctx else ""
                candidates.append(
                    Candidate("quantity", m.group(0), el, hint=hint, in_base_region=base_region)
                )

            for pat in DATE_RES:
                m = pat.search(text)
                if m:
                    candidates.append(
                        Candidate("date", m.group(1), el, in_base_region=base_region)
                    )
                    break

            m = PHONE_RE.search(text)
            if m and not LIC_RE.search(text) and not re.search(r"cm/l|isi|is\s*:", text, re.IGNORECASE):
                candidates.append(
                    Candidate("phone", m.group(0), el, in_base_region=base_region)
                )

            m = EMAIL_RE.search(text)
            if m:
                candidates.append(Candidate("email", m.group(0), el, in_base_region=base_region))

            if self._address_candidate(el, pool):
                candidates.append(Candidate("address", text, el, in_base_region=base_region))

            if self._looks_like_entity(el, pool):
                candidates.append(
                    Candidate("entity", text, el, in_base_region=base_region)
                )

            code = self._code_candidate(text, el, pool, nutrition_ctx)
            if code:
                code.in_base_region = base_region
                candidates.append(code)

            for country in COUNTRIES:
                if re.search(rf"\b{re.escape(country)}\b", text, re.IGNORECASE):
                    candidates.append(
                        Candidate("country", country.title(), el, in_base_region=base_region)
                    )
                    break

            pointer = self._pointer_candidate(text, el)
            if pointer:
                candidates.append(pointer)

        return candidates

    # ------------------------------------------------------------------
    # Vertical text chains (base-of-can rim codes)
    # ------------------------------------------------------------------

    def detect_vertical_chains(self, pool: List[EvidenceElement]) -> List[Candidate]:
        """Chain short numeric fragments stacked in the same x-column (text
        printed around the base rim of a can, read vertically by OCR)."""
        fragments = [
            el
            for el in pool
            if el.claimed_by is None
            and re.fullmatch(r"\d{1,8}", el.text.strip())
            and el.surface_usable
        ]
        chains: List[Candidate] = []
        used = set()
        fragments.sort(key=lambda e: (e.image_index, e.x_min, e.y_min))
        for i, el in enumerate(fragments):
            if id(el) in used:
                continue
            group = [el]
            used.add(id(el))
            for other in fragments[i + 1:]:
                if id(other) in used:
                    continue
                if other.image_index != el.image_index:
                    continue
                if abs(other.x_min - el.x_min) <= 40:
                    if 0 < other.y_min - group[-1].y_max < 90:
                        group.append(other)
                        used.add(id(other))
            if len(group) >= 2:
                value = "".join(g.text.strip() for g in group)
                # non-anchor members are consumed by the chain (their own
                # candidates stop double-reporting); the anchor stays
                # unclaimed so the chain candidate remains associable
                for g in group[1:]:
                    g.claimed_by = "vertical_chain"
                chains.append(
                    Candidate(
                        kind="code",
                        value=value,
                        element=el,
                        hint=(
                            "vertical text run (base-of-can rim) - possible "
                            "batch/lot or date code"
                        ),
                        in_base_region=True,
                    )
                )
        return chains

    # ------------------------------------------------------------------
    # Association
    # ------------------------------------------------------------------

    def associate(
        self,
        pool: List[EvidenceElement],
        candidates: List[Candidate],
        merged_fields: Dict[str, Dict[str, Any]],
        pointers: List[Candidate],
    ) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        """Associate unclaimed candidates with still-missing fields.

        Association is allowed when:
        - cross-image: the field's value kind matches and the candidate is on
          another captured surface
        - pointer-gated: a label pointer ('see base of can') says the field
          lives on another part of the package
        - base-region: cylindrical package + candidate in the base region
        Associated candidates get LOW confidence (human review), never a
        silent PASS. Everything else stays unclaimed evidence.
        """
        cylindrical = any(
            re.search(r"can|bottle|tin|jar|neck|lid|cap", p.get("text", ""), re.IGNORECASE)
            for p in pointers
        ) or self._has_cylindrical_signature(pool)

        pointer_fields = self._pointer_fields(pointers)

        by_kind: Dict[str, List[Candidate]] = {}
        for c in candidates:
            if c.element.claimed_by is not None or not c.element.surface_usable:
                continue
            if c.kind == "contact":
                by_kind.setdefault("phone", []).append(c)
                by_kind.setdefault("email", []).append(c)
            else:
                by_kind.setdefault(c.kind, []).append(c)

        anchor_text = " | ".join(el.text for el in pool)

        for field_name, kind in FIELD_KINDS.items():
            current = merged_fields.get(field_name, {})
            if current.get("value") is not None:
                continue

            # freshness: exclude candidates claimed by earlier fields
            if kind == "contact":
                pool_kind = [
                    c
                    for c in by_kind.get("phone", []) + by_kind.get("email", [])
                    if c.element.claimed_by is None
                ]
            else:
                pool_kind = [
                    c for c in by_kind.get(kind, []) if c.element.claimed_by is None
                ]
            if kind == "quantity":
                pool_kind = [c for c in pool_kind if "nutrition" not in (c.hint or "")]
            if kind == "entity":
                pool_kind = [c for c in pool_kind if c.element.claimed_by is None]
            if kind == "date":
                # a date whose own text says 'USEBY'/'EXP' belongs to
                # best_before, never to manufacturing/packing date (and
                # vice versa); bare dates stay eligible for any field
                if field_name == "best_before":
                    pool_kind = [
                        c for c in pool_kind if not DATE_TEXT_MFG_RE.search(c.element.text)
                    ]
                else:
                    pool_kind = [
                        c for c in pool_kind if not DATE_TEXT_USEBY_RE.search(c.element.text)
                    ]

            if not pool_kind:
                continue

            pointer_gated = field_name in pointer_fields.get("specific", set())
            base_gated = (
                cylindrical
                and field_name in BASE_CARRIED_FIELDS
                and any(c.in_base_region for c in pool_kind)
            )
            anchor_gated = field_name in ANCHOR_REQUIRED_FIELDS and bool(
                LABEL_ANCHORS.get(field_name, re.compile(r"(?!)")).search(anchor_text)
            )

            if not (pointer_gated or base_gated or anchor_gated):
                continue

            eligible = pool_kind
            if base_gated and not pointer_gated:
                eligible = [c for c in pool_kind if c.in_base_region]
            best = max(eligible, key=lambda c: c.element.confidence)
            conf = min(best.element.confidence, 0.65)
            value = self._field_value_from_candidate(field_name, best)
            if value is None:
                continue

            reason = (
                f"Unlabelled {kind} candidate '{value}' associated with {field_name} "
                f"from surface '{best.element.image_name}'"
            )
            if pointer_gated:
                reason += " (label points to this information on another part of the package)"
            elif base_gated:
                reason += " (cylindrical package - value found in base region)"
            elif anchor_gated:
                reason += " (matching label found on another surface)"

            best.element.claimed_by = field_name
            merged_fields[field_name] = {
                "field_name": field_name,
                "value": value,
                "ocr_text": best.element.text,
                "ocr_confidence": best.element.confidence,
                "extraction_confidence": conf,
                "confidence_level": level_from_conf(conf),
                "bbox": best.element.bbox,
                "reason": reason,
                "line_index": -1,
                "source_image": best.element.image_name,
                "evidence": [best.to_dict()],
            }

        unclaimed = [c for c in candidates if c.element.claimed_by is None]
        return merged_fields, [c.to_dict() for c in unclaimed]

    # ------------------------------------------------------------------
    # Pointers
    # ------------------------------------------------------------------

    POINTER_CONTINUATION_RE = re.compile(
        r"^(mfd|mfg|use\s*by|useby|net\s*quant|batch|lot|exp|best\s*before|mrp"
        r"|unit\s*sale|date|no\.|lic)",
        re.IGNORECASE,
    )

    def extract_pointers(
        self, candidates: List[Candidate], pool: Optional[List[EvidenceElement]] = None
    ) -> List[Dict[str, Any]]:
        # element sequences per surface (reading order) for continuation merge
        image_elements: Dict[int, List[EvidenceElement]] = {}
        if pool is not None:
            for el in pool:
                if el.variant == "base":
                    image_elements.setdefault(el.image_index, []).append(el)

        def continuation_text(el: EvidenceElement) -> str:
            """A pointer often spans several OCR lines:
            'SEE NECK FOR BATCH NO.,' / 'MFD., USE BY DATE,' / 'NET QUANTIT'.
            Merge following unclaimed lines that continue the enumeration."""
            if pool is None:
                return el.text
            els = image_elements.get(el.image_index, [])
            try:
                pos = els.index(el)
            except ValueError:
                return el.text
            parts = [el.text]
            for nxt in els[pos + 1 : pos + 3]:
                if nxt.claimed_by is not None:
                    break
                t = nxt.text.strip()
                if not t:
                    break
                if t.endswith(",") or self.POINTER_CONTINUATION_RE.match(t):
                    parts.append(t)
                else:
                    break
            return " ".join(parts)

        pointers = []
        for c in candidates:
            if c.kind != "pointer":
                continue
            text = continuation_text(c.element)
            location = "base"
            m = POINTER_RE.search(text) or ON_LOCATION_RE.search(text) or POINTER_LOCATION_RE.search(text)
            if m:
                location = m.group(1).lower()
            fields_hinted = set()
            for pat, flds in POINTER_FIELD_HINTS:
                if pat.search(text):
                    fields_hinted.update(flds)
            pointers.append(
                {
                    "text": text,
                    "original_text": c.element.text,
                    "location": location,
                    "fields": sorted(fields_hinted),
                    "image": c.element.image_name,
                    "image_index": c.element.image_index,
                    "bbox": c.element.bbox,
                    "confidence": round(c.element.confidence, 3),
                }
            )
        return pointers

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------

    def run(self, per_image: List[Dict[str, Any]]) -> Dict[str, Any]:
        """per_image: [{idx, name, usable, fields: {...serialized...},
        ocr: {...}}]. Returns {fields, pointers, unclaimed_evidence,
        pool_size, cylindrical_package}."""
        pool = self.build_pool(per_image)

        # Mark elements claimed by per-image labelled extraction
        image_elements: Dict[int, List[EvidenceElement]] = {}
        for el in pool:
            if el.variant == "base":
                image_elements.setdefault(el.image_index, []).append(el)
        for e in per_image:
            els = image_elements.get(e["idx"], [])
            for fname, f in (e.get("fields") or {}).items():
                if f.get("value") is None:
                    continue
                idx = f.get("line_index")
                if isinstance(idx, int) and 0 <= idx < len(els):
                    els[idx].claimed_by = fname

        candidates = self.detect_candidates(pool)
        chains = self.detect_vertical_chains(pool)
        candidates.extend(chains)
        pointers = self.extract_pointers(candidates, pool)

        # Merge labelled fields across images (best confidence wins), then
        # associate unclaimed candidates with still-missing fields
        merged = self._merge_labelled_fields(per_image)
        merged, unclaimed = self.associate(pool, candidates, merged, pointers)
        merged = self._enrich_entity_addresses(pool, merged)

        return {
            "fields": merged,
            "pointers": pointers,
            "unclaimed_evidence": unclaimed,
            "pool_size": len(pool),
            "cylindrical_package": any(
                p.get("location") in ("base", "bottom", "lid", "cap", "neck")
                for p in pointers
            ),
        }

    # ------------------------------------------------------------------
    # Entity address enrichment (Rule 6(1)(a) / Rule 10: name AND address)
    # ------------------------------------------------------------------

    ENTITY_FIELDS = ("manufacturer", "packer", "importer")

    @staticmethod
    def _boxes_near(bbox1, bbox2, y_gap: float = 220.0, x_gap: float = 160.0) -> bool:
        if not bbox1 or not bbox2:
            return False
        try:
            y1a, y1b = min(p[1] for p in bbox1), max(p[1] for p in bbox1)
            x1a, x1b = min(p[0] for p in bbox1), max(p[0] for p in bbox1)
            y2a, y2b = min(p[1] for p in bbox2), max(p[1] for p in bbox2)
            x2a, x2b = min(p[0] for p in bbox2), max(p[0] for p in bbox2)
            v_gap = max(0.0, max(y1a, y2a) - min(y1b, y2b))
            h_gap = max(0.0, max(x1a, x2a) - min(x1b, x2b))
            return v_gap <= y_gap and h_gap <= x_gap
        except Exception:
            return False

    def _enrich_entity_addresses(
        self, pool: List[EvidenceElement], merged: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """For each detected entity, look for an address block spatially next
        to the entity name on the same surface. Sets address_detected /
        address_text so the rule engine can enforce name-AND-address rules."""
        for field_name in self.ENTITY_FIELDS:
            f = merged.get(field_name)
            if not f or f.get("value") is None or not f.get("bbox"):
                continue
            src_image = f.get("source_image")
            best_addr = None
            for el in pool:
                if el.image_name != src_image or el.variant != "base":
                    continue
                if el.claimed_by is not None:
                    continue
                if not self._boxes_near(f["bbox"], el.bbox):
                    continue
                if self._address_candidate(el, pool):
                    best_addr = el
                    break
            if best_addr is not None:
                best_addr.claimed_by = f"{field_name}_address"
                f["address_detected"] = True
                f["address_text"] = best_addr.text
                f.setdefault("evidence", []).append(
                    {
                        "kind": "address",
                        "value": best_addr.text,
                        "image": best_addr.image_name,
                        "bbox": best_addr.bbox,
                        "confidence": round(best_addr.confidence, 3),
                    }
                )
            else:
                f["address_detected"] = False
        return merged

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _merge_labelled_fields(self, per_image: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        field_names = set()
        for e in per_image:
            field_names.update((e.get("fields") or {}).keys())
        for name in sorted(field_names):
            best_key, best_field, best_source = None, None, None
            for e in per_image:
                f = (e.get("fields") or {}).get(name)
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
                best_field.setdefault("evidence", [])
                merged[name] = best_field
            else:
                stub_source = next((e for e in per_image if e.get("fields")), None)
                stub = dict((stub_source["fields"].get(name, {})) if stub_source else {})
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
    def _surface_heights(pool: List[EvidenceElement]) -> Dict[int, float]:
        heights = {}
        for el in pool:
            if el.y_max > heights.get(el.image_index, 0.0):
                heights[el.image_index] = el.y_max
        return heights

    def _in_base_region(self, el: EvidenceElement, heights: Dict[int, float]) -> bool:
        h = heights.get(el.image_index, 0.0)
        if h <= 0:
            return False
        return el.y_min >= h * self.BASE_REGION_FRACTION

    @staticmethod
    def _nutrition_context(el: EvidenceElement, pool: List[EvidenceElement]) -> bool:
        neighbours = [
            other.text
            for other in pool
            if other.image_index == el.image_index
            and other is not el
            and abs(other.y_min - el.y_min) < 80
        ]
        context = el.text + " " + " ".join(neighbours)
        return bool(NUTRITION_CONTEXT_RE.search(context))

    @staticmethod
    def _looks_like_entity(el: EvidenceElement, pool: List[EvidenceElement]) -> bool:
        text = el.text.strip()
        if len(text) < 4 or len(text) > 60:
            return False
        if LIC_RE.search(text):
            return False
        if re.search(r"see\s+(the\s+)?(base|first|bottom)|base\s+of\s+can", text, re.IGNORECASE):
            return False
        return bool(COMPANY_INDICATOR_RE.search(text))

    def _code_candidate(
        self, text: str, el: EvidenceElement, pool: List[EvidenceElement], nutrition_ctx: bool
    ) -> Optional[Candidate]:
        t = text.strip()
        if not CODE_RE.match(t):
            return None
        if LIC_RE.search(t):
            return None
        if nutrition_ctx:
            return None
        if any(pat.search(t) for pat in DATE_RES):
            return None
        if CURRENCY_RE.search(t):
            return None
        if QUANTITY_RE.search(t):
            return None
        # Reject PIN codes (6 digits in address context)
        if re.fullmatch(r"\d{6}", t) and self._near_address(el, pool):
            return None
        hint = "possible batch/lot code"
        return Candidate("code", t, el, hint=hint)

    @staticmethod
    def _near_address(el: EvidenceElement, pool: List[EvidenceElement]) -> bool:
        for other in pool:
            if other is el:
                continue
            if other.image_index == el.image_index and abs(other.y_min - el.y_min) < 100:
                if ADDRESS_RE.search(other.text):
                    return True
        return False

    def _address_candidate(self, el: EvidenceElement, pool: List[EvidenceElement]) -> bool:
        """An address needs a strong signal (road/plot/PIN/estate...), or at
        least two distinct weak signals (city/state/country names). A single
        'India' inside a company name is NOT an address."""
        text = el.text.strip()
        if ADDRESS_STRONG_RE.search(text):
            return True
        if re.fullmatch(r"\d{6}", text):
            return self._near_address(el, pool)
        weak_hits = set(m.group(0).lower() for m in ADDRESS_WEAK_RE.finditer(text))
        return len(weak_hits) >= 2

    @staticmethod
    def _pointer_candidate(text: str, el: EvidenceElement) -> Optional[Candidate]:
        if POINTER_RE.search(text) or ON_LOCATION_RE.search(text) or POINTER_LOCATION_RE.search(text):
            return Candidate("pointer", text.strip(), el, hint="package reference pointer")
        return None

    @staticmethod
    def _pointer_fields(pointers: List[Dict[str, Any]]) -> Dict[str, set]:
        specific = set()
        for p in pointers:
            text = p.get("text", "")
            for pat, flds in POINTER_FIELD_HINTS:
                if pat.search(text):
                    specific.update(flds)
        return {"specific": specific}

    @staticmethod
    def _has_cylindrical_signature(pool: List[EvidenceElement]) -> bool:
        """Short numeric fragments stacked in a narrow column suggest a
        cylindrical rim/base text layout."""
        per_image: Dict[int, List[EvidenceElement]] = {}
        for el in pool:
            if re.fullmatch(r"\d{1,3}", el.text.strip()):
                per_image.setdefault(el.image_index, []).append(el)
        for els in per_image.values():
            xs = [el.x_min for el in els]
            if len(els) >= 3 and (max(xs) - min(xs)) <= 80:
                return True
        return False

    ENTITY_LABEL_PREFIX_RE = re.compile(
        r"^(?:mfd|mfg|mkt|manufactured|marketed|packed|imported|brand\s*owned"
        r"|and\s*mkt)\.?\s*(?:by|and)?\s*[:\-]?\s*",
        re.IGNORECASE,
    )

    @staticmethod
    def _field_value_from_candidate(field_name: str, c: Candidate) -> Optional[str]:
        if field_name == "mrp":
            m = CURRENCY_RE.search(c.element.text)
            return f"₹{m.group(1)}" if m else None
        if field_name == "consumer_care":
            if c.kind == "phone":
                return f"Phone: {c.value}"
            if c.kind == "email":
                return f"Email: {c.value}"
            return None
        if field_name == "country_of_origin":
            return c.value
        if field_name in ("manufacturer", "packer", "importer"):
            value = c.value.strip()
            for _ in range(3):
                stripped = EvidencePipeline.ENTITY_LABEL_PREFIX_RE.sub("", value).strip(":.,;- ")
                if stripped == value:
                    break
                value = stripped
            return value or None
        return c.value
