from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TicketPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TicketCategory(str, Enum):
    HARDWARE = "HARDWARE"
    SOFTWARE = "SOFTWARE"
    NETWORK = "NETWORK"
    ACCESS = "ACCESS"
    OTHER = "OTHER"


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class TicketCreate(BaseModel):
    title: str = Field(
        min_length=3,
        max_length=100,
    )

    description: str = Field(
        min_length=5,
        max_length=1000,
    )

    category: TicketCategory = (
        TicketCategory.OTHER
    )

    priority: TicketPriority = (
        TicketPriority.MEDIUM
    )


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketResponse(BaseModel):
    id: int
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    created_at: datetime
    updated_at: datetime


class CommentCreate(BaseModel):
    author: str = Field(
        min_length=2,
        max_length=50,
    )

    message: str = Field(
        min_length=1,
        max_length=1000,
    )


class CommentResponse(BaseModel):
    id: int
    ticket_id: int
    author: str
    message: str
    created_at: datetime


class AttachmentPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str


class AttachmentPresignResponse(BaseModel):
    attachment_id: int
    upload_url: str
    upload_fields: dict[str, str]


class AttachmentResponse(BaseModel):
    id: int
    ticket_id: int
    original_filename: str
    content_type: str
    size_bytes: Optional[int]
    created_at: datetime
    download_url: str
    thumbnail_url: str


class DashboardSummary(BaseModel):
    total_tickets: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
