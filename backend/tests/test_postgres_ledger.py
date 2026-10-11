"""Real migration/row-lock verification; use only a disposable PostgreSQL URL."""
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text, func, inspect
from sqlalchemy.orm import sessionmaker

from app.common.errors import AppError
from app.db.models.user import ExtensionUser
from app.db.models.expense import ExpenseClaim, ExpensePayment, ExpenseAttachment
from app.db.models.ledger import ExpenseRecord, Reimbursement, ReimbursementItem, LedgerEvent
from app.deps import CurrentUser
from app.ledger import service
from app.ledger.schemas import RecordCreate, RecordUpdate, BatchInput, HistoryConfirm, VersionReason

pytestmark = pytest.mark.skipif(not os.getenv('OPS_TEST_POSTGRES_URL'), reason='no disposable PostgreSQL test URL')


def migrate(engine, revision, *, downgrade=False):
    cfg=Config(str(Path(__file__).parents[1]/'alembic.ini'))
    cfg.set_main_option('script_location',str(Path(__file__).parents[1]/'alembic'))
    with engine.begin() as connection:
        cfg.attributes['connection']=connection
        (command.downgrade if downgrade else command.upgrade)(cfg,revision)


@pytest.fixture()
def pg():
    admin_engine=create_engine(os.environ['OPS_TEST_POSTGRES_URL'])
    schema='ops_ledger_'+uuid.uuid4().hex[:16]
    with admin_engine.begin() as connection: connection.execute(text(f'CREATE SCHEMA {schema}'))
    engine=create_engine(os.environ['OPS_TEST_POSTGRES_URL'],connect_args={'options':f'-csearch_path={schema}'})
    try: yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection: connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin_engine.dispose()


def actor_and_record(factory, **changes):
    with factory() as db:
        user=ExtensionUser(sub2api_user_id=9201,sub2api_role='admin',username_snapshot='并发测试')
        db.add(user);db.commit()
        actor=CurrentUser(user.id,9201,'并发测试',None,'admin')
        body=dict(title='并发支出',expense_date='2026-10-01',payer='张三',amount='100.00',idempotency_key=str(uuid.uuid4()))
        body.update(changes)
        row=service.create_record(db,actor,RecordCreate(**body))
        return actor,row.id,row.version


def test_postgres_date_range_includes_both_boundaries(pg):
    from app.ledger import reports
    migrate(pg, 'head')
    factory = sessionmaker(pg, expire_on_commit=False, autoflush=False)
    actor, first, _ = actor_and_record(factory, expense_date='2025-12-31', amount='20')
    with factory() as db:
        second = service.create_record(db, actor, RecordCreate(title='跨年支出', expense_date='2026-01-01', payer='张三', amount='30', idempotency_key=str(uuid.uuid4())))
        service.create_record(db, actor, RecordCreate(title='范围外支出', expense_date='2026-01-02', payer='张三', amount='40', idempotency_key=str(uuid.uuid4())))
        filters = {'date_from': '2025-12-31', 'date_to': '2026-01-01'}
        result = reports.monthly(db, filters, actor)
        assert result['total_amount'] == '50.00'
        assert {row['id'] for row in result['items']} == {first, second.id}


def test_fresh_upgrade_and_empty_downgrade(pg):
    migrate(pg,'head')
    assert 'expense_records' in inspect(pg).get_table_names()
    migrate(pg,'007',downgrade=True)
    assert 'expense_records' not in inspect(pg).get_table_names() and 'expense_claims' in inspect(pg).get_table_names()
    migrate(pg,'head')


