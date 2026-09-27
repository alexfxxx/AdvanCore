"""Only run against the disposable GitHub Actions PostgreSQL service."""
import os
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

pytestmark=pytest.mark.skipif(os.getenv('GITHUB_ACTIONS')!='true',reason='CI disposable PostgreSQL only; never reset local business data')

def test_fuel_chain_preserves_existing_facts():
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root/'alembic.ini'))
    command.downgrade(config,'base')
    command.upgrade(config,'fae192assign')
    engine=create_engine(os.environ['DATABASE_URL'])
    with engine.begin() as c:
        vehicle=c.execute(text("INSERT INTO vehicles (registration_number,status,created_at,updated_at) VALUES ('TEST-BUS','active',now(),now()) RETURNING id")).scalar_one()
        c.execute(text("INSERT INTO fuel_entries (vehicle_id,recorded_on,litres,total_cost,created_at,updated_at) VALUES (:v,'2026-01-01',10,20,now(),now())"),{'v':vehicle})
    command.upgrade(config,'head')
    with engine.connect() as c:
        assert c.execute(text('SELECT product,litres,total_cost FROM fuel_entries')).one()==('diesel',10,20)
        assert c.execute(text('SELECT count(*) FROM diesel_transactions')).scalar_one()==0
    assert {'diesel_rates','diesel_transactions','diesel_settings'} <= set(inspect(engine).get_table_names())
    engine.dispose()
