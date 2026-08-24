"""System setting repository for bounded application preferences."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import SystemSetting


class SystemSettingRepository:
    """Persistence operations for existing SystemSetting records."""

    def __init__(self, session: Session):
        self._session = session

    def get_by_key(self, key: str) -> SystemSetting | None:
        return self._session.scalar(
            select(SystemSetting).where(SystemSetting.key == key)
        )

    def add(self, setting: SystemSetting) -> SystemSetting:
        self._session.add(setting)
        self._session.flush()
        self._session.refresh(setting)
        return setting

    def save(self, setting: SystemSetting) -> SystemSetting:
        self._session.flush()
        self._session.refresh(setting)
        return setting
