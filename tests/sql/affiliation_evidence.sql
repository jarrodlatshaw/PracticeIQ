\set ON_ERROR_STOP on
insert into practiceiq.affiliation_evidence_batches (cms_file_sha256s, practice_export_sha256, nppes_source_sha256, matching_method)
values (array[repeat('a',64)], repeat('b',64), repeat('c',64), 'test');
insert into practiceiq.affiliation_evidence_candidates
(batch_id, practice_id, clinician_npi, cms_group_pac_id, cms_group_name, evidence, clinician_practice_count, group_practice_count)
values (1, 'synthetic-va', '1000000004', 'group-1', 'Example', 'name and address', 1, 1);
do $$
begin
 if (select review_status from practiceiq.affiliation_evidence_candidates limit 1) <> 'candidate' then raise exception 'unexpected status'; end if;
 if has_table_privilege('authenticated', 'practiceiq.affiliation_evidence_candidates', 'SELECT') then raise exception 'client access allowed'; end if;
 begin
  update practiceiq.affiliation_evidence_candidates set review_status='reviewed';
  raise exception 'automatic promotion allowed';
 exception when check_violation then null; end;
 begin
  insert into practiceiq.affiliation_evidence_candidates
  (batch_id,practice_id,clinician_npi,cms_group_pac_id,cms_group_name,evidence,clinician_practice_count,group_practice_count)
  values (1,'missing','1000000004','group-2','Example','test',1,1);
  raise exception 'missing practice accepted';
 exception when foreign_key_violation then null; end;
end $$;
