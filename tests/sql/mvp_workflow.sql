\set ON_ERROR_STOP on
insert into public.medical_practices values
('client','Client','Client','Orthopedic Surgery','207X00000X',38,-77,'VA',extensions.st_setsrid(extensions.st_makepoint(-77,38),4326)::extensions.geography),
('competitor','Competitor','Competitor','Orthopedic Surgery','207X00000X',38.1,-77,'VA',extensions.st_setsrid(extensions.st_makepoint(-77,38.1),4326)::extensions.geography),
('source','Source','Source','Family Medicine','207Q00000X',38.05,-77,'VA',extensions.st_setsrid(extensions.st_makepoint(-77,38.05),4326)::extensions.geography);
insert into practiceiq.affiliation_evidence_batches(cms_file_sha256s,practice_export_sha256,nppes_source_sha256,matching_method) values(array[repeat('a',64)],repeat('b',64),repeat('c',64),'synthetic');
insert into practiceiq.affiliation_evidence_candidates(batch_id,practice_id,clinician_npi,cms_group_pac_id,cms_group_name,evidence,clinician_practice_count,group_practice_count) values
(1,'client','1000000012','g1','Client','test',1,1),(1,'competitor','1000000020','g2','Competitor','test',1,1),(1,'source','1000000004','g3','Source','test',1,1);
insert into practiceiq.providers(npi,entity_type,first_name,last_name,primary_taxonomy_code,active) values
('1000000004','individual','Jane','Smith','207Q00000X',true),('1000000012','individual','Client','Doctor','207X00000X',true),('1000000020','individual','Competitor','Doctor','207X00000X',true);
insert into practiceiq.dataset_releases(source,version,period_start,period_end,sha256,direction_notes,status,is_synthetic) values('synthetic','fixture','2024-01-01','2024-12-31',repeat('d',64),'synthetic from to','published',true);
insert into practiceiq.referral_edges(release_id,from_npi,to_npi,patient_count) values (1,'1000000004','1000000012',60),(1,'1000000004','1000000020',140);
update practiceiq.mvp_settings set evidence_batch_id=1,edge_release_id=1;
do $$ declare x jsonb; begin
 x := public.get_referral_opportunities('client');
 if (x#>>'{dataset,synthetic}')::boolean is not true or (x#>>'{opportunities,0,synthetic_data}')::boolean is not true then raise exception 'synthetic data not labeled'; end if;
 if (x#>>'{market_summary,competitor_count}')::int<>1 or jsonb_array_length(x->'opportunities')<>1 then raise exception 'discovery failed: %',x; end if;
 if (x#>>'{opportunities,0,estimated_leakage}')::numeric<>140 or (x#>>'{opportunities,0,revenue_base}')::numeric<>25200 then raise exception 'calculation failed: %',x; end if;
 if has_function_privilege('authenticated','public.get_referral_opportunities(text)','EXECUTE') then raise exception 'unsecured execute'; end if;
 update practiceiq.referral_edges set patient_count=null,suppressed=true where to_npi='1000000020';
 x := public.get_referral_opportunities('client');
 if x#>'{opportunities,0,revenue_base}' <> 'null'::jsonb then raise exception 'suppression lost'; end if;
end $$;
