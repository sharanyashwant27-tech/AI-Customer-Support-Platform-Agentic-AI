"""SQLAlchemy ORM models package — PostgreSQL core tables."""

from app.db.models.agent import Agent, AgentKind
from app.db.models.chat_history import ChatHistory, ChatRole
from app.db.models.customer import Customer
from app.db.models.feedback import Feedback
from app.db.models.knowledge_doc import KnowledgeDoc
from app.db.models.order import Order, OrderItem, OrderStatus
from app.db.models.product import Product
from app.db.models.ticket import Ticket, TicketPriority, TicketStatus
from app.db.models.user import User, UserRole

# Legacy conversation models kept for soft migration / optional use
from app.db.models.conversation import Conversation, Message, MessageRole

__all__ = [
    "Customer",
    "Order",
    "OrderItem",
    "OrderStatus",
    "Ticket",
    "TicketStatus",
    "TicketPriority",
    "Product",
    "KnowledgeDoc",
    "ChatHistory",
    "ChatRole",
    "Agent",
    "AgentKind",
    "Feedback",
    "User",
    "UserRole",
    "Conversation",
    "Message",
    "MessageRole",
]

# Canonical PostgreSQL tables for the platform
CORE_TABLES = [
    "customers",
    "orders",
    "tickets",
    "products",
    "knowledge_docs",
    "chat_history",
    "agents",
    "feedback",
]
