"""Intent inference from external stimulus into internal goals."""

from anubis.planner import Goal


class IntentInference:
    def infer_goal(self, text: str, *, kind: str = "investigate_alert") -> Goal:
        return Goal(kind=kind, objective=text.strip())

