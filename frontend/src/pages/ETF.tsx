import { useState, useMemo, MouseEvent } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../store';
import { useEtfs, useBuyEtf } from '../hooks';
import { formatCurrency, formatVolume, getCategory } from '../utils';
import { useToast, ToastContainer } from '../components/Toast';
import type { ETF, BuyOrderRequest } from '../types';

type FilterType = 'all' | 'discount' | 'premium';
type FilterCategory = 'all' | 'gold' | 'silver' | 'nifty' | 'bank' | 'it' | 'other';

export function ETFPage() {
    const logout = useAuthStore((state) => state.logout);
    const toast = useToast();

    const { data: etfData, isLoading, refetch } = useEtfs();
    const buyMutation = useBuyEtf();

    // Filters
    const [filterType, setFilterType] = useState<FilterType>('discount');
    const [filterCategory, setFilterCategory] = useState<FilterCategory>('all');
    const [minTurnover, setMinTurnover] = useState(0);

    // Buy modal state
    const [showModal, setShowModal] = useState(false);
    const [selectedEtf, setSelectedEtf] = useState<ETF | null>(null);
    const [quantity, setQuantity] = useState(1);
    const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
    const [limitPrice, setLimitPrice] = useState(0);

    const allEtfs = etfData?.etfs || [];

    // Filter ETFs
    const filteredEtfs = useMemo(() => {
        return allEtfs.filter(e => {
            if (filterType === 'discount' && e.discount_premium >= 0) return false;
            if (filterType === 'premium' && e.discount_premium <= 0) return false;
            if (filterCategory !== 'all' && getCategory(e) !== filterCategory) return false;
            if (e.turnover < minTurnover) return false;
            return true;
        });
    }, [allEtfs, filterType, filterCategory, minTurnover]);

    // Stats
    const discountEtfs = allEtfs.filter(e => e.discount_premium < 0);
    const premiumEtfs = allEtfs.filter(e => e.discount_premium > 0);
    const bestDiscount = discountEtfs.length > 0
        ? Math.min(...discountEtfs.map(e => e.discount_premium))
        : 0;

    const openBuyModal = (etf: ETF) => {
        setSelectedEtf(etf);
        setQuantity(1);
        setOrderType('MARKET');
        setLimitPrice(etf.ltp);
        setShowModal(true);
    };

    const closeBuyModal = () => {
        setShowModal(false);
        setSelectedEtf(null);
    };

    const handleBuy = async () => {
        if (!selectedEtf) return;

        if (quantity < 1) {
            toast.error('Quantity must be at least 1');
            return;
        }

        try {
            const data: BuyOrderRequest = {
                symbol: selectedEtf.symbol,
                quantity,
                order_type: orderType,
            };
            if (orderType === 'LIMIT') {
                data.price = limitPrice;
            }

            const result = await buyMutation.mutateAsync(data);
            toast.success(result.message || 'Order placed successfully');
            closeBuyModal();
        } catch (err) {
            toast.error(err instanceof Error ? err.message : 'Failed to place order');
        }
    };

    const handleOverlayClick = (e: MouseEvent) => {
        if (e.target === e.currentTarget) {
            closeBuyModal();
        }
    };

    return (
        <div className="dashboard etf-page">
            <header className="header">
                <h1>📈 ETF Recommendations</h1>
                <div className="header-actions">
                    <Link to="/" className="btn-link">← Back to Portfolio</Link>
                    <button className="btn btn-primary" onClick={() => refetch()}>Refresh</button>
                    <button className="btn btn-secondary" onClick={logout}>Logout</button>
                </div>
            </header>

            {/* Stats */}
            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-label">Total ETFs</div>
                    <div className="stat-value">{allEtfs.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Discount ETFs</div>
                    <div className="stat-value positive">{discountEtfs.length}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Best Discount</div>
                    <div className="stat-value positive">{bestDiscount.toFixed(2)}%</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Premium ETFs</div>
                    <div className="stat-value negative">{premiumEtfs.length}</div>
                </div>
            </div>

            {/* Filters */}
            <div className="filters">
                <div className="filter-group">
                    <label>Show:</label>
                    <select value={filterType} onChange={(e) => setFilterType(e.target.value as FilterType)}>
                        <option value="all">All ETFs</option>
                        <option value="discount">Discount Only</option>
                        <option value="premium">Premium Only</option>
                    </select>
                </div>
                <div className="filter-group">
                    <label>Category:</label>
                    <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value as FilterCategory)}>
                        <option value="all">All Categories</option>
                        <option value="gold">Gold</option>
                        <option value="silver">Silver</option>
                        <option value="nifty">Nifty Index</option>
                        <option value="bank">Bank</option>
                        <option value="it">IT</option>
                        <option value="other">Other</option>
                    </select>
                </div>
                <div className="filter-group">
                    <label>Min Turnover (Cr):</label>
                    <input
                        type="number"
                        value={minTurnover}
                        min="0"
                        step="1"
                        onChange={(e) => setMinTurnover(parseFloat(e.target.value) || 0)}
                    />
                </div>
            </div>

            {/* ETF Table */}
            <div className="card">
                <div className="card-header">
                    <h2 className="card-title">ETFs by Discount/Premium</h2>
                    <span style={{ color: 'var(--text-secondary)' }}>
                        Showing {filteredEtfs.length} of {allEtfs.length}
                    </span>
                </div>
                <div className="table-container">
                    {isLoading ? (
                        <p className="loading">Loading ETF data...</p>
                    ) : filteredEtfs.length === 0 ? (
                        <p className="loading">No ETFs match your filters</p>
                    ) : (
                        <table>
                            <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th>Underlying</th>
                                    <th className="text-right">LTP</th>
                                    <th className="text-right">NAV</th>
                                    <th className="text-right">Discount/Premium</th>
                                    <th className="text-right">Change %</th>
                                    <th className="text-right">Volume</th>
                                    <th className="text-right">Turnover</th>
                                    <th className="text-right">Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredEtfs.map((e) => {
                                    const discountClass = e.discount_premium < 0 ? 'good' : 'bad';
                                    const changeClass = e.pchange >= 0 ? 'positive' : 'negative';
                                    return (
                                        <tr key={e.symbol}>
                                            <td>
                                                <strong>{e.symbol}</strong>
                                                {e.discount_premium < -2 && (
                                                    <span className="badge badge-success">Great Buy</span>
                                                )}
                                                {e.discount_premium >= -2 && e.discount_premium < 0 && (
                                                    <span className="badge badge-warning">Discount</span>
                                                )}
                                            </td>
                                            <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                {e.underlying}
                                            </td>
                                            <td className="text-right">{formatCurrency(e.ltp)}</td>
                                            <td className="text-right">{e.nav > 0 ? formatCurrency(e.nav) : '-'}</td>
                                            <td className={`text-right discount-cell ${discountClass}`}>
                                                {e.discount_premium.toFixed(2)}%
                                            </td>
                                            <td className={`text-right ${changeClass}`}>{e.pchange.toFixed(2)}%</td>
                                            <td className="text-right">{formatVolume(e.volume)}</td>
                                            <td className="text-right">{e.turnover.toFixed(2)} Cr</td>
                                            <td className="text-right">
                                                <button
                                                    className="btn btn-success btn-sm"
                                                    onClick={() => openBuyModal(e)}
                                                >
                                                    Buy
                                                </button>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>

            {/* Buy Modal */}
            {showModal && selectedEtf && (
                <div className="modal-overlay" onClick={handleOverlayClick}>
                    <div className="modal">
                        <h2>Buy ETF</h2>
                        <div className="modal-info">
                            <strong>{selectedEtf.symbol}</strong><br />
                            LTP: {formatCurrency(selectedEtf.ltp)} | NAV: {selectedEtf.nav > 0 ? formatCurrency(selectedEtf.nav) : '-'} |
                            Discount: {selectedEtf.discount_premium.toFixed(2)}%
                        </div>
                        <div className="modal-field">
                            <label>Quantity</label>
                            <input
                                type="number"
                                min="1"
                                value={quantity}
                                onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
                            />
                        </div>
                        <div className="modal-field">
                            <label>Order Type</label>
                            <select value={orderType} onChange={(e) => setOrderType(e.target.value as 'MARKET' | 'LIMIT')}>
                                <option value="MARKET">Market Order</option>
                                <option value="LIMIT">Limit Order</option>
                            </select>
                        </div>
                        {orderType === 'LIMIT' && (
                            <div className="modal-field">
                                <label>Limit Price</label>
                                <input
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    value={limitPrice}
                                    onChange={(e) => setLimitPrice(parseFloat(e.target.value) || 0)}
                                />
                            </div>
                        )}
                        <div className="modal-actions">
                            <button className="btn btn-secondary" onClick={closeBuyModal}>Cancel</button>
                            <button
                                className="btn btn-success"
                                onClick={handleBuy}
                                disabled={buyMutation.isPending}
                            >
                                {buyMutation.isPending ? 'Placing...' : 'Place Order'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <ToastContainer />
        </div>
    );
}
