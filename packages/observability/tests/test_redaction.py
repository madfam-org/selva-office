"""Credential redaction: no password may survive in a rendered log line."""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest
import structlog

from selva_observability import redact_text, redact_url
from selva_observability.logging import configure_logging
from selva_observability.redaction import MASK, redact_credentials_processor

# Obviously fake test values -- never a real credential.
PW = "Fake-Pa55word-xyz"
HOST = "redis.data.svc.cluster.local"


class TestRedactUrl:
    def test_redis_password_only_form(self) -> None:
        out = redact_url(f"redis://:{PW}@{HOST}:6379/8")
        assert out == f"redis://:{MASK}@{HOST}:6379/8"
        assert PW not in out

    def test_user_and_password_keeps_user_host_port_db(self) -> None:
        out = redact_url(f"postgresql+asyncpg://selva:{PW}@db.data:5432/selva?ssl=require")
        assert out == f"postgresql+asyncpg://selva:{MASK}@db.data:5432/selva?ssl=require"

    @pytest.mark.parametrize(
        "url",
        [
            f"rediss://default:{PW}@{HOST}:6380/0",
            f"amqp://guest:{PW}@rabbit:5672/vhost",
            f"https://x-access-token:{PW}@github.com/org/repo.git",
            f"nats://u:{PW}@nats:4222",
            f"mongodb+srv://u:{PW}@cluster0.example.net/db",
        ],
    )
    def test_common_schemes(self, url: str) -> None:
        out = redact_url(url)
        assert PW not in out
        assert MASK in out

    def test_percent_encoded_password(self) -> None:
        encoded = "p%40ss%2Fw0rd%3Ax"
        out = redact_url(f"redis://:{encoded}@{HOST}:6379/8")
        assert encoded not in out
        assert "p%40ss" not in out
        assert out.endswith(f"@{HOST}:6379/8")

    def test_raw_at_sign_inside_password_is_fully_masked(self) -> None:
        out = redact_url(f"redis://:ab@cd{PW}@{HOST}:6379/8")
        assert PW not in out
        assert out == f"redis://:{MASK}@{HOST}:6379/8"

    def test_userinfo_without_colon_is_masked(self) -> None:
        out = redact_url(f"https://{PW}@sentry.example.com/42")
        assert out == f"https://{MASK}@sentry.example.com/42"

    def test_url_without_credentials_is_unchanged(self) -> None:
        url = f"redis://{HOST}:6379/8"
        assert redact_url(url) == url

    def test_schemeless_dsn_is_masked_up_to_last_at(self) -> None:
        out = redact_url(f"selva:{PW}@db.data:5432/selva")
        assert out == f"{MASK}@db.data:5432/selva"

    def test_none_and_empty(self) -> None:
        assert redact_url(None) == ""
        assert redact_url("") == ""


class TestRedactText:
    def test_multiple_urls_in_one_message(self) -> None:
        msg = f"primary redis://:{PW}@a:6379/1 replica redis://:{PW}2@b:6379/1 ok"
        out = redact_text(msg)
        assert PW not in out
        assert out == f"primary redis://:{MASK}@a:6379/1 replica redis://:{MASK}@b:6379/1 ok"

    def test_email_and_plain_text_untouched(self) -> None:
        msg = "contact ops@example.com about http://example.com/path?a=b@c"
        assert redact_text(msg) == msg

    def test_fully_percent_encoded_url_in_query_string(self) -> None:
        msg = f"GET /debug?dsn=redis%3A%2F%2F%3A{PW}%40{HOST}%3A6379%2F8&x=1"
        out = redact_text(msg)
        assert PW not in out
        assert f"redis%3A%2F%2F%3A{MASK}%40{HOST}%3A6379%2F8&x=1" in out

    def test_lowercase_percent_encoding(self) -> None:
        msg = f"redis%3a%2f%2fuser%3a{PW}%40{HOST}"
        out = redact_text(msg)
        assert PW not in out
        assert out.startswith("redis%3A%2F%2Fuser%3A***%40")

    def test_quoted_inside_repr(self) -> None:
        msg = repr({"redis_url": f"redis://:{PW}@{HOST}:6379/8", "n": 1})
        assert PW not in redact_text(msg)


