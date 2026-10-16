import os
import sys
import tempfile
from pathlib import Path

# Isola el almacén del usuario que ejecuta CI.
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="siga-local-")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import OfflineVault

def test_vault_encrypts_queue_and_caches_credentials():
    vault = OfflineVault()
    vault.cache_user("MATRICULA-TEST", "Password de prueba 123", "Alumno Test")
    assert vault.verify_user("MATRICULA-TEST", "Password de prueba 123") == "Alumno Test"
    assert vault.verify_user("MATRICULA-TEST", "incorrecta") is None
    vault.enqueue({"type": "incident", "description": "Error de prueba"})
    events = vault.events()
    assert len(events) == 1
    assert events[0]["type"] == "incident"
    assert events[0].get("event_id")
    vault.clear_events()
    assert vault.events() == []

def test_windows_idle_detector_is_optional_on_non_windows():
    from client import windows_idle_seconds
    value = windows_idle_seconds()
    if os.name == "nt":
        assert value is None or value >= 0
    else:
        assert value is None
