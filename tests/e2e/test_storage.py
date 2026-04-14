import pytest
from apps.nexus_api.nexus_api.memory_store.db import EdgeMemoryDB
import os

def test_fts5_memory_search():
    # Use in-memory SQLite for testing to avoid disk locks
    db = EdgeMemoryDB(":memory:")
    
    # Normally this would be handled within internal functions, but testing schema basic assertions
    db._init_schema()
    
    # insert mock
    db._conn.execute(
        "INSERT INTO conversation_episodes (id, run_id, agent_role, started_at) VALUES (?, ?, ?, ?)",
        ("ep123", "run999", "acp-clean-swarm", 16000000.0)
    )
    db._conn.execute(
        "INSERT INTO transcripts (episode_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        ("ep123", "assistant", "We have generated a python script bypassing the captcha using Playwright.", 16000005.0)
    )
    db._conn.commit()
    
    # run full text search
    results = db.fts_search("captcha")
    
    assert len(results) == 1
    assert "Playwright" in results[0]["content"]
    assert results[0]["agent_role"] == "acp-clean-swarm"
    
    db.close()
