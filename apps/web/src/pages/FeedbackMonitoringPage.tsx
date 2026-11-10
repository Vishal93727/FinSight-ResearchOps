import { FormEvent, useEffect, useState } from 'react';
import { Activity, AlertTriangle, ArrowUpRight, BrainCircuit, RefreshCw, Target } from 'lucide-react';
import { apiRequest } from '../lib/api';

type Summary = {
  outcome_metrics: { sample_count: number; mae: number | null; rmse: number | null; mean_bias: number | null; directional_accuracy: number | null; directional_sample_count: number };
  outcome_count: number;
  latest_outcomes: { id: string; symbol: string; forecast_date: string; realised_date: string; predicted: number; realised: number; error: number; benchmark: number | null }[];
  strategy_snapshots: { id: string; strategy_key: string; period_start: string; period_end: string; metrics: Record<string, number | string | null> }[];
  drift: { total: number; open: number; latest: { id: string; status: string; summary: { drifted_features?: number; review_features?: number }; created_at: string }[] };
  suggestions: { id: string; title: string; rationale: string; suggested_action: string; source_type: string; status: string; created_at: string }[];
  proposed_suggestions: number;
};

const today = new Date().toISOString().slice(0, 10);
const priorWeek = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
const fmt = (value: number | null | undefined, digits = 4) => value == null ? '—' : value.toFixed(digits);

