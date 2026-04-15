from unittest.mock import AsyncMock, patch

import pytest

from autoswarm_skills.hub import SkillsHubClient


@pytest.mark.asyncio
async def test_hub_browse_mock():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "skills": [
                {"name": "test-skill", "description": "desc", "author": "me", "version": "1.0", "category": "it", "downloads": 10}
            ]
        }

        client = SkillsHubClient()
        skills = await client.browse()
        assert len(skills) == 1
        assert skills[0].name == "test-skill"

@pytest.mark.asyncio
async def test_hub_install_mock(tmp_path):
    with patch("httpx.AsyncClient.get") as mock_get:
        # Mock metadata response
        mock_resp_meta = AsyncMock()
        mock_resp_meta.status_code = 200
        mock_resp_meta.json.return_value = {"download_url": "http://example.com/skill.py"}

        # Mock download response
        mock_resp_dl = AsyncMock()
        mock_resp_dl.status_code = 200
        mock_resp_dl.content = b"print('installed')"

        mock_get.side_effect = [mock_resp_meta, mock_resp_dl]

        client = SkillsHubClient()
        path = await client.install("test-skill", tmp_path)

        assert path.exists()
        assert (path / "test-skill.py").exists()
        assert (path / "test-skill.py").read_text() == "print('installed')"
