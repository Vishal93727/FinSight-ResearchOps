import { useEffect, useState, type FormEvent } from 'react';
import { apiRequest } from '../lib/api';

type Role = { key: string; name: string };
type Me = { id: string; email: string; full_name: string; roles: Role[] };
type UserSummary = { id: string; email: string; full_name: string; roles: Role[]; is_active: boolean };
type UserList = { users: UserSummary[]; total: number };
type Instrument = { id: string; symbol: string; name: string; exchange: string; asset_type: string };
type OperationsSummary = { generated_at: string; environment: string; services: Record<string, string>; worker_names: string[]; stale_job_count: number; recent_failures: { id: string; task_name: string; status: string; created_at: string; completed_at: string | null; failure_recorded: boolean }[]; jobs: Record<string, number>; experiment_runs: Record<string, number>; paper_execution: { accounts: number; kill_switch_enabled_accounts: number; orders_by_status: Record<string, number> }; governance: { model_versions_by_state: Record<string, number> }; feedback: { realised_outcomes: number; open_drift_assessments: number; proposed_research_suggestions: number }; notes: string[] };
const ROLE_OPTIONS = ['ADMIN', 'RESEARCH_ANALYST', 'QUANT_RESEARCHER', 'RISK_REVIEWER', 'PORTFOLIO_ANALYST', 'READ_ONLY_VIEWER'];

