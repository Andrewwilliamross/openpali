"""Declared lifecycles are the single source of truth for every status string."""
import re
import typing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openpali.api.app import create_app
from openpali.api.routers import evidence
from openpali.domain.lifecycles import (
    ACQUISITION_RUN, ACQUISITION_TASK, CIVIC_SNAPSHOT, JOB_RUN, PUBLICATION,
    RECOVERY_STAGE, IllegalTransition, catalog,
)
from openpali.intelligence.repository import EvidenceRepository
from openpali.intelligence.workspace import TaskUpdate, Workspace
from tests.test_evidence_workspace import fixture_release

PKG = Path(__file__).resolve().parents[1] / 'openpali'
STATUS_LITERAL = re.compile(r'status\s*==?\s*"(\w+)"(?:\s+if\s[^\n]*?\selse\s+"(\w+)")?')


@pytest.mark.parametrize('path,machines', [
    ('ingestion/acquire.py', [ACQUISITION_RUN]),
    ('ingestion/snapshot.py', [CIVIC_SNAPSHOT, ACQUISITION_RUN]),
    ('publication/release.py', [PUBLICATION, CIVIC_SNAPSHOT]),
    ('orchestration/jobs.py', [JOB_RUN]),
    ('orchestration/flows.py', [JOB_RUN, ACQUISITION_RUN]),
])
def test_every_written_status_is_declared(path, machines):
    written = {g for m in STATUS_LITERAL.finditer((PKG / path).read_text()) for g in m.groups() if g}
    declared = set().union(*(m.states for m in machines))
    assert written, f'scanner found no statuses in {path}'
    assert written <= declared, f'{path} writes undeclared states: {written - declared}'


def test_task_update_schema_matches_lifecycle():
    accepted = set(typing.get_args(TaskUpdate.model_fields['status'].annotation))
    assert accepted == ACQUISITION_TASK.states - ACQUISITION_TASK.initial


def test_lifecycles_reject_skips_and_allow_idempotent_retries():
    assert ACQUISITION_TASK.can('queued', 'queued')
    with pytest.raises(IllegalTransition) as exc:
        ACQUISITION_TASK.require('queued', 'needs_review')
    assert exc.value.allowed == ['in_progress']
    with pytest.raises(IllegalTransition):
        PUBLICATION.require('staged', 'superseded')
    assert PUBLICATION.can('superseded', 'published')  # rollback restores LKG
    assert CIVIC_SNAPSHOT.terminal == {'published'}
    assert set(catalog()['lifecycles']) == {'acquisition_task', 'acquisition_run', 'civic_snapshot', 'publication', 'job_run'}


def test_recovery_stage_never_moves_backwards():
    assert RECOVERY_STAGE.advance('permit', 'application') == 'permit'
    assert RECOVERY_STAGE.advance('permit', 'occupancy') == 'occupancy'
    assert RECOVERY_STAGE.order[0] == 'unknown' and RECOVERY_STAGE.order[-1] == 'occupancy'


def test_task_api_enforces_lifecycle(tmp_path, monkeypatch):
    rid = fixture_release(tmp_path); repo = EvidenceRepository(tmp_path); ops = Workspace(tmp_path / 'workspace.sqlite')
    monkeypatch.setattr(evidence, 'repository', lambda: repo); monkeypatch.setattr(evidence, 'workspace', lambda: ops)
    monkeypatch.setenv('OPENPALI_LOCAL_WORKSPACE', '1')
    client = TestClient(create_app()); headers = {'X-OpenPali-Workspace': 'local-draft'}
    url = f'/v1/evidence/releases/{rid}/tasks/task1'
    note = 'Queued from the test suite'

    assert client.get(url + '/history').json()['allowed_next'] == ['in_progress', 'queued']
    assert client.post(url, json=dict(status='queued', note=note), headers=headers).status_code == 201
    retry = client.post(url, json=dict(status='queued', note=note), headers=headers)
    assert retry.status_code == 200 and len(ops.list('task', 'task1')) == 1

    skip = client.post(url, json=dict(status='needs_review', note=note), headers=headers)
    assert skip.status_code == 409
    assert skip.json()['current'] == 'queued' and skip.json()['allowed_next'] == ['in_progress']

    history = client.get(url + '/history').json()
    assert history['status'] == 'queued' and history['allowed_next'] == ['in_progress']
    assert client.get('/v1/evidence/lifecycles').json()['ladders']['recovery_stage']['order'][-1] == 'occupancy'


def test_web_stage_legend_follows_recovery_ladder():
    source = (PKG.parents[1] / 'web/src/lib/api.ts').read_text()
    block = source[source.index('export const stages'):].split('\n', 1)[0]
    assert re.findall(r'(\w+):\{label:', block) == list(RECOVERY_STAGE.order)
