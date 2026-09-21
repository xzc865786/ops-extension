from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.session import enforce_bootstrap_freshness, get_valid_session
from app.common.errors import forbidden, unauthorized
from app.config import get_settings
from app.db.session import get_db


@dataclass
class CurrentUser:
    id: int
    sub2api_user_id: int
    username_snapshot: str | None
    email_snapshot: str | None
    sub2api_role: str

    @property
    def is_admin(self) -> bool:
        return self.sub2api_role == "admin"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    settings = get_settings()
    sid = request.cookies.get(settings.cookie_name)
    if not sid:
        raise unauthorized()
    pair = get_valid_session(db, sid)
    if not pair:
        raise unauthorized("会话已过期", "SESSION_EXPIRED")
    sess, user = pair
    user = enforce_bootstrap_freshness(db, sess, user)
    if user.sub2api_role not in ("user", "admin"):
        raise forbidden("不支持的角色")
    return CurrentUser(
        id=user.id,
        sub2api_user_id=user.sub2api_user_id,
        username_snapshot=user.username_snapshot,
        email_snapshot=user.email_snapshot,
        sub2api_role=user.sub2api_role,
    )


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise forbidden("需要管理员权限", "ADMIN_REQUIRED")
    return user


def require_login(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user
