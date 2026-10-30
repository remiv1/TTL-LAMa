"""Profile policies and assignments, reusable by global configuration.

.. classes::
    - `ProfileRepository`: Manage profiles and policies in the caller's transaction.

.. author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from api.common.db_objects.devices import Device
from api.common.db_objects.leases import Lease
from api.common.db_objects.profiles import Profile, ProfileUser
from api.common.db_objects.profile_policy import ProfilePolicy
from api.common.db_objects.users import User
from api.config.c_profiles import AccessProfile, AccessProfiles
from .base import ConflictError, Repository
from .leases import LeaseRepository, utcnow


class ProfileRepository(Repository[Profile]):
    """Manage profiles and policies in the caller's transaction.
    
    :param session: The SQLAlchemy session to use for database operations.
    :type session: Session

    .. author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, Profile)

    def find(self, *, user: str | None = None, device: int | None = None,
             lease: int | None = None) -> list[Profile]:
        """Filter by active assignments or historical leases.
        
        :param user: Filter by user ID.
        :type user: str | None
        :param device: Filter by device ID.
        :type device: int | None
        :param lease: Filter by lease ID.
        :type lease: int | None
        :return: A list of profiles matching the specified filters.
        :rtype: list[Profile]
        """
        conditions: list[ColumnElement[bool]] = []
        if user is not None:
            conditions.append(Profile.id.in_(select(ProfileUser.profile_id).where(
                ProfileUser.user_id == user, ProfileUser.revoked_at.is_(None)
            )))
        if device is not None or lease is not None:
            related = select(ProfileUser.profile_id).join(Lease)
            if device is not None:
                # Device ownership alone does not grant a profile.
                related = related.join(Device).where(Device.id == device)
            if lease is not None:
                related = related.where(Lease.id == lease)
            conditions.append(Profile.id.in_(related))
        return self.list(*conditions)

    def policy(self, profile: Profile) -> AccessProfile | None:
        """Read a policy, explicitly reporting legacy records with no policy.
        
        :param profile: The profile to read the policy for.
        :type profile: Profile
        :return: The access policy for the profile, or None if no policy exists.
        :rtype: AccessProfile | None
        """
        stored = self.session.get(ProfilePolicy, profile.id)
        if stored is None:
            return None
        return AccessProfile.model_validate({
            "default_duration": stored.default_duration,
            "maximum_duration": stored.maximum_duration,
            "networks": stored.networks,
        })

    def set_policy(self, profile: Profile, policy: AccessProfile) -> None:
        """Replace a validated policy and revoke leases based on the old policy.
        
        :param profile: The profile to update the policy for.
        :type profile: Profile
        :param policy: The new access policy to set.
        :type policy: AccessProfile
        """
        stored = self.session.get(ProfilePolicy, profile.id)
        if self.policy(profile) == policy:
            return
        if stored is None:
            stored = ProfilePolicy(profile_id=profile.id)
            self.session.add(stored)
        stored.default_duration = policy.default_duration
        stored.maximum_duration = policy.maximum_duration
        stored.networks = [str(network) for network in policy.networks]
        self.revoke_leases(profile)

    def ensure_name(self, name: str, identifier: int | None = None) -> None:
        """Reject ambiguous names, including logically deleted profiles.
        
        :param name: The name to check for uniqueness.
        :type name: str
        :param identifier: The ID of the profile to exclude from the check (useful for updates).
        :type identifier: int | None
        :raises ConflictError: If a profile with the same name already exists.
        """
        existing = self.session.scalar(select(Profile).where(Profile.name == name))
        if existing is not None and existing.id != identifier:
            raise ConflictError("Profile name already exists")

    def create(self, name: str, policy: AccessProfile) -> Profile:
        """Create a named profile with its policy.
        
        :param name: The name of the profile to create.
        :type name: str
        :param policy: The access policy to associate with the profile.
        :type policy: AccessProfile
        :return: The newly created profile.
        :rtype: Profile
        """
        self.ensure_name(name)
        profile = self.add(Profile(name=name))
        self.set_policy(profile, policy)
        return profile

    def revoke_leases(self, profile: Profile) -> None:
        """Revoke access based on this profile.
        
        :param profile: The profile whose leases should be revoked.
        :type profile: Profile
        """
        LeaseRepository(self.session).revoke_matching(Lease.profile_user_id.in_(
            select(ProfileUser.id).where(ProfileUser.profile_id == profile.id)
        ))

    def delete(self, profile: Profile) -> Profile:
        """Revoke a profile, its assignments and leases without erasing history.
        
        :param profile: The profile to revoke.
        :type profile: Profile
        :return: The revoked profile.
        :rtype: Profile
        """
        if profile.revoked_at is None:
            profile.revoked_at = utcnow()
        self.revoke_leases(profile)
        self.session.execute(update(ProfileUser).where(
            ProfileUser.profile_id == profile.id, ProfileUser.revoked_at.is_(None)
        ).values(revoked_at=utcnow()))
        return profile

    def assign(self, user: User, profile: Profile) -> ProfileUser:
        """Assign idempotently, preserving previously revoked assignments.
        
        :param user: The user to assign the profile to.
        :type user: User
        :param profile: The profile to assign to the user.
        :type profile: Profile
        :return: The created or existing profile assignment.
        :rtype: ProfileUser
        """
        if not user.enabled or profile.revoked_at is not None:
            raise ConflictError("Cannot assign a disabled user or revoked profile")
        assignment = self.session.scalar(select(ProfileUser).where(
            ProfileUser.user_id == str(user.id), ProfileUser.profile_id == profile.id,
            ProfileUser.revoked_at.is_(None)
        ).with_for_update())
        if assignment is None:
            assignment = ProfileUser(user_id=str(user.id), profile_id=profile.id)
            self.session.add(assignment)
            self.session.flush()
        return assignment

    def unassign(self, user: User, profile: Profile) -> None:
        """Revoke all current assignments and their leases idempotently.
        
        :param user: The user whose profile assignments should be revoked.
        :type user: User
        :param profile: The profile to unassign from the user.
        :type profile: Profile
        """
        assignments = select(ProfileUser.id).where(
            ProfileUser.user_id == str(user.id), ProfileUser.profile_id == profile.id
        )
        LeaseRepository(self.session).revoke_matching(Lease.profile_user_id.in_(assignments))
        self.session.execute(update(ProfileUser).where(
            ProfileUser.user_id == str(user.id), ProfileUser.profile_id == profile.id,
            ProfileUser.revoked_at.is_(None)
        ).values(revoked_at=utcnow()))

    def import_missing(self, profiles: AccessProfiles) -> None:
        """Seed YAML policies once; persisted administrative edits take precedence.
        
        :param profiles: The access profiles to import.
        :type profiles: AccessProfiles
        """
        for name, policy in profiles.profiles.items():
            matches = self.list(Profile.name == name)
            if len(matches) > 1:
                raise ConflictError(f"Ambiguous profile name: {name}")
            if not matches:
                self.create(name, policy)
            elif self.policy(matches[0]) is None and matches[0].revoked_at is None:
                self.set_policy(matches[0], policy)
        self.session.flush()