def test_007_legacy_data_preserved_and_populated_downgrade_refused(pg):
    migrate(pg,'007')
    factory=sessionmaker(pg,expire_on_commit=False,autoflush=False)
    with factory() as db:
        user=ExtensionUser(sub2api_user_id=9301,sub2api_role='admin');db.add(user);db.flush()
        claim=ExpenseClaim(claim_no='LEGACY-CHECK',applicant_user_id=user.id,expense_date=date(2026,9,1),category='STAFF_ADVANCE',
                           currency='HKD',amount_tax_included=Decimal('250'),pay_type='PERSONAL_ADVANCE',status='PAID',invoice_status='RECEIVED')
        db.add(claim);db.flush()
        db.add(ExpensePayment(claim_id=claim.id,amount=Decimal('20'),currency='USD',paid_at=datetime.now(timezone.utc),created_by_user_id=user.id))
        db.add(ExpenseAttachment(claim_id=claim.id,uploader_user_id=user.id,file_name='历史凭证.pdf',object_key='original/do-not-move',mime_type='application/pdf',file_size=10,sha256='a'*64))
        db.commit(); claim_id,user_id=claim.id,user.id
    migrate(pg,'008')
    with factory() as db:
        old=db.get(ExpenseClaim,claim_id)
        assert old.currency=='HKD' and old.status=='PAID' and old.amount_tax_included==250
        assert db.scalar(select(ExpenseAttachment)).object_key=='original/do-not-move'
        assert service.unconfirmed_count(db)==1
        actor=CurrentUser(user_id,9301,None,None,'admin')
        record=service.create_record(db,actor,RecordCreate(title='新支出',expense_date='2026-10-01',payer='任意人',amount='100',idempotency_key=str(uuid.uuid4())))
        assert record.id
    with pytest.raises(RuntimeError,match='ledger data must be retained'): migrate(pg,'007',downgrade=True)
    assert 'expense_records' in inspect(pg).get_table_names()


@pytest.mark.parametrize('same_key',[False,True])
def test_concurrent_reimbursement_and_retries(pg,same_key):
    migrate(pg,'head');factory=sessionmaker(pg,expire_on_commit=False,autoflush=False)
    actor,rid,version=actor_and_record(factory)
    with factory() as db:
        second=ExtensionUser(sub2api_user_id=9202,sub2api_role='admin');db.add(second);db.commit()
        actors=[actor,CurrentUser(second.id,9202,'另一管理员',None,'admin')]
    barrier=threading.Barrier(2);key=str(uuid.uuid4())
    def reimburse(index):
        with factory() as db:
            body=BatchInput(records=[{'id':rid,'version':version}],actual_amount='100',reimbursement_date='2026-11-01',idempotency_key=key if same_key else str(uuid.uuid4()))
            barrier.wait(timeout=10)
            try: return ('ok',service.create_batch(db,actors[index],body).id)
            except AppError as exc: db.rollback();return (exc.code,None)
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(reimburse,range(2)))
    if same_key: assert results[0]==results[1] and results[0][0]=='ok'
    else: assert [r[0] for r in results].count('ok')==1 and any(r[0]=='VERSION_CONFLICT' for r in results)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Reimbursement))==1
        assert db.scalar(select(func.count()).select_from(ReimbursementItem).where(ReimbursementItem.active_record_id==rid))==1


def test_edit_reimbursement_race_never_settles_stale_amount(pg):
    migrate(pg,'head');factory=sessionmaker(pg,expire_on_commit=False,autoflush=False)
    actor,rid,version=actor_and_record(factory);barrier=threading.Barrier(2)
    def work(kind):
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                if kind=='edit': service.edit_record(db,actor,rid,RecordUpdate(title='并发支出',expense_date='2026-10-01',payer='张三',amount='200',version=version))
                else: service.create_batch(db,actor,BatchInput(records=[{'id':rid,'version':version}],actual_amount='100',reimbursement_date='2026-11-01',idempotency_key=str(uuid.uuid4())))
                return kind
            except AppError: db.rollback();return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(work,['edit','reimburse']))
    assert results.count('conflict')==1
    with factory() as db:
        row=db.get(ExpenseRecord,rid);item=service.active_item(db,rid)
        if item: assert row.rmb_amount==100 and item.expected_amount==100
        else: assert row.rmb_amount==200


