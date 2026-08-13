import math
import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Comment, Notification, Ticket, User
from src.schemas import (
    CommentCreate,
    CommentResponse,
    DashboardSummary,
    NotificationType,
    PaginatedTickets,
    Role,
    TicketCategory,
    TicketCreate,
    TicketPriority,
    TicketResponse,
    TicketStatus,
    TicketStatusUpdate,
)
from src.security import get_current_user, require_roles
from src.ticket_access import (
    can_view_ticket,
    get_ticket_or_404,
    is_admin,
)


router = APIRouter(prefix="/tickets", tags=["tickets"])


# Strict sequential lifecycle, ported from the reference project's
# TicketServiceImpl.validateStatusTransition: OPEN -> IN_PROGRESS ->
# RESOLVED -> CLOSED, with IN_PROGRESS/RESOLVED allowed to step back one
# stage and CLOSED reopenable straight to IN_PROGRESS. Same-status is
# always a no-op, handled separately below.
_STATUS_TRANSITIONS = {
    TicketStatus.OPEN: {TicketStatus.IN_PROGRESS},
    TicketStatus.IN_PROGRESS: {
        TicketStatus.RESOLVED,
        TicketStatus.OPEN,
    },
    TicketStatus.RESOLVED: {
        TicketStatus.CLOSED,
        TicketStatus.IN_PROGRESS,
    },
    TicketStatus.CLOSED: {TicketStatus.IN_PROGRESS},
}


def _to_ticket_response(ticket: Ticket) -> TicketResponse:

    return TicketResponse(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        user_sequence=ticket.user_sequence,
        title=ticket.title,
        description=ticket.description,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        created_by=ticket.created_by_id,
        created_by_username=ticket.creator.username,
        assigned_to=ticket.assigned_to_id,
        assigned_to_username=(
            ticket.assignee.username if ticket.assignee else None
        ),
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def _to_comment_response(comment: Comment) -> CommentResponse:

    return CommentResponse(
        id=comment.id,
        ticket_id=comment.ticket_id,
        author_id=comment.author_id,
        author_username=comment.author.username,
        message=comment.message,
        created_at=comment.created_at,
    )


def _generate_ticket_number(
    db: Session, creator_id: int
) -> tuple[str, int]:

    seq = (
        db.query(func.count(Ticket.id))
        .filter(Ticket.created_by_id == creator_id)
        .scalar()
        or 0
    ) + 1

    # Matches the reference project: a random 4-digit code plus the
    # creator's own sequence number. Not guaranteed globally unique, but
    # this is a display identifier, not a key.
    number = f"TKT-{random.randint(1000, 9999)}-{seq:02d}"

    return number, seq


def _notify(
    db: Session,
    recipient_id: int,
    ticket_id: int,
    ntype: NotificationType,
    message: str,
) -> None:

    db.add(
        Notification(
            recipient_id=recipient_id,
            ticket_id=ticket_id,
            type=ntype.value,
            message=message,
        )
    )


def _notify_creator_and_assignee(
    db: Session,
    ticket: Ticket,
    actor_id: int,
    ntype: NotificationType,
    message: str,
) -> None:
    """Notify the creator and assignee, skipping whichever of them
    performed the action (no need to tell someone about their own
    change) and de-duplicating when creator == assignee."""

    for recipient_id in {ticket.created_by_id, ticket.assigned_to_id}:

        if recipient_id and recipient_id != actor_id:

            _notify(db, recipient_id, ticket.id, ntype, message)


@router.post(
    "",
    response_model=TicketResponse,
    status_code=201,
)
def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    number, seq = _generate_ticket_number(db, current_user.id)

    new_ticket = Ticket(
        title=ticket.title,
        description=ticket.description,
        category=ticket.category.value,
        priority=ticket.priority.value,
        status=TicketStatus.OPEN.value,
        created_by_id=current_user.id,
        ticket_number=number,
        user_sequence=seq,
    )

    db.add(new_ticket)

    db.flush()

    _notify(
        db,
        recipient_id=current_user.id,
        ticket_id=new_ticket.id,
        ntype=NotificationType.TICKET_CREATED,
        message=(
            f"Your ticket #{new_ticket.ticket_number} has been "
            "successfully created."
        ),
    )

    db.commit()

    db.refresh(new_ticket)

    return _to_ticket_response(new_ticket)


@router.get(
    "",
    response_model=PaginatedTickets,
)
def get_all_tickets(
    status: Optional[TicketStatus] = Query(default=None),
    priority: Optional[TicketPriority] = Query(default=None),
    category: Optional[TicketCategory] = Query(default=None),
    assigned_status: Optional[str] = Query(
        default=None,
        pattern="(?i)^(unassigned|assigned)$",
        description="Admin-only filter: 'unassigned' or 'assigned'.",
    ),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    query = db.query(Ticket)

    if status is not None:
        query = query.filter(Ticket.status == status.value)

    if priority is not None:
        query = query.filter(Ticket.priority == priority.value)

    if category is not None:
        query = query.filter(Ticket.category == category.value)

    # Role-based visibility, ported from TicketServiceImpl.getTickets:
    # admins see everything, agents see only what's assigned to them,
    # everyone else sees only what they created.
    if is_admin(current_user):

        if assigned_status:

            if assigned_status.lower() == "unassigned":
                query = query.filter(Ticket.assigned_to_id.is_(None))
            else:
                query = query.filter(
                    Ticket.assigned_to_id.isnot(None)
                )

    elif current_user.role == Role.AGENT.value:
        query = query.filter(
            Ticket.assigned_to_id == current_user.id
        )

    else:
        query = query.filter(
            Ticket.created_by_id == current_user.id
        )

    total = query.count()

    total_pages = math.ceil(total / size) if total else 0

    items = (
        query.order_by(Ticket.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return PaginatedTickets(
        items=[_to_ticket_response(t) for t in items],
        page=page,
        size=size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/dashboard",
    response_model=DashboardSummary,
)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(Role.ADMIN, Role.AGENT)
    ),
):
    # Global counts (not scoped to the caller) - matches the reference
    # project, which restricts this endpoint to AGENT/ADMIN precisely
    # because it's a org-wide view, not a personal one.

    total = db.query(
        func.count(Ticket.id)
    ).scalar()

    status_rows = (
        db.query(
            Ticket.status,
            func.count(Ticket.id),
        )
        .group_by(Ticket.status)
        .all()
    )

    priority_rows = (
        db.query(
            Ticket.priority,
            func.count(Ticket.id),
        )
        .group_by(Ticket.priority)
        .all()
    )

    by_status = {
        status.value: 0
        for status in TicketStatus
    }
    by_status.update(dict(status_rows))

    by_priority = {
        priority.value: 0
        for priority in TicketPriority
    }
    by_priority.update(dict(priority_rows))

    return DashboardSummary(
        total_tickets=total or 0,
        by_status=by_status,
        by_priority=by_priority,
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ticket = get_ticket_or_404(db, ticket_id)

    if not can_view_ticket(ticket, current_user):

        raise HTTPException(
            status_code=403,
            detail=(
                "You are not authorized to view "
                f"ticket ID: {ticket_id}"
            ),
        )

    return _to_ticket_response(ticket)


@router.patch(
    "/{ticket_id}/status",
    response_model=TicketResponse,
)
def update_ticket_status(
    ticket_id: int,
    update: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(Role.ADMIN, Role.AGENT)
    ),
):

    ticket = get_ticket_or_404(db, ticket_id)

    current_status = TicketStatus(ticket.status)
    target_status = update.status

    if current_status != target_status:

        allowed = _STATUS_TRANSITIONS.get(current_status, set())

        if target_status not in allowed:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid status transition from "
                    f"'{current_status.value}' to "
                    f"'{target_status.value}'. Tickets must follow "
                    "the sequential lifecycle: OPEN -> IN_PROGRESS -> "
                    "RESOLVED -> CLOSED."
                ),
            )

        old_status = ticket.status

        ticket.status = target_status.value

        db.flush()

        _notify_creator_and_assignee(
            db,
            ticket,
            actor_id=current_user.id,
            ntype=NotificationType.STATUS_CHANGED,
            message=(
                f"Ticket #{ticket.ticket_number} status changed from "
                f"{old_status} to {ticket.status}."
            ),
        )

    db.commit()

    db.refresh(ticket)

    return _to_ticket_response(ticket)


