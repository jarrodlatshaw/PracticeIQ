"""Conservative identifiers and candidate affiliation evidence."""
import re


def normalize_npi(value: str) -> str:
    """Validate a 10-digit NPI including its CMS Luhn check digit."""
    if not isinstance(value, str):
        raise ValueError("NPI must be text")
    npi = value.strip()
    if not re.fullmatch(r"[0-9]{10}", npi) or npi[0] not in "12":
        raise ValueError("NPI must be 10 digits and begin with 1 or 2")
    digits = [int(c) for c in "80840" + npi]
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    if total % 10:
        raise ValueError("invalid NPI check digit")
    return npi


def affiliation_evidence(*, organization_npi_match: bool = False,
                         authoritative_affiliation: bool = False,
                         name_match: bool = False, address_match: bool = False,
                         phone_match: bool = False, conflict: bool = False) -> str:
    """Classify evidence; a candidate is never an automatic practice merge."""
    if conflict:
        return "conflict_review"
    if organization_npi_match or authoritative_affiliation:
        return "high"
    if name_match and address_match and phone_match:
        return "candidate_review"
    return "insufficient"
