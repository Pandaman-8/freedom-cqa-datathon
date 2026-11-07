"""Contract for the ML teammate. No fake evaluation in the foundation."""
from typing import Protocol

from .schemas import Checklist, CriterionAnswer


class Evaluator(Protocol):
    def evaluate(self, conversation: dict, checklist: Checklist) -> list[CriterionAnswer]:
        """Return one grounded answer per criterion, with original message IDs."""
        ...


class UnconfiguredEvaluator:
    def evaluate(self, conversation: dict, checklist: Checklist) -> list[CriterionAnswer]:
        raise NotImplementedError("ML provider is not configured yet")


evaluator: Evaluator = UnconfiguredEvaluator()
