import { useState } from 'react';
import { Activity, BarChart3, BrainCircuit, FileSearch, FlaskConical, LayoutDashboard, LogOut, ShieldCheck } from 'lucide-react';
import { AdminPage } from './pages/AdminPage';
import { ReinforcementLearningPage } from './pages/ReinforcementLearningPage';
import { LoginPage } from './pages/LoginPage';
import { OverviewPage } from './pages/OverviewPage';
import { ResearchWorkspacePage } from './pages/ResearchWorkspacePage';
import { ExperimentLabPage } from './pages/ExperimentLabPage';
import { StrategyBacktestPage } from './pages/StrategyBacktestPage';
import { ResearchIntelligencePage } from './pages/ResearchIntelligencePage';
import { ModelGovernancePage } from './pages/ModelGovernancePage';
import { PaperExecutionPage } from './pages/PaperExecutionPage';
import { FeedbackMonitoringPage } from './pages/FeedbackMonitoringPage';

type User = { id: string; full_name: string; email: string; roles: { key: string }[] };
type Page = 'overview' | 'research' | 'intelligence' | 'experiments' | 'backtests' | 'rl' | 'governance' | 'paper' | 'feedback' | 'admin';

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [page, setPage] = useState<Page>('overview');
  if (!token || !user) return <LoginPage onLogin={(nextToken, nextUser) => { setToken(nextToken); setUser(nextUser); }} />;

  const roleKeys = user.roles.map(role => role.key);
  const nav = [
    { id: 'overview' as const, label: 'Overview', icon: LayoutDashboard },
    { id: 'research' as const, label: 'Research workspace', icon: FileSearch },
    { id: 'intelligence' as const, label: 'Research intelligence', icon: BrainCircuit },
    { id: 'experiments' as const, label: 'Experiment lab', icon: FlaskConical },
    { id: 'backtests' as const, label: 'Strategy & backtests', icon: BarChart3 },
    { id: 'rl' as const, label: 'RL strategy lab', icon: BrainCircuit },
    { id: 'governance' as const, label: 'Model governance', icon: ShieldCheck },
    { id: 'paper' as const, label: 'Paper execution', icon: Activity },
    { id: 'feedback' as const, label: 'Feedback & monitoring', icon: BarChart3 },
    { id: 'admin' as const, label: 'Operations & administration', icon: ShieldCheck },
  ].filter(item => {
    if (item.id === 'governance') return ['ADMIN', 'RISK_REVIEWER', 'QUANT_RESEARCHER', 'PORTFOLIO_ANALYST', 'READ_ONLY_VIEWER'].some(role => roleKeys.includes(role));
    if (item.id === 'paper') return ['ADMIN', 'PORTFOLIO_ANALYST', 'RISK_REVIEWER', 'READ_ONLY_VIEWER'].some(role => roleKeys.includes(role));
    if (item.id === 'admin') return ['ADMIN', 'RISK_REVIEWER', 'PORTFOLIO_ANALYST', 'READ_ONLY_VIEWER'].some(role => roleKeys.includes(role));
    return true;
  });
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="sidebar-brand"><div className="brand-mark"><Activity size={19} /></div><div><strong>FinSight</strong><small>RESEARCHOPS</small></div></div>
      <p className="nav-label">WORKSPACE</p>
      <nav>{nav.map(item => { const Icon = item.icon; return <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => setPage(item.id)}><Icon size={17} />{item.label}</button>; })}</nav>
      <div className="sidebar-bottom"><div className="user-chip"><div className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</div><div><strong>{user.full_name}</strong><small>{user.roles[0]?.key.replaceAll('_', ' ')}</small></div></div><button className="logout-button" onClick={() => { setToken(null); setUser(null); }}><LogOut size={15} /> Sign out</button></div>
    </aside>
    <main className="main-content"><header className="topbar"><div><span className="breadcrumb">FinSight / {nav.find(n => n.id === page)?.label}</span></div><div className="topbar-right"><span className="environment"><span /> LOCAL ENVIRONMENT</span><span className="avatar small-avatar">{user.full_name.slice(0, 1).toUpperCase()}</span></div></header>
      <div className="page-content">{page === 'overview' && <OverviewPage token={token} />}{page === 'research' && <ResearchWorkspacePage token={token} />}{page === 'intelligence' && <ResearchIntelligencePage token={token} roles={user.roles.map(role => role.key)} />}{page === 'experiments' && <ExperimentLabPage token={token} userId={user.id} roles={user.roles.map(role => role.key)} />}{page === 'backtests' && <StrategyBacktestPage token={token} />}{page === 'rl' && <ReinforcementLearningPage token={token} roles={user.roles.map(role => role.key)} />}{page === 'governance' && <ModelGovernancePage token={token} userId={user.id} roles={user.roles.map(role => role.key)} />}{page === 'paper' && <PaperExecutionPage token={token} roles={user.roles.map(role => role.key)} />}{page === 'feedback' && <FeedbackMonitoringPage token={token} roles={user.roles.map(role => role.key)} />}{page === 'admin' && <AdminPage token={token} />}</div>
      <footer>FinSight ResearchOps <span>Research and paper simulation only · No live trading</span></footer>
    </main>
  </div>;
}
