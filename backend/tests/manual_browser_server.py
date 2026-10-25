"""Local browser harness. Temporary SQLite, memory storage, loopback bind, no production credentials.

Run from backend with PYTHONPATH=. then run frontend/tests/manual/image-browser.mjs.
"""
import os
os.environ.update(DATABASE_URL='sqlite+pysqlite:///:memory:', DEV_AUTH_BYPASS='true', COOKIE_SECURE='false', SESSION_SECRET='isolated-browser-test', MINIO_ENDPOINT='localhost:1', SUB2API_ADMIN_API_KEY='')
from pathlib import Path
from io import BytesIO
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.auth.session import upsert_extension_user, create_session
from app.db.models.manual import ManualConfigVersion
from app.manual.schema import load_default_config
import app.db.models as _models
import app.attachments.minio_client as storage_module

temporary = TemporaryDirectory(prefix='huima-manual-browser-')
engine = create_engine(f'sqlite+pysqlite:///{Path(temporary.name) / "test.sqlite"}', connect_args={'check_same_thread':False})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


def database():
    with Session() as db:
        yield db


app.dependency_overrides[get_db] = database
with Session() as db:
    user = upsert_extension_user(db, sub2api_user_id=990001, username='隔离验收管理员', email='browser@example.test', role='admin')
    session = create_session(db, user)
    session_id = str(session.id)
    cfg = load_default_config().dump()
    cfg.pop('image_mcp')
    cfg['groups']['items'] = [{'name':'隔离生图组', 'sub2api_id':7001, 'visible':True, 'platform':'openai', 'summary':'只供隔离验收', 'notes':'不验证真实权限'}]
    db.add(ManualConfigVersion(version=1, config=cfg, note='旧版隔离配置'))
    db.commit()


class Stream(BytesIO):
    def stream(self, size):
        while data := self.read(size):
            yield data

    def release_conn(self):
        pass


class Storage:
    objects = {}

    def put_bytes(self, *, key, data, content_type):
        self.objects[key] = data

    def stat_object(self, key):
        return SimpleNamespace(size=len(self.objects[key]))

    def open_stream(self, key):
        return Stream(self.objects[key])


storage_module._storage = Storage()


@app.get('/__test/session')
def test_session():
    return {'id': session_id}


root = Path(__file__).resolve().parents[2]
app.mount('/docs', StaticFiles(directory=root/'frontend/manual', html=True), name='test-docs')
app.mount('/ext/app/assets', StaticFiles(directory=root/'frontend/dist/assets'), name='test-assets')


@app.get('/ext/app/theme-init.js')
def theme_init():
    return FileResponse(root/'frontend/public/theme-init.js')


@app.get('/ext/app/{path:path}')
def spa(path: str):
    return FileResponse(root/'frontend/dist/index.html')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=18091, log_level='warning')
