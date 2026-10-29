from __future__ import annotations

from geodata_catalog.exceptions import ConfigurationException
from geodata_catalog.metadata.settings_manager import SettingsManager
from geodata_catalog.models.user_profile import UserProfile


class ProfileRepository:
    """Local, freely selectable work modes; not authentication or authorization."""

    SETTINGS_KEY = "user_profiles"

    def __init__(self, settings: SettingsManager) -> None:
        self._settings = settings

    def load(self) -> tuple[list[UserProfile], str]:
        payload = self._settings.get_json(self.SETTINGS_KEY, None)
        if payload is None:
            profiles = [UserProfile("developer", "Developer", "developer"), UserProfile("user", "User")]
            self.save(profiles, "user")
            return profiles, "user"
        if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), list):
            raise ConfigurationException("Invalid user profile configuration.")
        profiles: list[UserProfile] = []
        for item in payload["profiles"]:
            if not isinstance(item, dict):
                raise ConfigurationException("Each profile must be an object.")
            visible = item.get("visible_layer_ids")
            if visible is not None and (
                not isinstance(visible, list) or not all(isinstance(key, str) and key for key in visible)
            ):
                raise ConfigurationException("Profile visibility must be null or a list of layer IDs.")
            if not all(isinstance(item.get(key), str) and item[key].strip() for key in ("id", "name", "role")):
                raise ConfigurationException("Profile ID, name and role are required.")
            profiles.append(UserProfile(item["id"], item["name"], item["role"], visible))
        active_id = payload.get("active_profile_id")
        self._validate(profiles, active_id)
        return profiles, active_id

    def save(self, profiles: list[UserProfile], active_id: str) -> None:
        self._validate(profiles, active_id)
        self._settings.set_json(self.SETTINGS_KEY, {
            "active_profile_id": active_id,
            "profiles": [profile.to_dict() for profile in profiles],
        })

    @staticmethod
    def _validate(profiles: list[UserProfile], active_id: str) -> None:
        if not profiles or len({profile.id for profile in profiles}) != len(profiles):
            raise ConfigurationException("Profiles must have unique IDs.")
        if any(not profile.id.strip() or not profile.name.strip() or profile.role not in ("user", "developer")
               for profile in profiles):
            raise ConfigurationException("Each profile needs an ID, name and a valid role.")
        if len({profile.name.casefold() for profile in profiles}) != len(profiles):
            raise ConfigurationException("Profile names must be unique.")
        if any(profile.visible_layer_ids is not None and (
            not isinstance(profile.visible_layer_ids, list)
            or not all(isinstance(key, str) and key for key in profile.visible_layer_ids)
        ) for profile in profiles):
            raise ConfigurationException("Profile visibility must be null or a list of layer IDs.")
        if not any(profile.is_developer for profile in profiles):
            raise ConfigurationException("At least one developer work profile is required.")
        if active_id not in {profile.id for profile in profiles}:
            raise ConfigurationException("The selected work profile does not exist.")
