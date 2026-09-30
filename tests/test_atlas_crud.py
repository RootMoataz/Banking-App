from concurrent.futures import ThreadPoolExecutor

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.main import create_app

pytestmark = pytest.mark.integration


def customer(client, opted_in=False):
    response = client.post('/api/customers', json={'name':'Moataz Hikal','email':'moataz@example.com'})
    assert response.status_code == 201, response.text
    cid = response.json()['customerId']
    if opted_in:
        assert client.patch(f'/api/customers/{cid}/preferences', json={'marketingEnabled':True}).status_code == 200
    return cid


def account(client, cid):
    response = client.post('/api/accounts', json={'customerId':cid,'accountType':'SAVINGS'})
    assert response.status_code == 201, response.text
    return response.json()['accountId']


def test_persistence_and_initial_messages(client, settings):
    cid = customer(client, True)
    assert client.get(f'/api/customers/{cid}/notifications').json() == []
    aid = account(client, cid)
    assert ObjectId.is_valid(cid) and ObjectId.is_valid(aid)
    account(client, cid)
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f'/api/accounts/{aid}').json()['balance'] == '0.00'
        messages = restarted.get(f'/api/customers/{cid}/notifications').json()
        assert {m['kind'] for m in messages} == {'LOW_BALANCE_ALERT','LOW_BALANCE_MARKETING'}
        assert len(messages) == 2


def test_concurrent_initial_accounts_only_alert_once(client):
    cid = customer(client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        aids = list(pool.map(lambda _: account(client, cid), range(4)))
    assert len(set(aids)) == 4
    assert len(client.get(f'/api/customers/{cid}/notifications').json()) == 1


def test_closure_preserves_audit_and_email(client):
    cid = customer(client)
    aid = account(client, cid)
    path = f'/api/accounts/{aid}'
    client.post(path + '/deposit', json={'amount':100})
    assert client.delete(path).status_code == 409
    client.post(path + '/withdraw', json={'amount':100})
    assert client.delete(f'/api/customers/{cid}').status_code == 409
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert len(client.get(path + '/transactions').json()) == 2
    assert client.post(path + '/deposit', json={'amount':1}).status_code == 404
    assert client.delete(f'/api/customers/{cid}').status_code == 204
    assert len(client.get('/api/audit/transactions', params={'customerId':cid}).json()) == 2
    assert client.post('/api/customers', json={'name':'Moataz Hikal','email':'MOATAZ@example.com'}).status_code == 409


def test_preference_does_not_backfill_messages(client):
    cid = customer(client)
    account(client, cid)
    path = f'/api/customers/{cid}'
    assert client.patch(path+'/preferences', json={'marketingEnabled':'yes'}).status_code == 422
    assert client.patch(path+'/preferences', json={'marketingEnabled':True}).status_code == 200
    assert len(client.get(path+'/notifications').json()) == 1
    edited = client.put(path, json={'name':'Moataz Hikal','email':'updated@example.com'})
    assert edited.json()['marketingEnabled'] is True


def test_creation_and_archival_cannot_leave_an_orphan(client, db):
    cid = customer(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        created = pool.submit(client.post, '/api/accounts', json={'customerId':cid,'accountType':'SAVINGS'})
        deleted = pool.submit(client.delete, f'/api/customers/{cid}')
        codes = (created.result().status_code, deleted.result().status_code)
    assert codes in {(201,409),(404,204)}
    owner = db.customers.find_one({'_id':ObjectId(cid)})
    active_accounts = db.accounts.count_documents({'customerId':ObjectId(cid),'active':True})
    assert owner['active'] or active_accounts == 0


def test_deposit_racing_account_closure_keeps_balances_consistent(client, db):
    cid = customer(client)
    aid = account(client, cid)
    path = f'/api/accounts/{aid}'
    with ThreadPoolExecutor(max_workers=2) as pool:
        deposit = pool.submit(client.post, path+'/deposit', json={'amount':1})
        closed = pool.submit(client.delete, path)
        codes = (deposit.result().status_code, closed.result().status_code)
    assert codes in {(200,409),(404,204)}
    row = db.accounts.find_one({'_id':ObjectId(aid)})
    owner = db.customers.find_one({'_id':ObjectId(cid)})
    assert row['balanceCents'] == owner['totalCents']
    assert row['active'] or row['balanceCents'] == 0
