"""Add independent expense ledger; do not transform legacy financial data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():

    op.create_table('expense_rate_quotes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('rate', sa.Numeric(precision=24, scale=12), nullable=False),
    sa.Column('effective_date', sa.Date(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('expense_records',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('expense_date', sa.Date(), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('payer', sa.String(length=100), nullable=False),
    sa.Column('merchant', sa.String(length=200), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('rmb_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('amount_mode', sa.String(length=10), nullable=False),
    sa.Column('quote_id', sa.String(length=36), nullable=True),
    sa.Column('reference_rate', sa.Numeric(precision=24, scale=12), nullable=True),
    sa.Column('rate_date', sa.Date(), nullable=True),
    sa.Column('rate_fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rate_source', sa.String(length=100), nullable=True),
    sa.Column('needs_reimbursement', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_by', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('updated_by', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('version', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('legacy_claim_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("amount_mode IN ('AUTO', 'MANUAL')", name='ck_record_mode'),
    sa.CheckConstraint("currency IN ('CNY', 'USD')", name='ck_record_currency'),
    sa.CheckConstraint('amount > 0 AND rmb_amount > 0', name='ck_record_positive'),
    sa.ForeignKeyConstraint(['created_by'], ['extension_users.id'], ),
    sa.ForeignKeyConstraint(['legacy_claim_id'], ['expense_claims.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['expense_rate_quotes.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['extension_users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key'),
    sa.UniqueConstraint('legacy_claim_id')
    )
    op.create_index('ix_record_date_active', 'expense_records', ['expense_date', 'active'], unique=False)
    op.create_index('ix_record_payer', 'expense_records', ['payer'], unique=False)
    op.create_table('expense_reimbursements',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('payer', sa.String(length=100), nullable=False),
    sa.Column('actual_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('reimbursement_date', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('difference_reason', sa.Text(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('revoked_by', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('revoke_reason', sa.Text(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('actual_amount > 0', name='ck_reimbursement_positive'),
    sa.ForeignKeyConstraint(['created_by'], ['extension_users.id'], ),
    sa.ForeignKeyConstraint(['revoked_by'], ['extension_users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_table('expense_reimbursement_items',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('record_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('batch_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('active_record_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('expected_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('actual_amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('difference', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.CheckConstraint('active_record_id IS NULL OR active_record_id = record_id', name='ck_item_active_record'),
    sa.CheckConstraint('actual_amount >= 0 AND expected_amount > 0', name='ck_reimbursement_item_amount'),
    sa.ForeignKeyConstraint(['active_record_id'], ['expense_records.id'], ),
    sa.ForeignKeyConstraint(['batch_id'], ['expense_reimbursements.id'], ),
    sa.ForeignKeyConstraint(['record_id'], ['expense_records.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('active_record_id')
    )
    op.create_index('ix_reimbursement_item_record', 'expense_reimbursement_items', ['record_id'], unique=False)
    op.create_table('expense_ledger_attachments',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('record_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('batch_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('uploader_user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('object_key', sa.String(length=512), nullable=False),
    sa.Column('mime_type', sa.String(length=128), nullable=False),
    sa.Column('file_size', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('(record_id IS NULL) != (batch_id IS NULL)', name='ck_ledger_attachment_owner'),
    sa.ForeignKeyConstraint(['batch_id'], ['expense_reimbursements.id'], ),
    sa.ForeignKeyConstraint(['record_id'], ['expense_records.id'], ),
    sa.ForeignKeyConstraint(['uploader_user_id'], ['extension_users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('expense_ledger_events',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('record_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('batch_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('actor_user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('actor_name', sa.String(length=100), nullable=True),
    sa.Column('event_type', sa.String(length=40), nullable=False),
    sa.Column('old_value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('new_value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['extension_users.id'], ),
    sa.ForeignKeyConstraint(['batch_id'], ['expense_reimbursements.id'], ),
    sa.ForeignKeyConstraint(['record_id'], ['expense_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ledger_event_record', 'expense_ledger_events', ['record_id', 'id'], unique=False)



def downgrade():
    # Never drop financial history through an application rollback.
    if op.get_context().as_sql:
        raise RuntimeError("Ledger downgrade requires an online empty-data check")
    connection = op.get_bind()
    tables = ("expense_records", "expense_reimbursements", "expense_ledger_attachments", "expense_ledger_events")
    if any(connection.execute(sa.text("SELECT COUNT(*) FROM " + name)).scalar() for name in tables):
        raise RuntimeError("Refusing downgrade: ledger data must be retained; roll back application only")
    for name in ("expense_ledger_events", "expense_ledger_attachments", "expense_reimbursement_items", "expense_reimbursements", "expense_records", "expense_rate_quotes"):
        op.drop_table(name)
