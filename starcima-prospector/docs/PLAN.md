# StarCima Prospector — Architecture & Implementation Plan

Private internal prospecting tool for StarCima, LLC. Single owner, no SaaS features.
Status: **proposal awaiting approval** (prepared 2026-11-20). Prices were checked on that date; confirm on each vendor's page before you sign up.

---

## 1. Development environment (inspected)

| Item | Finding |
|---|---|
| Repository | `starcima/photo-converter`, which holds the unrelated Sony RAW→JPG desktop app. The prospector should get its **own repository**; see the decisions in §11. |
| Runtimes | Node 22.23, npm 10.9, pnpm 10.28, Python 3.13, Docker 29, psql 16 client. Chromium and Playwright are preinstalled. |
| Resources | 4 CPU, 15 GB RAM, 60 GB free disk. That is enough to run Postgres, Lighthouse and Playwright locally for development and tests. |
| Limits | This is an ephemeral cloud container, so all work must be pushed to git. Production cannot run here. It needs its own small host (§2). |

---

## 2. Architecture evaluation

### Recommendation

```
┌──────────────────────────┐     ┌────────────────────────────────────────┐
│  Next.js + TypeScript    │     │  Python 3.13 worker (one process)      │
│  dashboard (App Router)  │     │  • scheduler (reads `searches`)        │
│  • Supabase Auth (1 user)│     │  • job runner (Postgres queue)         │
│  • reads/writes via RLS  │     │  • discovery / detection / audit /     │
│  • enqueues jobs         │     │    enrichment / scoring / AI / notify  │
│  • streaming AI chat     │     │  • Playwright + Lighthouse (Chromium)  │
└────────────┬─────────────┘     └───────────────┬────────────────────────┘
             │                                   │
             └──────────► Supabase (Postgres, Auth, Storage, daily backups) ◄─┘
                         jobs table = the queue (SELECT … FOR UPDATE SKIP LOCKED)
```

| Proposed component | Verdict | Reasoning |
|---|---|---|
| Next.js + TypeScript dashboard | **Keep** | Good fit for a data-heavy UI. Server components keep API keys server-side. |
| Supabase (Postgres + Auth) | **Keep** | Managed Postgres, auth with TOTP MFA, Storage for screenshots and daily backups in a single $25/mo service. Row Level Security locks every table to the owner. |
| Python for auditing and data | **Keep** | It has the best tooling for the job: Playwright, DuckDB/GeoParquet for bulk place data, BeautifulSoup/extruct for SEO and schema parsing, and the Anthropic SDK. |
| PageSpeed Insights API | **Keep (primary)** | Free (about 25k requests/day). It returns lab Lighthouse data **and** real-user Chrome UX (Core Web Vitals) field data when Google has it. |
| Lighthouse (local) | **Keep (fallback)** | Runs when PSI fails or is rate-limited. It is free and runs in the worker's Chromium. |
| Background jobs | **Change: no Redis/Celery/Inngest** | A `jobs` table in the same Postgres database with `SKIP LOCKED`, retries, backoff, priorities and dedupe keys. This volume (thousands of jobs a day) is far below what needs a broker, and it saves a service. |
| Vercel hosting | **Change: one small VPS** | Vercel's free Hobby tier is non-commercial only, so you would need Pro at $20/mo. Serverless functions also cannot run Chromium audits that take several minutes. A single VPS (Hetzner or DigitalOcean, 4–8 GB) runs the dashboard and worker under Docker Compose with Caddy for HTTPS. It costs about the same and is simpler. Vercel Pro plus a worker host remains an option if you prefer it. |
| Claude API | **Keep, scoped** | Used for things code can't measure: visual and design judgment from screenshots, a contextual summary, service recommendations and outreach drafts. It never produces technical metrics. |
| "Licensed business discovery APIs" | **Use open licensed data first, paid APIs selectively** | See §3. Overture Maps Places plus the NPI Registry plus Texas state data give a large, storable, attribution-friendly base at $0. Google Places is used for targeted verification within its terms. |

---

## 3. Discovery data sources (research)

