import React, { useState, useRef, useEffect, forwardRef, useImperativeHandle } from 'react';
import axios from 'axios';
import { Send, Terminal, AlertTriangle, CheckCircle, HelpCircle, Activity, Trash2, Server, User } from 'lucide-react';

const ChatInterface = forwardRef(({ activeJob }, ref) => {
    const [messages, setMessages] = useState([
        { role: 'bot', text: 'Hello! I am your Jenkins AI Assistant. You can ask me to trigger jobs or check their status.', type: 'text' }
    ]);
    const [inputText, setInputText] = useState('');
    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);
    const [loading, setLoading] = useState(false);

    useImperativeHandle(ref, () => ({
        setInputText: (text) => setInputText(text),
        focusInput: () => inputRef.current?.focus()
    }));

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const clearChat = () => {
        setMessages([
            { role: 'bot', text: 'Hello! I am your Jenkins AI Assistant. You can ask me to trigger jobs or check their status.', type: 'text' }
        ]);
    };

    const sendImmediate = async (text, extraParams = null) => {
        const userMsg = { role: 'user', text: text, type: 'text' };
        setMessages(prev => [...prev, userMsg]);
        setLoading(true);

        // Get context from last bot message
        const botMsgs = messages.filter(m => m.role === 'bot');
        const lastBotMsg = botMsgs.length > 0 ? botMsgs[botMsgs.length - 1] : null;

        const context = {};
        if (lastBotMsg?.data?.job_name) context.current_job = lastBotMsg.data.job_name;

        // Combine existing params with any new ones being submitted
        const baseParams = lastBotMsg?.data?.parameters || {};
        context.parameters = extraParams ? { ...baseParams, ...extraParams } : baseParams;

        try {
            const res = await axios.post('/api/chat', { text, context });
            const data = res.data;
            const botMsg = {
                role: 'bot',
                text: data.response_text,
                type: data.action_required,
                data: data
            };
            setMessages(prev => [...prev, botMsg]);
        } catch (err) {
            setMessages(prev => [...prev, { role: 'bot', text: 'Error communicating with server.', type: 'error' }]);
        } finally {
            setLoading(false);
        }
    };

    const handleParamSubmit = (params) => {
        const updates = Object.entries(params).map(([k, v]) => `${k} is ${v}`).join(', ');
        const msg = `Here are the details: ${updates}`;
        sendImmediate(msg, params); // Pass actual params object as extraParams
    };

    const handleConfirm = async (jobName, params) => {
        const processId = Date.now();
        setMessages(prev => [...prev, {
            role: 'bot',
            type: 'TRIGGER_PROCESS',
            id: processId,
            status: 'pending',
            job_name: jobName,
            text: `Contacting Jenkins to trigger '${jobName}'...`
        }]);

        try {
            const res = await axios.post('/api/trigger', { job_name: jobName, params: params });
            const data = res.data;

            if (!data.triggered) {
                setMessages(prev => prev.map(m => m.id === processId ? { ...m, status: 'error', text: data.error || 'Trigger failed.' } : m));
                return;
            }

            const queueId = data.queue_item;
            setMessages(prev => prev.map(m => m.id === processId ? { ...m, text: 'Job in queue, waiting for build to start...' } : m));

            // 1. Poll for build number
            let buildNumber = null;
            for (let i = 0; i < 30; i++) { // Poll for 30s max
                await new Promise(r => setTimeout(r, 2000));
                const qRes = await axios.get(`/api/queue/${queueId}`);
                if (qRes.data.build_number) {
                    buildNumber = qRes.data.build_number;
                    break;
                }
                if (qRes.data.error) break;
            }

            if (!buildNumber) {
                setMessages(prev => prev.map(m => m.id === processId ? { ...m, status: 'error', text: 'Build failed to start in time.' } : m));
                return;
            }

            setMessages(prev => prev.map(m => m.id === processId ? {
                ...m,
                status: 'active',
                text: `Build #${buildNumber} started. Monitoring progress...`,
                data: { ...m.data, job_status: { job_url: `${data.job_url}${buildNumber}/` } }
            } : m));

            // 2. Poll for completion
            let finalStatus = null;
            for (let i = 0; i < 60; i++) { // Poll for 2 mins max
                await new Promise(r => setTimeout(r, 3000));
                const sRes = await axios.get(`/api/job/${jobName}/build/${buildNumber}`);
                const result = sRes.data.result;

                if (result) {
                    finalStatus = result;
                    break;
                }
            }

            const isSuccess = finalStatus === 'SUCCESS';
            setMessages(prev => prev.map(m => m.id === processId ? {
                ...m,
                status: isSuccess ? 'success' : 'error',
                text: isSuccess ? `Job completed successfully! (Build #${buildNumber})` : `Job finished with status: ${finalStatus || 'UNKNOWN'}`,
                data: { ...m.data, job_status: { job_url: `${data.job_url}${buildNumber}/`, result: finalStatus } }
            } : m));

        } catch (err) {
            setMessages(prev => prev.map(m => m.id === processId ? {
                ...m,
                status: 'error',
                text: 'Communication error during job monitoring.'
            } : m));
        }
    };

    const handleSend = async () => {
        if (!inputText.trim()) return;
        const text = inputText;
        setInputText('');
        await sendImmediate(text);
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
            {/* Chat Header Area */}
            <div style={{
                padding: '12px 20px',
                borderBottom: '1px solid rgba(255,255,255,0.05)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                background: 'rgba(0,0,0,0.15)'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem' }}>
                    <Terminal size={16} />
                    <span>Active Session</span>
                </div>
                <button
                    onClick={clearChat}
                    style={{
                        background: 'rgba(255, 75, 75, 0.1)',
                        border: '1px solid rgba(255, 75, 75, 0.2)',
                        color: '#ff4b4b',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '0.75rem',
                        padding: '6px 12px',
                        borderRadius: '6px',
                        transition: 'all 0.2s',
                        fontWeight: '500'
                    }}
                    onMouseEnter={(e) => e.target.style.background = 'rgba(255, 75, 75, 0.2)'}
                    onMouseLeave={(e) => e.target.style.background = 'rgba(255, 75, 75, 0.1)'}
                >
                    <Trash2 size={14} />
                    Clear Chat
                </button>
            </div>

            <div className="chat-container" style={{ flex: 1, overflowY: 'auto' }}>
                {messages.map((msg, idx) => (
                    <div key={idx} className={`chat-bubble ${msg.role}`} style={{ maxWidth: '85%' }}>
                        {['text', 'ASK_JOB_NAME', 'NONE', 'error'].includes(msg.type) && <p style={{ margin: 0 }}>{msg.text}</p>}

                        {msg.type === 'PROVIDE_PARAMS' && (
                            <div style={{ marginTop: '10px' }}>
                                <p style={{ margin: '0 0 10px 0' }}>{msg.text}</p>
                                <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '8px' }}>
                                    {msg.data.missing_parameters && msg.data.missing_parameters.map(param => (
                                        <div key={param} style={{ marginBottom: '8px' }}>
                                            <label style={{ display: 'block', fontSize: '0.8rem', opacity: 0.8, marginBottom: '4px' }}>{param}</label>
                                            <input
                                                className="glass-input"
                                                placeholder={`Enter ${param}`}
                                                id={`input-${idx}-${param}`}
                                                style={{ fontSize: '0.9rem', padding: '8px' }}
                                            />
                                        </div>
                                    ))}
                                    <button
                                        className="glass-button"
                                        style={{ width: '100%', marginTop: '5px', padding: '8px' }}
                                        onClick={() => {
                                            const params = {};
                                            if (msg.data.missing_parameters) {
                                                msg.data.missing_parameters.forEach(p => {
                                                    const el = document.getElementById(`input-${idx}-${p}`);
                                                    if (el && el.value) params[p] = el.value;
                                                });
                                                handleParamSubmit(params);
                                            }
                                        }}
                                    >
                                        Submit Parameters
                                    </button>
                                    {msg.data.job_doc_url && (
                                        <div style={{ marginTop: '10px', fontSize: '0.8rem', textAlign: 'center' }}>
                                            <a href={msg.data.job_doc_url} target="_blank" rel="noopener noreferrer" style={{ color: '#4facfe' }}>
                                                Read Documentation
                                            </a>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {msg.type === 'CONFIRM_TRIGGER' && (
                            <div style={{ marginTop: '8px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                                    <HelpCircle size={18} color="var(--primary-color)" />
                                    <strong style={{ color: 'var(--primary-color)', fontSize: '0.9rem' }}>Confirm Build</strong>
                                </div>
                                <p style={{ margin: '0 0 8px 0', fontSize: '0.85rem' }}>{msg.text}</p>
                                <div style={{ background: 'rgba(255,255,255,0.05)', padding: '10px', borderRadius: '8px', marginBottom: '8px' }}>
                                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>Parameters:</div>
                                    {Object.entries(msg.data.parameters || {}).map(([k, v]) => (
                                        <div key={k} style={{ fontSize: '0.85rem', marginBottom: '2px', display: 'flex', justifyContent: 'space-between' }}>
                                            <span style={{ opacity: 0.7 }}>{k}:</span>
                                            <span>{v}</span>
                                        </div>
                                    ))}
                                </div>
                                <div style={{ display: 'flex', gap: '8px' }}>
                                    <button
                                        className="glass-button"
                                        style={{ flex: 1, padding: '6px' }}
                                        onClick={() => handleConfirm(msg.data.job_name, msg.data.parameters)}
                                    >
                                        Confirm
                                    </button>
                                    <button
                                        className="glass-button"
                                        style={{ flex: 1, padding: '6px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.1)', color: 'white' }}
                                        onClick={() => setMessages(prev => [...prev, { role: 'bot', text: 'Trigger cancelled.', type: 'text' }])}
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        )}

                        {msg.type === 'AMBIGUOUS_JOB' && (
                            <div style={{ marginTop: '10px' }}>
                                <p style={{ margin: '0 0 12px 0' }}>{msg.text}</p>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                                    {msg.data.potential_jobs && msg.data.potential_jobs.map(job => (
                                        <button
                                            key={job}
                                            className="glass-button hover-glow"
                                            style={{
                                                padding: '8px 16px',
                                                fontSize: '0.85rem',
                                                background: 'rgba(255,255,255,0.05)',
                                                border: '1px solid rgba(255,255,255,0.1)',
                                                color: 'white',
                                                textTransform: 'none'
                                            }}
                                            onClick={() => sendImmediate(`Proceed with ${job}`)}
                                        >
                                            {job}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {msg.type === 'TRIGGER_PROCESS' && (
                            <div style={{ width: '100%', minWidth: '220px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', margin: '10px 0' }}>
                                    <div className={`connection-node ${msg.status === 'pending' ? 'active' : msg.status}`}>
                                        <User size={16} />
                                    </div>
                                    <div className="connection-line"></div>
                                    <div className={`connection-node ${msg.status === 'pending' ? 'active' : msg.status}`}>
                                        <Server size={16} />
                                    </div>
                                </div>
                                <p style={{ margin: '8px 0 0 0', textAlign: 'center', fontSize: '0.85rem' }} className={`status-text-${msg.status}`}>
                                    {msg.text}
                                </p>
                                {msg.status === 'success' && msg.data?.job_status && (
                                    <div style={{ marginTop: '10px', padding: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                                        <div style={{ fontSize: '0.8rem' }}>
                                            <a href={msg.data.job_status.job_url} target="_blank" rel="noopener noreferrer" style={{ color: '#00e5ff', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '5px' }}>
                                                <Terminal size={14} /> View Build in Jenkins
                                            </a>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {msg.type === 'SHOW_RESULT' && (
                            <div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                                    <CheckCircle size={20} color="#00e676" />
                                    <strong style={{ color: '#00e676' }}>Job Triggered!</strong>
                                </div>
                                <p style={{ margin: 0 }}>{msg.text}</p>
                                {msg.data.job_status && (
                                    <div style={{ marginTop: '8px', fontSize: '0.85rem', background: 'rgba(255,255,255,0.05)', padding: '8px', borderRadius: '4px' }}>
                                        <div>Job: {msg.data.job_name}</div>
                                        <div>Build URL: <a href={msg.data.job_status.job_url} target="_blank" style={{ color: '#4facfe' }}>Link</a></div>
                                    </div>
                                )}
                            </div>
                        )}

                        {msg.type === 'SHOW_STATUS' && (
                            <div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                                    <Activity size={18} color="#00f2fe" />
                                    <strong style={{ fontSize: '0.9rem' }}>Job Status Found</strong>
                                </div>
                                <p style={{ margin: 0, fontSize: '0.85rem' }}>{msg.text}</p>
                                {msg.data.job_status && (
                                    <div style={{ marginTop: 6, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '6px', fontSize: '0.85rem' }}>
                                        <div>Result:</div>
                                        <div><span className={`status-badge status-${msg.data.job_status.result === 'SUCCESS' ? 'success' : 'failure'}`} style={{ padding: '2px 6px', fontSize: '0.7rem' }}>
                                            {msg.data.job_status.result || 'RUNNING'}
                                        </span></div>
                                        <div>Build #:</div>
                                        <div>{msg.data.job_status.number}</div>
                                        <div>Duration:</div>
                                        <div>{msg.data.job_status.duration}ms</div>
                                        {msg.data.job_status.url && (
                                            <>
                                                <div>Link:</div>
                                                <div>
                                                    <a href={msg.data.job_status.url} target="_blank" rel="noopener noreferrer" style={{ color: '#4facfe' }}>
                                                        View Job
                                                    </a>
                                                </div>
                                            </>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}

                        {msg.type === 'error' && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ff4b4b' }}>
                                <AlertTriangle size={18} />
                                <span>{msg.text}</span>
                            </div>
                        )}

                    </div>
                ))}
                {loading && (
                    <div className="chat-bubble bot">
                        <div className="spinner"></div> Thinking...
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            <div style={{ padding: '15px', borderTop: '1px solid rgba(255,255,255,0.1)', background: 'rgba(0,0,0,0.2)' }}>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                    <input
                        type="text"
                        ref={inputRef}
                        className="glass-input"
                        placeholder="Type a command (e.g., 'Trigger create namespace in dev cluster')..."
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                        style={{ paddingRight: '50px' }}
                        disabled={loading}
                    />
                    <button
                        onClick={handleSend}
                        disabled={loading}
                        style={{
                            position: 'absolute',
                            right: '5px',
                            background: 'transparent',
                            border: 'none',
                            cursor: 'pointer',
                            color: 'var(--primary-color)',
                            display: 'flex',
                            alignItems: 'center',
                            height: '100%',
                            padding: '0 10px'
                        }}
                    >
                        <Send size={20} />
                    </button>
                </div>
            </div>
        </div>
    );
});

export default ChatInterface;
