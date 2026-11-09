import { BrainCircuit, ShieldCheck } from 'lucide-react';
import { RLEvaluationPanel } from '../components/RLEvaluationPanel';

export function ReinforcementLearningPage({ token, roles }: { token: string; roles: string[] }) {
  return <>
    <div className="page-heading">
      <div>
        <p className="eyebrow">PHASE 4 · REINFORCEMENT LEARNING</p>
        <h2>RL Strategy Lab</h2>
        <p className="muted">Train PPO/SAC policies on historical data, evaluate them out-of-sample and compare same-lineage runs before governance review.</p>
      </div>
      <span className="status-pill"><BrainCircuit size={14} /> Research simulation</span>
    </div>
    <section className="notice">
      <ShieldCheck size={18} />
      <p><strong>Research-only policy boundary.</strong> RL policies are evaluated on historical snapshots with fees and slippage. Training does not create orders. A successful evaluation must still pass deterministic risk review, independent human approval and administrator promotion before it can be selected by the separate paper broker.</p>
    </section>
    <RLEvaluationPanel token={token} roles={roles} />
  </>;
}
