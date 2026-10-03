import { useEffect, useRef, useState } from 'react';
import { apiRequest } from './api';
import { Empty, Loading, Summary, dateTime, endingIn, money, shortDate } from './ui';

export const amountPattern = '(?:0|[1-9][0-9]{0,7})(?:[.][0-9]{1,2})?';
const flowOf = type => /^deposit/i.test(type) ? { sign: '+', className: 'credit' } : /^withdraw/i.test(type) ? { sign: '-', className: 'debit' } : { sign: '', className: '' };
const labels = { deposit: 'deposit', withdraw: 'withdrawal', transfer: 'transfer' };

export function useList(path, revision = 0) {
  const [state, setState] = useState({ items: [], loading: true, error: '' });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ items: [], loading: true, error: '' });
    apiRequest(path, { signal: controller.signal })
      .then(items => { if (!controller.signal.aborted) setState({ items, loading: false, error: '' }); })
      .catch(error => { if (!controller.signal.aborted) setState({ items: [], loading: false, error: error.message }); });
    return () => controller.abort();
  }, [path, revision, retry]);
  return { ...state, retry: () => setRetry(value => value + 1) };
}

export function ListStatus({ state }) {
  return state.loading ? <Loading /> : state.error ? <div><p role="alert" className="error">{state.error}</p><button type="button" onClick={state.retry}>Retry</button></div> : null;
}

function TransferFields({ from, to, setFrom, setTo }) {
  const state = useList('/accounts');
  return <>
    <ListStatus state={state} />
    {!state.loading && !state.error && <>
      {state.items.length < 2 && <p>At least two accounts are needed for a transfer.</p>}
      <label htmlFor="from-account">From account</label>
      <select id="from-account" required value={from} onChange={event => { setFrom(event.target.value); if (event.target.value === to) setTo(''); }}>
        <option value="">Choose source account</option>
        {state.items.map(item => <option key={item.accountId} value={item.accountId}>{item.userName} · {item.accountType} · {item.accountId} · {money(item.balance)}</option>)}
      </select>
      <label htmlFor="to-account">To account</label>
      <select id="to-account" required value={to} onChange={event => setTo(event.target.value)}>
        <option value="">Choose destination account</option>
        {state.items.filter(item => item.accountId !== from).map(item => <option key={item.accountId} value={item.accountId}>{item.userName} · {item.accountType} · {item.accountId}</option>)}
      </select>
    </>}
  </>;
}

