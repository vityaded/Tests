"""Add learn_test_result table

Revision ID: 1f608820cd9f
Revises: f22429b40b29
Create Date: 2024-10-13 19:08:43.170239

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f608820cd9f'
down_revision = 'f22429b40b29'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('learn_test_result',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('test_id', sa.Integer(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['test_id'], ['test.id'], name=op.f('fk_learn_test_result_test_id_test')),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_learn_test_result_user_id_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_learn_test_result'))
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('learn_test_result')
    # ### end Alembic commands ###