def test_amount_extreme_exact_precision_and_largest_remainder(pg):
    migrate(pg,'head');factory=sessionmaker(pg,expire_on_commit=False,autoflush=False)
    actor,rid,version=actor_and_record(factory,amount='9999999999999999.99')
    with factory() as db:
        assert db.get(ExpenseRecord,rid).rmb_amount==Decimal('9999999999999999.99')
        rows=[service.create_record(db,actor,RecordCreate(title='一分钱分配',expense_date='2026-10-01',payer='李四',amount='1',idempotency_key=str(uuid.uuid4()))) for _ in range(3)]
        batch=service.create_batch(db,actor,BatchInput(records=[{'id':r.id,'version':r.version} for r in reversed(rows)],actual_amount='0.01',reimbursement_date='2026-10-02',difference_reason='整批结清调整',idempotency_key=str(uuid.uuid4())))
        items=db.scalars(select(ReimbursementItem).where(ReimbursementItem.batch_id==batch.id).order_by(ReimbursementItem.record_id)).all()
        assert [i.actual_amount for i in items]==[Decimal('.01'),Decimal('0'),Decimal('0')]
        assert sum(i.actual_amount for i in items)==Decimal('.01')


def test_simultaneous_history_confirm_unique(pg):
    migrate(pg,'head');factory=sessionmaker(pg,expire_on_commit=False,autoflush=False)
    actor,rid,version=actor_and_record(factory)
    with factory() as db:
        old=ExpenseClaim(claim_no='HISTORY-RACE',applicant_user_id=actor.id,expense_date=date(2026,9,1),category='CDN',currency='CNY',amount_tax_included=100,pay_type='PERSONAL_ADVANCE',status='PAID',invoice_status='NONE')
        db.add(old);db.commit();old_id=old.id
    body=HistoryConfirm(title='历史确认',expense_date='2026-09-01',payer='李四',amount='100',history_settled=False,idempotency_key=str(uuid.uuid4()))
    barrier=threading.Barrier(2)
    def confirm(_):
        with factory() as db:
            barrier.wait(timeout=10)
            return service.confirm_history(db,actor,old_id,body).id
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(confirm,range(2)))
    assert results[0]==results[1]
    with factory() as db: assert db.scalar(select(func.count()).select_from(ExpenseRecord).where(ExpenseRecord.legacy_claim_id==old_id))==1


def test_concurrent_creation_same_key_returns_same_record(pg):
    migrate(pg,'head');factory=sessionmaker(pg,expire_on_commit=False,autoflush=False)
    actor,_,_=actor_and_record(factory)
    body=RecordCreate(title='创建重试',expense_date='2026-10-01',payer='外部付款人',amount='50',idempotency_key=str(uuid.uuid4()))
    barrier=threading.Barrier(2)
    def create(_):
        with factory() as db:
            barrier.wait(timeout=10)
            return service.create_record(db,actor,body).id
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(create,range(2)))
    assert results[0]==results[1]
    with factory() as db: assert db.scalar(select(func.count()).select_from(ExpenseRecord).where(ExpenseRecord.idempotency_key==body.idempotency_key))==1


def test_concurrent_whole_batch_revocation_is_once(pg):
    migrate(pg,'head');factory=sessionmaker(pg,expire_on_commit=False,autoflush=False)
    actor,rid,version=actor_and_record(factory)
    with factory() as db:
        batch=service.create_batch(db,actor,BatchInput(records=[{'id':rid,'version':version}],actual_amount='100',reimbursement_date='2026-11-01',idempotency_key=str(uuid.uuid4())))
        bid=batch.id
    barrier=threading.Barrier(2)
    def revoke(_):
        with factory() as db:
            barrier.wait(timeout=10)
            try: service.revoke_batch(db,actor,bid,VersionReason(version=1,reason='并发更正'));return 'revoked'
            except AppError as exc:db.rollback();return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(revoke,range(2)))
    assert sorted(results)==['VERSION_CONFLICT','revoked']
    with factory() as db:
        assert service.active_item(db,rid) is None and db.get(ExpenseRecord,rid).version==3
        assert db.scalar(select(func.count()).select_from(LedgerEvent).where(LedgerEvent.record_id==rid,LedgerEvent.event_type=='REIMBURSEMENT_REVOKED'))==1
