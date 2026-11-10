"""Screen transfer records and report valuation support before fitting models."""
from datetime import datetime


def screen_transfer(row):
    reasons=[]
    raw_date=row.get('RecordingDate')
    try: date=datetime.strptime(str(raw_date).strip(),'%m/%d/%Y').date().isoformat()
    except ValueError:
        date=None; reasons.append('invalid_recording_date')
    try: price=float(str(row.get('DTTSalePrice','')).replace(',',''))
    except ValueError: price=None
    if price is None or price <= 1000: reasons.append('missing_or_nominal_price')
    description=str(row.get('DocumentTypeDesc','')).strip()
    if 'Sale for Consideration' not in description: reasons.append('not_identified_as_sale')
    reason=str(row.get('DocumentReasonCodeDesc','')).strip()
    if 'Typical Change in Ownership' not in reason: reasons.append('transfer_requires_review')
    # Missing scope is not evidence of a single parcel/full interest transfer.
    try: parcels=int(row.get('NumberOfParcels',0))
    except (ValueError,TypeError): parcels=0
    if parcels != 1: reasons.append('parcel_scope_unverified_or_multiple')
    return dict(kind='recorded_transfer', date=date, date_kind='recording_date', raw_date=raw_date,
                price=price, price_kind='transfer_tax_derived', document=row.get('DocumentNumber'),
                description=description, screening='candidate' if not reasons else 'review_required',
                reasons=reasons, raw=row)


def market_support(events):
    screened=[e for e in events if e['screening']=='candidate']
    return dict(status='insufficient_evidence', estimated_price=None, vacancy_price_effect=None,
                recorded_transfers=len(events), screened_candidates=len(screened),
                reason='No validated local model or held-out post-fire sales evaluation. Assessed values and asking prices are not closing prices.',
                requirements=['verified arm’s-length closing prices and sale dates',
                              'lot/structure condition at sale', 'time and neighborhood controls',
                              'spatial and temporal holdout evaluation', 'calibrated prediction intervals'])
