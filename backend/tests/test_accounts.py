import base64
import json
import os
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.common import vault
from app.config import get_settings
from app.db.models.account import AccountEvent, AccountRecord
from app.ledger.rates import today
from tests.conftest import login_as, make_user

ROOT = '/ext/api/v1/admin/accounts'
KEY = base64.b64encode(os.urandom(32)).decode()


@pytest.fixture()
def key(monkeypatch):
    monkeypatch.setattr(get_settings(), 'account_vault_key', KEY)


@pytest.fixture()
def admin(client, db, key):
    actor = make_user(db, sub2api_id=8801, role='admin', username='账号管理员')
    login_as(client, db, actor)
    return actor


def create(http, **changes):
    body = {'client': 'Claude', 'login': 'team@example.com', 'status': 'ACTIVE', 'password': ' p@ss word ', **changes}
    response = http.post(ROOT, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def reveal(client, account, field='password', purpose='view'):
    return client.post(f"{ROOT}/{account['id']}/reveal", json={'field': field, 'purpose': purpose})


def test_password_encrypted_at_rest_and_never_listed(client, db, admin):
    account = create(client, secret_notes='恢复码 1234')
    row = db.get(AccountRecord, account['id'])
    assert row.password_enc.startswith('v1:') and 'p@ss' not in row.password_enc
    assert '1234' not in row.secret_notes_enc
    for payload in (account, client.get(ROOT).json(), client.get(f"{ROOT}/{account['id']}").json()):
        text = json.dumps(payload, ensure_ascii=False)
        assert 'p@ss' not in text and '1234' not in text and 'v1:' not in text
    assert account['has_password'] and account['has_secret_notes']
    response = reveal(client, account)
    assert response.json() == {'value': ' p@ss word '} and response.headers['cache-control'] == 'no-store'
    assert reveal(client, account, 'secret_notes').json() == {'value': '恢复码 1234'}


def test_reveals_and_secret_changes_are_audited_without_values(client, db, admin):
    account = create(client)
    reveal(client, account, purpose='copy')
    reveal(client, account)
    updated = client.patch(f"{ROOT}/{account['id']}", json={'client': 'Claude', 'login': 'team@example.com', 'status': 'ACTIVE',
                                                               'password': 'new-secret', 'version': account['version']}).json()
    assert reveal(client, updated).json()['value'] == 'new-secret'
    events = client.get(f"{ROOT}/{account['id']}").json()['events']
    kinds = [e['event_type'] for e in reversed(events)]
    assert kinds == ['CREATED', 'SECRET_COPIED', 'SECRET_VIEWED', 'UPDATED', 'SECRET_VIEWED']
    assert all(e['actor_name'] == '账号管理员' for e in events)
    assert next(e for e in events if e['event_type'] == 'UPDATED')['detail']['secrets'] == {'密码': '已修改'}
    stored = json.dumps([e.detail for e in db.scalars(select(AccountEvent))], ensure_ascii=False)
    assert 'new-secret' not in stored and 'p@ss' not in stored and 'v1:' not in stored


def test_omitted_secret_kept_and_empty_clears(client, admin):
    account = create(client)
    base = {'client': 'Claude', 'login': 'team@example.com', 'status': 'ACTIVE'}
    kept = client.patch(f"{ROOT}/{account['id']}", json={**base, 'plan': 'Max', 'version': account['version']}).json()
    assert kept['has_password'] and kept['plan'] == 'Max'
    assert reveal(client, kept).json()['value'] == ' p@ss word '
    cleared = client.patch(f"{ROOT}/{account['id']}", json={**base, 'password': '', 'version': kept['version']}).json()
    assert not cleared['has_password'] and reveal(client, cleared).status_code == 404


def test_ciphertext_bound_to_row_and_field(client, db, admin):
    a, b = create(client, login='a@example.com'), create(client, login='b@example.com', password='other')
    row_a, row_b = db.get(AccountRecord, a['id']), db.get(AccountRecord, b['id'])
    row_b.password_enc = row_a.password_enc
    row_b.secret_notes_enc = row_a.password_enc
    db.commit()
    assert reveal(client, b).json()['code'] == 'VAULT_DECRYPT_FAILED'
    assert reveal(client, b, 'secret_notes').json()['code'] == 'VAULT_DECRYPT_FAILED'


def test_missing_or_wrong_key(client, db, admin, monkeypatch):
    account = create(client)
    monkeypatch.setattr(get_settings(), 'account_vault_key', '')
    assert client.get(ROOT + '/meta').json()['vault_ready'] is False
    # Account details without secrets still work.
    plain = client.post(ROOT, json={'client': 'Google', 'login': 'x@example.com'})
    assert plain.status_code == 201 and not plain.json()['has_password']
    refused = client.post(ROOT, json={'client': 'Google', 'login': 'y@example.com', 'password': 'pw'})
    assert refused.status_code == 503 and refused.json()['code'] == 'VAULT_NOT_CONFIGURED'
    assert db.scalar(select(AccountRecord).where(AccountRecord.login == 'y@example.com')) is None
    assert reveal(client, account).status_code == 503
    monkeypatch.setattr(get_settings(), 'account_vault_key', 'not-base64!')
    assert reveal(client, account).json()['code'] == 'VAULT_KEY_INVALID'
    monkeypatch.setattr(get_settings(), 'account_vault_key', base64.b64encode(os.urandom(32)).decode())
    assert reveal(client, account).json()['code'] == 'VAULT_DECRYPT_FAILED'


def test_duplicate_per_client_case_insensitive_and_archive_frees_identity(client, admin):
    first = create(client)
    dup = client.post(ROOT, json={'client': 'claude', 'login': 'TEAM@example.com'})
    assert dup.status_code == 409 and dup.json()['code'] == 'ACCOUNT_DUPLICATE'
    assert client.post(ROOT, json={'client': 'ChatGPT', 'login': 'team@example.com'}).status_code == 201
    archived = client.post(f"{ROOT}/{first['id']}/archive", json={'version': first['version']}).json()
    assert archived['archived'] and all(i['id'] != first['id'] for i in client.get(ROOT).json()['items'])
    assert [i['id'] for i in client.get(ROOT, params={'archived': True}).json()['items']] == [first['id']]
    replacement = create(client)
    restore = client.post(f"{ROOT}/{first['id']}/restore", json={'version': archived['version']})
    assert restore.status_code == 409 and restore.json()['code'] == 'ACCOUNT_DUPLICATE'
    client.post(f"{ROOT}/{replacement['id']}/archive", json={'version': replacement['version']})
    assert client.post(f"{ROOT}/{first['id']}/restore", json={'version': archived['version']}).status_code == 200


def test_status_change_versioned_and_counts(client, admin):
    a = create(client, login='a@example.com')
    create(client, login='b@example.com', status='STANDBY')
    create(client, client='Google', login='g@example.com', status='BANNED')
    changed = client.post(f"{ROOT}/{a['id']}/status", json={'status': 'BANNED', 'version': a['version']})
    assert changed.status_code == 200 and changed.json()['status_label'] == '封禁'
    stale = client.post(f"{ROOT}/{a['id']}/status", json={'status': 'ACTIVE', 'version': a['version']})
    assert stale.status_code == 409 and stale.json()['code'] == 'VERSION_CONFLICT'
    data = client.get(ROOT, params={'client': 'Claude'}).json()
    assert data['clients'] == [{'client': 'Claude', 'count': 2}, {'client': 'Google', 'count': 1}]
    assert data['statuses'] == {'ACTIVE': 0, 'STANDBY': 1, 'BANNED': 1, 'DISABLED': 0}
    assert len(data['items']) == 2
    assert [i['login'] for i in client.get(ROOT, params={'status': 'BANNED'}).json()['items']] == ['a@example.com', 'g@example.com']
    assert client.get(ROOT, params={'status': 'GONE'}).status_code == 422


def test_expiring_first_and_keyword(client, admin):
    now = today()
    create(client, login='later@example.com', expires_on=(now + timedelta(days=90)).isoformat())
    create(client, login='none@example.com', owner='小王')
    create(client, login='soon@example.com', expires_on=(now + timedelta(days=5)).isoformat())
    create(client, login='past@example.com', expires_on=(now - timedelta(days=1)).isoformat())
    items = client.get(ROOT).json()['items']
    assert [i['login'] for i in items] == ['past@example.com', 'soon@example.com', 'later@example.com', 'none@example.com']
    assert [i['expiry'] for i in items] == ['EXPIRED', 'SOON', None, None]
    assert [i['login'] for i in client.get(ROOT, params={'keyword': '小王'}).json()['items']] == ['none@example.com']


def test_plain_fields_trimmed_but_password_kept_verbatim(client, admin):
    account = create(client, client=' Claude ', login=' x@example.com ')
    assert account['client'] == 'Claude' and account['login'] == 'x@example.com'
    assert reveal(client, account).json()['value'] == ' p@ss word '
    assert client.post(ROOT, json={'client': ' ', 'login': 'a'}).status_code == 422
    assert client.post(ROOT, json={'client': 'A', 'login': 'a', 'status': 'LIMITED'}).status_code == 422


def test_meta_suggestions(client, admin):
    create(client, client='Poe', owner='小李', plan='Pro')
    meta = client.get(ROOT + '/meta').json()
    assert meta['clients'][0] == 'Poe' and 'ChatGPT' in meta['clients']
    assert meta['owners'] == ['小李'] and meta['plans'] == ['Pro'] and meta['vault_ready'] is True
    assert [s['label'] for s in meta['statuses']] == ['启用', '备用', '封禁', '停用']


def test_non_admin_and_anonymous_denied(client, db, key):
    user = make_user(db, sub2api_id=8802, role='user', username='普通用户')
    login_as(client, db, user)
    for method, path in [('get', ROOT), ('get', ROOT + '/meta'), ('get', ROOT + '/1'), ('post', ROOT + '/1/reveal')]:
        assert getattr(client, method)(path, **({'json': {'field': 'password'}} if method == 'post' else {})).status_code == 403
    client.cookies.clear()
    assert client.get(ROOT).status_code == 401


def test_vault_round_trip_unit(key):
    token = vault.encrypt('密码', 'account:1:password')
    assert token != vault.encrypt('密码', 'account:1:password')  # fresh nonce
    assert vault.decrypt(token, 'account:1:password') == '密码'
    with pytest.raises(Exception):
        vault.decrypt(token, 'account:2:password')
