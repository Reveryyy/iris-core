from enum import Enum


class Permission(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    GUI = "GUI"
    NETWORK = "NETWORK"
    DELETE = "DELETE"
    ADMIN = "ADMIN"
    PUBLIC = "PUBLIC"


class PermissionManager:
    CONFIRMATION_PERMISSIONS = {
        Permission.DELETE,
        Permission.ADMIN,
        Permission.PUBLIC,
    }

    def __init__(
            self,
            granted: set[Permission] | None = None,
    ):
        self.granted = granted or set()

    def grant(
            self,
            permission: Permission,
    ) -> None:
        self.granted.add(permission)

    def revoke(
            self,
            permission: Permission,
    ) -> None:
        self.granted.discard(permission)

    def is_allowed(
            self,
            required: set[Permission],
    ) -> bool:
        return required.issubset(
            self.granted
        )

    def missing_permissions(
            self,
            required: set[Permission],
    ) -> set[Permission]:
        return required - self.granted

    def requires_confirmation(
            self,
            required: set[Permission],
    ) -> bool:
        return bool(
            required
            & self.CONFIRMATION_PERMISSIONS
        )

    def authorize(
            self,
            required: set[Permission],
            confirmed: bool = False,
    ) -> None:

        missing = self.missing_permissions(
            required
        )

        if missing:
            names = ", ".join(
                permission.value
                for permission in sorted(
                    missing,
                    key=lambda item: item.value,
                )
            )

            raise PermissionError(
                f"Permessi mancanti: {names}"
            )

        if (
            self.requires_confirmation(required)
            and not confirmed
        ):
            raise PermissionError(
                "L'azione richiede una conferma esplicita."
            )

    def require(
            self,
            required: set[Permission],
    ) -> None:
        self.authorize(
            required=required,
            confirmed=False,
        )