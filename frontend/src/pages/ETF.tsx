import { useState, useMemo, MouseEvent } from 'react';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../store';
import { useEtfs, useBuyEtf } from '../hooks';
import { formatCurrency, formatVolume, getCategory, getNseUrl } from '../utils';
import { useToast, ToastContainer } from '../components/Toast';
import type { ETF, BuyOrderRequest } from '../types';
import './ETF.css';

type FilterType = 'all' | 'discount' | 'premium';
type FilterCategory = 'all' | 'gold' | 'silver' | 'nifty' | 'bank' | 'it' | 'other';
type SortField = 'discount' | 'turnover' | 'volume' | 'change';

const CATEGORY_ICONS: Record<FilterCategory, string> = {
    all: '◎',
    gold: '🥇',
    silver: '🥈',
    nifty: '📊',
    bank: '🏦',
    it: '💻',
    other: '📁'
};

export function ETFPage() {
    const logout = useAuthStore((state) => state.logout);
    const toast = useToast();

    const { data: etfData, isLoading, refetch } = useEtfs();
    const buyMutation = useBuyEtf();

    // Filters
    const [filterType, setFilterType] = useState<FilterType>('discount');
    const [filterCategory, setFilterCategory] = useState<FilterCategory>('all');
    const [minTurnover, setMinTurnover] = useState(0);
    const [sortField, setSortField] = useState<SortField>('discount');
    const [sortAsc, setSortAsc] = useState(true);

    // Buy modal state
    const [showModal, setShowModal] = useState(false);
    const [selectedEtf, setSelectedEtf] = useState<ETF | null>(null);
    const [quantity, setQuantity] = useState(1);
    const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
    const [limitPrice, setLimitPrice] = useState(0);

    const allEtfs = etfData?.etfs || [];

    // Filter & Sort ETFs
    const filteredEtfs = useMemo(() => {
        let result = allEtfs.filter(e => {
            if (filterType === 'discount' && e.discount_premium >= 0) return false;
            if (filterType === 'premium' && e.discount_premium <= 0) return false;
            if (filterCategory !== 'all' && getCategory(e) !== filterCategory) return false;
            if (e.turnover < minTurnover) return false;
            return true;
        });

        // Sort
        result.sort((a, b) => {
            let valA = 0, valB = 0;
            switch (sortField) {
                case 'discount': valA = a.discount_premium; valB = b.discount_premium; break;
                case 'turnover': valA = a.turnover; valB = b.turnover; break;
                case 'volume': valA = a.volume; valB = b.volume; break;
                case 'change': valA = a.pchange; valB = b.pchange; break;
            }
            return sortAsc ? valA - valB : valB - valA;
        });

        return result;
    }, [allEtfs, filterType, filterCategory, minTurnover, sortField, sortAsc]);

    // Stats
    const discountEtfs = allEtfs.filter(e => e.discount_premium < 0);
    const premiumCount = allEtfs.filter(e => e.discount_premium > 0).length;
    const bestDiscount = discountEtfs.length > 0
        ? Math.min(...discountEtfs.map(e => e.discount_premium))
        : 0;
    const avgDiscount = discountEtfs.length > 0
        ? discountEtfs.reduce((s, e) => s + e.discount_premium, 0) / discountEtfs.length
        : 0;

    // Use premiumCount somewhere to avoid unused variable warning
    void premiumCount;

    // Dynamic turnover filter values based on actual data
    const turnoverOptions = useMemo(() => {
        if (allEtfs.length === 0) return [0];
        const turnovers = allEtfs.map(e => e.turnover).filter(t => t > 0);
        if (turnovers.length === 0) return [0];
        const maxTurnover = Math.max(...turnovers);
        const p25 = turnovers.sort((a, b) => a - b)[Math.floor(turnovers.length * 0.25)] || 0;
        const p50 = turnovers.sort((a, b) => a - b)[Math.floor(turnovers.length * 0.5)] || 0;
        const p75 = turnovers.sort((a, b) => a - b)[Math.floor(turnovers.length * 0.75)] || 0;
        // Create nice rounded values
        const round = (v: number) => v < 1 ? Math.round(v * 10) / 10 : Math.round(v);
        return [
            0,
            round(p25),
            round(p50),
            round(p75),
            round(maxTurnover * 0.5)
        ].filter((v, i, arr) => arr.indexOf(v) === i).slice(0, 5); // Unique values, max 5
    }, [allEtfs]);

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

    const handleSort = (field: SortField) => {
        if (sortField === field) {
            setSortAsc(!sortAsc);
        } else {
            setSortField(field);
            setSortAsc(field === 'discount'); // Ascending for discount (best first), descending for others
        }
    };

    const getDiscountClass = (discount: number) => {
        if (discount <= -2) return 'excellent';
        if (discount < 0) return 'good';
        if (discount === 0) return 'neutral';
        return 'premium';
    };

    return (
        <div className="etf-shell">
            {/* Header */}
            <header className="etf-header">
                <div className="header-brand">
                    <span className="brand-icon">◈</span>
                    <h1>ETF <span className="brand-accent">Scanner</span></h1>
                </div>
                <nav className="header-nav">
                    <Link to="/" className="nav-link">← Portfolio</Link>
                    <button className="nav-btn" onClick={() => refetch()}>
                        <span className="refresh-icon">⟳</span> Refresh
                    </button>
                    <button className="nav-btn logout" onClick={logout}>Logout</button>
                </nav>
            </header>

            <main className="etf-main">
                {/* Hero Stats */}
                <section className="hero-stats">
                    <div className="stat-block primary">
                        <div className="stat-eyebrow">ETFs Tracked</div>
                        <div className="stat-amount">{allEtfs.length}</div>
                        <div className="stat-delta">
                            <span className="delta-label">Showing {filteredEtfs.length} matching filters</span>
                        </div>
                    </div>
                    <div className="stat-block">
                        <div className="stat-eyebrow">Trading at Discount</div>
                        <div className="stat-amount-sm positive">{discountEtfs.length}</div>
                        <div className="stat-subtitle">ETFs below NAV</div>
                    </div>
                    <div className="stat-block">
                        <div className="stat-eyebrow">Best Discount</div>
                        <div className="stat-amount-sm positive">{bestDiscount.toFixed(2)}%</div>
                        <div className="stat-subtitle">Best opportunity</div>
                    </div>
                    <div className="stat-block">
                        <div className="stat-eyebrow">Avg Discount</div>
                        <div className="stat-amount-sm">{avgDiscount.toFixed(2)}%</div>
                        <div className="stat-subtitle">Of discount ETFs</div>
                    </div>
                </section>

                {/* Filters Bar */}
                <section className="filters-bar">
                    <div className="filter-group">
                        <label className="filter-label">Type</label>
                        <div className="filter-pills">
                            {(['all', 'discount', 'premium'] as FilterType[]).map(t => (
                                <button
                                    key={t}
                                    className={`filter-pill ${filterType === t ? 'active' : ''}`}
                                    onClick={() => setFilterType(t)}
                                >
                                    {t === 'all' ? 'All' : t === 'discount' ? '↓ Discount' : '↑ Premium'}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="filter-group">
                        <label className="filter-label">Category</label>
                        <div className="filter-pills category-pills">
                            {(['all', 'gold', 'silver', 'nifty', 'bank', 'it', 'other'] as FilterCategory[]).map(c => (
                                <button
                                    key={c}
                                    className={`filter-pill ${filterCategory === c ? 'active' : ''}`}
                                    onClick={() => setFilterCategory(c)}
                                    title={c}
                                >
                                    <span className="pill-icon">{CATEGORY_ICONS[c]}</span>
                                    <span className="pill-text">{c.charAt(0).toUpperCase() + c.slice(1)}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="filter-group turnover-filter">
                        <label className="filter-label">Min Turnover</label>
                        <div className="filter-pills">
                            {turnoverOptions.map(t => (
                                <button
                                    key={t}
                                    className={`filter-pill ${minTurnover === t ? 'active' : ''}`}
                                    onClick={() => setMinTurnover(t)}
                                >
                                    {t === 0 ? 'All' : `≥${t} Cr`}
                                </button>
                            ))}
                        </div>
                    </div>
                </section>

                {/* ETF Table */}
                <section className="etf-section">
                    <div className="section-header">
                        <h2>ETFs by Discount/Premium</h2>
                        <span className="section-count">{filteredEtfs.length} results</span>
                    </div>

                    {isLoading ? (
                        <div className="table-loading">
                            <div className="loader"></div>
                            <span>Scanning ETF markets...</span>
                        </div>
                    ) : filteredEtfs.length === 0 ? (
                        <div className="table-empty">
                            <span className="empty-icon">◇</span>
                            <p>No ETFs match your filters</p>
                        </div>
                    ) : (
                        <div className="etf-table-wrapper">
                            <table className="etf-table">
                                <thead>
                                    <tr>
                                        <th className="col-symbol">Symbol</th>
                                        <th className="col-underlying">Underlying</th>
                                        <th className="col-price">LTP</th>
                                        <th className="col-price">NAV</th>
                                        <th
                                            className={`col-discount sortable ${sortField === 'discount' ? 'sorted' : ''}`}
                                            onClick={() => handleSort('discount')}
                                        >
                                            Discount/Premium {sortField === 'discount' && (sortAsc ? '↑' : '↓')}
                                        </th>
                                        <th
                                            className={`col-change sortable ${sortField === 'change' ? 'sorted' : ''}`}
                                            onClick={() => handleSort('change')}
                                        >
                                            Change % {sortField === 'change' && (sortAsc ? '↑' : '↓')}
                                        </th>
                                        <th
                                            className={`col-volume sortable ${sortField === 'volume' ? 'sorted' : ''}`}
                                            onClick={() => handleSort('volume')}
                                        >
                                            Volume {sortField === 'volume' && (sortAsc ? '↑' : '↓')}
                                        </th>
                                        <th
                                            className={`col-turnover sortable ${sortField === 'turnover' ? 'sorted' : ''}`}
                                            onClick={() => handleSort('turnover')}
                                        >
                                            Turnover {sortField === 'turnover' && (sortAsc ? '↑' : '↓')}
                                        </th>
                                        <th className="col-action">Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredEtfs.map((e) => {
                                        const discountClass = getDiscountClass(e.discount_premium);
                                        const changeClass = e.pchange >= 0 ? 'positive' : 'negative';
                                        return (
                                            <tr key={e.symbol} className={`etf-row ${discountClass}`}>
                                                <td className="col-symbol">
                                                    <a
                                                        href={getNseUrl(e.symbol, e.underlying)}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="symbol-link"
                                                    >
                                                        {e.symbol}
                                                    </a>
                                                    {e.discount_premium <= -2 && (
                                                        <span className="badge badge-excellent">★ Great Buy</span>
                                                    )}
                                                    {e.discount_premium > -2 && e.discount_premium < 0 && (
                                                        <span className="badge badge-good">Discount</span>
                                                    )}
                                                </td>
                                                <td className="col-underlying">
                                                    <span className="underlying-text">{e.underlying}</span>
                                                </td>
                                                <td className="col-price">
                                                    <span className="mono">{formatCurrency(e.ltp)}</span>
                                                </td>
                                                <td className="col-price">
                                                    <span className="mono">{e.nav > 0 ? formatCurrency(e.nav) : '—'}</span>
                                                </td>
                                                <td className={`col-discount ${discountClass}`}>
                                                    <span className="discount-value">{e.discount_premium.toFixed(2)}%</span>
                                                </td>
                                                <td className={`col-change ${changeClass}`}>
                                                    <span className="mono">{e.pchange >= 0 ? '+' : ''}{e.pchange.toFixed(2)}%</span>
                                                </td>
                                                <td className="col-volume">
                                                    <span className="mono">{formatVolume(e.volume)}</span>
                                                </td>
                                                <td className="col-turnover">
                                                    <span className="mono">{e.turnover.toFixed(2)} Cr</span>
                                                </td>
                                                <td className="col-action">
                                                    <button
                                                        className="buy-btn"
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
                        </div>
                    )}
                </section>

                {/* Legend */}
                <footer className="etf-footer">
                    <div className="legend">
                        <div className="legend-item">
                            <span className="legend-dot excellent"></span>
                            <span>≤ -2% (Excellent)</span>
                        </div>
                        <div className="legend-item">
                            <span className="legend-dot good"></span>
                            <span>-2% to 0% (Good)</span>
                        </div>
                        <div className="legend-item">
                            <span className="legend-dot neutral"></span>
                            <span>0% (Fair)</span>
                        </div>
                        <div className="legend-item">
                            <span className="legend-dot premium"></span>
                            <span>&gt; 0% (Premium)</span>
                        </div>
                    </div>
                </footer>
            </main>

            {/* Buy Modal */}
            {showModal && selectedEtf && (
                <div className="modal-overlay" onClick={handleOverlayClick}>
                    <div className="modal">
                        <div className="modal-header">
                            <h2>Buy ETF</h2>
                            <button className="modal-close" onClick={closeBuyModal}>×</button>
                        </div>
                        <div className="modal-body">
                            <div className="modal-etf-info">
                                <div className="etf-name">{selectedEtf.symbol}</div>
                                <div className="etf-meta">
                                    <span>LTP: <strong>{formatCurrency(selectedEtf.ltp)}</strong></span>
                                    <span>NAV: <strong>{selectedEtf.nav > 0 ? formatCurrency(selectedEtf.nav) : '—'}</strong></span>
                                    <span className={selectedEtf.discount_premium < 0 ? 'positive' : 'negative'}>
                                        {selectedEtf.discount_premium.toFixed(2)}%
                                    </span>
                                </div>
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
                                <div className="order-type-pills">
                                    <button
                                        className={`type-pill ${orderType === 'MARKET' ? 'active' : ''}`}
                                        onClick={() => setOrderType('MARKET')}
                                    >
                                        Market
                                    </button>
                                    <button
                                        className={`type-pill ${orderType === 'LIMIT' ? 'active' : ''}`}
                                        onClick={() => setOrderType('LIMIT')}
                                    >
                                        Limit
                                    </button>
                                </div>
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

                            <div className="order-summary">
                                <span>Estimated Value</span>
                                <span className="mono">
                                    {formatCurrency(quantity * (orderType === 'LIMIT' ? limitPrice : selectedEtf.ltp))}
                                </span>
                            </div>
                        </div>

                        <div className="modal-footer">
                            <button className="btn-cancel" onClick={closeBuyModal}>Cancel</button>
                            <button
                                className="btn-confirm"
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
