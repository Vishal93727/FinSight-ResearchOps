import { useEffect, useMemo, useState } from 'react';
import { BadgeCheck, GitBranch, RefreshCw, ShieldCheck, XCircle } from 'lucide-react';
import { apiRequest } from '../lib/api';

type Evaluation = { id: string; model_family: string; metrics: Record<string, unknown>; status: string; dataset_snapshot_id: string; feature_set_version_id: string };
type RLEvaluation = { id: string; algorithm: string; metrics: Record<string, unknown>; status: string; out_of_sample: boolean; dataset_snapshot_id: string; feature_set_version_id: string };
type ModelVersion = { id: string; model_key: string; version: string; model_family: string; source_evaluation_id: string | null; source_rl_evaluation_id: string | null; artifact_uri: string | null; artifact_sha256: string | null; dataset_snapshot_id: string | null; feature_set_version_id: string | null; metrics: Record<string, unknown>; risk_decision: string; state: string; created_by: string };
type RiskReview = { decision: string; policy_version: string; limits: Record<string, unknown>; observed_metrics: Record<string, unknown>; breaches: Array<Record<string, unknown>>; warnings: Array<Record<string, unknown>>; deterministic: boolean; override_allowed: boolean };

export function ModelGovernancePage({ token, userId, roles }: { token: string; userId: string; roles: string[] }) {
  const [models, setModels] = useState<ModelVersion[]>([]);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [rlEvaluations, setRlEvaluations] = useState<RLEvaluation[]>([]);
  const [sourceType, setSourceType] = useState<'supervised' | 'rl'>('supervised');
  const [sourceId, setSourceId] = useState('');
  const [modelKey, setModelKey] = useState('financial-alpha');
  const [version, setVersion] = useState('1.0.0');
  const [selectedRisk, setSelectedRisk] = useState<RiskReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const isReviewer = roles.includes('ADMIN') || roles.includes('RISK_REVIEWER');
  const isAdmin = roles.includes('ADMIN');
  const canRegister = isAdmin || roles.includes('QUANT_RESEARCHER');
  const sources = useMemo(() => sourceType === 'supervised'
    ? evaluations.filter(item => item.status === 'SUCCEEDED')
    : rlEvaluations.filter(item => item.status === 'SUCCEEDED' && item.out_of_sample), [sourceType, evaluations, rlEvaluations]);

  async function refresh() {
    setBusy(true); setError('');
    try {
      const [nextModels, nextEvaluations, nextRl] = await Promise.all([
        apiRequest<ModelVersion[]>('/governance/models', { token }),
        apiRequest<Evaluation[]>('/ml/evaluations', { token }),
        apiRequest<RLEvaluation[]>('/rl/evaluations', { token }),
      ]);
      setModels(nextModels); setEvaluations(nextEvaluations); setRlEvaluations(nextRl);
      if (!sourceId && sources.length) setSourceId(sources[0].id);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load model registry'); }
    finally { setBusy(false); }
  }
  useEffect(() => { void refresh(); }, [token]);
  useEffect(() => {
    if (sources.length && !sources.some(item => item.id === sourceId)) setSourceId(sources[0].id);
    if (!sources.length && sourceId) setSourceId('');
  }, [sources, sourceId]);

  async function register() {
    setBusy(true); setError(''); setNotice('');
    try {
      const payload = sourceType === 'supervised'
        ? { model_key: modelKey, version, source_evaluation_id: sourceId }
        : { model_key: modelKey, version, source_rl_evaluation_id: sourceId };
      await apiRequest('/governance/models', { token, method: 'POST', body: JSON.stringify(payload) });
      setNotice('Candidate registered with an independent deterministic risk review.');
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : 'Model registration failed'); }
    finally { setBusy(false); }
  }

  async function decide(model: ModelVersion, decision: 'APPROVE' | 'REJECT') {
    setBusy(true); setError('');
    try {
      await apiRequest(`/governance/models/${model.id}/decision`, { token, method: 'POST', body: JSON.stringify({ decision, comment: `Reviewed in Model Registry: ${decision}` }) });
      setNotice(`Governance decision recorded: ${decision}.`); await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : 'Decision failed'); }
    finally { setBusy(false); }
  }

  async function transition(model: ModelVersion, action: 'promote' | 'rollback') {
    setBusy(true); setError('');
    try {
      await apiRequest(`/governance/models/${model.id}/${action}`, { token, method: 'POST' });
      setNotice(action === 'promote' ? 'Model version promoted.' : 'Model version restored through rollback.');
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : `Model ${action} failed`); }
    finally { setBusy(false); }
  }

  async function inspect(model: ModelVersion) {
    setError(''); setSelectedRisk(null);
    try { setSelectedRisk(await apiRequest<RiskReview>(`/governance/models/${model.id}/risk-review`, { token })); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to inspect model risk'); }
  }

  return <>
    <div className="page-heading">
      <div><p className="eyebrow">PHASE 4 · GOVERNANCE</p><h2>Model Registry & Governance</h2><p className="muted">Versioned artifacts, deterministic risk gates, independent review, promotion and rollback.</p></div>
      <button className="secondary-button" onClick={() => void refresh()} disabled={busy}><RefreshCw size={14} /> Refresh</button>
    </div>
    {error && <p className="error-banner">{error}</p>}{notice && <p className="success-banner">{notice}</p>}
    {canRegister ? <section className="panel">
      <div className="panel-title"><div><h3>Register evaluation as a candidate</h3><p className="muted small">Registration pins the evaluation lineage and calculates a deterministic risk decision. It does not promote the model.</p></div><span className="tag">Candidate intake</span></div>
      <div className="experiment-form governance-form">
        <label>Evaluation family<select value={sourceType} onChange={event => { setSourceType(event.target.value as 'supervised' | 'rl'); setSourceId(''); }}><option value="supervised">Supervised ML</option><option value="rl">Reinforcement learning</option></select></label>
        <label>Evaluation<select value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">Select evaluation</option>{sources.map(item => <option key={item.id} value={item.id}>{'model_family' in item ? item.model_family : item.algorithm} · {item.id.slice(0, 8)}</option>)}</select></label>
        <label>Model key<input value={modelKey} onChange={event => setModelKey(event.target.value)} maxLength={120} /></label>
        <label>Version<input value={version} onChange={event => setVersion(event.target.value)} maxLength={64} /></label>
        <button className="primary-button" disabled={busy || !sourceId || !modelKey.trim() || !version.trim()} onClick={() => void register()}><GitBranch size={14} /> Register candidate</button>
      </div>
    </section> : <p className="inline-note">Model candidate registration requires the ADMIN or QUANT_RESEARCHER role. You can inspect versions and risk decisions using your read permissions.</p>}
    <section className="panel">
      <div className="panel-title"><div><h3>Version history</h3><p className="muted small">Human approval and deterministic risk PASS are mandatory before promotion.</p></div><span className="tag">{models.length} versions</span></div>
      <div className="table-scroll"><table><thead><tr><th>Model</th><th>Version</th><th>Family</th><th>Risk</th><th>State</th><th>Artifact hash</th><th>Actions</th></tr></thead><tbody>
        {models.map(model => <tr key={model.id}><td>{model.model_key}</td><td>{model.version}</td><td>{model.model_family}</td><td><span className={`run-status ${model.risk_decision.toLowerCase()}`}>{model.risk_decision}</span></td><td><span className={`run-status ${model.state.toLowerCase()}`}>{model.state}</span></td><td className="mono">{model.artifact_sha256?.slice(0, 12) ?? 'Missing'}</td><td><div className="stack-actions">
          <button className="secondary-button" onClick={() => void inspect(model)}>Risk</button>
          {isReviewer && model.state === 'CANDIDATE' && model.created_by !== userId && <><button className="secondary-button" disabled={busy} onClick={() => void decide(model, 'APPROVE')}><BadgeCheck size={12} /> Approve</button><button className="secondary-button" disabled={busy} onClick={() => void decide(model, 'REJECT')}><XCircle size={12} /> Reject</button></>}
          {isAdmin && model.state === 'APPROVED' && <button className="secondary-button" disabled={busy} onClick={() => void transition(model, 'promote')}>Promote</button>}
          {isAdmin && model.state === 'SUPERSEDED' && <button className="secondary-button" disabled={busy} onClick={() => void transition(model, 'rollback')}>Rollback</button>}
        </div></td></tr>)}
      </tbody></table></div>
      {!models.length && <div className="empty-state">No registered model versions yet. Complete an ML/RL evaluation and register it above.</div>}
    </section>
    {selectedRisk && <section className="panel"><div className="panel-title"><div><h3>Deterministic model risk review</h3><p className="muted small">Policy {selectedRisk.policy_version}</p></div><span className={`run-status ${selectedRisk.decision.toLowerCase()}`}>{selectedRisk.decision}</span></div>
      <p className="inline-note"><ShieldCheck size={14} /> Deterministic: {String(selectedRisk.deterministic)} · Override allowed: {String(selectedRisk.override_allowed)}</p>
      <div className="table-scroll"><table><thead><tr><th>Rule</th><th>Severity</th><th>Observed</th><th>Limit</th></tr></thead><tbody>{[...selectedRisk.breaches, ...selectedRisk.warnings].map((item, index) => <tr key={`${String(item.rule)}-${index}`}><td>{String(item.rule)}</td><td>{String(item.severity)}</td><td>{String(item.observed)}</td><td>{String(item.limit)}</td></tr>)}</tbody></table></div>
      {!selectedRisk.breaches.length && !selectedRisk.warnings.length && <p className="success-banner">No deterministic risk findings.</p>}
    </section>}
    <div className="notice"><ShieldCheck size={18} /><p><strong>Separation of duties:</strong> model authors cannot approve their own versions. Only an administrator can promote an independently approved model with a passing deterministic risk review. Rollback preserves prior decision history.</p></div>
  </>;
}
