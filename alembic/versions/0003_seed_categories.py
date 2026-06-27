"""seed default categories

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

categories = [
    ("Supermercado", "🛒"),
    ("Restaurantes", "🍽️"),
    ("Transporte", "🚗"),
    ("Entretenimiento", "🎬"),
    ("Salud", "💊"),
    ("Ropa", "👕"),
    ("Educación", "📚"),
    ("Servicios", "💡"),
    ("Hogar", "🏠"),
    ("Suscripciones", "🔁"),
    ("Mascotas", "🐾"),
    ("Tecnología", "💻"),
    ("Otros", "📦"),
]


def upgrade() -> None:
    table = sa.table(
        "categories",
        sa.column("name", sa.String),
        sa.column("icon", sa.String),
    )
    op.bulk_insert(table, [{"name": name, "icon": icon} for name, icon in categories])


def downgrade() -> None:
    op.execute("DELETE FROM categories WHERE name IN (%s)" %
               ", ".join(f"'{name}'" for name, _ in categories))
