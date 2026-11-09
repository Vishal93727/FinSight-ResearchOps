import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Activity, CheckCircle2, Clock3, FlaskConical, Play, RefreshCw, ShieldAlert } from 'lucide-react';
import { apiRequest } from '../lib/api';

type Snapshot = {
  id: string; instrument_symbol: string; start_date: string; end_date: string;
  status: string; row_count: number; sha256: string;
};
type Hypothesis = { id: string; owner_user_id: string; title: string; symbol: string; thesis: string; status: string; version: number };
type FeatureSet = { id: string; feature_key: string; version: number; source_snapshot_id: string; definition_sha256: string };
type Experiment = {
  id: string; name: string; hypothesis_id: string; instrument_symbol: string;
  dataset_snapshot_id: string; feature_set_version_id: string; benchmark_snapshot_id?: string | null;
  configuration: Record<string, unknown>; configuration_sha256: string; status: string;
};
type ExperimentRun = {
  id: string; experiment_id: string; run_number: number; status: string; random_seed: number;
  metrics: Record<string, unknown>; artifacts: Record<string, string>; error_message?: string | null;
  created_at: string; completed_at?: string | null;
};
type RunComparison = {
  run_id: string; run_number: number; status: string; total_return?: number | null;
  annualized_return?: number | null; sharpe_ratio?: number | null; max_drawdown?: number | null;
  annualized_volatility?: number | null; benchmark_total_return?: number | null;
  information_ratio?: number | null; risk_decision?: string | null;
};
type WindowDates = {
  trainStart: string; trainEnd: string; validationStart: string;
  validationEnd: string; testStart: string; testEnd: string;
};

