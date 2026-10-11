"""Isolated browser fixture: disposable SQLite, fixed quote, in-memory attachments.

Run with python -m tests.serve_ledger_browser. Never reads the project .env.
"""
import base64
import hashlib
import os
import tempfile
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path


def main():
    import uvicorn
    with tempfile.TemporaryDirectory(prefix='ops-ledger-browser-') as directory:
        os.environ.update(DATABASE_URL='sqlite+pysqlite:///'+(Path(directory)/'test.db').as_posix(),
                          DEV_AUTH_BYPASS='true', COOKIE_SECURE='false', SESSION_SECRET='isolated-browser-test',
                          ACCOUNT_VAULT_KEY=base64.b64encode(os.urandom(32)).decode())
        from app.config import get_settings, Settings
        Settings.model_config = {**Settings.model_config, "env_file": None}
        get_settings.cache_clear()
        # An env_file must not point this fixture at external services.
        get_settings().legacy_expense_writes_enabled=False
        from app.db.base import Base
        from app.db.session import engine, SessionLocal
        from app.db.models.user import ExtensionUser
        from app.db.models.expense import ExpenseClaim
        from app.main import app
        from app.ledger import rates, router
        from app.attachments import router as download_router
        from app.attachments.minio_client import StoredObject, validate_attachment
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            user=ExtensionUser(sub2api_user_id=9901,sub2api_role='admin',username_snapshot='页面测试管理员')
            db.add(user);db.flush()
            db.add(ExpenseClaim(claim_no='BROWSER-LEGACY',applicant_user_id=user.id,expense_date=date(2026,9,1),
                category='CDN',currency='USD',amount_tax_included=Decimal('20'),pay_type='PERSONAL_ADVANCE',status='PAID',invoice_status='NONE'))
            db.commit()
        rates.provider.latest=lambda: (Decimal('7.10'),rates.today())
        class MemoryStorage:
            objects={}
            def upload(self,*,prefix,entity_id,filename,content_type,data):
                name,mime=validate_attachment(filename,content_type,len(data))
                key=f'{prefix}/{entity_id}/{uuid.uuid4()}/{name}';self.objects[key]=data
                return StoredObject(key,hashlib.sha256(data).hexdigest(),len(data),mime,name)
            def get_bytes(self,key): return self.objects[key]
            def presigned_get_public(self,*args,**kwargs): return None
        storage=MemoryStorage()
        router.get_storage=lambda: storage
        download_router.get_storage=lambda: storage
        try: uvicorn.run(app,host='127.0.0.1',port=8090,access_log=False)
        finally: engine.dispose()


if __name__=='__main__':main()
