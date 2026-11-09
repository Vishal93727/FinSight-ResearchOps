import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertOctagon, RefreshCw, ShieldCheck } from 'lucide-react';
import { apiRequest } from '../lib/api';

type Account = { id: string; name: string; currency: string; initial_cash: string; cash_balance: string; max_gross_exposure: number; max_symbol_exposure: number; max_order_notional: string; fee_bps: number; slippage_bps: number; kill_switch: boolean };
type Model = { id: string; model_key: string; version: string; model_family: string; state: string; risk_decision: string };
type Summary = { cash_balance: string; market_value: string; equity: string; gross_exposure: string; gross_exposure_ratio: string; kill_switch: boolean; positions: Array<{ symbol: string; quantity: string; average_entry_price: string; mark_price: string; market_value: string; realized_pnl: string }>; recent_orders: Array<{ id: string; symbol: string; side: string; quantity: string; status: string; client_order_id: string }> };
type Audit = { orders: Array<Record<string, unknown>>; fills: Array<Record<string, unknown>>; ledger: Array<Record<string, unknown>>; audit_events: Array<Record<string, unknown>> };

export function PaperExecutionPage({ token, roles }: { token: string; roles: string[] }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [summary, setSummary] = useState<Summary | null>(null);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [accountName, setAccountName] = useState('Research paper portfolio');
  const [initialCash, setInitialCash] = useState('100000');
  const [modelId, setModelId] = useState('');
  const [symbol, setSymbol] = useState('MSFT');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [quantity, setQuantity] = useState('10');
  const [referencePrice, setReferencePrice] = useState('100');
  const [reason, setReason] = useState('Risk control action');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const canCreate = roles.includes('ADMIN') || roles.includes('PORTFOLIO_ANALYST');
  const isAdmin = roles.includes('ADMIN');
  const canRiskOperate = isAdmin || roles.includes('RISK_REVIEWER');
  const canReconcile = canCreate || roles.includes('RISK_REVIEWER');
  const promotedModels = useMemo(() => models.filter(item => item.state === 'PROMOTED' && item.risk_decision === 'PASS'), [models]);

  async function refresh() {
    setBusy(true); setError('');
    try {
      const [nextAccounts, nextModels] = await Promise.all([
        apiRequest<Account[]>('/execution/accounts', { token }),
        apiRequest<Model[]>('/governance/models', { token }),
      ]);
      setAccounts(nextAccounts); setModels(nextModels);
      if (!selectedAccountId && nextAccounts.length) setSelectedAccountId(nextAccounts[0].id);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load paper execution workspace'); }
    finally { setBusy(false); }
  }

  async function refreshSelected(id = selectedAccountId) {
    if (!id) { setSummary(null); setAudit(null); return; }
    try {
      const [nextSummary, nextAudit] = await Promise.all([
        apiRequest<Summary>(`/execution/accounts/${id}/summary`, { token }),
        apiRequest<Audit>(`/execution/accounts/${id}/audit`, { token }),
      ]);
      setSummary(nextSummary); setAudit(nextAudit);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load account state'); }
  }
  useEffect(() => { void refresh(); }, [token]);
  useEffect(() => { void refreshSelected(); }, [selectedAccountId, token]);

  async function createAccount() {
    setBusy(true); setError(''); setNotice('');
    try {
      const account = await apiRequest<Account>('/execution/accounts', { token, method: 'POST', body: JSON.stringify({
        name: accountName, initial_cash: initialCash, currency: 'USD', max_gross_exposure: 1,
        max_symbol_exposure: 0.4, max_order_notional: '25000', fee_bps: 5, slippage_bps: 5,
      }) });
      setSelectedAccountId(account.id); setNotice('Paper account created. No live broker connection is used.'); await refresh(); await refreshSelected(account.id);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not create paper account'); }
    finally { setBusy(false); }
  }

  async function submitOrder() {
    if (!selectedAccountId) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await apiRequest<{ id: string; status: string; rejection_reason: string | null }>(`/execution/accounts/${selectedAccountId}/orders`, {
        token, method: 'POST',
        body: JSON.stringify({ client_order_id: `paper-${crypto.randomUUID()}`, model_version_id: modelId,
          symbol: symbol.toUpperCase(), side, quantity, simulation_reference_price: referencePrice }),
      });
      setNotice(`Paper order ${result.status.toLowerCase()}: ${result.id}${result.rejection_reason ? ` · ${result.rejection_reason}` : ''}`);
      await refreshSelected();
    } catch (err) { setError(err instanceof Error ? err.message : 'Paper order failed'); }
    finally { setBusy(false); }
  }

  async function setKillSwitch(active: boolean) {
    if (!selectedAccountId) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await apiRequest(`/execution/accounts/${selectedAccountId}/kill-switch`, { token, method: 'POST', body: JSON.stringify({ active, reason }) });
      setNotice(active ? 'Kill switch activated. New orders will be rejected.' : 'Kill switch deactivated by administrator.');
      await refresh(); await refreshSelected();
    } catch (err) { setError(err instanceof Error ? err.message : 'Kill-switch update failed'); }
    finally { setBusy(false); }
  }

  async function reconcile(repair: boolean) {
    if (!selectedAccountId) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await apiRequest<{ consistent: boolean; repaired: boolean; discrepancies: unknown[] }>(`/execution/accounts/${selectedAccountId}/reconcile`, {
        token, method: 'POST', body: JSON.stringify({ repair }),
      });
      setNotice(`Reconciliation ${result.consistent ? 'consistent' : 'found discrepancies'}${result.repaired ? ' · repaired by administrator' : ''}. Findings: ${result.discrepancies.length}`);
      await refreshSelected();
    } catch (err) { setError(err instanceof Error ? err.message : 'Reconciliation failed'); }
    finally { setBusy(false); }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">PHASE 4 · PAPER EXECUTION ONLY</p><h2>Paper Execution</h2><p className="muted">Simulated orders from promoted models, deterministic risk checks, fill accounting and reconciliation.</p></div><button className="secondary-button" onClick={() => void refresh()} disabled={busy}><RefreshCw size={14} /> Refresh</button></div>
    {error && <p className="error-banner">{error}</p>}{notice && <p className="success-banner">{notice}</p>}
    {canCreate && <section className="panel"><div className="panel-title"><div><h3>Create paper account</h3><p className="muted small">Simulation ledger only. Account limits are enforced by the broker service.</p></div><span className="tag">USD</span></div>
      <div className="catalogue-form"><label>Account name<input value={accountName} onChange={e => setAccountName(e.target.value)} /></label><label>Starting cash<input type="number" min="1" value={initialCash} onChange={e => setInitialCash(e.target.value)} /></label><button className="primary-button" disabled={busy || !accountName.trim()} onClick={() => void createAccount()}>Create paper account</button></div>
    </section>}
    <section className="panel"><div className="panel-title"><div><h3>Account & portfolio state</h3><p className="muted small">Equity equals paper cash plus marked position value.</p></div><span className="tag">{accounts.length} accounts</span></div>
      <div className="run-toolbar"><label>Paper account<select value={selectedAccountId} onChange={e => setSelectedAccountId(e.target.value)}><option value="">Select account</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name} · {account.currency}</option>)}</select></label></div>
      {summary && <><div className="metric-grid"><article className="metric-card"><p>Cash balance</p><strong>{Number(summary.cash_balance).toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></article><article className="metric-card"><p>Market value</p><strong>{Number(summary.market_value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></article><article className="metric-card"><p>Paper equity</p><strong>{Number(summary.equity).toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></article><article className="metric-card"><p>Gross exposure</p><strong>{(Number(summary.gross_exposure_ratio) * 100).toFixed(2)}%</strong></article></div>
        <p className="inline-note"><AlertOctagon size={14} /> Kill switch: <strong>{summary.kill_switch ? 'ACTIVE · ORDERS HALTED' : 'inactive'}</strong></p>
        <div className="table-scroll"><table><thead><tr><th>Symbol</th><th>Quantity</th><th>Average entry</th><th>Mark</th><th>Market value</th><th>Realized P&L</th></tr></thead><tbody>{summary.positions.map(pos => <tr key={pos.symbol}><td>{pos.symbol}</td><td>{pos.quantity}</td><td>{pos.average_entry_price}</td><td>{pos.mark_price}</td><td>{pos.market_value}</td><td>{pos.realized_pnl}</td></tr>)}</tbody></table></div>
      </>}
    </section>
    {canCreate && summary && <section className="panel"><div className="panel-title"><div><h3>Submit simulated order</h3><p className="muted small">Use a promoted and risk-passing model. Reference price is an explicit simulation input, not a live quote.</p></div><span className="tag">Paper broker</span></div>
      <div className="experiment-form"><label>Promoted model<select value={modelId} onChange={e => setModelId(e.target.value)}><option value="">Select model version</option>{promotedModels.map(model => <option key={model.id} value={model.id}>{model.model_key} v{model.version} · {model.model_family}</option>)}</select></label><label>Symbol<input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} /></label><label>Side<select value={side} onChange={e => setSide(e.target.value as 'BUY' | 'SELL')}><option value="BUY">BUY</option><option value="SELL">SELL</option></select></label><label>Quantity<input type="number" min="0.00000001" step="any" value={quantity} onChange={e => setQuantity(e.target.value)} /></label><label>Simulation reference price<input type="number" min="0.00000001" step="any" value={referencePrice} onChange={e => setReferencePrice(e.target.value)} /></label><button className="primary-button" disabled={busy || !modelId || !symbol.trim()} onClick={() => void submitOrder()}>Submit paper order</button></div>
    </section>}
    {summary && <section className="panel"><div className="panel-title"><div><h3>Risk operations</h3><p className="muted small">Kill switch overrides every model signal. Only administrators may deactivate it or repair ledger records.</p></div><ShieldCheck size={18} /></div>
      <div className="catalogue-form">{(canRiskOperate || canReconcile) && <label>Action reason<input value={reason} onChange={e => setReason(e.target.value)} /></label>}{canRiskOperate && <button className="secondary-button" disabled={busy || summary.kill_switch} onClick={() => void setKillSwitch(true)}>Activate kill switch</button>}{isAdmin && <button className="secondary-button" disabled={busy || !summary.kill_switch} onClick={() => void setKillSwitch(false)}>Deactivate kill switch</button>}{canReconcile && <button className="secondary-button" disabled={busy} onClick={() => void reconcile(false)}>Reconcile ledger</button>}{isAdmin && <button className="secondary-button" disabled={busy} onClick={() => void reconcile(true)}>Repair from fill history</button>}</div>
    </section>}
    {audit && <section className="panel"><div className="panel-title"><div><h3>Order, fill and audit history</h3><p className="muted small">Append-only order/fill/ledger history with auditable account actions.</p></div></div><div className="table-scroll"><table><thead><tr><th>Order ID</th><th>Client ID</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Status</th></tr></thead><tbody>{audit.orders.map((item, index) => <tr key={String(item.id ?? index)}><td className="mono">{String(item.id).slice(0, 10)}</td><td>{String(item.client_order_id)}</td><td>{String(item.symbol)}</td><td>{String(item.side)}</td><td>{String(item.quantity)}</td><td>{String(item.status)}</td></tr>)}</tbody></table></div><p className="inline-note"><Activity size={14} /> {audit.fills.length} fills · {audit.ledger.length} ledger entries · {audit.audit_events.length} audit events</p></section>}
    <div className="notice"><ShieldCheck size={18} /><p><strong>No live-money path exists.</strong> These endpoints only create internal paper orders and simulated fills from a user-entered reference price with configured fee/slippage assumptions. There is no live broker adapter or order endpoint.</p></div>
  </>;
}
