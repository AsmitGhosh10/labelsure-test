import re
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class ExtractedField:
    field_name: str
    value: Optional[str]
    ocr_text: str
    ocr_confidence: float
    extraction_confidence: float
    confidence_level: str  # HIGH, MEDIUM, LOW, MISSING
    bbox: List[List[int]]
    reason: str
    line_index: int

class FieldExtractor:
    """Robust field extraction from PaddleOCR results with context awareness."""
    
    def __init__(self):
        # Common reject patterns to avoid false positives
        self.reject_patterns = {
            'fssai': re.compile(r'fssai|lic\.?\s*no', re.IGNORECASE),
            'pin_code': re.compile(r'pin\s*:?\s*\d{6}|\b\d{6}\b.*india', re.IGNORECASE),
            'phone': re.compile(r'\+?\d{1,2}[-\s]?\d{3,4}[-\s]?\d{3,4}[-\s]?\d{0,4}', re.IGNORECASE),
            'barcode': re.compile(r'^\d{8,14}$'),
            'nutrition': re.compile(r'(total\s*(fat|protein|cholesterol|carbohydrate|sugar|fiber)|saturated|trans|sodium|potassium|calcium|iron|vitamin|energy|calories|nutritional)', re.IGNORECASE),
            'batch': re.compile(r'batch\s*(no|number)|lot\s*(no|number)|b\.?no', re.IGNORECASE),
        }
        
    def extract_all(self, ocr_texts: List[str], ocr_confidences: List[float], 
                    bboxes: List[List[List[int]]]) -> Dict[str, ExtractedField]:
        """Extract all mandatory fields from OCR results."""
        
        results = {}
        
        # Extract each field
        results['mrp'] = self._extract_mrp(ocr_texts, ocr_confidences, bboxes)
        # Brand first: an explicitly labelled or trademarked brand line is not
        # the generic commodity name, so it is excluded from that search.
        brand = self._extract_brand(ocr_texts, ocr_confidences, bboxes)
        results['product_name'] = self._extract_product_name(
            ocr_texts, ocr_confidences, bboxes,
            exclude_idx=brand.line_index if brand.confidence_level == 'HIGH' else -1,
        )
        results['net_quantity'] = self._extract_net_quantity(ocr_texts, ocr_confidences, bboxes)
        results['manufacturer'] = self._extract_entity(ocr_texts, ocr_confidences, bboxes, 'manufacturer')
        results['packer'] = self._extract_entity(ocr_texts, ocr_confidences, bboxes, 'packer')
        results['importer'] = self._extract_entity(ocr_texts, ocr_confidences, bboxes, 'importer')
        results['manufacturing_date'] = self._extract_date(ocr_texts, ocr_confidences, bboxes, 'manufacturing')
        results['packing_date'] = self._extract_date(ocr_texts, ocr_confidences, bboxes, 'packing')
        results['best_before'] = self._extract_date(ocr_texts, ocr_confidences, bboxes, 'best_before')
        results['batch_number'] = self._extract_batch(ocr_texts, ocr_confidences, bboxes)
        results['consumer_care'] = self._extract_consumer_care(ocr_texts, ocr_confidences, bboxes)
        results['country_of_origin'] = self._extract_country_of_origin(ocr_texts, ocr_confidences, bboxes)
        results['brand'] = (
            brand
            if brand.confidence_level == 'HIGH'
            else self._extract_brand(
                ocr_texts, ocr_confidences, bboxes,
                exclude_idx=results['product_name'].line_index,
            )
        )
        
        return results
    
    def _is_reject(self, text: str, reject_type: str = None) -> bool:
        """Check if text matches a reject pattern."""
        if reject_type and reject_type in self.reject_patterns:
            return bool(self.reject_patterns[reject_type].search(text))
        # Check all
        for key, pattern in self.reject_patterns.items():
            if pattern.search(text):
                return True
        return False
    
    def _find_label_context(self, texts: List[str], target_idx: int, 
                           window: int = 3) -> List[Tuple[int, str]]:
        """Get surrounding text lines for context."""
        context = []
        for i in range(max(0, target_idx - window), min(len(texts), target_idx + window + 1)):
            if i != target_idx:
                context.append((i, texts[i]))
        return context
    
    def _bbox_distance(self, bbox1: List[List[int]], bbox2: List[List[int]]) -> float:
        """Calculate approximate distance between two bounding boxes."""
        if not bbox1 or not bbox2:
            return float('inf')
        # Use center points
        c1_x = sum(p[0] for p in bbox1) / len(bbox1)
        c1_y = sum(p[1] for p in bbox1) / len(bbox1)
        c2_x = sum(p[0] for p in bbox2) / len(bbox2)
        c2_y = sum(p[1] for p in bbox2) / len(bbox2)
        return ((c1_x - c2_x) ** 2 + (c1_y - c2_y) ** 2) ** 0.5
    
    def _vertical_overlap(self, bbox1: List[List[int]], bbox2: List[List[int]]) -> float:
        """Vertical overlap ratio between two bboxes (0..1), normalised by the
        shorter box height. High values mean the boxes sit on the same visual
        row - the standard label|value columnar layout on packages."""
        if not bbox1 or not bbox2:
            return 0.0
        try:
            y1a = min(p[1] for p in bbox1)
            y1b = max(p[1] for p in bbox1)
            y2a = min(p[1] for p in bbox2)
            y2b = max(p[1] for p in bbox2)
            h1 = max(1.0, y1b - y1a)
            h2 = max(1.0, y2b - y2a)
            overlap = min(y1b, y2b) - max(y1a, y2a)
            return max(0.0, overlap / min(h1, h2))
        except Exception:
            return 0.0
    
    def _extract_mrp(self, texts: List[str], confidences: List[float], 
                     bboxes: List[List[List[int]]]) -> ExtractedField:
        """Extract MRP with robust pattern matching and false-positive rejection."""
        
        mrp_patterns = [
            r'\bm\.?r\.?p\.?\b',
            r'\bmax\.?\s*retail\s*price\b',
            r'\bunit\s*selling\s*price\b',
            r'\bmax\.?\s*retail\s*pr\b',
        ]
        
        price_value_pattern = re.compile(
            r'(?:rs\.?|₹|inr)?\s*[\.:]?\s*(\d{1,5}(?:\.\d{1,2})?)',
            re.IGNORECASE
        )
        
        # Reject: nutrition values, very small numbers, FSSAI, PIN, batch, phone
        def is_valid_mrp_value(val_str: str, full_text: str) -> bool:
            try:
                val = float(val_str)
                # MRP should be >= 1 and <= 50000
                if not (1 <= val <= 50000):
                    return False
                # Reject if text contains nutrition keywords
                if self._is_reject(full_text, 'nutrition'):
                    return False
                # Reject if it's clearly a phone/barcode/FSSAI/PIN
                if re.search(r'\b\d{6,14}\b', full_text) and not re.search(r'(?:rs|₹|mrp|price)', full_text, re.IGNORECASE):
                    return False
                # Reject if followed by mg, g, kcal, etc. (nutrition units)
                if re.search(r'\d+\.?\d*\s*(mg|g|kg|ml|l|kcal|cal|mcg|%)(?:\s|$)', full_text, re.IGNORECASE):
                    # Unless it's explicitly an MRP line
                    if not re.search(r'(?:mrp|price|₹|rs)', full_text, re.IGNORECASE):
                        return False
                return True
            except ValueError:
                return False
        
        # Strategy 1: Find MRP keyword and extract value from same or adjacent lines
        for i, text in enumerate(texts):
            if any(re.search(p, text, re.IGNORECASE) for p in mrp_patterns):
                # Try same line first
                match = price_value_pattern.search(text)
                if match and is_valid_mrp_value(match.group(1), text):
                    val = match.group(1)
                    # Look for currency symbol
                    currency = '₹'
                    if re.search(r'rs\.?', text, re.IGNORECASE):
                        currency = 'Rs.'
                    
                    return ExtractedField(
                        field_name='mrp',
                        value=f"{currency}{val}",
                        ocr_text=text,
                        ocr_confidence=confidences[i],
                        extraction_confidence=min(confidences[i], 0.95),
                        confidence_level='HIGH',
                        bbox=bboxes[i],
                        reason=f"Price value '{val}' found on MRP declaration line",
                        line_index=i
                    )
                
                # Try adjacent lines (within 2 lines)
                for j in range(max(0, i-2), min(len(texts), i+3)):
                    if j == i:
                        continue
                    adj_text = texts[j]
                    # Skip nutrition/ingredient lines
                    if re.search(r'(nutrition|ingredient|total\s*fat|protein|carbohydrate|calories|%)', adj_text, re.IGNORECASE):
                        continue
                    match = price_value_pattern.search(adj_text)
                    if match and is_valid_mrp_value(match.group(1), adj_text):
                        val = match.group(1)
                        currency = '₹'
                        if re.search(r'rs\.?', adj_text, re.IGNORECASE):
                            currency = 'Rs.'
                        
                        return ExtractedField(
                            field_name='mrp',
                            value=f"{currency}{val}",
                            ocr_text=f"{text} | {adj_text}",
                            ocr_confidence=min(confidences[i], confidences[j]),
                            extraction_confidence=min(confidences[i], confidences[j], 0.85),
                            confidence_level='MEDIUM',
                            bbox=bboxes[i],
                            reason=f"Price value '{val}' found near MRP keyword (line {j})",
                            line_index=i
                        )
        
        # Strategy 2: Look for "(Inclusive of all taxes)" / "unit sale" fragments
        # (on cans the MRP line is often OCR-fragmented, e.g. 'TAXES), UNIT SALE')
        for i, text in enumerate(texts):
            if re.search(r'(inclusive of all taxes|incl\.?\s*of\s*all taxes|\(incl\b|unit\s*sale|all\s*taxes\b)', text, re.IGNORECASE):
                for j in range(max(0, i-3), min(len(texts), i+3)):
                    match = price_value_pattern.search(texts[j])
                    if match and is_valid_mrp_value(match.group(1), texts[j]):
                        val = match.group(1)
                        return ExtractedField(
                            field_name='mrp',
                            value=f"₹{val}",
                            ocr_text=texts[j],
                            ocr_confidence=confidences[j],
                            extraction_confidence=min(confidences[j], 0.80),
                            confidence_level='MEDIUM',
                            bbox=bboxes[j],
                            reason=f"Price '{val}' found near tax-inclusive declaration",
                            line_index=j
                        )
        
        # Strategy 3: Detect unusual format like ".20.00" attached to MRP text
        for i, text in enumerate(texts):
            if re.search(r'\bm\.?r\.?p', text, re.IGNORECASE):
                # Look for pattern: MRP followed by dot and number
                match = re.search(r'm\.?r\.?p[^\d]*(\d{1,5}(?:\.\d{1,2})?)', text, re.IGNORECASE)
                if match and is_valid_mrp_value(match.group(1), text):
                    val = match.group(1)
                    return ExtractedField(
                        field_name='mrp',
                        value=f"₹{val}",
                        ocr_text=text,
                        ocr_confidence=confidences[i],
                        extraction_confidence=min(confidences[i], 0.85),
                        confidence_level='MEDIUM',
                        bbox=bboxes[i],
                        reason=f"Price '{val}' extracted from MRP line with unusual formatting",
                        line_index=i
                    )
        
        return ExtractedField(
            field_name='mrp',
            value=None,
            ocr_text='',
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            confidence_level='MISSING',
            bbox=[],
            reason="No MRP declaration found or all candidates rejected as false positives",
            line_index=-1
        )
    
    def _extract_product_name(self, texts: List[str], confidences: List[float],
                              bboxes: List[List[List[int]]],
                              exclude_idx: int = -1) -> ExtractedField:
        """Extract the common/generic name of the commodity (Rule 6(1)(b)).

        Heuristic: the most prominent text block on the surface (largest
        bounding-box area) that is not a declaration label, nutrition row,
        licence number, address or warning line. Brand names double as the
        common name when nothing more generic is printed prominently.
        """
        skip_pattern = re.compile(
            r'm\.?r\.?p|retail\s*price|unit\s*sale|taxes|incl\b|usp\b'
            r'|net\s*(wt|weight|qty|quant)'
            r'|mfg|mfd|manufactur|facture|packed|marketed|mkt\.?\s*by|batch|lot\b'
            r'|\bbrand\b'
            r'|best\s*before|use\s*by|useby|exp|licen|lic\.?\s*no|fssa'
            r'|ingredient|nutrition|energy|protein|fat\b|carbohydrate|sodium'
            r'|calcium|vitamin|sugar|cholesterol|serving|kcal|per\s*100'
            r'|consumer|customer|helpline|toll|call\s*us|contact|email|phone'
            r'|feedback|address|pin\b|road|street'
            r'|industrial|estate|plot\b|product\s*of|made\s*in|country\s*of\s*origin'
            r'|store\b|keep\b|warning|contains|allergen|see\s+(the\s+)?(base|neck|first)'
            r'|base\s*of\s*can|qr\s*code|bar\s*code|smart\s*app|letter\b'
            r'|maharashtra|gujarat|haryana|karnataka|tamil|kerala|andhra|telangana'
            r'|bengal|rajasthan|punjab|pradesh|bihar|odisha|assam|delhi|mumbai'
            r'|chennai|kolkata|hyderabad|bangalore|bengaluru|ahmedabad|surat'
            r'|jaipur|lucknow|indore|nagpur|gurugram|india\b|www|\.com',
            re.IGNORECASE,
        )

        def alpha_ratio(s: str) -> float:
            letters = sum(c.isalpha() for c in s)
            return letters / max(1, len(s.replace(" ", "")))

        best_idx, best_score = None, 0.0
        for i, text in enumerate(texts):
            if i == exclude_idx:
                continue  # already claimed as the brand
            t = text.strip()
            if len(t) < 3 or len(t) > 40 or confidences[i] < 0.80:
                continue
            if "(" in t and ")" in t:
                # parenthesised fragments like 'LETTER (S) OF THE' are not names
                continue
            if skip_pattern.search(t):
                continue
            # A company name is the manufacturer/packer, never the commodity's
            # common name - Rule 6(1)(b) asks what the thing *is*.
            if self.ENTITY_SUFFIX_RE.search(t):
                continue
            if alpha_ratio(t) < 0.6:
                continue
            if not bboxes[i]:
                continue
            try:
                ys = [p[1] for p in bboxes[i]]
                xs = [p[0] for p in bboxes[i]]
                area = max(1, (max(ys) - min(ys))) * max(1, (max(xs) - min(xs)))
            except Exception:
                continue
            score = area * float(confidences[i]) * min(1.0, len(t) / 6.0)
            if score > best_score:
                best_score = score
                best_idx = i

        if best_idx is not None:
            return ExtractedField(
                field_name='product_name',
                value=texts[best_idx].strip(),
                ocr_text=texts[best_idx],
                ocr_confidence=confidences[best_idx],
                extraction_confidence=min(confidences[best_idx], 0.75),
                confidence_level='MEDIUM',
                bbox=bboxes[best_idx],
                reason="Most prominent non-declaration text on the captured surface",
                line_index=best_idx,
            )

        return ExtractedField(
            field_name='product_name',
            value=None,
            ocr_text='',
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            confidence_level='MISSING',
            bbox=[],
            reason="No prominent commodity name text found",
            line_index=-1,
        )

    def _extract_net_quantity(self, texts: List[str], confidences: List[float],
                              bboxes: List[List[List[int]]]) -> ExtractedField:
        """Extract net quantity with nutrition table rejection."""
        
        qty_label_patterns = [
            r'\bnet\s*(?:wt\.?|weight|wt|qty|quantity)\b',
            r'\bnet\s*wt\b',
            r'\bquantity\s*when\s*packed\b',
        ]
        
        qty_value_patterns = [
            r'(\d+(?:\.\d+)?)\s*(g|gm|grams?|kg|ml|l|liters?|pcs?|pieces?)\b',
            r'(\d{2,4})\s*(g|gm|kg|ml|l)\b',
        ]
        
        nutrition_keywords = [
            'total fat', 'saturated fat', 'trans fat', 'cholesterol', 'sodium', 
            'potassium', 'total carbohydrate', 'dietary fiber', 'sugar', 'protein',
            'calcium', 'iron', 'vitamin', 'energy', 'calories', 'nutritional',
            'nutrition facts', 'per 100', 'serving size', 'amount per'
        ]
        
        def is_nutrition_context(idx: int) -> bool:
            window = []
            for j in range(max(0, idx-2), min(len(texts), idx+3)):
                window.append(texts[j].lower())
            context = ' '.join(window)
            return any(kw in context for kw in nutrition_keywords)
        
        # Strategy 1: Find explicit net weight label
        for i, text in enumerate(texts):
            if any(re.search(p, text, re.IGNORECASE) for p in qty_label_patterns):
                # Try same line
                for pattern in qty_value_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        val = match.group(0)
                        return ExtractedField(
                            field_name='net_quantity',
                            value=val,
                            ocr_text=text,
                            ocr_confidence=confidences[i],
                            extraction_confidence=min(confidences[i], 0.95),
                            confidence_level='HIGH',
                            bbox=bboxes[i],
                            reason=f"Quantity '{val}' found on net weight declaration line",
                            line_index=i
                        )
                
                # Try adjacent lines (within 3 lines)
                for j in range(max(0, i-1), min(len(texts), i+4)):
                    if j == i:
                        continue
                    adj_text = texts[j]
                    # Skip nutrition context
                    adj_context = []
                    for k in range(max(0, j-1), min(len(texts), j+2)):
                        adj_context.append(texts[k].lower())
                    adj_ctx = ' '.join(adj_context)
                    if any(kw in adj_ctx for kw in nutrition_keywords):
                        continue
                    
                    for pattern in qty_value_patterns:
                        match = re.search(pattern, adj_text, re.IGNORECASE)
                        if match:
                            val = match.group(0)
                            return ExtractedField(
                                field_name='net_quantity',
                                value=val,
                                ocr_text=f"{text} | {adj_text}",
                                ocr_confidence=min(confidences[i], confidences[j]),
                                extraction_confidence=min(confidences[i], confidences[j], 0.85),
                                confidence_level='MEDIUM',
                                bbox=bboxes[i],
                                reason=f"Quantity '{val}' found near net weight label",
                                line_index=i
                            )
        
        # Strategy 2: Find standalone quantity values that are NOT in nutrition context
        # Only use this if we haven't found anything yet - scan from bottom up to prefer
        # values that appear lower on the label (usually where net qty is placed)
        for i in range(len(texts) - 1, -1, -1):
            text = texts[i]
            if is_nutrition_context(i):
                continue
            
            for pattern in qty_value_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    val = match.group(0)
                    num_val = float(match.group(1))
                    # Reject small values in suspicious context
                    if num_val < 20 and not re.search(r'net|qty|weight|wt', text, re.IGNORECASE):
                        continue
                    # Reject if line contains nutrition keywords
                    if re.search(r'(total\s*fat|protein|carbohydrate|calories|energy|sodium|cholesterol|sugar|fiber)', text, re.IGNORECASE):
                        continue
                    
                    return ExtractedField(
                        field_name='net_quantity',
                        value=val,
                        ocr_text=text,
                        ocr_confidence=confidences[i],
                        extraction_confidence=min(confidences[i], 0.70),
                        confidence_level='LOW',
                        bbox=bboxes[i],
                        reason=f"Quantity '{val}' found without explicit net weight label",
                        line_index=i
                    )
        
        return ExtractedField(
            field_name='net_quantity',
            value=None,
            ocr_text='',
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            confidence_level='MISSING',
            bbox=[],
            reason="No net quantity declaration found",
            line_index=-1
        )
    
    def _looks_like_company_name(self, text: str) -> bool:
        """Check if text looks like a company/entity name."""
        company_indicators = ['ltd', 'pvt', 'private', 'limited', 'corp', 'corporation',
                             'inc', 'llc', 'foods', 'beverages', 'industries', 'enterprise',
                             'gruh', 'udhyog', 'sakhi', 'mandal']
        nutrition_reject = ['protein', 'fat', 'carbohydrate', 'calories', 'energy', 'sodium',
                           'cholesterol', 'sugar', 'fiber', 'vitamin', 'iron', 'calcium',
                           'proprietary', 'food:', 'foods,']
        lower = text.lower()
        # Reject nutrition lines
        if any(rej in lower for rej in nutrition_reject):
            return False
        return any(ind in lower for ind in company_indicators)

    # Lines that must never be used as an entity name (licence numbers,
    # 'see base of can' pointers, certification marks, etc.)
    ENTITY_REJECT = re.compile(
        r'fssai|fssat|lic\.?\s*no|licence|license|see\s+(?:the\s+)?(?:first|base|bottom|lid|back)'
        r'|base\s+of\s+can|on\s+the\s+base|expiry|use\s*by|best\s*before|batch|lot\s*no'
        r'|isi\s*mark|is\s*:|cm/l|address|see\s+label',
        re.IGNORECASE
    )

    # Tokens that continue a company name onto the next OCR line
    NAME_CONTINUATION = re.compile(
        r'^(?:private|pvt\.?|ltd\.?|limited|llp|inc\.?|co\.?,?|company|and|&|india|enterprises?)\.?$',
        re.IGNORECASE
    )
    
    def _extract_entity(self, texts: List[str], confidences: List[float],
                        bboxes: List[List[List[int]]], entity_type: str) -> ExtractedField:
        """Extract manufacturer, packer, or importer."""
        
        keywords_map = {
            'manufacturer': [
                r'\bmanufactured by\b', r'\bmfg\.?\s*by\b', r'\bmanufacturer\b',
                r'\bmarketed by\b', r'\bmanufactured & marketed by\b',
                r'\bmanufactured and marketed by\b',
                r'\bmfd\.?\s*by\b', r'\bmkt\.?\s*by\b'
            ],
            'packer': [
                r'\bpacked by\b', r'\bpkd\.?\s*by\b', r'\bpacker\b',
                r'\bpacked & marketed by\b', r'\bpacked and marketed by\b',
                r'\bpacked on\b', r'\bdate of packing\b'
            ],
            'importer': [
                r'\bimported by\b', r'\bimp\.?\s*by\b', r'\bimporter\b'
            ]
        }
        
        keywords = keywords_map.get(entity_type, [])
        
        for i, text in enumerate(texts):
            for kw in keywords:
                if re.search(kw, text, re.IGNORECASE):
                    # Try to get the actual entity name
                    clean = re.sub(kw, '', text, flags=re.IGNORECASE).strip(':.,; ')
                    
                    # If same line has the name, use it
                    if len(clean) >= 5 and self._looks_like_company_name(clean):
                        return ExtractedField(
                            field_name=entity_type,
                            value=clean,
                            ocr_text=text,
                            ocr_confidence=confidences[i],
                            extraction_confidence=min(confidences[i], 0.90),
                            confidence_level='HIGH',
                            bbox=bboxes[i],
                            reason=f"{entity_type.capitalize()} name found on same line as keyword",
                            line_index=i
                        )
                    
                    # Look at next few lines for a company name
                    if i + 1 < len(texts):
                        found_j = None
                        for j in range(i+1, min(len(texts), i+4)):
                            candidate = texts[j]
                            # Skip nutrition/address lines
                            if re.search(r'(nutrition|total fat|protein|carbohydrate|calories|energy|sodium|cholesterol)', candidate, re.IGNORECASE):
                                continue
                            # Skip licence numbers, pointers, certification marks
                            if self.ENTITY_REJECT.search(candidate):
                                continue
                            if self._looks_like_company_name(candidate):
                                found_j = j
                                break

                        if found_j is not None:
                            value = texts[found_j]
                            # Append a name continuation line (e.g. 'PRIVATE LIMITED')
                            if found_j + 1 < len(texts) and self.NAME_CONTINUATION.match(texts[found_j + 1].strip()):
                                value = f"{value} {texts[found_j + 1].strip()}"
                            return ExtractedField(
                                field_name=entity_type,
                                value=value,
                                ocr_text=f"{text} | {value}",
                                ocr_confidence=min(confidences[i], confidences[found_j]),
                                extraction_confidence=min(confidences[i], confidences[found_j], 0.90),
                                confidence_level='HIGH',
                                bbox=bboxes[i],
                                reason=f"{entity_type.capitalize()} name found on line following keyword",
                                line_index=i
                            )

                        # Extended search: up to 10 lines, skipping rejects
                        # (handles interleaved columns on real labels)
                        for j in range(i+4, min(len(texts), i+11)):
                            candidate = texts[j]
                            if self.ENTITY_REJECT.search(candidate):
                                continue
                            if re.search(r'(nutrition|total fat|protein|carbohydrate|calories|energy|sodium|cholesterol)', candidate, re.IGNORECASE):
                                continue
                            if self._looks_like_company_name(candidate):
                                value = candidate
                                if j + 1 < len(texts) and self.NAME_CONTINUATION.match(texts[j + 1].strip()):
                                    value = f"{value} {texts[j + 1].strip()}"
                                return ExtractedField(
                                    field_name=entity_type,
                                    value=value,
                                    ocr_text=f"{text} | {value}",
                                    ocr_confidence=min(confidences[i], confidences[j]),
                                    extraction_confidence=min(confidences[i], confidences[j], 0.85),
                                    confidence_level='MEDIUM',
                                    bbox=bboxes[i],
                                    reason=f"{entity_type.capitalize()} name found {j - i} lines after keyword",
                                    line_index=i
                                )

                        # Fallback: next non-reject line (preserves legacy behaviour
                        # for unusual layouts while never returning licence/pointer text)
                        for j in range(i+1, min(len(texts), i+5)):
                            if self.ENTITY_REJECT.search(texts[j]):
                                continue
                            if re.search(r'(nutrition|total fat|protein|carbohydrate|calories|energy|sodium|cholesterol)', texts[j], re.IGNORECASE):
                                continue
                            entity_name = texts[j]
                            return ExtractedField(
                                field_name=entity_type,
                                value=entity_name,
                                ocr_text=f"{text} | {entity_name}",
                                ocr_confidence=min(confidences[i], confidences[j]),
                                extraction_confidence=min(confidences[i], confidences[j], 0.75),
                                confidence_level='MEDIUM',
                                bbox=bboxes[i],
                                reason=f"{entity_type.capitalize()} name found on line following keyword (fallback)",
                                line_index=i
                            )
        
        return ExtractedField(
            field_name=entity_type,
            value=None,
            ocr_text='',
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            confidence_level='MISSING',
            bbox=[],
            reason=f"No {entity_type} declaration found",
            line_index=-1
        )
    
    def _extract_date(self, texts: List[str], confidences: List[float],
                      bboxes: List[List[List[int]]], date_type: str) -> ExtractedField:
        """Extract dates with type-specific labels.
        
        Uses three strategies in order:
        1. Same line as the label
        2. Spatial: value on the same visual row as the label (columnar
           label|value layouts where OCR interleaves other columns between
           the label and its value in reading order)
        3. Line-order adjacency (fallback) + batch-embedded dates
        """
        
        label_patterns_map = {
            'manufacturing': [
                r'\bmfg\.?\s*(?:date)?\b', r'\bmfd\.?\s*(?:date)?\b',
                r'\bmanufacturing\s*(?:date)?\b', r'\bmanufactured\s*(?:date|on)?\b',
                r'\bmfd\b'
            ],
            'packing': [
                r'\bpkd\.?\s*(?:date|on)?\b', r'\bpacked\s*(?:date|on)?\b',
                r'\bpacking\s*(?:date)?\b', r'\bdate of packing\b'
            ],
            'best_before': [
                r'\bbest before\b', r'\buse\s*by\b', r'\buseby(?![a-z])',
                r'\bexp\.?\s*(?:date)?\b',
                r'\bexpiry\b', r'\bbest before date\b'
            ]
        }
        
        date_value_patterns = [
            # no leading \b: dates embedded in tokens ('USEBY12/04/27') must match
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b',
            r'\b(\d{1,2}[A-Za-z]{3}\d{2,4})\b',
            r'\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b',
            r'\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]*\d{2,4})\b',
            # Month/year only - the form Rule 6(1)(d) actually requires.
            # Tried last so a full dd/mm/yyyy is never truncated to mm/yyyy.
            r'\b(\d{1,2}[/\-.]\d{4})\b',
        ]
        
        address_keywords = ['road', 'street', 'area', 'industrial', 'gidc', 'india', 'pin', 'dist', 'district', 'po:', 'p.o.']
        
        # Lines declaring a DIFFERENT date type must not be used as candidates
        other_date_type_patterns = {
            'manufacturing': r'\b(best\s*before|use\s*by|exp\.?|expiry)\b',
            'packing': r'\b(best\s*before|use\s*by|exp\.?|expiry)\b',
            'best_before': r'\b(mfg|mfd|manufactur\w*|pkd|pack\w*)\b',
        }
        other_type_pattern = other_date_type_patterns.get(date_type, r'(?!)')
        
        def own_line_is_address(idx: int) -> bool:
            return any(kw in texts[idx].lower() for kw in address_keywords)
        
        def is_other_date_type_label(idx: int) -> bool:
            return bool(re.search(other_type_pattern, texts[idx], re.IGNORECASE))
        
        def candidate_claimed_by_other_type(j: int) -> bool:
            """Candidate sits on the same visual row as a DIFFERENT date-type
            label - the value belongs to that label, not this one."""
            for k in range(len(texts)):
                if k == j:
                    continue
                if not re.search(other_type_pattern, texts[k], re.IGNORECASE):
                    continue
                if self._vertical_overlap(bboxes[k], bboxes[j]) >= 0.2:
                    return True
            return False
        
        def find_date_in_line(idx: int) -> Optional[str]:
            for pattern in date_value_patterns:
                match = re.search(pattern, texts[idx], re.IGNORECASE)
                if match:
                    return match.group(1)
            return None
        
        labels = label_patterns_map.get(date_type, [])
        
        for i, text in enumerate(texts):
            if not any(re.search(p, text, re.IGNORECASE) for p in labels):
                continue
            
            # Same line
            val = find_date_in_line(i)
            if val:
                return ExtractedField(
                    field_name=f'{date_type}_date',
                    value=val,
                    ocr_text=text,
                    ocr_confidence=confidences[i],
                    extraction_confidence=min(confidences[i], 0.95),
                    confidence_level='HIGH',
                    bbox=bboxes[i],
                    reason=f"Date '{val}' found on {date_type} declaration line",
                    line_index=i
                )
            
            # Spatial: value on the same visual row as the label (columnar layout)
            same_row = []
            for j in range(len(texts)):
                if j == i:
                    continue
                if is_other_date_type_label(j):
                    continue
                cand_val = find_date_in_line(j)
                if not cand_val:
                    continue
                if own_line_is_address(j):
                    continue
                if self._vertical_overlap(bboxes[i], bboxes[j]) >= 0.2:
                    same_row.append((self._bbox_distance(bboxes[i], bboxes[j]), j, cand_val))
            if same_row:
                same_row.sort(key=lambda c: c[0])
                _, j, cand_val = same_row[0]
                return ExtractedField(
                    field_name=f'{date_type}_date',
                    value=cand_val,
                    ocr_text=f"{text} | {texts[j]}",
                    ocr_confidence=min(confidences[i], confidences[j]),
                    extraction_confidence=min(confidences[i], confidences[j], 0.85),
                    confidence_level='MEDIUM',
                    bbox=bboxes[j],
                    reason=f"Date '{cand_val}' spatially aligned with {date_type} label (same visual row)",
                    line_index=j
                )
            
            # Line-order adjacency fallback (OCR reading order)
            for j in range(max(0, i-2), min(len(texts), i+3)):
                if j == i:
                    continue
                if is_other_date_type_label(j):
                    continue
                cand_val = find_date_in_line(j)
                if not cand_val:
                    continue
                if own_line_is_address(j):
                    continue
                if candidate_claimed_by_other_type(j):
                    continue
                return ExtractedField(
                    field_name=f'{date_type}_date',
                    value=cand_val,
                    ocr_text=f"{text} | {texts[j]}",
                    ocr_confidence=min(confidences[i], confidences[j]),
                    extraction_confidence=min(confidences[i], confidences[j], 0.85),
                    confidence_level='MEDIUM',
                    bbox=bboxes[j],
                    reason=f"Date '{cand_val}' found near {date_type} label",
                    line_index=j
                )
        
        # Strategy: batch number lines often embed dates
        if date_type in ['manufacturing', 'packing']:
            instruction_context = re.compile(
                r'feedback|quer(?:y|ies)|complaint|mention|write to|call us|'
                r'consumer care|customer care|indicating',
                re.IGNORECASE
            )
            for i, text in enumerate(texts):
                if instruction_context.search(text):
                    continue
                if re.search(r'\b(batch no|b\.no|bno|batch|lot no|lot)\b', text, re.IGNORECASE):
                    for j in range(max(0, i-1), min(len(texts), i+4)):
                        if own_line_is_address(j):
                            continue
                        embedded = re.search(r'\b(\d{1,2}[A-Za-z]{3}\d{2,4})\b', texts[j])
                        if embedded:
                            val = embedded.group(1)
                            return ExtractedField(
                                field_name=f'{date_type}_date',
                                value=val,
                                ocr_text=texts[j],
                                ocr_confidence=confidences[j],
                                extraction_confidence=min(confidences[j], 0.75),
                                confidence_level='LOW',
                                bbox=bboxes[j],
                                reason=f"Embedded date '{val}' found in batch number line",
                                line_index=j
                            )
        
        return ExtractedField(
            field_name=f'{date_type}_date',
            value=None,
            ocr_text='',
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            confidence_level='MISSING',
            bbox=[],
            reason=f"No {date_type} date found",
            line_index=-1
        )
    
    def _extract_batch(self, texts: List[str], confidences: List[float],
                       bboxes: List[List[List[int]]]) -> ExtractedField:
        """Extract batch or lot number."""
        
        batch_patterns = [
            r'\bbatch\s*(?:no\.?|number)?\s*:?\s*([A-Za-z0-9\-/]+)',
            r'\bb\.?\s*no\.?\s*:?\s*([A-Za-z0-9\-/]+)',
            r'\blot\s*(?:no\.?|number)?\s*:?\s*([A-Za-z0-9\-/]+)',
        ]
        
        def is_valid_batch(val: str) -> bool:
            # Reject trivial values
            if len(val) < 2:
                return False
            if val.lower() in ['no', 'ne', 'number', 'lot', 'batch', 'and', 'the', 'for', 'of', 'in']:
                return False
            # Should have at least some alphanumeric mix or be reasonably long
            if val.isdigit() and len(val) < 4:
                return False
            # Reject if it's just a common English word
            common_words = ['and', 'the', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
                           'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has',
                           'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two',
                           'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she',
                           'too', 'use']
            if val.lower() in common_words:
                return False
            return True
        
        # Candidate value shapes for label-only lines (columnar layout):
        # short standalone alphanumeric codes like 'B05P', 'A25X77'
        batch_code_shape = re.compile(r'^[A-Za-z0-9][A-Za-z0-9\-/]{1,11}$')
        quantity_unit = re.compile(r'\b\d+\s*(?:mg|g|gm|kg|ml|l|kcal|cal|mcg|pcs)\b', re.IGNORECASE)
        date_like = re.compile(
            r'\b\d{1,2}[A-Za-z]{3}\d{2,4}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'
        )
        # Care/instruction lines mention 'batch no.' but are not declarations
        instruction_context = re.compile(
            r'feedback|quer(?:y|ies)|complaint|mention|write to|call us|'
            r'consumer care|customer care|indicating',
            re.IGNORECASE
        )
        # Nutrition table row headers must never be batch codes
        nutrition_word = re.compile(
            r'^(?:protein|fats?|carbs?|carbohydrates?|sugars?|fibre|fiber|sodium|'
            r'energy|calcium|iron|vitamins?\w*|cholesterol|moisture|ash|trans|'
            r'saturated|kcal|calories)$',
            re.IGNORECASE
        )
        
        label_line_idxs = []
        for i, text in enumerate(texts):
            if instruction_context.search(text):
                continue
            matched_label = False
            for pattern in batch_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    val = match.group(1)
                    if is_valid_batch(val):
                        return ExtractedField(
                            field_name='batch_number',
                            value=val,
                            ocr_text=text,
                            ocr_confidence=confidences[i],
                            extraction_confidence=min(confidences[i], 0.90),
                            confidence_level='HIGH',
                            bbox=bboxes[i],
                            reason=f"Batch number '{val}' extracted",
                            line_index=i
                        )
                    matched_label = True
            if matched_label:
                label_line_idxs.append(i)
        
        # Label found but value not on the same line: search spatially-aligned
        # or nearby lines for a standalone batch code (columnar label|value layout)
        for i in label_line_idxs:
            candidates = []
            for j in range(max(0, i-4), min(len(texts), i+5)):
                if j == i:
                    continue
                t = texts[j].strip()
                if not batch_code_shape.match(t):
                    continue
                tl = t.lower()
                if 'lic' in tl or 'fssai' in tl or 'pin' in tl:
                    continue
                if quantity_unit.search(t) or date_like.search(t):
                    continue
                if nutrition_word.match(t):
                    continue
                if self._is_reject(t):
                    continue
                if not is_valid_batch(t):
                    continue
                overlap = self._vertical_overlap(bboxes[i], bboxes[j])
                dist = self._bbox_distance(bboxes[i], bboxes[j])
                candidates.append((0 if overlap >= 0.2 else 1, dist, j, overlap))
            if candidates:
                candidates.sort(key=lambda c: (c[0], c[1]))
                _, _, j, overlap = candidates[0]
                spatial = overlap >= 0.2
                level = 'MEDIUM' if spatial else 'LOW'
                cap = 0.85 if spatial else 0.70
                return ExtractedField(
                    field_name='batch_number',
                    value=texts[j].strip(),
                    ocr_text=f"{texts[i]} | {texts[j]}",
                    ocr_confidence=min(confidences[i], confidences[j]),
                    extraction_confidence=min(confidences[i], confidences[j], cap),
                    confidence_level=level,
                    bbox=bboxes[j],
                    reason=(
                        f"Batch code '{texts[j].strip()}' spatially aligned with batch label"
                        if spatial else
                        f"Batch code '{texts[j].strip()}' found near batch label"
                    ),
                    line_index=j
                )
        
        return ExtractedField(
            field_name='batch_number',
            value=None,
            ocr_text='',
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            confidence_level='MISSING',
            bbox=[],
            reason="No batch/lot number found",
            line_index=-1
        )
    
    def _extract_consumer_care(self, texts: List[str], confidences: List[float],
                               bboxes: List[List[List[int]]]) -> ExtractedField:
        """Extract consumer care information (phone + email)."""
        
        care_keywords = [
            'customer care', 'consumer care', 'toll free', 'helpline',
            'contact', 'call us', 'for feedback', 'for queries', 'for complaints',
            'write to us', 'feedback', 'complaints', 'queries',
            'consumer relations', 'customer relations', 'relations representative',
            'consumer cell', 'contact us', 'consumer services'
        ]
        
        phone_pattern = re.compile(
            r'(?:\+?91[-\s]?)?(?:\d{5}[-\s]?\d{5}|\d{4}[-\s]?\d{3}[-\s]?\d{4}'
            r'|\d{3}[-\s]?\d{4}[-\s]?\d{4}|\d{3}[-\s]?\d{3}[-\s]?\d{4}'
            r'|\d{4}[-\s]?\d{2}[-\s]?\d{4}'
            r'|\d{5}[-\s]?\d{3}[-\s]?\d{3})'
        )
        email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        CARE_LOCAL_PARTS = ('info', 'care', 'support', 'contact', 'feedback', 'helpdesk', 'help', 'customercare')
        
        best_match = None
        best_conf = 0
        
        for i, text in enumerate(texts):
            lower = text.lower()
            if any(kw in lower for kw in care_keywords):
                # Look for phone/email on same or adjacent lines
                context_lines = [texts[j] for j in range(max(0, i-1), min(len(texts), i+3))]
                context = ' | '.join(context_lines)
                
                phone = phone_pattern.search(context)
                email = email_pattern.search(context)
                
                if phone or email:
                    parts = []
                    if phone:
                        parts.append(f"Phone: {phone.group()}")
                    if email:
                        parts.append(f"Email: {email.group()}")
                    
                    val = ' | '.join(parts)
                    conf = confidences[i]
                    
                    if conf > best_conf:
                        best_conf = conf
                        best_match = ExtractedField(
                            field_name='consumer_care',
                            value=val,
                            ocr_text=context,
                            ocr_confidence=conf,
                            extraction_confidence=min(conf, 0.90),
                            confidence_level='HIGH',
                            bbox=bboxes[i],
                            reason=f"Consumer care info found: {val}",
                            line_index=i
                        )
        
        if best_match:
            return best_match
        
        # Fallback: find any email or phone that looks like customer care
        for i, text in enumerate(texts):
            email = email_pattern.search(text)
            if email:
                local_part = email.group().split('@')[0].lower()
                domain = email.group().split('@')[1].lower()
                care_domains = ['care', 'support', 'help', 'service', 'feedback', 'customercare', 'consumer']
                if any(d in domain for d in care_domains) or local_part in CARE_LOCAL_PARTS:
                    reason_detail = (
                        f"care email local part '{local_part}'"
                        if local_part in CARE_LOCAL_PARTS
                        else f"care email domain '{domain}'"
                    )
                    return ExtractedField(
                        field_name='consumer_care',
                        value=f"Email: {email.group()}",
                        ocr_text=text,
                        ocr_confidence=confidences[i],
                        extraction_confidence=min(confidences[i], 0.75),
                        confidence_level='MEDIUM',
                        bbox=bboxes[i],
                        reason=f"Consumer care info found ({reason_detail})",
                        line_index=i
                    )
        
        return ExtractedField(
            field_name='consumer_care',
            value=None,
            ocr_text='',
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            confidence_level='MISSING',
            bbox=[],
            reason="No consumer care information found",
            line_index=-1
        )
    
    def _extract_country_of_origin(self, texts: List[str], confidences: List[float],
                                   bboxes: List[List[List[int]]]) -> ExtractedField:
        """Extract country of origin."""
        
        origin_patterns = [
            (r'\bcountry of origin\s*:?\s*([A-Za-z\s]+)', 'country of origin'),
            (r'\bproduct of\s+([A-Za-z\s]+)', 'product of'),
            (r'\bmade in\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\b', 'made in'),
        ]
        
        valid_countries = ['india', 'china', 'usa', 'america', 'united states', 'uk', 'united kingdom',
                          'thailand', 'vietnam', 'bangladesh', 'nepal', 'sri lanka', 'pakistan',
                          'malaysia', 'singapore', 'indonesia', 'japan', 'korea', 'germany',
                          'france', 'italy', 'spain', 'netherlands', 'australia', 'canada',
                          'brazil', 'mexico', 'uae', 'dubai', 'saudi arabia', 'turkey']
        
        for i, text in enumerate(texts):
            for pattern, label in origin_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    val = match.group(1).strip()
                    # Validate it's actually a country
                    if any(country in val.lower() for country in valid_countries):
                        return ExtractedField(
                            field_name='country_of_origin',
                            value=val,
                            ocr_text=text,
                            ocr_confidence=confidences[i],
                            extraction_confidence=min(confidences[i], 0.90),
                            confidence_level='HIGH',
                            bbox=bboxes[i],
                            reason=f"Country of origin: {val}",
                            line_index=i
                        )
                    # If it says "made in a facility" etc., reject
                    if re.search(r'(facility|plant|factory|premises)', val, re.IGNORECASE):
                        continue
        
        return ExtractedField(
            field_name='country_of_origin',
            value=None,
            ocr_text='',
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            confidence_level='MISSING',
            bbox=[],
            reason="No country of origin found",
            line_index=-1
        )

    # ------------------------------------------------------------------
    # Brand name (Rule 6(1)(b) - the brand/trade name printed on the label,
    # distinct from the generic commodity name)
    # ------------------------------------------------------------------

    BRAND_LABEL_RE = re.compile(
        r'\b(?:brand(?:\s*name)?|marketed\s*(?:by|under)|a\s+brand\s+of)\b\s*[:\-]?\s*(.*)',
        re.IGNORECASE,
    )
    # OCR renders trademark marks as the glyph or as an ASCII fallback
    TRADEMARK_RE = re.compile(r'[\u2122\u00ae\u00a9]|\((?i:tm|r|c)\)|(?<=[A-Za-z])\s?TM\b')

    # A brand is a proper noun, not a declaration, address or nutrition row.
    BRAND_SKIP_RE = re.compile(
        r'm\.?r\.?p|retail\s*price|unit\s*sale|taxes|incl\b'
        r'|net\s*(wt|weight|qty|quant)'
        r'|mfg|mfd|manufactur|facture|packed|pkd|batch|lot\b'
        r'|best\s*before|use\s*by|useby|\bexp\b|licen|lic\.?\s*no|fssa'
        r'|ingredient|nutrition|energy|protein|fat\b|carbohydrate|sodium'
        r'|calcium|vitamin|sugar|cholesterol|serving|kcal|per\s*100'
        r'|consumer|customer|helpline|toll|call\s*us|contact|email|phone'
        r'|feedback|address|pin\b|road|street|plot\b|estate|industrial'
        r'|product\s*of|made\s*in|country\s*of\s*origin'
        # place names: an address line is not a brand
        r'|maharashtra|gujarat|haryana|karnataka|tamil|kerala|andhra|telangana'
        r'|bengal|rajasthan|punjab|pradesh|bihar|odisha|assam|delhi|mumbai'
        r'|chennai|kolkata|hyderabad|bangalore|bengaluru|ahmedabad|surat'
        r'|jaipur|lucknow|indore|nagpur|gurugram|\bindia\b'
        r'|store\b|keep\b|warning|contains|allergen|see\s+(the\s+)?(base|neck|first)'
        r'|base\s*of\s*can|qr\s*code|bar\s*code|www|\.com|@',
        re.IGNORECASE,
    )
    # Legal-entity suffixes mark a manufacturer/packer line, not a brand mark
    ENTITY_SUFFIX_RE = re.compile(
        r'\b(pvt|private|ltd|limited|llp|inc|corp|corporation|co\.?|company|'
        r'industries|enterprises|foods?\s+pvt|&\s*sons)\b',
        re.IGNORECASE,
    )

    def _extract_brand(self, texts: List[str], confidences: List[float],
                       bboxes: List[List[List[int]]],
                       exclude_idx: int = -1) -> ExtractedField:
        """Extract the brand / trade name.

        Priority:
          1. An explicit ``Brand:`` label (same line, then next line).
          2. A trademark-marked word (``ACME(TM)``).
          3. The most prominent proper-noun block that is NOT the block already
             claimed as the generic commodity name.

        Returning None is correct when the label carries only a generic name -
        a brand is not a mandatory declaration under LM(PC)R 2011, so an
        absent brand must never be invented.
        """

        def clean(value: str) -> str:
            value = self.TRADEMARK_RE.sub('', value).strip()
            return value.strip(' :-–—.,')

        # 1. Explicit label
        for i, text in enumerate(texts):
            match = self.BRAND_LABEL_RE.search(text or '')
            if not match:
                continue
            value = clean(match.group(1))
            if not value and i + 1 < len(texts):
                value = clean(texts[i + 1])
                if value and 2 <= len(value) <= 40:
                    return ExtractedField(
                        field_name='brand',
                        value=value,
                        ocr_text=f"{texts[i]} | {texts[i + 1]}",
                        ocr_confidence=min(confidences[i], confidences[i + 1]),
                        extraction_confidence=min(
                            min(confidences[i], confidences[i + 1]), 0.90
                        ),
                        confidence_level='HIGH',
                        bbox=bboxes[i + 1] if bboxes[i + 1] else bboxes[i],
                        reason="Brand label with value on the following line",
                        line_index=i + 1,
                    )
                continue
            if value and 2 <= len(value) <= 40:
                return ExtractedField(
                    field_name='brand',
                    value=value,
                    ocr_text=texts[i],
                    ocr_confidence=confidences[i],
                    extraction_confidence=min(confidences[i], 0.92),
                    confidence_level='HIGH',
                    bbox=bboxes[i],
                    reason="Explicit brand label on the package",
                    line_index=i,
                )

        # 2. Trademark marker
        for i, text in enumerate(texts):
            t = (text or '').strip()
            if not self.TRADEMARK_RE.search(t):
                continue
            value = clean(t)
            if not (2 <= len(value) <= 40) or self.BRAND_SKIP_RE.search(value):
                continue
            return ExtractedField(
                field_name='brand',
                value=value,
                ocr_text=text,
                ocr_confidence=confidences[i],
                extraction_confidence=min(confidences[i], 0.88),
                confidence_level='HIGH',
                bbox=bboxes[i],
                reason="Trademark symbol marks this text as the brand name",
                line_index=i,
            )

        # 3. Prominent proper-noun block distinct from the commodity name
        best_idx, best_score = None, 0.0
        for i, text in enumerate(texts):
            if i == exclude_idx:
                continue
            t = (text or '').strip()
            if not (2 <= len(t) <= 30) or confidences[i] < 0.85:
                continue
            if self.BRAND_SKIP_RE.search(t) or self.ENTITY_SUFFIX_RE.search(t):
                continue
            if self._is_reject(t):
                continue
            words = t.split()
            if len(words) > 3:
                continue
            letters = sum(c.isalpha() for c in t)
            if letters / max(1, len(t.replace(' ', ''))) < 0.8:
                continue
            # brands are printed as capitals or Title Case
            if not (t.isupper() or t == t.title()):
                continue
            if not bboxes[i]:
                continue
            try:
                ys = [p[1] for p in bboxes[i]]
                xs = [p[0] for p in bboxes[i]]
                area = max(1, max(ys) - min(ys)) * max(1, max(xs) - min(xs))
            except Exception:
                continue
            score = area * float(confidences[i])
            if score > best_score:
                best_score, best_idx = score, i

        if best_idx is not None:
            return ExtractedField(
                field_name='brand',
                value=texts[best_idx].strip(),
                ocr_text=texts[best_idx],
                ocr_confidence=confidences[best_idx],
                # inferred, not labelled - capped so it can never auto-PASS a rule
                extraction_confidence=min(confidences[best_idx], 0.62),
                confidence_level='LOW',
                bbox=bboxes[best_idx],
                reason=(
                    "Prominent proper-noun text distinct from the commodity "
                    "name - inferred brand, not an explicit declaration"
                ),
                line_index=best_idx,
            )

        return ExtractedField(
            field_name='brand',
            value=None,
            ocr_text='',
            ocr_confidence=0.0,
            extraction_confidence=0.0,
            confidence_level='MISSING',
            bbox=[],
            reason="No brand or trade name found on the captured surfaces",
            line_index=-1,
        )
