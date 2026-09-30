import httpx
import pytest

from openpali.discovery.clearance import (
    Archive, approved_pdf_url, choose_samples, fetch_inventory, pdf_profile, summarize,
)


def test_inventory_requires_every_frozen_source_id(tmp_path):
    def reply(request):
        if request.url.params.get("returnIdsOnly"):
            return httpx.Response(200, json={"objectIdFieldName": "OBJECTID", "objectIds": [1, 2]})
        return httpx.Response(200, json={"features": [{"attributes": {"OBJECTID": 1}}]})

    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        with pytest.raises(ValueError, match="omitted"):
            fetch_inventory(Archive(tmp_path, client))
    assert len(list((tmp_path / "objects").iterdir())) == 2


def test_arcgis_error_is_not_an_empty_dataset(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"error": {"code": 400}})
    )) as client:
        with pytest.raises(ValueError, match="invalid ArcGIS"):
            fetch_inventory(Archive(tmp_path, client))


def test_samples_cover_status_groups_and_deduplicate_documents():
    prefix = "https://pwgis.blob.core.windows.net/epd/Debris_Removal/"
    rows = [{"APN": str(i), "FSO_URL": prefix + str(i) + ".pdf", "ROE_STATUS": "government"}
            for i in range(10)]
    rows += [{"APN": "p", "FSO_URL": prefix + "private.pdf", "ROE_STATUS": "private"}]
    rows += [rows[0]]
    selected = choose_samples(rows, 4)
    assert {r["ROE_STATUS"] for r in selected} == {"private", "government"}
    assert len({r["FSO_URL"] for r in selected}) == 4
    assert choose_samples(rows, 4) == selected
    assert choose_samples(rows, 0) == []


def test_source_urls_cannot_redirect_collection_to_arbitrary_hosts():
    assert approved_pdf_url("https://pwgis.blob.core.windows.net/epd/Debris_Removal/a.pdf")
    assert not approved_pdf_url("https://pwgis.blob.core.windows.net.evil.test/epd/Debris_Removal/a.pdf")
    assert not approved_pdf_url("http://127.0.0.1/a.pdf")
    assert not approved_pdf_url("https://pwgis.blob.core.windows.net/another/a.pdf")


def test_nonempty_placeholder_is_preserved_not_promoted_to_completion():
    report = summarize([{"APN": "1", "ROE_STATUS": "private", "FSO_URL": None,
                         "DEBRIS_REMOVAL_EPICLA": "No Data", "BUILD_PLAN_APPROVED": None}])
    assert report["debris_removal_epicla_domain"] == {"No Data": 1}
    assert report["populated_url_rows"] == 0
    assert report["by_roe_status"]["private"]["parcels"] == 1


def test_html_block_page_cannot_be_counted_as_a_pdf(tmp_path):
    with pytest.raises(ValueError, match="not a PDF"):
        pdf_profile(b"<html>unavailable</html>", tmp_path / "unused")
