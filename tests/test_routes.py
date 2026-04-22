from __future__ import annotations


def test_root_serves_landing_page(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200
