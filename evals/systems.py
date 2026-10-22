"""Registry for RAG systems evaluated by RegulatorIQ evaluation harness."""

from __future__ import annotations

from typing import Any, Callable, Dict

_SYSTEM_REGISTRY: Dict[str, Callable[..., Any]] = {}


def register_system(name: str, factory: Callable[..., Any]) -> None:
    """Register a system factory function under a unique name."""
    _SYSTEM_REGISTRY[name] = factory


def get_system(name: str, **kwargs: Any) -> Any:
    """Retrieve and instantiate a registered system by name."""
    if name not in _SYSTEM_REGISTRY:
        available = list(_SYSTEM_REGISTRY.keys())
        raise KeyError(f"Unknown system '{name}'. Available systems: {available}")
    return _SYSTEM_REGISTRY[name](**kwargs)


def list_systems() -> list[str]:
    """Return all registered system names."""
    return list(_SYSTEM_REGISTRY.keys())


# Register baseline system
def _create_baseline(**kwargs: Any) -> Any:
    from agent.baseline import BaselineRAG
    from retrieval.index_store import IndexStore

    index_store = kwargs.get("index_store")
    if index_store is None:
        index_store = IndexStore.load(verify="fast")
    llm = kwargs.get("llm")
    return BaselineRAG(index_store=index_store, llm=llm)


register_system("baseline", _create_baseline)
