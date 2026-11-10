"""Conservative primary-home milestone projection and observed timing summaries."""
from datetime import datetime,timezone,date
import math
from statistics import median

PRIMARY_USES={'Dwelling - Single Family','Duplex','Condo-Single Family'}


def event_date(value,observed_at):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):return None
    try: occurred=datetime.fromtimestamp(value/1000,tz=timezone.utc).date()
    except (ValueError,OverflowError,OSError):return None
    cutoff=datetime.fromisoformat(observed_at.replace('Z','+00:00')).date()
    return occurred if date(2025,1,7)<=occurred<=cutoff else None


def primary_home(row):
    return row.get('PERMIT_TYPE')=='Bldg-New' and row.get('PALISADES_WF_REBUILD')=='Rebuild' and row.get('ZONE_USE_DESC') in PRIMARY_USES


def permit_stage(row,observed_at):
    if not primary_home(row):return 'unknown'
    dates={k:event_date(row.get(k),observed_at) for k in ('SUBMIT_DATE','PC_APPROVED_DATE','ISSUE_DATE','COFO_DATE')}
    ordered=[d for d in dates.values() if d]
    if ordered!=sorted(ordered):return 'unknown'
    for key,stage in [('COFO_DATE','occupancy'),('ISSUE_DATE','permit'),('PC_APPROVED_DATE','design'),('SUBMIT_DATE','application')]:
        if dates[key]:return stage
    return 'unknown'


def timing_summary(rows,observed_at):
    durations=[];pending=0
    for row in rows:
        if not primary_home(row):continue
        start=event_date(row.get('SUBMIT_DATE'),observed_at);end=event_date(row.get('ISSUE_DATE'),observed_at)
        if start and end and end>=start:durations.append((end-start).days)
        elif start and not end:pending+=1
    return dict(issued_with_valid_dates=len(durations),not_yet_issued=pending,
                median_observed_days_to_issue=median(durations) if durations else None,
                population='Explicit primary residential Bldg-New fire rebuild permits',
                interpretation='Descriptive completed durations only; excludes pending durations and is not a forecast. Application elapsed time includes applicant, agency and other delays.')
