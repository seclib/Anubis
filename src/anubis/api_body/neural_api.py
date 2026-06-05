"""Brain-facing API facade."""

from dataclasses import dataclass

from anubis.core_life.brain.intent_inference import IntentInference


@dataclass(slots=True)
class NeuralAPI:
    intent: IntentInference

    def ingest(self, text: str):
        return self.intent.infer_goal(text)

