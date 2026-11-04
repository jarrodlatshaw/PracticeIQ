-- Minimal isolated stand-in for existing Supabase objects, not a schema export.
create role anon nologin;
create role authenticated nologin;
create table public.medical_practices (practice_id text primary key);
alter table public.medical_practices enable row level security;
insert into public.medical_practices values ('synthetic-va');
