import json
import tempfile
import unittest
from pathlib import Path

from anubis.distributed import (
    DomainAllowlist,
    NetworkDecision,
    NetworkIsolationConfig,
    NetworkPolicy,
    NetworkProxyResponse,
    NetworkRequest,
    ProxyController,
    RateLimitRule,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        return NetworkProxyResponse(
            success=True,
            url=request.url,
            status_code=200,
            body="proxied",
            headers={"x-proxy": "anubis"},
        )


def controller(*, allow_network=False, domains=(), resolver=None, rate_limit=None, audit_log_path=None):
    config = NetworkIsolationConfig(
        allow_network=allow_network,
        allowlist=DomainAllowlist(frozenset(domains)),
        rate_limit=rate_limit or RateLimitRule(max_requests=10, window_seconds=60),
        audit_log_path=str(audit_log_path) if audit_log_path else None,
        resolve_dns=resolver is not False,
    )
    transport = FakeTransport()
    policy = NetworkPolicy(config, resolver=resolver) if callable(resolver) else None
    return ProxyController(config, transport=transport, policy=policy), transport


class NetworkIsolationTest(unittest.TestCase):
    def test_network_is_denied_by_default(self) -> None:
        proxy, transport = controller()

        result = proxy.get("task-001", "https://example.com/docs")

        self.assertFalse(result.success)
        self.assertEqual(result.error, "network access disabled by default")
        self.assertEqual(transport.calls, [])
        self.assertEqual(proxy.audit_entries()[0].decision, NetworkDecision.DENY)

    def test_allowlisted_domain_is_proxied_and_logged(self) -> None:
        proxy, transport = controller(allow_network=True, domains=("example.com",), resolver=lambda host: ("93.184.216.34",))

        result = proxy.get("task-001", "https://docs.example.com/page")

        self.assertTrue(result.success)
        self.assertEqual(result.body, "proxied")
        self.assertEqual(len(transport.calls), 1)
        entry = proxy.audit_entries()[0]
        self.assertEqual(entry.decision, NetworkDecision.ALLOW)
        self.assertEqual(entry.host, "docs.example.com")

    def test_unknown_external_domain_is_blocked(self) -> None:
        proxy, transport = controller(allow_network=True, domains=("example.com",), resolver=lambda host: ("93.184.216.34",))

        result = proxy.get("task-001", "https://unknown.test/resource")

        self.assertFalse(result.success)
        self.assertEqual(result.error, "domain is not allowlisted")
        self.assertEqual(transport.calls, [])

    def test_localhost_and_internal_addresses_are_blocked_even_if_allowlisted(self) -> None:
        proxy, transport = controller(allow_network=True, domains=("localhost", "internal.example.com"), resolver=lambda host: ("10.0.0.5",))

        localhost = proxy.get("task-001", "http://localhost:8080/health")
        internal = proxy.get("task-001", "https://internal.example.com/metadata")

        self.assertFalse(localhost.success)
        self.assertEqual(localhost.error, "sensitive endpoint is blocked")
        self.assertFalse(internal.success)
        self.assertEqual(internal.error, "resolved address is blocked")
        self.assertEqual(transport.calls, [])

    def test_rate_limit_blocks_excess_requests(self) -> None:
        proxy, transport = controller(
            allow_network=True,
            domains=("example.com",),
            resolver=lambda host: ("93.184.216.34",),
            rate_limit=RateLimitRule(max_requests=1, window_seconds=60),
        )

        first = proxy.get("task-001", "https://example.com/one")
        second = proxy.get("task-001", "https://example.com/two")

        self.assertTrue(first.success)
        self.assertFalse(second.success)
        self.assertEqual(second.error, "network rate limit exceeded")
        self.assertEqual(len(transport.calls), 1)

    def test_audit_logger_writes_allowed_and_denied_requests(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            audit_path = Path(root) / "network.jsonl"
            proxy, _transport = controller(
                allow_network=True,
                domains=("example.com",),
                resolver=lambda host: ("93.184.216.34",),
                audit_log_path=audit_path,
            )

            proxy.get("task-001", "https://example.com/ok")
            proxy.get("task-001", "https://blocked.example.net/nope")

            records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([record["decision"] for record in records], ["allow", "deny"])
            self.assertEqual(records[0]["host"], "example.com")
            self.assertEqual(records[1]["reason"], "domain is not allowlisted")

    def test_non_http_schemes_are_denied(self) -> None:
        proxy, transport = controller(allow_network=True, domains=("example.com",), resolver=False)

        result = proxy.request(NetworkRequest(task_id="task-001", url="file:///etc/passwd"))

        self.assertFalse(result.success)
        self.assertEqual(result.error, "only http/https proxy requests are allowed")
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
