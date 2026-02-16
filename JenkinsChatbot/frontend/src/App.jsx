import React, { useState, useRef, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';
import axios from 'axios';
import { Terminal, Activity, Zap, Search, AlertCircle } from 'lucide-react';

function App() {
    const chatRef = useRef(null);
    const [systemStatus, setSystemStatus] = useState('checking'); // 'online', 'offline', 'checking'

    useEffect(() => {
        checkSystemHealth();
        const interval = setInterval(checkSystemHealth, 30000); // Check every 30s
        return () => clearInterval(interval);
    }, []);

    const checkSystemHealth = async () => {
        try {
            await axios.get('/api/jobs');
            setSystemStatus('online');
        } catch (e) {
            setSystemStatus('offline');
        }
    };

    // Handlers to trigger specific chat modes/inputs
    const handleQuickAction = (mode) => {
        if (!chatRef.current) return;

        let text = "";
        if (mode === 'TRIGGER') {
            text = "I want to trigger a job";
        } else if (mode === 'STATUS') {
            text = "Check the status of a job";
        }

        // We can directly call a method on the child if we expose it, 
        // or simpler: just pass a prop "initialMessage" or similar, 
        // but for a persistent chat, invoking a function is cleaner.
        // Let's use the exposed method approach via ref (need to update ChatInterface to forwardRef)
        // OR simpler: Just manual typing simulation or state lift.

        // Let's try the simplest: Set a state that ChatInterface listens to for *one-off* injection?
        // No, let's update ChatInterface to accept an imperative handle or just use the ref.

        if (chatRef.current.setInputText) {
            chatRef.current.setInputText(text);
            chatRef.current.focusInput();
        }
    };

    return (
        <div className="glass-container" style={{ width: '95%', maxWidth: '1200px', height: '90vh', display: 'flex', flexDirection: 'column', background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(255,255,255,0.05)' }}>

            {/* Header */}
            <header style={{
                marginBottom: '20px',
                borderBottom: '1px solid rgba(255,255,255,0.05)',
                paddingBottom: '15px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ background: 'rgba(0, 229, 255, 0.1)', padding: '8px', borderRadius: '12px' }}>
                        <Activity size={32} color="#00e5ff" />
                    </div>
                    <div>
                        <h1 style={{ margin: 0, fontSize: '1.8rem', fontWeight: '500', letterSpacing: '-0.02em', color: '#ffffff', fontFamily: "'Inter', sans-serif" }}>
                            Jenkins Chat Assistant
                        </h1>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    {systemStatus === 'online' && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', background: 'rgba(0, 230, 118, 0.1)', padding: '6px 12px', borderRadius: '20px', border: '1px solid rgba(0, 230, 118, 0.2)' }}>
                            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#00e676', boxShadow: '0 0 8px #00e676' }}></span>
                            System Online
                        </span>
                    )}
                    {systemStatus === 'offline' && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', background: 'rgba(255, 75, 75, 0.1)', padding: '6px 12px', borderRadius: '20px', border: '1px solid rgba(255, 75, 75, 0.2)', color: '#ff4b4b' }}>
                            <AlertCircle size={12} />
                            Backend Offline
                        </span>
                    )}
                    {systemStatus === 'checking' && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', background: 'rgba(255, 255, 255, 0.05)', padding: '6px 12px', borderRadius: '20px' }}>
                            Connecting...
                        </span>
                    )}
                </div>
            </header>

            {/* Main Content Area */}
            <div style={{ display: 'grid', gridTemplateRows: 'auto 1fr', gap: '20px', flex: 1, overflow: 'hidden' }}>

                {/* Quick Actions Row */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                    <button
                        className="glass-card hover-glow"
                        onClick={() => handleQuickAction('TRIGGER')}
                        style={{
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '15px',
                            border: '1px solid rgba(0, 229, 255, 0.2)',
                            background: 'linear-gradient(135deg, rgba(0,0,0,0.4) 0%, rgba(0, 229, 255, 0.05) 100%)'
                        }}
                    >
                        <div style={{ background: 'rgba(0, 229, 255, 0.2)', padding: '12px', borderRadius: '50%' }}>
                            <Zap size={24} color="#00e5ff" />
                        </div>
                        <div style={{ textAlign: 'left' }}>
                            <h3 style={{ margin: '0 0 4px 0', fontSize: '1.1rem' }}>Trigger Job</h3>
                            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Start a new build pipeline</p>
                        </div>
                    </button>

                    <button
                        className="glass-card hover-glow"
                        onClick={() => handleQuickAction('STATUS')}
                        style={{
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '15px',
                            border: '1px solid rgba(41, 121, 255, 0.2)',
                            background: 'linear-gradient(135deg, rgba(0,0,0,0.4) 0%, rgba(41, 121, 255, 0.05) 100%)'
                        }}
                    >
                        <div style={{ background: 'rgba(41, 121, 255, 0.2)', padding: '12px', borderRadius: '50%' }}>
                            <Search size={24} color="#2979ff" />
                        </div>
                        <div style={{ textAlign: 'left' }}>
                            <h3 style={{ margin: '0 0 4px 0', fontSize: '1.1rem' }}>Check Status</h3>
                            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>View running build details</p>
                        </div>
                    </button>
                </div>

                {/* Chat Interface */}
                <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden', height: '100%', background: 'rgba(0,0,0,0.3)' }}>
                    <ChatInterface ref={chatRef} />
                </div>

            </div>
        </div>
    );
}

export default App;
