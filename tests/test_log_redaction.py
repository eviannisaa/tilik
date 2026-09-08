"""No credential reaches a log line.

Two providers authenticate by query string, because it is the only way they
offer: WAQI takes `?token=`, OpenTopography takes `?API_Key=`. `httpx` logs
every request URL at INFO and `api/index.py` turns INFO on, so before this
filter existed the WAQI token was printed in full on every air-quality lookup.
On a serverless host those lines go to durable log storage.

The line is worth keeping: it names the host and the status, which is how a
flaky provider gets diagnosed. So the secret is removed rather than the logger
silenced, and the two tests that matter are that a secret goes and that an
ordinary coordinate stays.
"""

from __future__ import annotations

import logging

import pytest

from api.core.http import SECRET_PARAMS, RedactSecrets, install_log_redaction


def _record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("httpx", logging.INFO, __file__, 0, message, args, None)


def _through(message: str, *args: object) -> str:
    record = _record(message, *args)
    RedactSecrets().filter(record)
    return record.getMessage()


class TestRedaction:
    @pytest.mark.parametrize("param", SECRET_PARAMS)
    def test_every_named_parameter_is_stripped(self, param: str):
        got = _through("HTTP Request: GET %s", f"https://example.com/x?{param}=s3cr3t-value")

        assert "s3cr3t-value" not in got
        assert f"{param}=REDACTED" in got

    def test_the_real_waqi_line(self):
        """Exactly what httpx logged before this existed."""
        got = _through(
            'HTTP Request: GET %s "%s"',
            "https://api.waqi.info/feed/geo:-6.2088;106.8456/?token=529f40165bcbde725de971cd",
            "HTTP/1.1 200 OK",
        )

        assert "529f40165bcbde725de971cd" not in got
        # The diagnostic value of the line has to survive the redaction.
        assert "api.waqi.info" in got
        assert "200 OK" in got

    def test_case_does_not_matter(self):
        """OpenTopography spells it `API_Key`, WAQI spells it `token`."""
        got = _through(
            "HTTP Request: GET %s",
            "https://portal.opentopography.org/API/globaldem?demtype=SRTMGL1&API_Key=abc123",
        )

        assert "abc123" not in got
        assert "demtype=SRTMGL1" in got

    def test_a_secret_in_the_middle_stops_at_the_separator(self):
        got = _through("HTTP Request: GET %s", "https://x.test/a?token=abc123&south=-6.3&n=1")

        assert "abc123" not in got
        assert "south=-6.3" in got
        assert "n=1" in got

    def test_an_ordinary_url_is_left_exactly_alone(self):
        url = "https://nominatim.openstreetmap.org/reverse?lat=-6.2&lon=106.8&format=jsonv2"
        got = _through("HTTP Request: GET %s", url)

        assert got == f"HTTP Request: GET {url}"

    def test_a_record_that_cannot_be_formatted_does_not_break_logging(self):
        """A filter that raises takes the whole log call down with it."""
        record = _record("needs %d args", "not a number")

        assert RedactSecrets().filter(record) is True


class TestInstall:
    def test_it_attaches_to_the_root_handlers(self):
        root = logging.getLogger()
        handler = logging.NullHandler()
        root.addHandler(handler)
        try:
            install_log_redaction()
            assert any(isinstance(f, RedactSecrets) for f in handler.filters)

            # Twice must not stack two copies on one handler.
            install_log_redaction()
            assert sum(isinstance(f, RedactSecrets) for f in handler.filters) == 1
        finally:
            root.removeHandler(handler)
