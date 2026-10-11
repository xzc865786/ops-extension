"""Migration 009 against real PostgreSQL; use only a disposable PostgreSQL URL."""
import base64
import os

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.accounts import service
from app.accounts.schemas import AccountCreate, Reveal, VersionOnly
from app.config import get_settings
from app.db.models.account import AccountEvent, AccountRecord
from app.db.models.user import ExtensionUser
from app.deps import CurrentUser
from tests.test_postgres_ledger import migrate, pg  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.getenv('OPS_TEST_POSTGRES_URL'), reason='no disposable PostgreSQL test URL')


def test_009_upgrade_constraints_and_downgrade(pg, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), 'account_vault_key', base64.b64encode(os.urandom(32)).decode())
    migrate(pg, '008')
    assert 'account_records' not in inspect(pg).get_table_names()
    migrate(pg, 'head')
    factory = sessionmaker(bind=pg)
    with factory() as db:
        user = ExtensionUser(sub2api_user_id=9301, sub2api_role='admin', username_snapshot='迁移测试')
        db.add(user)
        db.commit()
        actor = CurrentUser(user.id, 9301, '迁移测试', None, 'admin')
        row = service.create(db, actor, AccountCreate(client='Claude', login='a@example.com', password='pw'))
        assert service.reveal(db, actor, row.id, Reveal(field='password')) == 'pw'
        assert [e.event_type for e in db.scalars(select(AccountEvent).order_by(AccountEvent.id))] == ['CREATED', 'SECRET_VIEWED']
        # The database itself rejects a second live account with the same identity.
        db.add(AccountRecord(client='claude', login='A@example.com', identity=row.identity, active_identity=row.identity,
                             status='STANDBY', archived=False, version=1, created_by=user.id, updated_by=user.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        service.set_archived(db, actor, row.id, VersionOnly(version=row.version), True)
        again = service.create(db, actor, AccountCreate(client='claude', login='A@example.com'))
        assert again.id != row.id
    migrate(pg, '008', downgrade=True)
    assert 'account_records' not in inspect(pg).get_table_names()
