from advancore.models.activity import ActivityLog
from advancore.models.customer import Customer
from advancore.models.driver import Driver
from advancore.models.fuel_entry import FuelEntry
from advancore.models.financial_entry import FinancialEntry
from advancore.models.base import Base
from advancore.models.knowledge import KnowledgeItem
from advancore.models.project import Project
from advancore.models.route import Route
from advancore.models.setting import SystemSetting
from advancore.models.vehicle import Vehicle
from advancore.models.trip import Trip
from advancore.models.trip_assignment import TripAssignment

__all__ = [
    "Base",
    "Customer",
    "Driver",
    "FuelEntry",
    "FinancialEntry",
    "Project",
    "Route",
    "KnowledgeItem",
    "ActivityLog",
    "SystemSetting",
    "Vehicle",
    "Trip",
    "TripAssignment",
]