function shiftDate(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function defaultWindows(snapshot?: Snapshot): WindowDates {
  if (!snapshot) return {
    trainStart: '', trainEnd: '', validationStart: '', validationEnd: '', testStart: '', testEnd: '',
  };
  const span = Math.max(0, Math.floor((Date.parse(`${snapshot.end_date}T00:00:00Z`) - Date.parse(`${snapshot.start_date}T00:00:00Z`)) / 86_400_000));
  const trainOffset = Math.floor(span * 0.58);
  const validationEndOffset = Math.floor(span * 0.78);
  const trainEnd = shiftDate(snapshot.start_date, trainOffset);
  const validationStart = shiftDate(trainEnd, 3);
  const validationEnd = shiftDate(snapshot.start_date, validationEndOffset);
  const testStart = shiftDate(validationEnd, 3);
  return {
    trainStart: snapshot.start_date, trainEnd, validationStart,
    validationEnd, testStart, testEnd: snapshot.end_date,
  };
}

export function ExperimentLabPage({ token, userId, roles }: { token: string; userId: string; roles: string[] }) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [features, setFeatures] = useState<FeatureSet[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [comparison, setComparison] = useState<RunComparison[]>([]);
  const [benchmarkSnapshotId, setBenchmarkSnapshotId] = useState('');
  const [selectedSnapshotId, setSelectedSnapshotId] = useState('');
  const [selectedHypothesisId, setSelectedHypothesisId] = useState('');
  const [selectedFeatureId, setSelectedFeatureId] = useState('');
  const [selectedExperimentId, setSelectedExperimentId] = useState('');
  const [title, setTitle] = useState('');
  const [symbol, setSymbol] = useState('');
  const [thesis, setThesis] = useState('');
  const [featureKey, setFeatureKey] = useState('ohlcv_momentum');
  const [experimentName, setExperimentName] = useState('');
  const [baseline, setBaseline] = useState<'buy_and_hold' | 'moving_average_crossover' | 'rsi_mean_reversion'>('buy_and_hold');
  const [evaluationMode, setEvaluationMode] = useState<'holdout' | 'walk_forward'>('holdout');
  const [windows, setWindows] = useState<WindowDates>(defaultWindows());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const selectedSnapshot = useMemo(
    () => snapshots.find(item => item.id === selectedSnapshotId), [snapshots, selectedSnapshotId],
  );
  const selectedExperiment = useMemo(
    () => experiments.find(item => item.id === selectedExperimentId), [experiments, selectedExperimentId],
  );
  const canReview = roles.includes('ADMIN') || roles.includes('RISK_REVIEWER');
  const canCreate = roles.includes('ADMIN') || roles.includes('QUANT_RESEARCHER');
  const canResearch = canCreate || roles.includes('RESEARCH_ANALYST');

  async function refreshWorkspace() {
    setError('');
    try {
      const [nextSnapshots, nextHypotheses, nextFeatures, nextExperiments] = await Promise.all([
        apiRequest<Snapshot[]>('/data/snapshots', { token }),
        apiRequest<Hypothesis[]>('/research/hypotheses', { token }),
        apiRequest<FeatureSet[]>('/features/versions', { token }),
        apiRequest<Experiment[]>('/experiments', { token }),
      ]);
      setSnapshots(nextSnapshots);
      setHypotheses(nextHypotheses);
      setFeatures(nextFeatures);
      setExperiments(nextExperiments);
      if (!selectedSnapshotId && nextSnapshots.length) {
        const readySnapshot = nextSnapshots.find(item => item.status === 'READY');
        if (readySnapshot) setSelectedSnapshotId(readySnapshot.id);
      }
      if (!selectedExperimentId && nextExperiments.length) {
        setSelectedExperimentId(nextExperiments[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load the experiment workspace');
    }
  }

  useEffect(() => { void refreshWorkspace(); }, [token]);
  useEffect(() => {
    if (selectedSnapshot) setWindows(defaultWindows(selectedSnapshot));
  }, [selectedSnapshotId, selectedSnapshot?.start_date, selectedSnapshot?.end_date]);
  useEffect(() => {
    if (!selectedExperimentId) { setRuns([]); setComparison([]); return; }
    let live = true;
    apiRequest<ExperimentRun[]>(`/experiments/${selectedExperimentId}/runs`, { token })
      .then(result => { if (live) setRuns(result); })
      .catch(err => { if (live) setError(err instanceof Error ? err.message : 'Unable to load runs'); });
    apiRequest<RunComparison[]>(`/experiments/${selectedExperimentId}/runs/comparison`, { token })
      .then(result => { if (live) setComparison(result); })
      .catch(err => { if (live) setError(err instanceof Error ? err.message : 'Unable to load comparison'); });
    return () => { live = false; };
  }, [token, selectedExperimentId]);

  async function act<T>(operation: () => Promise<T>, successMessage: string, after?: (value: T) => void) {
    setBusy(true); setError(''); setNotice('');
    try {
      const value = await operation();
      after?.(value);
      setNotice(successMessage);
      await refreshWorkspace();
      return value;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The operation failed');
      return undefined;
    } finally { setBusy(false); }
  }

  async function createHypothesis(event: FormEvent) {
    event.preventDefault();
    await act(() => apiRequest<Hypothesis>('/research/hypotheses', {
      method: 'POST', token, body: JSON.stringify({ title, symbol: symbol.toUpperCase(), thesis }),
    }), 'Draft hypothesis created. Submit it for independent review when its evidence is ready.');
    setTitle(''); setThesis('');
  }

  async function createFeatureVersion() {
    if (!selectedSnapshot) return;
    await act(() => apiRequest<FeatureSet>('/features/versions', {
      method: 'POST', token, body: JSON.stringify({
        feature_key: featureKey, description: 'Close-derived price momentum, moving-average and volatility features.',
        source_snapshot_id: selectedSnapshot.id,
        definition: {
          inputs: ['open', 'high', 'low', 'close', 'volume'],
          features: ['return_1d', 'momentum_5d', 'sma_ratio_5d', 'sma_ratio_20d', 'volatility_20d', 'volume_change_1d'],
          target: 'next_day_return', target_shift: -1,
        },
      }),
    }), `Feature set version created from ${selectedSnapshot.instrument_symbol} snapshot.`);
  }

  async function createExperiment(event: FormEvent) {
    event.preventDefault();
    const feature = features.find(item => item.id === selectedFeatureId);
    const hypothesis = hypotheses.find(item => item.id === selectedHypothesisId);
    if (!selectedSnapshot || !feature || !hypothesis) {
      setError('Select an approved hypothesis, a source snapshot and a feature-set version.'); return;
    }
    if (feature.source_snapshot_id !== selectedSnapshot.id || hypothesis.status !== 'APPROVED' || hypothesis.symbol !== selectedSnapshot.instrument_symbol) {
      setError('The hypothesis, feature set and selected snapshot must refer to the same instrument and dataset lineage.'); return;
    }
    await act(() => apiRequest<Experiment>('/experiments', {
      method: 'POST', token, body: JSON.stringify({
        name: experimentName, hypothesis_id: hypothesis.id, dataset_snapshot_id: selectedSnapshot.id,
        feature_set_version_id: feature.id,
        benchmark_snapshot_id: benchmarkSnapshotId || null,
        configuration: {
          model_family: 'baseline', baseline, target: 'next_day_return',
          evaluation_mode: evaluationMode, walk_forward_test_days: 63, walk_forward_step_days: 63,
          prediction_horizon_days: 1, purge_gap_days: 1,
          train_start: windows.trainStart, train_end: windows.trainEnd,
          validation_start: windows.validationStart, validation_end: windows.validationEnd,
          test_start: windows.testStart, test_end: windows.testEnd,
          random_seed: 42, commission_bps: 5, slippage_bps: 5, benchmark_symbol: 'SPY',
        },
      }),
    }), 'Experiment specification saved with a reproducible configuration hash.');
    setExperimentName('');
  }

  async function submitRun() {
    if (!selectedExperiment) return;
    await act(() => apiRequest<ExperimentRun>(`/experiments/${selectedExperiment.id}/runs`, {
      method: 'POST', token, headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({}),
    }), 'Experiment run submitted to the background queue. Refresh run status after the worker processes it.');
    const nextRuns = await apiRequest<ExperimentRun[]>(`/experiments/${selectedExperiment.id}/runs`, { token });
    setRuns(nextRuns);
  }

  async function changeHypothesisStatus(hypothesis: Hypothesis, action: 'submit-review' | 'decision') {
    const path = `/research/hypotheses/${hypothesis.id}/${action}`;
    const body = action === 'decision' ? { decision: 'APPROVE', note: 'Approved for a controlled offline quantitative experiment.' } : undefined;
    await act(() => apiRequest<Hypothesis>(path, { method: 'POST', token, ...(body ? { body: JSON.stringify(body) } : {}) }),
      action === 'decision' ? 'Hypothesis approved for controlled experimentation.' : 'Hypothesis submitted for independent review.');
  }

  async function refreshRuns() {
    if (!selectedExperimentId) return;
    try {
      const [nextRuns, nextComparison] = await Promise.all([
        apiRequest<ExperimentRun[]>(`/experiments/${selectedExperimentId}/runs`, { token }),
        apiRequest<RunComparison[]>(`/experiments/${selectedExperimentId}/runs/comparison`, { token }),
      ]);
      setRuns(nextRuns); setComparison(nextComparison);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to refresh run status'); }
  }

  return <>
    <div className="page-heading">
      <div><p className="eyebrow">PHASE 2 · QUANTITATIVE RESEARCH</p><h2>Experiment lab</h2>
        <p className="muted">Turn approved research questions into versioned, reproducible offline experiments.</p></div>
      <button className="secondary-button" onClick={() => void refreshWorkspace()} disabled={busy}><RefreshCw size={14} /> Refresh</button>
    </div>
    {error && <p className="error-banner">{error}</p>}
    {notice && <p className="success-banner">{notice}</p>}

    <section className="panel-grid experiment-top-grid">
      <div className="panel">
        <div className="section-icon"><FlaskConical /></div><h3>1. Research hypothesis</h3>
        <p className="muted small">Create a falsifiable thesis. A separate risk reviewer or administrator must approve it before experiment creation.</p>
        <form className="upload-form" onSubmit={createHypothesis}>
          <label>Hypothesis title<input value={title} onChange={e => setTitle(e.target.value)} minLength={3} maxLength={180} required placeholder="Short-horizon momentum persistence" /></label>
          <label>Instrument symbol<input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} maxLength={32} required placeholder="MSFT" /></label>
          <label>Research thesis<textarea value={thesis} onChange={e => setThesis(e.target.value)} minLength={20} maxLength={5000} required rows={3} placeholder="A positive five-session momentum signal may predict next-session returns..." /></label>
          <button className="primary-button" disabled={busy || !canResearch}>Create draft hypothesis</button>
        </form>
        <div className="stack-list">
          {hypotheses.slice(0, 8).map(item => <div className="stack-row" key={item.id}>
            <div className="stack-main"><strong>{item.title}</strong><small>{item.symbol} · v{item.version} · {item.status.replaceAll('_', ' ')}</small></div>
            <div className="stack-actions">
              {item.status === 'DRAFT' && (item.owner_user_id === userId || roles.includes('ADMIN')) && <button className="secondary-button" disabled={busy} onClick={() => void changeHypothesisStatus(item, 'submit-review')}>Submit review</button>}
              {item.status === 'UNDER_REVIEW' && canReview && <button className="secondary-button" disabled={busy} onClick={() => void changeHypothesisStatus(item, 'decision')}>Approve</button>}
            </div>
          </div>)}
          {!hypotheses.length && <div className="empty-state">No research hypotheses yet.</div>}
        </div>
        {!canReview && <p className="inline-note"><ShieldAlert size={14} /> Approval is restricted to the ADMIN or RISK_REVIEWER role.</p>}
      </div>

      <div className="panel">
        <div className="section-icon"><Activity /></div><h3>2. Version a feature set</h3>
        <p className="muted small">Each definition is immutable and pinned to the source snapshot. The target is stored separately from input features.</p>
        <div className="upload-form">
          <label>Source data snapshot<select value={selectedSnapshotId} onChange={e => setSelectedSnapshotId(e.target.value)}>
            <option value="">Select a READY snapshot</option>
            {snapshots.filter(item => item.status === 'READY').map(item => <option key={item.id} value={item.id}>{item.instrument_symbol} · {item.start_date} to {item.end_date} · {item.row_count} rows</option>)}
          </select></label>
          <label>Feature key<input value={featureKey} onChange={e => setFeatureKey(e.target.value)} pattern="[a-z][a-z0-9_]*" required /></label>
          <button className="primary-button" onClick={() => void createFeatureVersion()} disabled={busy || !canCreate || !selectedSnapshot}>Create feature version</button>
        </div>
        <div className="stack-list">
          {features.slice(0, 8).map(item => <div className="stack-row" key={item.id}><div className="stack-main"><strong>{item.feature_key} · v{item.version}</strong><small className="mono">{item.definition_sha256.slice(0, 16)}…</small></div><span className="tag">Immutable</span></div>)}
          {!features.length && <div className="empty-state">Feature versions appear here after creation.</div>}
        </div>
      </div>
    </section>

    <section className="panel">
      <div className="section-icon"><FlaskConical /></div><h3>3. Create a reproducible experiment</h3>
      <p className="muted small">Choose an approved hypothesis, the matching dataset and a feature-set version derived from that exact snapshot. The API validates chronology and purge gaps.</p>
      <form className="experiment-form" onSubmit={createExperiment}>
        <label>Experiment name<input value={experimentName} onChange={e => setExperimentName(e.target.value)} minLength={3} maxLength={180} required placeholder="MSFT momentum baseline · holdout 2025" /></label>
        <label>Approved hypothesis<select value={selectedHypothesisId} onChange={e => setSelectedHypothesisId(e.target.value)} required><option value="">Select hypothesis</option>{hypotheses.filter(item => item.status === 'APPROVED').map(item => <option key={item.id} value={item.id}>{item.symbol} · {item.title}</option>)}</select></label>
        <label>Dataset snapshot<select value={selectedSnapshotId} onChange={e => setSelectedSnapshotId(e.target.value)} required><option value="">Select snapshot</option>{snapshots.filter(item => item.status === 'READY').map(item => <option key={item.id} value={item.id}>{item.instrument_symbol} · {item.start_date} to {item.end_date}</option>)}</select></label>
        <label>Feature-set version<select value={selectedFeatureId} onChange={e => setSelectedFeatureId(e.target.value)} required><option value="">Select feature version</option>{features.filter(item => item.source_snapshot_id === selectedSnapshotId).map(item => <option key={item.id} value={item.id}>{item.feature_key} · v{item.version}</option>)}</select></label>
        <label>Baseline strategy<select value={baseline} onChange={e => setBaseline(e.target.value as typeof baseline)}><option value="buy_and_hold">Buy and hold</option><option value="moving_average_crossover">Moving average crossover</option><option value="rsi_mean_reversion">RSI mean reversion</option></select></label>
        <label>Evaluation method<select value={evaluationMode} onChange={e => setEvaluationMode(e.target.value as typeof evaluationMode)}><option value="holdout">Single holdout</option><option value="walk_forward">Rolling walk-forward</option></select></label>
        <label>Benchmark snapshot (optional)<select value={benchmarkSnapshotId} onChange={e => setBenchmarkSnapshotId(e.target.value)}><option value="">Not pinned — benchmark comparison unavailable</option>{snapshots.filter(item => item.status === 'READY' && item.instrument_symbol === 'SPY').map(item => <option key={item.id} value={item.id}>SPY · {item.start_date} to {item.end_date} · {item.row_count} rows</option>)}</select></label>
        <label>Train start<input type="date" value={windows.trainStart} onChange={e => setWindows({ ...windows, trainStart: e.target.value })} required /></label>
        <label>Train end<input type="date" value={windows.trainEnd} onChange={e => setWindows({ ...windows, trainEnd: e.target.value })} required /></label>
        <label>Validation start<input type="date" value={windows.validationStart} onChange={e => setWindows({ ...windows, validationStart: e.target.value })} required /></label>
        <label>Validation end<input type="date" value={windows.validationEnd} onChange={e => setWindows({ ...windows, validationEnd: e.target.value })} required /></label>
        <label>Test start<input type="date" value={windows.testStart} onChange={e => setWindows({ ...windows, testStart: e.target.value })} required /></label>
        <label>Test end<input type="date" value={windows.testEnd} onChange={e => setWindows({ ...windows, testEnd: e.target.value })} required /></label>
        <button className="primary-button" disabled={busy || !canCreate || !selectedSnapshot || !selectedFeatureId || !selectedHypothesisId}>Save experiment specification</button>
      </form>
      {!selectedSnapshot && <p className="inline-note">Ingest a historical CSV snapshot first. Long enough date coverage is required for train, validation and test windows.</p>}
    </section>

    <section className="panel">
      <div className="panel-title"><div><h3>4. Execute and inspect runs</h3><p className="muted small">Runs are queued for the Celery worker. Duplicate requests are guarded by an idempotency key.</p></div><button className="secondary-button" onClick={() => void refreshRuns()} disabled={!selectedExperimentId}><RefreshCw size={14} /> Refresh runs</button></div>
      <div className="run-toolbar">
        <label>Experiment<select value={selectedExperimentId} onChange={e => setSelectedExperimentId(e.target.value)}><option value="">Select an experiment</option>{experiments.map(item => <option key={item.id} value={item.id}>{item.instrument_symbol} · {item.name}</option>)}</select></label>
        <button className="primary-button" onClick={() => void submitRun()} disabled={busy || !selectedExperiment || !canCreate}><Play size={14} /> Queue baseline run</button>
      </div>
      {selectedExperiment && <p className="inline-note">Config SHA-256: <span className="mono">{selectedExperiment.configuration_sha256}</span></p>}
      <div className="table-scroll"><table><thead><tr><th>Run</th><th>Status</th><th>Seed</th><th>Total return</th><th>Sharpe</th><th>Max drawdown</th><th>Risk decision</th><th>Created</th></tr></thead><tbody>
        {runs.map(run => {
          const totalReturn = run.metrics.total_return;
          const sharpe = run.metrics.sharpe_ratio;
          const drawdown = run.metrics.max_drawdown;
          const risk = run.metrics.risk_decision;
          return <tr key={run.id}><td>#{run.run_number}</td><td><span className={`run-status ${run.status.toLowerCase()}`}>{run.status}</span></td><td>{run.random_seed}</td>
            <td>{typeof totalReturn === 'number' ? `${(totalReturn * 100).toFixed(2)}%` : '—'}</td>
            <td>{typeof sharpe === 'number' ? sharpe.toFixed(2) : '—'}</td>
            <td>{typeof drawdown === 'number' ? `${(drawdown * 100).toFixed(2)}%` : '—'}</td>
            <td>{typeof risk === 'string' ? risk : 'Pending'}</td><td>{new Date(run.created_at).toLocaleString()}</td></tr>;
        })}
      </tbody></table></div>
      {comparison.length > 0 && <><div className="section-divider" /><h4>Run comparison</h4><div className="table-scroll"><table><thead><tr><th>Run</th><th>Return</th><th>Benchmark</th><th>Sharpe</th><th>Information ratio</th><th>Risk</th></tr></thead><tbody>
        {comparison.map(item => <tr key={item.run_id}><td>#{item.run_number}</td><td>{typeof item.total_return === 'number' ? `${(item.total_return * 100).toFixed(2)}%` : '—'}</td><td>{typeof item.benchmark_total_return === 'number' ? `${(item.benchmark_total_return * 100).toFixed(2)}%` : 'Not pinned'}</td><td>{typeof item.sharpe_ratio === 'number' ? item.sharpe_ratio.toFixed(2) : '—'}</td><td>{typeof item.information_ratio === 'number' ? item.information_ratio.toFixed(2) : '—'}</td><td>{item.risk_decision ?? 'Pending'}</td></tr>)}
      </tbody></table></div></>}
      {!runs.length && <div className="empty-state"><Clock3 size={18} /><p>No runs for this experiment yet. Queue a run to begin.</p></div>}
    </section>
    <div className="notice"><ShieldAlert size={18} /><p><strong>Research-only execution:</strong> this page queues deterministic baseline backtests. It does not submit orders to a broker, provide investment advice or execute live-money trades. Results are historical simulations, not guarantees of future performance.</p></div>
  </>;
}
