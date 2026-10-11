from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update

from app.common import vault
from app.common.errors import conflict, not_found
from app.db.models.account import AccountEvent, AccountRecord
from app.ledger.rates import today

STATUS_LABELS = {"ACTIVE": "启用", "STANDBY": "备用", "BANNED": "封禁", "DISABLED": "停用"}
CLIENT_SUGGESTIONS = ["Claude", "ChatGPT", "Google", "Gemini", "Cursor", "GitHub", "Microsoft", "Apple"]
PLAIN_FIELDS = ("client", "login", "status", "plan", "expires_on", "owner", "phone", "recovery_email", "notes")
SECRET_FIELDS = {"password": "password_enc", "secret_notes": "secret_notes_enc"}
SECRET_LABELS = {"password": "密码", "secret_notes": "敏感备注"}
EXPIRING_DAYS = 30


def identity(client, login):
    return client.casefold() + "\n" + login.casefold()


def context(row, field):
    return f"account:{row.id}:{field}"


def event(db, row, actor, kind, detail=None):
    db.add(AccountEvent(account_id=row.id, actor_user_id=actor.id, actor_name=actor.username_snapshot,
                        event_type=kind, detail=detail))


def plain(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def locked(db, account_id):
    row = db.scalar(select(AccountRecord).where(AccountRecord.id == account_id)
                    .with_for_update().execution_options(populate_existing=True))
    if not row:
        raise not_found("账号记录不存在")
    return row


def bump(db, row, expected, actor):
    now = datetime.now(timezone.utc)
    result = db.execute(update(AccountRecord).where(AccountRecord.id == row.id, AccountRecord.version == expected)
                        .values(version=expected + 1, updated_by=actor.id, updated_at=now)
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise conflict("账号记录已被其他管理员修改，请刷新后重试", "VERSION_CONFLICT")
    row.version, row.updated_by, row.updated_at = expected + 1, actor.id, now


def ensure_unique(db, row):
    if row.archived:
        return
    clash = db.scalar(select(AccountRecord.id).where(AccountRecord.active_identity == row.identity, AccountRecord.id != row.id))
    if clash:
        raise conflict(f"{row.client} 下已有账号 {row.login}（记录 #{clash}）", "ACCOUNT_DUPLICATE")


def set_secret(row, field, value):
    """Returns the audit wording for the change, or None when nothing changed. Plaintext never leaves this function."""
    column = SECRET_FIELDS[field]
    had = getattr(row, column) is not None
    if not value:
        setattr(row, column, None)
        return "已清除" if had else None
    setattr(row, column, vault.encrypt(value, context(row, field)))
    return "已修改" if had else "已设置"


def create(db, actor, body):
    secrets = {f: getattr(body, f) for f in SECRET_FIELDS if getattr(body, f)}
    if secrets:
        vault.require()
    row = AccountRecord(**body.model_dump(include=set(PLAIN_FIELDS)), identity=identity(body.client, body.login),
                        archived=False, version=1, created_by=actor.id, updated_by=actor.id)
    row.active_identity = row.identity
    ensure_unique(db, row)
    db.add(row)
    db.flush()
    changes = {f: set_secret(row, f, v) for f, v in secrets.items()}
    event(db, row, actor, "CREATED", {"after": {k: plain(getattr(row, k)) for k in PLAIN_FIELDS},
                                      "secrets": {SECRET_LABELS[f]: c for f, c in changes.items()}})
    db.commit()
    return row


def edit(db, actor, account_id, body):
    row = locked(db, account_id)
    if row.archived:
        raise conflict("已归档的账号请先恢复再编辑", "ACCOUNT_ARCHIVED")
    sent = body.model_fields_set
    secrets = {f: getattr(body, f) for f in SECRET_FIELDS if f in sent}
    if any(secrets.values()):
        vault.require()
    before = {k: plain(getattr(row, k)) for k in PLAIN_FIELDS}
    bump(db, row, body.version, actor)
    for k in PLAIN_FIELDS:
        setattr(row, k, getattr(body, k))
    row.identity = identity(row.client, row.login)
    row.active_identity = row.identity
    ensure_unique(db, row)
    changes = {SECRET_LABELS[f]: c for f, v in secrets.items() if (c := set_secret(row, f, v))}
    after = {k: plain(getattr(row, k)) for k in PLAIN_FIELDS}
    diff = {k: [before[k], after[k]] for k in PLAIN_FIELDS if before[k] != after[k]}
    event(db, row, actor, "UPDATED", {"changes": diff, "secrets": changes})
    db.commit()
    return row


def change_status(db, actor, account_id, body):
    row = locked(db, account_id)
    if row.archived:
        raise conflict("已归档的账号请先恢复", "ACCOUNT_ARCHIVED")
    old = row.status
    bump(db, row, body.version, actor)
    row.status = body.status
    event(db, row, actor, "STATUS_CHANGED", {"changes": {"status": [old, body.status]}})
    db.commit()
    return row


def set_archived(db, actor, account_id, body, archived):
    row = locked(db, account_id)
    if row.archived == archived:
        raise conflict("账号已归档" if archived else "账号未归档", "ACCOUNT_ARCHIVE_STATE")
    bump(db, row, body.version, actor)
    row.archived = archived
    row.active_identity = None if archived else row.identity
    ensure_unique(db, row)
    event(db, row, actor, "ARCHIVED" if archived else "RESTORED")
    db.commit()
    return row


def reveal(db, actor, account_id, body):
    row = db.get(AccountRecord, account_id)
    if not row:
        raise not_found("账号记录不存在")
    token = getattr(row, SECRET_FIELDS[body.field])
    if token is None:
        raise not_found(f"未保存{SECRET_LABELS[body.field]}")
    value = vault.decrypt(token, context(row, body.field))
    event(db, row, actor, "SECRET_COPIED" if body.purpose == "copy" else "SECRET_VIEWED", {"field": SECRET_LABELS[body.field]})
    db.commit()
    return value


def output(row, now=None):
    now = now or today()
    expiry = None
    if row.expires_on:
        expiry = "EXPIRED" if row.expires_on < now else "SOON" if row.expires_on <= now + timedelta(days=EXPIRING_DAYS) else None
    return {**{k: plain(getattr(row, k)) for k in PLAIN_FIELDS},
            "id": row.id, "status_label": STATUS_LABELS[row.status], "archived": row.archived, "version": row.version,
            "has_password": row.password_enc is not None, "has_secret_notes": row.secret_notes_enc is not None,
            "expiry": expiry, "created_at": plain(row.created_at), "updated_at": plain(row.updated_at)}


def listing(db, *, client="", status="", keyword="", archived=False):
    rows = db.scalars(select(AccountRecord).where(AccountRecord.archived.is_(archived))).all()
    clients, statuses = {}, dict.fromkeys(STATUS_LABELS, 0)
    for r in rows:
        clients[r.client] = clients.get(r.client, 0) + 1
        if not client or r.client == client:
            statuses[r.status] += 1
    if keyword:
        needle = keyword.casefold()
        rows = [r for r in rows if any(needle in (getattr(r, k) or "").casefold() for k in ("login", "owner", "plan", "notes", "client"))]
    rows = [r for r in rows if (not client or r.client == client) and (not status or r.status == status)]
    now = today()
    # Expired and soon-to-expire accounts first, then by client and login.
    soon = now + timedelta(days=EXPIRING_DAYS)
    rows.sort(key=lambda r: (not (r.expires_on and r.expires_on <= soon), r.expires_on or date.max, r.client.casefold(), r.login.casefold()))
    return {"items": [output(r, now) for r in rows],
            "clients": [{"client": c, "count": n} for c, n in sorted(clients.items(), key=lambda x: (-x[1], x[0].casefold()))],
            "statuses": statuses}


def detail(db, account_id):
    row = db.get(AccountRecord, account_id)
    if not row:
        raise not_found("账号记录不存在")
    events = db.scalars(select(AccountEvent).where(AccountEvent.account_id == row.id).order_by(AccountEvent.id.desc())).all()
    return {**output(row), "events": [{"id": e.id, "event_type": e.event_type, "actor_name": e.actor_name,
                                       "actor_user_id": e.actor_user_id, "detail": e.detail, "created_at": plain(e.created_at)}
                                      for e in events]}


def meta(db):
    used = db.scalars(select(AccountRecord.client).distinct()).all()
    clients = list(dict.fromkeys([*sorted(used, key=str.casefold), *CLIENT_SUGGESTIONS]))
    def distinct(column):
        return db.scalars(select(column).where(column != "").distinct().order_by(column)).all()
    return {"clients": clients, "owners": distinct(AccountRecord.owner), "plans": distinct(AccountRecord.plan),
            "statuses": [{"value": k, "label": v} for k, v in STATUS_LABELS.items()], "vault_ready": vault.ready()}
