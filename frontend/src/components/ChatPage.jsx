import { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

const API_BASE =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : import.meta.env.VITE_API_URL;

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatMarkdown(text, citations = []) {
  if (!text) return '';

  const codeBlocks = [];
  let formatted = text.replace(/```([\s\S]*?)```/g, (match, code) => {
    codeBlocks.push(code);
    return `___CODE_BLOCK_${codeBlocks.length - 1}___`;
  });

  formatted = escapeHtml(formatted)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/- (.*?)(?:\n|$)/g, '• $1<br/>')
    .replace(/\n/g, '<br/>')
    .replace(/`(.*?)`/g, '<code>$1</code>');

  formatted = formatted.replace(/___CODE_BLOCK_(\d+)___/g, (match, index) => {
    let rawCode = codeBlocks[index];
    rawCode = rawCode.replace(/^[a-z0-9]+\n/i, '');
    const safeCode = escapeHtml(rawCode);
    return `<div class="code-block-container"><button class="copy-btn">Copy</button><pre><code>${safeCode}</code></pre></div>`;
  });

  if (citations && citations.length > 0) {
    formatted = formatted.replace(/\[(\d+)\]/g, (match, p1) => {
      const index = parseInt(p1, 10) - 1;
      if (index >= 0 && index < citations.length) {
        return `<a href="${citations[index]}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-primary); text-decoration: underline; font-weight: bold; font-size: 0.9em; padding: 0 2px;">[${p1}]</a>`;
      }
      return match;
    });
  }
  return formatted;
}

