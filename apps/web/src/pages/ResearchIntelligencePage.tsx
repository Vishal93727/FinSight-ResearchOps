import { useEffect, useState, type FormEvent } from 'react';
import { BrainCircuit, FilePlus2, FileSearch, RefreshCw, ShieldCheck, UploadCloud } from 'lucide-react';
import { apiRequest } from '../lib/api';

type DocumentItem = {
  id: string; title: string; filename: string; media_type: string; content_sha256: string;
  character_count: number; chunk_count: number; status: string; created_at: string;
};
type Citation = {
  citation_id: string; document_id: string; document_title: string; filename: string;
  chunk_index: number; score: number; excerpt: string; text_sha256: string;
};
type ResearchReport = {
  id: string; query: string; answer: string; status: string; citations: Citation[];
  workflow_trace: { node: string; status: string }[]; evidence_verified: boolean;
  created_by: string; review_comment?: string | null; created_at: string; claim_checks?: { passed?: boolean; claim_count?: number; supported_count?: number };
};
type Snapshot = { id: string; instrument_symbol: string; status: string; row_count: number };
type JobItem = { id: string; task_name: string; status: string; error_message?: string | null; result?: Record<string, unknown> | null; created_at: string; completed_at?: string | null };
type FeatureSet = { id: string; feature_key: string; version: number; source_snapshot_id: string; definition: { features?: string[]; target?: string }; definition_sha256: string };
type ModelComparison = { comparison_count: number; ranking_metric: string; ranked_by_rmse: ModelEvaluation[]; best_directional_accuracy_evaluation_id?: string | null };
type SentimentResult = { label: string; score: number; method: string; pretrained_model: boolean; probabilities?: Record<string, number> };
type ModelEvaluation = {
  id: string; instrument_symbol: string; model_family: string; target_column: string;
  metrics: Record<string, string | number>; configuration_sha256: string; status: string;
};

