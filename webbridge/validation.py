# -*- coding: utf-8 -*-
"""Parameter validation utilities for API endpoints.

Provides safe parsing functions for query parameters that return
user-friendly error messages instead of crashing with 500 errors.
"""


def parse_int_param(params, key, default=None, required=False, non_negative=True, max_value=None):
    """Safely parse an integer from query parameters.

    Args:
        params: dict mapping param names to lists of string values
                (WSGI query string format, e.g. {"offset": ["10"]})
        key: parameter name to parse
        default: default value if param is missing (only used if not required)
        required: if True, missing param returns error instead of default
        non_negative: if True, negative values return error
        max_value: if provided, cap value at this maximum (no error, just cap)

    Returns:
        tuple: (value, None) on success - value is parsed int or default
               (None, error_message) on failure - error_message is user-friendly string

    Examples:
        >>> parse_int_param({"offset": ["10"]}, "offset", default=0)
        (10, None)

        >>> parse_int_param({"offset": [":"]}, "offset", default=0)
        (None, "Invalid 'offset' parameter: must be a non-negative integer, got ':'")

        >>> parse_int_param({"limit": ["5000"]}, "limit", default=20, max_value=1000)
        (1000, None)

        >>> parse_int_param({}, "offset", default=0)
        (0, None)

        >>> parse_int_param({"limit": ["-5"]}, "limit", default=20)
        (None, "Invalid 'limit' parameter: must be a non-negative integer, got '-5'")
    """
    # Get the raw value from params (WSGI format: values are lists)
    values = params.get(key, [])
    raw_value = values[0] if values else None

    # Handle missing or empty parameter
    if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
        if required:
            return None, "Missing required parameter '%s'" % key
        return default, None

    # Strip whitespace
    raw_value = raw_value.strip()

    # Try to parse as integer
    try:
        value = int(raw_value)
    except ValueError:
        return None, "Invalid '%s' parameter: must be a non-negative integer, got '%s'" % (key, raw_value)

    # Check non-negative constraint
    if non_negative and value < 0:
        return None, "Invalid '%s' parameter: must be a non-negative integer, got '%s'" % (key, raw_value)

    # Apply max_value cap (no error, just cap)
    if max_value is not None and value > max_value:
        value = max_value

    return value, None


def validate_params(params, validations):
    """Validate multiple parameters at once.

    Args:
        params: dict mapping param names to lists of string values
        validations: list of tuples (key, options_dict) where options_dict
                     can contain: default, required, non_negative, max_value

    Returns:
        tuple: (values_dict, None) on success
               (None, error_response_dict) on first failure

    Examples:
        >>> validations = [
        ...     ("offset", {"default": 0}),
        ...     ("limit", {"default": 20, "max_value": 1000}),
        ... ]
        >>> validate_params({"offset": ["10"], "limit": ["50"]}, validations)
        ({"offset": 10, "limit": 50}, None)

        >>> validate_params({"offset": [":"]}, validations)
        (None, {"error": "Invalid 'offset' parameter: must be a non-negative integer, got ':'"})
    """
    result = {}
    for key, options in validations:
        value, error = parse_int_param(
            params,
            key,
            default=options.get("default"),
            required=options.get("required", False),
            non_negative=options.get("non_negative", True),
            max_value=options.get("max_value"),
        )
        if error:
            return None, {"error": error}
        result[key] = value
    return result, None

