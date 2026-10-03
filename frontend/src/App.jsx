import { useEffect, useRef, useState } from 'react';
import { customerRequest } from './api';
import './styles.css';
import Accounts from './Accounts';
import { useI18n } from './i18n';
import Shell from './Shell';
import { Empty, Loading, Summary, initials, shortDate } from './ui';

function CustomerForm({ customer, busy, onSave, onCancel }) {
  const { t } = useI18n();
  const [name, setName] = useState(customer?.name || '');
  const [email, setEmail] = useState(customer?.email || '');
  return <section className="panel" aria-labelledby="form-title">
    <h2 id="form-title">{customer ? t('customers.editTitle') : t('customers.addTitle')}</h2>
    <form onSubmit={event => { event.preventDefault(); if (name.trim()) onSave({ name: name.trim(), email: email.trim() }); }}>
      <fieldset disabled={busy}>
        <label htmlFor="name">{t('common.name')}</label>
        <input id="name" autoFocus value={name} onChange={event => setName(event.target.value)} required maxLength={100} pattern=".*\S.*" autoComplete="name" />
        <label htmlFor="email">{t('common.email')}</label>
        <input id="email" type="email" value={email} onChange={event => setEmail(event.target.value)} required maxLength={100} autoComplete="email" />
        <div className="actions"><button type="submit">{busy ? t('customers.saving') : t('customers.save')}</button><button type="button" className="secondary" onClick={onCancel}>{t('common.cancel')}</button></div>
      </fieldset>
    </form>
  </section>;
}

function DeleteDialog({ customer, busy, error, onDelete, onCancel }) {
  const { t, errorText } = useI18n();
  const ref = useRef(null);
  useEffect(() => { ref.current?.showModal?.(); }, []);
  return <dialog ref={ref} role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-description" onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="delete-title">{t('customers.deleteTitle', { name: customer.name })}</h2>
    <p id="delete-description">{t('customers.deleteText')}</p>
    {error && <p role="alert" className="error">{errorText(error)}</p>}
    <div className="actions"><button autoFocus className="secondary" disabled={busy} onClick={onCancel}>{t('common.cancel')}</button><button className="danger" disabled={busy} onClick={onDelete}>{busy ? t('customers.deleting') : t('customers.deleteConfirm')}</button></div>
  </dialog>;
}

