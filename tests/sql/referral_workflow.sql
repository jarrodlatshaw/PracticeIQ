\set ON_ERROR_STOP on
insert into public.medical_practices values ('test-client'), ('test-competitor');
insert into practiceiq.affiliation_evidence_batches (cms_file_sha256s,practice_export_sha256,nppes_source_sha256,matching_method)
values (array[repeat('a',64)],repeat('b',64),repeat('c',64),'synthetic');
insert into practiceiq.affiliation_evidence_candidates
(batch_id,practice_id,clinician_npi,cms_group_pac_id,cms_group_name,evidence,clinician_practice_count,group_practice_count)
values ((select id from practiceiq.affiliation_evidence_batches where matching_method='synthetic'),'test-client','1000000012','g1','Client','fixture',1,1),
((select id from practiceiq.affiliation_evidence_batches where matching_method='synthetic'),'test-competitor','1000000020','g2','Competitor','fixture',1,1);
insert into practiceiq.dataset_releases (source,version,period_start,period_end,sha256,status)
values ('docgraph-synthetic','v1','2024-01-01','2024-12-31',repeat('d',64),'published');
insert into practiceiq.providers (npi,entity_type) values ('1000000004','individual'),('1000000012','individual'),('1000000020','individual');
insert into practiceiq.referral_edges (release_id,from_npi,to_npi,patient_count)
select id,'1000000004','1000000012',60 from practiceiq.dataset_releases where source='docgraph-synthetic';
insert into practiceiq.referral_edges (release_id,from_npi,to_npi,patient_count)
select id,'1000000004','1000000020',140 from practiceiq.dataset_releases where source='docgraph-synthetic';
do $$
declare b bigint; d bigint; result jsonb;
begin
 select id into b from practiceiq.affiliation_evidence_batches where matching_method='synthetic';
 select id into d from practiceiq.dataset_releases where source='docgraph-synthetic';
 result := practiceiq.calculate_referral_opportunity(b,d,'1000000004','test-client',array['test-competitor'],'2024-12-31',true,true,1800);
 if result->'estimates' <> 'null'::jsonb then raise exception 'unreviewed candidates used'; end if;
 insert into practiceiq.affiliation_reviews(batch_id,practice_id,clinician_npi,cms_group_pac_id,decision,reviewer,effective_from)
 values (b,'test-client','1000000012','g1','approved','test','2024-01-01'),(b,'test-competitor','1000000020','g2','approved','test','2024-01-01');
 result := practiceiq.calculate_referral_opportunity(b,d,'1000000004','test-client',array['test-competitor'],'2024-12-31',true,true,1800);
 if (result#>>'{estimates,leakage}')::numeric <> 140 or (result#>>'{estimates,revenue,base}')::numeric <> 25200 then raise exception 'wrong opportunity: %', result; end if;
 result := practiceiq.calculate_referral_opportunity(b,d,'1000000004','test-client',array['test-competitor'],'2024-12-31',false,true,1800);
 if result->'estimates' <> 'null'::jsonb then raise exception 'incomplete coverage used'; end if;
 result := practiceiq.calculate_referral_opportunity(b,d,'1000000004','test-client',array['test-competitor'],'2024-12-31',true,false,1800);
 if result->'estimates' <> 'null'::jsonb then raise exception 'unverified direction used'; end if;
 update practiceiq.referral_edges set patient_count=null,suppressed=true where release_id=d and to_npi='1000000020';
 result := practiceiq.calculate_referral_opportunity(b,d,'1000000004','test-client',array['test-competitor'],'2024-12-31',true,true,1800);
 if result->'estimates' <> 'null'::jsonb then raise exception 'suppressed count used'; end if;
 if has_function_privilege('authenticated','practiceiq.calculate_referral_opportunity(bigint,bigint,text,text,text[],date,boolean,boolean,numeric,numeric,numeric,numeric)','EXECUTE') then raise exception 'client execute privilege'; end if;
end $$;
