import pytest

from openpali.discovery.parcel_universe import FIELDS, fetch


class Source:
    def __init__(self, rows, *, truncated=False):
        self.rows, self.truncated = rows, truncated

    def json(self, url, parameters, *, post=False):
        if not url.endswith('/query'):
            return {'fields': [{'name': name} for name in FIELDS]}
        if parameters.get('returnIdsOnly'):
            return {'objectIds': [1, 2]}
        return {'features': self.rows, 'exceededTransferLimit': self.truncated}


def row(oid):
    return {'properties': {'OBJECTID': oid}, 'geometry': {'type': 'Polygon', 'coordinates': []}}


@pytest.mark.parametrize('source', [Source([row(1)]), Source([row(1), row(1)]),
                                   Source([row(1), row(2)], truncated=True)])
def test_incomplete_or_duplicated_universe_cannot_succeed(source):
    with pytest.raises(ValueError, match='incomplete or substituted'):
        fetch(source)
