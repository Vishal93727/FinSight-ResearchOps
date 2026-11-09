import { useEffect, useState, type ReactNode } from 'react';
import { Activity, Database, FileText, ShieldCheck } from 'lucide-react';
import { apiRequest } from '../lib/api';

type Instrument = { symbol: string; name: string; exchange: string };
type Provider = { key: string; display_name: string; provider_type: string };
type Snapshot = { id: string; instrument_symbol: string; row_count: number; created_at: string; sha256: string };

export function OverviewPage({ token }: { token: string }) {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    Promise.all([
      apiRequest<Instrument[]>('/instruments', { token }),
      apiRequest<Provider[]>('/providers', { token }),
      apiRequest<Snapshot[]>('/data/snapshots', { token }),
    ]).then(([i, p, s]) => { if (live) { setInstruments(i); setProviders(p); setSnapshots(s); } })
      .catch(err => { if (live) setError(err instanceof Error ? err.message : 'Unable to load overview'); });
    return () => { live = false; };
  }, [token]);

  return <>
    <div className="page-heading"><div><p className="eyebrow">WORKSPACE OVERVIEW</p><h2>Research operations</h2><p className="muted">A live view of your financial research foundation.</p></div><span className="status-pill"><span /> Research mode</span></div>
    {error && <p className="error-banner">{error}. The API may be running before migrations or seed data are available.</p>}
    <section className="metric-grid">
      <Metric icon={<Activity />} label="Tracked instruments" value={String(instruments.length)} hint="Catalogue records" />
      <Metric icon={<Database />} label="Data snapshots" value={String(snapshots.length)} hint="Immutable ingestions" />
      <Metric icon={<FileText />} label="Enabled providers" value={String(providers.length)} hint="Configured sources" />
      <Metric icon={<ShieldCheck />} label="Execution mode" value="Paper only" hint="Live trading disabled" />
    </section>
    <section className="panel-grid">
      <div className="panel"><div className="panel-title"><h3>Data snapshots</h3><span className="tag">Latest 8</span></div>
        {snapshots.length ? <div className="table-scroll"><table><thead><tr><th>Instrument</th><th>Rows</th><th>Created</th><th>SHA-256</th></tr></thead><tbody>{snapshots.slice(0, 8).map(s => <tr key={s.id}><td>{s.instrument_symbol}</td><td>{s.row_count}</td><td>{new Date(s.created_at).toLocaleString()}</td><td className="mono">{s.sha256.slice(0, 12)}…</td></tr>)}</tbody></table></div> : <Empty text="No market-data snapshots have been ingested yet." />}
      </div>
      <div className="panel"><div className="panel-title"><h3>Data providers</h3><span className="tag">Enabled</span></div>
        {providers.length ? providers.map(p => <div className="list-row" key={p.key}><div className="provider-icon"><Database size={16} /></div><div><strong>{p.display_name}</strong><small>{p.provider_type.replace('_', ' ')}</small></div><span className="tiny-status">Active</span></div>) : <Empty text="Provider records appear after the initial database migration." />}
      </div>
    </section>
    <div className="notice"><ShieldCheck size={18} /><p><strong>Product boundary:</strong> FinSight is a research and paper-simulation portfolio application. It does not provide investment advice or execute real-money trades.</p></div>
  </>;
}

function Metric({ icon, label, value, hint }: { icon: ReactNode; label: string; value: string; hint: string }) {
  return <div className="metric-card"><div className="metric-icon">{icon}</div><p>{label}</p><strong>{value}</strong><small>{hint}</small></div>;
}
function Empty({ text }: { text: string }) { return <div className="empty-state">{text}</div>; }
