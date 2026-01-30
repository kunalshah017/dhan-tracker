import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../store';
import { useHoldings, useOrders, useProtectionStatus, useSchedulerStatus, useRunAmoProtection, useCancelAllOrders, useTokenStatus, useRefreshToken } from '../hooks';
import { formatCurrency } from '../utils';
import { useToast, ToastContainer } from '../components/Toast';
import type { Order } from '../types';
import './Portfolio.css';

export function Portfolio() {
    const logout = useAuthStore((state) => state.logout);
    const toast = useToast();
    const [showOrders, setShowOrders] = useState(false);
    const [expandedRow, setExpandedRow] = useState<string | null>(null);
    const [confirmDialog, setConfirmDialog] = useState<{ type: 'protect' | 'cancel' | null; open: boolean }>({ type: null, open: false });

    const { data: holdingsData, isLoading: holdingsLoading, refetch: refetchHoldings } = useHoldings();
    const { data: ordersData, isLoading: ordersLoading, refetch: refetchOrders } = useOrders();
    const { data: protectionData, refetch: refetchProtection } = useProtectionStatus();
    const { data: schedulerData } = useSchedulerStatus();
    const { data: tokenData, refetch: refetchToken } = useTokenStatus();

    const runAmoMutation = useRunAmoProtection();
    const cancelMutation = useCancelAllOrders();
    const refreshTokenMutation = useRefreshToken();

    const refreshAll = () => {
        refetchHoldings();
        refetchOrders();
        refetchProtection();
        refetchToken();
    };

    const handleRunProtection = async () => {
        setConfirmDialog({ type: null, open: false });
        try {
            const result = await runAmoMutation.mutateAsync();
            toast.success(result.message || 'Protection orders placed');
            refreshAll();
        } catch (err) {
            toast.error(err instanceof Error ? err.message : 'Failed to run protection');
        }
    };

    const handleCancelAll = async () => {
        setConfirmDialog({ type: null, open: false });
        try {
            const result = await cancelMutation.mutateAsync();
            toast.success(result.message || 'All orders cancelled');
            refreshAll();
        } catch (err) {
            toast.error(err instanceof Error ? err.message : 'Failed to cancel orders');
        }
    };

    const openConfirmDialog = (type: 'protect' | 'cancel') => {
        setConfirmDialog({ type, open: true });
    };

    const closeConfirmDialog = () => {
        setConfirmDialog({ type: null, open: false });
    };

    const handleRefreshToken = async () => {
        try {
            await refreshTokenMutation.mutateAsync();
            toast.success('API token refreshed');
            refetchToken();
        } catch (err) {
            toast.error(err instanceof Error ? err.message : 'Failed to refresh token');
        }
    };

    const holdings = holdingsData?.holdings || [];
    const orders = ordersData?.orders || [];
    // protectionData available for future use
    void protectionData;

    const totalInvested = holdingsData?.total_invested ?? 0;
    const totalCurrent = holdingsData?.total_current ?? 0;
    const totalPnL = holdingsData?.total_pnl ?? 0;
    const pnlPercent = holdingsData?.total_pnl_percent ?? 0;

    // Create a map of protected symbols from orders
    const protectedSymbols = new Map<string, Order>();
    orders.forEach(o => {
        if (o.orderStatus !== 'CANCELLED' && o.orderStatus !== 'REJECTED') {
            protectedSymbols.set(o.tradingSymbol, o);
        }
    });

    // Merge holdings with protection data
    const enrichedHoldings = holdings.map(h => ({
        ...h,
        isProtected: protectedSymbols.has(h.symbol),
        protectionOrder: protectedSymbols.get(h.symbol),
        triggerPrice: protectedSymbols.get(h.symbol)?.triggerPrice || 0,
    }));

    const protectedCount = enrichedHoldings.filter(h => h.isProtected).length;
    const protectionPercent = holdings.length > 0 ? (protectedCount / holdings.length) * 100 : 0;

    const getProtectionTier = (h: typeof enrichedHoldings[0]) => {
        if (!h.isProtected || !h.triggerPrice) return null;
        const pnlAtTrigger = ((h.triggerPrice - h.avg_cost) / h.avg_cost) * 100;
        if (pnlAtTrigger >= 30) return { tier: 'EXCELLENT', color: '#10b981', icon: '◆◆◆' };
        if (pnlAtTrigger >= 15) return { tier: 'GOOD', color: '#3b82f6', icon: '◆◆' };
        if (pnlAtTrigger >= 0) return { tier: 'SAFE', color: '#f59e0b', icon: '◆' };
        return { tier: 'RECOVERY', color: '#ef4444', icon: '○' };
    };

    return (
        <div className="portfolio-shell">
            {/* Header Bar */}
            <header className="portfolio-header">
                <div className="header-brand">
                    <span className="brand-icon">◈</span>
                    <h1>DHAN<span className="brand-accent">TRACKER</span></h1>
                </div>
                <nav className="header-nav">
                    <Link to="/etf" className="nav-link">ETF Scanner</Link>
                    <button className="nav-btn" onClick={refreshAll}>
                        <span className="refresh-icon">↻</span>
                    </button>
                    <button className="nav-btn logout" onClick={logout}>Exit</button>
                </nav>
            </header>

            {/* Main Content */}
            <main className="portfolio-main">
                {/* Hero Stats */}
                <section className="hero-stats">
                    <div className="stat-block primary">
                        <div className="stat-eyebrow">Portfolio Value</div>
                        <div className="stat-amount">{formatCurrency(totalCurrent)}</div>
                        <div className={`stat-delta ${totalPnL >= 0 ? 'up' : 'down'}`}>
                            {totalPnL >= 0 ? '▲' : '▼'} {formatCurrency(Math.abs(totalPnL))}
                            <span className="delta-percent">({pnlPercent.toFixed(2)}%)</span>
                        </div>
                    </div>
                    <div className="stat-block">
                        <div className="stat-eyebrow">Invested</div>
                        <div className="stat-amount-sm">{formatCurrency(totalInvested)}</div>
                    </div>
                    <div className="stat-block">
                        <div className="stat-eyebrow">Holdings</div>
                        <div className="stat-amount-sm">{holdings.length}</div>
                    </div>
                    <div className="stat-block protection-stat">
                        <div className="stat-eyebrow">Protected</div>
                        <div className="protection-ring">
                            <svg viewBox="0 0 36 36" className="ring-svg">
                                <path
                                    className="ring-bg"
                                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                />
                                <path
                                    className="ring-progress"
                                    strokeDasharray={`${protectionPercent}, 100`}
                                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                />
                            </svg>
                            <span className="ring-text">{protectedCount}/{holdings.length}</span>
                        </div>
                    </div>
                </section>

                {/* Action Bar */}
                <section className="action-bar">
                    <div className="action-group">
                        <button
                            className="action-btn primary"
                            onClick={() => openConfirmDialog('protect')}
                            disabled={runAmoMutation.isPending}
                        >
                            <span className="btn-icon">⛊</span>
                            {runAmoMutation.isPending ? 'Protecting...' : 'Activate Protection'}
                        </button>
                        <button
                            className="action-btn danger"
                            onClick={() => openConfirmDialog('cancel')}
                            disabled={cancelMutation.isPending || orders.length === 0}
                        >
                            {cancelMutation.isPending ? 'Cancelling...' : 'Cancel All GTT'}
                        </button>
                    </div>
                    <div className="action-group">
                        <button
                            className={`action-btn toggle ${showOrders ? 'active' : ''}`}
                            onClick={() => setShowOrders(!showOrders)}
                        >
                            Orders {orders.length > 0 && <span className="badge">{orders.length}</span>}
                        </button>
                    </div>
                </section>

                {/* Orders Panel (Collapsible) */}
                {showOrders && (
                    <section className="orders-panel">
                        <div className="panel-header">
                            <h3>Active GTT Orders</h3>
                            <span className="panel-count">{orders.length} orders</span>
                        </div>
                        {ordersLoading ? (
                            <div className="panel-loading">Loading orders...</div>
                        ) : orders.length === 0 ? (
                            <div className="panel-empty">No active protection orders</div>
                        ) : (
                            <div className="orders-grid">
                                {orders.map((o, idx) => (
                                    <div key={o.orderId || idx} className="order-chip">
                                        <span className="chip-symbol">{o.tradingSymbol}</span>
                                        <span className="chip-trigger">@ {formatCurrency(o.triggerPrice || o.price)}</span>
                                        <span className={`chip-status ${o.orderStatus.toLowerCase()}`}>{o.orderStatus}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>
                )}

                {/* Holdings Table */}
                <section className="holdings-section">
                    <div className="section-header">
                        <h2>Holdings & Protection Status</h2>
                        <div className="legend">
                            <span className="legend-item protected">● Protected</span>
                            <span className="legend-item unprotected">○ Unprotected</span>
                        </div>
                    </div>

                    {holdingsLoading ? (
                        <div className="table-loading">
                            <div className="loader"></div>
                            <span>Loading portfolio...</span>
                        </div>
                    ) : holdings.length === 0 ? (
                        <div className="table-empty">
                            <span className="empty-icon">◇</span>
                            <p>No holdings found</p>
                        </div>
                    ) : (
                        <div className="holdings-table-wrapper">
                            <table className="holdings-table">
                                <thead>
                                    <tr>
                                        <th className="col-status"></th>
                                        <th className="col-symbol">Symbol</th>
                                        <th className="col-qty">Qty</th>
                                        <th className="col-price">Avg Cost</th>
                                        <th className="col-price">LTP</th>
                                        <th className="col-value">Value</th>
                                        <th className="col-pnl">P&L</th>
                                        <th className="col-protection">Protection</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {enrichedHoldings.map((h) => {
                                        const tier = getProtectionTier(h);
                                        const isExpanded = expandedRow === h.symbol;
                                        return (
                                            <tr
                                                key={h.symbol}
                                                className={`holding-row ${h.isProtected ? 'protected' : 'unprotected'} ${isExpanded ? 'expanded' : ''}`}
                                                onClick={() => setExpandedRow(isExpanded ? null : h.symbol)}
                                            >
                                                <td className="col-status">
                                                    <span className={`status-dot ${h.isProtected ? 'active' : ''}`}></span>
                                                </td>
                                                <td className="col-symbol">
                                                    <span className="symbol-name">{h.symbol}</span>
                                                </td>
                                                <td className="col-qty">{h.quantity}</td>
                                                <td className="col-price">{formatCurrency(h.avg_cost)}</td>
                                                <td className="col-price">
                                                    <span className={h.ltp >= h.avg_cost ? 'price-up' : 'price-down'}>
                                                        {formatCurrency(h.ltp)}
                                                    </span>
                                                </td>
                                                <td className="col-value">{formatCurrency(h.current_value)}</td>
                                                <td className={`col-pnl ${(h.pnl || 0) >= 0 ? 'positive' : 'negative'}`}>
                                                    <span className="pnl-amount">{formatCurrency(h.pnl)}</span>
                                                    <span className="pnl-percent">({(h.pnl_percent || 0).toFixed(1)}%)</span>
                                                </td>
                                                <td className="col-protection">
                                                    {h.isProtected && tier ? (
                                                        <div className="protection-badge" style={{ '--tier-color': tier.color } as React.CSSProperties}>
                                                            <span className="tier-icon">{tier.icon}</span>
                                                            <span className="trigger-price">SL @ {formatCurrency(h.triggerPrice)}</span>
                                                        </div>
                                                    ) : (
                                                        <span className="no-protection">—</span>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </section>

                {/* Footer Status Bar */}
                <footer className="status-bar">
                    <div className="status-item">
                        <span className="status-label">Token</span>
                        <span className={`status-value ${tokenData?.last_refresh_result?.status === 'success' ? 'ok' : 'warn'}`}>
                            {tokenData?.token_source || 'env'}
                        </span>
                        <button className="status-action" onClick={handleRefreshToken} disabled={refreshTokenMutation.isPending}>
                            ↻
                        </button>
                    </div>
                    <div className="status-item">
                        <span className="status-label">Scheduler</span>
                        <span className="status-value ok">
                            {schedulerData?.jobs?.length || 0} jobs
                        </span>
                    </div>
                    <div className="status-item">
                        <span className="status-label">Last Refresh</span>
                        <span className="status-value">
                            {new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                        </span>
                    </div>
                </footer>
            </main>

            {/* Confirmation Dialog */}
            {confirmDialog.open && (
                <div className="modal-overlay" onClick={closeConfirmDialog}>
                    <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
                        <div className="confirm-icon">
                            {confirmDialog.type === 'protect' ? '⛊' : '⚠'}
                        </div>
                        <h3 className="confirm-title">
                            {confirmDialog.type === 'protect'
                                ? 'Activate Protection?'
                                : 'Cancel All Orders?'}
                        </h3>
                        <p className="confirm-message">
                            {confirmDialog.type === 'protect'
                                ? `This will place protective stop-loss orders for ${holdings.filter(h => !enrichedHoldings.find(e => e.symbol === h.symbol)?.isProtected).length || 'all unprotected'} holdings using Forever (GTT) orders.`
                                : `This will cancel all ${orders.length} active GTT protection orders. Your holdings will be unprotected.`}
                        </p>
                        <div className="confirm-actions">
                            <button className="confirm-btn cancel" onClick={closeConfirmDialog}>
                                Cancel
                            </button>
                            <button
                                className={`confirm-btn ${confirmDialog.type === 'protect' ? 'primary' : 'danger'}`}
                                onClick={confirmDialog.type === 'protect' ? handleRunProtection : handleCancelAll}
                            >
                                {confirmDialog.type === 'protect' ? 'Yes, Protect' : 'Yes, Cancel All'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <ToastContainer />
        </div>
    );
}
