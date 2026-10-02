import { useEffect, useRef, useState } from 'react';
import { customerRequest } from './api';
import './styles.css';
import Accounts from './Accounts';
import logo from './assets/paper-maker-logo.png';

function CustomerForm({ customer, busy, onSave, onCancel }) {
  const [name, setName] = useState(customer?.name || '');
  const [email, setEmail] = useState(customer?.email || '');
  return <section className="panel" aria-labelledby="form-title">
    <h2 id="form-title">{customer ? 'Edit customer' : 'Add customer'}</h2>
    <form onSubmit={event => { event.preventDefault(); if (name.trim()) onSave({ name: name.trim(), email: email.trim() }); }}>
      <fieldset disabled={busy}>
        <label htmlFor="name">Name</label>
        <input id="name" autoFocus value={name} onChange={event => setName(event.target.value)} required maxLength={100} pattern=".*\S.*" autoComplete="name" />
        <label htmlFor="email">Email</label>
        <input id="email" type="email" value={email} onChange={event => setEmail(event.target.value)} required maxLength={100} autoComplete="email" />
        <div className="actions"><button type="submit">{busy ? 'Saving…' : 'Save customer'}</button><button type="button" className="secondary" onClick={onCancel}>Cancel</button></div>
      </fieldset>
    </form>
  </section>;
}

function DeleteDialog({ customer, busy, error, onDelete, onCancel }) {
  const ref = useRef(null);
  useEffect(() => { ref.current?.showModal?.(); }, []);
  return <dialog ref={ref} role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-description" onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="delete-title">Delete {customer.name}?</h2>
    <p id="delete-description">This permanently deletes this customer and all their accounts, including any remaining balances. Transaction and notification history is retained.</p>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="actions"><button autoFocus className="secondary" disabled={busy} onClick={onCancel}>Cancel</button><button className="danger" disabled={busy} onClick={onDelete}>{busy ? 'Deleting…' : 'Delete customer'}</button></div>
  </dialog>;
}

export default function App() {
  const [accountNavigationLocked, setAccountNavigationLocked] = useState(false);
  const [accountView, setAccountView] = useState(null);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reload, setReload] = useState(0);
  const [form, setForm] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigationLocked = accountNavigationLocked || busy || Boolean(form) || Boolean(deleting);
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
  function closeDelete() { setDeleting(null); setError(''); actionButton.current?.focus(); }
  async function save(data) {
    if (busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const editing = form.customer;
      const saved = await customerRequest(editing ? `/${encodeURIComponent(editing.customerId)}` : '', { method: editing ? 'PUT' : 'POST', data });
      setCustomers(previous => editing ? previous.map(item => item.customerId === saved.customerId ? saved : item) : [...previous, saved]);
      closeEditor(); setMessage(editing ? 'Customer updated.' : 'Customer added.');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await customerRequest(`/${encodeURIComponent(deleting.customerId)}`, { method: 'DELETE' });
      setCustomers(previous => previous.filter(item => item.customerId !== deleting.customerId));
      setDeleting(null); setMessage('Customer deleted.'); addButton.current?.focus();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header><div className="container brand-row"><img className="brand-logo" src={logo} alt="" /><p className="brand">Paper Maker Banking</p></div>
      <nav aria-label="Main navigation"><div className="container nav-items">
        <button disabled={navigationLocked} aria-current={!accountView ? 'page' : undefined} onClick={() => setAccountView(null)}>Customers</button>
        <button disabled={navigationLocked} aria-current={accountView && !accountView.customer ? 'page' : undefined} onClick={() => setAccountView({ customer: null })}>Premium accounts</button>
      </div></nav>
    </header>
    <main id="main" className="container">
      {accountView ? <Accounts key={accountView.customer?.customerId || "premium"} onNavigationLock={setAccountNavigationLocked} customer={accountView.customer} onBack={() => setAccountView(null)} /> : <>
      <div className="heading"><div><h1 id="customers">Customers</h1><p>Manage customer names and contact details.</p></div><button ref={addButton} disabled={loading || Boolean(loadError) || busy || Boolean(form) || Boolean(deleting)} onClick={() => { actionButton.current = addButton.current; setError(''); setMessage(''); setForm({ customer: null }); }}>Add customer</button></div>
      <p role="status">{message}</p>
      {loading ? <p>Loading customers…</p> : loadError ? <div className="panel"><p role="alert" className="error">{loadError}</p><button onClick={() => setReload(value => value + 1)}>Retry</button></div> : <>
        {error && !deleting && <p role="alert" className="error">{error}</p>}
        {form && <CustomerForm key={form.customer?.customerId || 'new'} customer={form.customer} busy={busy} onSave={save} onCancel={closeEditor} />}
        {customers.length === 0 ? <p className="panel">No customers yet.</p> : <div className="table-scroll"><table><caption>{customers.length} {customers.length === 1 ? 'customer' : 'customers'}</caption><thead><tr><th scope="col">Name</th><th scope="col">Email</th><th scope="col">Customer ID</th><th scope="col">Actions</th></tr></thead><tbody>{customers.map(customer => <tr key={customer.customerId}><th scope="row">{customer.name}</th><td>{customer.email}</td><td className="identifier">{customer.customerId}</td><td><div className="actions"><button className="secondary" disabled={busy || Boolean(form) || Boolean(deleting)} aria-label={`Accounts for ${customer.name}`} onClick={() => setAccountView({ customer })}>Accounts</button><button className="secondary" disabled={busy || Boolean(form) || Boolean(deleting)} aria-label={`Edit ${customer.name}`} onClick={event => { actionButton.current = event.currentTarget; setError(''); setMessage(''); setForm({ customer }); }}>Edit</button><button className="secondary danger-text" disabled={busy || Boolean(form) || Boolean(deleting)} aria-label={`Delete ${customer.name}`} onClick={event => { actionButton.current = event.currentTarget; setError(''); setMessage(''); setDeleting(customer); }}>Delete</button></div></td></tr>)}</tbody></table></div>}
      </>}
      {deleting && <DeleteDialog customer={deleting} busy={busy} error={error} onDelete={remove} onCancel={closeDelete} />}
      </>}
    </main>
    <footer className="container">Paper Maker Banking · Customer management</footer>
  </>;
}

