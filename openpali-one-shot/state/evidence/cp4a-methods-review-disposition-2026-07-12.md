# Methods review of the ML protocol: findings + dispositions

Two independent read-only reviews (openpali-methods-reviewer) of
dataset/experiments/registry/serving/fixture at commit `d85793e`. Convergent
findings dispositioned below; repairs land in the commit following this file.

## Blockers (both reviews) — FIXED

1. **Interleaved "rolling-origin" folds.** `fold_{index % 3}` over
   origin-sorted rows was a stratified split: fold_0 evaluation rows had
   fit-set temporal neighbors on both sides — optimistic for a monotone
   calendar covariate. REPAIR: `rolling-origin-v2` — folds are contiguous
   chronological blocks; dev evaluation is FORWARD (fit fold_0+fold_1,
   evaluate fold_2); split policy folded into the dataset identity hash so
   changed split semantics can never silently overwrite parquet bytes.
   Unit test: `test_split_blocks_are_contiguous_in_time`.
2. **Promotion gates unenforced.** `evaluate_gates` never required
   final-holdout evaluation, compared against "latest KM of any split",
   hardcoded `dataset_contracts` to PASS, passed calibration OPEN on missing
   values, had no cohort-regression check, and accepted any reviewer string.
   REPAIR: new predeclared gate set — `final_holdout_only` (challenger AND
   the KM comparator matched on final_holdout), Brier, calibration
   FAIL-CLOSED on missing, `no_cohort_regression` (persisted per-cohort
   IPCW Brier, n>=30, >20% relative regression fails, missing brier on a
   qualifying cohort fails closed), `dataset_contracts` actually reads
   `DatasetVersion.leakage_audit` + `sufficiency.gate.passed`, reviewer
   validated against reserved identities. The drill now PROVES the negative
   case: promoting a fold-evaluated model is attempted and must be refused,
   then a single final-holdout evaluation is promoted.

## Should-fixes — FIXED

3. IPCW event weight now uses the left limit G(T_i - 0.5) (integer-day
   durations make this exact); G-floor hits are counted and persisted as
   `ipcw_g_floor_hits_180` instead of a silent cap.
   Unit tests: `test_ipcw_*` (no-censoring identity, survivor scoring,
   denominator semantics, left-limit tie behavior).
4. `NaiveBaseline.survival` was horizon-blind (90-day metric silently reused
   the 180-day rate). Now fit per horizon; unknown horizons raise.
   Unit test: `test_naive_baseline_is_horizon_specific`.
5. Calibration bins enforce minimum mass (>=15 definitive rows per bin;
   tail remainders dropped). Unit test included.
6. Serving gating decoupled from the parcel-history gate when the champion
   consumes only origin-derived covariates (`ORIGIN_DERIVED_FEATURES`),
   preserving "a failed evaluation never blocks a compatible reviewed
   champion". CRITICAL companion fix surfaced by this change: champion
   DOMAIN compatibility — a fixture-trained champion is structurally barred
   from serving civic snapshots (and vice versa) via snapshot input-run
   lineage; previously only the (unrelated) gate check accidentally
   prevented fixture->civic champion leakage.
7. Extrapolation disclosure: the champion's training covariate range is
   persisted in `ModelVersion.signature`; served rows outside it carry
   `basis.extrapolated_features` + an explicit caution note.
8. Cox PH diagnostic: Schoenfeld-residual test p-values + log-hazard-ratio
   coefficients (labeled association, NOT causal) logged as
   `cox-diagnostics.json` for the human reviewer (gate 6).
9. Fixture v3: submissions continue to near the final acquisition so the
   final holdout carries real evaluation mass (39 rows / 17 definitive in
   simulation) instead of 9.

## Accepted as-is (with reasons)

- IPCW denominator = full n (censored-before-horizon contribute 0): standard
  Graf formulation — confirmed by both reviews.
- Naive baseline complete-case bias: intended weak strawman, scored under
  the same IPCW metric; kept (now horizon-honest).
- `COX_PENALIZER=0.1` on an unstandardized covariate: verified against
  installed lifelines 0.30.3 source — penalization is applied to
  STANDARDIZED coefficients internally; not a bug (review 2 #10).
- Fit-G-on-evaluation-rows: classical Graf/pec convention; kept, now with
  the floor-hit diagnostic making tail instability visible.
- Gate measures parcel-feature history while the current challenger uses
  only calendar covariates: retained deliberately — the gate is the
  precommitted condition for EXPANDING to parcel covariates, and it is what
  keeps the single-burst representative ledger honestly insufficient. The
  serving-side coupling (the actual hazard) was removed in (6).

## Deferred (recorded, not silently dropped)

- Multi-seed fixture margin study (review 1 Q7): the fixture is executable
  wiring proof, not skill evidence; margins on the PH-clean generator are
  decisively positive in simulation (fold: 0.0278 vs 0.0507; holdout:
  0.0108 vs 0.0299). A seed sweep is cheap follow-on work under CP5 gates.
- Calibration-scope note on the model card (review 2 #8): the
  definitive-rows-only calibration population vs the served (censored)
  population — documented here; card wording lands with CP4C model-status UI.
