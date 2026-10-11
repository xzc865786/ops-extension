"""Add account records with encrypted secrets and audit events; existing tables untouched."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

ID = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')


def upgrade():
    op.create_table('account_records',
    sa.Column('id', ID, autoincrement=True, nullable=False),
    sa.Column('client', sa.String(length=50), nullable=False),
    sa.Column('login', sa.String(length=255), nullable=False),
    sa.Column('identity', sa.String(length=310), nullable=False),
    sa.Column('active_identity', sa.String(length=310), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('plan', sa.String(length=50), nullable=False),
    sa.Column('expires_on', sa.Date(), nullable=True),
    sa.Column('owner', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=50), nullable=False),
    sa.Column('recovery_email', sa.String(length=255), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('password_enc', sa.Text(), nullable=True),
    sa.Column('secret_notes_enc', sa.Text(), nullable=True),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('version', ID, nullable=False),
    sa.Column('created_by', ID, nullable=False),
    sa.Column('updated_by', ID, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'STANDBY', 'BANNED', 'DISABLED')", name='ck_account_status'),
    sa.CheckConstraint('active_identity IS NULL OR active_identity = identity', name='ck_account_active_identity'),
    sa.ForeignKeyConstraint(['created_by'], ['extension_users.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['extension_users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('active_identity')
    )
    op.create_index('ix_account_client', 'account_records', ['client'], unique=False)
    op.create_table('account_events',
    sa.Column('id', ID, autoincrement=True, nullable=False),
    sa.Column('account_id', ID, nullable=False),
    sa.Column('actor_user_id', ID, nullable=False),
    sa.Column('actor_name', sa.String(length=100), nullable=True),
    sa.Column('event_type', sa.String(length=40), nullable=False),
    sa.Column('detail', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['account_records.id'], ),
    sa.ForeignKeyConstraint(['actor_user_id'], ['extension_users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_account_event_account', 'account_events', ['account_id', 'id'], unique=False)


def downgrade():
    # Dropping these tables destroys stored account data; back up before downgrading.
    op.drop_index('ix_account_event_account', table_name='account_events')
    op.drop_table('account_events')
    op.drop_index('ix_account_client', table_name='account_records')
    op.drop_table('account_records')
