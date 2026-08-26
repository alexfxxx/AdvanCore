"""AdvanCore persistence repositories.

Repositories contain SQLAlchemy queries and persistence operations only.
Business orchestration belongs in services; presentation belongs in pages.
"""

from advancore.repositories.activity import ActivityLogRepository
from advancore.repositories.customer import CustomerRepository
from advancore.repositories.driver import DriverRepository
from advancore.repositories.knowledge import KnowledgeItemRepository
from advancore.repositories.project import ProjectRepository
from advancore.repositories.route import RouteRepository
from advancore.repositories.setting import SystemSettingRepository
from advancore.repositories.vehicle import VehicleRepository
from advancore.repositories.trip import TripRepository

__all__ = [
    "ActivityLogRepository",
    "CustomerRepository",
    "DriverRepository",
    "KnowledgeItemRepository",
    "ProjectRepository",
    "RouteRepository",
    "SystemSettingRepository",
    "VehicleRepository",
    "TripRepository",
]