@router.patch(
    "/{ticket_id}/assign",
    response_model=TicketResponse,
)
def assign_ticket(
    ticket_id: int,
    agent_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.ADMIN)),
):

    ticket = get_ticket_or_404(db, ticket_id)

    # Self-assign when no agent_id is given, matching the reference's
    # assignTicket logic.
    assignee_id = (
        agent_id if agent_id is not None else current_user.id
    )

    assignee = db.get(User, assignee_id)

    if assignee is None:

        raise HTTPException(
            status_code=404,
            detail=f"User not found with ID: {assignee_id}",
        )

    ticket.assigned_to_id = assignee_id

    db.commit()

    db.refresh(ticket)

    return _to_ticket_response(ticket)


@router.delete(
    "/{ticket_id}",
)
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):

    ticket = get_ticket_or_404(db, ticket_id)

    db.delete(ticket)

    db.commit()

    return {
        "message": (
            "Ticket deleted successfully"
        )
    }


@router.post(
    "/{ticket_id}/comments",
    response_model=CommentResponse,
    status_code=201,
)
def add_comment(
    ticket_id: int,
    comment: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ticket = get_ticket_or_404(db, ticket_id)

    if not can_view_ticket(ticket, current_user):

        raise HTTPException(
            status_code=403,
            detail=(
                "You are not authorized to comment on "
                f"ticket ID: {ticket_id}"
            ),
        )

    new_comment = Comment(
        ticket_id=ticket_id,
        author_id=current_user.id,
        message=comment.message,
    )

    db.add(new_comment)

    db.flush()

    snippet = (
        comment.message
        if len(comment.message) <= 50
        else comment.message[:50] + "..."
    )

    _notify_creator_and_assignee(
        db,
        ticket,
        actor_id=current_user.id,
        ntype=NotificationType.COMMENT_ADDED,
        message=(
            f"New comment on ticket #{ticket.ticket_number}: "
            f"'{snippet}'"
        ),
    )

    db.commit()

    db.refresh(new_comment)

    return _to_comment_response(new_comment)


@router.get(
    "/{ticket_id}/comments",
    response_model=List[CommentResponse],
)
def get_ticket_comments(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ticket = get_ticket_or_404(db, ticket_id)

    if not can_view_ticket(ticket, current_user):

        raise HTTPException(
            status_code=403,
            detail=(
                "You are not authorized to view comments on "
                f"ticket ID: {ticket_id}"
            ),
        )

    comments = (
        db.query(Comment)
        .filter(Comment.ticket_id == ticket_id)
        .order_by(Comment.created_at)
        .all()
    )

    return [_to_comment_response(c) for c in comments]
