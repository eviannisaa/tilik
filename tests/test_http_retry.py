"""A transient upstream failure must not empty a whole section.

Overpass's public endpoint is shared and frequently queues past its own limit,
answering 504. `fetch_json` had no retry at all, so one of those turned "137
places within 1.5 km" into "We couldn't check what's nearby" — for a query that
succeeds when asked again a second later.
"""

from __future__ import annotations

import asyncio

import pytest

from api.core import http
from api.core.errors import (
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    InvalidQueryError,
)


class Recorder:
    """Stands in for `_request`, failing a set number of times first."""

    def __init__(self, failures: int, error: type[Exception] = UpstreamUnavailableError):
        self.failures = failures
        self.error = error
        self.calls = 0

    async def __call__(self, url, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error(detail="upstream is having a moment")

        class Response:
            @staticmethod
            def json():
                return {"items": ["ok"]}

        return Response()


def run(monkeypatch: pytest.MonkeyPatch, recorder: Recorder, **kwargs):
    monkeypatch.setattr(http, "_request", recorder)
    # The backoff is real time; tests should not spend it.
    monkeypatch.setattr(http, "RETRY_BACKOFF_SECONDS", 0)
    return asyncio.run(
        http.fetch_json("https://example.test", provider="overpass", **kwargs)
    )


class TestRetry:
    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(UpstreamUnavailableError, id="504"),
            pytest.param(UpstreamTimeoutError, id="timeout"),
            pytest.param(UpstreamRateLimitedError, id="429"),
        ],
    )
    def test_one_transient_failure_is_survived(
        self, monkeypatch: pytest.MonkeyPatch, error: type[Exception]
    ) -> None:
        recorder = Recorder(failures=1, error=error)

        payload = run(monkeypatch, recorder, retries=1)

        assert payload == {"items": ["ok"]}
        assert recorder.calls == 2

    def test_the_attempt_budget_is_respected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One retry means two attempts, not indefinite patience."""
        recorder = Recorder(failures=99)

        with pytest.raises(UpstreamUnavailableError):
            run(monkeypatch, recorder, retries=1)

        assert recorder.calls == 2

    def test_retrying_is_opt_in(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A retry is only safe where the call is a read, so callers decide.

        Overpass takes its query by POST and is still a read; a POST elsewhere
        may not be, which is why this is not a default.
        """
        recorder = Recorder(failures=1)

        with pytest.raises(UpstreamUnavailableError):
            run(monkeypatch, recorder)

        assert recorder.calls == 1

    def test_a_rejected_request_is_not_repeated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rejected request is wrong; repeating it burns the provider's quota.

        `_request` maps 4xx onto a non-retriable error, so this stands in for
        one: only the three transient upstream errors are tried again.
        """
        recorder = Recorder(failures=99, error=InvalidQueryError)

        with pytest.raises(InvalidQueryError):
            run(monkeypatch, recorder, retries=1)

        assert recorder.calls == 1

    def test_a_first_attempt_that_works_costs_nothing_extra(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorder = Recorder(failures=0)

        run(monkeypatch, recorder, retries=1)

        assert recorder.calls == 1


class HostRecorder:
    """Stands in for `fetch_json`, failing named hosts and answering the rest."""

    def __init__(self, failing: set[str]):
        self.failing = failing
        self.tried: list[str] = []

    async def __call__(self, url, **kwargs):
        self.tried.append(url)
        if url in self.failing:
            raise UpstreamUnavailableError(detail=f"{url} is down")
        return {"items": [url]}


def chain(monkeypatch: pytest.MonkeyPatch, recorder: HostRecorder, urls: list[str]):
    monkeypatch.setattr(http, "fetch_json", recorder)
    return asyncio.run(
        http.fetch_json_from_first(urls, provider="overpass", method="POST")
    )


HOSTS = ["https://main.test", "https://mirror-one.test", "https://mirror-two.test"]


class TestMirrorChain:
    def test_a_dead_main_host_falls_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Measured in one minute: the main host refused the connection outright,
        one mirror returned 502, two timed out and one answered. A retry against
        a rate-limited address cannot recover that; another host can.
        """
        recorder = HostRecorder(failing={HOSTS[0], HOSTS[1]})

        payload, index = chain(monkeypatch, recorder, HOSTS)

        assert payload == {"items": [HOSTS[2]]}
        assert recorder.tried == HOSTS
        # Which host answered, so a caller can weigh an empty result from a
        # mirror differently from one from the primary.
        assert index == 2

    def test_the_main_host_is_tried_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A mirror is a fallback, not a load balancer."""
        recorder = HostRecorder(failing=set())

        payload, index = chain(monkeypatch, recorder, HOSTS)

        assert payload == {"items": [HOSTS[0]]}
        assert recorder.tried == [HOSTS[0]]
        assert index == 0

    def test_every_host_down_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorder = HostRecorder(failing=set(HOSTS))

        with pytest.raises(UpstreamUnavailableError):
            chain(monkeypatch, recorder, HOSTS)

        assert recorder.tried == HOSTS

    def test_no_hosts_is_an_error_not_a_silent_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returning nothing here would read as "the area is empty"."""
        recorder = HostRecorder(failing=set())

        with pytest.raises(UpstreamUnavailableError):
            chain(monkeypatch, recorder, [])


