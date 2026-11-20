# Prospect Intelligence Platform: Feasibility Study (Phase 1)

**Owner:** StarCima, LLC
**Prepared:** 2026-11-20
**Status:** Draft for review. No implementation has started, and no money has been spent or committed.

> **How to read this.** Prices were checked in November 2026. Some came from vendor pages and some from third-party summaries, and each one is marked. Treat every dollar figure as a planning estimate until it is checked on the vendor's live pricing page. Items marked **⚖ Legal review** need a lawyer before launch.

---

## 0. Executive summary: what I think, including where I disagree

1. **The product is feasible and the technology is cheap.** Except for data licensing, every capability you listed can be built with commodity tools. At StarCima's own scale, running costs should be **about $150–$300 a month**.

2. **The hard problem is data rights, not software.** Most "find local businesses without websites" tools scrape Google Maps or resell Google Places data. My reading of Google's Maps Platform terms is that this is not allowed. The terms restrict scraping, bulk export, caching, and building your own database from Google Maps content. They also limit what you may store: you may keep `place_id` indefinitely and lat/lng for 30 days ([Places API policies](https://developers.google.com/maps/documentation/places/web-service/policies?authuser=6); [Service Specific Terms](https://cloud.google.com/archive/maps-platform/terms/maps-service-terms-20250501)). A SaaS that keeps a prospect database built on Google Places content is a real legal and business risk. **⚖ Legal review.**
   **My recommendation:** build the discovery layer on **commercially licensed open datasets** (Overture Maps Places, Foursquare OS Places), **official public registries** (the NPPES/NPI registry for healthcare, Secretary of State filings), and **paid licensed data** (Data Axle) where needed. Use Google Places only within its terms, if at all: live lookups that store only `place_id`.

3. **I disagree with "universal from day one" as a product strategy, but I agree with it as an architecture.** The cheap-tool market for agencies is crowded (Get Map Leads, BirdSift, LeadWebia, TheWebLead, WebbedLeads, Apify scrapers). The large B2B market is dominated by Apollo, ZoomInfo, and Clay. A product that does everything for everyone loses to both groups. The right plan:
   - Build a **universal data model** of profiles, signals, modules, and scoring rules.
   - Ship **one vertical solution** first: local-SMB digital-presence prospecting for agencies, which covers StarCima.
   - Add verticals as configuration templates only once paying demand appears.

4. **I disagree with Python/FastAPI, n8n, and agent frameworks for the core.** Use **one language, TypeScript, end to end**: Next.js, a Node worker, Playwright, and Lighthouse. Lighthouse and Playwright are Node-native, so a second language and service would only add operational load.
   - **n8n** can come later as a customer-facing integration option, not as the backbone.
   - **AI agents are not needed** for the pipeline. Deterministic code collects the facts. Single Claude API calls interpret them.

5. **First milestone:** a two-week **data-source and audit bake-off** in StarCima's home market, run in parallel with a one-hour legal consult. Its result decides the discovery strategy before we build the full platform. See §15.

---

## 1. Recommended universal SaaS architecture

```
┌──────────────────────────── Next.js app (Vercel) ─────────────────────────────┐
│ Dashboard (config-driven) · Profile builder · Prospect DB · Assistant · Billing│
└───────────────┬───────────────────────────────────────────────┬───────────────┘
                │ Supabase Auth (JWT w/ org claims)              │ Stripe webhooks
┌───────────────▼──────────────── Supabase Postgres ─────────────▼──────────────┐
│ Tenant tables (RLS)   │ Shared catalog (licensed-for-sharing data only)        │
│ Job queue (pg-boss / pgmq)  │ Vault (customer API keys)  │ Storage (screenshots)│
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ jobs
┌───────────────▼──────────── Worker service (Node, Fly.io/Railway/Render) ─────┐
│ Pipeline runner:  Discover → Resolve/Dedupe → Analyze (modules) → Score → AI   │
│ Modules (plug-ins): discovery.overture · discovery.npi · discovery.sos ·       │
│   web.presence · web.lighthouse · web.tech · web.seo · web.visual(AI) ·         │
│   contact.site_extract · contact.hunter · contact.verify · growth.signals       │
│ Provider adapters with rate limits, cost metering, source attribution          │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │
     Claude API (Haiku / Sonnet, Batch API)   PageSpeed/CrUX   Licensed data APIs
```

### Core design concepts (the "universal" part)

