"""Read-only adaptation of existing medical_practices rows.

NPI strings are parsed only when the caller explicitly supplies the confirmed
serialization format. Candidates are not automatically accepted affiliations.
"""
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import json
import math

from practiceiq.identity import normalize_npi


def parse_npis(value: object, *, format: str) -> list[str] | None:
    if format not in ("single", "json_array", "comma_separated", "semicolon_separated"):
        raise ValueError("choose an NPI format: single, json_array, comma_separated, or semicolon_separated")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("npis must be text or null")
    if not value.strip():
        return None
    if format == "single":
        values = [value]
    elif format == "json_array":
        try:
            values = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("npis is not a JSON array") from exc
        if not isinstance(values, list):
            raise ValueError("npis is not a JSON array")
    else:
        values = value.split(";" if format == "semicolon_separated" else ",")
    npis = [normalize_npi(npi) for npi in values]
    if len(npis) != len(set(npis)):
        raise ValueError("duplicate NPI in practice row")
    return npis


def count_status(reported: object, npis: list[str] | None) -> str:
    """Compare the reported count when both it and the parsed list exist."""
    if reported is None or npis is None:
        return "unavailable"
    if isinstance(reported, bool):
        return "invalid_reported_count"
    try:
        count = Decimal(str(reported))
    except (InvalidOperation, ValueError):
        return "invalid_reported_count"
    if not count.is_finite() or count < 0 or count != count.to_integral_value():
        return "invalid_reported_count"
    return "match" if count == len(npis) else "mismatch"


def adapt_practice(row: Mapping, *, npi_format: str) -> dict:
    """Return a proposed practice/location and unverified NPI candidates.

    The source identifier is retained verbatim. This function performs no
    writes, merges, geocoding, or confirmation of provider affiliation.
    """
    practice_id = row.get("practice_id")
    if not isinstance(practice_id, str) or not practice_id.strip():
        raise ValueError("practice_id must be nonempty text")
    npis = parse_npis(row.get("npis"), format=npi_format)
    latitude, longitude = row.get("latitude"), row.get("longitude")
    if (latitude is None) != (longitude is None):
        raise ValueError("latitude and longitude must both be present or both null")
    if latitude is not None:
        try:
            latitude, longitude = float(latitude), float(longitude)
        except (TypeError, ValueError):
            raise ValueError("coordinates must be numeric") from None
        if not (math.isfinite(latitude) and math.isfinite(longitude) and
                -90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("coordinates are outside WGS84 bounds")
    return {
        "source_table": "medical_practices",
        "practice_id": practice_id,
        "practice_name": row.get("practice_name"),
        "legal_name": row.get("legal_name"),
        "primary_specialty": row.get("primary_specialty"),
        "primary_specialty_code": row.get("primary_specialty_code"),
        "taxonomy_codes_raw": row.get("taxonomy_codes"),
        "location": {key: row.get(key) for key in
                     ("address_1", "address_2", "city", "state", "zip5", "phone",
                      "location_sources", "geocode_status", "geocode_quality", "geocoded_address", "location")}
                    | {"latitude": latitude, "longitude": longitude},
        "npi_candidates": None if npis is None else [
            {"npi": npi, "evidence": "medical_practices.npis", "status": "requires_review"}
            for npi in npis],
        "reported_npi_count": row.get("npi_count"),
        "npi_count_status": count_status(row.get("npi_count"), npis),
    }
