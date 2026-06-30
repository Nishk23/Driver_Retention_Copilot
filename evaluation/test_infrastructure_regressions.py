import json

from rag.ingest_policy import DEFAULT_PDF, build_policy_chunks
from state.memory import MEMORY_DIR, load_memory, save_memory


def test_policy_pdf_is_split_into_policy_level_chunks():
    chunks = build_policy_chunks(str(DEFAULT_PDF))
    texts = [chunk["text"] for chunk in chunks]

    assert len(chunks) > 1
    assert any("Global Monthly Cap" in text for text in texts)
    assert any("Airport Short Fares" in text for text in texts)
    assert any("Technical & GPS Glitches" in text for text in texts)
    assert max(len(text) for text in texts) < 800


def test_memory_path_is_repo_root_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session_id = "cwd-independent-test"
    save_memory(session_id, {"last_driver_id": "D-LON-001"})

    memory_path = MEMORY_DIR / f"{session_id}.json"
    try:
        assert memory_path.exists()
        assert json.loads(memory_path.read_text())["last_driver_id"] == "D-LON-001"
        assert load_memory(session_id)["last_driver_id"] == "D-LON-001"
        assert not (tmp_path / "outputs" / "memory" / f"{session_id}.json").exists()
    finally:
        memory_path.unlink(missing_ok=True)