export default function App({ initialView, onSignOut }) {
  const { t, errorText } = useI18n();
  const [accountNavigationLocked, setAccountNavigationLocked] = useState(false);
  const [accountView, setAccountView] = useState(initialView === 'premium' ? { customer: null } : null);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState(''); // a dictionary key, so it follows a language change
  const [reload, setReload] = useState(0);
  const [form, setForm] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const actionsLocked = busy || Boolean(form) || Boolean(deleting);
  const navigationLocked = accountNavigationLocked || actionsLocked;
  const addButton = useRef(null);
  const actionButton = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setLoadError('');
    customerRequest('', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setCustomers(data); })
      .catch(err => { if (!controller.signal.aborted) setLoadError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);

  function closeEditor() { setForm(null); setError(''); (actionButton.current || addButton.current)?.focus(); }
  // Focus moves after the modal dialog has left the DOM; while it is open the page behind it is inert.
  function closeDelete() { setDeleting(null); setError(''); setTimeout(() => actionButton.current?.focus(), 0); }
  async function save(data) {
    if (busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const editing = form.customer;
      const saved = await customerRequest(editing ? `/${encodeURIComponent(editing.customerId)}` : '', { method: editing ? 'PUT' : 'POST', data });
      setCustomers(previous => editing ? previous.map(item => item.customerId === saved.customerId ? saved : item) : [...previous, saved]);
      closeEditor(); setMessage(editing ? 'customers.updated' : 'customers.added');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await customerRequest(`/${encodeURIComponent(deleting.customerId)}`, { method: 'DELETE' });
      setCustomers(previous => previous.filter(item => item.customerId !== deleting.customerId));
      setDeleting(null); setMessage('customers.deleted'); setTimeout(() => addButton.current?.focus(), 0);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  const navItems = [
    { label: t('nav.customers'), icon: 'users', current: !accountView, disabled: navigationLocked, onSelect: () => setAccountView(null) },
    { label: t('nav.premium'), icon: 'star', current: Boolean(accountView && !accountView.customer), disabled: navigationLocked, onSelect: () => setAccountView({ customer: null }) },
  ];
  const openForm = (trigger, customer = null) => { actionButton.current = trigger; setError(''); setMessage(''); setForm({ customer }); };

  return <Shell items={navItems} onSignOut={onSignOut}>
      {accountView ? <Accounts key={accountView.customer?.customerId || "premium"} onNavigationLock={setAccountNavigationLocked} customer={accountView.customer} onBack={() => setAccountView(null)} /> : <>
      <div className="heading"><div><h1 id="customers">{t('customers.title')}</h1><p>{t('customers.intro')}</p></div><div className="actions"><button ref={addButton} disabled={loading || Boolean(loadError) || actionsLocked} onClick={() => openForm(addButton.current)}>{t('customers.add')}</button></div></div>
      {!loading && !loadError && <Summary items={[[t('customers.onRecord'), customers.length, 'lead'], [t('customers.marketing'), customers.filter(item => item.marketingEnabled === true).length]]} />}
      <p role="status">{message && t(message)}</p>
      {loading ? <Loading label={t('customers.loading')} rows={5} /> : loadError ? <div className="panel"><p role="alert" className="error">{errorText(loadError)}</p><button onClick={() => setReload(value => value + 1)}>{t('common.retry')}</button></div> : <>
        {error && !deleting && <p role="alert" className="error">{errorText(error)}</p>}
        {form && <CustomerForm key={form.customer?.customerId || 'new'} customer={form.customer} busy={busy} onSave={save} onCancel={closeEditor} />}
        {customers.length === 0 ? <Empty title={t('customers.emptyTitle')} hint={t('customers.emptyHint')} action={{ label: t('customers.emptyAction'), disabled: actionsLocked, onClick: () => openForm(addButton.current) }} /> : <div className="table-scroll"><table className="stack"><caption>{t('customers.caption', { count: customers.length })}</caption><thead><tr><th scope="col">{t('common.name')}</th><th scope="col">{t('common.email')}</th><th scope="col">{t('customers.colId')}</th><th scope="col">{t('customers.colSince')}</th><th scope="col">{t('common.actions')}</th></tr></thead><tbody>{customers.map(customer => <tr key={customer.customerId}><th scope="row"><span className="person"><span className="monogram" aria-hidden="true">{initials(customer.name)}</span><span>{customer.name}</span></span></th><td className="c-email" data-label={t('common.email')}>{customer.email}</td><td className="identifier" data-label={t('customers.colId')}>{customer.customerId}</td><td data-label={t('customers.colSince')}>{shortDate(customer.createdAt)}</td><td><div className="actions"><button className="secondary" disabled={actionsLocked} aria-label={t('customers.accountsFor', { name: customer.name })} onClick={() => setAccountView({ customer })}>{t('customers.accounts')}</button><button className="secondary" disabled={actionsLocked} aria-label={t('customers.editFor', { name: customer.name })} onClick={event => openForm(event.currentTarget, customer)}>{t('customers.edit')}</button><button className="secondary danger-text" disabled={actionsLocked} aria-label={t('customers.deleteFor', { name: customer.name })} onClick={event => { actionButton.current = event.currentTarget; setError(''); setMessage(''); setDeleting(customer); }}>{t('customers.delete')}</button></div></td></tr>)}</tbody></table></div>}
      </>}
      {deleting && <DeleteDialog customer={deleting} busy={busy} error={error} onDelete={remove} onCancel={closeDelete} />}
      </>}
  </Shell>;
}
