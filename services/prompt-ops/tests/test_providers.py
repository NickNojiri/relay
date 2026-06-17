from app.config import Settings
from app.providers import EchoProvider, OllamaProvider, build_provider


def test_build_provider_echo():
    assert isinstance(build_provider(Settings(relay_default_provider="echo")), EchoProvider)


def test_build_provider_ollama_default():
    assert isinstance(build_provider(Settings(relay_default_provider="ollama")), OllamaProvider)
