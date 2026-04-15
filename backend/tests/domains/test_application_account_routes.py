def test_application_account_routes_create_list_update_and_delete(auth_client) -> None:
    create_response = auth_client.post(
        "/api/application-accounts",
        json={
            "platform_family": "icims",
            "tenant_host": "acme.icims.com",
            "login_identifier": "owner@example.com",
            "password": "hunter2",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["platform_family"] == "icims"
    assert create_response.json()["tenant_host"] == "acme.icims.com"
    assert create_response.json()["login_identifier_masked"] == "o***r@example.com"
    assert "password" not in create_response.text
    assert "hunter2" not in create_response.text

    list_response = auth_client.get("/api/application-accounts")

    assert list_response.status_code == 200
    assert list_response.json()[0]["login_identifier_masked"] == "o***r@example.com"

    update_response = auth_client.put(
        f"/api/application-accounts/{create_response.json()['id']}",
        json={
            "platform_family": "icims",
            "tenant_host": "globex.icims.com",
            "password": "new-password",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["tenant_host"] == "globex.icims.com"
    assert update_response.json()["login_identifier_masked"] == "o***r@example.com"
    assert "new-password" not in update_response.text

    delete_response = auth_client.delete(f"/api/application-accounts/{create_response.json()['id']}")

    assert delete_response.status_code == 204
    assert auth_client.get("/api/application-accounts").json() == []


def test_application_account_routes_reject_duplicate_platform_tenant(auth_client) -> None:
    payload = {
        "platform_family": "icims",
        "tenant_host": "acme.icims.com",
        "login_identifier": "owner@example.com",
        "password": "hunter2",
    }

    first = auth_client.post("/api/application-accounts", json=payload)
    second = auth_client.post("/api/application-accounts", json=payload)
    third = auth_client.post(
        "/api/application-accounts",
        json={**payload, "tenant_host": "globex.icims.com"},
    )

    assert first.status_code == 201
    assert second.status_code == 422
    assert second.json()["detail"] == "An application account already exists for that platform and employer host."
    assert third.status_code == 201


def test_application_account_routes_reject_platforms_that_do_not_need_credentials(auth_client) -> None:
    response = auth_client.post(
        "/api/application-accounts",
        json={
            "platform_family": "greenhouse",
            "tenant_host": "",
            "login_identifier": "owner@example.com",
            "password": "hunter2",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Greenhouse does not use stored application accounts."
