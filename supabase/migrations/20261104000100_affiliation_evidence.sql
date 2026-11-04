-- Private evidence staging; no customer access or automatic promotion.
begin;
create table practiceiq.affiliation_evidence_batches (
    id bigint generated always as identity primary key,
    cms_file_sha256s text[] not null check (cardinality(cms_file_sha256s) > 0),
    practice_export_sha256 text not null check (practice_export_sha256 ~ '^[0-9a-f]{64}$'),
    nppes_source_sha256 text not null check (nppes_source_sha256 ~ '^[0-9a-f]{64}$'),
    cms_release_date date,
    matching_method text not null check (length(trim(matching_method)) > 0),
    created_at timestamptz not null default now()
);

create table practiceiq.affiliation_evidence_candidates (
    batch_id bigint not null references practiceiq.affiliation_evidence_batches(id),
    practice_id text not null references public.medical_practices(practice_id),
    clinician_npi text not null check (clinician_npi ~ '^[12][0-9]{9}$'),
    cms_group_pac_id text not null check (length(trim(cms_group_pac_id)) > 0),
    cms_group_name text not null check (length(trim(cms_group_name)) > 0),
    cms_address_1 text,
    cms_city text,
    cms_zip text,
    evidence text not null,
    clinician_practice_count integer not null check (clinician_practice_count > 0),
    group_practice_count integer not null check (group_practice_count > 0),
    review_status text not null default 'candidate' check (review_status = 'candidate'),
    primary key (batch_id, practice_id, clinician_npi, cms_group_pac_id)
);
create index affiliation_evidence_npi_idx on practiceiq.affiliation_evidence_candidates (clinician_npi, practice_id);
alter table practiceiq.affiliation_evidence_batches enable row level security;
alter table practiceiq.affiliation_evidence_candidates enable row level security;
revoke all on practiceiq.affiliation_evidence_batches, practiceiq.affiliation_evidence_candidates from public, anon, authenticated;
revoke all on sequence practiceiq.affiliation_evidence_batches_id_seq from public, anon, authenticated;
commit;
