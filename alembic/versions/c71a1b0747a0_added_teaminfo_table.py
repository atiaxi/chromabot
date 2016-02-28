"""Added TeamInfo table

Revision ID: c71a1b0747a0
Revises: 2a147893565a
Create Date: 2016-02-27 19:38:42.508684

"""

# revision identifiers, used by Alembic.
revision = 'c71a1b0747a0'
down_revision = '2a147893565a'

from alembic import op
import sqlalchemy as sa


def upgrade(engine_name):
    eval("upgrade_%s" % engine_name)()


def downgrade(engine_name):
    eval("downgrade_%s" % engine_name)()





def upgrade_engine1():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('team_info',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('greeting', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    ### end Alembic commands ###


def downgrade_engine1():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('team_info')
    ### end Alembic commands ###


def upgrade_engine2():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('team_info',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('greeting', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    ### end Alembic commands ###


def downgrade_engine2():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('team_info')
    ### end Alembic commands ###


def upgrade_engine3():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('team_info',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('greeting', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    ### end Alembic commands ###


def downgrade_engine3():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('team_info')
    ### end Alembic commands ###

