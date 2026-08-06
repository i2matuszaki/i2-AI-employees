from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.database.session import create_session_factory, get_db_session
from app.main import app
from app.models import Meeting, MeetingParticipant, User
from app.security.password import hash_password
from app.security.session import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

TEST_PASSWORD = "fictional-meeting-password"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)
START = datetime(2026, 8, 10, 1, 0, tzinfo=UTC)


@pytest.fixture
def session_factory(test_engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(test_engine)


@pytest.fixture
def users(session_factory: sessionmaker[Session]) -> dict[str, str]:
    records = [
        User(
            email=f"{name}@example.test",
            display_name=display_name,
            role=role,
            password_hash=TEST_PASSWORD_HASH,
        )
        for name, display_name, role in (
            ("creator", "作成者", "user"),
            ("organizer", "主催者", "approver"),
            ("alpha", "あ参加者", "user"),
            ("beta", "い参加者", "admin"),
            ("gamma", "う参加者", "user"),
        )
    ]
    with session_factory() as session:
        session.add_all(records)
        session.commit()
        return {record.email.split("@")[0]: record.id for record in records}


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    users: dict[str, str],
) -> Iterator[TestClient]:
    del users

    def override_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: Settings.from_env({})
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client: TestClient) -> TestClient:
    response = client.post(
        "/api/auth/login",
        json={"email": "creator@example.test", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return client


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]}


def meeting_payload(users: dict[str, str], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "  定例会議  ",
        "scheduled_start_at": START.isoformat(),
        "scheduled_end_at": (START + timedelta(hours=1)).isoformat(),
        "organizer_user_id": users["organizer"],
    }
    payload.update(overrides)
    return payload


def create_via_api(
    client: TestClient,
    users: dict[str, str],
    **overrides: object,
) -> dict[str, object]:
    response = client.post(
        "/api/meetings",
        headers=csrf_headers(client),
        json=meeting_payload(users, **overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def seed_meeting(
    session_factory: sessionmaker[Session],
    users: dict[str, str],
    *,
    title: str = "保存済み会議",
    start: datetime = START,
    meeting_id: str | None = None,
    participants: list[tuple[str, str, str]] | None = None,
    **overrides: object,
) -> str:
    values: dict[str, object] = {
        "title": title,
        "status": "scheduled",
        "scheduled_start_at": start,
        "scheduled_end_at": start + timedelta(hours=1),
        "organizer_user_id": users["organizer"],
        "created_by_user_id": users["creator"],
    }
    values.update(overrides)
    if meeting_id is not None:
        values["id"] = meeting_id
    meeting = Meeting(**values)
    for user_name, role, attendance in participants or []:
        meeting.participants.append(
            MeetingParticipant(
                user_id=users[user_name],
                participant_role=role,
                attendance_status=attendance,
            )
        )
    with session_factory() as session:
        session.add(meeting)
        session.commit()
        return meeting.id


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/api/meetings", {}),
        ("get", "/api/meetings", None),
        ("get", f"/api/meetings/{uuid4()}", None),
        ("patch", f"/api/meetings/{uuid4()}", {}),
        ("delete", f"/api/meetings/{uuid4()}", None),
    ],
)
def test_all_meeting_apis_require_authentication(
    client: TestClient,
    method: str,
    path: str,
    json_body: dict[str, object] | None,
) -> None:
    response = client.request(method, path, json=json_body)
    assert response.status_code == 401
    assert response.json() == {"detail": "認証できませんでした。"}


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
@pytest.mark.parametrize("csrf_state", ["missing", "invalid"])
def test_mutations_require_valid_csrf(
    authenticated_client: TestClient,
    method: str,
    csrf_state: str,
) -> None:
    path = "/api/meetings" if method == "post" else f"/api/meetings/{uuid4()}"
    headers = {} if csrf_state == "missing" else {CSRF_HEADER_NAME: "invalid"}
    response = authenticated_client.request(method, path, headers=headers, json={})
    assert response.status_code == 403


def test_get_does_not_require_csrf(authenticated_client: TestClient) -> None:
    assert authenticated_client.get("/api/meetings").status_code == 200


