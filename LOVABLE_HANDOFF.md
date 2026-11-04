# Lovable handoff — referral MVP prototype

Status: **local prototype; not deployed or client-accessible**. The development example uses a real Virginia practice and invented patient-sharing records. The invented flows, revenue and scores are not observations and must never be shown as real data. No live Supabase data has been changed.

## Contract

`public.get_referral_opportunities(p_practice_id text) -> jsonb` is implemented in `supabase/migrations/20261104000300_referral_mvp.sql`. The SQL is `SECURITY INVOKER` and execution is revoked from `PUBLIC`, `anon`, and `authenticated`; this is intentional until a practice-scoped authorization model is implemented and tested. Do not put a service-role key in a Lovable client. A secure backend or tenant-aware RPC is still required.

The object has `practice_id`, `practice_name`, `specialty`, `latitude`, `longitude`, `market_summary` (`competitor_count`, `potential_referral_sources`, `sources_with_observed_edges`), `dataset` (source, version, period and synthetic flag), `assumptions`, `limitations`, and `opportunities`. Each opportunity contains source NPI, provider name, practice and taxonomy, coordinates, distance, nullable drive time, patient-sharing flow and leakage, low/base/high revenue, score and components, rule-based confidence and synthetic flag. Missing/suppressed edge counts produce null estimates. An empty list does not prove no opportunity, because datasets can be incomplete or suppressed.

The compatibility table supports selected orthopedic taxonomy codes and source specialties only. Competitors are same-specialty practices within the configured radius, with an active NPPES individual and an unambiguous CMS affiliation; practices with the same normalized organization or CMS group are excluded. Source providers use primary taxonomy. The underlying NPPES/CMS snapshots may be stale, their organization mapping is heuristic, and group name/address agreement is not employment verification. The CMS source date needs verification. Pairwise patient-sharing counts overlap and are not unique patients or verified referrals. Illustrative default collections of $1,800, capture rates of 5%, 10%, 15%, and score weights are configurable in `practiceiq.mvp_settings`, not measured financial forecasts. Routing is not implemented; drive time is null.

## Example

A local PostGIS test using real practice ID `1627cd39a9ef0dcbe804e3cf` and **invented** 2024 edges found one competitor, 58 eligible potential sources, and three fixture sources with edges. An example source had invented client flow 9, competitor flow 78, and a base revenue estimate of $14,040 under the $1,800 and 10% assumptions. Do not interpret this as a real relationship or forecast. The example mixes current provider/practice snapshots with a fictitious historical period and is for exercising the pipeline only.

## Frontend guidance

When an authorized API exists, select a practice and render market summary, a ranked table and map markers from the result. Show the dataset period, limitations, score components, capture assumptions and benchmark alongside every estimate. Clearly identify synthetic data and never present it as actual; show unavailable drive times as unavailable. Provide loading, no-data, unsupported-specialty, missing-location, incomplete-coverage and authorization states. Do not have the frontend infer missing counts, calculate revenue, or assume a zero result means no patient flow.

## Before real use

Obtain and validate licensed DocGraph data, its period, direction, suppression and permitted use; load providers and edges and configure the selected data release. Review CMS snapshot date and affiliation quality; automate high-confidence matches only within documented limitations. Validate practice coverage and score benchmarks with domain experts. Implement tenant access and server authorization, test against the actual Supabase schema and RLS, and deploy with appropriate review. This prototype has not been tested against live Supabase.
