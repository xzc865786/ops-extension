import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.session import create_session, destroy_session, upsert_extension_user
from app.common.errors import forbidden, unauthorized
from app.config import get_settings
from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.identity.sub2api import get_identity_provider

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


def _sanitize_next(next_path: str | None) -> str:
    default = "/ext/app/tickets"
    if not next_path:
        return default
    if not next_path.startswith("/"):
        return default
    if "//" in next_path or "\\" in next_path:
        return default
    parsed = urlparse(next_path)
    if parsed.scheme or parsed.netloc:
        return default
    if not next_path.startswith("/ext/app"):
        return default
    return next_path


@router.get("/ext/auth/bootstrap")
def bootstrap(
    request: Request,
    db: Session = Depends(get_db),
    token: str | None = None,
    user_id: int | None = None,
    next: str | None = None,
    theme: str | None = None,
    lang: str | None = None,
    ui_mode: str | None = None,
):
    """Auth Bridge: verify Sub2API token via /auth/me, create session cookie, 302 without token."""
    settings = get_settings()
    headers = {
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
    }
    if not token:
        raise unauthorized("缺少 token", "MISSING_TOKEN")

    provider = get_identity_provider()
    # Never log token / Authorization
    remote = provider.verify_and_get_user(token)

    if remote.status != "active":
        logger.info(
            "bootstrap rejected non-active user sub2api_id=%s status=%s",
            remote.id,
            remote.status,
        )
        raise forbidden("用户状态不可用", "USER_INACTIVE")

    if remote.role not in ("user", "admin"):
        raise forbidden("不支持的角色", "UNSUPPORTED_ROLE")

    if user_id is not None and int(user_id) != int(remote.id):
        logger.warning(
            "bootstrap user_id mismatch query=%s me.id=%s",
            user_id,
            remote.id,
        )
        raise forbidden("用户身份不一致", "USER_MISMATCH")

    user = upsert_extension_user(
        db,
        sub2api_user_id=remote.id,
        username=remote.username,
        email=remote.email,
        role=remote.role,
    )
    client_ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    sess = create_session(db, user, ip=client_ip, user_agent=ua, bearer_token=token)

    dest = _sanitize_next(next)
    redirect = RedirectResponse(url=dest, status_code=302, headers=headers)
    redirect.set_cookie(
        key=settings.cookie_name,
        value=str(sess.id),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/ext",
        max_age=settings.session_ttl_hours * 3600,
    )
    if theme:
        redirect.set_cookie("ops_theme", theme, path="/ext", max_age=86400 * 30)
    if lang:
        redirect.set_cookie("ops_lang", lang, path="/ext", max_age=86400 * 30)
    if ui_mode:
        redirect.set_cookie("ops_ui_mode", ui_mode, path="/ext", max_age=86400 * 30)
    return redirect


@router.post("/ext/api/v1/auth/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    settings = get_settings()
    sid = request.cookies.get(settings.cookie_name)
    if sid:
        destroy_session(db, sid)
    resp = Response(content='{"ok":true}', media_type="application/json")
    resp.delete_cookie(settings.cookie_name, path="/ext")
    return resp


@router.get("/ext/api/v1/auth/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return {
        "id": user.id,
        "sub2api_user_id": user.sub2api_user_id,
        "username": user.username_snapshot,
        "email": user.email_snapshot,
        "sub2api_role": user.sub2api_role,
    }
