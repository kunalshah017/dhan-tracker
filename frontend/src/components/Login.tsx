import { useState, FormEvent } from 'react';
import { useAuthStore } from '../store';

export function Login() {
    const [password, setPassword] = useState('');
    const [error, setError] = useState(false);
    const [loading, setLoading] = useState(false);
    const login = useAuthStore((state) => state.login);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setError(false);
        setLoading(true);

        try {
            await login(password);
        } catch {
            setError(true);
            setPassword('');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-screen">
            <form className="login-box" onSubmit={handleSubmit}>
                <h1>🔐 Dhan Tracker</h1>
                <input
                    type="password"
                    placeholder="Enter password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoFocus
                />
                {error && <p className="login-error">Invalid password</p>}
                <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%' }}>
                    {loading ? 'Logging in...' : 'Login'}
                </button>
            </form>
        </div>
    );
}
