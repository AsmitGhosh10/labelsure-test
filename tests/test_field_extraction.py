import sys
sys.path.insert(0, '/Users/mohit/Documents/Default Project')

import pytest
from backend.app.services.field_extraction import FieldExtractor, ExtractedField

class TestFieldExtractor:
    def setup_method(self):
        self.extractor = FieldExtractor()
    
    # --- MRP Tests ---
    def test_mrp_standard_format(self):
        texts = ["MRP: Rs. 250.00", "Net Wt: 500g"]
        confs = [0.99, 0.98]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]], [[0,60],[100,60],[100,110],[0,110]]]
        result = self.extractor._extract_mrp(texts, confs, bboxes)
        assert result.value is not None
    
    def test_mrp_rupee_symbol(self):
        texts = ["MRP ₹20"]
        confs = [0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]]]
        result = self.extractor._extract_mrp(texts, confs, bboxes)
        assert result.value is not None
        assert '20' in result.value
    
    def test_mrp_dot_format(self):
        """M.R.P. (Inclusive of all taxes).20.00"""
        texts = ["M.R.P. (Inclusive of all taxes).20.00"]
        confs = [0.99]
        bboxes = [[[0,0],[200,0],[200,50],[0,50]]]
        result = self.extractor._extract_mrp(texts, confs, bboxes)
        assert result.value is not None
        assert '20' in result.value
    
    def test_mrp_no_space(self):
        texts = ["MRP:Rs.20"]
        confs = [0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]]]
        result = self.extractor._extract_mrp(texts, confs, bboxes)
        assert result.value is not None
    
    def test_mrp_reject_nutrition_value(self):
        """11.23g near 'Total Fat' should NOT be MRP"""
        texts = ["Total Fat", "11.23g"]
        confs = [0.99, 0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]], [[0,60],[100,60],[100,110],[0,110]]]
        result = self.extractor._extract_mrp(texts, confs, bboxes)
        assert result.value is None or result.confidence_level == 'MISSING'
    
    def test_mrp_reject_fssai_number(self):
        texts = ["FSSAI Lic. No. 10012013000346"]
        confs = [0.99]
        bboxes = [[[0,0],[200,0],[200,50],[0,50]]]
        result = self.extractor._extract_mrp(texts, confs, bboxes)
        assert result.value is None or result.confidence_level == 'MISSING'
    
    def test_mrp_missing(self):
        texts = ["Net Wt: 500g", "Manufactured by ABC"]
        confs = [0.99, 0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]], [[0,60],[100,60],[100,110],[0,110]]]
        result = self.extractor._extract_mrp(texts, confs, bboxes)
        assert result.confidence_level == 'MISSING'
    
    def test_mrp_max_retail_price(self):
        texts = ["MAX RETAIL PRICE ₹50"]
        confs = [0.99]
        bboxes = [[[0,0],[150,0],[150,50],[0,50]]]
        result = self.extractor._extract_mrp(texts, confs, bboxes)
        assert result.value is not None
        assert '50' in result.value
    
    def test_mrp_surrounded_by_numbers(self):
        """Address with PIN, phone, and MRP"""
        texts = [
            "Dist. Navsari-396445 Guj-India",
            "Customer Care: 8511082737",
            "MRP. Rs. 30.00"
        ]
        confs = [0.99, 0.99, 0.99]
        bboxes = [[[0,0],[200,0],[200,50],[0,50]], [[0,60],[200,60],[200,110],[0,110]], [[0,120],[200,120],[200,170],[0,170]]]
        result = self.extractor._extract_mrp(texts, confs, bboxes)
        assert result.value is not None
        assert '30' in result.value
        assert '396445' not in (result.value or '')
        assert '8511082737' not in (result.value or '')
    
    # --- Net Quantity Tests ---
    def test_net_qty_explicit_label(self):
        texts = ["Net Wt. : 85 g"]
        confs = [0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]]]
        result = self.extractor._extract_net_quantity(texts, confs, bboxes)
        assert result.value is not None
        assert '85' in result.value
    
    def test_net_qty_reject_nutrition(self):
        texts = ["Total Fat 11.23g", "Total Protein 4.3g"]
        confs = [0.99, 0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]], [[0,60],[100,60],[100,110],[0,110]]]
        result = self.extractor._extract_net_quantity(texts, confs, bboxes)
        # Should not extract nutrition values
        assert result.confidence_level == 'MISSING' or result.value is None
    
    def test_net_qty_500g(self):
        texts = ["Net Qty: 500g"]
        confs = [0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]]]
        result = self.extractor._extract_net_quantity(texts, confs, bboxes)
        assert result.value == "500g"
    
    # --- Date Tests ---
    def test_date_dd_mm_yyyy(self):
        texts = ["Mfg. Date: 15/08/2024"]
        confs = [0.99]
        bboxes = [[[0,0],[150,0],[150,50],[0,50]]]
        result = self.extractor._extract_date(texts, confs, bboxes, 'manufacturing')
        assert result.value == "15/08/2024"
    
    def test_date_batch_embedded(self):
        texts = ["BATCH NO.: A25X77", "17Jul28"]
        confs = [0.99, 0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]], [[0,60],[100,60],[100,110],[0,110]]]
        result = self.extractor._extract_date(texts, confs, bboxes, 'manufacturing')
        assert result.value == "17Jul28"
    
    def test_date_reject_address_date(self):
        """Date inside address should not be manufacturing date"""
        texts = ["Malivada Road, Junagadh-362 001"]
        confs = [0.99]
        bboxes = [[[0,0],[200,0],[200,50],[0,50]]]
        result = self.extractor._extract_date(texts, confs, bboxes, 'manufacturing')
        assert result.confidence_level == 'MISSING'
    
    def test_date_columnar_layout_label_left_value_right(self):
        """image4 pattern: 'MFD.' label and its date on different OCR lines,
        same visual row, with an address column interleaved in reading order."""
        texts = [
            "BATCH NO.",                                   # label col, y 0-36
            "C/O India Food Park. Plot No. 26B.",          # address col, y 40-80
            "B05P",                                        # value col, y 28-54
            "15Nov28",                                     # value col, y 60-84
            "MFD.",                                        # label col, y 73-106
            "Bathsandra, Tumkur, Karnataka, Pin: 572138.", # address col, y 64-85
        ]
        confs = [0.99] * 6
        bboxes = [
            [[17,0],[178,0],[178,36],[17,36]],
            [[654,40],[926,40],[926,80],[654,80]],
            [[183,28],[242,28],[242,54],[183,54]],
            [[185,60],[282,60],[282,84],[185,84]],
            [[10,73],[91,73],[91,106],[10,106]],
            [[654,64],[926,64],[926,85],[654,85]],
        ]
        result = self.extractor._extract_date(texts, confs, bboxes, 'manufacturing')
        assert result.value == "15Nov28"
        assert result.confidence_level == 'MEDIUM'
        assert 'spatially aligned' in result.reason
    
    def test_date_own_line_address_candidate_rejected(self):
        """A date-looking value on an address line is rejected even next to label."""
        texts = ["MFD.", "Plot 15/07/2026 Road"]
        confs = [0.99, 0.99]
        bboxes = [
            [[10,73],[91,73],[91,106],[10,106]],
            [[185,73],[350,73],[350,106],[185,106]],
        ]
        result = self.extractor._extract_date(texts, confs, bboxes, 'manufacturing')
        assert result.confidence_level == 'MISSING'
    
    def test_date_far_away_candidate_not_matched(self):
        """Date candidate on a different visual row AND beyond the line window
        must not be attributed to the label."""
        texts = ["MFD.", "random line", "another line", "yet another", "15Nov28"]
        confs = [0.99] * 5
        bboxes = [
            [[10,73],[91,73],[91,106],[10,106]],
            [[10,200],[200,200],[200,250],[10,250]],
            [[10,300],[200,300],[200,350],[10,350]],
            [[10,400],[200,400],[200,450],[10,450]],
            [[185,600],[282,600],[282,624],[185,624]],
        ]
        result = self.extractor._extract_date(texts, confs, bboxes, 'manufacturing')
        assert result.confidence_level == 'MISSING'
    
    def test_date_best_before_not_stolen_by_mfd_row(self):
        """A date on the same row as MFD must not satisfy a best-before label."""
        texts = ["MFD.", "15Nov28", "Best Before:"]
        confs = [0.99, 0.99, 0.99]
        bboxes = [
            [[10,73],[91,73],[91,106],[10,106]],
            [[185,73],[282,73],[282,97],[185,97]],
            [[10,150],[200,150],[200,183],[10,183]],
        ]
        result = self.extractor._extract_date(texts, confs, bboxes, 'best_before')
        assert result.confidence_level == 'MISSING'
    
    def test_date_best_before(self):
        texts = ["Best Before: 28/02/25"]
        confs = [0.99]
        bboxes = [[[0,0],[150,0],[150,50],[0,50]]]
        result = self.extractor._extract_date(texts, confs, bboxes, 'best_before')
        assert result.value == "28/02/25"
    
    # --- Manufacturer Tests ---
    def test_manufacturer_found(self):
        texts = ["Manufactured By:", "ABC Foods Pvt. Ltd."]
        confs = [0.99, 0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]], [[0,60],[100,60],[100,110],[0,110]]]
        result = self.extractor._extract_entity(texts, confs, bboxes, 'manufacturer')
        assert result.value is not None
        assert 'ABC' in result.value
    
    def test_manufacturer_marketed_by(self):
        texts = ["Marketed By: XYZ Corp"]
        confs = [0.99]
        bboxes = [[[0,0],[150,0],[150,50],[0,50]]]
        result = self.extractor._extract_entity(texts, confs, bboxes, 'manufacturer')
        assert result.value is not None
    
    # --- Batch Tests ---
    def test_batch_number(self):
        texts = ["Batch No.: A25X77"]
        confs = [0.99]
        bboxes = [[[0,0],[150,0],[150,50],[0,50]]]
        result = self.extractor._extract_batch(texts, confs, bboxes)
        assert result.value == "A25X77"
    
    def test_batch_label_only_value_same_row(self):
        """image4 pattern: 'BATCH NO.' label with value 'B05P' on a different
        OCR line, same visual row (columnar layout)."""
        texts = ["BATCH NO.", "B05P"]
        confs = [0.99, 0.99]
        bboxes = [
            [[17,0],[178,0],[178,36],[17,36]],
            [[183,28],[242,28],[242,54],[183,54]],
        ]
        result = self.extractor._extract_batch(texts, confs, bboxes)
        assert result.value == "B05P"
        assert result.confidence_level == 'MEDIUM'
    
    def test_batch_rejects_date_like_and_quantity_candidates(self):
        """Date-like strings and quantity values near the batch label are not
        batch numbers."""
        texts = ["BATCH NO.", "17Jul28", "48g", "B05P"]
        confs = [0.99] * 4
        bboxes = [
            [[17,0],[178,0],[178,36],[17,36]],
            [[183,40],[283,40],[283,68],[183,68]],
            [[183,70],[242,70],[242,96],[183,96]],
            [[183,28],[242,28],[242,54],[183,54]],
        ]
        result = self.extractor._extract_batch(texts, confs, bboxes)
        assert result.value == "B05P"
    
    def test_batch_instruction_line_not_label(self):
        """Care instruction 'mention batch no...' is not a batch declaration;
        nutrition row headers on its row are not batch codes."""
        texts = [
            "For Feedback & queries (mention batch no. and manufacturing date),",
            "Protein",
            "14g",
        ]
        confs = [0.99] * 3
        bboxes = [
            [[17,0],[420,0],[420,30],[17,30]],
            [[183,40],[260,40],[260,66],[183,66]],
            [[300,40],[340,40],[340,66],[300,66]],
        ]
        result = self.extractor._extract_batch(texts, confs, bboxes)
        assert result.confidence_level == 'MISSING'
    
    def test_batch_label_only_no_valid_candidate(self):
        texts = ["BATCH NO.", "Total Fat 11.23g", "Lic. No.10021031000393"]
        confs = [0.99] * 3
        bboxes = [
            [[17,0],[178,0],[178,36],[17,36]],
            [[183,28],[350,28],[350,54],[183,54]],
            [[183,60],[400,60],[400,86],[183,60]],
        ]
        result = self.extractor._extract_batch(texts, confs, bboxes)
        assert result.confidence_level == 'MISSING'
    
    # --- Consumer Care Tests ---
    def test_consumer_care_phone_email(self):
        texts = ["Customer Care: 1800-123-4567", "Email: care@abc.com"]
        confs = [0.99, 0.99]
        bboxes = [[[0,0],[150,0],[150,50],[0,50]], [[0,60],[150,60],[150,110],[0,110]]]
        result = self.extractor._extract_consumer_care(texts, confs, bboxes)
        assert result.value is not None
        assert '1800-123-4567' in result.value
        assert 'care@abc.com' in result.value
    
    def test_consumer_care_missing(self):
        texts = ["Net Wt: 500g", "MRP: Rs. 50"]
        confs = [0.99, 0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]], [[0,60],[100,60],[100,110],[0,110]]]
        result = self.extractor._extract_consumer_care(texts, confs, bboxes)
        assert result.confidence_level == 'MISSING'
    
    # --- Country of Origin Tests ---
    def test_country_of_origin(self):
        texts = ["Product of India"]
        confs = [0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]]]
        result = self.extractor._extract_country_of_origin(texts, confs, bboxes)
        assert result.value == "India"
    
    # --- Full Pipeline Test ---
    def test_full_pipeline_compliant_package(self):
        texts = [
            "Premium Biscuits",
            "Net Qty: 500g",
            "MRP: Rs. 250.00",
            "Manufactured By: ABC Foods Pvt. Ltd.",
            "Mfg. Date: 15/08/2024",
            "Best Before: 6 months",
            "Customer Care: 1800-123-4567",
            "Email: care@abcfoods.com",
            "Product of India"
        ]
        confs = [0.99] * len(texts)
        bboxes = [[[0, i*60],[200, i*60],[200, i*60+50],[0, i*60+50]] for i in range(len(texts))]
        
        results = self.extractor.extract_all(texts, confs, bboxes)
        
        assert results['mrp'].value is not None
        assert results['net_quantity'].value is not None
        assert results['manufacturer'].value is not None
        assert results['manufacturing_date'].value is not None
        assert results['consumer_care'].value is not None
        assert results['country_of_origin'].value is not None
    
    def test_full_pipeline_missing_mrp(self):
        texts = [
            "Net Qty: 500g",
            "Manufactured By: ABC Foods",
        ]
        confs = [0.99, 0.99]
        bboxes = [[[0,0],[100,0],[100,50],[0,50]], [[0,60],[100,60],[100,110],[0,110]]]
        
        results = self.extractor.extract_all(texts, confs, bboxes)
        assert results['mrp'].confidence_level == 'MISSING'
        assert results['net_quantity'].value is not None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestEntityIsNotACommodityName:
    """A company name is not the commodity, and an address is not a brand.

    Seen on a real inspection of test_packages/demo_snack, whose back label
    carries the manufacturer on one line and its address on the next:

        product_name  "ABC Foods Pvt. Ltd."
        brand         "Mumbai, Maharashtra, India"

    Both are prominent, neither carries a declaration label, so the
    largest-block heuristics took them.
    """

    BACK_LABEL = [
        "ABC Foods Pvt. Ltd.",
        "Mumbai, Maharashtra, India",
        "Mfg Date: 15/01/2026",
        "Batch No: A25X77",
        "Consumer Care: 1800-123-4567",
    ]

    def _extract(self, texts):
        from backend.app.services.field_extraction import FieldExtractor

        bboxes = [
            [[20, i * 60], [400, i * 60], [400, i * 60 + 44], [20, i * 60 + 44]]
            for i in range(len(texts))
        ]
        return FieldExtractor().extract_all(texts, [0.95] * len(texts), bboxes)

    def test_a_company_name_is_not_the_product_name(self):
        fields = self._extract(self.BACK_LABEL)
        assert fields["product_name"].value != "ABC Foods Pvt. Ltd."

    def test_an_address_line_is_not_the_brand(self):
        fields = self._extract(self.BACK_LABEL)
        assert fields["brand"].value != "Mumbai, Maharashtra, India"

    def test_the_company_is_still_read_as_the_manufacturer(self):
        """Rejecting it as a product name must not lose it entirely."""
        fields = self._extract(["Manufactured By: ABC Foods Pvt. Ltd."] + self.BACK_LABEL[1:])
        assert fields["manufacturer"].value
        assert "ABC Foods" in fields["manufacturer"].value

    def test_missing_commodity_name_is_reported_not_invented(self):
        """Rule 6(1)(b) makes an absent common name a finding - filling it in
        from the letterhead would hide the violation."""
        fields = self._extract(self.BACK_LABEL)
        name = fields["product_name"]
        if name.value is None:
            assert name.confidence_level == "MISSING"
        else:
            # whatever it picked, it must not be an entity or an address
            assert "pvt" not in name.value.lower()
            assert "ltd" not in name.value.lower()

    @pytest.mark.parametrize(
        "entity",
        [
            "ABC Foods Pvt. Ltd.",
            "Sunrise Industries Limited",
            "Global Snacks LLP",
            "Acme Corporation",
        ],
    )
    def test_legal_entity_suffixes_are_rejected_as_product_names(self, entity):
        fields = self._extract([entity, "Some Prominent Words"])
        assert fields["product_name"].value != entity

    @pytest.mark.parametrize(
        "address",
        [
            "Mumbai, Maharashtra, India",
            "Pune 411001, Maharashtra",
            "Nagpur, India",
        ],
    )
    def test_place_names_are_rejected_as_brands(self, address):
        fields = self._extract([address, "Mfg Date: 01/2026"])
        assert fields["brand"].value != address

    def test_a_real_commodity_name_still_wins(self):
        """The guards must not suppress a genuine product name."""
        fields = self._extract(
            ["ABC Foods Pvt. Ltd.", "Crispy Potato Wafers", "Net Qty: 100 g"]
        )
        assert fields["product_name"].value == "Crispy Potato Wafers"
