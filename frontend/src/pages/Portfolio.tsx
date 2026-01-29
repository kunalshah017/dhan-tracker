import { Link } from 'react-router-dom';
import { useAuthStore } from '../store';
import { useHoldings, useOrders, useProtectionStatus, useSchedulerStatus, useRunAmoProtection, useCancelAllOrders } from '../hooks';
import { formatCurrency } from '../utils';
import { useToast, ToastContainer } from '../components/Toast';

export function Portfolio() {
    const logout = useAuthStore((state) => state.logout);
    const toast = useToast();

    const { data: holdingsData, isLoading: holdingsLoading, refetch: refetchHoldings } = useHoldings();
    const { data: ordersData, isLoading: ordersLoading, refetch: refetchOrders } = useOrders();
    const { data: protectionData, refetch: refetchProtection } = useProtectionStatus();
    const { data: schedulerData, refetch: refetchScheduler } = useSchedulerStatus();

    const runAmoMutation = useRunAmoProtection();
    const cancelMutation = useCancelAllOrders();

    const refreshAll = () => {
        refetchHoldings();
        refetchOrders();
        refetchProtection();
        refetchScheduler();
    };

    const handleRunAmo = async () => {
        try {
            const result = await runAmoMutation.mutateAsync();
            toast.success(result.message || 'Super Order protection placed');
        } catch (err) {
            toast.error(err instanceof Error ? err.message : 'Failed to run protection');
        }
    };

    const handleCancelAll = async () => {
        try {
            const result = await cancelMutation.mutateAsync();
            toast.success(result.message || 'All orders cancelled');
        } catch (err) {
            toast.error(err instanceof Error ? err.message : 'Failed to cancel orders');
        }
    };

    // Calculate totals
    const holdings = holdingsData?.holdings || [];
    const orders = ordersData?.orders || [];
    const protection = protectionData;
    const scheduler = schedulerData;

    // Use pre-calculated totals from API, fallback to manual calculation
    const totalInvested = holdingsData?.total_invested ?? holdings.reduce((sum, h) => sum + (h.invested || 0), 0);
    const totalCurrent = holdingsData?.total_current ?? holdings.reduce((sum, h) => sum + (h.current_value || 0), 0);
    const totalPnL = holdingsData?.total_pnl ?? (totalCurrent - totalInvested);
    const pnlPercent = holdingsData?.total_pnl_percent ?? (totalInvested > 0 ? (totalPnL / totalInvested) * 100 : 0);

    return (
        <div className="dashboard">
            <header className="header">
                <h1>📊 Portfolio Dashboard</h1>
                <div className="header-actions">
                    <Link to="/etf" className="btn-link">ETF Recommendations →</Link>
                    <button className="btn btn-primary" onClick={refreshAll}>Refresh</button>
                    <button className="btn btn-secondary" onClick={logout}>Logout</button>
                </div>
            </header>

            {/* Stats */}
            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-label">Total Invested</div>
                    <div className="stat-value">{formatCurrency(totalInvested)}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Current Value</div>
                    <div className="stat-value">{formatCurrency(totalCurrent)}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Total P&L</div>
                    <div className={`stat-value ${totalPnL >= 0 ? 'positive' : 'negative'}`}>
                        {formatCurrency(totalPnL)} ({(pnlPercent || 0).toFixed(2)}%)
                    </div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Protected</div>
                    <div className="stat-value">{protection?.protected_count || 0} / {protection?.total_holdings || 0}</div>
                </div>
            </div>

            {/* Holdings Table */}
            <div className="card">
                <div className="card-header">
                    <h2 className="card-title">Holdings ({holdings.length})</h2>
                </div>
                <div className="table-container">
                    {holdingsLoading ? (
                        <p className="loading">Loading holdings...</p>
                    ) : holdings.length === 0 ? (
                        <p className="loading">No holdings found</p>
                    ) : (
                        <table>
                            <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th className="text-right">Qty</th>
                                    <th className="text-right">Avg Cost</th>
                                    <th className="text-right">LTP</th>
                                    <th className="text-right">Current Value</th>
                                    <th className="text-right">P&L</th>
                                </tr>
                            </thead>
                            <tbody>
                                {holdings.map((h) => {
                                    return (
                                        <tr key={h.symbol}>
                                            <td><strong>{h.symbol}</strong></td>
                                            <td className="text-right">{h.quantity}</td>
                                            <td className="text-right">{formatCurrency(h.avg_cost)}</td>
                                            <td className="text-right">{formatCurrency(h.ltp)}</td>
                                            <td className="text-right">{formatCurrency(h.current_value)}</td>
                                            <td className={`text-right ${(h.pnl || 0) >= 0 ? 'positive' : 'negative'}`}>
                                                {formatCurrency(h.pnl)} ({(h.pnl_percent || 0).toFixed(2)}%)
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>

            {/* Pending Orders */}
            <div className="card">
                <div className="card-header">
                    <h2 className="card-title">Pending Protection Orders ({orders.length})</h2>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                            className="btn btn-success btn-sm"
                            onClick={handleRunAmo}
                            disabled={runAmoMutation.isPending}
                        >
                            {runAmoMutation.isPending ? 'Running...' : '🛡️ Run Protection (DDPI)'}
                        </button>
                        <button
                            className="btn btn-danger btn-sm"
                            onClick={handleCancelAll}
                            disabled={cancelMutation.isPending}
                        >
                            {cancelMutation.isPending ? 'Cancelling...' : 'Cancel All'}
                        </button>
                    </div>
                </div>
                <div className="table-container">
                    {ordersLoading ? (
                        <p className="loading">Loading orders...</p>
                    ) : orders.length === 0 ? (
                        <p className="loading">No pending orders</p>
                    ) : (
                        <table>
                            <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th className="text-right">Qty</th>
                                    <th className="text-right">Price</th>
                                    <th>Type</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {orders.map((o, idx) => (
                                    <tr key={o.orderId || idx}>
                                        <td><strong>{o.tradingSymbol}</strong></td>
                                        <td className="text-right">{o.quantity}</td>
                                        <td className="text-right">{formatCurrency(o.price)}</td>
                                        <td>{o.transactionType}</td>
                                        <td>{o.orderStatus}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>

            {/* Protection Status */}
            {protection && (
                <div className="card">
                    <div className="card-header">
                        <h2 className="card-title">Protection Status</h2>
                    </div>
                    <div className="card-body">
                        <div className="protection-grid">
                            <div className="protection-item">
                                <span className="protection-label">Total Holdings</span>
                                <span className="protection-value">{protection.total_holdings || 0}</span>
                            </div>
                            <div className="protection-item">
                                <span className="protection-label">Protected</span>
                                <span className="protection-value">{protection.protected_count || 0}</span>
                            </div>
                            <div className="protection-item">
                                <span className="protection-label">Unprotected</span>
                                <span className="protection-value">{protection.unprotected_count || 0}</span>
                            </div>
                            <div className="protection-item">
                                <span className="protection-label">Protection %</span>
                                <span className="protection-value">{(protection.protection_percent || 0).toFixed(1)}%</span>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Scheduler Status */}
            {scheduler?.jobs && scheduler.jobs.length > 0 && (
                <div className="card">
                    <div className="card-header">
                        <h2 className="card-title">Scheduler Jobs</h2>
                    </div>
                    <div className="card-body">
                        <div className="scheduler-grid">
                            {scheduler.jobs.map((job, idx) => (
                                <div key={idx} className="job-card">
                                    <div className="job-name">{job.id}</div>
                                    <div className="job-info">
                                        <p>Next Run: {job.next_run_time || 'Not scheduled'}</p>
                                        <p>Trigger: {job.trigger}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            <ToastContainer />
        </div>
    );
}
