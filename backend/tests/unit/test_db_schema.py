"""PostgreSQL core table model smoke tests."""

from app.db.models import CORE_TABLES
from app.db.models.agent import Agent
from app.db.models.chat_history import ChatHistory
from app.db.models.customer import Customer
from app.db.models.feedback import Feedback
from app.db.models.knowledge_doc import KnowledgeDoc
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.ticket import Ticket


def test_core_tables_list():
    assert CORE_TABLES == [
        "customers",
        "orders",
        "tickets",
        "products",
        "knowledge_docs",
        "chat_history",
        "agents",
        "feedback",
    ]


def test_model_tablename_alignment():
    assert Customer.__tablename__ == "customers"
    assert Order.__tablename__ == "orders"
    assert Ticket.__tablename__ == "tickets"
    assert Product.__tablename__ == "products"
    assert KnowledgeDoc.__tablename__ == "knowledge_docs"
    assert ChatHistory.__tablename__ == "chat_history"
    assert Agent.__tablename__ == "agents"
    assert Feedback.__tablename__ == "feedback"
