\set ON_ERROR_STOP on
insert into practiceiq.dataset_releases (source, version, period_start, period_end, sha256, direction_notes)
values ('synthetic', 'v1', '2024-01-01', '2024-12-31', repeat('a',64), 'test only');
insert into practiceiq.providers (npi, entity_type) values ('1000000004','individual'), ('1000000012','individual');
insert into practiceiq.provider_practice_affiliations (practice_id, provider_npi, evidence, confidence)
values ('synthetic-va', '1000000012', 'fixture', 'candidate');
insert into practiceiq.referral_edges (release_id, from_npi, to_npi, patient_count)
values (1, '1000000004', '1000000012', 60);
do $$
begin
  if (select count(*) from practiceiq.referral_edges) <> 1 then raise exception 'edge not inserted'; end if;
  if has_schema_privilege('anon', 'practiceiq', 'USAGE') or has_schema_privilege('authenticated', 'practiceiq', 'USAGE') then
    raise exception 'client role has schema usage';
  end if;
  if exists (select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
             where n.nspname='practiceiq' and c.relkind='r' and not c.relrowsecurity) then
    raise exception 'missing RLS';
  end if;
  begin
    insert into practiceiq.referral_edges (release_id, from_npi, to_npi, patient_count)
    values (1, '1000000004', '1000000012', 5);
    raise exception 'duplicate edge accepted';
  exception when unique_violation then null; end;
  begin
    insert into practiceiq.referral_edges (release_id, from_npi, to_npi, patient_count)
    values (1, '1000000012', '1000000004', -1);
    raise exception 'negative count accepted';
  exception when check_violation then null; end;
  begin
    insert into practiceiq.provider_practice_affiliations (practice_id, provider_npi, evidence, confidence)
    values ('missing', '1000000004', 'test', 'candidate');
    raise exception 'missing practice accepted';
  exception when foreign_key_violation then null; end;
  begin
    insert into practiceiq.referral_edges (release_id, from_npi, to_npi, patient_count, suppressed)
    values (1, '1000000012', '1000000004', 10, true);
    raise exception 'suppressed count accepted';
  exception when check_violation then null; end;
end $$;
