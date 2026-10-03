import { useEffect, useRef, useState } from 'react';
import { apiRequest } from './api';
import { ACCOUNT_TYPES, accountTypeLabel } from './accountTypes';
import { useI18n } from './i18n';
import { Empty, Loading, Summary, dateTime, money, shortDate } from './ui';

export const amountPattern = '(?:0|[1-9][0-9]{0,7})(?:[.][0-9]{1,2})?';
const flowOf = type => /^deposit/i.test(type) ? { sign: '+', className: 'credit' } : /^withdraw/i.test(type) ? { sign: '-', className: 'debit' } : { sign: '', className: '' };
const isZero = balance => /^0(?:\.0+)?$/.test(String(balance));
const MOVES = ['deposit', 'withdraw', 'transfer']; // the operations that move money
const cap = word => `${word[0].toUpperCase()}${word.slice(1)}`;
const UNKNOWN_ACCOUNTS = 'The result is unknown. Check account balances and history before submitting again.';

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
  const { t, errorText } = useI18n();
  return state.loading ? <Loading /> : state.error ? <div><p role="alert" className="error">{errorText(state.error)}</p><button type="button" onClick={state.retry}>{t('common.retry')}</button></div> : null;
}

function TransferFields({ from, to, setFrom, setTo }) {
  const { t } = useI18n();
  const state = useList('/accounts');
  return <>
    <ListStatus state={state} />
    {!state.loading && !state.error && <>
      {state.items.length < 2 && <p>{t('op.needTwo')}</p>}
      <label htmlFor="from-account">{t('op.from')}</label>
      <select id="from-account" required value={from} onChange={event => { setFrom(event.target.value); if (event.target.value === to) setTo(''); }}>
        <option value="">{t('op.fromChoose')}</option>
        {state.items.map(item => <option key={item.accountId} value={item.accountId}>{item.userName} · {accountTypeLabel(t, item.accountType)} · {item.accountId} · {money(item.balance)}</option>)}
      </select>
      <label htmlFor="to-account">{t('op.to')}</label>
      <select id="to-account" required value={to} onChange={event => setTo(event.target.value)}>
        <option value="">{t('op.toChoose')}</option>
        {state.items.filter(item => item.accountId !== from).map(item => <option key={item.accountId} value={item.accountId}>{item.userName} · {accountTypeLabel(t, item.accountType)} · {item.accountId}</option>)}
      </select>
    </>}
  </>;
}

function Operation({ operation, customer, onCancel, onSuccess, onBusy }) {
  const { t, errorText } = useI18n();
  const [amount, setAmount] = useState('');
  const [accountType, setAccountType] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  const dialog = useRef(null);
  const { kind, account } = operation;
  const movesMoney = MOVES.includes(kind);
  useEffect(() => { if (kind === 'delete') dialog.current?.showModal(); }, [kind]);

  async function submit(event) {
    event?.preventDefault();
    if (lock.current) return;
    if (movesMoney && (!new RegExp(`^${amountPattern}$`).test(amount) || !/[1-9]/.test(amount))) {
      setError('Enter a positive amount up to 99999999.99 with at most two decimal places.'); return;
    }
    if (kind === 'transfer' && (!from || !to || from === to)) { setError('Choose two different accounts.'); return; }
    if (kind === 'open' && !accountType) { setError('Select an account type.'); return; }
    lock.current = true; setBusy(true); onBusy(true); setError('');
    try {
      let path, options;
      if (kind === 'delete') { path = `/accounts/${encodeURIComponent(account.accountId)}`; options = { method: 'DELETE' }; }
      else if (kind === 'open') { path = '/accounts'; options = { method: 'POST', data: { customerId: customer.customerId, accountType } }; }
      else {
        path = kind === 'transfer' ? '/transfers' : `/accounts/${encodeURIComponent(account.accountId)}/${kind}`;
        options = { method: 'POST', idempotencyKey: crypto.randomUUID(), data: kind === 'transfer' ? { fromAccountId: from, toAccountId: to, amount } : { amount } };
      }
      await apiRequest(path, options);
      onSuccess(`op.done${cap(kind)}`);
    } catch (err) { setError(`${err.message}${movesMoney && err.message.startsWith('Unable to reach') ? ` ${UNKNOWN_ACCOUNTS}` : ''}`); }
    finally { lock.current = false; setBusy(false); onBusy(false); }
  }

  if (kind === 'delete') return <dialog ref={dialog} role="alertdialog" aria-modal="true" aria-labelledby="account-delete-title" onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="account-delete-title">{t('op.deleteTitle', { id: account.accountId })}</h2>
    <p>{t('op.deleteText')}</p>
    {error && <p role="alert" className="error">{errorText(error)}</p>}
    <div className="actions"><button autoFocus disabled={busy} className="secondary" onClick={onCancel}>{t('common.cancel')}</button><button disabled={busy} className="danger" onClick={submit}>{busy ? t('op.deleting') : t('op.deleteConfirm')}</button></div>
  </dialog>;
  return <section className="panel" aria-labelledby="operation-title">
    <h2 id="operation-title">{t(`op.${kind}`)}{account ? ` · ${account.accountId}` : ''}</h2>
    {error && <p role="alert" className="error">{errorText(error)}</p>}
    <form onSubmit={submit}><fieldset disabled={busy}>
      {kind === 'open' ? <><label htmlFor="account-type">{t('accounts.type')}</label><select id="account-type" autoFocus required value={accountType} onInvalid={event => event.target.setCustomValidity(t('err.accountType'))} onChange={event => { event.target.setCustomValidity(''); setAccountType(event.target.value); }}>
        <option value="" disabled>{t('accounts.typeChoose')}</option>
        {ACCOUNT_TYPES.map(type => <option key={type} value={type}>{accountTypeLabel(t, type)}</option>)}
      </select></> : <>
        {kind === 'transfer' && <TransferFields from={from} to={to} setFrom={setFrom} setTo={setTo} />}
        <label htmlFor="amount">{t('common.amount')}</label><input id="amount" autoFocus={kind !== 'transfer'} inputMode="decimal" required pattern={amountPattern} value={amount} onChange={event => setAmount(event.target.value)} aria-describedby="amount-help" />
        <p id="amount-help">{t('op.amountHelp')}</p>
      </>}
      <div className="actions"><button type="submit" disabled={kind === 'transfer' && (!from || !to)}>{busy ? t('op.submitting') : kind === 'open' ? t('accounts.create') : t(`op.submit${cap(kind)}`)}</button><button type="button" className="secondary" onClick={onCancel}>{t('common.cancel')}</button></div>
    </fieldset></form>
  </section>;
}