function Operation({ operation, customer, onCancel, onSuccess, onBusy }) {
  const [amount, setAmount] = useState('');
  const [accountType, setAccountType] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  const dialog = useRef(null);
  const { kind, account } = operation;
  const label = labels[kind] && `${labels[kind][0].toUpperCase()}${labels[kind].slice(1)}`;
  useEffect(() => { if (kind === 'delete') dialog.current?.showModal(); }, [kind]);

  async function submit(event) {
    event?.preventDefault();
    if (lock.current) return;
    if (labels[kind] && (!new RegExp(`^${amountPattern}$`).test(amount) || !/[1-9]/.test(amount))) {
      setError('Enter a positive amount up to 99999999.99 with at most two decimal places.'); return;
    }
    if (kind === 'transfer' && (!from || !to || from === to)) { setError('Choose two different accounts.'); return; }
    if (kind === 'open' && !accountType.trim()) { setError('Enter an account type.'); return; }
    lock.current = true; setBusy(true); onBusy(true); setError('');
    try {
      let path, options;
      if (kind === 'delete') { path = `/accounts/${encodeURIComponent(account.accountId)}`; options = { method: 'DELETE' }; }
      else if (kind === 'open') { path = '/accounts'; options = { method: 'POST', data: { customerId: customer.customerId, accountType: accountType.trim() } }; }
      else {
        path = kind === 'transfer' ? '/transfers' : `/accounts/${encodeURIComponent(account.accountId)}/${kind}`;
        options = { method: 'POST', idempotencyKey: crypto.randomUUID(), data: kind === 'transfer' ? { fromAccountId: from, toAccountId: to, amount } : { amount } };
      }
      await apiRequest(path, options);
      onSuccess(kind === 'open' ? 'Account opened.' : kind === 'delete' ? 'Account deleted.' : `${label} completed.`);
    } catch (err) { setError(`${err.message}${labels[kind] && err.message.startsWith('Unable to reach') ? ' The result is unknown. Check account balances and history before submitting again.' : ''}`); }
    finally { lock.current = false; setBusy(false); onBusy(false); }
  }

  if (kind === 'delete') return <dialog ref={dialog} role="alertdialog" aria-modal="true" aria-labelledby="account-delete-title" onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="account-delete-title">Delete account {account.accountId}?</h2>
    <p>Only an account with a zero balance can be deleted. Transaction history is retained.</p>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="actions"><button autoFocus disabled={busy} className="secondary" onClick={onCancel}>Cancel</button><button disabled={busy} className="danger" onClick={submit}>{busy ? 'Deleting...' : 'Delete account'}</button></div>
  </dialog>;
  return <section className="panel" aria-labelledby="operation-title">
    <h2 id="operation-title">{kind === 'open' ? 'Open account' : label}{account ? ` · ${account.accountId}` : ''}</h2>
    {error && <p role="alert" className="error">{error}</p>}
    <form onSubmit={submit}><fieldset disabled={busy}>
      {kind === 'open' ? <><label htmlFor="account-type">Account type</label><input id="account-type" autoFocus required maxLength={50} value={accountType} onChange={event => setAccountType(event.target.value)} /></> : <>
        {kind === 'transfer' && <TransferFields from={from} to={to} setFrom={setFrom} setTo={setTo} />}
        <label htmlFor="amount">Amount</label><input id="amount" autoFocus={kind !== 'transfer'} inputMode="decimal" required pattern={amountPattern} value={amount} onChange={event => setAmount(event.target.value)} aria-describedby="amount-help" />
        <p id="amount-help">Use a positive amount with up to two decimal places.</p>
      </>}
      <div className="actions"><button type="submit" disabled={kind === 'transfer' && (!from || !to)}>{busy ? 'Submitting...' : kind === 'open' ? 'Create account' : `Submit ${labels[kind]}`}</button><button type="button" className="secondary" onClick={onCancel}>Cancel</button></div>
    </fieldset></form>
  </section>;
}

export function History({ account, onClose, onDeposit }) {
  const state = useList(`/accounts/${encodeURIComponent(account.accountId)}/transactions`);
  return <section className="panel tape-panel"><div className="heading"><h2>Transactions · {account.accountId}</h2><button className="secondary" onClick={onClose}>Close history</button></div>
    <ListStatus state={state} />
    {!state.loading && !state.error && (state.items.length === 0 ? <Empty title="No transactions yet." hint="Deposits, withdrawals and transfers will be listed here." action={onDeposit && { label: 'Make a deposit', onClick: onDeposit }} /> : <div className="tape"><table><caption>Transaction history, oldest first</caption><thead><tr><th scope="col">Date</th><th scope="col">Type</th><th scope="col" className="money">Amount</th><th scope="col" className="money">Balance after</th></tr></thead><tbody>{state.items.map(item => { const flow = flowOf(item.type); return <tr key={item.txnId}><td className="t-date">{dateTime(item.date)}</td><td className="t-type">{item.type}</td><td className={`money t-amount ${flow.className}`} data-label="Amount">{flow.sign && <span aria-hidden="true">{flow.sign}</span>}{money(item.amount)}</td><td className="money t-bal" data-label="Balance">{money(item.balanceAfter)}</td></tr>; })}</tbody></table></div>)}
  </section>;
}

