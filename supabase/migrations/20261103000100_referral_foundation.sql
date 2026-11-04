-- Additive referral foundation. Local validation only; review before deployment.
-- Existing PracticeIQ objects, RLS and grants remain untouched.
begin;
create schema practiceiq;
revoke all on schema practiceiq from public, anon, authenticated;

create table practiceiq.dataset_releases (
    id bigint generated always as identity primary key,
    source text not null check (length(trim(source)) > 0),
    version text not null check (length(trim(version)) > 0),
    period_start date not null,
    period_end date not null check (period_end >= period_start),
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    source_uri text,
    license_reference text,
    coverage_notes text,
    suppression_notes text,
    direction_notes text,
    status text not null default 'staged' check (status in ('staged','validated','published','retired')),
    loaded_at timestamptz not null default now(),
    unique (source, version, sha256)
);

create table practiceiq.providers (
    npi text primary key check (npi ~ '^[12][0-9]{9}$'),
    entity_type text not null default 'unknown' check (entity_type in ('individual','organization','unknown')),
    display_name text,
    source_release_id bigint references practiceiq.dataset_releases(id),
    last_verified_at timestamptz
);

-- The existing medical_practices row is the authoritative practice key.
create table practiceiq.provider_practice_affiliations (
    id bigint generated always as identity primary key,
    practice_id text not null references public.medical_practices(practice_id),
    provider_npi text not null references practiceiq.providers(npi),
    source_release_id bigint references practiceiq.dataset_releases(id),
    evidence text not null,
    confidence text not null check (confidence in ('candidate','high','reviewed','rejected')),
    effective_from date,
    effective_to date,
    reviewed_at timestamptz,
    check (effective_from is null or effective_to is null or effective_to >= effective_from),
    check (confidence <> 'reviewed' or reviewed_at is not null)
);
create index practiceiq_affiliations_practice_idx on practiceiq.provider_practice_affiliations (practice_id, provider_npi);
create index practiceiq_affiliations_provider_idx on practiceiq.provider_practice_affiliations (provider_npi, practice_id);

-- Patient-sharing counts may overlap and do not prove a referral.
create table practiceiq.referral_edges (
    release_id bigint not null references practiceiq.dataset_releases(id),
    from_npi text not null references practiceiq.providers(npi),
    to_npi text not null references practiceiq.providers(npi),
    patient_count bigint check (patient_count >= 0),
    transaction_count bigint check (transaction_count >= 0),
    average_day_wait numeric check (average_day_wait >= 0),
    std_day_wait numeric check (std_day_wait >= 0),
    suppressed boolean not null default false,
    primary key (release_id, from_npi, to_npi),
    check (from_npi <> to_npi),
    check (not suppressed or patient_count is null)
);
create index practiceiq_edges_destination_idx on practiceiq.referral_edges (release_id, to_npi, from_npi);

create table practiceiq.cms_utilization (
    id bigint generated always as identity primary key,
    release_id bigint not null references practiceiq.dataset_releases(id),
    provider_npi text not null references practiceiq.providers(npi),
    report_year integer not null check (report_year between 1900 and 2100),
    specialty text,
    geography text,
    hcpcs text,
    beneficiary_count bigint check (beneficiary_count >= 0),
    allowed_amount numeric check (allowed_amount >= 0),
    payment_amount numeric check (payment_amount >= 0),
    denominator_description text not null,
    source_row_key text not null,
    unique (release_id, source_row_key)
);
create index practiceiq_cms_provider_year_idx on practiceiq.cms_utilization (provider_npi, report_year);

create table practiceiq.revenue_benchmarks (
    id bigint generated always as identity primary key,
    release_id bigint not null references practiceiq.dataset_releases(id),
    report_year integer not null check (report_year between 1900 and 2100),
    specialty text not null,
    geography text not null,
    basis text not null,
    cohort_count integer not null check (cohort_count > 0),
    amount_per_beneficiary numeric not null check (amount_per_beneficiary >= 0),
    methodology text not null,
    unique (release_id, report_year, specialty, geography, basis)
);

-- No public policies or grants are introduced: future tenant access requires a
-- separately reviewed authorization model and security-tested API.
alter table practiceiq.dataset_releases enable row level security;
alter table practiceiq.providers enable row level security;
alter table practiceiq.provider_practice_affiliations enable row level security;
alter table practiceiq.referral_edges enable row level security;
alter table practiceiq.cms_utilization enable row level security;
alter table practiceiq.revenue_benchmarks enable row level security;
revoke all on all tables in schema practiceiq from public, anon, authenticated;
revoke all on all sequences in schema practiceiq from public, anon, authenticated;
commit;
