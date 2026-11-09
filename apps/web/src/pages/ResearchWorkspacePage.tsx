import { useState, type FormEvent } from 'react';
import { FileSearch, Search, UploadCloud } from 'lucide-react';
import { apiRequest } from '../lib/api';

type SECResult = { cik: string; company_name: string; filings_count: number; payload_sha256: string };
type Snapshot = { id: string; instrument_symbol: string; row_count: number; sha256: string; manifest: Record<string, unknown> };

export function ResearchWorkspacePage({ token }: { token: string }) {
  const [cik, setCik] = useState('');
  const [secResult, setSecResult] = useState<SECResult | null>(null);
  const [symbol, setSymbol] = useState('');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submitSEC(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSecResult(null);
    try { setSecResult(await apiRequest<SECResult>(`/data/ingestions/sec/${encodeURIComponent(cik)}`, { method: 'POST', token })); }
    catch (err) { setError(err instanceof Error ? err.message : 'SEC ingestion failed'); }
    finally { setBusy(false); }
  }

  async function submitCSV(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSnapshot(null);
    if (!csvFile) { setError('Choose a CSV file first.'); setBusy(false); return; }
    try {
      const form = new FormData();
      form.append('symbol', symbol.trim().toUpperCase());
      form.append('interval', '1d');
      form.append('adjustment_policy', 'provider_defined');
      form.append('file', csvFile);
      setSnapshot(await apiRequest<Snapshot>('/data/ingestions/market/csv', { method: 'POST', token, body: form }));
    } catch (err) { setError(err instanceof Error ? err.message : 'Market-data ingestion failed'); }
    finally { setBusy(false); }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">FINANCIAL DATA</p><h2>Research workspace</h2><p className="muted">Ingest permitted public filings and traceable historical market data.</p></div></div>
    {error && <p className="error-banner">{error}</p>}
    <div className="panel-grid research-grid">
      <section className="panel research-panel"><div className="section-icon"><FileSearch /></div><h3>SEC EDGAR company submissions</h3><p className="muted">Retrieve public submissions metadata using a 1–10 digit Central Index Key (CIK). The payload hash and ingestion time are retained.</p>
        <form className="inline-form" onSubmit={submitSEC}><label>Company CIK<input value={cik} onChange={e => setCik(e.target.value)} required inputMode="numeric" pattern="[0-9]{1,10}" placeholder="e.g. 0000320193" /></label><button className="primary-button" disabled={busy || !cik.trim()}><Search size={16} /> Retrieve</button></form>
        {secResult && <div className="result-card"><strong>{secResult.company_name}</strong><span>CIK {secResult.cik}</span><span>{secResult.filings_count} recent filing metadata entries</span><small className="mono">SHA-256: {secResult.payload_sha256}</small></div>}
      </section>
      <section className="panel research-panel"><div className="section-icon"><UploadCloud /></div><h3>Historical OHLCV CSV ingestion</h3><p className="muted">Upload a CSV containing <code>date, open, high, low, close, volume</code>. The API validates bars and stores an immutable, content-hashed Parquet snapshot.</p>
        <form className="upload-form" onSubmit={submitCSV}><label>Instrument symbol<input value={symbol} onChange={e => setSymbol(e.target.value)} required placeholder="MSFT" /></label><label>CSV file<input type="file" accept=".csv,text/csv" onChange={e => setCsvFile(e.target.files?.[0] ?? null)} required /></label><button className="primary-button" disabled={busy || !symbol.trim() || !csvFile}><UploadCloud size={16} /> {busy ? 'Ingesting…' : 'Create data snapshot'}</button></form>
        {snapshot && <div className="result-card"><strong>{snapshot.instrument_symbol} snapshot created</strong><span>{snapshot.row_count} market bars saved</span><small className="mono">SHA-256: {snapshot.sha256}</small></div>}
      </section>
    </div>
    <section className="panel"><h3>Research lifecycle</h3><div className="timeline"><span>Source ingestion</span><i /> <span>Evidence review</span><i /> <span>Hypothesis</span><i /> <span>Experiment</span><i /> <span>Risk approval</span></div><p className="muted small">Hypothesis approval, immutable feature-set versioning and baseline experiments are available in the Experiment Lab. Advanced research RAG and ML model training are planned for Phase 3.</p></section>
  </>;
}
