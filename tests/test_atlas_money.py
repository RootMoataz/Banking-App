from concurrent.futures import ThreadPoolExecutor

import pytest
from bson import ObjectId

from test_atlas_crud import customer, account

pytestmark = pytest.mark.integration


def test_combined_balance_crossings_and_opt_out(client):
    cid = customer(client, True)
    one, two = account(client, cid), account(client, cid)
    client.post(f'/api/accounts/{one}/deposit', json={'amount':50})
    assert len(client.get(f'/api/customers/{cid}/notifications').json()) == 2
    client.post(f'/api/accounts/{two}/deposit', json={'amount':9950})
    snapshot = client.get(f'/api/customers/{cid}').json()
    assert (snapshot['totalBalance'], snapshot['category']) == ('10000.00','PREMIUM')
    messages = client.get(f'/api/customers/{cid}/notifications').json()
    assert len(messages) == 3 and messages[0]['kind'] == 'PREMIUM_MARKETING'
    client.patch(f'/api/customers/{cid}/preferences', json={'marketingEnabled':False})
    client.post(f'/api/accounts/{two}/withdraw', json={'amount':9950})
    messages = client.get(f'/api/customers/{cid}/notifications').json()
    assert len(messages) == 4 and messages[0]['kind'] == 'LOW_BALANCE_ALERT'


def test_simultaneous_withdrawals_and_multiple_account_totals(client):
    cid = customer(client)
    one, two = account(client, cid), account(client, cid)
    client.post(f'/api/accounts/{one}/deposit', json={'amount':100})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(f'/api/accounts/{one}/withdraw', json={'amount':75}), range(2)))
    assert sorted(r.status_code for r in responses) == [200,400]
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda aid: client.post(f'/api/accounts/{aid}/deposit', json={'amount':1}), [one,two]*5))
    assert all(r.status_code == 200 for r in responses)
    assert client.get(f'/api/customers/{cid}').json()['totalBalance'] == '35.00'


@pytest.mark.parametrize('failing_repository', ['transactions','notifications'])
def test_database_write_failure_rolls_back_all_changes(client, db, monkeypatch, failing_repository):
    from pymongo.errors import OperationFailure
    cid = customer(client, True)
    aid = account(client, cid)
    before = db.customers.find_one({'_id':ObjectId(cid)})
    history_before, notices_before = db.transactions.count_documents({}), db.notifications.count_documents({})
    repository = getattr(client.app.state.accounts, failing_repository)
    method = 'add' if failing_repository == 'transactions' else 'add_messages'
    def fail(*args, **kwargs):
        raise OperationFailure('sentinel_db_secret')
    monkeypatch.setattr(repository, method, fail)
    response = client.post(f'/api/accounts/{aid}/deposit', json={'amount':10000})
    assert response.status_code == 503 and 'sentinel_db_secret' not in response.text
    assert db.accounts.find_one({'_id':ObjectId(aid)})['balanceCents'] == 0
    assert db.customers.find_one({'_id':ObjectId(cid)}) == before
    assert db.transactions.count_documents({}) == history_before
    assert db.notifications.count_documents({}) == notices_before


def test_transaction_retry_does_not_duplicate_history_or_messages(client, monkeypatch):
    from pymongo.errors import OperationFailure
    cid = customer(client, True)
    aid = account(client, cid)
    repository = client.app.state.accounts.notifications
    original = repository.add_messages
    attempts = []
    def retry_once(*args, **kwargs):
        original(*args, **kwargs)
        attempts.append(1)
        if len(attempts) == 1:
            raise OperationFailure('retry', code=112, details={'errorLabels':['TransientTransactionError']})
    monkeypatch.setattr(repository, 'add_messages', retry_once)
    assert client.post(f'/api/accounts/{aid}/deposit', json={'amount':10000}).status_code == 200
    assert len(client.get(f'/api/accounts/{aid}/transactions').json()) == 1
    assert len(client.get(f'/api/customers/{cid}/notifications').json()) == 3


def test_total_overflow_is_rejected(client, db):
    cid = customer(client)
    aid = account(client, cid)
    db.customers.update_one({'_id':ObjectId(cid)}, {'$set':{'totalCents':9223372036854775807}})
    assert client.post(f'/api/accounts/{aid}/deposit', json={'amount':1}).status_code == 400
    assert client.get(f'/api/accounts/{aid}').json()['balance'] == '0.00'
    assert db.transactions.count_documents({}) == 0


def test_preference_race_uses_serialized_preference(client, db):
    cid = customer(client, True)
    aid = account(client, cid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deposit = pool.submit(client.post, f'/api/accounts/{aid}/deposit', json={'amount':10000})
        opt_out = pool.submit(client.patch, f'/api/customers/{cid}/preferences', json={'marketingEnabled':False})
        assert deposit.result().status_code == opt_out.result().status_code == 200
    messages = client.get(f'/api/customers/{cid}/notifications', params={'kind':'PREMIUM_MARKETING'}).json()
    assert len(messages) in {0,1}
    assert client.get(f'/api/customers/{cid}').json()['marketingEnabled'] is False
    client.post(f'/api/accounts/{aid}/withdraw', json={'amount':10000})
    client.post(f'/api/accounts/{aid}/deposit', json={'amount':10000})
    assert client.get(f'/api/customers/{cid}/notifications', params={'kind':'PREMIUM_MARKETING'}).json() == messages
