import copy

import pytest


@pytest.fixture
def valid_report(analysis_payload):
    return {"analysis": copy.deepcopy(analysis_payload)}


def test_create_report_returns_submission_metadata(client, valid_report):
    response = client.post("/api/reports", json=valid_report)

    assert response.status_code == 200
    result = response.json()
    assert result["id"]
    assert result["status"] == "Submitted"
    assert result["created_at"]


@pytest.mark.parametrize(
    "field",
    [
        "issue_type",
        "severity",
        "title",
        "description",
        "evidence",
        "department",
        "confidence",
        "limitations",
    ],
)
def test_create_report_rejects_missing_analysis_fields(client, valid_report, field):
    del valid_report["analysis"][field]

    response = client.post("/api/reports", json=valid_report)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issue_type", ""),
        ("issue_type", "Flooding"),
        ("severity", ""),
        ("severity", "Critical"),
        ("title", ""),
        ("description", ""),
        ("department", ""),
    ],
)
def test_create_report_rejects_empty_or_unsupported_fields(
    client, valid_report, field, value
):
    valid_report["analysis"][field] = value

    response = client.post("/api/reports", json=valid_report)

    assert response.status_code == 422


@pytest.mark.parametrize("confidence", [-0.01, 1.01, True, "0.5"])
def test_create_report_rejects_invalid_confidence(client, valid_report, confidence):
    valid_report["analysis"]["confidence"] = confidence

    response = client.post("/api/reports", json=valid_report)

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["evidence", "limitations"])
def test_create_report_rejects_non_list_evidence_and_limitations(
    client, valid_report, field
):
    valid_report["analysis"][field] = "not a list"

    response = client.post("/api/reports", json=valid_report)

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["evidence", "limitations"])
def test_create_report_rejects_too_many_evidence_and_limitations(
    client, valid_report, field
):
    valid_report["analysis"][field] = [f"item {index}" for index in range(9)]

    response = client.post("/api/reports", json=valid_report)

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["evidence", "limitations"])
def test_create_report_rejects_non_string_evidence_and_limitations(
    client, valid_report, field
):
    valid_report["analysis"][field] = ["valid text", 42]

    response = client.post("/api/reports", json=valid_report)

    assert response.status_code == 422


def test_create_report_rejects_missing_or_empty_analysis(client):
    missing = client.post("/api/reports", json={})
    empty = client.post("/api/reports", json={"analysis": {}})

    assert missing.status_code == 422
    assert empty.status_code == 422


def test_report_can_be_retrieved_from_database(client, valid_report):
    created = client.post(
        "/api/reports",
        json={
            **valid_report,
            "location": "Test location",
            "description": "Resident description",
            "image_name": "sample.png",
        },
    )
    assert created.status_code == 200

    response = client.get("/api/reports")

    assert response.status_code == 200
    reports = response.json()
    assert len(reports) == 1
    report = reports[0]
    assert report["id"] == created.json()["id"]
    assert report["issue_type"] == valid_report["analysis"]["issue_type"]
    assert report["evidence"] == valid_report["analysis"]["evidence"]
    assert report["limitations"] == valid_report["analysis"]["limitations"]
    assert report["location"] == "Test location"
    assert report["image_name"] == "sample.png"
    assert report["status"] == "Submitted"


@pytest.mark.parametrize("status", ["Submitted", "Under Review", "Resolved"])
def test_report_status_can_be_updated(client, valid_report, status):
    created = client.post("/api/reports", json=valid_report)

    response = client.patch(
        f"/api/reports/{created.json()['id']}",
        json={"status": status},
    )

    assert response.status_code == 200
    assert response.json() == {"id": created.json()["id"], "status": status}
    assert client.get("/api/reports").json()[0]["status"] == status


@pytest.mark.parametrize("status", ["Filed", "", "resolved", "In Progress"])
def test_report_status_rejects_unsupported_values(client, valid_report, status):
    created = client.post("/api/reports", json=valid_report)

    response = client.patch(
        f"/api/reports/{created.json()['id']}",
        json={"status": status},
    )

    assert response.status_code == 422


def test_report_status_update_rejects_missing_report_id(client):
    response = client.patch(
        "/api/reports/NO-SUCH-REPORT",
        json={"status": "Resolved"},
    )

    assert response.status_code == 404


def test_report_status_update_rejects_missing_status(client):
    response = client.patch("/api/reports/NO-SUCH-REPORT", json={})

    assert response.status_code == 422
