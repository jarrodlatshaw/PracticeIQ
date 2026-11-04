-- V1 referral RPC: private server-side prototype; not yet tenant-authorized.
begin;
alter table practiceiq.dataset_releases add column is_synthetic boolean not null default false;
alter table practiceiq.providers add column first_name text, add column last_name text,
  add column primary_taxonomy_code text, add column active boolean;
create table practiceiq.mvp_settings (
  singleton boolean primary key default true check (singleton),
  evidence_batch_id bigint references practiceiq.affiliation_evidence_batches(id),
  edge_release_id bigint references practiceiq.dataset_releases(id),
  radius_miles numeric not null default 25 check (radius_miles > 0 and radius_miles <= 100),
  collections_per_patient numeric not null default 1800 check (collections_per_patient >= 0),
  capture_low numeric not null default .05, capture_base numeric not null default .10, capture_high numeric not null default .15,
  flow_weight numeric not null default .40, revenue_weight numeric not null default .25,
  proximity_weight numeric not null default .15, leakage_weight numeric not null default .10, size_weight numeric not null default .10,
  volume_cap numeric not null default 200 check (volume_cap > 0), size_cap numeric not null default 10 check (size_cap > 0),
  check (capture_low >= 0 and capture_low <= capture_base and capture_base <= capture_high and capture_high <= 1),
  check (flow_weight >= 0 and revenue_weight >= 0 and proximity_weight >= 0 and leakage_weight >= 0 and size_weight >= 0
     and flow_weight + revenue_weight + proximity_weight + leakage_weight + size_weight = 1)
);
insert into practiceiq.mvp_settings(singleton) values (true);
create table practiceiq.mvp_compatibility (
  destination_taxonomy text not null, source_taxonomy text not null,
  primary key(destination_taxonomy,source_taxonomy)
);
insert into practiceiq.mvp_compatibility(destination_taxonomy,source_taxonomy)
select d,s from unnest(array['207X00000X','207XS0106X','207XS0114X','207XS0117X','207XX0004X','207XX0005X']) d
cross join unnest(array['207Q00000X','207R00000X','207P00000X','208100000X','2081P2900X','2081S0010X','207QS0010X']) s;
alter table practiceiq.mvp_settings enable row level security;
alter table practiceiq.mvp_compatibility enable row level security;
revoke all on practiceiq.mvp_settings,practiceiq.mvp_compatibility from public,anon,authenticated;

create function public.get_referral_opportunities(p_practice_id text)
returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare cfg practiceiq.mvp_settings%rowtype; client public.medical_practices%rowtype;
  release_record practiceiq.dataset_releases%rowtype; result jsonb;