export function FeedbackMonitoringPage({ token, roles }: { token: string; roles: string[] }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [symbol, setSymbol] = useState('MSFT');
  const [forecastDate, setForecastDate] = useState(priorWeek);
  const [realisedDate, setRealisedDate] = useState(today);
  const [predicted, setPredicted] = useState('0.012');
  const [realised, setRealised] = useState('0.009');
  const [horizon, setHorizon] = useState('5');
  const [outcomeModelVersionId, setOutcomeModelVersionId] = useState('');
  const [outcomeRunId, setOutcomeRunId] = useState('');
  const [outcomePaperAccountId, setOutcomePaperAccountId] = useState('');
  const [benchmarkOutcome, setBenchmarkOutcome] = useState('');
  const [baseline, setBaseline] = useState('0.01,0.02,0.00,-0.01,0.015,0.006,-0.004,0.008,0.011,-0.003,0.005,0.009');
  const [current, setCurrent] = useState('0.10,0.12,0.08,0.13,0.09,0.11,0.14,0.07,0.12,0.10,0.08,0.13');
  const [strategyKey, setStrategyKey] = useState('baseline-momentum');
  const [experimentRunId, setExperimentRunId] = useState('');
  const [returnsText, setReturnsText] = useState('0.01,0.012,-0.004,0.008,0.006,0.011,-0.003,0.009');
  const [benchmarkText, setBenchmarkText] = useState('0.006,0.008,-0.002,0.007,0.004,0.008,-0.001,0.006');

  const canWrite = roles.some(role => ['ADMIN', 'QUANT_RESEARCHER', 'PORTFOLIO_ANALYST'].includes(role));
  const canDrift = roles.some(role => ['ADMIN', 'QUANT_RESEARCHER', 'RISK_REVIEWER'].includes(role));
  const canDecide = roles.some(role => ['ADMIN', 'QUANT_RESEARCHER'].includes(role));

  async function refresh() {
    setLoading(true);
    try {
      const value = await apiRequest<Summary>('/feedback/summary', { token });
      setSummary(value); setError('');
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load monitoring data'); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, [token]);

  async function recordOutcome(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      await apiRequest('/feedback/outcomes', { token, method: 'POST', body: JSON.stringify({
        instrument_symbol: symbol.trim().toUpperCase(), forecast_date: forecastDate, realised_date: realisedDate,
        horizon_sessions: Number(horizon), predicted_return: Number(predicted), realised_return: Number(realised),
        ...(benchmarkOutcome.trim() !== '' ? { benchmark_return: Number(benchmarkOutcome) } : {}),
        ...(outcomeModelVersionId.trim() ? { model_version_id: outcomeModelVersionId.trim() } : {}),
        ...(outcomeRunId.trim() ? { experiment_run_id: outcomeRunId.trim() } : {}),
        ...(outcomePaperAccountId.trim() ? { paper_account_id: outcomePaperAccountId.trim() } : {}),
        observation_source: 'MANUAL_RECONCILIATION', idempotency_key: `web-${Date.now()}-${symbol.trim().toUpperCase()}`,
      }) });
      setNotice('Realised outcome recorded and linked to the feedback ledger.'); await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to record outcome'); }
    finally { setBusy(false); }
  }

  async function checkDrift(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const parse = (text: string) => text.split(',').map(item => Number(item.trim()));
      const base = parse(baseline); const now = parse(current);
      if (base.some(Number.isNaN) || now.some(Number.isNaN)) throw new Error('Drift samples must be comma-separated numbers.');
      await apiRequest('/feedback/drift/check', { token, method: 'POST', body: JSON.stringify({
        reference_features: { daily_return: base }, current_features: { daily_return: now },
      }) });
      setNotice('Feature drift assessment saved. A drift flag is a review trigger, not an automatic retraining decision.'); await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to assess drift'); }
    finally { setBusy(false); }
  }

  async function evaluateStrategy(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const parse = (text: string) => text.split(',').map(item => Number(item.trim()));
      const values = parse(returnsText); const benchmark = parse(benchmarkText);
      if (values.some(Number.isNaN) || benchmark.some(Number.isNaN)) throw new Error('Returns must be comma-separated decimal values.');
      await apiRequest('/feedback/strategies/evaluate', { token, method: 'POST', body: JSON.stringify({
        strategy_key: strategyKey, period_start: `${forecastDate}T00:00:00Z`, period_end: `${realisedDate}T23:59:59Z`,
        returns: values, benchmark_returns: benchmark, source_reference: 'Feedback Monitoring UI',
      }) });
      setNotice('Strategy monitoring snapshot saved.'); await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to evaluate strategy'); }
    finally { setBusy(false); }
  }


  async function evaluateCompletedRun(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const result = await apiRequest<{ strategy_key: string; metrics: Record<string, number | string | null> }>('/feedback/strategies/evaluate-run', {
        token, method: 'POST', body: JSON.stringify({ experiment_run_id: experimentRunId.trim() }),
      });
      setNotice(`Imported ${result.strategy_key} from a hash-verified completed experiment run.`);
      setExperimentRunId(''); await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to import completed backtest run'); }
    finally { setBusy(false); }
  }

  async function generateSuggestions() {
    setBusy(true); setError(''); setNotice('');
    try { await apiRequest('/feedback/suggestions/generate', { token, method: 'POST' }); setNotice('Follow-up research suggestions generated.'); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to generate suggestions'); }
    finally { setBusy(false); }
  }

  async function decideSuggestion(id: string, status: 'ACCEPTED' | 'DISMISSED') {
    setBusy(true); setError('');
    try { await apiRequest(`/feedback/suggestions/${id}/decision`, { token, method: 'POST', body: JSON.stringify({ status, comment: status === 'ACCEPTED' ? 'Accepted for research backlog review.' : 'Dismissed after review.' }) }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to update suggestion'); }
    finally { setBusy(false); }
  }

  const metrics = summary?.outcome_metrics;
  return <>
    <div className="page-heading"><div><p className="eyebrow">OUTCOME FEEDBACK LOOP</p><h2>Feedback & monitoring</h2><p className="muted">Compare forecasts with realised outcomes, watch strategy health and turn monitoring evidence into follow-up research.</p></div><button className="secondary-button" onClick={() => void refresh()}><RefreshCw size={13}/> Refresh</button></div>
    {error && <p className="error-banner">{error}</p>}{notice && <p className="success-banner">{notice}</p>}
    <div className="metric-grid phase5-metrics">
      <article className="metric-card"><span>Realised outcomes</span><strong>{loading ? '…' : summary?.outcome_count ?? 0}</strong><small>Prediction-to-outcome records</small></article>
      <article className="metric-card"><span>Forecast MAE</span><strong>{fmt(metrics?.mae)}</strong><small>Mean absolute return error</small></article>
      <article className="metric-card"><span>Directional accuracy</span><strong>{metrics?.directional_accuracy == null ? '—' : `${(metrics.directional_accuracy * 100).toFixed(1)}%`}</strong><small>{metrics?.directional_sample_count ?? 0} non-zero directions</small></article>
      <article className="metric-card"><span>Drift flags</span><strong>{summary?.drift.open ?? 0}</strong><small>Require human investigation</small></article>
      <article className="metric-card"><span>Research proposals</span><strong>{summary?.proposed_suggestions ?? 0}</strong><small>Awaiting researcher decision</small></article>
    </div>

    {canWrite && <div className="phase5-grid">
      <section className="panel"><div className="panel-title"><h3><Target size={15}/> Record realised outcome</h3><span className="tag">Manual reconciliation</span></div><p className="muted small">Record a forecast and its realised return after the evaluation horizon. Optional model/run/account lineage can also be submitted through the API.</p>
        <form className="phase5-form" onSubmit={recordOutcome}>
          <label>Instrument<input value={symbol} onChange={e => setSymbol(e.target.value)} required maxLength={32}/></label>
          <label>Forecast date<input type="date" value={forecastDate} onChange={e => setForecastDate(e.target.value)} required/></label>
          <label>Realised date<input type="date" value={realisedDate} onChange={e => setRealisedDate(e.target.value)} required min={forecastDate}/></label>
          <label>Horizon (sessions)<input type="number" min="1" max="252" value={horizon} onChange={e => setHorizon(e.target.value)} required/></label>
          <label>Predicted return<input type="number" step="0.0001" value={predicted} onChange={e => setPredicted(e.target.value)} required/></label>
          <label>Realised return<input type="number" step="0.0001" value={realised} onChange={e => setRealised(e.target.value)} required/></label>
          <label>Benchmark return (optional)<input type="number" step="0.0001" value={benchmarkOutcome} onChange={e => setBenchmarkOutcome(e.target.value)} /></label>
          <label>Model version ID (optional)<input value={outcomeModelVersionId} onChange={e => setOutcomeModelVersionId(e.target.value)} maxLength={36} /></label>
          <label>Experiment run ID (optional)<input value={outcomeRunId} onChange={e => setOutcomeRunId(e.target.value)} maxLength={36} /></label>
          <label>Paper account ID (optional)<input value={outcomePaperAccountId} onChange={e => setOutcomePaperAccountId(e.target.value)} maxLength={36} /></label>
          <button className="primary-button" disabled={busy}>Save outcome</button>
        </form>
      </section>
      <section className="panel"><div className="panel-title"><h3><Activity size={15}/> Evaluate strategy window</h3><span className="tag">Cost-adjusted returns expected</span></div>
        <form className="phase5-form" onSubmit={evaluateStrategy}>
          <label>Strategy key<input value={strategyKey} onChange={e => setStrategyKey(e.target.value)} required/></label>
          <label>Period start<input type="date" value={forecastDate} onChange={e => setForecastDate(e.target.value)} required/></label>
          <label>Period end<input type="date" value={realisedDate} onChange={e => setRealisedDate(e.target.value)} required min={forecastDate}/></label>
          <label className="phase5-wide">Strategy returns<textarea rows={2} value={returnsText} onChange={e => setReturnsText(e.target.value)}/></label>
          <label className="phase5-wide">Benchmark returns<textarea rows={2} value={benchmarkText} onChange={e => setBenchmarkText(e.target.value)}/></label>
          <button className="primary-button" disabled={busy}>Save performance snapshot</button>
        </form>
      </section>
    </div>}

    {canWrite && <section className="panel"><div className="panel-title"><h3><Activity size={15}/> Import a completed backtest</h3><span className="tag">Pinned run artifact</span></div><p className="muted small">Derive monitoring metrics directly from a successful Phase 2 run. The API verifies artifact path ownership and SHA-256 before reading the equity curve.</p><form className="phase5-form phase5-run-import" onSubmit={evaluateCompletedRun}><label className="phase5-wide">Experiment run ID<input value={experimentRunId} onChange={event => setExperimentRunId(event.target.value)} required minLength={1} maxLength={36} placeholder="Paste a completed experiment run ID" /></label><button className="primary-button" disabled={busy || !experimentRunId.trim()}>Import and evaluate run</button></form></section>}

    {canDrift && <section className="panel"><div className="panel-title"><h3><AlertTriangle size={15}/> Feature drift check</h3><span className="tag">PSI + KS diagnostic</span></div><p className="muted small">Compare at least 10 reference and current numeric observations per feature. A drift signal prompts investigation; it never automatically promotes, rolls back or retrains a model.</p>
      <form className="phase5-form phase5-drift-form" onSubmit={checkDrift}>
        <label>Reference sample (comma-separated)<textarea rows={2} value={baseline} onChange={e => setBaseline(e.target.value)}/></label>
        <label>Current sample (comma-separated)<textarea rows={2} value={current} onChange={e => setCurrent(e.target.value)}/></label>
        <button className="primary-button" disabled={busy}>Run drift check</button>
      </form>
    </section>}

    <section className="panel"><div className="panel-title"><h3><ArrowUpRight size={15}/> Prediction versus realised</h3><span className="tag">Latest records</span></div>
      <div className="table-scroll"><table><thead><tr><th>Symbol</th><th>Forecast date</th><th>Realised date</th><th>Predicted</th><th>Realised</th><th>Error</th></tr></thead><tbody>{summary?.latest_outcomes.map(row => <tr key={row.id}><td>{row.symbol}</td><td>{row.forecast_date}</td><td>{row.realised_date}</td><td>{fmt(row.predicted, 4)}</td><td>{fmt(row.realised, 4)}</td><td className={row.error > 0 ? 'value-negative' : 'value-positive'}>{fmt(row.error, 4)}</td></tr>)}</tbody></table>{!summary?.latest_outcomes.length && <div className="empty-state">No realised outcomes have been recorded yet.</div>}</div>
    </section>

    <div className="panel-grid"><section className="panel"><h3>Strategy performance snapshots</h3>{summary?.strategy_snapshots.map(row => <div className="list-row" key={row.id}><div><strong>{row.strategy_key}</strong><small>{row.period_start.slice(0, 10)} to {row.period_end.slice(0, 10)} · CAGR-style compounded return {fmt(Number(row.metrics.cumulative_return) * 100, 2)}%</small></div><span className="tiny-status">Sharpe {fmt(Number(row.metrics.annualized_sharpe) || null, 2)}</span></div>)}{!summary?.strategy_snapshots.length && <div className="empty-state">No strategy monitoring snapshots yet.</div>}</section>
      <section className="panel"><h3>Latest drift assessments</h3>{summary?.drift.latest.map(row => <div className="list-row" key={row.id}><div><strong>{row.status}</strong><small>{row.summary.drifted_features ?? 0} drifted · {row.summary.review_features ?? 0} review features</small></div><span className={`run-status ${row.status.toLowerCase()}`}>{row.status}</span></div>)}{!summary?.drift.latest.length && <div className="empty-state">No feature drift assessments yet.</div>}</section></div>

    <section className="panel"><div className="panel-title"><h3><BrainCircuit size={15}/> Follow-up research suggestions</h3>{canDrift && <button className="secondary-button" disabled={busy} onClick={() => void generateSuggestions()}>Generate suggestions</button>}</div>
      {summary?.suggestions.map(item => <div className="phase5-suggestion" key={item.id}><div><strong>{item.title}</strong><small>{item.rationale}</small><p>{item.suggested_action}</p></div><div className="phase5-suggestion-actions"><span className={`run-status ${item.status.toLowerCase()}`}>{item.status}</span>{canDecide && item.status === 'PROPOSED' && <><button className="secondary-button" disabled={busy} onClick={() => void decideSuggestion(item.id, 'ACCEPTED')}>Accept</button><button className="secondary-button" disabled={busy} onClick={() => void decideSuggestion(item.id, 'DISMISSED')}>Dismiss</button></>}</div></div>)}{!summary?.suggestions.length && <div className="empty-state">No follow-up suggestions generated yet.</div>}
    </section>
  </>;
}
