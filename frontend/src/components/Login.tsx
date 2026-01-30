import { useState, FormEvent } from 'react';
import { useAuthStore } from '../store';

export function Login() {
    const [password, setPassword] = useState('');
    const [apiKey, setApiKey] = useState('');
    const [showApiKeyInput, setShowApiKeyInput] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [apiKeyLoading, setApiKeyLoading] = useState(false);
    const login = useAuthStore((state) => state.login);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            await login(password);
        } catch {
            setError('Invalid password');
            setPassword('');
        } finally {
            setLoading(false);
        }
    };

    const handleApiKeySubmit = async (e: FormEvent) => {
        e.preventDefault();
        if (!apiKey.trim()) {
            setError('Please enter your API key');
            return;
        }

        setError('');
        setApiKeyLoading(true);

        try {
            const response = await fetch('/api/token/update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Password': password,
                },
                body: JSON.stringify({ access_token: apiKey.trim() }),
            });

            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.detail || 'Failed to update API key');
            }

            // API key updated, now try to login again
            setShowApiKeyInput(false);
            setApiKey('');
            await login(password);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to update API key');
        } finally {
            setApiKeyLoading(false);
        }
    };

    return (
        <div className="login-screen">
            {!showApiKeyInput ? (
                <form className="login-box" onSubmit={handleSubmit}>
                    <h1>🔐 Dhan Tracker</h1>
                    <input
                        type="password"
                        placeholder="Enter password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoFocus
                    />
                    {error && <p className="login-error">{error}</p>}
                    <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%' }}>
                        {loading ? 'Logging in...' : 'Login'}
                    </button>
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setShowApiKeyInput(true)}
                        style={{ width: '100%', marginTop: '0.75rem' }}
                    >
                        🔑 Update API Key
                    </button>
                </form>
            ) : (
                <form className="login-box" onSubmit={handleApiKeySubmit}>
                    <h1>🔑 Update API Key</h1>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.875rem' }}>
                        Enter your new Dhan API access token from the{' '}
                        <a href="https://api.dhan.co" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-blue)' }}>
                            Dhan API Portal
                        </a>
                    </p>
                    <input
                        type="password"
                        placeholder="App password (required)"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        style={{ marginBottom: '0.5rem' }}
                    />
                    <input
                        type="text"
                        placeholder="Paste your new API access token"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        autoFocus
                    />
                    {error && <p className="login-error">{error}</p>}
                    <button className="btn btn-primary" type="submit" disabled={apiKeyLoading} style={{ width: '100%' }}>
                        {apiKeyLoading ? 'Updating...' : 'Update API Key'}
                    </button>
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => {
                            setShowApiKeyInput(false);
                            setApiKey('');
                            setError('');
                        }}
                        style={{ width: '100%', marginTop: '0.75rem' }}
                    >
                        ← Back to Login
                    </button>
                </form>
            )}
        </div>
    );
}
