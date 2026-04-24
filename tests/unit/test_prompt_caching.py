"""
Unit tests — Gap 7: Prompt Caching (Anthropic Prefix Caching)
"""

from madfam_inference.caching import PromptCacheManager


class TestPromptCacheManager:
    def setup_method(self):
        self.mgr = PromptCacheManager()

    def test_should_cache_anthropic_long_prompt(self):
        """should_cache returns True for Anthropic with a long system prompt."""
        long_prompt = "System instruction. " * 300  # ~6,000 chars > 1,024 tokens
        assert self.mgr.should_cache(long_prompt, "anthropic") is True

    def test_should_not_cache_anthropic_short_prompt(self):
        """should_cache returns False for short prompts."""
        short_prompt = "You are a helpful assistant."
        assert self.mgr.should_cache(short_prompt, "anthropic") is False

    def test_should_not_cache_openai(self):
        """should_cache returns False for non-Anthropic providers."""
        long_prompt = "System instruction. " * 300
        assert self.mgr.should_cache(long_prompt, "openai") is False

    def test_should_not_cache_ollama(self):
        """should_cache returns False for local providers."""
        long_prompt = "System instruction. " * 300
        assert self.mgr.should_cache(long_prompt, "ollama") is False

    def test_apply_breakpoints_anthropic(self):
        """apply_cache_breakpoints injects cache_control for Anthropic."""
        long_prompt = "System instruction. " * 300
        messages = [{"role": "user", "content": "Hello"}]
        out_msgs, out_system = self.mgr.apply_cache_breakpoints(messages, long_prompt, "anthropic")
        assert out_msgs == messages  # Messages unchanged
        assert isinstance(out_system, list)
        assert len(out_system) == 1
        assert out_system[0]["cache_control"] == {"type": "ephemeral"}
        assert out_system[0]["text"] == long_prompt

    def test_apply_breakpoints_non_anthropic_unchanged(self):
        """apply_cache_breakpoints is a no-op for non-Anthropic providers."""
        long_prompt = "System instruction. " * 300
        messages = [{"role": "user", "content": "Hello"}]
        out_msgs, out_system = self.mgr.apply_cache_breakpoints(messages, long_prompt, "openai")
        assert out_system == long_prompt  # Returned as string, unchanged
        assert out_msgs == messages

    def test_extract_cache_metrics_reads_headers(self):
        """extract_cache_metrics correctly reads response headers."""
        headers = {
            "anthropic-cache-read-input-tokens": "512",
            "anthropic-cache-creation-input-tokens": "2048",
        }
        metrics = self.mgr.extract_cache_metrics(headers)
        assert metrics["cache_read_tokens"] == 512
        assert metrics["cache_write_tokens"] == 2048

    def test_extract_cache_metrics_missing_headers(self):
        """extract_cache_metrics returns 0 when headers are absent."""
        metrics = self.mgr.extract_cache_metrics({})
        assert metrics["cache_read_tokens"] == 0
        assert metrics["cache_write_tokens"] == 0