export function History({ account, onClose, onDeposit }) {
  const { t } = useI18n();
  const state = useList(`/accounts/${encodeURIComponent(account.accountId)}/transactions`);
  const typeLabel = type => { const text = t(`txn.${type}`); return text === `txn.${type}` ? type : text; };
  return <section className="panel tape-panel"><div className="heading"><h2>{t('history.title', { id: account.accountId })}</h2><button className="secondary" onClick={onClose}>{t('history.close')}</button></div>
    <ListStatus state={state} />
    {!state.loading && !state.error && (state.items.length === 0 ? <Empty title={t('history.emptyTitle')} hint={t('history.emptyHint')} action={onDeposit && { label: t('history.emptyAction'), onClick: onDeposit }} /> : <div className="tape"><table><caption>{t('history.caption')}</caption><thead><tr><th scope="col">{t('history.colDate')}</th><th scope="col">{t('history.colType')}</th><th scope="col" className="money">{t('history.colAmount')}</th><th scope="col" className="money">{t('history.colBalance')}</th></tr></thead><tbody>{state.items.map(item => { const flow = flowOf(item.type); return <tr key={item.txnId}><td className="t-date">{dateTime(item.date)}</td><td className="t-type">{typeLabel(item.type)}</td><td className={`money t-amount ${flow.className}`} data-label={t('history.colAmount')}>{flow.sign && <span aria-hidden="true">{flow.sign}</span>}{money(item.amount)}</td><td className="money t-bal" data-label={t('css.balance')}>{money(item.balanceAfter)}</td></tr>; })}</tbody></table></div>)}
  </section>;
}

