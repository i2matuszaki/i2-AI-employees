from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.dependencies.auth import AuthenticatedSession, get_authenticated_session, require_csrf
from app.models import MeetingStatus
from app.schemas.meeting import (
    MeetingCreate,
    MeetingDetailResponse,
    MeetingListResponse,
    MeetingUpdate,
)
from app.services.meeting import (
    create_meeting,
    delete_meeting,
    get_meeting_detail,
    list_meetings,
    update_meeting,
)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


@router.post("", response_model=MeetingDetailResponse, status_code=status.HTTP_201_CREATED)
def create_meeting_endpoint(
    request: MeetingCreate,
    authenticated: Annotated[AuthenticatedSession, Depends(require_csrf)],
) -> MeetingDetailResponse:
    return create_meeting(
        authenticated.db_session,
        request,
        created_by_user_id=authenticated.user.id,
    )


@router.get("", response_model=MeetingListResponse)
def list_meetings_endpoint(
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
    meeting_status: Annotated[MeetingStatus | None, Query(alias="status")] = None,
    organizer_user_id: UUID | None = None,
    created_by_user_id: UUID | None = None,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MeetingListResponse:
    return list_meetings(
        authenticated.db_session,
        meeting_status=meeting_status.value if meeting_status is not None else None,
        organizer_user_id=str(organizer_user_id) if organizer_user_id is not None else None,
        created_by_user_id=str(created_by_user_id) if created_by_user_id is not None else None,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
        limit=limit,
        offset=offset,
    )


@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
def get_meeting_endpoint(
    meeting_id: UUID,
    authenticated: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
) -> MeetingDetailResponse:
    return get_meeting_detail(authenticated.db_session, str(meeting_id))


@router.patch("/{meeting_id}", response_model=MeetingDetailResponse)
def update_meeting_endpoint(
    meeting_id: UUID,
    request: MeetingUpdate,
    authenticated: Annotated[AuthenticatedSession, Depends(require_csrf)],
) -> MeetingDetailResponse:
    return update_meeting(authenticated.db_session, str(meeting_id), request)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting_endpoint(
    meeting_id: UUID,
    authenticated: Annotated[AuthenticatedSession, Depends(require_csrf)],
) -> Response:
    delete_meeting(authenticated.db_session, str(meeting_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
