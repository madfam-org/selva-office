from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from selva_skills.hub import SkillsHubClient


@pytest.mark.asyncio
async def test_hub_browse_mock():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "skills": [
            {
                "name": "test-skill", "description": "desc",
                "author": "me", "version": "1.0",
                "category": "it", "downloads": 10,
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        client = SkillsHubClient()
        skills = await client.browse()
        assert len(skills) == 1
        assert skills[0].name == "test-skill"

@pytest.mark.asyncio
async def test_hub_install_mock(tmp_path):
    # Mock metadata response
    mock_resp_meta = MagicMock()
    mock_resp_meta.status_code = 200
    mock_resp_meta.raise_for_status = MagicMock()
    mock_resp_meta.json.return_value = {"download_url": "http://example.com/skill.py"}

    # Mock download response
    mock_resp_dl = MagicMock()
    mock_resp_dl.status_code = 200
    mock_resp_dl.raise_for_status = MagicMock()
    mock_resp_dl.content = b"print('installed')"

    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        side_effect=[mock_resp_meta, mock_resp_dl],
    ):
        client = SkillsHubClient()
        path = await client.install("test-skill", tmp_path)

        assert path.exists()
        assert (path / "test-skill.py").exists()
        assert (path / "test-skill.py").read_text() == "print('installed')"
