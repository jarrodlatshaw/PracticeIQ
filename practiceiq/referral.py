"""Compute one source's eligible patient-sharing edge totals.

This is an in-memory calculation primitive, not a database query or API. The
caller must select exactly one release/period, verify its direction semantics,
and supply reviewed, disjoint client and competitor destination sets. Results
are sums of edges, not unique patients or verified referrals.
"""
from collections.abc import Iterable, Mapping
from practiceiq.calculations import Scenarios, opportunity
from practiceiq.identity import normalize_npi


def analyze_source(source_npi: str, edges: Iterable[Mapping], *, client_npis: set[str],
                   competitor_npis: set[str], coverage_complete: bool,
                   collections_per_patient: object | None,
                   scenarios: Scenarios = Scenarios()) -> dict:
    source_npi = normalize_npi(source_npi)
    client = {normalize_npi(npi) for npi in client_npis}
    competitors = {normalize_npi(npi) for npi in competitor_npis}
    if client & competitors:
        raise ValueError("client and competitor destination sets overlap")
    if not isinstance(coverage_complete, bool):
        raise ValueError("coverage_complete must be a boolean")
    seen = set()
    visible_client = 0
    visible_competitor = 0
    missing_count = 0
    for edge in edges:
        if normalize_npi(edge.get("from_npi")) != source_npi:
            raise ValueError("edges must belong to the requested source")
        destination = normalize_npi(edge.get("to_npi"))
        if destination == source_npi or destination in seen:
            raise ValueError("self or duplicate edge")
        seen.add(destination)
        if destination not in client and destination not in competitors:
            continue
        count = edge.get("patient_count")
        if count is None:
            missing_count += 1
            continue
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("patient count must be a nonnegative integer or null")
        if destination in client:
            visible_client += count
        else:
            visible_competitor += count
    complete = coverage_complete and missing_count == 0
    estimates = (opportunity(visible_client + visible_competitor, visible_client,
                             collections_per_patient, scenarios) if complete else None)
    return {
        "source_npi": source_npi,
        "visible_client_edge_volume": visible_client,
        "visible_competitor_edge_volume": visible_competitor,
        "missing_eligible_edge_counts": missing_count,
        "coverage_complete": complete,
        "estimates": estimates,
        "limitation": "Edge sums can overlap; they are not unique patients or confirmed referrals.",
    }
