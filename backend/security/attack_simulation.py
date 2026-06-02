from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
import hashlib
import ipaddress
import random
from typing import Any


class AttackType(str, Enum):
    PORT_SCAN = "port_scan_simulation"
    BRUTE_FORCE = "brute_force_simulation"
    INJECTION = "injection_attempt_simulation"
    PRIVILEGE_ESCALATION = "privilege_escalation_simulation"
    NETWORK_ANOMALY = "network_anomaly_simulation"


@dataclass(frozen=True)
class SandboxPolicy:
    allow_network: bool = False
    allow_shell: bool = False
    allow_filesystem: bool = False
    synthetic_only: bool = True


@dataclass(frozen=True)
class ThreatActor:
    name: str
    intent: str
    sophistication: int
    noise_level: float


@dataclass(frozen=True)
class Vulnerability:
    identifier: str
    service: str
    severity: str
    description: str
    simulated_exposure: float


@dataclass(frozen=True)
class AttackEvent:
    timestamp: str
    attack_type: AttackType
    source_ip: str
    target: str
    technique: str
    signal: str
    severity: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AttackScenario:
    scenario_id: str
    title: str
    actor: ThreatActor
    attack_type: AttackType
    target: str
    vulnerabilities: tuple[Vulnerability, ...]
    events: tuple[AttackEvent, ...]
    objectives: tuple[str, ...]
    defensive_goals: tuple[str, ...]


@dataclass(frozen=True)
class DefenseControl:
    name: str
    coverage: tuple[AttackType, ...]
    effectiveness: float
    response_minutes: int


@dataclass(frozen=True)
class DefenseScore:
    scenario_id: str
    detection_score: float
    response_score: float
    containment_score: float
    total_score: float
    findings: tuple[str, ...]


class SandboxIsolation:
    BLOCKED_TOKENS = (
        "socket",
        "requests",
        "urllib",
        "subprocess",
        "os.system",
        "shutil",
        "pathlib.Path(",
        "open(",
        "connect(",
        "send(",
        "recv(",
    )

    def __init__(self, policy: SandboxPolicy | None = None) -> None:
        self.policy = policy or SandboxPolicy()

    def assert_safe(self, intent: str = "") -> None:
        if not self.policy.synthetic_only:
            raise RuntimeError("attack simulation must remain synthetic-only")
        if self.policy.allow_network or self.policy.allow_shell or self.policy.allow_filesystem:
            raise RuntimeError("unsafe sandbox policy: host access is disabled for simulations")
        lowered = intent.lower()
        if any(token.lower() in lowered for token in self.BLOCKED_TOKENS):
            raise RuntimeError("unsafe simulation intent rejected")

    def synthetic_ip(self, seed: str) -> str:
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return str(ipaddress.IPv4Address(f"198.51.100.{digest[0] % 254 + 1}"))


class VulnerabilitySimulationEngine:
    CATALOG = {
        AttackType.PORT_SCAN: (
            ("SIM-PORT-001", "ssh", "medium", "Externally visible management service"),
            ("SIM-PORT-002", "http", "low", "Verbose synthetic service banner"),
        ),
        AttackType.BRUTE_FORCE: (
            ("SIM-AUTH-001", "ssh", "high", "Weak synthetic password policy"),
            ("SIM-AUTH-002", "vpn", "medium", "Missing synthetic rate limit"),
        ),
        AttackType.INJECTION: (
            ("SIM-INJ-001", "web", "high", "Unsanitized synthetic input field"),
            ("SIM-INJ-002", "api", "medium", "Synthetic query parameter trust"),
        ),
        AttackType.PRIVILEGE_ESCALATION: (
            ("SIM-PRIV-001", "linux", "critical", "Synthetic excessive sudo scope"),
            ("SIM-PRIV-002", "service", "high", "Synthetic writable service config"),
        ),
        AttackType.NETWORK_ANOMALY: (
            ("SIM-NET-001", "dns", "medium", "Synthetic beacon-like DNS cadence"),
            ("SIM-NET-002", "egress", "high", "Synthetic unusual outbound volume"),
        ),
    }

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def generate(self, attack_type: AttackType, count: int = 2) -> tuple[Vulnerability, ...]:
        entries = self.CATALOG[attack_type]
        selected = self.rng.sample(list(entries), k=min(count, len(entries)))
        return tuple(
            Vulnerability(
                identifier=item[0],
                service=item[1],
                severity=item[2],
                description=item[3],
                simulated_exposure=round(self.rng.uniform(0.25, 0.95), 3),
            )
            for item in selected
        )