begin
 select * into cfg from practiceiq.mvp_settings where singleton;
 if not found or cfg.evidence_batch_id is null or cfg.edge_release_id is null then
   raise exception 'MVP data sources are not configured';
 end if;
 select * into client from public.medical_practices where practice_id=p_practice_id;
 if not found or client.location is null then raise exception 'Practice or location unavailable'; end if;
 if not exists(select 1 from practiceiq.mvp_compatibility where destination_taxonomy=client.primary_specialty_code) then
   raise exception 'Practice specialty is not supported by the V1 compatibility map'; end if;
 select * into release_record from practiceiq.dataset_releases where id=cfg.edge_release_id and status='published';
 if not found or release_record.direction_notes is null then raise exception 'Patient-sharing release is not ready'; end if;
 if not exists(select 1 from practiceiq.referral_edges where release_id=cfg.edge_release_id) then raise exception 'Patient-sharing data is unavailable'; end if;
 if not exists(
   select c.clinician_npi from practiceiq.affiliation_evidence_candidates c
   join practiceiq.providers x on x.npi=c.clinician_npi and x.entity_type='individual' and x.active is true
   where c.batch_id=cfg.evidence_batch_id group by c.clinician_npi
   having count(distinct c.practice_id)=1 and min(c.practice_id)=p_practice_id
 ) then raise exception 'No unambiguous active client clinicians available'; end if;
 with unique_links as (
   select clinician_npi, min(practice_id) as practice_id from practiceiq.affiliation_evidence_candidates
   where batch_id=cfg.evidence_batch_id group by clinician_npi having count(distinct practice_id)=1
 ), links as (
   select u.clinician_npi,u.practice_id from unique_links u join practiceiq.providers x on x.npi=u.clinician_npi and x.entity_type='individual' and x.active is true
 ), client_groups as (
   select distinct cms_group_pac_id from practiceiq.affiliation_evidence_candidates
   where batch_id=cfg.evidence_batch_id and practice_id=p_practice_id
 ), nearby as (
   select p.practice_id,p.practice_name,p.legal_name,p.primary_specialty,p.primary_specialty_code,p.latitude,p.longitude,
     extensions.st_distance(p.location,client.location)/1609.344 as miles
   from public.medical_practices p where p.location is not null and p.state='VA'
     and extensions.st_dwithin(p.location,client.location,cfg.radius_miles::double precision*1609.344)
 ), competitors as (
   select p.* from nearby p where p.practice_id<>p_practice_id
     and p.primary_specialty_code in (select destination_taxonomy from practiceiq.mvp_compatibility)
     and regexp_replace(upper(coalesce(p.legal_name,p.practice_name,'')),'[^A-Z0-9]','','g') <>
         regexp_replace(upper(coalesce(client.legal_name,client.practice_name,'')),'[^A-Z0-9]','','g')
     and not exists(select 1 from practiceiq.affiliation_evidence_candidates c join client_groups g using(cms_group_pac_id)
                    where c.batch_id=cfg.evidence_batch_id and c.practice_id=p.practice_id)
     and exists(select 1 from links l where l.practice_id=p.practice_id)
 ), destinations as (
   select l.clinician_npi, l.practice_id from links l where l.practice_id=p_practice_id or l.practice_id in (select practice_id from competitors)
 ), sources as (
   select l.clinician_npi,l.practice_id,x.first_name,x.last_name,x.primary_taxonomy_code,n.practice_name,n.primary_specialty,n.latitude,n.longitude,n.miles,
     (select count(*) from links l2 where l2.practice_id=l.practice_id) as source_size
   from links l join nearby n on n.practice_id=l.practice_id join practiceiq.providers x on x.npi=l.clinician_npi
   where n.practice_id<>p_practice_id and n.practice_id not in (select practice_id from competitors)
     and regexp_replace(upper(coalesce(n.legal_name,n.practice_name,'')),'[^A-Z0-9]','','g') <>
         regexp_replace(upper(coalesce(client.legal_name,client.practice_name,'')),'[^A-Z0-9]','','g')
     and not exists(select 1 from practiceiq.affiliation_evidence_candidates c join client_groups g using(cms_group_pac_id)
                    where c.batch_id=cfg.evidence_batch_id and c.practice_id=n.practice_id)
     and exists(select 1 from practiceiq.mvp_compatibility c where c.destination_taxonomy=client.primary_specialty_code and c.source_taxonomy=x.primary_taxonomy_code)
 ), flows as (
   select s.clinician_npi,
      sum(e.patient_count) filter(where d.practice_id=p_practice_id) as client_flow,
      sum(e.patient_count) filter(where d.practice_id<>p_practice_id) as competitor_flow,
      count(*) filter(where e.patient_count is null or e.suppressed) as missing
   from sources s join practiceiq.referral_edges e on e.release_id=cfg.edge_release_id and e.from_npi=s.clinician_npi
   join destinations d on d.clinician_npi=e.to_npi group by s.clinician_npi
 ), metrics as (
   select s.*,coalesce(f.client_flow,0)::numeric as client_flow,coalesce(f.competitor_flow,0)::numeric as competitor_flow,f.missing
   from sources s join flows f using(clinician_npi)
 ), scored as (
   select m.*, case when missing>0 then null else round(100*(
       cfg.flow_weight*least(competitor_flow/cfg.volume_cap,1) +
       cfg.revenue_weight*case when cfg.collections_per_patient=0 or cfg.capture_base=0 then 0 else least(competitor_flow/cfg.volume_cap,1) end +
       cfg.proximity_weight*greatest(0,1-miles/cfg.radius_miles::double precision) +
       cfg.leakage_weight*coalesce(competitor_flow/nullif(client_flow+competitor_flow,0),0) +
       cfg.size_weight*least(source_size/cfg.size_cap,1))) end as score
   from metrics m
 )
 select jsonb_build_object('practice_id',client.practice_id,'practice_name',client.practice_name,'specialty',client.primary_specialty,
   'latitude',client.latitude,'longitude',client.longitude,
   'market_summary',jsonb_build_object('competitor_count',(select count(*) from competitors),'potential_referral_sources',(select count(*) from sources),'sources_with_observed_edges',(select count(*) from scored)),
   'dataset',jsonb_build_object('release_id',release_record.id,'source',release_record.source,'synthetic',release_record.is_synthetic,'version',release_record.version,'period_start',release_record.period_start,'period_end',release_record.period_end),
   'assumptions',jsonb_build_object('radius_miles',cfg.radius_miles,'collections_per_patient',cfg.collections_per_patient,'capture_low',cfg.capture_low,'capture_base',cfg.capture_base,'capture_high',cfg.capture_high),
   'limitations',jsonb_build_array('Counts are shared-patient edge sums and can overlap; they are not confirmed referrals or unique patients.', 'Unobserved and suppressed edges may be missing; leakage and revenue are estimates, not observed complete totals.', 'Affiliations are automated CMS and NPPES matches, not verified current employment.', 'Revenue assumptions and score weights are illustrative and unvalidated.'),
   'opportunities',coalesce((select jsonb_agg(jsonb_build_object('source_npi',s.clinician_npi,'provider_name',trim(concat_ws(' ',s.first_name,s.last_name)),
      'source_practice',s.practice_name,'source_practice_id',s.practice_id,'source_specialty_code',s.primary_taxonomy_code,
      'source_specialty',case s.primary_taxonomy_code when '207Q00000X' then 'Family Medicine' when '207R00000X' then 'Internal Medicine' when '207P00000X' then 'Emergency Medicine' when '208100000X' then 'Physical Medicine and Rehabilitation' when '2081P2900X' then 'Pain Medicine' when '2081S0010X' then 'Sports Medicine' when '207QS0010X' then 'Sports Medicine' else 'Unknown' end,
      'latitude',s.latitude,'longitude',s.longitude,'distance_miles',round(s.miles::numeric,2),'drive_time_minutes',null,
      'observed_market_flow',case when s.missing=0 then s.client_flow+s.competitor_flow end,'client_flow',case when s.missing=0 then s.client_flow end,
      'competitor_flow',case when s.missing=0 then s.competitor_flow end,'estimated_leakage',case when s.missing=0 then s.competitor_flow end,
      'revenue_low',case when s.missing=0 then s.competitor_flow*cfg.capture_low*cfg.collections_per_patient end,
      'revenue_base',case when s.missing=0 then s.competitor_flow*cfg.capture_base*cfg.collections_per_patient end,
      'revenue_high',case when s.missing=0 then s.competitor_flow*cfg.capture_high*cfg.collections_per_patient end,
      'opportunity_score',s.score,'score_components',jsonb_build_object('flow',round(100*least(s.competitor_flow/cfg.volume_cap,1),1),'revenue',case when cfg.collections_per_patient=0 or cfg.capture_base=0 then 0 else round(100*least(s.competitor_flow/cfg.volume_cap,1),1) end,'proximity',round((100*greatest(0,1-s.miles/cfg.radius_miles::double precision))::numeric,1),'leakage',round(100*coalesce(s.competitor_flow/nullif(s.client_flow+s.competitor_flow,0),0),1),'source_size',round(100*least(s.source_size/cfg.size_cap,1),1)),'synthetic_data',release_record.is_synthetic,'confidence','high rule-based; uncalibrated','missing_edge_counts',s.missing)
      order by s.score desc nulls last,s.clinician_npi) from scored s),'[]'::jsonb)) into result;
 return result;
end $$;
revoke all on function public.get_referral_opportunities(text) from public,anon,authenticated;
commit;