export default function ChatPage() {
  const [searchParams] = useSearchParams();
  const initialUrl = searchParams.get('url') || '';
  
  const [url, setUrl] = useState(initialUrl);
  const [activeUrl, setActiveUrl] = useState(''); // The URL we are currently chatting with
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  const messagesEndRef = useRef(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Handle copy button clicks for dynamically injected HTML
  useEffect(() => {
    const handleCopyClick = async (e) => {
      if (e.target && e.target.classList.contains('copy-btn')) {
        const preElement = e.target.nextElementSibling;
        if (preElement && preElement.tagName === 'PRE') {
          const codeToCopy = preElement.textContent;
          try {
            await navigator.clipboard.writeText(codeToCopy);
            const originalText = e.target.textContent;
            e.target.textContent = 'Copied!';
            e.target.style.background = '#10b981'; // Success green
            e.target.style.color = 'white';
            
            setTimeout(() => {
              e.target.textContent = originalText;
              e.target.style.background = '';
              e.target.style.color = '';
            }, 2000);
          } catch (err) {
            console.error('Failed to copy text: ', err);
          }
        }
      }
    };

    document.addEventListener('click', handleCopyClick);
    return () => {
      document.removeEventListener('click', handleCopyClick);
    };
  }, []);

  // Connect to the KB when the component mounts if a URL is provided
  useEffect(() => {
    if (initialUrl) {
      handleConnect(initialUrl);
    }
  }, [initialUrl]);

  async function handleConnect(targetUrl = url) {
    if (!targetUrl.trim()) return;
    setLoading(true);
    setError('');
    
    try {
      // 1. Check if the URL is in the database using /analyze
      const res = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: targetUrl })
      });
      
      const data = await res.json();
      
      if (data.status === 'indexed') {
        setActiveUrl(targetUrl);
        setMessages([{
          role: 'bot',
          text: `Connected to **${targetUrl}**. Ask me anything about this knowledge base!`
        }]);
      } else {
        // Not in database or currently processing
        setError(`No URL exists or it is still processing. Please go back to the Sync Page to add it.`);
        setActiveUrl('');
        setMessages([]);
      }
    } catch (err) {
      setError("Failed to connect: " + err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSend(e) {
    if (e) e.preventDefault();
    if (!input.trim() || loading || !activeUrl) return;

    const question = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text: question }]);
    setLoading(true);

    try {
      const historyPayload = messages.slice(1).slice(-6).map(m => ({
        role: m.role === 'bot' ? 'assistant' : 'user',
        content: m.text
      }));

      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: activeUrl, question, history: historyPayload })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to fetch response");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');

      let done = false;
      let buffer = '';
      let initializedBotMessage = false;

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmedLine = line.trim();
            if (trimmedLine.startsWith('data: ')) {
              const dataStr = trimmedLine.substring(6);
              try {
                const parsed = JSON.parse(dataStr);

                if (!initializedBotMessage && (parsed.type === 'citations' || parsed.type === 'chunk')) {
                  setLoading(false);
                  setMessages(prev => [...prev, { role: 'bot', text: '', citations: [] }]);
                  initializedBotMessage = true;
                }

                if (parsed.type === 'citations') {
                  setMessages(prev => {
                    const newMsgs = [...prev];
                    const lastMsg = { ...newMsgs[newMsgs.length - 1] };
                    lastMsg.citations = parsed.citations;
                    newMsgs[newMsgs.length - 1] = lastMsg;
                    return newMsgs;
                  });
                } else if (parsed.type === 'chunk') {
                  setMessages(prev => {
                    const newMsgs = [...prev];
                    const lastMsg = { ...newMsgs[newMsgs.length - 1] };
                    lastMsg.text += parsed.text;
                    newMsgs[newMsgs.length - 1] = lastMsg;
                    return newMsgs;
                  });
                } else if (parsed.type === 'done') {
                  done = true;
                }
              } catch (e) {
                // Ignore parse errors from partial chunks
              }
            }
          }
        }
      }
    } catch (e) {
      setMessages(prev => {
        const newMsgs = [...prev];
        if (newMsgs.length > 0 && newMsgs[newMsgs.length - 1].role === 'bot') {
          newMsgs[newMsgs.length - 1].text = `Sorry, I couldn't answer that. ${e.message}`;
        }
        return newMsgs;
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
      
      {!activeUrl ? (
        <div className="step-card" style={{ maxWidth: '600px', margin: '40px auto' }}>
          <div className="step-header">
            <h2 className="step-title">Connect to Chat</h2>
          </div>
          <p className="step-description">Enter a URL to chat with its knowledge base.</p>
          <div className="input-group">
            <div className="input-wrapper">
              <span className="input-icon">🔗</span>
              <input
                type="url"
                className="text-input"
                placeholder="https://docs.example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
            <button onClick={() => handleConnect(url)} className="btn btn-primary" disabled={loading}>
              {loading ? 'Connecting...' : 'Connect'}
            </button>
          </div>
          {error && <div className="status-message error" style={{ marginTop: '20px' }}>{error}</div>}
        </div>
      ) : (
        <div className="glass-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', maxWidth: '1000px', margin: '20px auto', width: '100%', height: 'calc(100vh - 120px)' }}>
          <div className="repo-info" style={{ margin: 0, borderRadius: '16px 16px 0 0', borderBottom: '1px solid var(--border-glass)' }}>
            <div className="repo-info-icon">📑</div>
            <div className="repo-info-text">
              <h3>Workspace Active</h3>
              <p>{activeUrl}</p>
            </div>
            <button onClick={() => setActiveUrl('')} className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '0.85rem' }}>
              Disconnect
            </button>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {messages.map((msg, i) => (
              <div key={i} style={{ display: 'flex', gap: '15px', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
                <div style={{
                  width: '40px', height: '40px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.2rem',
                  background: msg.role === 'user' ? 'var(--accent-gradient)' : 'var(--bg-tertiary)',
                  border: '1px solid var(--border-glass)', flexShrink: 0
                }}>
                  {msg.role === 'user' ? '👤' : '🤖'}
                </div>
                <div style={{
                  background: msg.role === 'user' ? 'var(--bg-glass-hover)' : 'var(--bg-tertiary)',
                  padding: '16px', borderRadius: '12px', border: '1px solid var(--border-glass)',
                  maxWidth: '80%', color: 'var(--text-primary)', fontSize: '0.95rem'
                }}>
                  <div className="result-code" dangerouslySetInnerHTML={{ __html: formatMarkdown(msg.text, msg.citations) }} />
                </div>
              </div>
            ))}
            {loading && (
              <div style={{ display: 'flex', gap: '15px' }}>
                <div style={{ width: '40px', height: '40px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-tertiary)', border: '1px solid var(--border-glass)' }}>🤖</div>
                <div style={{ padding: '16px', borderRadius: '12px', background: 'var(--bg-tertiary)', border: '1px solid var(--border-glass)' }}>
                  <div className="spinner"></div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSend} style={{ padding: '20px', borderTop: '1px solid var(--border-glass)', background: 'var(--bg-tertiary)', display: 'flex', gap: '10px' }}>
            <div className="input-wrapper" style={{ flex: 1 }}>
              <input
                type="text"
                className="text-input"
                style={{ paddingLeft: '20px' }}
                placeholder="Ask a question about the docs..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={loading || !input.trim()}>
              Send
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