class ThreatModelSimulator:
    ACTORS = (
        ThreatActor("synthetic opportunist", "find exposed services", 2, 0.85),
        ThreatActor("synthetic credential attacker", "test identity defenses", 3, 0.65),
        ThreatActor("synthetic web intruder", "probe input validation", 4, 0.45),
        ThreatActor("synthetic insider escalation", "test least privilege", 4, 0.35),
        ThreatActor("synthetic noisy implant", "test anomaly detection", 3, 0.75),
    )

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def actor_for(self, attack_type: AttackType) -> ThreatActor:
        index = {
            AttackType.PORT_SCAN: 0,
            AttackType.BRUTE_FORCE: 1,
            AttackType.INJECTION: 2,
            AttackType.PRIVILEGE_ESCALATION: 3,
            AttackType.NETWORK_ANOMALY: 4,
        }[attack_type]
        actor = self.ACTORS[index]
        jitter = self.rng.uniform(-0.08, 0.08)
        return ThreatActor(actor.name, actor.intent, actor.sophistication, max(0.0, min(1.0, actor.noise_level + jitter)))


class FakeLogGenerator:
    TECHNIQUES = {
        AttackType.PORT_SCAN: ("syn sweep", "banner probe", "closed-port retry"),
        AttackType.BRUTE_FORCE: ("password spray", "invalid login burst", "account lockout probe"),
        AttackType.INJECTION: ("sql-like payload", "template probe", "encoded parameter test"),
        AttackType.PRIVILEGE_ESCALATION: ("sudo policy probe", "service config probe", "token scope check"),
        AttackType.NETWORK_ANOMALY: ("dns beacon cadence", "egress volume spike", "rare destination contact"),
    }
    SEVERITY = ("low", "medium", "high", "critical")

    def __init__(self, isolation: SandboxIsolation, rng: random.Random | None = None) -> None:
        self.isolation = isolation
        self.rng = rng or random.Random()

    def events(self, attack_type: AttackType, target: str, count: int, start: datetime | None = None) -> tuple[AttackEvent, ...]:
        self.isolation.assert_safe(f"generate synthetic events for {attack_type.value}")
        start = start or datetime.now(UTC)
        source = self.isolation.synthetic_ip(f"{attack_type.value}:{target}:{count}")
        items: list[AttackEvent] = []
        for index in range(count):
            technique = self.rng.choice(self.TECHNIQUES[attack_type])
            severity = self.rng.choice(self.SEVERITY[: 2 + min(index // 4, 2)])
            timestamp = (start + timedelta(seconds=index * self.rng.randint(8, 90))).isoformat()
            signal = self._signal(attack_type, technique, target, index)
            items.append(AttackEvent(timestamp, attack_type, source, target, technique, signal, severity, {"synthetic": True}))
        return tuple(items)

    def lines(self, events: tuple[AttackEvent, ...]) -> tuple[str, ...]:
        return tuple(
            f"{event.timestamp} anubis-sim severity={event.severity} src={event.source_ip} "
            f"target={event.target} type={event.attack_type.value} technique=\"{event.technique}\" signal=\"{event.signal}\""
            for event in events
        )

    def _signal(self, attack_type: AttackType, technique: str, target: str, index: int) -> str:
        if attack_type == AttackType.PORT_SCAN:
            return f"{technique} observed across synthetic port bucket {20 + index}-{25 + index}"
        if attack_type == AttackType.BRUTE_FORCE:
            return f"{technique} against synthetic account user{index % 5}"
        if attack_type == AttackType.INJECTION:
            return f"{technique} submitted to synthetic endpoint /{target}/search"
        if attack_type == AttackType.PRIVILEGE_ESCALATION:
            return f"{technique} produced simulated privilege boundary alert"
        return f"{technique} generated simulated baseline deviation {index + 1}"


class AttackScenarioGenerator:
    GOALS = {
        AttackType.PORT_SCAN: ("detect reconnaissance", "identify exposed services", "verify alert enrichment"),
        AttackType.BRUTE_FORCE: ("detect auth abuse", "validate lockout policy", "measure response timing"),
        AttackType.INJECTION: ("detect malicious input", "validate sanitization alerts", "test web triage"),
        AttackType.PRIVILEGE_ESCALATION: ("detect privilege misuse", "validate least privilege", "test containment"),
        AttackType.NETWORK_ANOMALY: ("detect abnormal traffic", "validate egress monitoring", "test anomaly triage"),
    }

    def __init__(self, seed: int | None = None, isolation: SandboxIsolation | None = None) -> None:
        self.rng = random.Random(seed)
        self.isolation = isolation or SandboxIsolation()
        self.threats = ThreatModelSimulator(self.rng)
        self.vulnerabilities = VulnerabilitySimulationEngine(self.rng)
        self.logs = FakeLogGenerator(self.isolation, self.rng)

    def generate(self, attack_type: AttackType | str, target: str = "lab-host", event_count: int = 12) -> AttackScenario:
        attack = AttackType(attack_type)
        self.isolation.assert_safe(f"scenario {attack.value} for synthetic target {target}")
        actor = self.threats.actor_for(attack)
        vulns = self.vulnerabilities.generate(attack)
        events = self.logs.events(attack, target, event_count)
        digest = hashlib.sha256(f"{attack.value}:{target}:{events[0].timestamp}".encode("utf-8")).hexdigest()[:12]
        return AttackScenario(
            scenario_id=f"SIM-{digest}",
            title=f"{attack.value.replace('_', ' ').title()} Against {target}",
            actor=actor,
            attack_type=attack,
            target=target,
            vulnerabilities=vulns,
            events=events,
            objectives=(actor.intent, "generate defensive training evidence"),
            defensive_goals=self.GOALS[attack],
        )


class DefenseEvaluationSystem:
    def score(self, scenario: AttackScenario, controls: tuple[DefenseControl, ...]) -> DefenseScore:
        relevant = [control for control in controls if scenario.attack_type in control.coverage]
        if not relevant:
            return DefenseScore(scenario.scenario_id, 0.0, 0.0, 0.0, 0.0, ("no relevant controls mapped",))
        detection = min(1.0, sum(control.effectiveness for control in relevant) / max(1, len(relevant)))
        response = min(1.0, sum(max(0.0, 1 - control.response_minutes / 60) for control in relevant) / len(relevant))
        severe = sum(1 for event in scenario.events if event.severity in {"high", "critical"})
        containment = min(1.0, detection * 0.55 + response * 0.35 + (1 / max(1, severe + 1)) * 0.10)
        total = round(detection * 0.45 + response * 0.25 + containment * 0.30, 3)
        findings = self._findings(detection, response, containment, severe)
        return DefenseScore(scenario.scenario_id, round(detection, 3), round(response, 3), round(containment, 3), total, findings)

    def _findings(self, detection: float, response: float, containment: float, severe: int) -> tuple[str, ...]:
        findings: list[str] = []
        if detection < 0.6:
            findings.append("detection coverage below target")
        if response < 0.6:
            findings.append("response time exceeds target")
        if containment < 0.6:
            findings.append("containment confidence below target")
        if severe:
            findings.append(f"{severe} high-severity synthetic events require triage")
        return tuple(findings or ["defense posture met simulation target"])


def default_controls() -> tuple[DefenseControl, ...]:
    return (
        DefenseControl("synthetic ids", (AttackType.PORT_SCAN, AttackType.NETWORK_ANOMALY), 0.78, 12),
        DefenseControl("auth monitor", (AttackType.BRUTE_FORCE,), 0.82, 8),
        DefenseControl("web input monitor", (AttackType.INJECTION,), 0.74, 18),
        DefenseControl("privilege policy audit", (AttackType.PRIVILEGE_ESCALATION,), 0.69, 24),
        DefenseControl("incident playbook", tuple(AttackType), 0.64, 20),
    )


class SafeAttackSimulationEngine:
    def __init__(self, seed: int | None = None, isolation: SandboxIsolation | None = None) -> None:
        self.isolation = isolation or SandboxIsolation()
        self.generator = AttackScenarioGenerator(seed=seed, isolation=self.isolation)
        self.evaluator = DefenseEvaluationSystem()

    def simulate(
        self,
        attack_type: AttackType | str,
        target: str = "lab-host",
        event_count: int = 12,
        controls: tuple[DefenseControl, ...] | None = None,
    ) -> dict[str, Any]:
        self.isolation.assert_safe("safe synthetic attack simulation")
        scenario = self.generator.generate(attack_type, target, event_count)
        score = self.evaluator.score(scenario, controls or default_controls())
        logs = self.generator.logs.lines(scenario.events)
        return {"scenario": scenario, "logs": logs, "defense_score": score, "sandbox": self.isolation.policy}