class TestHostList:
    def test_the_main_host_leads_and_mirrors_follow(self) -> None:
        from api.core.config import Settings

        settings = Settings(
            overpass_api_url="https://main.test",
            overpass_fallback_urls="https://a.test, https://b.test",
        )

        assert settings.overpass_urls == [
            "https://main.test",
            "https://a.test",
            "https://b.test",
        ]

    def test_blank_disables_the_fallback(self) -> None:
        """Each mirror receives the checked coordinate, so opting out matters."""
        from api.core.config import Settings

        settings = Settings(
            overpass_api_url="https://main.test", overpass_fallback_urls=""
        )

        assert settings.overpass_urls == ["https://main.test"]


class TestChainBudget:
    """The timeout belongs to the chain, and its remainder goes to the next host.

    Two wrong versions came first. Giving each host the full timeout meant a
    failing first host spent all of it and the second then started its own: 32
    seconds for a lookup budgeted at 16. Splitting it evenly fixed that and broke
    something else, because a primary that refuses a connection in one second
    forfeited its whole half while the fallback got five seconds for a request
    that needs nine, so it could never succeed at all.
    """

    def test_a_fast_failure_hands_its_unspent_time_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[float | None] = []

        async def _capture(url, **kwargs):
            seen.append(kwargs.get("timeout"))
            if len(seen) == 1:
                raise UpstreamUnavailableError(detail="refused")
            return {"ok": True}

        monkeypatch.setattr(http, "fetch_json", _capture)
        asyncio.run(
            http.fetch_json_from_first(
                ["https://a.test", "https://b.test"],
                provider="overpass",
                timeout=10.0,
            )
        )

        # The first host is offered the whole budget, and the second gets what is
        # left rather than a pre-cut half.
        assert seen[0] == pytest.approx(10.0, abs=0.5)
        assert seen[1] == pytest.approx(10.0, abs=0.5)
        assert seen[1] > 5.0

    def test_a_single_host_keeps_the_whole_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[float | None] = []

        async def _capture(url, **kwargs):
            seen.append(kwargs.get("timeout"))
            return {"ok": True}

        monkeypatch.setattr(http, "fetch_json", _capture)
        asyncio.run(
            http.fetch_json_from_first(
                ["https://a.test"], provider="overpass", timeout=16.0
            )
        )

        assert seen[0] == pytest.approx(16.0, abs=0.5)

    def test_no_timeout_stays_no_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`None` means "use the client default", and must not be arithmetic on."""
        seen: list[float | None] = []

        async def _capture(url, **kwargs):
            seen.append(kwargs.get("timeout"))
            return {"ok": True}

        monkeypatch.setattr(http, "fetch_json", _capture)
        asyncio.run(http.fetch_json_from_first(["https://a.test"], provider="overpass"))

        assert seen == [None]

    def test_an_exhausted_budget_stops_the_chain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Below a second there is no point starting a request across the internet."""
        tried: list[str] = []

        async def _slow(url, **kwargs):
            tried.append(url)
            await asyncio.sleep(0.2)
            raise UpstreamUnavailableError(detail="down")

        monkeypatch.setattr(http, "fetch_json", _slow)

        with pytest.raises(UpstreamUnavailableError):
            asyncio.run(
                http.fetch_json_from_first(
                    ["https://a.test", "https://b.test", "https://c.test"],
                    provider="overpass",
                    timeout=1.0,
                )
            )

        # The first spends the budget; the rest are not started.
        assert tried == ["https://a.test"]
