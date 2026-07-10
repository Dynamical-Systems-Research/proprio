import pytest

from proprio.instrument_qualification import AdaptiveSkillLimits, compile_instrument_skill


class AdaptiveController:
    def __init__(self, scores: list[float]) -> None:
        self.scores = iter(scores)
        self.calls: list[tuple[str, float | None]] = []

    def reset(self) -> None:
        self.calls.append(("reset", None))

    def sample(self) -> dict[str, float]:
        value = next(self.scores)
        self.calls.append(("sample", value))
        return {"score": value}

    def adjust(self, amount: float) -> None:
        self.calls.append(("adjust", amount))

    def release(self) -> None:
        self.calls.append(("release", None))


METHODS = frozenset({"reset", "sample", "adjust", "release"})


def test_bounded_adaptive_skill_can_branch_on_controller_observations() -> None:
    source = """def run(controller):
    controller.reset()
    best = 0.0
    for index in range(3):
        reading = controller.sample()
        if reading["score"] > best:
            best = reading["score"]
        else:
            controller.adjust(0.5 * (index + 1))
    controller.release()
    return {"best": best}
"""
    controller = AdaptiveController([1.0, 0.5, 2.0])
    result = compile_instrument_skill(source, METHODS)(controller)
    assert result == {"best": 2.0}
    assert controller.calls == [
        ("reset", None),
        ("sample", 1.0),
        ("sample", 0.5),
        ("adjust", 1.0),
        ("sample", 2.0),
        ("release", None),
    ]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("while True:\n        controller.sample()", "While"),
        ("for i in range(controller.sample()):\n        pass", "range bounds"),
        ("for i in range(17):\n        controller.sample()", "iteration bound"),
        ("controller.trace", "direct reads"),
        ("open('x')", "only controller methods"),
    ],
)
def test_adaptive_skill_rejects_unbounded_or_ambient_behavior(body: str, message: str) -> None:
    source = f"def run(controller):\n    {body}\n    return {{}}\n"
    with pytest.raises(ValueError, match=message):
        compile_instrument_skill(source, METHODS)


def test_static_controller_call_bound_counts_loop_body() -> None:
    source = """def run(controller):
    for index in range(4):
        controller.sample()
        controller.adjust(index)
    return {}
"""
    with pytest.raises(ValueError, match="controller call bound 8 exceeds 7"):
        compile_instrument_skill(
            source,
            METHODS,
            limits=AdaptiveSkillLimits(max_controller_calls=7),
        )
