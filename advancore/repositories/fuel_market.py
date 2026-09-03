from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from advancore.models import (
    FuelMarketRefreshState,
    FuelMarketSnapshot,
    RecurringServiceFuelRule,
)


class FuelMarketRepository:
    def __init__(self, session: Session):
        self._session = session

    def refresh_state(self) -> FuelMarketRefreshState:
        state = self._session.get(FuelMarketRefreshState, 1)
        if state is None:
            state = FuelMarketRefreshState(id=1, consecutive_failures=0)
            self._session.add(state)
            self._session.flush()
        return state

    def snapshot_on(self, observed_on: date) -> FuelMarketSnapshot | None:
        return self._session.scalars(
            select(FuelMarketSnapshot).where(
                FuelMarketSnapshot.observed_on == observed_on
            )
        ).one_or_none()

    def add_snapshot(self, snapshot: FuelMarketSnapshot) -> FuelMarketSnapshot:
        self._session.add(snapshot)
        self._session.flush()
        self._session.refresh(snapshot)
        return snapshot

    def latest_snapshot(self) -> FuelMarketSnapshot | None:
        return self._session.scalars(
            select(FuelMarketSnapshot).order_by(
                FuelMarketSnapshot.observed_on.desc(),
                FuelMarketSnapshot.id.desc(),
            )
        ).first()

    def recent_snapshots(self, limit: int = 31) -> Sequence[FuelMarketSnapshot]:
        return self._session.scalars(
            select(FuelMarketSnapshot)
            .order_by(
                FuelMarketSnapshot.observed_on.desc(),
                FuelMarketSnapshot.id.desc(),
            )
            .limit(limit)
        ).all()

    def add_rule(self, rule: RecurringServiceFuelRule) -> RecurringServiceFuelRule:
        self._session.add(rule)
        self._session.flush()
        self._session.refresh(rule)
        return rule

    def latest_rule(self, recurring_service_id: int) -> RecurringServiceFuelRule | None:
        return self._session.scalars(
            select(RecurringServiceFuelRule)
            .where(
                RecurringServiceFuelRule.recurring_service_id
                == recurring_service_id
            )
            .order_by(
                RecurringServiceFuelRule.effective_from.desc(),
                RecurringServiceFuelRule.id.desc(),
            )
        ).first()

    def applicable_rule(
        self, recurring_service_id: int, on_date: date
    ) -> RecurringServiceFuelRule | None:
        return self._session.scalars(
            select(RecurringServiceFuelRule)
            .where(
                RecurringServiceFuelRule.recurring_service_id
                == recurring_service_id,
                RecurringServiceFuelRule.effective_from <= on_date,
                (
                    RecurringServiceFuelRule.effective_to.is_(None)
                    | (RecurringServiceFuelRule.effective_to >= on_date)
                ),
            )
            .order_by(
                RecurringServiceFuelRule.effective_from.desc(),
                RecurringServiceFuelRule.id.desc(),
            )
        ).first()

    def list_rules(
        self, recurring_service_id: int
    ) -> Sequence[RecurringServiceFuelRule]:
        return self._session.scalars(
            select(RecurringServiceFuelRule)
            .where(
                RecurringServiceFuelRule.recurring_service_id
                == recurring_service_id
            )
            .order_by(
                RecurringServiceFuelRule.effective_from.desc(),
                RecurringServiceFuelRule.id.desc(),
            )
        ).all()