export function AdminPage({ token }: { token: string }) {
  const [me, setMe] = useState<Me | null>(null);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [newName, setNewName] = useState('');
  const [newExchange, setNewExchange] = useState('NASDAQ');
  const [newAssetType, setNewAssetType] = useState<'EQUITY' | 'ETF'>('EQUITY');
  const [selectedRoles, setSelectedRoles] = useState<Record<string, string[]>>({});
  const [health, setHealth] = useState<string>('Checking…');
  const [operations, setOperations] = useState<OperationsSummary | null>(null);
  const [recovery, setRecovery] = useState<{ mode: string; candidate_count: number; candidates?: { id: string; task_name: string; status: string }[]; results?: { job_id: string; status: string }[]; warning: string } | null>(null);
  const [recoveryBusy, setRecoveryBusy] = useState(false);
  const [operationsBusy, setOperationsBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyUser, setBusyUser] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    apiRequest<Me>('/auth/me', { token }).then(async identity => {
      if (!live) return;
      setMe(identity);
      const catalogue = await apiRequest<Instrument[]>('/instruments', { token });
      if (live) setInstruments(catalogue);
      if (identity.roles.some(role => ['ADMIN', 'RISK_REVIEWER', 'PORTFOLIO_ANALYST', 'READ_ONLY_VIEWER'].includes(role.key))) {
        const summary = await apiRequest<OperationsSummary>('/operations/summary', { token });
        if (live) setOperations(summary);
      }
      if (identity.roles.some(role => role.key === 'ADMIN')) {
        const result = await apiRequest<UserList>('/users', { token });
        if (live) {
          setUsers(result.users);
          setSelectedRoles(Object.fromEntries(result.users.map(user => [user.id, user.roles.map(role => role.key)])));
        }
      }
    }).catch(err => { if (live) setError(err instanceof Error ? err.message : 'Unable to load identity'); });
    apiRequest<{ status: string }>('/health/ready').then(() => { if (live) setHealth('Ready'); })
      .catch(() => { if (live) setHealth('Dependencies not ready'); });
    return () => { live = false; };
  }, [token]);

  async function createInstrument(event: FormEvent) {
    event.preventDefault(); setError(''); setNotice('');
    try {
      const created = await apiRequest<Instrument>('/instruments', {
        method: 'POST', token,
        body: JSON.stringify({ symbol: newSymbol.trim().toUpperCase(), name: newName.trim(), exchange: newExchange, asset_type: newAssetType, currency: 'USD' }),
      });
      setInstruments(current => [...current, created].sort((a, b) => a.symbol.localeCompare(b.symbol)));
      setNewSymbol(''); setNewName('');
      setNotice(`Added ${created.symbol} to the instrument catalogue.`);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to create instrument'); }
  }



  async function refreshOperations() {
    setOperationsBusy(true); setError('');
    try {
      const summary = await apiRequest<OperationsSummary>('/operations/summary', { token });
      setOperations(summary);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to refresh operations summary'); }
    finally { setOperationsBusy(false); }
  }

  async function recoverStaleJobs(confirmRequeue: boolean) {
    setRecoveryBusy(true); setError(''); setNotice('');
    try {
      const result = await apiRequest<typeof recovery>('/operations/recover-stale-jobs', {
        method: 'POST', token, body: JSON.stringify({ stale_after_minutes: 30, limit: 50, confirm_requeue: confirmRequeue }),
      });
      setRecovery(result);
      if (confirmRequeue) setNotice('Recovery dispatch submitted. Check the job list and worker logs to confirm completion.');
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to inspect/requeue stale jobs'); }
    finally { setRecoveryBusy(false); }
  }

  async function saveRoles(userId: string) {
    setBusyUser(userId); setError(''); setNotice('');
    try {
      const updated = await apiRequest<UserSummary>(`/users/${userId}/roles`, {
        method: 'PATCH', token, body: JSON.stringify({ role_keys: selectedRoles[userId] ?? [] }),
      });
      setUsers(current => current.map(user => user.id === userId ? updated : user));
      setNotice(`Updated roles for ${updated.email}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update roles');
    } finally { setBusyUser(null); }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">PLATFORM CONTROL</p><h2>Operations & administration</h2><p className="muted">Identity, runtime health, job queues, governance and paper-portfolio operations.</p></div></div>
    {error && <p className="error-banner">{error}</p>}
    {notice && <p className="success-banner">{notice}</p>}
    {operations && <><section className="panel phase5-operations-panel"><div className="panel-title"><div><p className="eyebrow">RUNTIME SNAPSHOT</p><h3>Operations health</h3></div><button className="secondary-button" disabled={operationsBusy} onClick={() => void refreshOperations()}>{operationsBusy ? 'Refreshing…' : 'Refresh snapshot'}</button></div><div className="metric-grid phase5-metrics">
      <article className="metric-card"><span>Database</span><strong>{operations.services.database}</strong><small>{operations.environment} environment</small></article>
      <article className="metric-card"><span>Redis</span><strong>{operations.services.redis}</strong><small>Queue dependency</small></article>
      <article className="metric-card"><span>Celery worker</span><strong>{operations.services.worker ?? 'unknown'}</strong><small>{operations.worker_names?.length ? operations.worker_names.join(', ') : 'No responding worker detected'}</small></article>
      <article className="metric-card"><span>Stale jobs</span><strong>{operations.stale_job_count ?? 0}</strong><small>Queued/running for 30+ minutes</small></article>
      <article className="metric-card"><span>Paper accounts</span><strong>{operations.paper_execution.accounts}</strong><small>{operations.paper_execution.kill_switch_enabled_accounts} kill switches active</small></article>
      <article className="metric-card"><span>Realised outcomes</span><strong>{operations.feedback.realised_outcomes}</strong><small>Feedback ledger records</small></article>
      <article className="metric-card"><span>Open drift reviews</span><strong>{operations.feedback.open_drift_assessments}</strong><small>Feature monitoring flags</small></article>
    </div></section><div className="panel-grid"><section className="panel"><h3>Background job queue</h3>{Object.entries(operations.jobs).map(([status, count]) => <div className="list-row" key={status}><strong>{status}</strong><span className="tiny-status">{count}</span></div>)}{!Object.keys(operations.jobs).length && <p className="muted small">No jobs recorded.</p>}</section><section className="panel"><h3>Experiment runs, models and paper orders</h3>{Object.entries(operations.experiment_runs).map(([status, count]) => <div className="list-row" key={status}><strong>Runs · {status}</strong><span className="tiny-status">{count}</span></div>)}{Object.entries(operations.governance.model_versions_by_state).map(([status, count]) => <div className="list-row" key={status}><strong>Models · {status}</strong><span className="tiny-status">{count}</span></div>)}{Object.entries(operations.paper_execution.orders_by_status).map(([status, count]) => <div className="list-row" key={status}><strong>Paper orders · {status}</strong><span className="tiny-status">{count}</span></div>)}</section></div><section className="panel"><h3>Recent failed jobs</h3>{operations.recent_failures?.map(job => <div className="list-row" key={job.id}><div><strong>{job.task_name}</strong><small>{job.id.slice(0, 8)} · {new Date(job.created_at).toLocaleString()} · {job.failure_recorded ? 'Failure details recorded; inspect protected logs' : 'No failure detail recorded'}</small></div><span className={`run-status ${job.status.toLowerCase()}`}>{job.status}</span></div>)}{!operations.recent_failures?.length && <p className="muted small">No failed jobs in the latest records.</p>}</section><p className="muted small">Snapshot generated {new Date(operations.generated_at).toLocaleString()}. Counts are database snapshots, not uptime/SLO measurements.</p></>}
    {operations && <section className="panel"><h3>Monitoring tools</h3><p className="muted small">Local Compose endpoints for service metrics and traces. These tools are loopback-bound by default and should not be exposed publicly without authentication and network policy.</p><div className="ops-tool-links"><a href="http://localhost:9090" target="_blank" rel="noreferrer">Prometheus ↗</a><a href="http://localhost:3000" target="_blank" rel="noreferrer">Grafana ↗</a><a href="/metrics" target="_blank" rel="noreferrer">API metrics ↗</a><a href="/docs" target="_blank" rel="noreferrer">OpenAPI docs ↗</a></div></section>}
    <div className="panel-grid">
      <section className="panel"><h3>Signed-in user</h3>{me ? <><strong>{me.full_name}</strong><p className="muted">{me.email}</p><div className="role-list">{me.roles.map(role => <span className="tag" key={role.key}>{role.name}</span>)}</div></> : <p className="muted">Loading account…</p>}</section>
      <section className="panel"><h3>Service readiness</h3><div className="health-value">{health}</div><p className="muted small">Readiness requires both the configured database and Redis queue to respond.</p><a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">Open API documentation ↗</a></section>
    </div>
    <section className="panel"><div className="panel-title"><h3>Instrument catalogue</h3><span className="tag">US equities & ETFs</span></div>
      {instruments.length ? <div className="table-scroll"><table><thead><tr><th>Symbol</th><th>Company / Fund</th><th>Exchange</th><th>Type</th></tr></thead><tbody>{instruments.map(item => <tr key={item.id}><td>{item.symbol}</td><td>{item.name}</td><td>{item.exchange}</td><td>{item.asset_type}</td></tr>)}</tbody></table></div> : <p className="muted small">No instruments registered yet. Add one before uploading its market-data CSV.</p>}
      {me?.roles.some(role => ['ADMIN', 'QUANT_RESEARCHER'].includes(role.key)) && <form className="catalogue-form" onSubmit={createInstrument}>
        <label>Symbol<input required value={newSymbol} onChange={event => setNewSymbol(event.target.value)} placeholder="MSFT" /></label>
        <label>Company / fund name<input required value={newName} onChange={event => setNewName(event.target.value)} placeholder="Microsoft Corporation" /></label>
        <label>Exchange<input required value={newExchange} onChange={event => setNewExchange(event.target.value)} /></label>
        <label>Asset type<select value={newAssetType} onChange={event => setNewAssetType(event.target.value as 'EQUITY' | 'ETF')}><option value="EQUITY">Equity</option><option value="ETF">ETF</option></select></label>
        <button className="primary-button" disabled={!newSymbol.trim() || !newName.trim()}>Add instrument</button>
      </form>}
    </section>
    {me?.roles.some(role => role.key === 'ADMIN') && <section className="panel"><div className="panel-title"><h3>User & role management</h3><span className="tag">Administrator</span></div>
      <p className="muted small">Choose one or more roles for each account. Access rules are applied by the backend, not only by this interface.</p>
      {users.map(user => <div className="admin-user-row" key={user.id}><div className="admin-user-identity"><strong>{user.full_name}</strong><small>{user.email}</small></div><select multiple value={selectedRoles[user.id] ?? []} onChange={event => setSelectedRoles(current => ({ ...current, [user.id]: Array.from(event.target.selectedOptions, option => option.value) }))}>{ROLE_OPTIONS.map(role => <option key={role} value={role}>{role.replaceAll('_', ' ')}</option>)}</select><button className="secondary-button" disabled={busyUser === user.id || !(selectedRoles[user.id]?.length)} onClick={() => saveRoles(user.id)}>{busyUser === user.id ? 'Saving…' : 'Save roles'}</button></div>)}
    </section>}
    {me?.roles.some(role => role.key === 'ADMIN') && <section className="panel"><div className="panel-title"><h3>Worker recovery</h3><span className="tag">Administrator only</span></div><p className="muted small">Preview jobs stuck in queued, running or queue-failed states for at least 30 minutes. Confirm only after checking worker health and logs; requeue preserves the existing job ID and payload.</p><button className="secondary-button" disabled={recoveryBusy} onClick={() => void recoverStaleJobs(false)}>Preview stale jobs</button>{recovery && <div className="result-card"><strong>{recovery.mode} · {recovery.candidate_count} candidate(s)</strong><small>{recovery.warning}</small>{recovery.candidates?.map(job => <div className="list-row" key={job.id}><span className="mono">{job.id.slice(0, 8)} · {job.task_name}</span><span>{job.status}</span></div>)}{recovery.results?.map(job => <div className="list-row" key={job.job_id}><span className="mono">{job.job_id.slice(0, 8)}</span><span>{job.status}</span></div>)}{recovery.mode === 'DRY_RUN' && recovery.candidate_count > 0 && <button className="primary-button" disabled={recoveryBusy} onClick={() => void recoverStaleJobs(true)}>Confirm requeue {recovery.candidate_count} job(s)</button>}</div>}</section>}
    <section className="panel"><h3>Access model</h3><p className="muted">Self-registration creates a Research Analyst account only. The first platform administrator must be bootstrapped through the protected command-line script after database migrations.</p><pre>python backend/scripts/create_admin.py --email admin@example.com --name "Platform Admin"</pre></section>
  </>;
}
