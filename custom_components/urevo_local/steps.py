"""Reset-aware accumulation of device-reported steps, without estimation."""

from dataclasses import dataclass


@dataclass
class StepCounter:
    total: int = 0
    steps: int | None = None
    elapsed: int | None = None

    def update(self, steps: int, elapsed: int) -> int:
        if self.steps is None or steps < self.steps or elapsed < self.elapsed:
            delta = steps
        else:
            delta = steps - self.steps
        self.total += delta
        self.steps, self.elapsed = steps, elapsed
        return self.total
