"""The frozen MVP metric catalog.

Every definition fixes unit, population, numerator, denominator, jurisdiction,
window, inclusion, missingness, censoring, suppression, and validation BEFORE
values are observed. Definition changes bump ``version`` and create explicit
comparability breaks. No observational trend is ever labeled causal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

CATALOG_VERSION = "metrics-v1"

#: Minimum subjects for publishing a censoring-aware time estimate.
KM_MIN_SAMPLE = 20

#: Rolling window for backlog/inflow/outflow throughput.
FLOW_WINDOW_DAYS = 28


@dataclass(frozen=True, slots=True)
class MetricSpec:
    metric_id: str
    version: str
    title: str
    unit: str
    population: str
    numerator: str
    denominator: str | None
    jurisdiction: str
    window: str | None
    inclusion: str
    missingness: str
    censoring: str
    suppression: str
    validation: str

    def row(self) -> dict:
        payload = asdict(self)
        payload["inclusion_rules"] = payload.pop("inclusion")
        payload["missingness_rules"] = payload.pop("missingness")
        payload["censoring_rules"] = payload.pop("censoring")
        payload["suppression_rules"] = payload.pop("suppression")
        return payload


SPECS: list[MetricSpec] = [
    MetricSpec(
        metric_id="universe_destroyed_parcels",
        version=CATALOG_VERSION,
        title="Destroyed-parcel universe",
        unit="parcels",
        population="County-declared destroyed parcels (DAMAGE='Destroyed (>50%)', FIRE_NAME='Palisades')",
        numerator="parcels present in the snapshot property-state projection",
        denominator=None,
        jurisdiction="all covered",
        window=None,
        inclusion="every parcel in the declared universe; none excluded",
        missingness="parcels dropped for unparseable APN or missing geometry are counted in acquisition health",
        censoring="not applicable",
        suppression="never suppressed",
        validation="must equal the county layer's server-side count captured at acquisition (tolerance 0%)",
    ),
    MetricSpec(
        metric_id="lane_signal_prevalence",
        version=CATALOG_VERSION,
        title="As-of prevalence per recovery lane signal",
        unit="parcels",
        population="destroyed-parcel universe",
        numerator="parcels whose lane projection carries the given signal at the snapshot cutoff",
        denominator="universe_destroyed_parcels",
        jurisdiction="cohort dimension (all, LA, COUNTY, MALIBU)",
        window="as-of cutoff",
        inclusion="all parcels; signals are the lanes-v1 projection outputs",
        missingness="'no_public_evidence' is absence from covered sources, never resident inactivity",
        censoring="not applicable (prevalence)",
        suppression="never suppressed",
        validation="signals sum to the universe within each lane",
    ),
    MetricSpec(
        metric_id="milestone_prevalence",
        version=CATALOG_VERSION,
        title="As-of evidenced milestone prevalence",
        unit="parcels",
        population="destroyed-parcel universe",
        numerator="parcels with the evidenced milestone fact true at cutoff",
        denominator="universe_destroyed_parcels",
        jurisdiction="cohort dimension",
        window="as-of cutoff",
        inclusion="milestones are evidence-backed facts (lanes-v1); scheduled/attempted activity never counts",
        missingness="undated milestone assertions count toward prevalence but are excluded from time series",
        censoring="not applicable (prevalence)",
        suppression="never suppressed",
        validation="qualifying permit issuance reconciles against the independent Socrata portal (see reconciliation)",
    ),
    MetricSpec(
        metric_id="weekly_transition_incidence",
        version=CATALOG_VERSION,
        title="Weekly qualifying application submissions and issuances",
        unit="permit applications",
        population="qualifying rebuild applications (Bldg-New AND PALISADES_WF_REBUILD='Rebuild')",
        numerator="events whose source-asserted exact occurrence date falls in the ISO week",
        denominator=None,
        jurisdiction="LA (LADBS)",
        window="ISO weeks since 2025-01-06",
        inclusion="exact-dated observations only",
        missingness="undated events are reported in the missingness metric and excluded here — disclosed, never imputed",
        censoring="the trailing partial week is marked incomplete",
        suppression="never suppressed",
        validation="week totals sum to the exact-dated event totals",
    ),
    MetricSpec(
        metric_id="time_to_issuance_km",
        version=CATALOG_VERSION,
        title="Censoring-aware time from qualifying application to issuance",
        unit="days",
        population="qualifying rebuild applications with exact submission dates",
        numerator="Kaplan-Meier median and P(issued within 180 days)",
        denominator=None,
        jurisdiction="LA (LADBS)",
        window="origin = application submission; horizon 180 days",
        inclusion="one risk unit per qualifying application, never property-level aggregation",
        missingness="applications without an exact submission date are excluded and counted",
        censoring="applications without issuance are right-censored at the snapshot cutoff; no competing events are currently distinguishable in the source (predeclared: withdrawal/expiration treated as censoring until a status field exposes them)",
        suppression=f"suppressed below n={KM_MIN_SAMPLE}; 'median not estimable' reported when S(t) stays above 0.5",
        validation="KM estimate cross-checked against the naive empirical fraction issued among applications with >=180 days of follow-up",
    ),
    MetricSpec(
        metric_id="permitting_backlog_flow",
        version=CATALOG_VERSION,
        title="Permitting backlog, inflow, outflow, net flow, throughput",
        unit="permit applications",
        population="qualifying rebuild applications",
        numerator=(
            "backlog: eligible applications without issuance at cutoff; "
            f"inflow: applications submitted in the trailing {FLOW_WINDOW_DAYS} days; "
            f"outflow: first issuances in the trailing {FLOW_WINDOW_DAYS} days; "
            "net = inflow - outflow; throughput = outflow / window days"
        ),
        denominator=None,
        jurisdiction="LA (LADBS)",
        window=f"trailing {FLOW_WINDOW_DAYS} days at cutoff",
        inclusion="exact-dated submissions/issuances for flows; undated included in backlog when unissued",
        missingness="undated events disclosed in the missingness metric",
        censoring="backlog is right-censored by construction and labeled as such",
        suppression="never suppressed",
        validation="a 'bottleneck' claim is this disclosed conjunction, never the largest stage count alone",
    ),
    MetricSpec(
        metric_id="evidence_missingness",
        version=CATALOG_VERSION,
        title="Missingness and join coverage",
        unit="fractions and counts",
        population="all observations and DINS join accounting in the snapshot",
        numerator="unknown/interval occurrence fractions per event type; DINS matched/unmatched/ambiguous counts",
        denominator="event-type totals",
        jurisdiction="all covered",
        window="as-of cutoff",
        inclusion="active observations in the snapshot",
        missingness="this IS the missingness disclosure",
        censoring="interval-censored occurrences counted separately from unknown",
        suppression="never suppressed",
        validation="DINS join counts equal the acquisition-run join accounting",
    ),
]


SPEC_BY_ID = {spec.metric_id: spec for spec in SPECS}
