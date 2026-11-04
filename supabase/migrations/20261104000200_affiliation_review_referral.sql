-- Server-only prototype. No client grants or automatic approvals.
begin;
alter table practiceiq.affiliation_evidence_batches add column import_fingerprint text unique
  check (import_fingerprint is null or import_fingerprint ~ '^[0-9a-f]{64}$');
create table practiceiq.affiliation_reviews (
    batch_id bigint not null,
    practice_id text not null,
    clinician_npi text not null,
    cms_group_pac_id text not null,
    decision text not null check (decision in ('approved','rejected')),
    reviewer text not null check (length(trim(reviewer)) > 0),
    reviewed_at timestamptz not null default now(),
    effective_from date not null,
    effective_to date,
    notes text,
    primary key (batch_id, practice_id, clinician_npi, cms_group_pac_id),
    foreign key (batch_id, practice_id, clinician_npi, cms_group_pac_id)
      references practiceiq.affiliation_evidence_candidates(batch_id, practice_id, clinician_npi, cms_group_pac_id),
    check (effective_to is null or effective_to >= effective_from)
);
alter table practiceiq.affiliation_reviews enable row level security;
revoke all on practiceiq.affiliation_reviews from public, anon, authenticated;

-- This function is invoker-security and server-only. Inputs must be preselected
-- for a single specialty, geography, source period and licensed dataset. The
-- caller must justify completeness and verify edge direction from source docs.
create function practiceiq.calculate_referral_opportunity(
    p_batch_id bigint, p_release_id bigint, p_source_npi text,
    p_client_practice_id text, p_competitor_practice_ids text[],
    p_as_of date, p_coverage_complete boolean, p_direction_verified boolean,
    p_collections numeric, p_low numeric default 0.05,
    p_base numeric default 0.10, p_high numeric default 0.15
) returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare
    v_period_start date; v_period_end date; v_unresolved bigint;
    v_client text[]; v_competitors text[]; v_client_flow bigint;
    v_competitor_flow bigint; v_missing bigint; v_reasons text[] := array[]::text[];
    v_leakage numeric; v_result jsonb;
begin
    if p_batch_id is null or p_release_id is null or p_source_npi is null or p_source_npi !~ '^[12][0-9]{9}$'
       or p_client_practice_id is null or length(trim(p_client_practice_id)) = 0
       or p_competitor_practice_ids is null or cardinality(p_competitor_practice_ids) = 0
       or array_position(p_competitor_practice_ids, null) is not null
       or p_client_practice_id = any(p_competitor_practice_ids)
       or p_as_of is null or p_coverage_complete is null or p_direction_verified is null
       or p_low is null or p_base is null or p_high is null
       or p_low::text in ('NaN','Infinity','-Infinity') or p_base::text in ('NaN','Infinity','-Infinity') or p_high::text in ('NaN','Infinity','-Infinity')
       or p_low < 0 or p_base < p_low or p_high < p_base or p_high > 1
       or (p_collections is not null and (p_collections < 0 or p_collections::text in ('NaN','Infinity','-Infinity'))) then
        raise exception 'Invalid referral analysis inputs';
    end if;
    if not exists (select 1 from practiceiq.affiliation_evidence_batches b where b.id = p_batch_id) then
        raise exception 'Unknown evidence batch';
    end if;
    select d.period_start, d.period_end into v_period_start, v_period_end
    from practiceiq.dataset_releases d where d.id = p_release_id and d.status = 'published';
    if not found or p_as_of <> v_period_end then
        raise exception 'A published release and its period-end date are required';
    end if;
    with scoped as (
      select c.practice_id, c.clinician_npi, r.decision, r.effective_from, r.effective_to
      from practiceiq.affiliation_evidence_candidates c
      left join practiceiq.affiliation_reviews r using (batch_id, practice_id, clinician_npi, cms_group_pac_id)
      where c.batch_id=p_batch_id and (c.practice_id=p_client_practice_id or c.practice_id=any(p_competitor_practice_ids))
    )
    select count(*) filter (where decision is null or effective_from > p_as_of or (effective_to is not null and effective_to < p_as_of)),
           coalesce(array_agg(distinct clinician_npi) filter (where practice_id=p_client_practice_id and decision='approved'
              and effective_from <= p_as_of and (effective_to is null or effective_to >= p_as_of)),array[]::text[]),
           coalesce(array_agg(distinct clinician_npi) filter (where practice_id=any(p_competitor_practice_ids) and decision='approved'
              and effective_from <= p_as_of and (effective_to is null or effective_to >= p_as_of)),array[]::text[])
    into v_unresolved, v_client, v_competitors from scoped;
    if v_client && v_competitors then raise exception 'Clinician assigned to both client and competitor'; end if;
    select coalesce(sum(patient_count) filter (where to_npi=any(v_client)),0),
           coalesce(sum(patient_count) filter (where to_npi=any(v_competitors)),0),
           count(*) filter (where patient_count is null or suppressed)
    into v_client_flow, v_competitor_flow, v_missing
    from practiceiq.referral_edges
    where release_id=p_release_id and from_npi=p_source_npi
      and (to_npi=any(v_client) or to_npi=any(v_competitors));
    if not p_coverage_complete then v_reasons := array_append(v_reasons,'coverage_not_established'); end if;
    if not p_direction_verified then v_reasons := array_append(v_reasons,'direction_not_verified'); end if;
    if v_unresolved > 0 then v_reasons := array_append(v_reasons,'unreviewed_or_expired_affiliations'); end if;
    if cardinality(v_client)=0 or cardinality(v_competitors)=0 then v_reasons := array_append(v_reasons,'insufficient_approved_affiliations'); end if;
    if v_missing > 0 then v_reasons := array_append(v_reasons,'missing_edge_counts'); end if;
    v_leakage := v_competitor_flow;
    v_result := jsonb_build_object('source_npi',p_source_npi,'period_start',v_period_start,'period_end',v_period_end,
      'evidence_batch_id',p_batch_id,'release_id',p_release_id,'unresolved_candidates',v_unresolved,
      'visible_client_edge_volume',v_client_flow,'visible_competitor_edge_volume',v_competitor_flow,
      'approved_client_provider_count',cardinality(v_client),'approved_competitor_provider_count',cardinality(v_competitors),
      'missing_eligible_edge_counts',v_missing,'reasons',to_jsonb(v_reasons),
      'coverage_declared_complete',p_coverage_complete,'direction_verified',p_direction_verified,
      'assumptions',jsonb_build_object('capture_low',p_low,'capture_base',p_base,'capture_high',p_high,'collections_per_patient',p_collections),
      'limitation','Shared-patient edge sums may overlap; they are neither unique patients nor verified referrals.');
    if cardinality(v_reasons)>0 then return v_result || jsonb_build_object('estimates',null); end if;
    return v_result || jsonb_build_object('estimates',jsonb_build_object('observed',v_client_flow+v_competitor_flow,
      'captured',v_client_flow,'leakage',v_leakage,
      'incremental',jsonb_build_object('low',v_leakage*p_low,'base',v_leakage*p_base,'high',v_leakage*p_high),
      'revenue',jsonb_build_object('low',v_leakage*p_low*p_collections,'base',v_leakage*p_base*p_collections,'high',v_leakage*p_high*p_collections)));
end $$;
revoke all on function practiceiq.calculate_referral_opportunity(bigint,bigint,text,text,text[],date,boolean,boolean,numeric,numeric,numeric,numeric) from public, anon, authenticated;
commit;
