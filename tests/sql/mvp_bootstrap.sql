create schema extensions;
create extension postgis with schema extensions;
create role anon nologin;
create role authenticated nologin;
create table public.medical_practices (
 practice_id text primary key, practice_name text, legal_name text,
 primary_specialty text, primary_specialty_code text, latitude double precision,
 longitude double precision, state text, location extensions.geography(point,4326)
);
