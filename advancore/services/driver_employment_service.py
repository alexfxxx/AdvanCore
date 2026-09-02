from collections.abc import Sequence
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from advancore.models import DriverEmploymentRecord
from advancore.repositories import DriverEmploymentRepository
from advancore.services.activity_service import ActivityLogService


WORKER_CATEGORIES = ("local_pr", "foreign_levy")
EMPLOYMENT_STATUSES = ("active", "inactive")


class DriverEmploymentValidationError(ValueError):
    pass


class DriverEmploymentConflictError(ValueError):
    pass


class DriverEmploymentNotFoundError(ValueError):
    pass


class DriverEmploymentService:
    def __init__(
        self,
        repository: DriverEmploymentRepository,
        activity_service: ActivityLogService | None = None,
    ):
        self._repo = repository
        self._activity = activity_service

    @staticmethod
    def _money(value, label: str, *, required: bool) -> Decimal | None:
        if value is None and not required:
            return None
        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise DriverEmploymentValidationError(f"{label} must be a valid amount.") from exc
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise DriverEmploymentValidationError(
                f"{label} must be non-negative with no more than two decimal places."
            )
        return amount

    def create_record(
        self,
        driver_id: int,
        effective_month: date,
        worker_category: str,
        basic_salary: Decimal,
        employer_cpf_amount: Decimal | None,
        monthly_levy_amount: Decimal | None,
        monthly_allowance: Decimal | None,
        employment_status: str,
    ) -> DriverEmploymentRecord:
        if not isinstance(driver_id, int) or isinstance(driver_id, bool) or driver_id <= 0:
            raise DriverEmploymentValidationError("Driver identifier is invalid.")
        if self._repo.driver(driver_id) is None:
            raise DriverEmploymentNotFoundError("The selected driver could not be found.")
        if not isinstance(effective_month, date) or effective_month.day != 1:
            raise DriverEmploymentValidationError(
                "Effective month must be the first calendar day of a month."
            )
        if worker_category not in WORKER_CATEGORIES:
            raise DriverEmploymentValidationError("Worker category is invalid.")
        if employment_status not in EMPLOYMENT_STATUSES:
            raise DriverEmploymentValidationError("Employment status is invalid.")

        salary = self._money(basic_salary, "Basic salary", required=True)
        cpf = self._money(employer_cpf_amount, "Employer CPF amount", required=False)
        levy = self._money(monthly_levy_amount, "Monthly levy amount", required=False)
        allowance = self._money(monthly_allowance, "Monthly allowance", required=False)
        if worker_category == "local_pr" and levy is not None:
            raise DriverEmploymentValidationError(
                "Local/PR records cannot contain a foreign-worker levy amount."
            )
        if worker_category == "foreign_levy" and cpf is not None:
            raise DriverEmploymentValidationError(
                "Foreign-worker levy records cannot contain an employer CPF amount."
            )
        if self._repo.get_by_driver_and_month(driver_id, effective_month):
            raise DriverEmploymentConflictError(
                "That driver already has an employment record for this effective month."
            )

        try:
            saved = self._repo.add(
                DriverEmploymentRecord(
                    driver_id=driver_id,
                    effective_month=effective_month,
                    worker_category=worker_category,
                    basic_salary=salary,
                    employer_cpf_amount=cpf,
                    monthly_levy_amount=levy,
                    monthly_allowance=allowance,
                    employment_status=employment_status,
                )
            )
        except IntegrityError as exc:
            raise DriverEmploymentConflictError(
                "That driver already has an employment record for this effective month."
            ) from exc
        if self._activity:
            self._activity.record_activity(
                "driver_employment_record_created", "driver_employment_record", saved.id
            )
        return saved

    def list_by_driver(self, driver_id: int) -> Sequence[DriverEmploymentRecord]:
        if self._repo.driver(driver_id) is None:
            raise DriverEmploymentNotFoundError("The selected driver could not be found.")
        return self._repo.list_by_driver(driver_id)
