import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const API_BASE =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : import.meta.env.VITE_API_URL;

export default function SyncPage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState('');
  const [appState, setAppState] = useState('landing'); // 'landing', 'analyzing', 'not_found', 'processing', 'indexed'
  const [error, setError] = useState('');
  
  const [syncedLinks, setSyncedLinks] = useState([]);
  const [unsyncedLinks, setUnsyncedLinks] = useState([]);
  const [activeTab, setActiveTab] = useState('synced'); // 'synced' or 'unsynced'
  
  const [selectedLinks, setSelectedLinks] = useState(new Set());
  const [loading, setLoading] = useState(false);

  async function handleAnalyze(e) {
    if (e) e.preventDefault();
    if (!url.trim()) return;

    setAppState('analyzing');
    setError('');

    try {
      const res = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });

      if (!res.ok) throw new Error("Failed to reach server");
      const data = await res.json();

      if (data.status === 'processing') {
        setAppState('processing');
      } else if (data.status === 'not_found') {
        setAppState('not_found');
      } else if (data.status === 'indexed') {
        setSyncedLinks(data.synced_links || []);
        setUnsyncedLinks(data.unsynced_links || []);
        setSelectedLinks(new Set());
        setActiveTab('synced');
        setAppState('indexed');
      }
    } catch (err) {
      setError("Analysis failed: " + err.message);
      setAppState('landing');
    }
  }

  const toggleLinkSelection = (link) => {
    const newSet = new Set(selectedLinks);
    if (newSet.has(link)) {
      newSet.delete(link);
    } else {
      if (newSet.size >= 5) {
        alert("You can only select a maximum of 5 URLs per bulk sync request.");
        return;
      }
      newSet.add(link);
    }
    setSelectedLinks(newSet);
  };

  async function handleSyncBulk(urlsToSync) {
    if (!urlsToSync || urlsToSync.length === 0) return;
    
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/sync_bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: urlsToSync })
      });
      
      if (!res.ok) throw new Error("Failed to queue links");
      
      alert(`Successfully queued ${urlsToSync.length} pages for syncing! They will be available in chat shortly.`);
      if (appState === 'indexed') {
        setSelectedLinks(new Set());
        // Move them optimistically to avoid confusion, or let user refresh
      } else if (appState === 'not_found') {
        setAppState('processing');
      }
    } catch (err) {
      alert("Failed to sync: " + err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
      {appState === 'landing' && (
        <div className="step-card" style={{ maxWidth: '600px', margin: '40px auto' }}>
          <div className="step-header">
            <div className="step-number">1</div>
            <h2 className="step-title">Connect Knowledge Base</h2>
          </div>
          <p className="step-description">
            Paste the URL of any documentation to check if it's in the AI's knowledge base. 
            If not, we will index it for you!
          </p>
          <form onSubmit={handleAnalyze} className="input-group">
            <div className="input-wrapper">
              <span className="input-icon">🔗</span>
              <input
                type="url"
                className="text-input"
                placeholder="https://docs.example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn btn-primary">
              Check URL
            </button>
          </form>
          {error && <div className="status-message error" style={{ marginTop: '20px' }}>{error}</div>}
        </div>
      )}

      {appState === 'analyzing' && (
        <div className="step-card" style={{ maxWidth: '600px', margin: '40px auto', textAlign: 'center' }}>
          <div className="spinner" style={{ margin: '0 auto 20px', width: '40px', height: '40px', borderColor: 'rgba(139, 92, 246, 0.3)', borderTopColor: '#8b5cf6' }}></div>
          <h2 className="step-title">Checking Knowledge Base</h2>
          <p className="step-description">Looking for existing data. Hang tight...</p>
        </div>
      )}

      {appState === 'processing' && (
        <div className="step-card" style={{ maxWidth: '600px', margin: '40px auto', textAlign: 'center' }}>
          <div className="spinner" style={{ margin: '0 auto 20px', width: '40px', height: '40px', borderColor: 'rgba(59, 130, 246, 0.3)', borderTopColor: '#3b82f6' }}></div>
          <h2 className="step-title">Indexing in Progress</h2>
          <p className="step-description">The AI workers are currently processing this URL in the background. Please wait...</p>
          <button onClick={() => handleAnalyze()} className="btn btn-secondary" style={{ marginTop: '20px' }}>
            Refresh Status
          </button>
        </div>
      )}

      {appState === 'not_found' && (
        <div className="step-card" style={{ maxWidth: '600px', margin: '40px auto', textAlign: 'center' }}>
          <div style={{ fontSize: '48px', marginBottom: '20px' }}>🔍</div>
          <h2 className="step-title">URL Not Found</h2>
          <p className="step-description">This URL is not currently in the AI Knowledge Base.</p>
          <button 
            onClick={() => handleSyncBulk([url])} 
            disabled={loading}
            className="btn btn-primary"
            style={{ width: '100%', marginTop: '20px', padding: '15px', fontSize: '1.1rem' }}
          >
            {loading ? 'Queuing...' : 'Scrape & Index This Page'}
          </button>
          <button onClick={() => setAppState('landing')} className="btn btn-secondary" style={{ marginTop: '10px' }}>
            Go Back
          </button>
        </div>
      )}

      {appState === 'indexed' && (
        <div className="step-card" style={{ maxWidth: '800px', margin: '40px auto' }}>
          <div className="step-header" style={{ justifyContent: 'space-between', display: 'flex', alignItems: 'center' }}>
            <div>
              <div className="step-number">2</div>
              <h2 className="step-title">Knowledge Base Dashboard</h2>
            </div>
            <button onClick={() => navigate(`/chat?url=${encodeURIComponent(url)}`)} className="btn btn-primary" style={{ padding: '12px 24px', fontSize: '1.1rem', background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)' }}>
              💬 Start Chatting Now
            </button>
          </div>
          <p className="step-description">
            We successfully found <strong>{url}</strong> in the database.
          </p>
          
          <div style={{ display: 'flex', gap: '10px', marginTop: '20px', borderBottom: '1px solid var(--border-glass)', paddingBottom: '10px' }}>
            <button 
              onClick={() => setActiveTab('synced')}
              style={{
                padding: '8px 16px',
                background: activeTab === 'synced' ? 'var(--bg-secondary)' : 'transparent',
                border: '1px solid',
                borderColor: activeTab === 'synced' ? 'var(--border-glass)' : 'transparent',
                borderRadius: '8px',
                color: activeTab === 'synced' ? 'var(--text-primary)' : 'var(--text-secondary)',
                cursor: 'pointer'
              }}
            >
              ✅ Synced Pages ({syncedLinks.length})
            </button>
            <button 
              onClick={() => setActiveTab('unsynced')}
              style={{
                padding: '8px 16px',
                background: activeTab === 'unsynced' ? 'var(--bg-secondary)' : 'transparent',
                border: '1px solid',
                borderColor: activeTab === 'unsynced' ? 'var(--border-glass)' : 'transparent',
                borderRadius: '8px',
                color: activeTab === 'unsynced' ? 'var(--text-primary)' : 'var(--text-secondary)',
                cursor: 'pointer'
              }}
            >
              🔲 Available to Sync ({unsyncedLinks.length})
            </button>
          </div>

          <div style={{ maxHeight: '300px', overflowY: 'auto', margin: '10px 0 20px', border: '1px solid var(--border-glass)', borderRadius: '8px', padding: '10px', background: 'var(--bg-tertiary)' }}>
            {activeTab === 'synced' && (
              syncedLinks.length === 0 ? (
                <p style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No internal links have been synced yet.</p>
              ) : (
                syncedLinks.map((link, idx) => (
                  <div key={idx} style={{ display: 'flex', alignItems: 'center', padding: '8px', borderBottom: '1px solid var(--border-glass)' }}>
                    <span style={{ marginRight: '10px' }}>✅</span>
                    <span style={{ color: 'var(--text-primary)', wordBreak: 'break-all' }}>{link}</span>
                  </div>
                ))
              )
            )}
            
            {activeTab === 'unsynced' && (
              unsyncedLinks.length === 0 ? (
                <p style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No new internal links available to sync.</p>
              ) : (
                unsyncedLinks.map((link, idx) => (
                  <div key={idx} style={{ display: 'flex', alignItems: 'center', padding: '8px', borderBottom: '1px solid var(--border-glass)' }}>
                    <input 
                      type="checkbox" 
                      id={`link-${idx}`} 
                      checked={selectedLinks.has(link)}
                      onChange={() => toggleLinkSelection(link)}
                      disabled={selectedLinks.size >= 5 && !selectedLinks.has(link)}
                      style={{ marginRight: '10px', cursor: (selectedLinks.size >= 5 && !selectedLinks.has(link)) ? 'not-allowed' : 'pointer' }}
                    />
                    <label htmlFor={`link-${idx}`} style={{ cursor: 'pointer', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                      {link}
                    </label>
                  </div>
                ))
              )
            )}
          </div>

          {activeTab === 'unsynced' && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-secondary)' }}>
                {selectedLinks.size} / 5 links selected
              </span>
              <button 
                onClick={() => handleSyncBulk(Array.from(selectedLinks))} 
                disabled={loading || selectedLinks.size === 0}
                className="btn btn-primary"
              >
                {loading ? 'Queueing...' : 'Sync Selected Pages'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
