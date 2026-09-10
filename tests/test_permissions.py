import pytest

from app.tools import Permission, PermissionManager


def test_permission_manager_starts_empty():
    manager = PermissionManager()

    assert manager.granted == set()


def test_grant_permission():
    manager = PermissionManager()

    manager.grant(
        Permission.READ
    )

    assert manager.is_allowed(
        {Permission.READ}
    )


def test_revoke_permission():
    manager = PermissionManager()

    manager.grant(
        Permission.READ
    )

    manager.revoke(
        Permission.READ
    )

    assert not manager.is_allowed(
        {Permission.READ}
    )


def test_multiple_permissions():
    manager = PermissionManager(
        granted={
            Permission.READ,
            Permission.WRITE,
        }
    )

    assert manager.is_allowed(
        {
            Permission.READ,
            Permission.WRITE,
        }
    )


def test_missing_permission_is_denied():
    manager = PermissionManager(
        granted={
            Permission.READ,
        }
    )

    assert not manager.is_allowed(
        {
            Permission.READ,
            Permission.WRITE,
        }
    )


def test_require_raises_for_missing_permission():
    manager = PermissionManager(
        granted={
            Permission.READ,
        }
    )

    with pytest.raises(
        PermissionError,
        match="WRITE",
    ):
        manager.require(
            {
                Permission.READ,
                Permission.WRITE,
            }
        )


def test_require_passes_when_permissions_are_granted():
    manager = PermissionManager(
        granted={
            Permission.READ,
            Permission.WRITE,
        }
    )

    manager.require(
        {
            Permission.READ,
            Permission.WRITE,
        }
    )


def test_delete_requires_confirmation():
    manager = PermissionManager(
        granted={
            Permission.DELETE,
        }
    )

    assert manager.requires_confirmation(
        {Permission.DELETE}
    )

    with pytest.raises(
        PermissionError,
        match="conferma esplicita",
    ):
        manager.authorize(
            required={Permission.DELETE}
        )


def test_delete_is_allowed_with_confirmation():
    manager = PermissionManager(
        granted={
            Permission.DELETE,
        }
    )

    manager.authorize(
        required={Permission.DELETE},
        confirmed=True,
    )


def test_admin_requires_confirmation():
    manager = PermissionManager(
        granted={
            Permission.ADMIN,
        }
    )

    with pytest.raises(PermissionError):
        manager.authorize(
            required={Permission.ADMIN}
        )


def test_public_requires_confirmation():
    manager = PermissionManager(
        granted={
            Permission.PUBLIC,
        }
    )

    with pytest.raises(PermissionError):
        manager.authorize(
            required={Permission.PUBLIC}
        )