def test_create_meeting_without_participants_uses_defaults_and_authenticated_creator(
    authenticated_client: TestClient,
    users: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    response = authenticated_client.post(
        "/api/meetings",
        headers=csrf_headers(authenticated_client),
        json=meeting_payload(users),
        follow_redirects=False,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "定例会議"
    assert body["status"] == "scheduled"
    assert body["participants"] == []
    assert body["created_by"]["id"] == users["creator"]
    with session_factory() as session:
        meeting = session.get(Meeting, body["id"])
        assert meeting is not None
        assert meeting.created_by_user_id == users["creator"]


def test_create_meeting_with_participants_uses_attendance_default(
    authenticated_client: TestClient,
    users: dict[str, str],
) -> None:
    body = create_via_api(
        authenticated_client,
        users,
        participants=[
            {"user_id": users["alpha"], "participant_role": "participant"},
            {
                "user_id": users["beta"],
                "participant_role": "observer",
                "attendance_status": "accepted",
            },
        ],
    )
    assert [item["attendance_status"] for item in body["participants"]] == [
        "invited",
        "accepted",
    ]


@pytest.mark.parametrize(
    ("overrides", "expected_status"),
    [
        ({"created_by_user_id": str(uuid4())}, 422),
        ({"organizer_user_id": str(uuid4())}, 422),
        (
            {
                "participants": [
                    {"user_id": str(uuid4()), "participant_role": "participant"}
                ]
            },
            422,
        ),
        (
            {
                "participants": [
                    {"user_id": "{alpha}", "participant_role": "participant"},
                    {"user_id": "{alpha}", "participant_role": "observer"},
                ]
            },
            422,
        ),
        ({"scheduled_end_at": START.isoformat()}, 422),
        ({"actual_end_at": (START + timedelta(hours=1)).isoformat()}, 422),
        ({"actual_start_at": (START + timedelta(hours=2)).isoformat(), "actual_end_at": (START + timedelta(hours=1)).isoformat()}, 422),
        ({"scheduled_start_at": "2026-08-10T01:00:00"}, 422),
        ({"status": "unknown"}, 422),
        ({"title": "   "}, 422),
    ],
)
def test_create_rejects_invalid_input(
    authenticated_client: TestClient,
    users: dict[str, str],
    overrides: dict[str, object],
    expected_status: int,
) -> None:
    resolved = str(overrides).replace("{alpha}", users["alpha"])
    import ast

    values = ast.literal_eval(resolved)
    response = authenticated_client.post(
        "/api/meetings",
        headers=csrf_headers(authenticated_client),
        json=meeting_payload(users, **values),
    )
    assert response.status_code == expected_status


def test_create_integrity_failure_rolls_back_and_hides_database_details(
    authenticated_client: TestClient,
    users: dict[str, str],
    session_factory: sessionmaker[Session],
    test_engine: Engine,
) -> None:
    def fail_participant_insert(
        _connection: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().lower().startswith("insert into meeting_participants"):
            raise IntegrityError(statement, parameters, Exception("secret constraint detail"))

    event.listen(test_engine, "before_cursor_execute", fail_participant_insert)
    try:
        response = authenticated_client.post(
            "/api/meetings",
            headers=csrf_headers(authenticated_client),
            json=meeting_payload(
                users,
                participants=[
                    {"user_id": users["alpha"], "participant_role": "participant"}
                ],
            ),
        )
    finally:
        event.remove(test_engine, "before_cursor_execute", fail_participant_insert)
    assert response.status_code == 409
    assert response.json() == {"detail": "データベースの整合性競合が発生しました。"}
    assert "secret" not in response.text
    assert "insert" not in response.text.lower()
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Meeting)) == 0
        assert session.scalar(select(func.count()).select_from(MeetingParticipant)) == 0


def test_list_empty(authenticated_client: TestClient) -> None:
    assert authenticated_client.get("/api/meetings").json() == {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }


def test_list_orders_pages_counts_and_omits_participants(
    authenticated_client: TestClient,
    users: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    later_id = "00000000-0000-4000-8000-000000000002"
    first_id = "00000000-0000-4000-8000-000000000001"
    seed_meeting(session_factory, users, title="後ID", meeting_id=later_id, participants=[])
    seed_meeting(
        session_factory,
        users,
        title="前ID",
        meeting_id=first_id,
        participants=[
            ("alpha", "participant", "invited"),
            ("beta", "observer", "accepted"),
        ],
    )
    seed_meeting(session_factory, users, title="翌日", start=START + timedelta(days=1))
    response = authenticated_client.get("/api/meetings?limit=1&offset=0")
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 3
    assert body["limit"] == 1
    assert [item["id"] for item in body["items"]] == [first_id]
    assert body["items"][0]["participant_count"] == 2
    assert "participants" not in body["items"][0]
    second_page = authenticated_client.get("/api/meetings?limit=1&offset=1").json()
    assert second_page["items"][0]["id"] == later_id
    assert second_page["items"][0]["participant_count"] == 0


def test_list_filters(
    authenticated_client: TestClient,
    users: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    target = seed_meeting(session_factory, users, status="completed")
    other = seed_meeting(
        session_factory,
        users,
        title="別会議",
        start=START + timedelta(days=2),
        organizer_user_id=users["alpha"],
        created_by_user_id=users["beta"],
    )
    queries = [
        ("status=completed", [target]),
        (f"organizer_user_id={users['organizer']}", [target]),
        (f"created_by_user_id={users['creator']}", [target]),
        (f"scheduled_from={START.isoformat()}", [target, other]),
        (f"scheduled_to={(START + timedelta(days=1)).isoformat()}", [target]),
        (
            f"scheduled_from={START.isoformat()}&scheduled_to={(START + timedelta(days=1)).isoformat()}",
            [target],
        ),
    ]
    for query, expected_ids in queries:
        response = authenticated_client.get(f"/api/meetings?{query.replace('+', '%2B')}")
        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == expected_ids


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
        "scheduled_from=2026-08-10T02:00:00%2B00:00&scheduled_to=2026-08-10T01:00:00%2B00:00",
        "scheduled_from=2026-08-10T01:00:00&scheduled_to=2026-08-10T02:00:00%2B00:00",
    ],
)
def test_list_rejects_invalid_query(authenticated_client: TestClient, query: str) -> None:
    assert authenticated_client.get(f"/api/meetings?{query}").status_code == 422


def test_list_nonexistent_uuid_filter_returns_empty(authenticated_client: TestClient) -> None:
    response = authenticated_client.get(f"/api/meetings?organizer_user_id={uuid4()}")
    assert response.status_code == 200
    assert response.json()["items"] == []


def count_selects_for_request(client: TestClient, engine: Engine, path: str) -> int:
    statements: list[str] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert client.get(path).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return len(statements)


def test_list_select_count_does_not_grow_with_meetings(
    authenticated_client: TestClient,
    users: dict[str, str],
    session_factory: sessionmaker[Session],
    test_engine: Engine,
) -> None:
    seed_meeting(session_factory, users)
    one_count = count_selects_for_request(authenticated_client, test_engine, "/api/meetings")
    for index in range(4):
        seed_meeting(session_factory, users, title=f"追加{index}", start=START + timedelta(days=index + 1))
    many_count = count_selects_for_request(authenticated_client, test_engine, "/api/meetings")
    assert many_count == one_count


def test_detail_returns_users_and_sorted_participants(
    authenticated_client: TestClient,
    users: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    meeting_id = seed_meeting(
        session_factory,
        users,
        participants=[
            ("gamma", "observer", "invited"),
            ("beta", "participant", "accepted"),
            ("alpha", "participant", "attended"),
            ("organizer", "organizer", "accepted"),
        ],
    )
    response = authenticated_client.get(f"/api/meetings/{meeting_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["organizer"]["id"] == users["organizer"]
    assert body["created_by"]["id"] == users["creator"]
    assert [item["participant_role"] for item in body["participants"]] == [
        "organizer",
        "participant",
        "participant",
        "observer",
    ]
    assert [item["user"]["display_name"] for item in body["participants"]][1:3] == [
        "あ参加者",
        "い参加者",
    ]


@pytest.mark.parametrize(
    ("meeting_id", "expected"),
    [("not-a-uuid", 422), (str(uuid4()), 404)],
)
def test_detail_rejects_invalid_or_missing_id(
    authenticated_client: TestClient,
    meeting_id: str,
    expected: int,
) -> None:
    assert authenticated_client.get(f"/api/meetings/{meeting_id}").status_code == expected


def test_detail_select_count_does_not_grow_with_participants(
    authenticated_client: TestClient,
    users: dict[str, str],
    session_factory: sessionmaker[Session],
    test_engine: Engine,
) -> None:
    one_id = seed_meeting(session_factory, users, participants=[("alpha", "participant", "invited")])
    many_id = seed_meeting(
        session_factory,
        users,
        start=START + timedelta(days=1),
        participants=[
            ("alpha", "participant", "invited"),
            ("beta", "participant", "invited"),
            ("gamma", "observer", "invited"),
        ],
    )
    one_count = count_selects_for_request(authenticated_client, test_engine, f"/api/meetings/{one_id}")
    many_count = count_selects_for_request(authenticated_client, test_engine, f"/api/meetings/{many_id}")
    assert many_count == one_count


def test_patch_updates_fields_and_nullable_values(
    authenticated_client: TestClient,
    users: dict[str, str],
) -> None:
    body = create_via_api(
        authenticated_client,
        users,
        description="説明",
        actual_start_at=START.isoformat(),
        actual_end_at=(START + timedelta(minutes=30)).isoformat(),
    )
    response = authenticated_client.patch(
        f"/api/meetings/{body['id']}",
        headers=csrf_headers(authenticated_client),
        json={"title": "  更新後  ", "description": None, "actual_end_at": None},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "更新後"
    assert updated["description"] is None
    assert updated["actual_start_at"] is not None
    assert updated["actual_end_at"] is None


def test_patch_can_clear_actual_times_in_one_request(
    authenticated_client: TestClient,
    users: dict[str, str],
) -> None:
    body = create_via_api(
        authenticated_client,
        users,
        actual_start_at=START.isoformat(),
        actual_end_at=(START + timedelta(minutes=30)).isoformat(),
    )
    response = authenticated_client.patch(
        f"/api/meetings/{body['id']}",
        headers=csrf_headers(authenticated_client),
        json={"actual_start_at": None, "actual_end_at": None},
    )
    assert response.status_code == 200
    assert response.json()["actual_start_at"] is None
    assert response.json()["actual_end_at"] is None


def test_patch_changes_organizer_and_replaces_or_preserves_participants(
    authenticated_client: TestClient,
    users: dict[str, str],
) -> None:
    body = create_via_api(
        authenticated_client,
        users,
        participants=[{"user_id": users["alpha"], "participant_role": "participant"}],
    )
    preserved = authenticated_client.patch(
        f"/api/meetings/{body['id']}",
        headers=csrf_headers(authenticated_client),
        json={"organizer_user_id": users["beta"]},
    ).json()
    assert preserved["organizer"]["id"] == users["beta"]
    assert [item["user"]["id"] for item in preserved["participants"]] == [users["alpha"]]
    replaced = authenticated_client.patch(
        f"/api/meetings/{body['id']}",
        headers=csrf_headers(authenticated_client),
        json={"participants": [{"user_id": users["gamma"], "participant_role": "observer"}]},
    ).json()
    assert [item["user"]["id"] for item in replaced["participants"]] == [users["gamma"]]
    cleared = authenticated_client.patch(
        f"/api/meetings/{body['id']}",
        headers=csrf_headers(authenticated_client),
        json={"participants": []},
    ).json()
    assert cleared["participants"] == []


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"created_by_user_id": str(uuid4())}, 422),
        ({"unknown": "value"}, 422),
        ({"organizer_user_id": str(uuid4())}, 422),
        ({"participants": [{"user_id": str(uuid4()), "participant_role": "observer"}]}, 422),
        ({"scheduled_start_at": (START + timedelta(hours=2)).isoformat()}, 422),
        ({"actual_start_at": None}, 422),
        ({"title": None}, 422),
    ],
)
def test_patch_rejects_invalid_input_or_merged_state(
    authenticated_client: TestClient,
    users: dict[str, str],
    payload: dict[str, object],
    expected: int,
) -> None:
    body = create_via_api(
        authenticated_client,
        users,
        actual_start_at=START.isoformat(),
        actual_end_at=(START + timedelta(minutes=30)).isoformat(),
    )
    response = authenticated_client.patch(
        f"/api/meetings/{body['id']}",
        headers=csrf_headers(authenticated_client),
        json=payload,
    )
    assert response.status_code == expected


