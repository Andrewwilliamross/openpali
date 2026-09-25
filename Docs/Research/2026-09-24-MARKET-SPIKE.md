# Market data research spike: access, samples and modeling contract

September 24, 2026 local / September 25 UTC. This spike supersedes the earlier
“no free feed verified” stopping point. Public records and public listing pages
can already contribute data. A reliable complete longitudinal feed still needs
an acquisition worker, coverage measurement and source-specific publication rules.

## Verified sample routes

### Redfin: live listing and events retrieved

[758 Radcliffe Avenue](https://www.redfin.com/CA/Pacific-Palisades/758-Radcliffe-Ave-90272/home/6841381)
opened in normal Chrome. Direct HTTP had returned 429; no repeated HTTP attempts
or challenge bypass was used. The live page identifies APN **4412006025**, a
**7,508 sq ft vacant lot**, asking **$2,095,000**. Its loaded history contains:

| Date | Event | Amount shown |
|---|---|---:|
| September 9, 2026 | Listed | $2,095,000 |
| September 14, 2026 | Contingent | None |
| September 17, 2026 | Pending | None |
| January 31, 1991 | Public-record sale | $950,000 |
| October 23, 1989 | Public-record sale | $590,000 |

The search service's indexed page still described the property as for sale.
The live browser showed pending. Preserve both retrieval times and source
vintages; do not make search snippets the source of current status. A pending
asking price is not the accepted offer or closing price. This sample is an
acquisition proof, not an appraisal.

### Zillow: live listing retrieved; history access differs

[17713 Posetano Road](https://www.zillow.com/homedetails/17713-Posetano-Rd-Pacific-Palisades-CA-90272/95670767_zpid/)
opened in normal Chrome despite direct HTTP returning 403. The live listing
showed **$3,995,000**, 3 beds, 3 baths, 2,622 sq ft of house and 3,685 sq ft of lot.
After rendering, its price/tax-history sections said unavailable. An indexed
primary-page copy supplied asking-price steps of $4,995,000 on June 22,
$4,495,000 on August 20 and $3,995,000 on September 8, 2026, and a March 1, 2024
sale of $3,670,500. These history values have weaker freshness/access evidence
than the live listing and need independent corroboration.

The primary Assessor API for APN **4416020028** returned 14 ownership records
and 61 assessment rows, including the March 1, 2024 recording. Its DTT-derived
amount is **$3,670,500**, agreeing with the indexed listing history; its category
describes a sale for consideration. That corroborates this sample, without
treating assessed value or recording date as an interchangeable sale price/closing date.
The house's current listing is not by itself proof that it escaped all fire damage.

### Independent aggregated benchmark

[Uplifters' data page](https://upliftersfoundation.org/data.php) was retrievable
as HTML and contains neighborhood/month tables through July 2026. Its scope is
flat lots below 10,000 sq ft without notable views. It describes a combination
of official records and licensed private transaction data. Use it to check
aggregate trends within that definition, not as a complete parcel transaction
feed or permission to redistribute its underlying private data.

### Free current property-record baseline

The County polygon service provides 2026 assessments and the Assessor public
JSON API provides transfer and assessment histories. The previously tested
PAIS **sales layer** is stale to 2024; that is a limitation of that endpoint,
not of every County route. Current assessor acquisition is implemented in
`pipeline/openpali/discovery/assessor.py`; see the linked reports in the
[expansion brief](2026-09-24-DATA-EXPANSION.md).

## Event schema

Store individual facts with `property_id`, `parcel_version_id`, source record/
listing ID, listing episode, event type, effective date/interval, recording date,
first/last observed time, asking or sale amount, currency, status, provenance,
extraction version and match confidence. Keep land area and floor area distinct.

Event types include listed, asking-price changed, contingent, pending, withdrawn,
expired, relisted, closed sale and recorded non-sale transfer. Do not turn a
listing disappearing from one page into a sale. Reconcile MLS identifiers and
recording-document numbers before counting syndications as independent events.
Keep list-price reductions separate from changes in modeled market value.

For transfer records preserve trust/gift/partial-interest/multi-parcel and
verification categories. Exclude or explicitly model non-comparable transfers;
values such as zero or nine dollars in the sampled County history do not become
market-price labels. Missing title-owner names remain a separate acquisition need.

## Collector work, in order

1. Start from the expanded parcel universe and primary-record histories.
   Resolve parcel splits, units, address aliases and multiple buildings.
2. Discover listing URLs from public search/broker pages and source links.
   Record discovery coverage and failures; don't assume search finds every listing.
3. Build a deterministic normal-browser recipe for each site's visible listing
   and event sections. Validate the address/APN and listing ID. Snapshot date,
   status and events; separate missing sections from a valid empty history.
4. Refresh active/pending listings more often than long-closed properties.
   Respect host feedback; access failures create an alternative-source work item.
   Browser rendering and syndication can disagree, so retain source precedence
   and conflict records rather than overwriting history silently.
5. Reconcile closings against primary recording evidence, including lag.
   Add broker/owner supplied records where public discovery leaves gaps.
6. Evaluate a structured MLS/vendor route against the measured gap: extra
   transactions, lag, historical depth, fields, permitted uses and cost. Purchasing
   a feed should have measurable benefit, not be a prerequisite to investigation.

The product needs asking-price history, comparable closing evidence, turnover,
time on market, lot/building characteristics and neighborhood recovery exposure.
Listing photographs are potentially useful visual evidence only after dating and
distinguishing existing conditions, pre-fire photos and architectural renderings.
The listing publication date does not establish when each photograph was taken.

## Insurance and transaction context

The [California Department of Insurance](https://www.insurance.ca.gov/01-consumers/200-wrr/DataAnalysisOnWildfiresAndInsurance.cfm)
publishes insurance-market data at specified aggregate geographies. Integrate
that context at its actual unit. Owner-consented quotes, renewals, payouts and
coverage gaps would provide a different, private evidence stream. A website's
mortgage calculator insurance estimate is not a property's quoted premium.

Deed documents can clarify transfer parties and instrument type; historical
permit files and archived assessments can clarify renovations; tax-bill/payment
records are distinct from assessed values. Acquire each with its own field
definitions and dates rather than labeling them collectively “financial data.”

## Modeling deliverable

Produce separately evaluated models for vacant land, standing homes and rebuilt
homes, with shared features only where justified. Features include usable area,
slope/view, access, project entitlements, utility evidence, broader market date
and neighborhood exposure to vacancies/construction. Repeat sales and matched
comparables provide baselines. Spatially and temporally held-out error,
calibration and data coverage determine whether the model is useful.

For surrounding vacancies, estimate a time-specific association conditional on
property and market characteristics. A causal value loss requires additional
identification work; desirability, destruction and rebuild speed are not randomly
assigned. Display uncertainty and comparable evidence. No dollar estimate or
neighborhood vacancy discount has been validated by this spike.
