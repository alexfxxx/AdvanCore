"""AdvanCore persistence repositories.

Repositories contain SQLAlchemy queries and persistence operations only.
Business orchestration belongs in services; presentation belongs in pages.
"""

from advancore.repositories.activity import ActivityLogRepository
from advancore.repositories.driver import DriverRepository
from advancore.repositories.knowledge import KnowledgeItemRepository
from advancore.repositories.project import ProjectRepository
from advancore.repositories.setting import SystemSettingRepository
from advancore.repositories.vehicle import VehicleRepository

__all__ = [
    "ActivityLogRepository",
    "DriverRepository",
    "KnowledgeItemRepository",
    "ProjectRepository",
    "SystemSettingRepository",
    "VehicleRepository",
]
