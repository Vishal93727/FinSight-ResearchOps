"""OpenAPI contract checks for the Phase 4 governance, RL and paper-only routes."""


def test_phase4_openapi_routes_are_registered_and_no_live_execution_route_exists(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    expected = {
        "/api/v1/rl/evaluations/jobs": {"post"},
        "/api/v1/rl/evaluations": {"get"},
        "/api/v1/rl/evaluations/comparison": {"get"},
        "/api/v1/governance/models": {"get", "post"},
        "/api/v1/governance/models/{model_version_id}/risk-review": {"get"},
        "/api/v1/governance/models/{model_version_id}/decision": {"post"},
        "/api/v1/governance/models/{model_version_id}/promote": {"post"},
        "/api/v1/governance/models/{model_version_id}/rollback": {"post"},
        "/api/v1/execution/accounts": {"get", "post"},
        "/api/v1/execution/accounts/{account_id}/summary": {"get"},
        "/api/v1/execution/accounts/{account_id}/orders": {"get", "post"},
        "/api/v1/execution/accounts/{account_id}/kill-switch": {"post"},
        "/api/v1/execution/accounts/{account_id}/reconcile": {"post"},
        "/api/v1/execution/accounts/{account_id}/audit": {"get"},
    }

    for path, methods in expected.items():
        assert path in paths, f"Missing Phase 4 route: {path}"
        assert methods.issubset(paths[path]), f"Missing methods for {path}: {methods - paths[path].keys()}"

    assert not any("live" in path.lower() or "broker/live" in path.lower() for path in paths)
    assert "paper execution only" in {
        tag.lower() for path_item in paths.values() for operation in path_item.values()
        for tag in operation.get("tags", [])
    }


def test_rl_openapi_contract_documents_role_and_request_constraints(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/rl/evaluations/jobs"]["post"]
    assert operation["requestBody"]["required"] is True
    payload_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert payload_schema["$ref"].endswith("RLEvaluationJobCreate")
    contract = schema["components"]["schemas"]["RLEvaluationJobCreate"]
    assert contract["properties"]["algorithm"]["enum"] == ["PPO", "SAC"]
    assert contract["properties"]["total_timesteps"]["minimum"] == 5000
    assert contract["properties"]["date_column"]["const"] == "date"
    assert contract["properties"]["price_column"]["const"] == "close"
