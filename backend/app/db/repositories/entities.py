"""Repositories for core PostgreSQL tables."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import Agent, AgentKind
from app.db.models.chat_history import ChatHistory, ChatRole
from app.db.models.conversation import Conversation, Message, MessageRole
from app.db.models.customer import Customer
from app.db.models.feedback import Feedback
from app.db.models.knowledge_doc import KnowledgeDoc
from app.db.models.product import Product
from app.db.models.ticket import Ticket, TicketPriority, TicketStatus


def _ticket_number() -> str:
    return f"TKT-{uuid.uuid4().hex[:8].upper()}"


class CustomerRepository:
    async def get_by_email(self, db: AsyncSession, email: str) -> Customer | None:
        result = await db.execute(select(Customer).where(Customer.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, customer_id: uuid.UUID) -> Customer | None:
        result = await db.execute(select(Customer).where(Customer.id == customer_id))
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        db: AsyncSession,
        *,
        email: str,
        full_name: str | None = None,
        external_id: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> Customer:
        existing = await self.get_by_email(db, email)
        if existing:
            return existing
        customer = Customer(
            email=email,
            full_name=full_name or email.split("@")[0],
            external_id=external_id,
            preferences=preferences or {},
        )
        db.add(customer)
        await db.flush()
        await db.refresh(customer)
        return customer


class TicketRepository:
    async def create(
        self,
        db: AsyncSession,
        *,
        customer_id: uuid.UUID,
        subject: str,
        description: str,
        priority: TicketPriority = TicketPriority.MEDIUM,
        category: str | None = None,
        ticket_number: str | None = None,
        assigned_agent_id: uuid.UUID | None = None,
    ) -> Ticket:
        ticket = Ticket(
            ticket_number=ticket_number or _ticket_number(),
            customer_id=customer_id,
            subject=subject,
            description=description,
            priority=priority,
            category=category,
            assigned_agent_id=assigned_agent_id,
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        await db.flush()
        await db.refresh(ticket)
        return ticket

    async def list_for_customer(
        self, db: AsyncSession, customer_id: uuid.UUID | None = None
    ) -> list[Ticket]:
        stmt = select(Ticket).order_by(Ticket.created_at.desc())
        if customer_id:
            stmt = stmt.where(Ticket.customer_id == customer_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
        result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
        return result.scalar_one_or_none()

    async def get_by_number(self, db: AsyncSession, ticket_number: str) -> Ticket | None:
        result = await db.execute(
            select(Ticket).where(Ticket.ticket_number == ticket_number.upper())
        )
        return result.scalar_one_or_none()

    async def update(
        self, db: AsyncSession, ticket: Ticket, **fields: object
    ) -> Ticket:
        for key, value in fields.items():
            if value is not None and hasattr(ticket, key):
                setattr(ticket, key, value)
        ticket.updated_at = datetime.now(UTC)
        await db.flush()
        await db.refresh(ticket)
        return ticket


class ChatHistoryRepository:
    async def add(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        role: ChatRole | str,
        content: str,
        customer_id: uuid.UUID | None = None,
        channel: str = "web",
        intent: str | None = None,
        sentiment: str | None = None,
        confidence: float | None = None,
        agent_name: str | None = None,
        ticket_number: str | None = None,
        citations: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChatHistory:
        row = ChatHistory(
            session_id=session_id,
            customer_id=customer_id,
            role=ChatRole(role) if isinstance(role, str) else role,
            content=content,
            channel=channel,
            intent=intent,
            sentiment=sentiment,
            confidence=confidence,
            agent_name=agent_name,
            ticket_number=ticket_number,
            citations=citations,
            metadata_=metadata or {},
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    async def list_session(
        self, db: AsyncSession, session_id: str, *, limit: int = 50
    ) -> list[ChatHistory]:
        result = await db.execute(
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


class ConversationRepository:
    """Legacy conversations/messages — also mirrors into chat_history."""

    async def get_or_create(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        customer_id: uuid.UUID | None,
        channel: str = "web",
        metadata: dict | None = None,
    ) -> Conversation:
        result = await db.execute(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        if customer_id is None:
            customer = await customer_repo.get_or_create(
                db,
                email=f"anon-{session_id[:12]}@example.local",
                full_name="Anonymous",
                external_id=session_id,
            )
            customer_id = customer.id

        conversation = Conversation(
            session_id=session_id,
            customer_id=customer_id,
            channel=channel,
            metadata_=metadata or {},
        )
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
        return conversation

    async def add_message(
        self,
        db: AsyncSession,
        *,
        conversation: Conversation,
        role: MessageRole,
        content: str,
        intent: str | None = None,
        confidence: float | None = None,
        agent_name: str | None = None,
        citations: list | None = None,
        metadata: dict | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation.id,
            role=role,
            content=content,
            intent=intent,
            confidence=confidence,
            agent_name=agent_name,
            citations=citations,
            metadata_=metadata or {},
        )
        db.add(message)
        conversation.updated_at = datetime.now(UTC)
        await chat_history_repo.add(
            db,
            session_id=conversation.session_id,
            customer_id=conversation.customer_id,
            role=role.value,
            content=content,
            channel=conversation.channel,
            intent=intent,
            confidence=confidence,
            agent_name=agent_name,
            citations=citations,
            metadata=metadata,
        )
        await db.flush()
        await db.refresh(message)
        return message


class FeedbackRepository:
    async def create(
        self,
        db: AsyncSession,
        *,
        rating: int,
        comment: str | None = None,
        category: str | None = None,
        customer_id: uuid.UUID | None = None,
        chat_history_id: uuid.UUID | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
    ) -> Feedback:
        item = Feedback(
            rating=rating,
            comment=comment,
            category=category,
            customer_id=customer_id,
            chat_history_id=chat_history_id,
            session_id=session_id,
            agent_name=agent_name,
        )
        db.add(item)
        await db.flush()
        await db.refresh(item)
        return item

    async def list_all(self, db: AsyncSession) -> list[Feedback]:
        result = await db.execute(select(Feedback).order_by(Feedback.created_at.desc()))
        return list(result.scalars().all())


class ProductRepository:
    async def upsert_sku(
        self,
        db: AsyncSession,
        *,
        sku: str,
        name: str,
        unit_price: float = 0.0,
        category: str | None = None,
        description: str | None = None,
    ) -> Product:
        result = await db.execute(select(Product).where(Product.sku == sku))
        product = result.scalar_one_or_none()
        if product:
            product.name = name
            product.unit_price = unit_price
            product.category = category
            product.description = description
        else:
            product = Product(
                sku=sku,
                name=name,
                unit_price=unit_price,
                category=category,
                description=description,
            )
            db.add(product)
        await db.flush()
        await db.refresh(product)
        return product


class KnowledgeDocRepository:
    async def create(
        self,
        db: AsyncSession,
        *,
        title: str,
        source: str,
        content: str,
        knowledge_source: str = "knowledge_base",
        file_type: str | None = None,
        chunk_count: int = 0,
        document_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeDoc:
        doc = KnowledgeDoc(
            title=title,
            source=source,
            content=content,
            knowledge_source=knowledge_source,
            file_type=file_type,
            chunk_count=chunk_count,
            document_id=document_id,
            metadata_=metadata or {},
        )
        db.add(doc)
        await db.flush()
        await db.refresh(doc)
        return doc


class AgentRepository:
    async def ensure_defaults(self, db: AsyncSession) -> None:
        defaults = [
            ("master", "Master Agent", AgentKind.AI, ["orchestrate", "delegate"]),
            ("intent", "Intent Classification Agent", AgentKind.AI, ["classify"]),
            ("knowledge", "Knowledge Agent", AgentKind.AI, ["rag", "answer"]),
            ("order", "Order Management Agent", AgentKind.AI, ["orders"]),
            ("ticket", "Ticket Agent", AgentKind.AI, ["tickets"]),
            ("sentiment", "Sentiment Agent", AgentKind.AI, ["sentiment"]),
            ("handoff", "Human Handoff Agent", AgentKind.AI, ["escalate"]),
            ("human_specialist", "Human Support Specialist", AgentKind.HUMAN, ["handoff"]),
        ]
        for name, display, kind, caps in defaults:
            result = await db.execute(select(Agent).where(Agent.name == name))
            if result.scalar_one_or_none():
                continue
            db.add(
                Agent(
                    name=name,
                    display_name=display,
                    kind=kind,
                    capabilities=caps,
                    description=display,
                )
            )
        await db.flush()


customer_repo = CustomerRepository()
ticket_repo = TicketRepository()
conversation_repo = ConversationRepository()
chat_history_repo = ChatHistoryRepository()
feedback_repo = FeedbackRepository()
product_repo = ProductRepository()
knowledge_doc_repo = KnowledgeDocRepository()
agent_repo = AgentRepository()
