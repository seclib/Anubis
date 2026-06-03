import unittest

from anubis.distributed import (
    CrossRepoPlanner,
    MultiRepoOrchestrator,
    RepoRegistry,
    RepoRole,
    RepoSelection,
    RepoStatus,
    RepositoryMetadata,
)


def repos() -> tuple[RepositoryMetadata, ...]:
    return (
        RepositoryMetadata(
            repo_id="web",
            name="anubis-web",
            path="/repos/web",
            language="typescript",
            structure=("src/components", "src/app/api-client"),
            role=RepoRole.FRONTEND,
            tags=("react", "ui", "dashboard"),
            dependencies=("api",),
        ),
        RepositoryMetadata(
            repo_id="api",
            name="anubis-api",
            path="/repos/api",
            language="python",
            structure=("backend/routes", "services/auth"),
            role=RepoRole.BACKEND,
            tags=("fastapi", "auth", "users"),
        ),
        RepositoryMetadata(
            repo_id="infra",
            name="anubis-infra",
            path="/repos/infra",
            language="hcl",
            structure=("docker", "deploy"),
            role=RepoRole.INFRA,
            tags=("redis", "ci"),
        ),
    )


class MultiRepoOrchestratorTest(unittest.TestCase):
    def test_repo_registry_tracks_metadata_and_status(self) -> None:
        registry = RepoRegistry()
        registered = registry.register(repos()[0])

        self.assertEqual(registered.language, "typescript")
        self.assertEqual(registry.get("web").role, RepoRole.FRONTEND)
        registry.update_status("web", RepoStatus.DEGRADED)
        self.assertEqual(registry.get("web").status, RepoStatus.DEGRADED)

    def test_repo_selector_chooses_correct_repo_for_task(self) -> None:
        orchestrator = MultiRepoOrchestrator(registry=RepoRegistry(repos()))

        selections = orchestrator.select_repos("fix FastAPI auth endpoint in python backend")

        self.assertEqual(selections[0].repo.repo_id, "api")
        self.assertGreater(selections[0].score, 0)
        self.assertTrue(any(reason.startswith("role:") for reason in selections[0].reasons))

    def test_cross_repo_planning_detects_fullstack_feature(self) -> None:
        orchestrator = MultiRepoOrchestrator(registry=RepoRegistry(repos()))

        plan = orchestrator.plan_task(
            task_id="feature-login",
            goal="build fullstack login feature across React frontend and FastAPI backend",
        )

        self.assertTrue(plan.cross_repo)
        self.assertEqual({route.repo_id for route in plan.routes}, {"web", "api"})
        self.assertTrue(all(route.goal.startswith("[anubis-") for route in plan.routes))

    def test_cross_repo_routes_include_repo_dependency_edges(self) -> None:
        orchestrator = MultiRepoOrchestrator(registry=RepoRegistry(repos()))

        plan = orchestrator.plan_task(
            task_id="feature-auth-ui",
            goal="build frontend ui and backend auth integration",
        )
        route_by_repo = {route.repo_id: route for route in plan.routes}

        self.assertIn("web", route_by_repo)
        self.assertIn("api", route_by_repo)
        self.assertEqual(route_by_repo["web"].depends_on, ("feature-auth-ui:api",))

    def test_cross_repo_planner_orders_dependency_repos_first(self) -> None:
        web, api, _infra = repos()
        planner = CrossRepoPlanner()

        plan = planner.build(
            task_id="feature-auth-ui",
            goal="build frontend ui and backend auth integration",
            selections=(
                RepoSelection(repo=web, score=20, reasons=("role:frontend",)),
                RepoSelection(repo=api, score=10, reasons=("role:backend",)),
            ),
        )

        self.assertEqual([route.repo_id for route in plan.routes], ["api", "web"])
        self.assertEqual(plan.routes[1].depends_on, ("feature-auth-ui:api",))

    def test_task_routing_falls_back_to_first_active_repo(self) -> None:
        orchestrator = MultiRepoOrchestrator(
            registry=RepoRegistry(
                (
                    RepositoryMetadata(
                        repo_id="core",
                        name="core",
                        path="/repos/core",
                        language="python",
                        status=RepoStatus.ACTIVE,
                    ),
                )
            )
        )

        routes = orchestrator.route_task(task_id="unknown", goal="ambiguous work")

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].repo_id, "core")
        self.assertEqual(routes[0].selection_reasons, ("fallback:first-active-repo",))

    def test_disabled_repositories_are_not_selected(self) -> None:
        registry = RepoRegistry(repos())
        registry.update_status("api", RepoStatus.DISABLED)
        orchestrator = MultiRepoOrchestrator(registry=registry)

        selections = orchestrator.select_repos("fix FastAPI auth endpoint")

        self.assertNotIn("api", {selection.repo.repo_id for selection in selections})


if __name__ == "__main__":
    unittest.main()
