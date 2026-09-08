"""Organization CRUD, and the membership check that makes "never trust
an organization ID from the client without checking membership" true on
every route: get_current_membership 404s for non-members."""

from httpx import AsyncClient


async def _create_org(client: AsyncClient, name: str = "Acme Inc") -> dict:
    response = await client.post("/orgs", json={"name": name})
    assert response.status_code == 201
    return response.json()


async def test_create_organization_makes_caller_the_owner(client: AsyncClient) -> None:
    organization = await _create_org(client)

    members = await client.get(f"/orgs/{organization['id']}/members")

    assert members.status_code == 200
    assert members.json()[0]["role"] == "OWNER"


async def test_list_my_organizations_returns_created_org(client: AsyncClient) -> None:
    organization = await _create_org(client)

    response = await client.get("/orgs")

    assert response.status_code == 200
    assert any(org["id"] == organization["id"] for org in response.json())


async def test_get_organization_requires_membership(
    client: AsyncClient, current_user_holder: dict, make_user
) -> None:
    organization = await _create_org(client)

    outsider = await make_user("Outsider")
    current_user_holder["user"] = outsider

    response = await client.get(f"/orgs/{organization['id']}")

    assert response.status_code == 404


async def test_rename_organization_requires_admin_or_higher(
    client: AsyncClient,
) -> None:
    organization = await _create_org(client)

    response = await client.patch(
        f"/orgs/{organization['id']}", json={"name": "New Name"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


async def test_rename_organization_rejects_a_plain_member(
    client: AsyncClient,
    current_user_holder: dict,
    make_user,
    add_member,
) -> None:
    owner = current_user_holder["user"]
    organization = await _create_org(client)

    member = await make_user("Just a Member")
    await add_member(organization["id"], member.id)
    current_user_holder["user"] = member

    response = await client.patch(
        f"/orgs/{organization['id']}", json={"name": "New Name"}
    )

    assert response.status_code == 403
    current_user_holder["user"] = owner


async def test_delete_organization_requires_owner(
    client: AsyncClient,
    current_user_holder: dict,
    make_user,
    add_member,
) -> None:
    owner = current_user_holder["user"]
    organization = await _create_org(client)

    admin = await make_user("An Admin")
    from fastauthx_orgs.models import RoleEnum

    await add_member(organization["id"], admin.id, RoleEnum.ADMIN)
    current_user_holder["user"] = admin

    response = await client.delete(f"/orgs/{organization['id']}")
    assert response.status_code == 403

    current_user_holder["user"] = owner
    response = await client.delete(f"/orgs/{organization['id']}")
    assert response.status_code == 204
