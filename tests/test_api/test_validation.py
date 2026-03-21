# -*- coding: utf-8 -*-
"""Tests for parameter validation utilities.

Tests the validation helper functions.
"""

import pytest


class TestParseIntParam:
    """Test the parse_int_param helper function."""

    def test_valid_integer(self):
        """Valid integer should be parsed correctly."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"offset": ["10"]}, "offset", default=0)
        assert value == 10
        assert error is None

    def test_missing_param_returns_default(self):
        """Missing parameter should return default value."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({}, "offset", default=0)
        assert value == 0
        assert error is None

    def test_empty_string_returns_default(self):
        """Empty string should be treated as missing and return default."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"offset": [""]}, "offset", default=0)
        assert value == 0
        assert error is None

    def test_whitespace_is_stripped(self):
        """Whitespace should be stripped before parsing."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"offset": ["  42  "]}, "offset", default=0)
        assert value == 42
        assert error is None

    def test_invalid_non_numeric_returns_error(self):
        """Non-numeric value should return error message."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"offset": [":"]}, "offset", default=0)
        assert value is None
        assert "offset" in error
        assert ":" in error

    def test_invalid_alpha_returns_error(self):
        """Alphabetic value should return error message."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"limit": ["abc"]}, "limit", default=20)
        assert value is None
        assert "limit" in error
        assert "abc" in error

    def test_negative_with_non_negative_true_returns_error(self):
        """Negative value with non_negative=True should return error."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"limit": ["-5"]}, "limit", default=20)
        assert value is None
        assert "-5" in error

    def test_negative_with_non_negative_false_allowed(self):
        """Negative value with non_negative=False should be allowed."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"offset": ["-5"]}, "offset", default=0, non_negative=False)
        assert value == -5
        assert error is None

    def test_max_value_caps_value(self):
        """Value exceeding max_value should be capped, not error."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"limit": ["5000"]}, "limit", default=20, max_value=1000)
        assert value == 1000
        assert error is None

    def test_max_value_at_boundary(self):
        """Value at max_value boundary should not be capped."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"limit": ["1000"]}, "limit", default=20, max_value=1000)
        assert value == 1000
        assert error is None

    def test_required_missing_returns_error(self):
        """Required parameter that is missing should return error."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({}, "offset", required=True)
        assert value is None
        assert "required" in error.lower()
        assert "offset" in error

    def test_zero_is_valid(self):
        """Zero should be a valid non-negative integer."""
        from moonstone.webbridge.validation import parse_int_param

        value, error = parse_int_param({"offset": ["0"]}, "offset", default=0)
        assert value == 0
        assert error is None


class TestValidateParams:
    """Test the validate_params helper function."""

    def test_multiple_valid_params(self):
        """Multiple valid parameters should all be parsed."""
        from moonstone.webbridge.validation import validate_params

        validations = [
            ("offset", {"default": 0}),
            ("limit", {"default": 20, "max_value": 1000}),
        ]
        result, error = validate_params({"offset": ["10"], "limit": ["50"]}, validations)
        assert result == {"offset": 10, "limit": 50}
        assert error is None

    def test_first_invalid_param_returns_error(self):
        """Should return error on first invalid parameter."""
        from moonstone.webbridge.validation import validate_params

        validations = [
            ("offset", {"default": 0}),
            ("limit", {"default": 20}),
        ]
        result, error = validate_params({"offset": [":"]}, validations)
        assert result is None
        assert "offset" in error.get("error", "")

    def test_defaults_applied_for_missing(self):
        """Missing parameters should get default values."""
        from moonstone.webbridge.validation import validate_params

        validations = [
            ("offset", {"default": 0}),
            ("limit", {"default": 20}),
        ]
        result, error = validate_params({}, validations)
        assert result == {"offset": 0, "limit": 20}
        assert error is None

