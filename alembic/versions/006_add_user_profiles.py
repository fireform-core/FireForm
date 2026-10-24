"""Add user profiles

Revision ID: 006
Revises: 005
Create Date: 2024-03-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None

def upgrade():
    # Create profiles table
    op.create_table('profiles',
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('profession', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('custom_fields', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('profile_id')
    )
    
    # Add profile_id to inputs table and create foreign key using batch mode
    with op.batch_alter_table('inputs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('profile_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key('fk_inputs_profiles', 'profiles', ['profile_id'], ['profile_id'])

def downgrade():
    with op.batch_alter_table('inputs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_inputs_profiles', type_='foreignkey')
        batch_op.drop_column('profile_id')
        
    op.drop_table('profiles')
