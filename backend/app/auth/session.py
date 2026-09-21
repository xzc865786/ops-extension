import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db.models.user import ExtensionUser, Session as UserSession


def create_session(
    db: DbSession,
    user: ExtensionUser,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> UserSession:
    settings = get_settings()
    sess = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def get_valid_session(db: DbSession, session_id: str) -> tuple[UserSession, ExtensionUser] | None:
    try:
        sid = uuid.UUID(session_id)
    except (ValueError, TypeError):
        return None
    sess = db.get(UserSession, sid)
    if not sess:
        return None
    now = datetime.now(timezone.utc)
    exp = sess.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= now:
        db.delete(sess)
        db.commit()
        return None
    user = db.get(ExtensionUser, sess.user_id)
    if not user:
        return None
    return sess, user


def destroy_session(db: DbSession, session_id: str) -> None:
    try:
        sid = uuid.UUID(session_id)
    except (ValueError, TypeError):
        return
    sess = db.get(UserSession, sid)
    if sess:
        db.delete(sess)
        db.commit()


def upsert_extension_user(
    db: DbSession,
    *,
    sub2api_user_id: int,
    username: str,
    email: str,
    role: str,
) -> ExtensionUser:
    user = (
        db.query(ExtensionUser)
        .filter(ExtensionUser.sub2api_user_id == sub2api_user_id)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if user is None:
        user = ExtensionUser(
            sub2api_user_id=sub2api_user_id,
            username_snapshot=username,
            email_snapshot=email,
            sub2api_role=role,
            extension_role=None,
            last_login_at=now,
        )
        db.add(user)
    else:
        user.username_snapshot = username
        user.email_snapshot = email
        user.sub2api_role = role
        user.last_login_at = now
        user.updated_at = now
    db.commit()
    db.refresh(user)
    return user