| Concept | What it is | Why it keeps the product universal |
|---|---|---|
| **Prospecting Profile** | A database record: target categories, geography, firmographic filters, enabled modules, scoring rules, services sold, outreach policy | New industries become new profiles and templates. No code changes. |
| **Module** | A versioned plug-in with a declared input (business entity, website URL, …) and declared output **signals** | Website audits are one module among many. A cleaning company enables `property.*` modules instead. |
| **Signal** | One typed observation: `{key, value, unit, method: deterministic\|ai\|provider, source, confidence, observed_at, evidence}` | Scoring, the UI, and AI all read signals. Facts and inferences are kept apart by `method`. |
| **Scoring Rule Set** | JSON rules (weights, thresholds, exclusions) evaluated against signals | Each customer defines "qualified" in its own way. Score explanations are generated mechanically from the rules that fired. |
| **Profile Template** | Starter configurations by vertical: "Web agency," "Cleaning company," … | Faster onboarding, and a marketplace later. |
| **Dashboard Layout** | Per-profile widget configuration that says which signal groups and panels to show | StarCima sees website audits; a cleaning company sees territory and property panels. |

**Pipeline pattern.** Each stage is an idempotent job keyed by `(org, profile, entity, module, version)`. Results are cached, with a TTL per module. Re-runs are cheap, history is preserved, and cost is metered per tenant.

**Deliberately excluded for now:** microservices, Kubernetes, Kafka/Redis, vector databases, multi-agent orchestration, and a separate Python service. Each can be added later if a measured need appears.

---

## 2. StarCima's initial configuration: "Website & Local SEO Opportunities"

**Profile: `starcima-web-presence-v1`**

| Setting | Initial value |
|---|---|
| Geography | StarCima's home metro, 25–40 mi radius (**needed from you:** the city or ZIP) |
| Categories (pilot) | Psychologists, counselors/therapists, dental practices, independent medical practices, legal, home services/contractors |
| Size | 1–50 employees, independent (exclude chains and franchises with corporate websites) |
| Modules | `discovery.overture`, `discovery.fsq_os`, `discovery.npi` (healthcare), `discovery.sos_new_filings`, `web.presence`, `web.lighthouse`, `web.tech`, `web.seo_basic`, `web.visual_ai`, `contact.site_extract`, `contact.verify`, `growth.signals` |
| Decision makers | Owner, practice owner, office manager, managing partner |
| Services catalog | Website design, redesign, SEO, local SEO, social media, digital marketing |
| Outreach | Email drafts only, human approval required, no SMS or autodialing |

**Signals and default weights (100 points of opportunity, plus gating rules):**

| Signal group | Example deterministic signals | Weight |
|---|---|---|
| Website presence | No website on any source · only a Facebook, Linktree, or directory page · domain parked or expired · site down/5xx | 25 |
| Mobile & performance | No viewport meta · Lighthouse mobile perf < 50 · LCP > 4 s (CrUX field data if available) · layout shifts | 15 |
| Technical health | No HTTPS / bad cert · broken links on homepage · JS errors · outdated CMS/jQuery versions · Flash/tables layout | 10 |
| SEO basics | Missing/duplicate title & meta description · no H1 · no LocalBusiness schema · no sitemap · not indexable · NAP mismatch | 15 |
| Conversion | No click-to-call · no contact form · no booking link (healthcare) · no clear CTA above the fold | 10 |
| Staleness | Copyright year ≥ 3 years old · last-modified headers · design assessed "outdated" (**AI, labeled**) | 10 |
| Growth / new business | Registered < 12 months ago · new location · hiring signals | 10 |
| Fit & contactability (gates) | Business active · in service area · has verified phone or general email · not on suppression list | gate |

**Exclusions:** chains/franchises, government, businesses on the suppression list, businesses with a recently rebuilt modern site (perf > 85 and SEO > 90 and copyright year current), and existing StarCima clients.

**Priority tiers:** **A ≥ 70** (call this week), **B 50–69** (email sequence), **C 35–49** (nurture), below 35 not qualified.

Every lead gets an explanation like this:
> *Score 78 (A). **Verified facts:** no website listed in Overture or NPI data; domain `example-dental.com` returns a GoDaddy parking page (checked 2026-11-20); the business is active per its NPI record, updated 2026-08. **AI assessment (medium confidence):** the Facebook page is the main web presence and shows no booking option. **Suggested services:** new website + Google Business Profile optimization.*

---

## 3. How other industries configure the same platform

