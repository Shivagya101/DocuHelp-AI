import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import SyncPage from './components/SyncPage';
import ChatPage from './components/ChatPage';
import './dochelper.css';

function Navigation() {
  const location = useLocation();
  
  return (
    <header className="header">
      <div className="header-content" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="logo" style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <div className="logo-icon">📚</div>
          <div className="logo-text">
            <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 600, color: 'var(--text-primary)' }}>DocHelper AI</h1>
          </div>
        </div>
        
        <nav style={{ display: 'flex', gap: '20px' }}>
          <Link 
            to="/" 
            style={{ 
              textDecoration: 'none', 
              color: location.pathname === '/' ? 'var(--accent-primary)' : 'var(--text-secondary)',
              fontWeight: location.pathname === '/' ? 'bold' : 'normal',
              padding: '8px 12px',
              borderRadius: '8px',
              background: location.pathname === '/' ? 'var(--bg-glass-hover)' : 'transparent',
              transition: 'all 0.2s ease'
            }}
          >
            Manage Knowledge Base
          </Link>
          <Link 
            to="/chat" 
            style={{ 
              textDecoration: 'none', 
              color: location.pathname === '/chat' ? 'var(--accent-primary)' : 'var(--text-secondary)',
              fontWeight: location.pathname === '/chat' ? 'bold' : 'normal',
              padding: '8px 12px',
              borderRadius: '8px',
              background: location.pathname === '/chat' ? 'var(--bg-glass-hover)' : 'transparent',
              transition: 'all 0.2s ease'
            }}
          >
            Chat Interface
          </Link>
        </nav>
      </div>
    </header>
  );
}

function App() {
  return (
    <Router>
      <div className="app">
        {/* Background Orbs */}
        <div className="bg-orb bg-orb-1"></div>
        <div className="bg-orb bg-orb-2"></div>
        
        <Navigation />
        
        <main className="main-content" style={{ display: 'flex', flexDirection: 'column', minHeight: 'calc(100vh - 80px)' }}>
          <Routes>
            <Route path="/" element={<SyncPage />} />
            <Route path="/chat" element={<ChatPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
