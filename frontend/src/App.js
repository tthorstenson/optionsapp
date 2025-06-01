import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

const API_BASE_URL = process.env.REACT_APP_BACKEND_URL;

function App() {
  const [activeTab, setActiveTab] = useState('backtest');
  const [backtestForm, setBacktestForm] = useState({
    ticker: 'TSLA',
    start_date: '2022-01-01',
    end_date: '2024-01-01',
    strategy_name: '',
    initial_capital: 100000,
    shares_per_contract: 100,
    strategy_params: {
      delta_target: 0.30,
      dte_target: 45,
      profit_target: 0.50,
      loss_limit: 2.0,
      strategy_type: 'weekly',
      entry_day: 'Monday',
      shares_owned: 1000,
      underlying_cost_basis: 200.0,
      max_contracts_to_sell: 5
    }
  });
  
  const [backtestResults, setBacktestResults] = useState(null);
  const [savedStrategies, setSavedStrategies] = useState([]);
  const [comparisonResults, setComparisonResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [polygonStatus, setPolygonStatus] = useState(null);

  useEffect(() => {
    testPolygonConnection();
    loadSavedStrategies();
  }, []);

  const testPolygonConnection = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/polygon-test`);
      setPolygonStatus(response.data);
    } catch (error) {
      setPolygonStatus({ status: 'error', message: 'Failed to connect to API' });
    }
  };

  const loadSavedStrategies = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/strategies`);
      setSavedStrategies(response.data.strategies);
    } catch (error) {
      console.error('Failed to load strategies:', error);
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type } = e.target;
    const parsedValue = type === 'number' ? parseFloat(value) : value;
    
    if (name.startsWith('strategy_params.')) {
      const paramName = name.split('.')[1];
      setBacktestForm(prev => ({
        ...prev,
        strategy_params: {
          ...prev.strategy_params,
          [paramName]: parsedValue
        }
      }));
    } else {
      setBacktestForm(prev => ({
        ...prev,
        [name]: parsedValue
      }));
    }
  };

  const runBacktest = async (e) => {
    e.preventDefault();
    setLoading(true);
    setBacktestResults(null); // Clear previous results
    
    console.log('Starting backtest with form data:', backtestForm);
    
    try {
      const response = await axios.post(`${API_BASE_URL}/api/backtest`, backtestForm);
      console.log('Backtest response received:', response.data);
      setBacktestResults(response.data);
      loadSavedStrategies(); // Refresh strategies list
      console.log('Results set successfully');
    } catch (error) {
      console.error('Backtest failed:', error);
      alert('Backtest failed: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const loadStrategy = (strategy) => {
    setBacktestForm({
      ...backtestForm,
      ticker: strategy.ticker,
      strategy_params: strategy.strategy_params,
      strategy_name: strategy.name + ' (Copy)'
    });
    setActiveTab('backtest');
  };

  const deleteStrategy = async (strategyId) => {
    if (!window.confirm('Are you sure you want to delete this strategy?')) return;
    
    try {
      await axios.delete(`${API_BASE_URL}/api/strategies/${strategyId}`);
      loadSavedStrategies();
    } catch (error) {
      console.error('Failed to delete strategy:', error);
      alert('Failed to delete strategy');
    }
  };

  const addToComparison = (results) => {
    const strategyName = backtestForm.strategy_name || 
      `${backtestForm.ticker} ${backtestForm.strategy_params.delta_target}Δ ${backtestForm.strategy_params.dte_target}DTE`;
    
    const comparisonData = {
      id: Date.now(),
      name: strategyName,
      ticker: backtestForm.ticker,
      strategy_params: backtestForm.strategy_params,
      results: results,
      color: `hsl(${Math.random() * 360}, 70%, 50%)`
    };
    
    setComparisonResults(prev => [...prev, comparisonData]);
    setActiveTab('comparison');
  };

  const removeFromComparison = (id) => {
    setComparisonResults(prev => prev.filter(item => item.id !== id));
  };

  const PerformanceChart = ({ data, comparison = false, comparisonData = [] }) => {
    if (!data && !comparison) return null;

    const chartData = comparison ? comparisonData : data.results;
    
    if (comparison && comparisonData.length === 0) {
      return (
        <div className="performance-chart">
          <div className="chart-placeholder">
            <p>No strategies added for comparison</p>
            <p className="text-sm text-gray-600">Run backtests and click "Add to Comparison" to compare strategies</p>
          </div>
        </div>
      );
    }

    if (comparison) {
      // Multiple strategy comparison
      const maxLength = Math.max(...comparisonData.map(strategy => strategy.results.results.length));
      const combinedData = [];
      
      for (let i = 0; i < maxLength; i++) {
        const dataPoint = { index: i };
        comparisonData.forEach(strategy => {
          if (strategy.results.results[i]) {
            const point = strategy.results.results[i];
            dataPoint[strategy.name] = point.portfolio_value;
            dataPoint.date = point.date;
          }
        });
        combinedData.push(dataPoint);
      }

      return (
        <div className="performance-chart">
          <h3>Strategy Comparison</h3>
          <div className="chart-container">
            <svg width="100%" height="400" viewBox="0 0 800 400">
              {/* Chart background */}
              <rect width="800" height="400" fill="#f8fafc" stroke="#e2e8f0"/>
              
              {/* Chart lines */}
              {comparisonData.map((strategy, strategyIndex) => {
                const strategyResults = strategy.results.results || [];
                if (strategyResults.length === 0) return null;
                
                const values = strategyResults.map(p => p.portfolio_value).filter(v => !isNaN(v) && isFinite(v));
                if (values.length === 0) return null;
                
                const maxValue = Math.max(...values);
                const minValue = Math.min(...values);
                const range = maxValue - minValue || 1;
                
                const points = strategyResults.map((point, index) => {
                  const x = (index / Math.max(strategyResults.length - 1, 1)) * 780 + 10;
                  const y = 390 - ((point.portfolio_value - minValue) / range) * 380;
                  return `${x},${y}`;
                }).filter(point => !point.includes('NaN')).join(' ');
                
                if (points.length === 0) return null;
                
                return (
                  <polyline
                    key={strategyIndex}
                    points={points}
                    fill="none"
                    stroke={strategy.color}
                    strokeWidth="2"
                  />
                );
              })}
            </svg>
          </div>
          
          {/* Legend */}
          <div className="chart-legend">
            {comparisonData.map(strategy => (
              <div key={strategy.id} className="legend-item">
                <div 
                  className="legend-color" 
                  style={{ backgroundColor: strategy.color }}
                ></div>
                <span>{strategy.name}</span>
                <span className="legend-return">
                  {(strategy.results.performance_metrics.total_return * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      );
    }

    // Single strategy chart
    if (!chartData || chartData.length === 0) {
      return (
        <div className="performance-chart">
          <div className="chart-placeholder">
            <p>No chart data available</p>
          </div>
        </div>
      );
    }
    
    const values = chartData.map(p => p.portfolio_value).filter(v => !isNaN(v) && isFinite(v));
    if (values.length === 0) {
      return (
        <div className="performance-chart">
          <div className="chart-placeholder">
            <p>Invalid chart data</p>
          </div>
        </div>
      );
    }
    
    const maxValue = Math.max(...values);
    const minValue = Math.min(...values);
    const range = maxValue - minValue || 1;
    
    const points = chartData.map((point, index) => {
      const x = (index / Math.max(chartData.length - 1, 1)) * 780 + 10;
      const y = 390 - ((point.portfolio_value - minValue) / range) * 380;
      return `${x},${y}`;
    }).filter(point => !point.includes('NaN')).join(' ');

    return (
      <div className="performance-chart">
        <h3>Portfolio Performance</h3>
        <div className="chart-container">
          <svg width="100%" height="400" viewBox="0 0 800 400">
            <rect width="800" height="400" fill="#f8fafc" stroke="#e2e8f0"/>
            {points.length > 0 && (
              <polyline
                points={points}
                fill="none"
                stroke="#1e3a8a"
                strokeWidth="3"
              />
            )}
          </svg>
        </div>
      </div>
    );
  };

  const MetricsGrid = ({ metrics, coveredCallMetrics, underlyingSummary, buyHoldComparison }) => (
    <div className="metrics-section">
      {/* Strategy Comparison */}
      {buyHoldComparison && (
        <div className="comparison-cards">
          <h3>Strategy Comparison</h3>
          
          {/* Stock Price Range */}
          <div className="price-range-display">
            <div className="price-range-item">
              <span className="price-label">Start:</span>
              <span className="price-value">${underlyingSummary?.backtest_start_price?.toFixed(2) || 'N/A'}</span>
              <span className="price-date">({underlyingSummary?.start_date || 'N/A'})</span>
            </div>
            <div className="price-arrow">→</div>
            <div className="price-range-item">
              <span className="price-label">End:</span>
              <span className="price-value">${underlyingSummary?.final_price?.toFixed(2) || 'N/A'}</span>
              <span className="price-date">({underlyingSummary?.end_date || 'N/A'})</span>
            </div>
            <div className="price-change">
              <span className={`price-change-value ${(underlyingSummary?.stock_price_change || 0) >= 0 ? 'positive' : 'negative'}`}>
                {(underlyingSummary?.stock_price_change || 0) >= 0 ? '+' : ''}{((underlyingSummary?.stock_price_change || 0) * 100).toFixed(1)}%
              </span>
            </div>
          </div>
          <div className="strategy-comparison">
            <div className="strategy-card buy-hold">
              <h4>Buy & Hold Only</h4>
              <div className="strategy-metrics">
                <div className="metric-value">
                  {buyHoldComparison.buy_and_hold.return_percentage.toFixed(2)}%
                </div>
                <div className="metric-label">Total Return</div>
                <div className="metric-detail">
                  ${buyHoldComparison.buy_and_hold.total_return.toLocaleString()}
                </div>
              </div>
            </div>
            
            <div className="strategy-card covered-calls">
              <h4>Covered Calls</h4>
              <div className="strategy-metrics">
                <div className="metric-value positive">
                  {buyHoldComparison.covered_calls.return_percentage.toFixed(2)}%
                </div>
                <div className="metric-label">Total Return</div>
                <div className="metric-detail">
                  ${buyHoldComparison.covered_calls.total_return.toLocaleString()}
                </div>
                <div className="metric-breakdown">
                  Underlying: ${buyHoldComparison.covered_calls.underlying_return.toLocaleString()} + 
                  Premium: ${buyHoldComparison.covered_calls.options_premium.toLocaleString()}
                </div>
              </div>
            </div>
            
            <div className="strategy-card outperformance">
              <h4>Outperformance</h4>
              <div className="strategy-metrics">
                <div className={`metric-value ${buyHoldComparison.comparison.outperformance_percentage >= 0 ? 'positive' : 'negative'}`}>
                  {buyHoldComparison.comparison.outperformance_percentage >= 0 ? '+' : ''}{buyHoldComparison.comparison.outperformance_percentage.toFixed(2)}%
                </div>
                <div className="metric-label">Enhanced Return</div>
                <div className="metric-detail">
                  ${buyHoldComparison.comparison.outperformance_dollars.toLocaleString()}
                </div>
                <div className="metric-breakdown">
                  Winner: {buyHoldComparison.comparison.better_strategy}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Detailed Metrics */}
      <div className="metrics-grid">
        <div className="metric-card">
          <h4>Total Return</h4>
          <div className="metric-value">
            {(metrics.total_return * 100).toFixed(2)}%
          </div>
        </div>
        
        <div className="metric-card">
          <h4>Your Cost Basis</h4>
          <div className="metric-value">
            ${underlyingSummary?.entry_price?.toFixed(2) || 'N/A'}
          </div>
          <small className="text-xs text-gray-600">
            Per share
          </small>
        </div>
        
        <div className="metric-card">
          <h4>Underlying P&L</h4>
          <div className="metric-value">
            ${underlyingSummary?.underlying_pnl?.toLocaleString() || 'N/A'}
          </div>
          <small className="text-xs text-gray-600">
            {underlyingSummary?.shares_owned} shares
          </small>
        </div>
        
        <div className="metric-card">
          <h4>Options Premium</h4>
          <div className="metric-value positive">
            ${coveredCallMetrics.total_premium_collected?.toLocaleString() || 'N/A'}
          </div>
          <small className="text-xs text-gray-600">
            {coveredCallMetrics.total_trades} trades
          </small>
        </div>
        
        <div className="metric-card">
          <h4>Sharpe Ratio</h4>
          <div className="metric-value">
            {metrics.sharpe_ratio?.toFixed(2) || 'N/A'}
          </div>
        </div>
        
        <div className="metric-card">
          <h4>Max Drawdown</h4>
          <div className="metric-value negative">
            {(metrics.max_drawdown * 100).toFixed(2)}%
          </div>
        </div>
        
        <div className="metric-card">
          <h4>Win Rate</h4>
          <div className="metric-value">
            {(coveredCallMetrics.win_rate * 100).toFixed(1)}%
          </div>
        </div>
        
        <div className="metric-card">
          <h4>Total Trades</h4>
          <div className="metric-value">
            {coveredCallMetrics.total_trades}
          </div>
        </div>
        
        <div className="metric-card">
          <h4>% Expired Worthless</h4>
          <div className="metric-value positive">
            {(coveredCallMetrics.pct_expired_worthless * 100).toFixed(1)}%
          </div>
        </div>
        
        <div className="metric-card">
          <h4>% Called Away</h4>
          <div className="metric-value">
            {(coveredCallMetrics.pct_called_away * 100).toFixed(1)}%
          </div>
          <small className="text-xs text-gray-600">
            {coveredCallMetrics.assignments_repurchased || 0} of {coveredCallMetrics.total_assignments || 0} repurchased
          </small>
        </div>
        
        <div className="metric-card">
          <h4>Final Price</h4>
          <div className="metric-value">
            ${underlyingSummary?.final_price?.toFixed(2) || 'N/A'}
          </div>
          <small className="text-xs text-gray-600">
            Current market
          </small>
        </div>
        
        <div className="metric-card">
          <h4>Underlying Return</h4>
          <div className="metric-value">
            {((underlyingSummary?.underlying_return || 0) * 100).toFixed(2)}%
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="App">
      <header className="app-header">
        <h1>Options Backtesting</h1>
        <div className="status-indicator">
          <span className={`status-dot ${polygonStatus?.status === 'success' ? 'success' : 'error'}`}></span>
          Polygon API: {polygonStatus?.status || 'Checking...'}
        </div>
      </header>

      <nav className="tab-navigation">
        <button 
          className={`tab ${activeTab === 'backtest' ? 'active' : ''}`}
          onClick={() => setActiveTab('backtest')}
        >
          Backtest
        </button>
        <button 
          className={`tab ${activeTab === 'strategies' ? 'active' : ''}`}
          onClick={() => setActiveTab('strategies')}
        >
          Library
        </button>
        <button 
          className={`tab ${activeTab === 'comparison' ? 'active' : ''}`}
          onClick={() => setActiveTab('comparison')}
        >
          Compare ({comparisonResults.length})
        </button>
      </nav>

      <main className="main-content">
        {activeTab === 'backtest' && (
          <div className="backtest-section">
            <div className="content-grid">
              <div className="form-section">
                <h2>Strategy</h2>
                <form onSubmit={runBacktest} className="backtest-form">
                  <div className="form-group">
                    <label>Ticker</label>
                    <input
                      type="text"
                      name="ticker"
                      value={backtestForm.ticker}
                      onChange={handleInputChange}
                      className="form-input"
                      required
                    />
                  </div>

                  <div className="form-row">
                    <div className="form-group">
                      <label>Start</label>
                      <input
                        type="date"
                        name="start_date"
                        value={backtestForm.start_date}
                        onChange={handleInputChange}
                        className="form-input"
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label>End</label>
                      <input
                        type="date"
                        name="end_date"
                        value={backtestForm.end_date}
                        onChange={handleInputChange}
                        className="form-input"
                        required
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label>Strategy Name (Optional)</label>
                    <input
                      type="text"
                      name="strategy_name"
                      value={backtestForm.strategy_name}
                      onChange={handleInputChange}
                      className="form-input"
                      placeholder="e.g., Conservative Weekly CCs"
                    />
                  </div>

                  <div className="strategy-params">
                    <h3>Parameters</h3>
                    
                    <div className="form-row">
                      <div className="form-group">
                        <label>Shares</label>
                        <input
                          type="number"
                          name="strategy_params.shares_owned"
                          value={backtestForm.strategy_params.shares_owned}
                          onChange={handleInputChange}
                          className="form-input"
                          min="100"
                          step="100"
                          placeholder="e.g., 1000"
                        />
                      </div>
                      <div className="form-group">
                        <label>Cost</label>
                        <input
                          type="number"
                          name="strategy_params.underlying_cost_basis"
                          value={backtestForm.strategy_params.underlying_cost_basis}
                          onChange={handleInputChange}
                          className="form-input"
                          min="1"
                          step="0.01"
                          placeholder="e.g., 200.00"
                        />
                      </div>
                    </div>
                    
                    <div className="form-group">
                      <label>Contracts to Sell</label>
                      <input
                        type="number"
                        name="strategy_params.max_contracts_to_sell"
                        value={backtestForm.strategy_params.max_contracts_to_sell}
                        onChange={handleInputChange}
                        className="form-input"
                        min="1"
                        max={Math.floor(backtestForm.strategy_params.shares_owned / 100)}
                        step="1"
                      />
                      <small className="text-xs text-gray-600 mt-1">
                        Maximum possible: {Math.floor(backtestForm.strategy_params.shares_owned / 100)} contracts 
                        (you own {backtestForm.strategy_params.shares_owned} shares)
                      </small>
                    </div>
                    
                    <div className="form-row">
                      <div className="form-group">
                        <label>Target Delta</label>
                        <input
                          type="number"
                          name="strategy_params.delta_target"
                          value={backtestForm.strategy_params.delta_target}
                          onChange={handleInputChange}
                          className="form-input"
                          step="0.01"
                          min="0.05"
                          max="0.95"
                        />
                      </div>
                      <div className="form-group">
                        <label>Days to Expiration</label>
                        <input
                          type="number"
                          name="strategy_params.dte_target"
                          value={backtestForm.strategy_params.dte_target}
                          onChange={handleInputChange}
                          className="form-input"
                          min="7"
                          max="365"
                        />
                      </div>
                    </div>

                    <div className="form-row">
                      <div className="form-group">
                        <label>Entry Day</label>
                        <select
                          name="strategy_params.entry_day"
                          value={backtestForm.strategy_params.entry_day}
                          onChange={handleInputChange}
                          className="form-select"
                        >
                          <option value="Monday">Monday</option>
                          <option value="Tuesday">Tuesday</option>
                          <option value="Wednesday">Wednesday</option>
                          <option value="Thursday">Thursday</option>
                          <option value="Friday">Friday</option>
                          <option value="Any">Any Day</option>
                        </select>
                      </div>
                      <div className="form-group">
                        <label>Strategy Type</label>
                        <select
                          name="strategy_params.strategy_type"
                          value={backtestForm.strategy_params.strategy_type}
                          onChange={handleInputChange}
                          className="form-select"
                        >
                          <option value="weekly">Weekly</option>
                          <option value="monthly">Monthly</option>
                          <option value="rolling">Rolling (45→21 DTE)</option>
                        </select>
                      </div>
                    </div>
                  </div>

                  <button 
                    type="submit" 
                    className="btn-primary btn-compact"
                    disabled={loading}
                  >
                    {loading ? 'Running...' : 'Backtest'}
                  </button>
                </form>
              </div>

              {backtestResults && (
                <div className="results-section">
                  <div className="results-header">
                    <h2>Results</h2>
                    <button 
                      onClick={() => addToComparison(backtestResults)}
                      className="btn-secondary"
                    >
                      Add to Comparison
                    </button>
                  </div>
                  
                  {/* Breakdown info */}
                  <div style={{ backgroundColor: '#f0f0f0', padding: '10px', marginBottom: '10px', fontSize: '12px' }}>
                    <strong>Breakdown:</strong> Results received - Total Return: {(backtestResults.performance_metrics?.total_return * 100).toFixed(2)}%, 
                    Total Trades: {backtestResults.covered_call_metrics?.total_trades || 'undefined'}, 
                    Underlying P&L: ${backtestResults.underlying_summary?.underlying_pnl?.toFixed(0) || 'N/A'}, 
                    Options Premium: ${backtestResults.covered_call_metrics?.total_premium_collected?.toFixed(0) || 'N/A'},
                    Results Length: {backtestResults.results?.length || 0}
                  </div>
                  
                  <MetricsGrid 
                    metrics={backtestResults.performance_metrics}
                    coveredCallMetrics={backtestResults.covered_call_metrics}
                    underlyingSummary={backtestResults.underlying_summary}
                    buyHoldComparison={backtestResults.buy_and_hold_comparison}
                  />
                  
                  <PerformanceChart data={backtestResults} />
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'strategies' && (
          <div className="strategies-section">
            <h2>Library</h2>
            <div className="strategies-grid">
              {savedStrategies.map(strategy => (
                <div key={strategy.id} className="strategy-card">
                  <div className="strategy-header">
                    <h3>{strategy.name}</h3>
                    <div className="strategy-actions">
                      <button 
                        onClick={() => loadStrategy(strategy)}
                        className="btn-small btn-primary"
                      >
                        Load
                      </button>
                      <button 
                        onClick={() => deleteStrategy(strategy.id)}
                        className="btn-small btn-danger"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  <div className="strategy-details">
                    <p><strong>Ticker:</strong> {strategy.ticker}</p>
                    <p><strong>Delta:</strong> {strategy.strategy_params.delta_target}</p>
                    <p><strong>DTE:</strong> {strategy.strategy_params.dte_target}</p>
                    <p><strong>Type:</strong> {strategy.strategy_params.strategy_type}</p>
                    <p><strong>Created:</strong> {new Date(strategy.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
              ))}
              
              {savedStrategies.length === 0 && (
                <div className="empty-state">
                  <p>No saved strategies yet</p>
                  <p className="text-sm">Run a backtest with a strategy name to save it</p>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'comparison' && (
          <div className="comparison-section">
            <h2>Comparison</h2>
            
            {comparisonResults.length > 0 && (
              <div className="comparison-controls">
                <div className="comparison-list">
                  {comparisonResults.map(strategy => (
                    <div key={strategy.id} className="comparison-item">
                      <div 
                        className="comparison-color" 
                        style={{ backgroundColor: strategy.color }}
                      ></div>
                      <span className="comparison-name">{strategy.name}</span>
                      <span className="comparison-return">
                        {(strategy.results.performance_metrics.total_return * 100).toFixed(1)}%
                      </span>
                      <button 
                        onClick={() => removeFromComparison(strategy.id)}
                        className="btn-small btn-danger"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            <PerformanceChart 
              comparison={true} 
              comparisonData={comparisonResults}
            />
            
            {comparisonResults.length > 0 && (
              <div className="comparison-table">
                <h3>Performance</h3>
                <table>
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      <th>Total Return</th>
                      <th>Sharpe Ratio</th>
                      <th>Max Drawdown</th>
                      <th>Win Rate</th>
                      <th>Total Trades</th>
                      <th>% Expired Worthless</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparisonResults.map(strategy => (
                      <tr key={strategy.id}>
                        <td>
                          <div className="strategy-cell">
                            <div 
                              className="strategy-color-dot" 
                              style={{ backgroundColor: strategy.color }}
                            ></div>
                            {strategy.name}
                          </div>
                        </td>
                        <td className="metric-cell">
                          {(strategy.results.performance_metrics.total_return * 100).toFixed(2)}%
                        </td>
                        <td className="metric-cell">
                          {strategy.results.performance_metrics.sharpe_ratio?.toFixed(2) || 'N/A'}
                        </td>
                        <td className="metric-cell negative">
                          {(strategy.results.performance_metrics.max_drawdown * 100).toFixed(2)}%
                        </td>
                        <td className="metric-cell">
                          {(strategy.results.covered_call_metrics.win_rate * 100).toFixed(1)}%
                        </td>
                        <td className="metric-cell">
                          {strategy.results.covered_call_metrics.total_trades}
                        </td>
                        <td className="metric-cell positive">
                          {(strategy.results.covered_call_metrics.pct_expired_worthless * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;