| Source | What it gives | Cost | Commercial use / retention | Role |
|---|---|---|---|---|
| **Overture Maps Places** (monthly GeoParquet release) | About 60M+ places with name, categories, address, lat/lng, and **websites, socials, emails and phones** fields. It excludes personal data. | Free (download by bounding box with DuckDB) | CDLA-Permissive-2.0, plus Apache 2.0 for records sourced from Foursquare. **Storable**; keep per-record source and license. | **Primary bulk discovery** for any industry or market. An empty `websites` field is the first "no website" signal. |
| **Foursquare OS Places** | About 100M POIs, 20+ attributes | Free (gated download) | Apache 2.0, storable | Optional second open source. It is largely merged into Overture already. |
| **NPI Registry (CMS/NPPES)** | Every US healthcare provider and practice: taxonomy (e.g. psychologist 103T, counselor 101Y, LCSW 1041C, dentist 1223), practice address and phone, **enumeration date**, and for organizations the **authorized official's name, title and phone**. | Free. The API is rate-limited per hour; the monthly bulk file is for volume. | Federal public data. Provider and business data only, **no patient data**. | **Healthcare discovery**, plus the "newly established practice" signal. It has no website field, so detection (§4) supplies that. |
| **Texas Comptroller open data**: weekly *New Sales Tax Permits*, *Active Franchise Tax Permit Holders* | New Texas businesses with outlet address and start dates. Some records include a phone number. | Free | Public records under Texas law | **"New businesses that may need a website"** in Texas. Other states can be added one registry at a time. |
| **Google Places API (New)** | The best coverage, including `websiteUri`, phone, rating and business status | Text Search Pro is $32/1k after 5k free a month. The **Enterprise SKU (needed for website and phone fields) is $35/1k after 1k free a month**, and each call returns up to 20 places. | **Restrictive.** The terms bar scraping or exporting content and building lead lists or substitute directories from Maps content. `place_id` may be cached; other content has ≤30-day limits. | **Verification only.** Store `place_id` plus our own derived facts (e.g. "Google listing shows no website as of date X"). Google-sourced name, phone and address are not kept past 30 days and are **excluded from CSV/Excel exports**. Off by default with a monthly cap. |
| **Brave Search API** (web + Place Search) | Web results to find an official site, social pages and directory listings | $5/1k requests, with a $5 monthly credit | Raw results may not be stored unless you buy a storage-rights plan. | **Transient lookup only.** We store the URL we then **visit and verify ourselves**, never the raw search response. |
| Paid B2B data (Data Axle, ZoomInfo, Apollo, Hunter) | Owner names and verified emails | $50–$500+/mo | Licensed for sales use | **Not in v1.** Hunter's verifier can be added later as a pluggable enricher if on-site emails aren't enough. |
| Facebook/Instagram | Social-only businesses | — | The Graph API page search requires app review, and scraping is prohibited. | We **record** social URLs found in sources or search results. We do not scrape Meta. |
| Manual / CSV import | Your own lists | — | Yours | Supported from Phase 2. |

**Example query flow.** For *"independent psychology and counseling practices within 50 miles of San Antonio with no website or poor websites"*:

1. Claude parses the text into structured filters: industries psychology and counseling, center San Antonio, radius 50 mi, website filter none or poor, exclude chains.
2. NPI is queried by taxonomy and the ZIPs inside the radius. Overture is queried by category and bounding box.
3. Records are merged and deduplicated.
4. Website detection runs, then audits on sites that exist, then scoring.

You can review and edit the parsed filters before a search is saved or scheduled.

---

## 4. Website detection (multi-signal, with confidence)

Signals collected per business, each one stored with its source and date:
1. Website or social fields from Overture, Foursquare and NPI (NPI has none), plus Google `websiteUri` when verification is enabled.
2. A Brave web search for `"<name>" <city> <state>` and `"<phone>"`. Candidate domains are scored.
3. Domain guesses (e.g. `businessname.com` and `.net`), checked with DNS and HTTP.
4. The email domain from source data (e.g. `info@acmeroofing.com` → `acmeroofing.com`).

**A candidate becomes "official" only after we fetch it** and find at least one of: a matching phone number (normalized E.164), a matching street address or ZIP, or a strong name match plus a matching city. We also reject directory and social domains (yelp, facebook, bbb, healthgrades, psychologytoday, …) and parked or for-sale pages.

