"""SQL Operations on authentication users and groups.

.. classes::
    - `UserService` class to manage SQL entities for users and groups.

.. constants::
    - `INITIAL_GROUPS` tuple containing the initial group names.
    - `OIDC_PASSWORD_MARKER` string marker for OIDC users without a password.
    - `MAX_FAILED_LOGIN_ATTEMPTS` integer for the maximum allowed failed login attempts.
    - `FAILED_LOGIN_DELAY_SECONDS` integer for the delay in seconds after a failed login attempt.
    - `DUMMY_PASSWORD_HASH` string containing a dummy password hash for invalid users.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
import hashlib
from functools import wraps
from datetime import datetime, timezone
from time import sleep
from typing import Any, Callable, Concatenate, Literal, ParamSpec, TypeVar, cast

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, object_session, scoped_session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from api.common.db_objects.users import (
    AuthRuntimeState,
    Group,
    User,
    UserIdentity,
    UserGroup,
    UserLoginState,
    UserSession,
    UserPreferences,
)
from auth.models import ExternalUserIdentity, User as UniformUser, UserUpdate

INITIAL_GROUPS = ("ADMIN", "EDITOR", "VIEWER")
OIDC_PASSWORD_MARKER = "!oidc-no-password"
MAX_FAILED_LOGIN_ATTEMPTS = 6
FAILED_LOGIN_DELAY_SECONDS = 5
DUMMY_PASSWORD_HASH = generate_password_hash("ttl-lama-invalid-user-password")
LOGGER = logging.getLogger(__name__)
_Params = ParamSpec("_Params")
_Result = TypeVar("_Result")


def _rollback_on_error(
    operation: Callable[Concatenate[UserService, _Params], _Result],
) -> Callable[Concatenate[UserService, _Params], _Result]:
    """Retry once after an integrity conflict and roll back failed operations.

    :param operation: A user-service operation that manages a transaction.
    :type operation: Callable[Concatenate[UserService, _Params], _Result]
    :returns: A wrapped operation with rollback handling.
    :rtype: Callable[Concatenate[UserService, _Params], _Result]
    """

    @wraps(operation)
    def wrapped(
        self: UserService,
        *args: _Params.args,
        **kwargs: _Params.kwargs,
    ) -> _Result:
        """Run the operation and roll back the session when it fails.

        :param self: The user service instance.
        :type self: UserService
        :param args: Positional arguments passed to the operation.
        :type args: _Params.args
        :param kwargs: Keyword arguments passed to the operation.
        :type kwargs: _Params.kwargs
        :returns: The wrapped operation's result.
        :rtype: _Result
        :raises Exception: Re-raises an operation failure after rollback.
        """
        try:
            return operation(self, *args, **kwargs)
        except IntegrityError:
            self.db_session.rollback()
            try:
                return operation(self, *args, **kwargs)
            except Exception:
                self.db_session.rollback()
                raise
        except Exception:
            self.db_session.rollback()
            raise

    return wrapped

class UserService:
    """Manage SQL entities for users and groups without exposing them to the rest
    of the application.

    :param db_session: Scoped SQLAlchemy session for database interactions.
    :type db_session: scoped_session[Session]

    :raises SQLAlchemyError: If committing the session to the database fails.

    .. methods::
        - `ensure_initial_admin`: method to create the initial admin user and groups.
        - `ensure_login_states`: method to create missing login-state rows for existing users.
        - `ensure_groups`: method to create missing groups.
        - `authenticate`: method to verify user credentials and handle login attempts.
        - `get`: method to retrieve a user by their ID.
        - `create_user`: method to create a new user in the database.
        - `update_user`: method to update an existing user's information.
        - `reset_login_lock`: method to reset the login lock for a user.
        - `delete_user`: method to delete a user from the database.
        - `list_users`: method to list all users in the database.
        - `sync_external_user`: method to synchronize external users with the database.
        - `synchronize_auth_context`: method to synchronize the authentication context with
        the configured owner.

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(self, db_session: scoped_session[Session]) -> None:
        """Initialize the UserService with a database session.

        :param db_session: Scoped SQLAlchemy session for database interactions.
        :type db_session: scoped_session[Session]
        """
        self.db_session = db_session

    @_rollback_on_error
    def ensure_initial_admin(self, username: str, password: str) -> None:
        """Create the initial groups and the administrator if they are missing.

        :param username: The username for the initial admin user.
        :type username: str
        :param password: The password for the initial admin user.
        :type password: str
        :raises ValueError: If the username or password is empty.
        """
        if not username.strip():
            raise ValueError("ADMIN_USERNAME doit etre defini en mode internal")
        session = self.db_session()
        self._bootstrap_initial_admin(session, username, password)

    def _bootstrap_initial_admin(
        self,
        session: Session,
        username: str,
        password: str,
    ) -> None:
        """Ensure the administrator, reference groups, and login state exist.

        :param session: The active SQLAlchemy session.
        :type session: Session
        :param username: The configured administrator username.
        :type username: str
        :param password: The configured administrator password.
        :type password: str
        :returns: ``None``.
        :rtype: None
        :raises ValueError: If a new administrator has no password.
        """
        user = session.scalar(select(User).where(User.username == username))
        if user is None and not password:
            raise ValueError("ADMIN_PASSWORD est requis pour creer le compte initial")
        groups = self._ensure_groups(session)
        if user is None:
            user = self._create_initial_admin(session, username, password, groups)
        elif (
            session.get(UserIdentity, user.id) is None
            and user.hash_password != OIDC_PASSWORD_MARKER
        ):
            session.add(UserIdentity(user_id=user.id, auth_source="internal"))
        self._ensure_login_state(session, user.id)
        self._commit(session)

    @staticmethod
    def _create_initial_admin(
        session: Session,
        username: str,
        password: str,
        groups: list[Group],
    ) -> User:
        """Create the initial administrator and its internal identity record.

        :param session: The active SQLAlchemy session.
        :type session: Session
        :param username: The administrator username.
        :type username: str
        :param password: The administrator password to hash.
        :type password: str
        :param groups: Existing groups to associate with the administrator.
        :type groups: list[Group]
        :returns: The persisted administrator record.
        :rtype: User
        """
        admin_group = next(group for group in groups if group.name == "ADMIN")
        user = User(
            username=username,
            email=f"{username}@localhost",
            hash_password=generate_password_hash(password),
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )
        user.groups = [admin_group]
        session.add(user)
        UserService._flush(session)
        session.add(UserIdentity(user_id=user.id, auth_source="internal"))
        return user

    @_rollback_on_error
    def ensure_login_states(self) -> None:
        """Create missing login-state rows for users already stored in the database."""
        session = self.db_session()
        user_ids = session.scalars(select(User.id)).all()
        for user_id in user_ids:
            self._ensure_login_state(session, user_id)
        self._commit(session)

    @_rollback_on_error
    def ensure_groups(self) -> None:
        """Create the missing reference groups.

        :return: None
        :rtype: None

        :raises SQLAlchemyError: If committing the session to the database fails.
        """
        session = self.db_session()
        self._ensure_groups(session)
        self._commit(session)

    @_rollback_on_error
    def authenticate(self, username: str | None, password: str | None) -> UniformUser | None:
        """Verify the internal credentials and return a uniform identity.

        :param username: The username of the internal user, if provided.
        :type username: str | None
        :param password: The password of the internal user, if provided.
        :type password: str | None

        :return: The uniform identity if authentication is successful, otherwise None.
        :rtype: UniformUser | None
        """
        session = self.db_session()
        record = (
            session.scalar(select(User).where(User.username == username))
            if username
            else None
        )
        if record is None:
            self._check_dummy_password(password)
            sleep(FAILED_LOGIN_DELAY_SECONDS)
            return None

        if not record.enabled or record.hash_password.startswith("!"):
            self._check_dummy_password(password)
            sleep(FAILED_LOGIN_DELAY_SECONDS)
            return None

        self._ensure_login_state(session, record.id)
        is_locked = session.scalar(
            select(UserLoginState.locked).where(UserLoginState.user_id == record.id)
        )
        if is_locked is None or is_locked:
            self._check_dummy_password(password)
            sleep(FAILED_LOGIN_DELAY_SECONDS)
            return None

        password_valid = isinstance(password, str) and check_password_hash(
            record.hash_password,
            password,
        )
        if not password_valid:
            session.execute(
                update(UserLoginState)
                .where(
                    UserLoginState.user_id == record.id,
                    UserLoginState.locked.is_(False),
                )
                .values(
                    failed_attempts=UserLoginState.failed_attempts + 1,
                    locked=(
                        UserLoginState.failed_attempts + 1
                        >= MAX_FAILED_LOGIN_ATTEMPTS
                    ),
                )
                .execution_options(synchronize_session=False)
            )
            self._commit(session)
            sleep(FAILED_LOGIN_DELAY_SECONDS)
            return None

        reset_result = session.execute(
            update(UserLoginState)
            .where(
                UserLoginState.user_id == record.id,
                UserLoginState.locked.is_(False),
            )
            .values(failed_attempts=0)
            .execution_options(synchronize_session=False)
        )
        if cast(CursorResult[Any], reset_result).rowcount != 1:
            session.rollback()
            self._check_dummy_password(password)
            sleep(FAILED_LOGIN_DELAY_SECONDS)
            return None

        record.last_login = datetime.now(timezone.utc)
        self._commit(session)
        return self._to_user(record)

    def get(self, user_id: int) -> UniformUser | None:
        """Return the uniform identity associated with a SQL identifier.

        :param user_id: The SQL identifier of the user.
        :type user_id: int

        :return: The uniform identity if the user exists and is enabled, otherwise None.
        :rtype: UniformUser | None

        :raises SQLAlchemyError: If committing the session to the database fails.
        """
        record = self.db_session().get(User, user_id)
        if record is None or not record.enabled:
            LOGGER.debug("User not found or not enabled for user_id: %d", user_id)
            return None
        return self._to_user(record)

    @_rollback_on_error
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        group_names: list[str] | None = None,
    ) -> UniformUser:
        """Create an internal user with a hashed password.

        :param username: The username of the internal user.
        :type username: str
        :param email: The email of the internal user.
        :type email: str
        :param password: The password of the internal user.
        :type password: str
        :param group_names: The list of group names to assign to the user.
        :type group_names: list[str] | None

        :return: The uniform identity of the created user.
        :rtype: UniformUser

        :raises ValueError: If the username, email, or password is empty.
        :raises SQLAlchemyError: If committing the session to the database fails.
        """
        if (
            not username.strip()
            or len(username) > 50
            or not email.strip()
            or len(email) > 100
            or not password
        ):
            LOGGER.exception("Username, email, or password is empty. Cannot create user.")
            raise ValueError("Username, email, or password is empty. Cannot create user.")
        session = self.db_session()
        record = User(
            username=username,
            email=email,
            hash_password=generate_password_hash(password),
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )
        record.groups = self._get_groups(session, group_names or [])
        session.add(record)
        self._flush(session)
        session.add(UserIdentity(user_id=record.id, auth_source="internal"))
        self._ensure_login_state(session, record.id)
        self._commit(session)
        return self._to_user(record)

    @_rollback_on_error
    def update_user(
        self,
        changes: UserUpdate,
    ) -> UniformUser | None:
        """Update only the fields provided in the request.

        :param changes: User identifier and fields to update.
        :type changes: UserUpdate

        :return: The updated identity, or ``None`` if the account does not exist.
        :rtype: UniformUser | None

        :raises ValueError: If a provided field is invalid.
        :raises SQLAlchemyError: If the transaction fails.
        """
        session = self.db_session()
        record = session.get(User, changes.user_id)
        if record is None:
            return None
        source = self._auth_source(record)
        self._validate_user_update(source, changes)
        self._apply_user_update(session, record, changes)
        self._commit(session)
        return self._to_user(record, source)

    @staticmethod
    def _validate_user_update(
        source: Literal["internal", "external"],
        changes: UserUpdate,
    ) -> None:
        """Validate changes against the account source and field limits.

        :param source: Authentication source of the account.
        :type source: Literal["internal", "external"]
        :param changes: Fields submitted for validation.
        :type changes: UserUpdate
        :raises ValueError: If a field is invalid or the account is external.
        """
        if source == "external" and any(
            value is not None
            for value in (changes.username, changes.email, changes.password)
        ):
            raise ValueError("Une identité externe ne peut pas être convertie en compte interne")
        if changes.username is not None and (
            not changes.username.strip() or len(changes.username) > 50
        ):
            LOGGER.exception("Invalid username for user_id: %d", changes.user_id)
            raise ValueError("Le nom d'utilisateur est invalide")
        if changes.email is not None and (
            not changes.email.strip() or len(changes.email) > 100
        ):
            LOGGER.exception("Invalid email for user_id: %d", changes.user_id)
            raise ValueError("L'email est invalide")
        if changes.password is not None and not changes.password:
            LOGGER.exception("Password is empty for user_id: %d", changes.user_id)
            raise ValueError("Le mot de passe ne peut pas etre vide")

    @staticmethod
    def _apply_user_update(
        session: Session,
        record: User,
        changes: UserUpdate,
    ) -> None:
        """Apply validated changes and revoke sessions when required.

        :param session: Active SQLAlchemy session.
        :type session: Session
        :param record: User record to update.
        :type record: User
        :param changes: Fields to apply.
        :type changes: UserUpdate
        """
        if changes.username is not None:
            record.username = changes.username
        if changes.email is not None:
            record.email = changes.email
        if changes.password is not None:
            record.hash_password = generate_password_hash(changes.password)
            session.execute(
                delete(UserSession).where(UserSession.user_id == changes.user_id)
            )
        if changes.group_names is not None:
            record.groups = UserService._get_groups(session, changes.group_names)
        if changes.enabled is not None:
            record.enabled = changes.enabled
            if not changes.enabled:
                session.execute(
                    delete(UserSession).where(UserSession.user_id == changes.user_id)
                )

    @_rollback_on_error
    def reset_login_lock(self, user_id: int) -> bool:
        """Reset the persistent login lock for a user.

        This service method is intended for a future administrator-only route.

        :param user_id: The identifier of the user to unlock.
        :type user_id: int

        :return: Whether the user exists.
        :rtype: bool
        """
        session = self.db_session()
        if session.get(User, user_id) is None:
            return False
        state = session.get(UserLoginState, user_id)
        if state is None:
            self._ensure_login_state(session, user_id)
            self._commit(session)
            return True
        state.failed_attempts = 0
        state.locked = False
        self._commit(session)
        return True

    @_rollback_on_error
    def delete_user(self, user_id: int) -> bool:
        """Delete a user and their persistent sessions.

        :param user_id: The SQL identifier of the user to delete.
        :type user_id: int

        :return: True if the user and its authentication records were deleted,
        False if the user does not exist.
        :rtype: bool

        :raises SQLAlchemyError: If committing the session to the database fails.
        """
        session = self.db_session()
        record = session.get(User, user_id)
        if record is None:
            return False
        session.execute(delete(UserSession).where(UserSession.user_id == user_id))
        session.execute(delete(UserLoginState).where(UserLoginState.user_id == user_id))
        session.execute(delete(UserGroup).where(UserGroup.user_id == user_id))
        session.execute(delete(UserIdentity).where(UserIdentity.user_id == user_id))
        session.execute(
            delete(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        session.delete(record)
        self._commit(session)
        return True

    def list_users(self) -> list[UniformUser]:
        """Returns the active users as uniform identities.

        :return: A list of uniform identities representing the active users.
        :rtype: list[UniformUser]
        """
        records = self.db_session().scalars(
            select(User).where(User.enabled.is_(True)).order_by(User.id)
        )
        return [self._to_user(record) for record in records]

    @_rollback_on_error
    def sync_external_user(self, issuer: str, claims: dict[str, object]) -> UniformUser:
        """Persist an OIDC identity and synchronize its authorized groups.

        :param issuer: The OIDC issuer identifier.
        :type issuer: str

        :param claims: The OIDC claims containing user information and groups.
        :type claims: dict[str, object]

        :return: The synchronized user as a uniform identity.
        :rtype: UniformUser

        :raises ValueError: If the OIDC response does not contain a valid subject.
        """
        identity_data = self._external_identity(issuer, claims)
        session = self.db_session()
        record = self._synchronize_external_record(session, identity_data)
        self._commit(session)
        return self._to_user(record, "external")

    @staticmethod
    def _external_identity(
        issuer: str,
        claims: dict[str, object],
    ) -> ExternalUserIdentity:
        """Validate OIDC claims and derive stable local identity fields.

        :param issuer: The configured OIDC issuer.
        :type issuer: str
        :param claims: User claims returned by the identity provider.
        :type claims: dict[str, object]

        :returns: External identity fields normalized for local persistence.
        :rtype: ExternalUserIdentity

        :raises ValueError: If the issuer or subject is invalid.
        """
        subject = claims.get("sub")
        if (
            not isinstance(subject, str)
            or not subject
            or len(subject) > 255
            or not issuer
            or len(issuer) > 255
        ):
            LOGGER.warning("OIDC response does not contain a valid subject")
            raise ValueError("La reponse OIDC ne contient pas de sujet valide")
        identity = hashlib.sha256(f"{issuer}|{subject}".encode("utf-8")).hexdigest()
        username = f"oidc_{identity[:40]}"
        email = f"{identity}@oidc.invalid"
        raw_groups = claims.get("groups", [])
        requested_groups: set[str] = set()
        if isinstance(raw_groups, list):
            for group in cast(list[object], raw_groups):
                if isinstance(group, str):
                    requested_groups.add(group)
        group_names = frozenset(requested_groups.intersection(INITIAL_GROUPS))
        return ExternalUserIdentity(issuer, subject, username, email, group_names)

    def _synchronize_external_record(
        self,
        session: Session,
        external_identity: ExternalUserIdentity,
    ) -> User:
        """Create or retrieve the local user associated with an external identity.

        :param session: Active SQLAlchemy session.
        :type session: Session
        :param external_identity: Normalized external identity data.
        :type external_identity: ExternalUserIdentity
        :returns: The synchronized local user record.
        :rtype: User
        :raises ValueError: If an existing account conflicts with the identity.
        """
        record = session.scalar(
            select(User).where(User.username == external_identity.username)
        )
        identity = session.get(UserIdentity, record.id) if record is not None else None
        self._validate_external_account(
            record,
            identity,
            external_identity.issuer,
            external_identity.subject,
        )
        groups = self._ensure_groups(session)
        if record is None:
            record = User(
                username=external_identity.username,
                email=external_identity.email,
                hash_password=OIDC_PASSWORD_MARKER,
                enabled=True,
                created_at=datetime.now(timezone.utc),
            )
            session.add(record)
            self._flush(session)
        if identity is None:
            session.add(
                UserIdentity(
                    user_id=record.id,
                    auth_source="external",
                    issuer=external_identity.issuer,
                    subject=external_identity.subject,
                )
            )
        self._ensure_login_state(session, record.id)
        record.groups = [
            group for group in groups if group.name in external_identity.group_names
        ]
        return record

    @staticmethod
    def _validate_external_account(
        record: User | None,
        identity: UserIdentity | None,
        issuer: str,
        subject: str,
    ) -> None:
        """Reject disabled, internal, or mismatched records for an OIDC identity.

        :param record: Existing user record, if one matches the generated username.
        :type record: User | None
        :param identity: Existing identity provenance record, if present.
        :type identity: UserIdentity | None
        :param issuer: The identity provider issuer.
        :type issuer: str
        :param subject: The subject identifier from the provider.
        :type subject: str
        :returns: ``None``.
        :rtype: None
        :raises ValueError: If the account is disabled or belongs to another identity.
        """
        if record is None:
            return
        if not record.enabled:
            raise ValueError("Le compte externe est désactivé")
        if identity is None:
            if record.hash_password != OIDC_PASSWORD_MARKER:
                raise ValueError("Le compte existant n'est pas une identité externe")
            return
        if identity.auth_source != "external":
            raise ValueError("L'identité externe ne correspond pas au compte existant")
        if identity.issuer is None and identity.subject is None:
            identity.issuer = issuer
            identity.subject = subject
        elif identity.issuer != issuer or identity.subject != subject:
            raise ValueError("L'identité externe ne correspond pas au compte existant")

    @_rollback_on_error
    def synchronize_auth_context(
        self,
        mode: Literal["internal", "external"],
        issuer: str | None = None,
    ) -> bool:
        """Reject a change of authentication owner until data is migrated explicitly.

        :param mode: The authentication mode to synchronize with.
        :type mode: Literal["internal", "external"]
        :param issuer: The issuer of the authentication token, if applicable.
        :type issuer: str | None
        :return: False when the stored authentication context matches.
        :rtype: bool
        :raises ValueError: If the authentication mode or issuer changes.
        """
        session = self.db_session()
        state = session.get(AuthRuntimeState, 1)
        normalized_issuer = issuer if mode == "external" and issuer else None
        if state is None:
            session.add(
                AuthRuntimeState(id=1, auth_mode=mode, issuer=normalized_issuer)
            )
            self._commit(session)
            return False
        if state.auth_mode == mode and state.issuer == normalized_issuer:
            return False
        raise ValueError(
            "Le mode ou l’émetteur d’authentification a changé; "
            "une migration explicite est requise pour préserver les comptes."
        )

    @_rollback_on_error
    def ensure_identity_records(self) -> None:
        """Persist provenance for accounts created before identity tracking.

        :raises SQLAlchemyError: If there is an error during database operations.
        """
        session = self.db_session()
        records = session.scalars(select(User)).all()
        for record in records:
            if session.get(UserIdentity, record.id) is not None:
                continue
            is_external = record.hash_password == OIDC_PASSWORD_MARKER
            session.add(
                UserIdentity(
                    user_id=record.id,
                    auth_source="external" if is_external else "internal",
                )
            )
        self._commit(session)

    @staticmethod
    def _ensure_groups(session: Session) -> list[Group]:
        """Ensure that all initial groups exist in the database.

        :param session: The SQLAlchemy session to use for database operations.
        :type session: Session

        :return: A list of all initial groups.
        :rtype: list[Group]
        """
        groups: list[Group] = []
        for name in INITIAL_GROUPS:
            group = session.scalar(select(Group).where(Group.name == name))
            if group is None:
                group = Group(name=name, description=f"TTL-LAMa {name.lower()} role")
                session.add(group)
            groups.append(group)
        UserService._flush(session)
        return groups

    @staticmethod
    def _ensure_login_state(session: Session, user_id: int) -> UserLoginState:
        """Return the user's persisted login state, creating it when absent.
        
        :param session: The SQLAlchemy session to use for database operations.
        :type session: Session
        :param user_id: The ID of the user whose login state is to be retrieved.
        :type user_id: int

        :return: The user's persisted login state.
        :rtype: UserLoginState

        :raises SQLAlchemyError: If there is an error during database operations.
        """
        state = session.get(UserLoginState, user_id)
        if state is None:
            state = UserLoginState(user_id=user_id)
            session.add(state)
            UserService._flush(session)
        return state

    @staticmethod
    def _check_dummy_password(password: str | None) -> None:
        """Perform a password-hash check when no usable account hash is available.

        :param password: The password to check against the dummy hash.
        :type password: str | None

        :raises ValueError: If the password does not match the dummy hash.
        """
        check_password_hash(
            DUMMY_PASSWORD_HASH,
            password if isinstance(password, str) else "",
        )

    @staticmethod
    def _flush(session: Session) -> None:
        """Flush pending changes and roll back if a constraint fails.
        
        :param session: The SQLAlchemy session to use for database operations.
        :type session: Session

        :raises SQLAlchemyError: If there is an error during database operations.
        """
        try:
            session.flush()
        except SQLAlchemyError:
            session.rollback()
            raise

    @staticmethod
    def _get_groups(session: Session, names: list[str]) -> list[Group]:
        """Retrieve groups by their names from the database.

        :param session: The SQLAlchemy session to use for database operations.
        :type session: Session
        :param names: A list of group names to retrieve.
        :type names: list[str]

        :return: A list of groups matching the provided names.
        :rtype: list[Group]

        :raises ValueError: If any of the requested groups do not exist.
        :raises SQLAlchemyError: If there is an error during database operations.
        """
        if not names:
            return []
        groups = list(session.scalars(select(Group).where(Group.name.in_(set(names)))))
        missing = set(names).difference(group.name for group in groups)
        if missing:
            raise ValueError(f"Groupes inconnus : {', '.join(sorted(missing))}")
        return groups

    @staticmethod
    def _to_user(
        record: User,
        source: Literal["internal", "external"] | None = None,
    ) -> UniformUser:
        """Convert a database user record to a uniform user identity.

        :param record: The database user record to convert.
        :type record: User
        :param source: The authentication source of the user, either "internal" or "external".
        :type source: Literal["internal", "external"]

        :return: The user as a uniform identity.
        :rtype: UniformUser
        """
        session = object_session(record)
        if source is None:
            source = UserService._auth_source(record)
        groups = []
        if session is not None:
            groups = list(
                session.scalars(
                    select(Group.name)
                    .join(UserGroup, UserGroup.group_id == Group.id)
                    .where(UserGroup.user_id == record.id, UserGroup.activated.is_(True))
                ).all()
            )
        return UniformUser(
            id=record.id,
            username=record.username,
            groups=groups,
            auth_source=source,
        )

    @staticmethod
    def _auth_source(record: User) -> Literal["internal", "external"]:
        """Return the persisted provenance, including a legacy OIDC fallback.

        :param record: The database user record to check.
        :type record: User

        :return: The authentication source of the user, either "internal" or "external".
        :rtype: Literal["internal", "external"]
        """
        session = object_session(record)
        identity = session.get(UserIdentity, record.id) if session is not None else None
        if identity is not None:
            return "external" if identity.auth_source == "external" else "internal"
        return "external" if record.hash_password == OIDC_PASSWORD_MARKER else "internal"

    @staticmethod
    def _commit(session: Session) -> None:
        """Commit the current transaction in the database session.

        :param session: The SQLAlchemy session to use for database operations.
        :type session: Session

        :raises SQLAlchemyError: If the commit fails, the transaction is rolled back and the
        exception is raised.
        """
        try:
            session.commit()
        except SQLAlchemyError as e:
            LOGGER.exception("Failed to commit the transaction: %s", e)
            session.rollback()
            raise
