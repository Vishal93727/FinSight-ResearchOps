import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, BarChart3, RefreshCw, ShieldCheck } from 'lucide-react';
import { apiRequest } from '../lib/api';
import { RLEvaluationPanel } from '../components/RLEvaluationPanel';

type Experiment = {
  id: string;
  name: string;
  instrument_symbol: string;
  dataset_snapshot_id: string;
  benchmark_snapshot_id?: string | null;
  configuration: Record<string, unknown>;
  configuration_sha256: string;
};
type Comparison = {
  run_id: string;
  run_number: number;
  status: string;
  total_return?: number | null;
  annualized_return?: number | null;
  sharpe_ratio?: number | null;
  max_drawdown?: number | null;
  annualized_volatility?: number | null;
  benchmark_total_return?: number | null;
  information_ratio?: number | null;
  risk_decision?: string | null;
};
type RiskReview = {
  decision: string;
  policy_version: string;
  limits: Record<string, unknown>;
  observed_metrics: Record<string, unknown>;
  breaches: Array<Record<string, unknown>>;
  warnings: Array<Record<string, unknown>>;
  deterministic: boolean;
  override_allowed: boolean;
};
type StrategyResult = {
  experiment: Experiment;
  comparison: Comparison;
};

function percent(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : '—';
}
function number(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '—';
}
function strategyName(configuration: Record<string, unknown>): string {
  const value = String(configuration.baseline ?? 'baseline');
  return ({
    buy_and_hold: 'Buy and hold',
    moving_average_crossover: 'Moving average crossover',
    rsi_mean_reversion: 'RSI mean reversion',
  } as Record<string, string>)[value] ?? value;
}

