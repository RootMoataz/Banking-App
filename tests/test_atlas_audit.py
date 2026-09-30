from datetime import datetime, timezone

import pytest

from test_atlas_crud import customer, account

pytestmark = pytest.mark.integration


def test_literal_search_paging_and_category(client):
    cid = customer(client)
    aid = account(client, cid)
    assert client.get('/api/customers', params={'search':'.*'}).json() == []
    assert len(client.get('/api/customers', params={'search':'MOATAZ'}).json()) == 1
    assert client.get('/api/customers', params={'category':'PREMIUM'}).json() == []
    client.post(f'/api/accounts/{aid}/deposit', json={'amount':10000})
    assert len(client.get('/api/customers', params={'category':'PREMIUM'}).json()) == 1
    assert client.get('/api/customers', params={'offset':1}).json() == []
    for params in [{'limit':101}, {'limit':0}, {'offset':-1}, {'category':'bad'}]:
        assert client.get('/api/customers', params=params).status_code == 422


def test_audit_dates_ids_and_archived_records(client, db):
    cid = customer(client)
    aid = account(client, cid)
    for _ in range(2):
        client.post(f'/api/accounts/{aid}/deposit', json={'amount':10})
    docs = list(db.transactions.find().sort('_id',1))
    db.transactions.update_one({'_id':docs[0]['_id']},{'$set':{'date':datetime(2026,1,1,tzinfo=timezone.utc)}})
    db.transactions.update_one({'_id':docs[1]['_id']},{'$set':{'date':datetime(2026,1,2,tzinfo=timezone.utc)}})
    params = {'customerId':cid,'accountId':aid,'from':'2026-01-01T00:00:00Z','to':'2026-01-02T00:00:00Z'}
    rows = client.get('/api/audit/transactions',params=params).json()
    assert len(rows) == 1 and rows[0]['txnId'] == str(docs[0]['_id'])
    params['from'] = '2025-12-31T19:00:00-05:00'
    assert client.get('/api/audit/transactions',params=params).json() == rows
    assert client.get('/api/audit/transactions/'+rows[0]['txnId']).json() == rows[0]
    assert len(client.get('/api/audit/transactions',params={'limit':1,'offset':1}).json()) == 1
    for query in [{'from':'2026-01-01'}, {'from':'2026-01-02T00:00:00Z','to':'2026-01-01T00:00:00Z'}, {'customerId':'invalid'}]:
        assert client.get('/api/audit/transactions',params=query).status_code == 422


def test_submillisecond_date_boundaries(client, db):
    cid = customer(client)
    aid = account(client, cid)
    client.post(f'/api/accounts/{aid}/deposit', json={'amount':1})
    db.transactions.update_many({}, {'$set':{'date':datetime(2026,1,1,tzinfo=timezone.utc)}})
    assert client.get('/api/audit/transactions',params={'from':'2026-01-01T00:00:00.000500Z'}).json() == []
    assert len(client.get('/api/audit/transactions',params={'to':'2026-01-01T00:00:00.000500Z'}).json()) == 1
