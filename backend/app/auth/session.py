import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DbSession

from app.auth.token_seal import seal_token, unseal_token
from app.common.errors import AppError, unauthorized
from app.config import get_settings
from app.db.models.user import ExtensionUser, Session as UserSession

logger = logging.getLogger(__name__)


def create_session(
    db: DbSession,
    user: ExtensionUser,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    bearer_token: str | None = None,
) -> UserSession:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    token_enc = seal_token(settings.session_secret, bearer_token) if bearer_token else None
    sess = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        ip=ip,
        user_agent=user_agent,
        token_enc=token_enc,
        last_checked_at=now,
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


def revalidate_session_if_needed(
    db: DbSession,
    sess: UserSession,
    user: ExtensionUser,
) -> ExtensionUser:
    """Periodically re-check Sub2API /auth/me; clear session + 401 if inactive/auth fails.

    Sessions without a sealed token (tests / legacy) skip the remote call.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    last = sess.last_checked_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    interval = max(0, int(settings.session_revalidate_seconds))
    if last is not None and (now - last).total_seconds() < interval:
        return user
    if not sess.token_enc:
        sess.last_checked_at = now
        db.commit()
        return user

    token = unseal_token(settings.session_secret, sess.token_enc)
    if not token:
        logger.info("session revalidate: token unseal failed sid=%s", sess.id)
        db.delete(sess)
        db.commit()
        raise unauthorized("会话已失效", "SESSION_REVALIDATE_FAILED")

    from app.identity.sub2api import get_identity_provider

    provider = get_identity_provider()
    try:
        remote = provider.verify_and_get_user(token)
    except AppError:
        logger.info("session revalidate: auth/me failed sid=%s", sess.id)
        db.delete(sess)
        db.commit()
        raise unauthorized("会话已失效", "SESSION_REVALIDATE_FAILED")
    except Exception:
        logger.warning("session revalidate: unexpected error sid=%s", sess.id)
        db.delete(sess)
        db.commit()
        raise unauthorized("会话已失效", "SESSION_REVALIDATE_FAILED")

    if remote.status != "active":
        logger.info(
            "session revalidate: inactive sub2api_id=%s status=%s",
            remote.id,
            remote.status,
        )
        db.delete(sess)
        db.commit()
        raise unauthorized("用户状态不可用", "USER_INACTIVE")

    if int(remote.id) != int(user.sub2api_user_id):
        logger.warning(
            "session revalidate: id mismatch sess_user=%s me.id=%s",
            user.sub2api_user_id,
            remote.id,
        )
        db.delete(sess)
        db.commit()
        raise unauthorized("会话已失效", "SESSION_REVALIDATE_FAILED")

    if remote.role not in ("user", "admin"):
        db.delete(sess)
        db.commit()
        raise unauthorized("不支持的角色", "UNSUPPORTED_ROLE")

    user.username_snapshot = remote.username
    user.email_snapshot = remote.email
    user.sub2api_role = remote.role
    user.updated_at = now
    sess.last_checked_at = now
    db.commit()
    db.refresh(user)
    return user
