import { useState, type FormEvent } from 'react';
import { Activity, ArrowRight, LockKeyhole } from 'lucide-react';
import { apiRequest } from '../lib/api';

type LoginResult = { access_token: string; user: { id: string; full_name: string; email: string; roles: { key: string }[] } };

export function LoginPage({ onLogin }: { onLogin: (token: string, user: LoginResult['user']) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const form = new URLSearchParams({ username: email, password });
      const result = await apiRequest<LoginResult>('/auth/login', { method: 'POST', body: form });
      onLogin(result.access_token, result.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-wrap">
      <section className="login-card">
        <div className="brand-mark"><Activity size={22} /></div>
        <p className="eyebrow">RESEARCH • QUANT • GOVERNANCE</p>
        <h1>FinSight <span>ResearchOps</span></h1>
        <p className="muted">A traceable workspace for financial research and quantitative experimentation.</p>
        <form onSubmit={submit} className="login-form">
          <label>Email address<input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="analyst@company.com" /></label>
          <label>Password<input type="password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Your password" /></label>
          {error && <p className="error-banner">{error}</p>}
          <button className="primary-button" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'} <ArrowRight size={16} /></button>
        </form>
        <div className="secure-note"><LockKeyhole size={14} /> Access is protected by backend authentication and role permissions.</div>
      </section>
    </main>
  );
}