export default function Accounts({ customer, onBack, onNavigationLock }) {
  const [revision, setRevision] = useState(0);
  const state = useList(customer ? `/customers/${encodeURIComponent(customer.customerId)}/accounts` : '/accounts/premium?limit=200', revision);
  const [operation, setOperation] = useState(null);
  const [history, setHistory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const opener = useRef(null);
  const heading = useRef(null);
  const disabled = busy || Boolean(operation);
  useEffect(() => { onNavigationLock?.(disabled); return () => onNavigationLock?.(false); }, [disabled, onNavigationLock]);
  function begin(kind, account, trigger = null) { opener.current = trigger; setMessage(''); setHistory(null); setOperation({ kind, account }); }
  // Closing a form or dialog hands focus back to the button that opened it; after a save the list reloads, so go to the heading.
  function closeOperation(saved) { setOperation(null); setTimeout(() => (!saved && opener.current?.isConnected ? opener.current : heading.current)?.focus(), 0); }
  function showHistory(account, trigger) { opener.current = trigger; setHistory(account); }
  function closeHistory() { setHistory(null); setTimeout(() => (opener.current?.isConnected ? opener.current : heading.current)?.focus(), 0); }
  return <>
    <button className="back-link" disabled={disabled} onClick={onBack}>Back to customers</button>
    <div className="heading"><h1 ref={heading} tabIndex={-1}>{customer ? `${customer.name}'s accounts` : 'Premium accounts'}</h1><div className="actions">
      {customer && <button disabled={disabled || state.loading || Boolean(state.error)} onClick={event => begin('open', null, event.currentTarget)}>Open account</button>}
      <button disabled={disabled} onClick={event => begin('transfer', null, event.currentTarget)}>Transfer</button>
      <button className="secondary" disabled={disabled || state.loading} onClick={state.retry}>Refresh accounts</button>
    </div></div>
    {!customer && <p className="loading-note">Up to 200 accounts meeting the server's premium balance threshold, highest balance first.</p>}
    {!state.loading && !state.error && state.items.length > 0 && <Summary items={[[customer ? 'Accounts held' : 'Accounts listed', state.items.length], ['Combined balance', money(state.items.reduce((sum, item) => sum + Number(item.balance), 0))], ...(customer ? [] : [['Highest balance', money(Math.max(...state.items.map(item => Number(item.balance))))]])]} />}
    <p role="status">{message}</p>
    {operation && <Operation operation={operation} customer={customer} onBusy={setBusy} onCancel={() => closeOperation(false)} onSuccess={text => { closeOperation(true); setMessage(text); setRevision(value => value + 1); }} />}
    <ListStatus state={state} />
    {!state.loading && !state.error && (state.items.length === 0 ? <Empty title="No accounts found." hint={customer ? "Open an account to begin this customer's ledger." : 'No account currently meets the premium balance threshold.'} action={customer ? { label: 'Open the first account', onClick: event => begin('open', null, event.currentTarget), disabled } : { label: 'Back to customers', onClick: onBack, disabled }} /> : <table className="cards"><caption>{customer ? 'Customer accounts' : 'Premium accounts'}</caption><thead><tr><th scope="col">Account ID</th><th scope="col">Owner</th><th scope="col">Type</th><th scope="col">Opened</th><th scope="col" className="money">Balance</th><th scope="col">Actions</th></tr></thead><tbody>{state.items.map(account => <tr key={account.accountId}>
      <th scope="row" className="identifier c-id">{account.accountId}</th><td className="c-type" data-label="Type">{account.accountType}<span className="c-end">{endingIn(account.accountId)}</span></td><td className="c-owner" data-label="Owner">{account.userName}</td><td className="c-opened" data-label="Opened">{shortDate(account.createdAt)}</td><td className="money c-bal" data-label="Balance">{money(account.balance)}</td><td className="c-act"><div className="actions account-actions">
        <button disabled={disabled} onClick={event => begin('deposit', account, event.currentTarget)}>Deposit</button><button disabled={disabled} onClick={event => begin('withdraw', account, event.currentTarget)}>Withdraw</button>
        <button className="secondary" disabled={disabled} onClick={event => showHistory(account, event.currentTarget)}>History</button>
        <button className="secondary danger-text" disabled={disabled || !/^0(?:\.0+)?$/.test(String(account.balance))} title="Only zero-balance accounts can be deleted" aria-label={`Delete account ${account.accountId}`} onClick={event => begin('delete', account, event.currentTarget)}>Delete</button>
      </div></td>
    </tr>)}</tbody></table>)}
    {history && <History key={history.accountId} account={history} onClose={closeHistory} onDeposit={() => begin('deposit', history, opener.current)} />}
  </>;
}
