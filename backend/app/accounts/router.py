from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts import service
from app.accounts.schemas import AccountCreate, AccountUpdate, Reveal, StatusChange, VersionOnly
from app.common.errors import conflict
from app.db.session import get_db
from app.deps import CurrentUser, require_admin

router = APIRouter(prefix="/ext/api/v1/admin/accounts", tags=["accounts"], dependencies=[Depends(require_admin)])


def mutate(db, operation):
    try:
        return operation()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("同一客户端下已有相同账号，或记录已被其他操作修改，请刷新后重试", "CONCURRENT_CONFLICT") from exc
    except Exception:
        db.rollback()
        raise


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    return service.meta(db)


@router.get("")
def listing(client: str = Query("", max_length=50), status: str = Query("", pattern="^(|ACTIVE|STANDBY|BANNED|DISABLED)$"),
            keyword: str = Query("", max_length=200), archived: bool = False, db: Session = Depends(get_db)):
    return service.listing(db, client=client.strip(), status=status, keyword=keyword.strip(), archived=archived)


@router.post("", status_code=201)
def create(body: AccountCreate, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    row = mutate(db, lambda: service.create(db, actor, body))
    return service.detail(db, row.id)


@router.get("/{account_id}")
def detail(account_id: int, db: Session = Depends(get_db)):
    return service.detail(db, account_id)


@router.patch("/{account_id}")
def edit(account_id: int, body: AccountUpdate, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    mutate(db, lambda: service.edit(db, actor, account_id, body))
    return service.detail(db, account_id)


@router.post("/{account_id}/status")
def change_status(account_id: int, body: StatusChange, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    return service.output(mutate(db, lambda: service.change_status(db, actor, account_id, body)))


@router.post("/{account_id}/archive")
def archive(account_id: int, body: VersionOnly, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    mutate(db, lambda: service.set_archived(db, actor, account_id, body, True))
    return service.detail(db, account_id)


@router.post("/{account_id}/restore")
def restore(account_id: int, body: VersionOnly, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    mutate(db, lambda: service.set_archived(db, actor, account_id, body, False))
    return service.detail(db, account_id)


@router.post("/{account_id}/reveal")
def reveal(account_id: int, body: Reveal, response: Response, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    # POST so the plaintext never lands in URLs, proxies' access logs or browser history; each call is audited.
    response.headers["Cache-Control"] = "no-store"
    return {"value": mutate(db, lambda: service.reveal(db, actor, account_id, body))}