def test_patch_rejects_duplicate_participants(
    authenticated_client: TestClient,
    users: dict[str, str],
) -> None:
    body = create_via_api(authenticated_client, users)
    response = authenticated_client.patch(
        f"/api/meetings/{body['id']}",
        headers=csrf_headers(authenticated_client),
        json={
            "participants": [
                {"user_id": users["alpha"], "participant_role": "participant"},
                {"user_id": users["alpha"].upper(), "participant_role": "observer"},
            ]
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(("meeting_id", "expected"), [("bad", 422), (str(uuid4()), 404)])
def test_patch_rejects_invalid_or_missing_id(
    authenticated_client: TestClient,
    meeting_id: str,
    expected: int,
) -> None:
    response = authenticated_client.patch(
        f"/api/meetings/{meeting_id}", headers=csrf_headers(authenticated_client), json={}
    )
    assert response.status_code == expected


def test_patch_failure_rolls_back_meeting_and_participants(
    authenticated_client: TestClient,
    users: dict[str, str],
    session_factory: sessionmaker[Session],
    test_engine: Engine,
) -> None:
    body = create_via_api(
        authenticated_client,
        users,
        participants=[{"user_id": users["alpha"], "participant_role": "participant"}],
    )

    def fail_insert(
        _connection: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().lower().startswith("insert into meeting_participants"):
            raise IntegrityError(statement, parameters, Exception("failure"))

    event.listen(test_engine, "before_cursor_execute", fail_insert)
    try:
        response = authenticated_client.patch(
            f"/api/meetings/{body['id']}",
            headers=csrf_headers(authenticated_client),
            json={
                "title": "失敗する更新",
                "participants": [
                    {"user_id": users["beta"], "participant_role": "observer"}
                ],
            },
        )
    finally:
        event.remove(test_engine, "before_cursor_execute", fail_insert)
    assert response.status_code == 409
    with session_factory() as session:
        meeting = session.get(Meeting, body["id"])
        assert meeting is not None
        assert meeting.title == "定例会議"
        participant_ids = set(
            session.scalars(
                select(MeetingParticipant.user_id).where(
                    MeetingParticipant.meeting_id == body["id"]
                )
            )
        )
        assert participant_ids == {users["alpha"]}


def test_delete_uses_database_cascade_without_participant_mutation(
    authenticated_client: TestClient,
    users: dict[str, str],
    session_factory: sessionmaker[Session],
    test_engine: Engine,
) -> None:
    meeting_id = seed_meeting(
        session_factory,
        users,
        participants=[("alpha", "participant", "invited")],
    )
    statements: list[str] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.lower())

    event.listen(test_engine, "before_cursor_execute", record)
    try:
        response = authenticated_client.delete(
            f"/api/meetings/{meeting_id}", headers=csrf_headers(authenticated_client)
        )
    finally:
        event.remove(test_engine, "before_cursor_execute", record)
    assert response.status_code == 204
    assert response.content == b""
    participant_mutations = [
        statement
        for statement in statements
        if statement.lstrip().startswith(("update", "delete"))
        and "meeting_participants" in statement
    ]
    assert participant_mutations == []
    with session_factory() as session:
        assert session.get(Meeting, meeting_id) is None
        assert session.scalar(
            select(func.count())
            .select_from(MeetingParticipant)
            .where(MeetingParticipant.meeting_id == meeting_id)
        ) == 0


@pytest.mark.parametrize(("meeting_id", "expected"), [("bad", 422), (str(uuid4()), 404)])
def test_delete_rejects_invalid_or_missing_id(
    authenticated_client: TestClient,
    meeting_id: str,
    expected: int,
) -> None:
    response = authenticated_client.delete(
        f"/api/meetings/{meeting_id}", headers=csrf_headers(authenticated_client)
    )
    assert response.status_code == expected