| Customer type | Discovery modules | Key signals | Example scoring |
|---|---|---|---|
| **Marketing agency** | Same as StarCima | Ad pixels absent, no GA/GTM, weak social cadence, low review count | Weight marketing-maturity signals higher |
| **Healthcare consulting** | `discovery.npi`, state license boards | Provider count per practice, specialty mix, new locations, independent vs. system-owned | Gate: independent; weight growth signals |
| **Commercial cleaning** | Overture places + licensed property data (e.g. county parcel/assessor data, Data Axle) | Building type, square footage (licensed source), distance from depot, multi-tenant office | Territory polygon gate; weight sq ft and type |
| **B2B sales org** | Licensed firmographics (Data Axle, Apollo via customer's key) | Employee band, tech stack, hiring, funding | ICP match + intent signals |
| **IT/MSP** | Overture + tech detection | Outdated email provider, no SPF/DMARC, legacy CMS | Weight security/tech-debt signals |

Customers pick a **template**, then use a form-based profile builder to adjust geography, categories, modules, weights, and thresholds. Advanced users get a JSON rule editor. Modules a customer's plan doesn't include are hidden.

---

## 4. Technology stack

| Layer | Choice | Rationale / alternatives considered |
|---|---|---|
| Language | **TypeScript** throughout | One language. Lighthouse and Playwright are Node-native. *Python/FastAPI rejected: it would add a second runtime with no capability gain.* |
| Web app | **Next.js (App Router)** on **Vercel Pro** ($20/user/mo, [Vercel](https://vercel.com/docs/plans/pro-plan)) | Fast to build. Could move to self-hosting later. |
| DB/Auth/Storage | **Supabase Pro** ($25/org/mo, [Supabase pricing](https://supabase.com/pricing)) | Postgres + RLS for tenant isolation, Auth, Storage, Vault, pgmq/cron. Avoids running separate auth, queue, and storage services. |
| Jobs | **pg-boss** or **Supabase Queues (pgmq)** + `pg_cron` | The queue lives in Postgres, so there's no Redis to run. *Trigger.dev/Inngest are fine alternatives if we want a hosted dashboard.* |
| Worker | Node container on **Fly.io / Railway / Render** (~$10–40/mo) | Runs headless Chromium for crawling, screenshots, and Lighthouse. Vercel functions are a poor fit for browser jobs. |
| Website audits | **Lighthouse (local)** + **PageSpeed Insights API** + **CrUX API** | The PSI API is free, with a default of about 25,000 requests/day per project ([third-party summary](https://unlighthouse.dev/learn-lighthouse/pagespeed-insights-api/rate-limits)). Local Lighthouse is the fallback. |
| AI | **Claude API**, model-tiered (see §9) | |
| Payments | **Stripe Billing** (subscriptions + metered usage) | Industry standard. Supports usage-based add-ons. |
| Email sending (later) | Customer's own Google Workspace/Microsoft 365 via OAuth, or Postmark/Resend | Sending from the customer's own mailbox protects deliverability and puts legal responsibility on the right party. |
| Observability | Sentry (free tier) + Postgres cost/usage tables | |
| Automation for customers | Webhooks + Zapier/Make/n8n connectors **later** | Customers can automate. The core doesn't depend on n8n. |
| Dev tooling | Claude Code in this kind of session; GitHub Actions CI | |

---

## 5. Database design

The model has two layers:
- a **shared catalog** of business entities and our own measurements, holding only data whose license allows sharing across tenants;
- **tenant-private overlays** holding scores, contacts, notes, campaigns, and anything licensed per customer.

Every tenant table carries `org_id` and is protected by RLS.

```
-- Tenancy & billing
organizations(id, name, plan, white_label jsonb, stripe_customer_id, created_at)
memberships(org_id, user_id, role)                   -- owner|admin|member|viewer
usage_ledger(id, org_id, meter, qty, unit_cost, provider, job_id, at)
org_secrets(org_id, provider, vault_secret_id)       -- BYO API keys (Supabase Vault)

-- Configuration (drives everything)
profile_templates(id, vertical, name, config jsonb, version)
prospecting_profiles(id, org_id, name, template_id, geography geojson,
                     categories text[], filters jsonb, modules text[],
                     services jsonb, outreach_policy jsonb, schedule cron, active)
scoring_rule_sets(id, org_id, profile_id, version, rules jsonb, thresholds jsonb)
module_registry(key, version, inputs, outputs jsonb, cost_class, plan_min)

-- Shared catalog (cross-tenant, license-permitting only)
businesses(id, canonical_name, normalized_phone, domain, address, geo geography,
           categories text[], status, first_seen, last_verified)
business_sources(business_id, source, source_record_id, license, retrieved_at,
                 shareable bool, raw jsonb)          -- attribution + licensing flag
website_snapshots(id, domain, fetched_at, http_status, final_url, tech jsonb,
                  lighthouse jsonb, seo jsonb, screenshot_path)

-- Tenant overlay
prospects(id, org_id, profile_id, business_id, status, tier, score,
          score_breakdown jsonb, first_discovered, last_scored, owner_user_id)
signals(id, org_id NULL=shared, business_id, module, key, value jsonb,
        method, source, confidence, evidence jsonb, observed_at, expires_at)
contacts(id, org_id, business_id, kind(phone|email|person|social), value,
         person_name, title, source, confidence, verification_status, verified_at)
ai_artifacts(id, org_id, prospect_id, kind(summary|outreach|callprep|report),
             model, prompt_version, content, input_signal_ids uuid[], created_at)
activities(id, org_id, prospect_id, type, payload, user_id, at)    -- CRM-lite
campaigns / campaign_steps / outbound_messages(approval_status, approved_by, sent_at)
suppression_list(org_id NULL=global, kind(email|domain|phone), value, reason, at)
discovery_runs / jobs(id, org_id, profile_id, stage, status, cost, started, ended)
```

Notes:
- Deduplication resolves on normalized phone, registrable domain, and address hash plus geo distance and name similarity (`pg_trgm`). Merges are recorded so history survives.
- Raw Google content never enters `businesses` or `business_sources` (`shareable=false`, `place_id` only).

---

## 6. Business discovery integrations

| Source | Coverage / fit | Cost | License / risk |
|---|---|---|---|
| **Overture Maps – Places** | Global POIs with names, categories, websites, phones, socials | Free (bulk download) | Permissive open data licensing (CDLA-Permissive-2.0, per my knowledge of Overture's terms). Commercial use OK, with attribution. **Verify freshness per category.** |
| **Foursquare OS Places** | About 100M POIs, open release | Free | Released under Apache 2.0 (per my knowledge, to verify). The Pro/Premium API is priced by volume and quoted on request ([Foursquare](https://location.foursquare.com/?p=19), [G2](https://www.g2.com/products/foursquare-places-api/pricing)). |
| **NPPES NPI Registry** | Every US healthcare provider: taxonomy (psychologist, counselor, dentist…), practice address, phone, last-updated date | Free API + bulk files | Federal public data. No PHI. **Ideal for the healthcare pilot.** |
| **State business registrations** (Secretary of State) | New LLC/corp filings, the "newly established" signal | Free–low, varies by state; OpenCorporates offers paid API plans ([OpenCorporates](https://opencorporates.com/pricing/)) | Varies by state. Some states sell bulk files. Registered-agent addresses are noisy. |
| **Data Axle API** | Licensed SMB firmographics, including employees and SIC/NAICS | About $50–75 per 1,000 records (3k–100k/mo), per a [third-party summary](https://fullenrich.com/content/data-axle-pricing) | Commercial license. Check the redistribution terms for SaaS. |
| **Google Places API (New)** | Best freshness and coverage, including `websiteUri` and business status | Text Search Pro is about $25–32 per 1,000 calls after a free monthly cap; sources conflict ([Google pricing](https://developers.google.com/maps/billing-and-pricing/pricing)) | **High risk for a lead database.** Store `place_id` only. Live display requires attribution. **⚖ Legal review** before any use. |
| SerpAPI / Outscraper / Apify Google Maps scrapers | Popular with competitors | Cheap | **Rejected.** They scrape Google, which violates the requirement not to bypass terms. |
| Industry directories (state license boards, ADA, Psychology Today, Avvo, BBB) | Niche coverage | Varies | Only via official APIs or licensed feeds. Most prohibit scraping. |

**Strategy:**
1. Seed from Overture + FSQ OS + NPI. These are free and licensed.
2. Add SOS filings for new businesses.
3. Measure gaps in the bake-off.
4. Buy Data Axle only if coverage gaps justify it.
5. Every adapter shares one interface, `discover(profile, geo) → candidate[]`, with rate limits, cost metering, and a `license` tag. No single provider is required.

---

## 7. Website intelligence integrations

All of this is **our own first-party measurement** of public websites. It's cheap, defensible, and shareable across tenants.

| Check | Tool | Cost |
|---|---|---|
| Presence & resolution | DNS lookup, HTTP fetch, redirect chain, parked-domain fingerprints, social-only detection | Compute only |
| Domain age / registration | RDAP (free public protocol) | Free |
| Performance & mobile | Lighthouse locally, plus the PSI API (lab) and CrUX API (real-user field data) | Free within quota |
| Tech stack / outdatedness | Open-source Wappalyzer-style fingerprints (e.g. community `webappanalyzer` ruleset), library versions | Free |
| SEO basics | Our own parser: title/meta/H1, canonical, robots, sitemap, schema.org LocalBusiness, NAP consistency vs. source data | Free |
| Broken functionality | Playwright: console errors, 4xx links on homepage plus 1 level deep, form presence, `tel:`/`mailto:` links | Compute |
| Visual / design quality | Full-page screenshot → Claude vision rates "dated design," CTA clarity, trust signals. **Stored as `method=ai` with a confidence score** | ~$0.001–0.01/site |
| Accessibility (bonus selling point) | Lighthouse a11y / axe-core | Free |

Politeness rules: respect `robots.txt`, limit to about 10 pages per site, identify with a clear user-agent, use per-domain rate limits, and never authenticate or bypass CAPTCHAs. Snapshots are cached for 30–90 days.

---

## 8. Contact enrichment options

| Option | Use | Cost (verify) | Notes |
|---|---|---|---|
| **Website extraction (first-party)** | Published phone, general email, contact page, social links, team page names | Compute | The best source. Evidence is the page URL. |
| **NPI / SOS records** | Practice phone; registered officers/agents (owner names) | Free | Public record, attributed. |
| **Hunter.io API** | Domain email search, finder, verifier | Seat plans about $34–$299/mo with 2k–25k credits. The API is priced separately ([Hunter](https://hunter.io/pricing), [summary](https://www.saleshandy.com/blog/hunter-io-pricing/)) | Good for SMB domains. |
| **Apollo.io** | People/decision-maker data | $49–$119/seat/mo; API access terms unclear; standard plans reportedly internal use only ([summary](https://fullenrich.com/content/apollo-pricing)) | **Do not resell. Offer as BYO-key.** |
| **ZeroBounce** | Email verification | $39 for 2,000 credits (about $0.02/check); cheaper at volume ([ZeroBounce](https://www.zerobounce.net/email-validation-pricing)) | Required before any send. |
| Clay / ZoomInfo / Seamless | Enterprise enrichment | Clay $185–$495/mo; ZoomInfo SMB reportedly ~$40k+/yr ([summary](https://www.spendhound.com/marketplace/clay-pricing)) | Not for the MVP. |

**SaaS licensing pattern.** For people-level data, use **bring-your-own-key**: the customer connects its own Apollo or Hunter account, so the customer is the licensee and we never redistribute. For StarCima now, a Hunter Starter plan plus ZeroBounce pay-as-you-go is enough.

**Rules carried into code:**
- Never generate guessed emails (`firstname@domain`) and present them as found. If pattern guessing is ever offered, it's labeled "unverified pattern guess" and must pass verification before use.
- Every contact stores its source, confidence, and verification date.
- No patient data. Review text, which can contain health information, is not stored.

---

## 9. AI architecture

**Principle: deterministic code collects facts, and Claude interprets them.** There is no autonomous agent in the core pipeline. Every AI output links back to the IDs of the signals it was given, so we can audit it and catch fabrication.

| Task | Model | Mode | Rough cost |
|---|---|---|---|
| Category classification, chain/franchise detection, page-type extraction | Claude Haiku 5.5 ($0.10/$0.50 per M tokens) | Batch API (50% off), structured outputs | < $0.001/business |
| Visual design assessment (screenshot) | Claude Sonnet 5.5 ($2/$10 per M) or Haiku 5.5 after eval | Batch | ~$0.005–0.01/site |
| Prospect summary + "why qualified" narrative + service recommendations | Sonnet 5.5 | On-demand or nightly batch for A/B tiers only | ~$0.01–0.02/prospect |
| Outreach drafts, follow-ups, call prep, PDF audit report text | Sonnet 5.5 (Opus 5.5 at $4/$20 as an opt-in "premium" option) | On demand, user-triggered | ~$0.01–0.05/draft |

Prices are from Anthropic's current model table. Prompt caching (cache reads at about 10% of the input price) applies to the per-tenant system prompt holding the services catalog and voice. The Batch API is 50% off for nightly jobs. Model choice per task is your call; these are my cost-conscious defaults, and I'll show you eval results before we lock them in.

**Guardrails:**
- Prompts receive only signals and evidence and must cite signal keys. Outputs are validated with a JSON schema.
- The UI renders sections labeled **"Verified facts"** and **"AI assessment"** separately.
- An **outreach policy engine** enforces human approval, suppression-list checks, the CAN-SPAM footer, and per-day send caps. Nothing is sent without an explicit user action, unless a customer later configures auto-send within strict policies.
- The assistant is **tenant-configured**: services, value propositions, tone, and banned claims all come from the profile. It is not hard-coded to web design.

---

## 10. Multi-tenant security strategy

1. **Shared database, `org_id` on every tenant row, Postgres RLS enforced on every tenant table.** Policies are written as `org_id in (select org_id from memberships where user_id = auth.uid())`.
2. **The service role is used only in the worker**, and every worker query is explicitly scoped by `org_id` through a single data-access layer. CI runs automated **cross-tenant isolation tests**: user A tries to read org B's prospects, contacts, signals, and AI artifacts, and every attempt must fail.
3. **Shared vs. private data:** the shared catalog holds only `shareable=true` source data and our own website measurements. Scores, contacts, notes, campaigns, and AI outputs are always private. AI prompts are built per tenant and never mix tenants' data.
4. **Secrets:** customers' API keys are stored in Supabase Vault and decrypted only inside the worker.
5. **Roles:** owner/admin/member/viewer, plus **agency sub-accounts** (a parent org manages child client orgs) for white-label.
6. **Audit log** of exports, sends, and role changes. **Export limits** per plan, to deter data hoarding and protect license terms.
7. **Standard hygiene:** MFA, rate-limited APIs, Dependabot, backups and point-in-time recovery (Supabase Pro), and a data-retention job that enforces source TTLs, e.g. the 30-day lat/lng rule if Google is ever used.
8. **Later, for Enterprise:** SOC 2 readiness, SSO/SAML, data residency.

---

## 11. Estimated MVP build costs (cash, not labor)

| Item | Estimate |
|---|---|
| Dev/staging infra (Supabase free → Pro, Vercel Hobby → Pro, worker) | $0–$80/mo during build |
| Claude API during development and evals | $20–$75 total |
| Hunter Starter (1 month) + ZeroBounce 2k pack | ~$75–$90 |
| Google Maps Platform for the bake-off comparison only (optional, within free caps) | $0–$25 |
| Data Axle sample (only if the bake-off shows gaps) | $0–$150 |
| **Legal consult** (data licensing, CAN-SPAM/TCPA, state privacy/data-broker) | **$500–$2,500**: the most valuable spend |
| Domain + transactional email | ~$20 |
| **Total cash to a working StarCima MVP** | **≈ $700–$3,000**, most of it legal |

**I will ask for approval before any paid signup.**

---

## 12. Estimated monthly operating costs

**Stage A: StarCima only** (~3,000 businesses scanned/mo, ~300 qualified, ~150 enriched)

| Item | $/mo |
|---|---|
| Vercel Pro (1 seat) | 20 |
| Supabase Pro | 25 |
| Worker host | 15–40 |
| Claude API (batch + caching) | 10–30 |
| PSI/CrUX/RDAP/Overture/NPI | 0 |
| Hunter (annual Starter) + ZeroBounce | 35–75 |
| Email sending / misc | 0–20 |
| **Total** | **≈ $105–$210** |

**Stage B: 50 SaaS customers** (~150k businesses scanned/mo)

| Item | $/mo |
|---|---|
| Hosting (Vercel, Supabase with larger compute, 2–3 workers) | 250–600 |
| Claude API | 200–600 |
| Licensed data (Data Axle etc., if needed) | 0–1,500 |
| Email verification (pass-through or bundled) | 100–400 |
| Stripe fees (~3% of revenue) | variable |
| Support tooling, Sentry, backups | 50–150 |
| **Total** | **≈ $600–$3,250**, against ~$7.5k–$15k MRR at the pricing below → **healthy 75–90% gross margin** |

---

## 13. Competitor analysis

| Segment | Players | Price | Strength | Weakness / our opening |
|---|---|---|---|---|
| Agency "no-website" finders | Get Map Leads, BirdSift, LeadWebia, TheWebLead, WebbedLeads, Apify actors ([GetApp](https://www.indiehackers.com/product/get-map-leads/), [BirdSift](https://www.goodfirms.co/software/birdsift), [Capterra](https://www.capterra.com/p/10044528/LeadWebia/), [Apify](https://apify.com/seibs.co/local-leads-without-websites?fpr=ewv9tm)) | ~$25–$100/mo | Cheap, simple, audit PDFs | Mostly Google Maps scraping (license risk), single-vertical, shallow scoring, little evidence/compliance |
| B2B data platforms | Apollo, ZoomInfo, Seamless.ai | $49–$119/seat → $40k+/yr | Huge people databases | Weak on local SMBs without LinkedIn presence; no website-quality intelligence |
| Enrichment orchestration | Clay | $185–$495+/mo | Extremely flexible | Requires expertise; no local discovery or audits built in |
| Agency all-in-ones | GoHighLevel, Semrush/BrightLocal local tools | $97–$497/mo | CRM + marketing suite | Prospecting is secondary; not configurable ICP intelligence |

**Positioning:** *evidence-backed, configurable opportunity intelligence for companies that sell to local and small businesses.* The differentiators are:
- licensed data;
- an explainable score separating facts from AI;
- vertical templates;
- compliance built in (suppression, approval, attribution).

The beachhead customers are **web, SEO, and marketing agencies**, the segment you know firsthand.

---

## 14. SaaS monetization

| Tier | Price (proposal) | Includes |
|---|---|---|
| **Starter** | $79–$99/mo | 1 user, 2 profiles, 1,000 analyzed businesses/mo, 100 enrichments, AI drafts |
| **Professional** | $199–$249/mo | 3 users, 10 profiles, 5,000 analyzed, 500 enrichments, scheduled discovery, PDF audit reports |
| **Agency** | $449–$599/mo | 10 users, white-label reports/portal, client sub-accounts, 20,000 analyzed, API/webhooks |
| **Enterprise** | Custom | SSO, custom modules/data sources, SLA, BYO data licenses |

**Additional revenue:**
- metered overages (analyses, enrichments, verified emails);
- **branded website-audit PDF reports** as a lead magnet;
- template marketplace (vertical profiles);
- done-for-you setup fee ($500–$1,500);
- StarCima's own services upsold from the platform.

**Annual billing at 2 months free.** Run a 14-day trial with a capped credit allowance, because the free tier is where API abuse happens.

---

## 15. Development roadmap (refined)

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **1. Feasibility & bake-off** (now, ~2 wks) | Data-source comparison in one metro; audit pipeline prototype on ~200 sites; legal consult | Discovery strategy chosen with measured coverage; legal go/no-go on sources |
| **2. Foundation** (~3–4 wks) | Repo, Supabase schema + RLS + isolation tests, auth/orgs, profile/module/signal/scoring core, job queue, worker skeleton | One profile runs end-to-end on fixtures; isolation tests green |
| **3. StarCima configuration** (~1–2 wks) | Template `web-presence-v1`, services catalog, weights, dashboard layout | StarCima profile configurable in UI with no code changes |
| **4. Discovery + contacts** (~2–3 wks) | Overture/FSQ/NPI/SOS adapters, dedupe, site contact extraction, Hunter + ZeroBounce adapters | ≥ X% of target categories found in pilot area; contacts carry source/confidence |
| **5. Website intelligence + qualification** (~2–3 wks) | Lighthouse/PSI/CrUX, tech, SEO, visual AI, explainable scores | Scores manually spot-checked on 50 leads: ≥ 85% "agree" |
| **6. AI assistant + approved outreach** (~2–3 wks) | Summaries, drafts, call prep, PDF reports, approval queue, suppression, CAN-SPAM footer | StarCima sends its first approved campaign |
| **7. Scheduling & monitoring** (~1–2 wks) | Recurring discovery, change detection ("site went down," "new business"), digests | Weekly new-lead digest running unattended |
| **8. Commercialization** (~3–4 wks) | Stripe tiers, usage metering, onboarding, templates, agency sub-accounts, ToS/DPA/privacy policy | First 3–5 paying design-partner agencies |

The durations are rough and assume focused part-time development with Claude Code. Phases 4 and 5 can overlap.

---

## Legal & compliance register (⚖ needs professional review)

1. **Google Maps Platform terms:** whether any Places-derived prospect workflow is permitted; storage limits (`place_id` indefinitely, lat/lng 30 days); attribution.
2. **Data licensing for resale:** Overture/FSQ attribution duties; Data Axle/Apollo redistribution inside a SaaS. The BYO-key model is preferred.
3. **CAN-SPAM:** applies to B2B commercial email. It requires accurate headers, non-deceptive subjects, a physical postal address, a working opt-out honored within 10 business days, and responsibility for vendors who send on your behalf. Penalties exceed $50,000 per violating email. → Built-in footer, a global plus per-tenant suppression list, and one-click unsubscribe.
4. **TCPA and state telemarketing laws** (e.g. Florida's FTSA, Oklahoma): many small businesses list owners' **cell phones**. Autodialed or prerecorded calls and texts require consent. → **No automated calling or SMS in the MVP.** Manual click-to-call only, with DNC scrubbing to be evaluated.
5. **State privacy and data-broker laws:** CCPA/CPRA now covers B2B contact data. California's Delete Act/DROP, Vermont, Texas, and Oregon have data-broker registration laws. Selling a database of named individuals may trigger registration. → Store people only when tied to a business role, honor deletion requests, and get a counsel opinion on broker status.
6. **GDPR/UK GDPR** if non-US customers or prospects are allowed. → US-only at launch.
7. **HIPAA:** not applicable as designed, because no PHI is collected. Avoid storing review text and anything about patients.
8. **Platform ToS:** our own SaaS terms must make customers responsible for lawful outreach and prohibit misuse. We also need a DPA and privacy policy.

---

## Recommendation: first implementation milestone

**Milestone 1, "Prove the data": a two-week bake-off and legal consult, before any platform build.**

1. **Pick one metro** (StarCima's) and **three categories**: psychologists/counselors, dentists, and roofing/contractors.
2. **Build a throwaway TypeScript script set** (in a new repo) that:
   - pulls candidates from **Overture Places, FSQ OS Places, and the NPI registry** (plus Google Places for comparison only, within free caps and storing only `place_id`, *if you approve*);
   - deduplicates them and measures **coverage, website-field accuracy, and the share of businesses that are active**;
   - runs the **website-presence + Lighthouse + SEO-basics** checks on about 200 businesses and produces a draft score with explanations.
3. **You hand-review 50 results** and judge each one: would you actually pitch this business?
4. **In parallel**, a one-hour **attorney consult** on items 1–5 of the legal register.
5. **Output:** a short report with coverage numbers, cost per qualified lead, score precision, and a go/no-go for each data source. That locks the discovery strategy for Phase 2.

**What I need from you to start:**
- StarCima's target metro or ZIP and radius.
- Approval to use a free Google Maps Platform key for comparison only: yes or no.
- A decision to create a **new repository** for the product. This study is temporarily stored in the `photo-converter` repo because that's the only repository attached to this session.
- An Anthropic API key, when we reach the AI steps. Estimated spend under $20 for Milestone 1.

---

### Sources

- Google Maps Platform pricing: https://developers.google.com/maps/billing-and-pricing/pricing · March 2025 billing changes: https://developers.google.com/maps/billing-and-pricing/march-2025
- Places API policies (caching/attribution): https://developers.google.com/maps/documentation/places/web-service/policies?authuser=6 · Service Specific Terms: https://cloud.google.com/archive/maps-platform/terms/maps-service-terms-20250501 · Third-party analysis of scraping terms: https://thunderbit.com/blog/is-scraping-google-maps-legal
- PageSpeed Insights API limits (third-party): https://unlighthouse.dev/learn-lighthouse/pagespeed-insights-api/rate-limits
- Apollo pricing: https://fullenrich.com/content/apollo-pricing · https://docs.apollo.io/docs/api-pricing
- Hunter pricing: https://hunter.io/pricing · https://www.saleshandy.com/blog/hunter-io-pricing/
- ZeroBounce pricing: https://www.zerobounce.net/email-validation-pricing · https://www.activepieces.com/blog/zerobounce-pricing-2026-plans-credits-costs
- Supabase pricing: https://supabase.com/pricing · Vercel Pro: https://vercel.com/docs/plans/pro-plan
- Data Axle pricing (third-party): https://fullenrich.com/content/data-axle-pricing · Data Axle APIs: https://data-axle.com/our-data/apis
- Foursquare pricing: https://location.foursquare.com/?p=19 · OpenCorporates: https://opencorporates.com/pricing/
- Clay / ZoomInfo / Seamless (third-party benchmarks): https://www.spendhound.com/marketplace/clay-pricing · https://pipeline.zoominfo.com/sales/seamless-ai-pricing
- Competitors: https://www.indiehackers.com/product/get-map-leads/ · https://www.goodfirms.co/software/birdsift · https://www.capterra.com/p/10044528/LeadWebia/ · https://apify.com/seibs.co/local-leads-without-websites?fpr=ewv9tm · https://ecommerceparadise.com/7-best-lead-generation-tools-for-web-design-agencies-in-2026/
- Claude API model pricing: Anthropic model table (Haiku 5.5 $0.10/$0.50, Sonnet 5.5 $2/$10, Opus 5.5 $4/$20 per M tokens; Batch API 50% discount)
- Items stated from general knowledge and **not re-verified in this session** (verify in Milestone 1): Overture and FSQ OS licenses, NPPES API terms, CAN-SPAM penalty amount, state data-broker laws.
