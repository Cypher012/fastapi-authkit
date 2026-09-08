"""Membership changes: role updates, removal, leaving — and the
last-owner guard that stops an organization from ever ending up
ownerless (OrgsService._guard_last_owner)."""

from httpx import AsyncClient

from fastauthx_orgs.models import RoleEnum


async def _create_org(client: AsyncClient, name: str = "Acme Inc") -> dict:
    response = await client.post("/orgs", json={"name": name})
    assert response.status_code == 201
    return response.json()


async def test_owner_can_promote_a_member_to_admin(
    client: AsyncClient, make_user, add_member
) -> None:
    organization = await _create_org(client)
    member = await make_user("Member")
    await add_member(organization["id"], member.id, RoleEnum.MEMBER)

    response = await client.patch(
        f"/orgs/{organization['id']}/members/{member.id}", json={"role": "ADMIN"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"


async def test_admin_cannot_change_roles(
    client: AsyncClient, current_user_holder: dict, make_user, add_member
) -> None:
    owner = current_user_holder["user"]
    organization = await _create_org(client)

    admin = await make_user("Admin")
    await add_member(organization["id"], admin.id, RoleEnum.ADMIN)
    other_member = await make_user("Other Member")
    await add_member(organization["id"], other_member.id, RoleEnum.MEMBER)

    current_user_holder["user"] = admin
    response = await client.patch(
        f"/orgs/{organization['id']}/members/{other_member.id}",
        json={"role": "ADMIN"},
    )

    assert response.status_code == 403
    current_user_holder["user"] = owner


async def test_cannot_demote_the_last_owner(client: AsyncClient) -> None:
    organization = await _create_org(client)
    owner_id = (await client.get(f"/orgs/{organization['id']}/members")).json()[0][
        "user_id"
    ]

    response = await client.patch(
        f"/orgs/{organization['id']}/members/{owner_id}", json={"role": "ADMIN"}
    )

    assert response.status_code == 409


async def test_admin_can_remove_a_member(
    client: AsyncClient, current_user_holder: dict, make_user, add_member
) -> None:
    owner = current_user_holder["user"]
    organization = await _create_org(client)

    admin = await make_user("Admin")
    await add_member(organization["id"], admin.id, RoleEnum.ADMIN)
    member = await make_user("Member")
    await add_member(organization["id"], member.id, RoleEnum.MEMBER)

    current_user_holder["user"] = admin
    response = await client.delete(f"/orgs/{organization['id']}/members/{member.id}")

    assert response.status_code == 204
    current_user_holder["user"] = owner


async def test_cannot_remove_the_last_owner(client: AsyncClient) -> None:
    organization = await _create_org(client)
    owner_id = (await client.get(f"/orgs/{organization['id']}/members")).json()[0][
        "user_id"
    ]

    response = await client.delete(f"/orgs/{organization['id']}/members/{owner_id}")

    assert response.status_code == 409


async def test_member_can_leave_organization(
    client: AsyncClient, current_user_holder: dict, make_user, add_member
) -> None:
    owner = current_user_holder["user"]
    organization = await _create_org(client)

    member = await make_user("Member")
    await add_member(organization["id"], member.id, RoleEnum.MEMBER)
    current_user_holder["user"] = member

    response = await client.delete(f"/orgs/{organization['id']}/members/me")

    assert response.status_code == 204
    current_user_holder["user"] = owner


async def test_sole_owner_cannot_leave_organization(client: AsyncClient) -> None:
    organization = await _create_org(client)

    response = await client.delete(f"/orgs/{organization['id']}/members/me")

    assert response.status_code == 409
