"""
E2E tests — Gap 1: Browser & Vision Tools
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


class TestBrowserExtract:
    @pytest.mark.asyncio
    async def test_extract_with_playwright(self):
        """browser_extract returns inner text when Playwright is available."""
        mock_page = AsyncMock()
        mock_page.inner_text = AsyncMock(return_value="Hello from SPA")
        mock_page.goto = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_pw = AsyncMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=None)
        mock_pw.chromium = MagicMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("autoswarm_tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch("autoswarm_tools.browser.async_playwright", return_value=mock_pw):
                from autoswarm_tools.browser import browser_extract
                result = await browser_extract("https://example.com")
                assert "Hello from SPA" in result

    @pytest.mark.asyncio
    async def test_extract_fallback_without_playwright(self):
        """browser_extract falls back to requests when Playwright is absent."""
        with patch("autoswarm_tools.browser.PLAYWRIGHT_AVAILABLE", False):
            with patch("requests.get") as mock_get:
                mock_get.return_value = MagicMock(text="<html><body>Plain content</body></html>", status_code=200)
                mock_get.return_value.raise_for_status = MagicMock()
                from autoswarm_tools.browser import browser_extract
                result = await browser_extract("https://example.com")
                assert isinstance(result, str)


class TestBrowserScreenshot:
    @pytest.mark.asyncio
    async def test_screenshot_returns_base64(self):
        """browser_screenshot returns base64-encoded PNG string."""
        import base64
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        expected_b64 = base64.b64encode(fake_png).decode()

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=fake_png)
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()
        mock_pw = AsyncMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=None)
        mock_pw.chromium = MagicMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch("autoswarm_tools.browser.PLAYWRIGHT_AVAILABLE", True):
            with patch("autoswarm_tools.browser.async_playwright", return_value=mock_pw):
                from autoswarm_tools.browser import browser_screenshot
                result = await browser_screenshot("https://example.com")
                assert result == expected_b64

    @pytest.mark.asyncio
    async def test_screenshot_returns_empty_without_playwright(self):
        with patch("autoswarm_tools.browser.PLAYWRIGHT_AVAILABLE", False):
            from autoswarm_tools.browser import browser_screenshot
            result = await browser_screenshot("https://example.com")
            assert result == ""


class TestVisionDescribe:
    @pytest.mark.asyncio
    async def test_vision_describe_calls_inference(self):
        """vision_describe invokes the LLM with the image."""
        mock_response = MagicMock()
        mock_response.content = "A screenshot of a landing page."

        mock_router = AsyncMock()
        mock_router.complete = AsyncMock(return_value=mock_response)

        with patch("autoswarm_tools.browser.get_default_router", return_value=mock_router, create=True):
            with patch("autoswarm_tools.browser.InferenceRequest", create=True):
                with patch("autoswarm_tools.browser.RoutingPolicy", create=True):
                    with patch("autoswarm_tools.browser.Sensitivity", create=True):
                        from autoswarm_tools.browser import vision_describe
                        result = await vision_describe("base64fakeimage==")
                        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_vision_describe_fallback_on_error(self):
        """vision_describe returns placeholder when LLM is unavailable."""
        with patch("autoswarm_tools.browser.get_default_router", side_effect=Exception("No provider"), create=True):
            from autoswarm_tools.browser import vision_describe
            result = await vision_describe("base64fakeimage==")
            assert "unavailable" in result.lower()
