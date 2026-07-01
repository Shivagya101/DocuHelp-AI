import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const API_BASE =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "https://mehtaprince-rag.hf.space";

export default function SyncPage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState('');
  const [appState, setAppState] = useState('landing'); // 'landing', 'analyzing', 'sync'
  const [error, setError] = useState('');
  const [internalLinks, setInternalLinks] = useState([]);
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
        setError("This URL is currently being fetched! Please wait 15 seconds and try again to see its internal links.");
        setAppState('landing');
      } else {
        // Cached! Show the Sync UI
        setInternalLinks(data.internal_links || []);
        setSelectedLinks(new Set());
        setAppState('sync');
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

  async function handleSyncBulk() {
    if (selectedLinks.size === 0) return;
    
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/sync_bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: Array.from(selectedLinks) })
      });
      
      if (!res.ok) throw new Error("Failed to queue links");
      
      alert(`Successfully queued ${selectedLinks.size} pages for syncing! They will be available in chat shortly.`);
      setSelectedLinks(new Set());
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
          <p className="step-description">Looking for existing data and fetching new links. Hang tight...</p>
        </div>
      )}

      {appState === 'sync' && (
        <div className="step-card" style={{ maxWidth: '800px', margin: '40px auto' }}>
          <div className="step-header" style={{ justifyContent: 'space-between', display: 'flex', alignItems: 'center' }}>
            <div>
              <div className="step-number">2</div>
              <h2 className="step-title">Manage Knowledge Base</h2>
            </div>
            <button onClick={() => navigate(`/chat?url=${encodeURIComponent(url)}`)} className="btn btn-secondary">
              Go to Chat
            </button>
          </div>
          <p className="step-description">
            We successfully loaded <strong>{url}</strong>. Here are the internal links we found. Select any additional pages you want to index into the AI's knowledge base.
          </p>
          
          <div style={{ maxHeight: '300px', overflowY: 'auto', margin: '20px 0', border: '1px solid var(--border-glass)', borderRadius: '8px', padding: '10px', background: 'var(--bg-tertiary)' }}>
            {internalLinks.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No internal links found on this page.</p>
            ) : (
              internalLinks.map((link, idx) => (
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
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>
              {selectedLinks.size} / 5 links selected
            </span>
            <button 
              onClick={handleSyncBulk} 
              disabled={loading || selectedLinks.size === 0}
              className="btn btn-primary"
            >
              {loading ? 'Queueing...' : 'Sync Selected Pages'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