class TestProcessor:
    def test_processor_walks_nested_values(self) -> None:
        class Cfg:
            def __repr__(self) -> str:
                return f"Cfg(url='redis://:{PW}@{HOST}')"

        ed = {
            "event": f"Connected to Redis at redis://:{PW}@{HOST}:6379/8",
            "cfg": {"urls": [f"postgresql://u:{PW}@db/x", ("ok", f"amqp://u:{PW}@q")]},
            "obj": Cfg(),
            "count": 3,
            "flag": True,
            "none": None,
        }
        out = redact_credentials_processor(None, "info", ed)
        assert PW not in json.dumps(out, default=repr)
        assert out["count"] == 3 and out["flag"] is True and out["none"] is None

    def test_processor_leaves_clean_objects_identical(self) -> None:
        sentinel = object()
        ed = {"event": "hello", "obj": sentinel}
        out = redact_credentials_processor(None, "info", ed)
        assert out["obj"] is sentinel
        assert out["event"] == "hello"


class TestConfigureLoggingRedacts:
    """End to end through configure_logging: the rendered line has no password."""

    def setup_method(self) -> None:
        structlog.reset_defaults()
        logging.getLogger().handlers.clear()

    def _capture(self, fmt: str = "json") -> StringIO:
        configure_logging(service_name="redact-svc", log_format=fmt, log_level="DEBUG")
        buf = StringIO()
        logging.getLogger().handlers[0].stream = buf  # type: ignore[attr-defined]
        return buf

    def test_stdlib_percent_format_message(self) -> None:
        """The exact workers startup shape: logger.info("... %s", url)."""
        buf = self._capture()
        logging.getLogger("selva_workers.__main__").info(
            "Connected to Redis at %s", f"redis://:{PW}@{HOST}:6379/8"
        )
        line = buf.getvalue()
        assert PW not in line
        assert json.loads(line)["event"] == f"Connected to Redis at redis://:{MASK}@{HOST}:6379/8"

    def test_stdlib_url_encoded_password(self) -> None:
        buf = self._capture()
        logging.getLogger("x").warning("dsn=%s", "postgresql://u:p%40ss%3Aw0rd@db/x")
        assert "p%40ss" not in buf.getvalue()

    def test_structlog_native_event_and_fields(self) -> None:
        buf = self._capture()
        structlog.get_logger().info(
            f"connect redis://:{PW}@{HOST}", url=f"rediss://u:{PW}@{HOST}:6380/2"
        )
        line = buf.getvalue()
        assert PW not in line
        parsed = json.loads(line)
        assert parsed["url"] == f"rediss://u:{MASK}@{HOST}:6380/2"

    def test_stdlib_exception_message_is_redacted(self) -> None:
        buf = self._capture()
        try:
            raise ValueError(f"Could not parse URL from string 'redis://:{PW}@{HOST}'")
        except ValueError:
            logging.getLogger("x").exception("startup failed")
        line = buf.getvalue()
        assert PW not in line
        assert "Could not parse URL" in line

    def test_structlog_exception_message_is_redacted(self) -> None:
        buf = self._capture()
        try:
            raise ConnectionError(f"cannot reach postgresql://u:{PW}@db/x")
        except ConnectionError:
            structlog.get_logger().exception("db down")
        assert PW not in buf.getvalue()

    def test_console_renderer_also_redacted(self) -> None:
        buf = self._capture(fmt="console")
        logging.getLogger("x").info("Connected to Redis at %s", f"redis://:{PW}@{HOST}:6379/8")
        assert PW not in buf.getvalue()
