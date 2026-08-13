"""Shared ticket-visibility rules, used by both the tickets and
attachments routers so the two stay consistent."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models import Ticket, User
from src.schemas import Role


def is_admin(user: User) -> bool:
    return user.role == Role.ADMIN.value


def is_agent_or_admin(user: User) -> bool:
    return user.role in (Role.ADMIN.value, Role.AGENT.value)


def can_view_ticket(ticket: Ticket, user: User) -> bool:
    """Agents/admins see everything; everyone else only sees tickets
    they created or are assigned to."""

    return (
        is_agent_or_admin(user)
        or ticket.created_by_id == user.id
        or ticket.assigned_to_id == user.id
    )


def get_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    return ticket
