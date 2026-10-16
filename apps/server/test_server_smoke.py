import os
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./sigacecyteo_ci_test.db"
os.environ["SIGA_ADMIN_USER"] = "ci-admin"
os.environ["SIGA_ADMIN_PASSWORD"] = "CI-test-password-only-12345"
os.environ["SIGA_SEED_DEMO"] = "true"

import server

def test_server_core_flow():
    with TestClient(server.app) as client:
        assert client.get("/api/health").status_code == 200

        login_admin = client.post("/api/admin/login", json={
            "username": "ci-admin", "password": "CI-test-password-only-12345"
        })
        assert login_admin.status_code == 200, login_admin.text
        admin_headers = {"Authorization": "Bearer " + login_admin.json()["access_token"]}

        student1 = client.post("/api/auth/login", json={
            "matricula": "2026001", "password": "cecyte123", "computer_code": "LAB-01"
        })
        student2 = client.post("/api/auth/login", json={
            "matricula": "2026002", "password": "cecyte123", "computer_code": "LAB-02"
        })
        assert student1.status_code == 200, student1.text
        assert student2.status_code == 200, student2.text
        client1 = {"Authorization": "Bearer " + student1.json()["access_token"]}
        client2 = {"Authorization": "Bearer " + student2.json()["access_token"]}

        heartbeat = client.post("/api/client/heartbeat", headers=client1, json={
            "hostname": "CI-LAB-01", "os_name": "Windows Test", "cpu": 12.0, "memory": 40.0, "disk": 55.0
        })
        assert heartbeat.status_code == 200
        report = client.post("/api/client/incidents", headers=client1, json={
            "category": "Teclado dañado", "description": "Tecla de prueba sin respuesta"
        })
        assert report.status_code == 200
        incident_id = report.json()["incident_id"]

        state = client.get("/api/admin/state", headers=admin_headers)
        assert state.status_code == 200
        body = state.json()
        assert len([s for s in body["sessions"] if not s["ended_at"]]) == 2
        assert any(x["category"] == "Teclado dañado" for x in body["incidents"])
        assert any(x["code"] == "LAB-01" and x["cpu"] == 12.0 for x in body["computers"])

        resolved = client.post(f"/api/admin/incidents/{incident_id}/resolve", headers=admin_headers, json={"note": "Probado"})
        assert resolved.status_code == 200
        for kind in ("csv", "xlsx", "pdf"):
            response = client.get(f"/api/admin/export/{kind}", headers=admin_headers)
            assert response.status_code == 200, (kind, response.text[:300])
            assert len(response.content) > 100

        qr = client.post("/api/admin/qr-tokens", headers=admin_headers, json={"matricula": "2026002"})
        assert qr.status_code == 200 and qr.json()["qr_data_url"].startswith("data:image/png;base64,")

        # Verifica entrega de comandos por WebSocket y confirmación del cliente.
        created = client.post("/api/admin/commands", headers=admin_headers, json={"computer_code": "LAB-01", "command": "lock"})
        assert created.status_code == 200
        with client.websocket_connect("/ws/client?token=" + student1.json()["access_token"]) as ws:
            command = ws.receive_json()
            assert command["command"] == "lock"
            ack = client.post("/api/client/command-ack", headers=client1, json={"command_id": command["command_id"]})
            assert ack.status_code == 200
            client.post("/api/admin/commands", headers=admin_headers, json={"computer_code": "LAB-01", "command": "unlock"})
            command2 = ws.receive_json()
            assert command2["command"] == "unlock"
            assert client.post("/api/client/command-ack", headers=client1, json={"command_id": command2["command_id"]}).status_code == 200

        offline_events = [
            {"event_id": "ci-start", "type": "session_start", "offline_id": "ci-offline-session", "computer_code": "LAB-02", "at": "2026-01-01T10:00:00+00:00"},
            {"event_id": "ci-incident", "type": "incident", "offline_id": "ci-offline-session", "computer_code": "LAB-02", "category": "Otro", "description": "Falla offline de prueba", "at": "2026-01-01T10:01:00+00:00"},
            {"event_id": "ci-end", "type": "session_end", "offline_id": "ci-offline-session", "computer_code": "LAB-02", "at": "2026-01-01T10:02:00+00:00"},
        ]
        sync = client.post("/api/client/sync-offline", headers=client2, json={"events": offline_events})
        assert sync.status_code == 200, sync.text
        # Una repetición no debe insertar dos veces el mismo evento offline.
        sync2 = client.post("/api/client/sync-offline", headers=client2, json={"events": offline_events})
        assert sync2.status_code == 200, sync2.text
        final_state = client.get("/api/admin/state", headers=admin_headers).json()
        assert len([x for x in final_state["incidents"] if x["description"] == "Falla offline de prueba"]) == 1

        assert client.post("/api/client/logout", headers=client1, json={}).status_code == 200
        assert client.post("/api/client/logout", headers=client2, json={}).status_code == 200
