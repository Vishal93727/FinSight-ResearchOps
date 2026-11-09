import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, BrainCircuit, Play, RefreshCw, RotateCcw } from 'lucide-react';
import { apiRequest } from '../lib/api';

type Snapshot = { id: string; instrument_symbol: string; status: string; storage_format: string; start_date: string; end_date: string };
type FeatureSet = { id: string; feature_key: string; version: number; source_snapshot_id: string };
type Job = { id: string; task_name: string; status: string; result: Record<string, unknown> | null; error_message: string | null; created_at?: string };
type RLEvaluation = { id: string; algorithm: string; status: string; metrics: Record<string, unknown>; configuration: Record<string, unknown>; configuration_sha256: string; artifact_uri: string | null; artifact_sha256?: string | null; out_of_sample: boolean; dataset_snapshot_id: string; feature_set_version_id: string; created_at?: string };

function metric(value: unknown, digits = 3): string {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '—';
}

export function RLEvaluationPanel({ token, roles }: { token: string; roles: string[] }) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [features, setFeatures] = useState<FeatureSet[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [evaluations, setEvaluations] = useState<RLEvaluation[]>([]);
  const [snapshotId, setSnapshotId] = useState('');
  const [featureId, setFeatureId] = useState('');
  const [algorithm, setAlgorithm] = useState<'PPO' | 'SAC'>('PPO');
  const [timesteps, setTimesteps] = useState('20000');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [comparison, setComparison] = useState<RLEvaluation[]>([]);
  const canTrain = roles.includes('ADMIN') || roles.includes('QUANT_RESEARCHER');
  const availableSnapshots = useMemo(
    () => snapshots.filter(item => item.status === 'READY' && item.storage_format.toLowerCase() === 'parquet'),
    [snapshots],
  );
  const selectedFeatures = useMemo(
    () => features.filter(item => item.source_snapshot_id === snapshotId),
    [features, snapshotId],
  );
  const queuedCount = jobs.filter(job => ['QUEUED', 'RUNNING', 'QUEUE_FAILED'].includes(job.status)).length;
  const succeededCount = evaluations.filter(item => item.status === 'SUCCEEDED' && item.out_of_sample).length;

  async function refresh() {
    setBusy(true);
    setError('');
    try {
      const [nextSnapshots, nextFeatures, nextJobs, nextEvaluations] = await Promise.all([
        apiRequest<Snapshot[]>('/data/snapshots', { token }),
        apiRequest<FeatureSet[]>('/features/versions', { token }),
        apiRequest<Job[]>('/jobs?limit=100', { token }),
        apiRequest<RLEvaluation[]>('/rl/evaluations', { token }),
      ]);
      setSnapshots(nextSnapshots);
      setFeatures(nextFeatures);
      setJobs(nextJobs.filter(job => job.task_name === 'rl.evaluate'));
      setEvaluations(nextEvaluations);
      if (!snapshotId) {
        const first = nextSnapshots.find(item => item.status === 'READY' && item.storage_format.toLowerCase() === 'parquet');
        if (first) setSnapshotId(first.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load RL workspace');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(timer);
  }, [token]);

  useEffect(() => {
    if (selectedFeatures.length && !selectedFeatures.some(item => item.id === featureId)) {
      setFeatureId(selectedFeatures[0].id);
    } else if (!selectedFeatures.length && featureId) {
      setFeatureId('');
    }
  }, [selectedFeatures, featureId]);

  useEffect(() => {
    setComparison([]);
  }, [snapshotId, featureId]);

  async function queueTraining() {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const job = await apiRequest<Job>('/rl/evaluations/jobs', {
        token,
        method: 'POST',
        body: JSON.stringify({
          idempotency_key: `rl-${crypto.randomUUID()}`,
          dataset_snapshot_id: snapshotId,
          feature_set_version_id: featureId,
          algorithm,
          price_column: 'close',
          date_column: 'date',
          seed: 42,
          total_timesteps: Number(timesteps),
          train_fraction: 0.70,
          fee_bps: 5,
          slippage_bps: 5,
        }),
      });
      setNotice(`Queued ${algorithm} training job ${job.id}. A configured Redis/Celery worker and the optional RL dependencies are required to execute it.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not queue RL training');
    } finally {
      setBusy(false);
    }
  }

  async function retry(job: Job) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const updated = await apiRequest<Job>(`/jobs/${job.id}/retry`, { token, method: 'POST' });
      setNotice(`RL evaluation job ${updated.id} was returned to the queue.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not retry RL job');
    } finally {
      setBusy(false);
    }
  }

  async function compare() {
    setBusy(true);
    setError('');
    try {
      const rows = await apiRequest<RLEvaluation[]>(
        `/rl/evaluations/comparison?dataset_snapshot_id=${encodeURIComponent(snapshotId)}&feature_set_version_id=${encodeURIComponent(featureId)}`,
        { token },
      );
      setComparison(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to compare RL evaluations');
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel">
    <div className="panel-title">
      <div>
        <h3><BrainCircuit size={16} /> PPO / SAC out-of-sample lab</h3>
        <p className="muted small">Chronological train/test split, bounded long-only allocation, trading costs and deterministic evaluation.</p>
      </div>
      <button className="secondary-button" onClick={() => void refresh()} disabled={busy}><RefreshCw size={13} /> Refresh</button>
    </div>
    {error && <p className="error-banner">{error}</p>}
    {notice && <p className="success-banner">{notice}</p>}

    <div className="metric-grid">
      <article className="metric-card"><p>READY Parquet snapshots</p><strong>{availableSnapshots.length}</strong><small>Eligible RL datasets</small></article>
      <article className="metric-card"><p>Queued / running jobs</p><strong>{queuedCount}</strong><small>Includes queue failures</small></article>
      <article className="metric-card"><p>OOS evaluations</p><strong>{succeededCount}</strong><small>Successfully completed</small></article>
      <article className="metric-card"><p>Algorithms</p><strong>PPO · SAC</strong><small>Stable-Baselines3</small></article>
    </div>

    <div className="experiment-form rl-form">
      <label>READY Parquet snapshot
        <select value={snapshotId} onChange={event => setSnapshotId(event.target.value)}>
          <option value="">Select snapshot</option>
          {availableSnapshots.map(item => <option key={item.id} value={item.id}>{item.instrument_symbol} · {item.start_date} to {item.end_date}</option>)}
        </select>
      </label>
      <label>Feature-set version
        <select value={featureId} onChange={event => setFeatureId(event.target.value)}>
          <option value="">Select feature set</option>
          {selectedFeatures.map(item => <option key={item.id} value={item.id}>{item.feature_key} v{item.version}</option>)}
        </select>
      </label>
      <label>Algorithm
        <select value={algorithm} onChange={event => setAlgorithm(event.target.value as 'PPO' | 'SAC')}>
          <option value="PPO">PPO</option><option value="SAC">SAC</option>
        </select>
      </label>
      <label>Training timesteps
        <input type="number" min="5000" max="2000000" step="1000" value={timesteps} onChange={event => setTimesteps(event.target.value)} />
      </label>
      {canTrain ? (
        <button className="primary-button" disabled={busy || !snapshotId || !featureId || !Number.isInteger(Number(timesteps)) || Number(timesteps) < 5000 || Number(timesteps) > 2000000} onClick={() => void queueTraining()}>
          <Play size={13} /> Queue {algorithm} training
        </button>
      ) : (
        <p className="inline-note"><AlertTriangle size={14} /> You have read-only access. Quant Researcher or Admin is required to queue training.</p>
      )}
      <button className="secondary-button" disabled={busy || !snapshotId || !featureId} onClick={() => void compare()}>Compare PPO vs SAC</button>
    </div>
    {!availableSnapshots.length && <div className="empty-state">No READY Parquet snapshot is available. Ingest a historical market-data snapshot and create a feature-set version first.</div>}

    <section className="panel">
      <div className="panel-title"><div><h3>Training jobs</h3><p className="muted small">Queue dispatch, worker state and retry after Redis/Celery outages.</p></div><span className="tag">{jobs.length} jobs</span></div>
      <div className="table-scroll"><table>
        <thead><tr><th>Job ID</th><th>Status</th><th>Evaluation</th><th>Created</th><th>Action</th></tr></thead>
        <tbody>{jobs.map(job => <tr key={job.id}>
          <td className="mono">{job.id.slice(0, 12)}</td>
          <td><span className={`run-status ${job.status.toLowerCase()}`}>{job.status}</span></td>
          <td>{String(job.result?.rl_evaluation_id ?? '—')}</td>
          <td>{job.created_at ? new Date(job.created_at).toLocaleString() : '—'}</td>
          <td>{job.status === 'QUEUE_FAILED' && canTrain ? <button className="secondary-button" disabled={busy} onClick={() => void retry(job)}><RotateCcw size={12} /> Retry</button> : '—'}</td>
        </tr>)}</tbody>
      </table></div>
      {!jobs.length && <div className="empty-state">No PPO/SAC training jobs have been queued.</div>}
    </section>

    <section className="panel">
      <div className="panel-title"><div><h3>Completed RL evaluations</h3><p className="muted small">Model metrics, artifact lineage and test-window status.</p></div><span className="tag">{evaluations.length} evaluations</span></div>
      <div className="table-scroll"><table>
        <thead><tr><th>Algorithm</th><th>OOS</th><th>Return</th><th>Sharpe</th><th>Max drawdown</th><th>Volatility</th><th>Test bars</th><th>Artifact SHA</th></tr></thead>
        <tbody>{evaluations.map(item => <tr key={item.id}>
          <td>{item.algorithm}</td><td>{item.out_of_sample ? 'Yes' : 'No'}</td>
          <td>{metric(item.metrics.total_return, 4)}</td><td>{metric(item.metrics.sharpe_ratio)}</td>
          <td>{metric(item.metrics.max_drawdown, 4)}</td><td>{metric(item.metrics.annualized_volatility, 4)}</td>
          <td>{String(item.metrics.test_observations ?? item.metrics.observations ?? '—')}</td>
          <td className="mono">{item.artifact_sha256?.slice(0, 12) ?? '—'}</td>
        </tr>)}</tbody>
      </table></div>
      {!evaluations.length && <div className="empty-state">No completed RL evaluation yet. Queue PPO or SAC after selecting a READY snapshot and feature version.</div>}
    </section>

    {comparison.length > 0 && <section className="panel">
      <div className="panel-title"><div><h3>Same-lineage algorithm comparison</h3><p className="muted small">Only successful out-of-sample runs with this exact snapshot and feature-set version are included.</p></div><span className="tag">{comparison.length} runs</span></div>
      <div className="table-scroll"><table>
        <thead><tr><th>Algorithm</th><th>Return</th><th>Sharpe</th><th>Drawdown</th><th>Volatility</th><th>Test observations</th><th>Run ID</th></tr></thead>
        <tbody>{comparison.map(item => <tr key={item.id}>
          <td>{item.algorithm}</td><td>{metric(item.metrics.total_return, 4)}</td><td>{metric(item.metrics.sharpe_ratio)}</td>
          <td>{metric(item.metrics.max_drawdown, 4)}</td><td>{metric(item.metrics.annualized_volatility, 4)}</td>
          <td>{String(item.metrics.test_observations ?? item.metrics.observations ?? '—')}</td><td className="mono">{item.id.slice(0, 12)}</td>
        </tr>)}</tbody>
      </table></div>
    </section>}

    <p className="inline-note"><AlertTriangle size={14} /> The action space is long-only and bounded to 0–100% exposure. RL outputs are research artifacts only; they cannot submit orders directly or bypass model governance.</p>
  </section>;
}
