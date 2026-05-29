"""Dependency-injected runtime runner for autonomous agent loops."""

from __future__ import annotations

from typing import Any, Callable

from core.contracts import AgentDependencies

ProgressCallback = Callable[[dict[str, Any]], None]
AgentLoop = Callable[..., Any]
DependencyFactory = Callable[[], AgentDependencies]


class AgentRunner:
    """Run an injected agent loop with injected concrete dependencies."""

    def __init__(
        self,
        *,
        agent_loop: AgentLoop,
        dependency_factory: DependencyFactory,
    ) -> None:
        self._agent_loop = agent_loop
        self._dependency_factory = dependency_factory

    def run(
        self,
        task: str,
        *,
        use_planner: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> Any:
        return self._agent_loop(
            task,
            use_planner=use_planner,
            progress_callback=progress_callback,
            dependencies=self._dependency_factory(),
        )


def build_agent_runner(
    *,
    agent_loop: AgentLoop,
    dependency_factory: DependencyFactory,
) -> AgentRunner:
    return AgentRunner(agent_loop=agent_loop, dependency_factory=dependency_factory)


def default_agent_runner() -> AgentRunner:
    """Compatibility bootstrap for existing CLI/API entrypoints.

    This is the composition root: concrete agent functions are imported here,
    wired to runtime services, then passed by dependency injection.
    """
    from agent.loop import run_agent_loop as agent_loop
    from agent.multi_agent import agent_prompt, get_agent
    from runtime.dependencies import default_agent_dependencies
    from runtime.llm_agents import build_llm_agent_caller

    call_agent = build_llm_agent_caller(
        get_agent=get_agent,
        build_prompt=agent_prompt,
    )
    return build_agent_runner(
        agent_loop=agent_loop,
        dependency_factory=lambda: default_agent_dependencies(call_agent),
    )


def run_agent_loop(
    task: str,
    *,
    use_planner: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> Any:
    return default_agent_runner().run(
        task,
        use_planner=use_planner,
        progress_callback=progress_callback,
    )


__all__ = ["AgentRunner", "build_agent_runner", "default_agent_runner", "run_agent_loop"]
