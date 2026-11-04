# PracticeIQ backend foundation

This is an initial implementation slice, not a working Supabase or Lovable backend. The additive migration has been tested only against an isolated local stand-in, not the existing Supabase project. The repository was empty at the start of this work; a screenshot and seven example rows identify parts of the existing PracticeIQ schema, but its complete definition is not available here. See [MVP design](docs/MVP_DESIGN.md) for the reference inventory, data model, calculations, planned API contracts, limitations and build sequence.

Requires Python 3.10+; no third-party dependencies for this slice. From the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m practiceiq.docgraph tests/fixtures/virginia_docgraph.csv /tmp/practiceiq-staged.csv --release synthetic --period 2024
```

The CSV contains synthetic NPIs and edge counts only; it is not actual Virginia provider data. The command validates and stages one CSV, reports source checksum and record count, and refuses to overwrite output. It does not upload, resolve providers, interpret edge direction, handle suppressed rows, or load Supabase. Validate the actual licensed release specification before importing. Keep licensed data outside Git.

`practiceiq.existing_practices` maps screenshot-described practice fields in memory and parses NPIs only with an explicitly selected format (the examples use semicolon-separated values; check consistency in the full dataset); its affiliations require review. It does not query or update Supabase. `practiceiq.identity` implements NPI check digits and a conservative evidence classification, not full entity resolution. `practiceiq.calculations` implements scenario arithmetic and a configurable weighted-score primitive. The numbers represent shared-patient edge-volume equivalents, which may overlap and do not establish referrals or unique patients. The toy example is not a clinical, financial, or production forecast.

Outstanding: integration with the real PracticeIQ database and security model; reviewed migrations; a complete Virginia synthetic fixture; CMS ingestion and benchmark derivation; transactional database loading, suppression and quarantine; geographic analysis; scored and secured RPCs; end-to-end tests and the final Lovable handoff. Do not expose this slice as a production API.

The proposed migration in `supabase/migrations/20261103000100_referral_foundation.sql` adds a private `practiceiq` schema with dataset releases, providers, candidate affiliations, shared-patient edges, CMS utilization, and revenue benchmarks. It uses `public.medical_practices.practice_id` as a foreign key, enables RLS, and revokes schema/table access from public, anon and authenticated. It does not create Lovable RPCs, grant customer access, ingest data, or modify existing objects. Review deployment, ownership, grants and integration before applying it to a real project.

`practiceiq.referral.analyze_source` calculates the client and competitor edge sums for one preselected source/release and reviewed destination sets. The caller must verify direction, specialty, geography, affiliation and completeness. If a relevant count is missing or coverage is declared incomplete, it withholds leakage and revenue estimates. Missingness in a suppressed dataset may not be visible in the rows: completeness must be based on release metadata, not absence of nulls.

SQL integration checks live in `tests/sql`. They were run on PostgreSQL 16/PostGIS against a minimal stand-in for `public.medical_practices`; they do not prove compatibility with all Supabase privileges, roles, data, or deployment configuration.

`practiceiq.nppes` can stream an extracted NPPES bulk CSV or a specified CSV member in a ZIP and stage selected NPIs from a one-NPI-per-line text file:

```sh
python3 -m practiceiq.nppes /path/to/nppes.csv /tmp/selected-nppes.csv --npis /path/to/npis.txt
```

It records a source checksum and reports matched and missing NPIs. Entity type is retained, but an NPPES identity alone does not establish a current practice affiliation. The staging script was tested with synthetic cases and the November 2, 2026 NPPES V2 bulk release: all nine user-supplied sample NPIs matched. Date semantics, release freshness, data coverage and operational ingestion still require review before production use. For a ZIP, pass `--member` with the exact CSV member name. It does not download the source or write to Supabase.

To stage individual NPPES records whose primary practice location is in Virginia:

```sh
python3 -m practiceiq.nppes_roster /path/to/nppes.zip 'npidata_pfile_20050523-20261102.csv' /tmp/virginia-individuals.csv
```

Use the exact data member for the release. The output is a source snapshot containing individual NPIs, primary location, taxonomy fields and deactivation/reactivation dates. It excludes secondary-only Virginia locations, includes non-physicians, and does not verify licenses, infer current active status, resolve affiliations, or load Supabase. Treat addresses as possible evidence only; use a separate group-affiliation source and review for practice matching.

The private, invoker-security SQL prototype in `20261104000200_affiliation_review_referral.sql` records review decisions and calculates one source's scenarios for one published release and a caller-supplied, preselected practice/specialty/geographic scope. It withholds estimates for unreviewed or expired decisions, suppressed counts, incomplete coverage, unverified direction, or missing approved destinations. Edge sums can overlap. A caller's completeness assertion must be supported by source coverage and suppression metadata. This is not a Lovable-facing RPC: no authenticated-user permissions, tenant authorization, selection of specialty/market, or review interface is implemented.

`python3 -m practiceiq.prepare_affiliation_import CANDIDATES.csv MANIFEST.json OUTPUT.sql` validates the candidate checksum and prepares an idempotent transactional SQL import; it does not execute the SQL. The manifest records CMS, NPPES and practice-export hashes, and the CMS release date is currently unknown. The 1,301-record import was tested twice against a disposable local database, producing one batch and no duplicates. Source checksums and license/date metadata must be checked before any real import. Apply the migrations and import only after reviewing existing Supabase ownership, grants, data freshness and tenant access. No live project has been changed.

## Referral MVP prototype

The current focus is `public.get_referral_opportunities(practice_id)`, implemented as a server-only SQL prototype in `supabase/migrations/20261104000300_referral_mvp.sql`. See `LOVABLE_HANDOFF.md` for contract and limitations. A real Falls Church orthopedic practice was exercised locally with **synthetic** edge counts; the demo is not evidence of real patient sharing. Existing CMS/NPPES location and group matches are used automatically when a provider maps to a single practice; ambiguous links are excluded. The current map covers selected orthopedic destination and referring specialties, with configurable radius, benchmark, rates and scoring weights.

A file-based local demonstration is available via `python3 -m scripts.run_referral_mvp --help`. `python3 -m practiceiq.prepare_docgraph_import --help` prepares a transaction for a validated CSV; it does not execute it and the release remains staged. A `--synthetic` flag labels invented files. A year currently sets a full calendar-year period, which must match the vendor's release definitions before use. Both scripts require input files that are not included in the repository.

The local SQL smoke test is `tests/sql/mvp_workflow.sql` and needs PostgreSQL/PostGIS with the preceding migrations and bootstrap. The function has no client grants or tenant authorization, no secured review interface and is not deployed. Provider/edge loads and settings must be configured before it returns data. No purchased DocGraph data has been loaded or tested.