export default function Accounts({ customer, onBack, onNavigationLock }) {
  const { t } = useI18n();
  const [revision, setRevision] = useState(0);
  const state = useList(customer ? `/customers/${encodeURIComponent(customer.customerId)}/accounts` : '/accounts/premium?limit=200', revision);
  const [operation, setOperation] = useState(null);
  const [history, setHistory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(''); // a dictionary key, so it follows a language change
  const opener = useRef(null);
  const heading = useRef(null);
  const disabled = busy || Boolean(operation);
  useEffect(() => { onNavigationLock?.(disabled); return () => onNavigationLock?.(false); }, [disabled, onNavigationLock]);
  function begin(kind, account, trigger = null) { opener.current = trigger; setMessage(''); setHistory(null); setOperation({ kind, account }); }
  // Closing a form or dialog hands focus back to the button that opened it; after a save the list reloads, so go to the heading.
  function closeOperation(saved) { setOperation(null); setTimeout(() => (!saved && opener.current?.isConnected ? opener.current : heading.current)?.focus(), 0); }
  function showHistory(account, trigger) { opener.current = trigger; setHistory(account); }
  function closeHistory() { setHistory(null); setTimeout(() => (opener.current?.isConnected ? opener.current : heading.current)?.focus(), 0); }
  const premiumTitle = t('nav.premium');
  return <>
    <button className="back-link" disabled={disabled} onClick={onBack}>{t('accounts.back')}</button>
    <div className="heading"><h1 ref={heading} tabIndex={-1}>{customer ? t('accounts.titleFor', { name: customer.name }) : premiumTitle}</h1><div className="actions">
      {customer && <button disabled={disabled || state.loading || Boolean(state.error)} onClick={event => begin('open', null, event.currentTarget)}>{t('accounts.open')}</button>}
      <button disabled={disabled} onClick={event => begin('transfer', null, event.currentTarget)}>{t('accounts.transfer')}</button>
      <button className="secondary" disabled={disabled || state.loading} onClick={state.retry}>{t('accounts.refresh')}</button>
    </div></div>
    {!customer && <p className="loading-note">{t('accounts.premiumNote')}</p>}
    {!state.loading && !state.error && state.items.length > 0 && <Summary items={[[t('accounts.combined'), money(state.items.reduce((sum, item) => sum + Number(item.balance), 0)), 'lead'], [customer ? t('accounts.held') : t('accounts.listed'), state.items.length], ...(customer ? [] : [[t('accounts.highest'), money(Math.max(...state.items.map(item => Number(item.balance))))]])]} />}
    <p role="status">{message && t(message)}</p>
    {operation && <Operation operation={operation} customer={customer} onBusy={setBusy} onCancel={() => closeOperation(false)} onSuccess={key => { closeOperation(true); setMessage(key); setRevision(value => value + 1); }} />}
    <ListStatus state={state} />
    {!state.loading && !state.error && (state.items.length === 0 ? <Empty title={t('accounts.emptyTitle')} hint={customer ? t('accounts.emptyHintCustomer') : t('accounts.emptyHintPremium')} action={customer ? { label: t('accounts.emptyOpen'), onClick: event => begin('open', null, event.currentTarget), disabled } : { label: t('accounts.back'), onClick: onBack, disabled }} /> : <table className="cards"><caption>{customer ? t('accounts.captionCustomer') : premiumTitle}</caption><thead><tr><th scope="col">{t('accounts.colId')}</th><th scope="col">{t('accounts.colOwner')}</th><th scope="col">{t('accounts.colType')}</th><th scope="col">{t('accounts.colOpened')}</th><th scope="col" className="money">{t('accounts.colBalance')}</th><th scope="col">{t('common.actions')}</th></tr></thead><tbody>{state.items.map(account => <tr key={account.accountId}>
      <AccountCells account={account} showOwner history={history} disabled={disabled} begin={begin} showHistory={showHistory} />
    </tr>)}</tbody></table>)}
    {history && <History key={history.accountId} account={history} onClose={closeHistory} onDeposit={() => begin('deposit', history, opener.current)} />}
  </>;
}

// The cells of one account card; shared by the administrator list and the customer's own list.
// With begin set, the card carries every action; otherwise it only offers History.
export function AccountCells({ account, showOwner = false, history, disabled = false, begin, showHistory }) {
  const { t } = useI18n();
  return <>
    <th scope="row" className="identifier c-id">{account.accountId}</th><td className="c-type" data-label={t('accounts.colType')}>{accountTypeLabel(t, account.accountType)}<span className="c-end">{t('accounts.ending', { id: String(account.accountId).slice(-4) })}</span></td>
    {showOwner && <td className="c-owner" data-label={t('accounts.colOwner')}>{account.userName}</td>}
    <td className="c-opened" data-label={t('accounts.colOpened')}>{shortDate(account.createdAt)}</td><td className="money c-bal" data-label={t('accounts.colBalance')}>{money(account.balance)}</td>
    <td className="c-act"><div className="actions account-actions">
      {begin && <><button disabled={disabled} onClick={event => begin('deposit', account, event.currentTarget)}>{t('accounts.deposit')}</button><button disabled={disabled} onClick={event => begin('withdraw', account, event.currentTarget)}>{t('accounts.withdraw')}</button></>}
      <button className="secondary" aria-pressed={history?.accountId === account.accountId} disabled={disabled} onClick={event => showHistory(account, event.currentTarget)}>{t('accounts.history')}</button>
      {begin && <button className="secondary danger-text" disabled={disabled || !isZero(account.balance)} title={t('accounts.deleteHintTitle')} aria-label={t('accounts.deleteFor', { id: account.accountId })} onClick={event => begin('delete', account, event.currentTarget)}>{t('accounts.delete')}</button>}
    </div>{begin && !isZero(account.balance) && <p className="c-hint">{t('accounts.deleteNeedsZero')}</p>}</td>
  </>;
}
