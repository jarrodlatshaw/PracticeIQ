"""Connect staged affiliation candidates and explicit reviews to edge analysis.

Inputs must refer to one selected data snapshot and a preselected market and
specialty. This function is an in-memory prototype, not an authorization or
Supabase integration layer. Candidates alone never authorize an affiliation.
"""
from datetime import date
from practiceiq.identity import normalize_npi
from practiceiq.referral import analyze_source


def analyze_evidence(source_npi, edges, candidates, reviews, *, client_practice_id,
                     competitor_practice_ids, as_of, coverage_complete,
                     collections_per_patient):
    if not isinstance(as_of, date):
        raise ValueError('as_of must be a date')
    competitors = set(competitor_practice_ids)
    if not client_practice_id or client_practice_id in competitors or not competitors:
        raise ValueError('client and competitor practice scope must be nonempty and disjoint')
    if not isinstance(coverage_complete, bool):
        raise ValueError('coverage_complete must be a boolean')
    scope = competitors | {client_practice_id}
    staged = {}
    for candidate in candidates:
        practice = candidate['practice_id']
        if practice not in scope:
            continue
        npi = normalize_npi(candidate['clinician_npi'])
        key = (practice, npi, candidate['cms_group_pac_id'])
        if not key[2] or key in staged:
            raise ValueError('candidate keys must be unique and contain a CMS group ID')
        staged[key] = candidate
    decisions = {}
    for review in reviews:
        key = (review['practice_id'], normalize_npi(review['clinician_npi']), review['cms_group_pac_id'])
        if key[0] not in scope:
            continue
        if key not in staged or key in decisions:
            raise ValueError('review must reference a unique staged candidate')
        if review.get('decision') not in ('approved', 'rejected') or not review.get('reviewer'):
            raise ValueError('review requires a decision and reviewer')
        start, end = review.get('effective_from'), review.get('effective_to')
        if not isinstance(start, date) or (end is not None and (not isinstance(end, date) or end < start)):
            raise ValueError('review requires a valid effective period')
        decisions[key] = review
    client_npis, competitor_npis = set(), set()
    unresolved = 0
    for key in staged:
        review = decisions.get(key)
        if review is None:
            unresolved += 1
            continue
        end = review.get('effective_to')
        if review['effective_from'] > as_of or (end is not None and end < as_of):
            unresolved += 1
            continue
        if review['decision'] == 'rejected':
            continue
        (client_npis if key[0] == client_practice_id else competitor_npis).add(key[1])
    result = analyze_source(source_npi, edges, client_npis=client_npis,
                            competitor_npis=competitor_npis,
                            coverage_complete=coverage_complete and unresolved == 0 and bool(client_npis) and bool(competitor_npis),
                            collections_per_patient=collections_per_patient)
    result.update({'unreviewed_candidate_count': unresolved,
                   'approved_client_provider_count': len(client_npis),
                   'approved_competitor_provider_count': len(competitor_npis),
                   'as_of': as_of.isoformat()})
    return result