`website_status` values:
- `has_website` (confidence 0–1)
- `social_only` (Facebook or Instagram found, no official site)
- `no_website_likely` (one source empty, search inconclusive)
- `no_website_confirmed` (≥2 independent sources empty **and** search plus domain guesses found nothing verifiable)
- `offline` (DNS or connection failure or 5xx on **two checks ≥24 h apart**)
- `parked`, `blocked` (bot protection; we **do not bypass** it and mark the result as such)
- `unknown`

---

## 5. Website audit and quality score (0–100)

Pipeline per site. Limits: the homepage plus up to 5 internal pages (contact and service pages). We respect `robots.txt` beyond the homepage, send one request per second per domain, and use an honest User-Agent.

| Category (weight) | Objective measurements | Claude's role |
|---|---|---|
| Visual design (20%) | Copyright year, last-modified date, legacy tech (Flash, table layouts, old jQuery or Bootstrap), font count, image resolution, stock-template fingerprints | **Primary.** Claude scores desktop and mobile screenshots against a fixed rubric (layout, typography, branding, imagery, navigation, professionalism) and must cite visual evidence. The score is labelled "AI-assessed". |
| Mobile usability (15%) | Viewport meta, horizontal overflow at 390 px, tap-target size, font size ≥16 px, click-to-call link, Lighthouse mobile | Secondary commentary only |
| SEO (20%) | Title and meta description presence and length, H1/H2 structure, canonical, robots/noindex, sitemap, alt text, LocalBusiness schema, NAP consistency, service and location pages, Lighthouse SEO | Notes on content gaps |
| Performance (15%) | PSI/Lighthouse mobile score, LCP/CLS/INP (field data when available), page weight, unoptimized images, render-blocking resources | None |
| Conversion (15%) | CTA above the fold, contact form present, phone visible in header, booking or quote widget, clicks to reach contact | Assessment of CTA clarity |
| Technical & accessibility (15%) | HTTPS and certificate validity, mixed content, broken links and 4xx/5xx, JavaScript console errors, Lighthouse accessibility and best practices | None |

Grades: 0–39 very poor · 40–59 below average · 60–74 average · 75–89 good · 90–100 excellent.
Businesses with no website get **no quality score**. They are shown as "No website (confirmed or likely)".
Every finding is stored as a row (category, severity, code, evidence, recommendation), so the score is always explainable and filterable.

Re-audit policy: a lightweight check every 30 days (HTTP status plus a content hash). A full audit runs only when the hash changes, or every 90 days.

---

## 6. Opportunity score (0–100, explained)

Each component is configurable in Settings, and every component stores a one-line reason.

| Component | Default weight | Examples |
|---|---|---|
| Website need | 35 | No website confirmed scores 35. Quality score 30 scores about 25. Quality score 85 scores about 3. Offline site scores 30. |
| Legitimacy & operating status | 15 | Active NPI or permit, address verified, appears in ≥2 sources. Closed, or unverifiable from a single source, scores 0. |
| Industry fit | 15 | From the `industries` table. High-ticket local services (counseling, dental, legal, roofing) rank high. |
| Contactability | 15 | Verified public phone 8, public business email 5, named administrator 2 |
| Market fit | 10 | Inside your target radius or states |
| Growth / new-business signal | 10 | NPI enumerated or permit issued in the last 12 months; new location; hiring |
| Penalties | — | Franchise or chain (corporate site), government entity, suppressed, or contacted in the last 90 days |

Tiers: 80–100 high priority · 60–79 good · 40–59 potential · 0–39 low.

