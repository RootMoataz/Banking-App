import { useEffect, useRef, useState } from 'react';
import { apiRequest } from './api';
import { History, ListStatus, amountPattern, useList } from './Accounts';
import { useAuth } from './auth';
import { Empty, Summary, endingIn, money, shortDate } from './ui';

const amountOk = amount => new RegExp(`^${amountPattern}$`).test(amount) && /[1-9]/.test(amount);

function OpenAccount({ customerId, onCancel, onDone }) {
  const [accountType, setAccountType] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  async function submit(event) {
    event.preventDefault();
    if (lock.current) return;
    if (!accountType.trim()) { setError('Enter an account type.'); return; }
    lock.current = true; setBusy(true); setError('');
    try { await apiRequest('/accounts', { method: 'POST', data: { customerId, accountType: accountType.trim() } }); onDone(); }
    catch (err) { setError(err.message); setBusy(false); }
    finally { lock.current = false; }
  }
  return <section className="panel" aria-labelledby="open-title"><h2 id="open-title">Open account</h2>
    {error && <p role="alert" className="error">{error}</p>}
    <form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="account-type">Account type</label>
      <input id="account-type" autoFocus required maxLength={50} value={accountType} onChange={event => setAccountType(event.target.value)} />
      <div className="actions"><button type="submit">{busy ? 'Submitting...' : 'Create account'}</button><button type="button" className="secondary" onClick={onCancel}>Cancel</button></div>
    </fieldset></form>
  </section>;
}

export function MyAccounts() {
  const { user } = useAuth();
  const [revision, setRevision] = useState(0);
  const state = useList(`/customers/${encodeURIComponent(user.customerId)}/accounts`, revision);
  const [opening, setOpening] = useState(false);
  const [history, setHistory] = useState(null);
  const [message, setMessage] = useState('');
  const opener = useRef(null);
  const heading = useRef(null);
  function openForm(event) { opener.current = event.currentTarget; setMessage(''); setHistory(null); setOpening(true); }
  function closeForm(saved) { setOpening(false); setTimeout(() => (!saved && opener.current?.isConnected ? opener.current : heading.current)?.focus(), 0); }
  function showHistory(account, trigger) { opener.current = trigger; setHistory(account); }
  function closeHistory() { setHistory(null); setTimeout(() => (opener.current?.isConnected ? opener.current : heading.current)?.focus(), 0); }
  return <>
    <div className="heading"><div><h1 ref={heading} tabIndex={-1}>My accounts</h1><p>Your accounts and their balances.</p></div><div className="actions">
      <button disabled={opening || state.loading || Boolean(state.error)} onClick={openForm}>Open account</button>
    </div></div>
    {!state.loading && !state.error && state.items.length > 0 && <Summary items={[['Combined balance', money(state.items.reduce((sum, item) => sum + Number(item.balance), 0)), 'lead'], ['Accounts held', state.items.length]]} />}
    <p role="status">{message}</p>
    {opening && <OpenAccount customerId={user.customerId} onCancel={() => closeForm(false)} onDone={() => { closeForm(true); setMessage('Account opened.'); setRevision(value => value + 1); }} />}
    <ListStatus state={state} />
    {!state.loading && !state.error && (state.items.length === 0 ? <Empty title="No accounts yet." hint="Open an account to begin your ledger." action={{ label: 'Open your first account', onClick: openForm, disabled: opening }} /> : <table className="cards"><caption>My accounts</caption><thead><tr><th scope="col">Account ID</th><th scope="col">Type</th><th scope="col">Opened</th><th scope="col" className="money">Balance</th><th scope="col">Actions</th></tr></thead><tbody>{state.items.map(account => <tr key={account.accountId}>
      <th scope="row" className="identifier c-id">{account.accountId}</th><td className="c-type" data-label="Type">{account.accountType}<span className="c-end">{endingIn(account.accountId)}</span></td><td className="c-opened" data-label="Opened">{shortDate(account.createdAt)}</td><td className="money c-bal" data-label="Balance">{money(account.balance)}</td>
      <td className="c-act"><div className="actions account-actions"><button className="secondary" aria-pressed={history?.accountId === account.accountId} onClick={event => showHistory(account, event.currentTarget)}>History</button></div></td>
    </tr>)}</tbody></table>)}
    {history && <History key={history.accountId} account={history} onClose={closeHistory} />}
  </>;
}

export function Transfer() {
  const { user } = useAuth();
  const [revision, setRevision] = useState(0);
  const state = useList(`/customers/${encodeURIComponent(user.customerId)}/accounts`, revision);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const lock = useRef(false);
  useEffect(() => { if (state.items.length === 1) setFrom(state.items[0].accountId); }, [state.items]);
  async function submit(event) {
    event.preventDefault();
    if (lock.current) return;
    setMessage('');
    if (!from || !to.trim() || to.trim() === from) { setError('Choose your account and a different destination account.'); return; }
    if (!amountOk(amount)) { setError('Enter a positive amount up to 99999999.99 with at most two decimal places.'); return; }
    lock.current = true; setBusy(true); setError('');
    try {
      await apiRequest('/transfers', { method: 'POST', idempotencyKey: crypto.randomUUID(), data: { fromAccountId: from, toAccountId: to.trim(), amount } });
      setTo(''); setAmount(''); setMessage('Transfer completed.'); setRevision(value => value + 1);
    } catch (err) { setError(`${err.message}${err.message.startsWith('Unable to reach') ? ' The result is unknown. Check your balances and history before submitting again.' : ''}`); }
    finally { lock.current = false; setBusy(false); }
  }
  return <>
    <div className="heading"><div><h1>Transfer</h1><p>Move money from one of your accounts to any account.</p></div></div>
    <p role="status">{message}</p>
    <ListStatus state={state} />
    {!state.loading && !state.error && <section className="panel" aria-labelledby="transfer-title"><h2 id="transfer-title">New transfer</h2>
      {error && <p role="alert" className="error">{error}</p>}
      {state.items.length === 0 ? <p>You need an account before you can transfer.</p> : <form onSubmit={submit}><fieldset disabled={busy}>
        <label htmlFor="from-account">From account</label>
        <select id="from-account" required value={from} onChange={event => setFrom(event.target.value)}>
          <option value="">Choose source account</option>
          {state.items.map(item => <option key={item.accountId} value={item.accountId}>{item.accountType} · {item.accountId} · {money(item.balance)}</option>)}
        </select>
        <label htmlFor="to-account">To account ID</label>
        <input id="to-account" required maxLength={64} value={to} onChange={event => setTo(event.target.value)} />
        <label htmlFor="amount">Amount</label>
        <input id="amount" inputMode="decimal" required pattern={amountPattern} value={amount} onChange={event => setAmount(event.target.value)} aria-describedby="amount-help" />
        <p id="amount-help">Use a positive amount with up to two decimal places.</p>
        <div className="actions"><button type="submit">{busy ? 'Submitting...' : 'Submit transfer'}</button></div>
      </fieldset></form>}
    </section>}
  </>;
}

export function Profile() {
  const { user } = useAuth();
  return <>
    <div className="heading"><div><h1>Profile</h1><p>Your details on record.</p></div></div>
    <Summary items={[['Name', user.name], ['Email', user.email]]} />
  </>;
}

export function AccessDenied() {
  return <div className="panel"><h1>Access denied</h1><p role="alert" className="error">Access denied. Your role does not allow this page.</p></div>;
}
