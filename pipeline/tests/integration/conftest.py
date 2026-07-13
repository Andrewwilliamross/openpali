"""Shared integration-suite isolation.

These tests exercise the REAL platform (PostGIS + object store), and some of
them legitimately publish and promote throwaway releases to prove publication
semantics. The shared cluster's CURRENT pointer must come back exactly as
found: the suite proves behavior, it does not get to change what users see.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def restore_current_release_pointer():
    if os.environ.get("OPENPALI_INTEGRATION") != "1":
        yield
        return

    from sqlalchemy import select

    from openpali.storage.db import get_engine, get_session_factory
    from openpali.storage.models import CurrentRelease, Publication

    factory = get_session_factory(get_engine())
    with factory() as session:
        row = session.get(CurrentRelease, 1)
        before = (row.current_release_id, row.lkg_release_id) if row else None
        # the suite's throwaway promotions also flip pre-existing publication
        # rows to "superseded"; capture their statuses so the release history
        # reads exactly as found afterward
        statuses_before = dict(
            session.execute(
                select(Publication.release_id, Publication.status)
            ).all()
        )
    yield
    if before is None:
        return
    with factory() as session:
        row = session.get(CurrentRelease, 1, with_for_update=True)
        row.current_release_id, row.lkg_release_id = before
        for pub in session.execute(
            select(Publication).where(
                Publication.release_id.in_(statuses_before)
            )
        ).scalars():
            if pub.status != statuses_before[pub.release_id]:
                pub.status = statuses_before[pub.release_id]
        # releases the suite itself published stay in ops.publication
        # history (append-only); only pre-existing state is restored
        session.commit()