export function ResearchIntelligencePage({ token, roles }: { token: string; roles: string[] }) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [featureSets, setFeatureSets] = useState<FeatureSet[]>([]);
  const [featureSetId, setFeatureSetId] = useState('');
  const [evaluations, setEvaluations] = useState<ModelEvaluation[]>([]);
  const [comparison, setComparison] = useState<ModelComparison | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [documentTitle, setDocumentTitle] = useState('');
  const [query, setQuery] = useState('');
  const [snapshotId, setSnapshotId] = useState('');
  const [modelFamily, setModelFamily] = useState<'ridge' | 'random_forest' | 'xgboost' | 'lightgbm' | 'lstm'>('ridge');
  const [sentimentText, setSentimentText] = useState('');
  const [sentimentProvider, setSentimentProvider] = useState<'lexicon' | 'finbert'>('lexicon');
  const [sentimentResult, setSentimentResult] = useState<SentimentResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const canUpload = roles.some(role => ['ADMIN', 'RESEARCH_ANALYST', 'QUANT_RESEARCHER'].includes(role));
  const canReview = roles.some(role => ['ADMIN', 'RISK_REVIEWER'].includes(role));
  const canRunModels = roles.some(role => ['ADMIN', 'QUANT_RESEARCHER'].includes(role));

  async function refresh() {
    setError('');
    try {
      const [docs, nextReports, nextSnapshots, nextEvaluations, nextFeatureSets, nextJobs] = await Promise.all([
        apiRequest<DocumentItem[]>('/documents', { token }),
        apiRequest<ResearchReport[]>('/research/reports', { token }),
        apiRequest<Snapshot[]>('/data/snapshots', { token }),
        apiRequest<ModelEvaluation[]>('/ml/evaluations', { token }),
        apiRequest<FeatureSet[]>('/features/versions', { token }),
        apiRequest<JobItem[]>('/jobs?limit=50', { token }),
      ]);
      setDocuments(docs); setReports(nextReports); setSnapshots(nextSnapshots); setEvaluations(nextEvaluations); setFeatureSets(nextFeatureSets); setJobs(nextJobs);
      const defaultSnapshot = nextSnapshots.some(item => item.id === snapshotId && item.status === 'READY')
        ? snapshotId : nextSnapshots.find(item => item.status === 'READY')?.id || '';
      const selectedFeatureSet = nextFeatureSets.find(item => item.id === featureSetId && item.source_snapshot_id === defaultSnapshot)?.id
        || nextFeatureSets.find(item => item.source_snapshot_id === defaultSnapshot)?.id || '';
      if (defaultSnapshot && selectedFeatureSet) {
        const nextComparison = await apiRequest<ModelComparison>(`/ml/evaluations/compare?snapshot_id=${defaultSnapshot}&feature_set_version_id=${selectedFeatureSet}`, { token });
        setComparison(nextComparison);
      } else setComparison(null);
      if (!snapshotId) setSnapshotId(defaultSnapshot);
      if (!featureSetId || !nextFeatureSets.some(item => item.id === featureSetId && item.source_snapshot_id === defaultSnapshot)) {
        setFeatureSetId(nextFeatureSets.find(item => item.source_snapshot_id === defaultSnapshot)?.id ?? '');
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load research intelligence workspace'); }
  }

  useEffect(() => { void refresh(); }, [token]);

  async function runAction(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); setNotice(message); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : 'The operation failed'); }
    finally { setBusy(false); }
  }

  async function uploadDocument(event: FormEvent) {
    event.preventDefault();
    if (!file) { setError('Choose a TXT, Markdown, CSV, JSON, HTML or PDF file first.'); return; }
    const queued = new FormData();
    queued.append('file', file);
    if (documentTitle.trim()) queued.append('title', documentTitle.trim());
    queued.append('idempotency_key', crypto.randomUUID());
    await runAction(() => apiRequest<JobItem>('/documents/upload/jobs', {
      method: 'POST', token, body: queued,
    }), 'Document ingestion queued. Refresh the job list to monitor parsing, chunking and indexing.');
    setFile(null); setDocumentTitle('');
    const input = document.getElementById('research-document-file') as HTMLInputElement | null;
    if (input) input.value = '';
  }

  async function retryJob(jobId: string) {
    await runAction(() => apiRequest<JobItem>(`/jobs/${jobId}/retry`, { method: 'POST', token }),
      'Job was re-submitted to the worker queue.');
  }

  async function askQuestion(event: FormEvent) {
    event.preventDefault();
    await runAction(() => apiRequest<JobItem>('/research/ask/jobs', {
      method: 'POST', token, body: JSON.stringify({ query, top_k: 6, lexical_weight: 0.45, diversity_weight: 0.15, idempotency_key: crypto.randomUUID() }),
    }), 'Research question queued. Refresh the job list to monitor retrieval, synthesis and citation checks.');
    setQuery('');
  }

  async function decideReport(reportId: string, decision: 'APPROVE' | 'REJECT') {
    await runAction(() => apiRequest<ResearchReport>(`/research/reports/${reportId}/decision`, {
      method: 'POST', token, body: JSON.stringify({ decision, comment: 'Reviewed in FinSight Research Intelligence.' }),
    }), `Research report ${decision.toLowerCase()}d and audit logged.`);
  }

  async function resumeReport(reportId: string) {
    await runAction(() => apiRequest<ResearchReport>(`/research/reports/${reportId}/resume`, {
      method: 'POST', token,
    }), 'Research workflow resumed from its last committed evidence checkpoint.');
  }

  async function scoreSentiment(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice(''); setSentimentResult(null);
    try {
      const result = await apiRequest<SentimentResult>('/ml/sentiment', { method: 'POST', token, body: JSON.stringify({ text: sentimentText, provider: sentimentProvider }) });
      setSentimentResult(result);
    } catch (err) { setError(err instanceof Error ? err.message : 'Sentiment analysis failed'); }
    finally { setBusy(false); }
  }

  async function runModelEvaluation(event: FormEvent) {
    event.preventDefault();
    await runAction(() => apiRequest<JobItem>('/ml/evaluations/jobs', {
      method: 'POST', token, body: JSON.stringify({
        dataset_snapshot_id: snapshotId, feature_set_version_id: featureSetId,
        date_column: 'date', model_family: modelFamily,
        random_seed: 42, test_fraction: 0.2, sequence_length: 12, epochs: 35, idempotency_key: crypto.randomUUID(),
      }),
    }), 'Supervised model evaluation queued. Refresh the job list to monitor worker execution.');
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">PHASE 03 · FINANCIAL RESEARCH AI</p><h2>Research intelligence</h2><p className="muted">Source-grounded document research, reviewer checkpoints and reproducible ML evaluation.</p></div><button className="secondary-button" onClick={() => void refresh()} disabled={busy}><RefreshCw size={14} /> Refresh</button></div>
    {error && <div className="error-banner">{error}</div>}{notice && <div className="success-banner">{notice}</div>}
    <section className="panel">
      <div className="panel-title"><h3>Research, document and ML worker jobs</h3><span className="tag">Durable queue status</span></div>
      <div className="document-list">{jobs.length === 0 ? <div className="empty-state">No background jobs submitted yet.</div> : jobs.slice(0, 12).map(job => <div className="list-row" key={job.id}><div className="provider-icon"><RefreshCw size={15} /></div><div><strong>{job.task_name}</strong><small>{job.id.slice(0, 12)}… · {new Date(job.created_at).toLocaleString()}{job.error_message ? ` · ${job.error_message}` : ''}{job.result?.report_id ? ` · Report ${String(job.result.report_id).slice(0, 8)}…` : ''}{job.result?.document_id ? ` · Document ${String(job.result.document_id).slice(0, 8)}…` : ''}{job.result?.model_evaluation_id ? ` · Evaluation ${String(job.result.model_evaluation_id).slice(0, 8)}…` : ''}</small></div><span className={`run-status ${job.status.toLowerCase()}`}>{job.status.replaceAll('_', ' ')}</span>{job.status === 'QUEUE_FAILED' && <button className="secondary-button" disabled={busy} onClick={() => void retryJob(job.id)}>Retry</button>}</div>)}</div>
    </section>
    <div className="phase3-grid">
      <section className="panel">
        <div className="panel-title"><h3><UploadCloud size={16} /> Document library</h3><span className="tag">{documents.length} sources</span></div>
        <p className="muted small">Upload filings and research material. Each source is content-hashed and split into provenance-linked chunks.</p>
        <form className="upload-form" onSubmit={uploadDocument}>
          <label>Document title<input value={documentTitle} onChange={event => setDocumentTitle(event.target.value)} placeholder="Annual report — FY2025" /></label>
          <label>Source file<input id="research-document-file" type="file" accept=".txt,.md,.markdown,.csv,.json,.html,.htm,.pdf" onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
          <button className="primary-button" type="submit" disabled={busy || !canUpload || !file}><FilePlus2 size={15} /> Ingest and index</button>
        </form>
        <div className="document-list">{documents.length === 0 ? <div className="empty-state">No research documents indexed yet.</div> : documents.slice(0, 8).map(item => <div className="list-row" key={item.id}><div className="provider-icon"><FileSearch size={16} /></div><div><strong>{item.title}</strong><small>{item.filename} · {item.chunk_count} chunks · SHA {item.content_sha256.slice(0, 12)}…</small></div><span className="tiny-status">{item.status}</span></div>)}</div>
      </section>
      <section className="panel">
        <div className="panel-title"><h3><BrainCircuit size={16} /> Evidence-grounded research</h3><span className="tag">Human review required</span></div>
        <p className="muted small">Hybrid lexical and vector retrieval. The default synthesizer is extractive and cannot approve its own output.</p>
        <form className="upload-form" onSubmit={askQuestion}>
          <label>Research question<input value={query} onChange={event => setQuery(event.target.value)} placeholder="What factors explain the company's margin expansion?" minLength={8} maxLength={2000} /></label>
          <button className="primary-button" type="submit" disabled={busy || !canUpload || query.trim().length < 8}><FileSearch size={15} /> Queue research draft</button>
        </form>
        <div className="report-list">{reports.length === 0 ? <div className="empty-state">No research reports created yet.</div> : reports.slice(0, 6).map(report => <article className="result-card" key={report.id}>
          <div className="report-head"><strong>{report.query}</strong><span className={`run-status ${report.status.toLowerCase()}`}>{report.status.replaceAll('_', ' ')}</span></div>
          <p>{report.answer}</p>
          <small>Claim screening: {report.claim_checks?.supported_count ?? 0}/{report.claim_checks?.claim_count ?? 0} supported · deterministic screen, human review required</small><div className="role-list">{report.citations.map(citation => <span className="tag" key={citation.citation_id}>{citation.citation_id} · {citation.document_title}</span>)}</div>
          {report.status === 'AWAITING_REVIEW' && canReview && <div className="review-actions"><button className="secondary-button" disabled={busy} onClick={() => void decideReport(report.id, 'APPROVE')}><ShieldCheck size={13} /> Approve</button><button className="secondary-button" disabled={busy} onClick={() => void decideReport(report.id, 'REJECT')}>Reject</button></div>}
          {report.status === 'FAILED' && report.created_by && canUpload && <div className="review-actions"><button className="secondary-button" disabled={busy} onClick={() => void resumeReport(report.id)}><RefreshCw size={13} /> Resume from checkpoint</button></div>}
          {report.review_comment && <small>Review note: {report.review_comment}</small>}
        </article>)}</div>
      </section>
    </div>
    <section className="panel">
      <div className="panel-title"><h3><BrainCircuit size={16} /> Financial sentiment</h3><span className="tag">Lexicon baseline or optional FinBERT</span></div>
      <form className="catalogue-form phase3-model-form" onSubmit={scoreSentiment}>
        <label>Financial text<input value={sentimentText} onChange={event => setSentimentText(event.target.value)} placeholder="Revenue beat estimates, but management cut its outlook…" maxLength={20000} /></label>
        <label>Sentiment provider<select value={sentimentProvider} onChange={event => setSentimentProvider(event.target.value as typeof sentimentProvider)}><option value="lexicon">Transparent lexicon</option><option value="finbert">FinBERT (optional model)</option></select></label>
        <button className="primary-button" type="submit" disabled={busy || !canUpload || !sentimentText.trim()}>Score sentiment</button>
      </form>
      {sentimentResult && <div className="result-card"><div className="report-head"><strong>{sentimentResult.label}</strong><span className="tag">{sentimentResult.method}</span></div><p>Score: {sentimentResult.score.toFixed(4)} · {sentimentResult.pretrained_model ? 'pretrained model' : 'transparent baseline'}</p>{sentimentResult.probabilities && <div className="role-list">{Object.entries(sentimentResult.probabilities).map(([label, score]) => <span className="tag" key={label}>{label}: {(score * 100).toFixed(1)}%</span>)}</div>}</div>}
    </section>
    <section className="panel">
      <div className="panel-title"><h3><BrainCircuit size={16} /> Supervised ML evaluation</h3><span className="tag">Chronological holdout · no shuffle</span></div>
      <p className="muted small">Train and evaluate on a READY Parquet snapshot using an immutable feature-set version. Features are materialized by the controlled OHLCV pipeline; the next-session target is generated separately and cannot enter the feature list.</p>
      <form className="catalogue-form phase3-model-form" onSubmit={runModelEvaluation}>
        <label>Dataset snapshot<select value={snapshotId} onChange={event => { const nextId = event.target.value; setSnapshotId(nextId); setFeatureSetId(featureSets.find(item => item.source_snapshot_id === nextId)?.id ?? ''); }}><option value="">Select READY snapshot</option>{snapshots.filter(item => item.status === 'READY').map(item => <option key={item.id} value={item.id}>{item.instrument_symbol} · {item.row_count} rows · {item.id.slice(0, 8)}</option>)}</select></label>
        <label>Feature-set version<select value={featureSetId} onChange={event => setFeatureSetId(event.target.value)}><option value="">Select feature set</option>{featureSets.filter(item => item.source_snapshot_id === snapshotId).map(item => <option key={item.id} value={item.id}>{item.feature_key} v{item.version}</option>)}</select></label>
        <label>Model family<select value={modelFamily} onChange={event => setModelFamily(event.target.value as typeof modelFamily)}><option value="ridge">Ridge baseline</option><option value="random_forest">Random Forest</option><option value="xgboost">XGBoost</option><option value="lightgbm">LightGBM</option><option value="lstm">PyTorch LSTM</option></select></label>
        <button className="primary-button" type="submit" disabled={busy || !canRunModels || !snapshotId || !featureSetId || featureSets.find(item => item.id === featureSetId)?.source_snapshot_id !== snapshotId}>Run evaluation</button>
      </form>
      <div className="table-scroll"><table><thead><tr><th>Instrument</th><th>Model</th><th>Target</th><th>MAE</th><th>RMSE</th><th>Directional accuracy</th><th>Status</th></tr></thead><tbody>
        {evaluations.map(item => <tr key={item.id}><td>{item.instrument_symbol}</td><td>{item.model_family}</td><td>{item.target_column}</td><td>{Number(item.metrics.mae).toFixed(5)}</td><td>{Number(item.metrics.rmse).toFixed(5)}</td><td>{(Number(item.metrics.directional_accuracy) * 100).toFixed(1)}%</td><td>{item.status}</td></tr>)}
      </tbody></table>{evaluations.length === 0 && <div className="empty-state">No supervised ML evaluations yet.</div>}</div>
    </section>
    <section className="panel">
      <div className="panel-title"><h3>Model family comparison</h3><span className="tag">Same snapshot and feature lineage</span></div>
      <p className="muted small">Evaluations are ranked by test RMSE (lower is better). Directional accuracy is shown as a separate diagnostic and should not be interpreted as tradable profitability.</p>
      <div className="table-scroll"><table><thead><tr><th>Rank</th><th>Model family</th><th>RMSE</th><th>MAE</th><th>Directional accuracy</th><th>Configuration fingerprint</th></tr></thead><tbody>
        {(comparison?.ranked_by_rmse ?? []).map((item, index) => <tr key={item.id}><td>{index + 1}</td><td>{item.model_family}{item.id === comparison?.best_directional_accuracy_evaluation_id ? ' · Best direction' : ''}</td><td>{Number(item.metrics.rmse).toFixed(5)}</td><td>{Number(item.metrics.mae).toFixed(5)}</td><td>{(Number(item.metrics.directional_accuracy) * 100).toFixed(1)}%</td><td><code>{item.configuration_sha256.slice(0, 12)}…</code></td></tr>)}
      </tbody></table>{!comparison?.comparison_count && <div className="empty-state">No evaluations exist for the selected data and feature lineage yet.</div>}</div>
    </section>
  </>;
}
