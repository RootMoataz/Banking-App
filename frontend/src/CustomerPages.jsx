import { useEffect, useRef, useState } from 'react';
import { apiRequest } from './api';
import { AccountCells, History, ListStatus, amountPattern, useList } from './Accounts';
import { useAuth } from './auth';
import { useI18n } from './i18n';
import { Empty, Summary, money } from './ui';

const amountOk = amount => new RegExp(`^${amountPattern}$`).test(amount) && /[1-9]/.test(amount);
const UNKNOWN_OWN = 'The result is unknown. Check your balances and history before submitting again.';

function OpenAccount({ customerId, onCancel, onDone }) {
  const { t, errorText } = useI18n();
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
  return <section className="panel" aria-labelledby="open-title"><h2 id="open-title">{t('accounts.open')}</h2>
    {error && <p role="alert" className="error">{errorText(error)}</p>}
    <form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="account-type">{t('accounts.type')}</label>
      <input id="account-type" autoFocus required maxLength={50} value={accountType} onChange={event => setAccountType(event.target.value)} />
      <div className="actions"><button type="submit">{busy ? t('op.submitting') : t('accounts.create')}</button><button type="button" className="secondary" onClick={onCancel}>{t('common.cancel')}</button></div>
    </fieldset></form>
  </section>;
}

export function MyAccounts() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [revision, setRevision] = useState(0);
  const state = useList(`/customers/${encodeURIComponent(user.customerId)}/accounts`, revision);
  const [opening, setOpening] = useState(false);
  const [history, setHistory] = useState(null);
  const [message, setMessage] = useState(''); // a dictionary key, so it follows a language change
  const opener = useRef(null);
  const heading = useRef(null);
  function openForm(event) { opener.current = event.currentTarget; setMessage(''); setHistory(null); setOpening(true); }
  function closeForm(saved) { setOpening(false); setTimeout(() => (!saved && opener.current?.isConnected ? opener.current : heading.current)?.focus(), 0); }
  function showHistory(account, trigger) { opener.current = trigger; setHistory(account); }
  function closeHistory() { setHistory(null); setTimeout(() => (opener.current?.isConnected ? opener.current : heading.current)?.focus(), 0); }
  return <>
    <div className="heading"><div><h1 ref={heading} tabIndex={-1}>{t('accounts.mineTitle')}</h1><p>{t('accounts.mineIntro')}</p></div><div className="actions">
      <button disabled={opening || state.loading || Boolean(state.error)} onClick={openForm}>{t('accounts.open')}</button>
    </div></div>
    {!state.loading && !state.error && state.items.length > 0 && <Summary items={[[t('accounts.combined'), money(state.items.reduce((sum, item) => sum + Number(item.balance), 0)), 'lead'], [t('accounts.held'), state.items.length]]} />}
    <p role="status">{message && t(message)}</p>
    {opening && <OpenAccount customerId={user.customerId} onCancel={() => closeForm(false)} onDone={() => { closeForm(true); setMessage('op.doneOpen'); setRevision(value => value + 1); }} />}
    <ListStatus state={state} />
    {!state.loading && !state.error && (state.items.length === 0 ? <Empty title={t('accounts.mineEmptyTitle')} hint={t('accounts.mineEmptyHint')} action={{ label: t('accounts.mineEmptyAction'), onClick: openForm, disabled: opening }} /> : <table className="cards"><caption>{t('accounts.mineTitle')}</caption><thead><tr><th scope="col">{t('accounts.colId')}</th><th scope="col">{t('accounts.colType')}</th><th scope="col">{t('accounts.colOpened')}</th><th scope="col" className="money">{t('accounts.colBalance')}</th><th scope="col">{t('common.actions')}</th></tr></thead><tbody>{state.items.map(account => <tr key={account.accountId}>
      <AccountCells account={account} history={history} showHistory={showHistory} />
    </tr>)}</tbody></table>)}
    {history && <History key={history.accountId} account={history} onClose={closeHistory} />}
  </>;
}

export function Transfer() {
  const { t, errorText } = useI18n();
  const { user } = useAuth();
  const [revision, setRevision] = useState(0);
  const state = useList(`/customers/${encodeURIComponent(user.customerId)}/accounts`, revision);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState(''); // a dictionary key, so it follows a language change
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
      setTo(''); setAmount(''); setMessage('op.doneTransfer'); setRevision(value => value + 1);
    } catch (err) { setError(`${err.message}${err.message.startsWith('Unable to reach') ? ` ${UNKNOWN_OWN}` : ''}`); }
    finally { lock.current = false; setBusy(false); }
  }
  return <>
    <div className="heading"><div><h1>{t('transfer.title')}</h1><p>{t('transfer.intro')}</p></div></div>
    <p role="status">{message && t(message)}</p>
    <ListStatus state={state} />
    {!state.loading && !state.error && <section className="panel" aria-labelledby="transfer-title"><h2 id="transfer-title">{t('transfer.panel')}</h2>
      {error && <p role="alert" className="error">{errorText(error)}</p>}
      {state.items.length === 0 ? <p>{t('transfer.needAccount')}</p> : <form onSubmit={submit}><fieldset disabled={busy}>
        <label htmlFor="from-account">{t('op.from')}</label>
        <select id="from-account" required value={from} onChange={event => setFrom(event.target.value)}>
          <option value="">{t('op.fromChoose')}</option>
          {state.items.map(item => <option key={item.accountId} value={item.accountId}>{item.accountType} · {item.accountId} · {money(item.balance)}</option>)}
        </select>
        <label htmlFor="to-account">{t('transfer.toId')}</label>
        <input id="to-account" required maxLength={64} value={to} onChange={event => setTo(event.target.value)} />
        <label htmlFor="amount">{t('common.amount')}</label>
        <input id="amount" inputMode="decimal" required pattern={amountPattern} value={amount} onChange={event => setAmount(event.target.value)} aria-describedby="amount-help" />
        <p id="amount-help">{t('op.amountHelp')}</p>
        <div className="actions"><button type="submit">{busy ? t('op.submitting') : t('transfer.submit')}</button></div>
      </fieldset></form>}
    </section>}
  </>;
}

export function Profile() {
  const { t } = useI18n();
  const { user } = useAuth();
  return <>
    <div className="heading"><div><h1>{t('profile.title')}</h1><p>{t('profile.intro')}</p></div></div>
    <Summary items={[[t('common.name'), user.name], [t('common.email'), user.email]]} />
  </>;
}

export function AccessDenied() {
  const { t } = useI18n();
  return <div className="panel"><h1>{t('denied.title')}</h1><p role="alert" className="error">{t('denied.text')}</p></div>;
}
