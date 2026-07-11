from types import SimpleNamespace

from proprio.policy import DSV4Client


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return {"ok": True}


def test_openrouter_route_and_reasoning_are_frozen_per_request() -> None:
    client = DSV4Client(
        base_url="https://openrouter.ai/api/v1",
        model="deepseek/deepseek-v4-flash",
        api_key="fixture",
        provider="GMICloud",
        reasoning_effort="high",
    )
    completions = FakeCompletions()
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    response = client.create_chat_completion(
        model=client.model,
        messages=[{"role": "user", "content": "probe"}],
        temperature=0.0,
    )
    assert response == {"ok": True}
    assert completions.kwargs["extra_body"] == {
        "provider": {
            "order": ["GMICloud"],
            "only": ["GMICloud"],
            "allow_fallbacks": False,
            "require_parameters": True,
        },
        "reasoning": {"effort": "high"},
        "include_reasoning": True,
    }


def test_reasoning_can_be_enabled_without_an_effort_parameter() -> None:
    client = DSV4Client(
        base_url="https://openrouter.ai/api/v1",
        model="qwen/qwen3.6-flash",
        api_key="fixture",
        provider="Alibaba",
        include_reasoning=True,
    )
    completions = FakeCompletions()
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client.create_chat_completion(model=client.model, messages=[])
    assert completions.kwargs["extra_body"]["reasoning"] == {"enabled": True}
    assert completions.kwargs["extra_body"]["include_reasoning"] is True


def test_openrouter_can_freeze_an_ordered_same_model_fallback_route() -> None:
    client = DSV4Client(
        base_url="https://openrouter.ai/api/v1",
        model="deepseek/deepseek-v4-flash",
        api_key="fixture",
        provider="DeepInfra,GMICloud",
        reasoning_effort="high",
    )
    completions = FakeCompletions()
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client.create_chat_completion(model=client.model, messages=[])
    assert completions.kwargs["extra_body"]["provider"] == {
        "order": ["DeepInfra", "GMICloud"],
        "only": ["DeepInfra", "GMICloud"],
        "allow_fallbacks": True,
        "require_parameters": True,
    }