export function StrategyBacktestPage({ token, roles }: { token: string; roles: string[] }) {
  const [results, setResults] = useState<StrategyResult[]>([]);
  const [symbolFilter, setSymbolFilter] = useState('ALL');
  const [strategyFilter, setStrategyFilter] = useState('ALL');
  const [selectedRisk, setSelectedRisk] = useState<RiskReview | null>(null);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function refresh() {
    setBusy(true);
    setError('');
    setSelectedRisk(null);
    try {
      const experiments = await apiRequest<Experiment[]>('/experiments', { token });
      const groups = await Promise.all(experiments.map(async experiment => {
        const comparisons = await apiRequest<Comparison[]>(`/experiments/${experiment.id}/runs/comparison`, { token });
        return comparisons
          .filter(item => item.status === 'SUCCEEDED')
          .map(comparison => ({ experiment, comparison }));
      }));
      const flattened = groups.flat().sort((a, b) => {
        const aRun = a.comparison.run_number;
        const bRun = b.comparison.run_number;
        return b.experiment.name.localeCompare(a.experiment.name) || bRun - aRun;
      });
      setResults(flattened);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load backtest results');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void refresh(); }, [token]);

  const symbols = useMemo(() => ['ALL', ...Array.from(new Set(results.map(item => item.experiment.instrument_symbol))).sort()], [results]);
  const strategies = useMemo(() => ['ALL', ...Array.from(new Set(results.map(item => String(item.experiment.configuration.baseline ?? 'baseline')))).sort()], [results]);
  const filtered = useMemo(() => results.filter(item =>
    (symbolFilter === 'ALL' || item.experiment.instrument_symbol === symbolFilter)
    && (strategyFilter === 'ALL' || item.experiment.configuration.baseline === strategyFilter)), [results, symbolFilter, strategyFilter]);

  async function inspectRisk(runId: string, experimentId: string) {
    setSelectedRunId(runId);
    setSelectedRisk(null);
    setError('');
    try {
      const review = await apiRequest<RiskReview>(`/experiments/${experimentId}/runs/${runId}/risk-review`, { token });
      setSelectedRisk(review);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Risk review is not available for this run');
    }
  }

  return <>
    <RLEvaluationPanel token={token} roles={roles} />
    <div className="page-heading">
      <div><p className="eyebrow">PHASE 2 · STRATEGY EVALUATION</p><h2>Strategy & backtest lab</h2>
        <p className="muted">Inspect completed historical simulations across baseline strategies, datasets and pinned benchmarks.</p></div>
      <button className="secondary-button" onClick={() => void refresh()} disabled={busy}><RefreshCw size={14} /> Refresh results</button>
    </div>
    {error && <p className="error-banner">{error}</p>}

    <section className="metric-grid">
      <article className="metric-card"><div className="metric-icon"><BarChart3 /></div><p>Completed runs</p><strong>{results.length}</strong><small>Successful historical simulations</small></article>
      <article className="metric-card"><div className="metric-icon"><Activity /></div><p>Strategies represented</p><strong>{new Set(results.map(item => item.experiment.configuration.baseline)).size}</strong><small>Baseline definitions</small></article>
      <article className="metric-card"><div className="metric-icon"><ShieldCheck /></div><p>Risk passes</p><strong>{results.filter(item => item.comparison.risk_decision === 'PASS').length}</strong><small>Policy outcome, not investment approval</small></article>
      <article className="metric-card"><div className="metric-icon"><AlertTriangle /></div><p>Review / reject</p><strong>{results.filter(item => ['REVIEW', 'REJECT'].includes(item.comparison.risk_decision ?? '')).length}</strong><small>Requires interpretation of policy findings</small></article>
    </section>

    <section className="panel">
      <div className="panel-title"><div><h3>Backtest comparison</h3><p className="muted small">Compare results only after checking instrument, dataset lineage and test-window comparability.</p></div><span className="tag">{filtered.length} results</span></div>
      <div className="run-toolbar">
        <label>Instrument<select value={symbolFilter} onChange={event => setSymbolFilter(event.target.value)}>{symbols.map(symbol => <option key={symbol} value={symbol}>{symbol === 'ALL' ? 'All instruments' : symbol}</option>)}</select></label>
        <label>Baseline strategy<select value={strategyFilter} onChange={event => setStrategyFilter(event.target.value)}>{strategies.map(strategy => <option key={strategy} value={strategy}>{strategy === 'ALL' ? 'All baselines' : strategyName({ baseline: strategy })}</option>)}</select></label>
      </div>
      <div className="table-scroll"><table><thead><tr><th>Instrument</th><th>Strategy</th><th>Evaluation</th><th>Run</th><th>Total return</th><th>Annualized return</th><th>Benchmark</th><th>Sharpe</th><th>Volatility</th><th>Max drawdown</th><th>Info ratio</th><th>Risk</th><th>Detail</th></tr></thead><tbody>
        {filtered.map(item => <tr key={item.comparison.run_id}>
          <td>{item.experiment.instrument_symbol}</td>
          <td>{strategyName(item.experiment.configuration)}</td>
          <td>{String(item.experiment.configuration.evaluation_mode ?? 'holdout').replaceAll('_', ' ')}</td>
          <td>#{item.comparison.run_number}</td>
          <td>{percent(item.comparison.total_return)}</td>
          <td>{percent(item.comparison.annualized_return)}</td>
          <td>{item.experiment.benchmark_snapshot_id ? percent(item.comparison.benchmark_total_return) : 'Not pinned'}</td>
          <td>{number(item.comparison.sharpe_ratio)}</td>
          <td>{percent(item.comparison.annualized_volatility)}</td>
          <td>{percent(item.comparison.max_drawdown)}</td>
          <td>{number(item.comparison.information_ratio)}</td>
          <td><span className={`run-status ${(item.comparison.risk_decision ?? 'pending').toLowerCase()}`}>{item.comparison.risk_decision ?? 'Pending'}</span></td>
          <td><button className="secondary-button" onClick={() => void inspectRisk(item.comparison.run_id, item.experiment.id)}>Risk review</button></td>
        </tr>)}
      </tbody></table></div>
      {!filtered.length && <div className="empty-state"><BarChart3 size={20} /><p>{busy ? 'Loading historical backtest results…' : 'No completed backtests match these filters. Create an experiment and queue a run in Experiment Lab.'}</p></div>}
    </section>

    {selectedRisk && <section className="panel">
      <div className="panel-title"><div><h3>Deterministic risk review</h3><p className="muted small">Run {selectedRunId} · Policy {selectedRisk.policy_version}</p></div><span className={`run-status ${selectedRisk.decision.toLowerCase()}`}>{selectedRisk.decision}</span></div>
      <div className="metric-grid">
        {Object.entries(selectedRisk.observed_metrics).filter(([, value]) => typeof value === 'number').slice(0, 8).map(([key, value]) => <article className="metric-card" key={key}><p>{key.replaceAll('_', ' ')}</p><strong>{typeof value === 'number' ? (key.includes('return') || key.includes('drawdown') || key.includes('volatility') || key.includes('alpha') ? percent(value) : number(value)) : '—'}</strong></article>)}
      </div>
      <p className="inline-note">Deterministic: {String(selectedRisk.deterministic)} · LLM override allowed: {String(selectedRisk.override_allowed)}</p>
      <div className="table-scroll"><table><thead><tr><th>Finding</th><th>Severity</th><th>Observed</th><th>Limit</th></tr></thead><tbody>
        {[...selectedRisk.breaches, ...selectedRisk.warnings].map((item, index) => <tr key={`${String(item.rule)}-${index}`}><td>{String(item.rule)}</td><td>{String(item.severity)}</td><td>{String(item.observed)}</td><td>{String(item.limit)}</td></tr>)}
      </tbody></table></div>
      {!selectedRisk.breaches.length && !selectedRisk.warnings.length && <p className="success-banner">No policy findings were recorded for this run.</p>}
    </section>}

    <div className="notice"><ShieldCheck size={18} /><p><strong>Interpret results carefully:</strong> these are historical, research-only simulations. Results can be affected by source quality, corporate actions, survivorship bias, liquidity, market impact and cost assumptions. A risk PASS is not an investment recommendation, model promotion or guarantee of future performance.</p></div>
  </>;
}
