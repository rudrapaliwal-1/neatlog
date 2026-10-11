from backend.policy import patch_hash


def test_requires_operator_and_current_hash(setup, finding, operator_headers):
    client, _, _, _ = setup
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    url = f"/api/jobs/{job_id}/approval"
    payload = {"patch_hash": patch["patch_hash"], "decision": "APPROVE"}
    assert client.post(url, headers={"X-Operator-Token": ""}, json=payload).status_code == 401
    assert client.post(url, headers=operator_headers,
                       json={**payload, "patch_hash": patch_hash("stale")}).status_code == 409
    assert client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers).status_code == 409
    assert client.post(url, headers=operator_headers, json=payload).status_code == 200
    assert client.post(url, headers=operator_headers, json=payload).status_code == 409


def test_rejection_is_terminal(setup, finding, operator_headers):
    client, _, _, _ = setup
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    response = client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                           json={"patch_hash": patch["patch_hash"], "decision": "REJECT"})
    assert response.status_code == 200
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "USER_REJECTED"
    assert client.post(f"/api/jobs/{job_id}/verify", headers=operator_headers).status_code == 409


def test_database_patch_tampering_is_detected(setup, finding, operator_headers):
    client, _, _, settings = setup
    job_id = client.post("/api/findings", json=finding).json()["job_id"]
    patch = client.get(f"/api/jobs/{job_id}/patch").json()
    with client.app.state.workflow.db.transaction() as db:
        db.execute("UPDATE patch_proposals SET patch_text = ? WHERE id = ?", ("tampered", patch["id"]))
    response = client.post(f"/api/jobs/{job_id}/approval", headers=operator_headers,
                           json={"patch_hash": patch["patch_hash"], "decision": "APPROVE"})
    assert response.status_code == 409
