# SPDX-License-Identifier: Apache-2.0
"""Unit tests for SKU address model, enums, and D9 heuristic."""

from __future__ import annotations

import pytest

from cerebra.cognition.sku import (
    D9Modality,
    D10Provenance,
    SKUAddress,
    d9_from_detected_type,
)


@pytest.mark.unit
class TestSKUAddressFormat:
    def test_hex_string_format(self) -> None:
        sku = SKUAddress(d1=0x2)  # MECHANISM
        assert sku.to_hex_string() == "200000.00.00"

    def test_all_zeros(self) -> None:
        sku = SKUAddress(d1=0x0)
        assert sku.to_hex_string() == "000000.00.00"

    def test_max_values(self) -> None:
        sku = SKUAddress(
            d1=0xF, d2=0xF, d3=0xF, d4=0xF, d5=0xF, d6=0xF, d7=0xF, d8=0xF, d9=0x7, d10=0x6
        )
        s = sku.to_hex_string()
        assert s == "FFFFFF.FF.76"

    def test_entry_index_encoding(self) -> None:
        # entry byte = d7 * 16 + d8
        sku = SKUAddress(d1=0x8, d7=0x0, d8=0x5)  # entry index 5
        assert sku.entry_index == 5
        assert sku.to_hex_string() == "800000.05.00"

    def test_entry_index_high_value(self) -> None:
        sku = SKUAddress(d1=0x4, d7=0x1, d8=0x0)  # entry index 16
        assert sku.entry_index == 16
        assert "10" in sku.to_hex_string()

    def test_round_trip_from_hex_string(self) -> None:
        original = SKUAddress(d1=0x2, d9=0x0, d10=0x0, d7=0x0, d8=0x3)
        s = original.to_hex_string()
        parsed = SKUAddress.from_hex_string(s)
        assert parsed.d1 == original.d1
        assert parsed.d7 == original.d7
        assert parsed.d8 == original.d8
        assert parsed.entry_index == original.entry_index

    def test_round_trip_various_addresses(self) -> None:
        for d1 in range(16):
            sku = SKUAddress(d1=d1, d7=0xA, d8=0x3, d9=0x0)
            assert SKUAddress.from_hex_string(sku.to_hex_string()).d1 == d1

    def test_invalid_digit_raises(self) -> None:
        with pytest.raises(ValueError):
            SKUAddress(d1=0x10)  # out of range

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError):
            SKUAddress.from_hex_string("bad-format")

    def test_location_tuple_all_zeros_except_d1(self) -> None:
        sku = SKUAddress(d1=0x5)
        t = sku.as_location_tuple()
        assert t == (0x5, 0, 0, 0, 0, 0, 0, 0)


@pytest.mark.unit
class TestD9Heuristic:
    def test_markdown_is_text(self) -> None:
        assert d9_from_detected_type("markdown") == D9Modality.TEXT

    def test_text_is_text(self) -> None:
        assert d9_from_detected_type("text") == D9Modality.TEXT

    def test_unknown_is_unknown(self) -> None:
        assert d9_from_detected_type("unknown") == D9Modality.UNKNOWN

    def test_code_is_code(self) -> None:
        assert d9_from_detected_type("code") == D9Modality.CODE

    def test_unrecognized_is_unknown(self) -> None:
        assert d9_from_detected_type("pdf") == D9Modality.UNKNOWN

    def test_case_insensitive(self) -> None:
        assert d9_from_detected_type("MARKDOWN") == D9Modality.TEXT


@pytest.mark.unit
class TestD10Provenance:
    def test_observed_is_zero(self) -> None:
        assert D10Provenance.OBSERVED == 0x0

    def test_synthesized_is_distinct(self) -> None:
        assert D10Provenance.SYNTHESIZED != D10Provenance.OBSERVED


@pytest.mark.unit
class TestSKUAssignmentAsDict:
    def test_as_dict_has_all_keys(self) -> None:
        from cerebra.cognition.sku import SKUAssignment

        sku = SKUAddress(d1=0x2)
        a = SKUAssignment(
            assignment_id="asgn_test",
            record_id="rec_test",
            sku_address=sku,
            raw_scores={"MECHANISM": 0.9},
            d1_confidence=0.9,
            classifier_version="1.0.0",
            prompt_version="1.0.0",
            subcategory_strategy_version="v1-stub",
            model_string="cerebra-classifier",
            latency_ms=500,
            input_tokens=800,
            output_tokens=150,
            created_at=0,
        )
        d = a.as_dict()
        required = {
            "assignment_id",
            "record_id",
            "sku_address",
            "d1",
            "d2",
            "d3",
            "d4",
            "d5",
            "d6",
            "d7",
            "d8",
            "d9",
            "d10",
            "raw_scores_json",
            "d1_confidence",
            "classifier_version",
            "prompt_version",
            "subcategory_strategy_version",
            "model_string",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "created_at",
            "schema_version",
        }
        assert required.issubset(d.keys())
        assert d["sku_address"] == "200000.00.00"
