from backend.main import create_app


def test_health_ingestion_listing_and_docs(setup, finding):
    client, agent, _, _ = setup
    assert client.get("/health").json() == {"status": "ok", "service": "sentinel-x-backend"}
    assert client.get("/docs").status_code == 200
    response = client.post("/api/findings", json=finding)
    assert response.status_code == 202
    assert response.json()["status"] == "FINDING_RECEIVED"
    job_id = response.json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "AWAITING_APPROVAL"
    assert client.get("/api/jobs").json()[0]["id"] == job_id
    assert client.get(f"/api/jobs/{job_id}/patch").json()["attempt"] == 0
    assert agent.calls[0][1] == {"app/access.py": "return document\n"}


def test_invalid_target_path_and_missing_job(setup, finding):
    client, _, _, _ = setup
    bad = {**finding, "target_app_id": "other-app"}
    assert client.post("/api/findings", json=bad).status_code == 422
    bad = {**finding, "finding": {**finding["finding"], "file_path": "tests/test.py"}}
    assert client.post("/api/findings", json=bad).status_code == 422
    assert client.get("/api/jobs/missing").status_code == 404
    assert client.get("/api/jobs/missing/evidence").status_code == 404


def test_verification_persistence_and_evidence(setup, finding, operator_headers):
    client, _, verifier, settings = setup
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    approval = client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert approval.status_code == 200
    result = client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers)
    assert result.status_code == 200
    assert result.json()["status"] == "VERIFIED"
    assert result.json()["tests_total"] == 2
    assert len(verifier.calls) == 1
    assert client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers).status_code == 409
    evidence = client.get(f"/api/jobs/{job_id}/evidence").json()
    assert evidence["conclusion"] == "VERIFIED"
    assert evidence["verification_runs"][0]["result"]["tests_passed"] == 2
    assert evidence["approvals"][0]["patch_hash"] == patch["patch_hash"]
    assert len(client.get(f"/api/jobs/{job_id}/events").json()) >= 7
    assert create_app(settings).state.workflow.get_job(job_id)["status"] == "VERIFIED"