**Data integrity.** Every contact value is tagged `verified` (seen on the business's own site or in an authoritative registry), `inferred` (e.g. one source only) or `unknown`. Emails are **never guessed or constructed**.

---

## 7. AI sales assistant

- **Automated (worker, via the Message Batches API at 50% cost):** visual audit assessment, prospect summary, top-3 deficiencies, recommended StarCima services.
- **On demand (dashboard, streaming):** "Analyze this prospect…" chat grounded in the stored audit, plus intro email, phone script, follow-ups and a downloadable prospect report (PDF).
- Inputs are only the stored, sourced facts. The prompt forbids inventing facts, and each claim references a finding ID.
- **Nothing is ever sent automatically.** Drafts move through draft → approved → "marked sent". An optional later step creates a **Gmail draft**, never sends it, and checks it against the suppression list first.
- Model choice is configurable per task. The default is Claude Opus 5.5 ($4 / $20 per M tokens). Claude Sonnet 5.5 ($2 / $10) is a cheaper option for bulk audits.

---

## 8. Database schema (Postgres / Supabase)

```sql
-- reference
industries(id, slug, name, npi_taxonomies text[], overture_categories text[],
           google_types text[], fit_score int, is_active bool)

-- core entity
businesses(id uuid pk, name, normalized_name, industry_id fk, categories text[],
           address_line, city, state, zip, county, geo geography(point),
           phone_e164, operating_status enum(active, closed, unknown),
           website_status enum(...§4), website_status_confidence numeric,
           is_chain bool, first_seen_at, last_seen_at,
           dedupe_key text unique, merged_into_id uuid null, suppressed bool)
business_sources(id, business_id fk, source enum(overture, fsq_os, npi, tx_comptroller,
           google_places, brave, csv, manual), source_record_id, source_url,
           license text, payload jsonb null,   -- payload only for storable sources
           fetched_at, expires_at null)        -- expires_at enforces Google's 30-day rule
           unique(source, source_record_id)

websites(id, business_id fk, url, domain, role enum(official, facebook, instagram,
           linkedin, yelp, directory, other), confidence numeric, signals jsonb,
           http_status, final_url, ssl_valid, status enum(live, redirect, offline,
           parked, blocked, error), content_hash, cms, last_checked_at)
website_checks(id, website_id, checked_at, http_status, ok bool, content_hash, error)

contacts(id, business_id fk, kind enum(phone, email, person, social, form_url),
           value, label, role, verification enum(verified, inferred, unknown),
           source_url, collected_at)

audits(id, website_id fk, version, started_at, finished_at, status,
           score_overall, score_design, score_mobile, score_seo, score_performance,
           score_conversion, score_technical, grade,
           psi jsonb, lighthouse jsonb, crux jsonb, pages_crawled int,
           screenshot_desktop_path, screenshot_mobile_path,
           ai_assessment jsonb, ai_model, cost_usd numeric)
audit_findings(id, audit_id fk, category, severity enum(critical, major, minor, info),
           code, title, evidence, recommendation, page_url)

opportunity_scores(id, business_id fk, score, tier, components jsonb,
           explanation text, scoring_version, computed_at, is_current bool)

-- searches & automation
searches(id, name, query_text, filters jsonb, sources text[],
           schedule enum(manual, daily, weekly, monthly), cron text, is_active,
           max_new_per_run int, monthly_budget_usd numeric, last_run_at, next_run_at)
search_runs(id, search_id, started_at, finished_at, status, found, new, updated,
           cost_usd, error)
search_results(search_run_id, business_id, is_new)
jobs(id bigserial, type, payload jsonb, status enum(queued, running, done, failed, dead),
           priority, attempts, max_attempts, run_after, locked_by, locked_at,
           dedupe_key unique, last_error, created_at, finished_at)
api_usage(id, provider, sku, units, est_cost_usd, job_id, at)  -- cost ledger + caps

-- sales workflow
pipeline(business_id pk, stage enum(new, reviewing, contacted, replied, meeting,
           won, lost, not_a_fit), next_follow_up date, updated_at)
notes(id, business_id, body, created_at)
outreach_drafts(id, business_id, kind enum(email, phone_script, followup, report),
           subject, body, model, status enum(draft, approved, sent_manually, discarded),
           created_at)
suppression_list(id, kind enum(domain, email, phone, business), value, reason, created_at)
notifications(id, kind, business_id, payload, sent_at, read_at)
settings(key pk, value jsonb)          -- weights, budgets, schedules, target markets
event_log(id, level, source, message, context jsonb, at)
```

RLS is enabled on every table, restricted to the single owner UID. The worker uses the service-role key, which lives on the server only. PostGIS handles radius queries. The schema uses `pg_trgm` for fuzzy name dedupe. Deduplication matches on normalized phone, then normalized address plus name similarity ≥0.85, then domain.

---

## 9. Directory structure

```
starcima-prospector/
├── apps/web/                       # Next.js (current stable) dashboard (TypeScript)
│   ├── app/(auth)/login/
│   ├── app/(dash)/                 # overview, prospects, prospects/[id], searches,
│   │                               # searches/[id], jobs, suppression, settings
│   ├── app/api/                    # export (csv/xlsx), assistant (streaming), enqueue
│   ├── components/  lib/ (supabase, queries, formatting)  tests/
├── worker/                         # Python 3.13 package "prospector"
│   ├── prospector/
│   │   ├── main.py  config.py  db.py  queue.py  scheduler.py  ratelimit.py  budget.py
│   │   ├── discovery/   overture.py npi.py tx_comptroller.py google_places.py
│   │   │                brave.py csv_import.py query_parser.py geo.py
│   │   ├── resolve/     normalize.py dedupe.py website_detect.py
│   │   ├── audit/       fetch.py render.py psi.py lighthouse.py seo.py mobile.py
│   │   │                conversion.py technical.py visual_ai.py score.py
│   │   ├── enrich/      contacts.py
│   │   ├── scoring/     opportunity.py
│   │   ├── ai/          client.py prompts/ summaries.py outreach.py
│   │   └── notify/      email.py
│   └── tests/                      # pytest, with recorded HTTP fixtures (no live calls)
├── supabase/migrations/  supabase/seed.sql   # industries, taxonomy maps
├── docker-compose.yml  Caddyfile  .env.example
├── .github/workflows/ci.yml        # lint, typecheck, pytest, migrations check
└── docs/  (PLAN.md, RUNBOOK.md, DATA_SOURCES.md)
```

---

## 10. Accounts, keys and costs

### Accounts you will need

| Account | Needed by | Notes |
|---|---|---|
| GitHub repository `starcima/starcima-prospector` | Phase 1 | You create it; I add it to the session. |
| Supabase (Pro recommended once real data exists) | Phase 1 | Project URL, anon key, service-role key |
| Anthropic API key | Phase 5 (Phase 2 for query parsing) | Set a monthly spend limit in the Console. |
| Google Cloud project | Phase 3 | PageSpeed Insights API key (free). Places API (New) is optional, with billing, a **budget alert and a quota cap**. |
| Brave Search API | Phase 3 | Search plan |
| VPS (Hetzner or DigitalOcean) and a subdomain, e.g. `prospects.starcima.com` | Phase 7 | |
| Email for notifications: Resend (free 3k/mo) or a Google Workspace SMTP app password | Phase 6 | |
| Optional: Sentry (free tier) | Phase 7 | Error tracking |

None of the free open sources (Overture, NPI, Texas Comptroller) need a key.

### Estimated monthly operating cost

Assumes about 2,000 businesses discovered and about 600 websites audited a month.

| Item | Low | Typical | Notes |
|---|---|---|---|
| Supabase | $0 (Free) | $25 (Pro) | The Free tier has no backups and pauses after a week of inactivity. Use Pro for production. |
| VPS (dashboard + worker) | $8 | $15–25 | 4–8 GB RAM for Chromium |
| Claude API | $10 | $25–50 | About $0.02–0.04 per audit with Batches. About $0.05 per outreach draft. Hard cap set in settings. |
| Brave Search | $0 | $5–15 | About 1–3k lookups; $5 credit included |
| Google Places (verification) | $0 | $0–35 | Usually within the 1k free Enterprise calls |
| PageSpeed Insights, Overture, NPI, Texas data | $0 | $0 | |
| Email notifications | $0 | $0 | |
| **Total** | **≈ $20** | **≈ $70–150** | Budget caps stop jobs before limits are exceeded. |

**Development effort.** Built incrementally in this environment, roughly one to two working sessions per phase. Phases 3 (auditor) and 2 (discovery) are the largest.

---

## 11. Limitations

### Legal and compliance (not legal advice; worth a short review by your attorney)

1. **Google Maps Platform terms.** No scraping, no bulk export, no building lead lists from Maps content, and no persistent storage beyond `place_id`. We use Google only as a short-lived verification signal, and Google data is excluded from exports.
2. **Brave and other search APIs.** Results are used transiently. We store only facts we verify ourselves.
3. **No bypassing.** No CAPTCHA solving, no logins, no evading bot protection. Sites that block us are marked `blocked`.
4. **Healthcare.** Only provider and business directory data (NPI is public provider data). No patient information is collected. Testimonials or patient content seen on a site are not extracted into the database.
5. **CAN-SPAM** applies to commercial email, including B2B. Every email needs an accurate sender, a non-deceptive subject, StarCima's physical address and a working opt-out honored within 10 business days. The suppression list enforces opt-outs.
6. **TCPA / Texas telemarketing rules.** Manual calls to business lines are low-risk. Do not use autodialers, prerecorded calls or **texts to mobile numbers without consent**. Phone numbers may be flagged as possibly mobile. Texas also has its own telemarketing registration rules for some sales calls (Bus. & Com. Code ch. 302), which are worth confirming with counsel.
7. **Personal data.** Sole proprietors' names and phones in Comptroller or NPI data are personal data. They are stored only as business contacts, with source and date, and can be deleted on request through suppression.
8. **Robots and politeness.** We respect `robots.txt` for anything beyond the homepage audit, crawl slowly and identify ourselves.

### Technical

- "No website" is probabilistic. Confidence levels and the two-source rule reduce false negatives but cannot eliminate them.
- Open data under-covers very new or home-based businesses. The Texas permit feeds and NPI enumeration dates close part of that gap.
- NPI has no websites or emails. Emails come only from the business's own site, so expect many prospects with phone only.
- Owner names are rarely available legally. Exceptions are the NPI authorized official (organizations) and names published on the business's own site.
- The AI design score is subjective and labelled as such. Lighthouse scores vary ±5 between runs, so we store the median of PSI and lab results where needed.
- Bot-protected sites (Cloudflare challenges) cannot be audited by design.
- New-business data from other states needs one connector per state.

---

## 12. Implementation plan

| Phase | Deliverables | Done when |
|---|---|---|
| **1. Foundation** | Monorepo scaffold. Supabase migrations for the full schema plus RLS and seed industries. Single-user auth (sign-ups disabled, TOTP MFA). Dashboard shell: overview KPIs, prospects table with filters and pagination, prospect profile, settings, suppression list. CSV/XLSX export. Local dev via Docker Postgres. CI. | You can log in, see seeded or sample data, filter, open profiles and export. Tests pass. |
| **2. Discovery** | Overture (DuckDB bounding-box/category pulls), NPI (API plus bulk), Texas Comptroller feeds, CSV import, natural-language query parser, geo radius, normalization and dedupe, saved searches, run history. | The San Antonio counseling search returns real, deduplicated practices with sources. |
| **3. Detection + audits** | Website detection (§4), Playwright render and screenshots, PSI/Lighthouse, SEO, mobile, conversion and technical modules, Claude visual assessment, quality score, findings UI. | Real sites get reproducible audits with evidence and screenshots. |
| **4. Enrichment + scoring** | Contact extraction from official sites, verification flags, opportunity score with explanations, optional Google verification. | Every prospect shows a score with one reason per component. |
| **5. AI assistant** | Summaries, top deficiencies, service recommendations, email, phone script, follow-up and PDF report. Streaming chat. Approval workflow. | Drafts are grounded in findings, with no fabricated facts (spot-checked). |
| **6. Automation** | Scheduler (daily, weekly, monthly), job queue with retries, backoff, rate limits and budget caps, recheck and offline detection, change detection, rescoring, dedupe sweeps, email alerts for prospects scoring ≥80, daily digest. | It runs unattended for a week with correct alerts and cost inside caps. |
| **7. Hardening + deploy** | End-to-end tests, a runbook, VPS deploy (Docker Compose and Caddy), backups verified, health checks, Sentry. | Production URL live, restore from backup tested. |

### Decisions needed before Phase 1
1. **Repository.** A new `starcima-prospector` repo (recommended), or a `prospector/` folder inside `photo-converter`.
2. **Hosting.** VPS plus Supabase (recommended), or Vercel Pro plus a separate worker host.
3. **First markets and industries** to seed. The proposed default is San Antonio within 50 mi, Texas-wide for new businesses; counseling and psychology, dental, medical clinics, law, roofing and contractors.
4. **Claude model for bulk audits.** Opus 5.5 (default, higher quality) or Sonnet 5.5 (about half the cost).
