"""AdvanCore persistence repositories.

Repositories contain SQLAlchemy queries and persistence operations only.
Business orchestration belongs in services; presentation belongs in pages.
"""

from advancore.repositories.activity import ActivityLogRepository
from advancore.repositories.customer import CustomerRepository
from advancore.repositories.driver import DriverRepository
from advancore.repositories.fuel_entry import FuelEntryRepository
from advancore.repositories.financial_entry import FinancialEntryRepository
from advancore.repositories.knowledge import KnowledgeItemRepository
from advancore.repositories.legal_entity import LegalEntityRepository
from advancore.repositories.project import ProjectRepository
from advancore.repositories.route import RouteRepository
from advancore.repositories.setting import SystemSettingRepository
from advancore.repositories.vehicle import VehicleRepository
from advancore.repositories.trip import TripRepository
from advancore.repositories.trip_assignment import TripAssignmentRepository

__all__ = [
    "ActivityLogRepository",
    "CustomerRepository",
    "DriverRepository",
    "FuelEntryRepository",
    "FinancialEntryRepository",
    "KnowledgeItemRepository",
    "LegalEntityRepository",
    "ProjectRepository",
    "RouteRepository",
    "SystemSettingRepository",
    "VehicleRepository",
    "TripRepository",
    "TripAssignmentRepository",
]
