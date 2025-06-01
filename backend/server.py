from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import json
import uuid
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pymongo import MongoClient
from polygon import RESTClient
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Options Backtesting API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB setup
client = MongoClient(os.environ.get('MONGO_URL'))
db = client[os.environ.get('DB_NAME', 'options_backtesting')]
strategies_collection = db.strategies
backtest_results_collection = db.backtest_results

# Polygon API setup
POLYGON_API_KEY = "jpdDHlJKhfxmcb4J0wjE6WLy0rz2Egco"

def get_polygon_client():
    return RESTClient(POLYGON_API_KEY)

# Pydantic models
class StrategyParams(BaseModel):
    delta_target: float = 0.30
    dte_target: int = 45
    profit_target: float = 0.50
    loss_limit: float = 2.0
    strategy_type: str = "weekly"  # weekly, monthly, rolling
    entry_day: str = "Monday"  # Monday, Tuesday, etc.

class BacktestRequest(BaseModel):
    ticker: str
    start_date: str
    end_date: str
    strategy_params: StrategyParams
    strategy_name: Optional[str] = None
    initial_capital: float = 100000
    shares_per_contract: int = 100

class Strategy(BaseModel):
    id: str
    name: str
    ticker: str
    strategy_params: StrategyParams
    created_at: datetime
    tags: List[str] = []

# Helper functions
def get_business_days(start_date: str, end_date: str) -> List[str]:
    """Get business days between start and end date"""
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    business_days = pd.bdate_range(start=start, end=end)
    return [day.strftime('%Y-%m-%d') for day in business_days]

def calculate_dte(expiration_date: str, current_date: str) -> int:
    """Calculate days to expiration"""
    exp = datetime.strptime(expiration_date, '%Y-%m-%d')
    curr = datetime.strptime(current_date, '%Y-%m-%d')
    return (exp - curr).days

class CoveredCallBacktester:
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.positions = []
        self.closed_trades = []
        self.performance_metrics = {}
        
    def run_backtest(self, ticker: str, start_date: str, end_date: str, strategy_params: StrategyParams):
        """Run covered call backtest"""
        try:
            # Get stock data
            stock_data = self.get_stock_data(ticker, start_date, end_date)
            if not stock_data:
                return {"error": "No stock data available"}
            
            # Get options data (simulated for now due to API limitations)
            options_data = self.simulate_options_data(stock_data, strategy_params)
            
            results = []
            business_days = get_business_days(start_date, end_date)
            
            for current_date in business_days:
                current_stock_data = next((d for d in stock_data if d['date'] == current_date), None)
                if not current_stock_data:
                    continue
                    
                current_price = current_stock_data['close']
                
                # Manage existing positions
                self.manage_positions(current_date, current_price, options_data)
                
                # Look for new opportunities
                if self.should_open_position(current_date, strategy_params):
                    self.open_covered_call(current_date, current_price, options_data, strategy_params)
                
                # Calculate portfolio value
                portfolio_value = self.calculate_portfolio_value(current_date, current_price, options_data)
                
                results.append({
                    'date': current_date,
                    'stock_price': current_price,
                    'portfolio_value': portfolio_value,
                    'cash': self.current_capital,
                    'positions_count': len([p for p in self.positions if p['status'] == 'open']),
                    'total_premium_collected': sum(t['premium_received'] for t in self.closed_trades),
                    'trades_count': len(self.closed_trades)
                })
            
            # Calculate performance metrics
            self.performance_metrics = self.calculate_performance_metrics(results)
            
            return {
                'results': results,
                'performance_metrics': self.performance_metrics,
                'trades': self.closed_trades,
                'covered_call_metrics': self.calculate_covered_call_metrics()
            }
            
        except Exception as e:
            print(f"Backtest error: {str(e)}")
            return {"error": str(e)}
    
    def get_stock_data(self, ticker: str, start_date: str, end_date: str):
        """Get stock price data from Polygon"""
        try:
            client = get_polygon_client()
            stock_data = []
            
            # Convert dates for Polygon API
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            # Get aggregates (daily bars)
            aggs = client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="day",
                from_=start_date,
                to=end_date,
                limit=50000
            )
            
            for agg in aggs:
                stock_data.append({
                    'date': datetime.fromtimestamp(agg.timestamp / 1000).strftime('%Y-%m-%d'),
                    'open': agg.open,
                    'high': agg.high,
                    'low': agg.low,
                    'close': agg.close,
                    'volume': agg.volume
                })
            
            return sorted(stock_data, key=lambda x: x['date'])
            
        except Exception as e:
            print(f"Error fetching stock data: {e}")
            # Return simulated data for demo
            return self.generate_demo_stock_data(ticker, start_date, end_date)
    
    def generate_demo_stock_data(self, ticker: str, start_date: str, end_date: str):
        """Generate simulated stock data for demo purposes"""
        business_days = get_business_days(start_date, end_date)
        
        # Start with realistic prices based on ticker
        base_prices = {'TSLA': 200, 'AAPL': 150, 'SPY': 400, 'QQQ': 300}
        base_price = base_prices.get(ticker, 100)
        
        stock_data = []
        current_price = base_price
        
        for date in business_days:
            # Random walk with slight upward bias
            change = np.random.normal(0.001, 0.02)  # 0.1% daily return, 2% volatility
            current_price *= (1 + change)
            
            stock_data.append({
                'date': date,
                'open': current_price * 0.999,
                'high': current_price * 1.01,
                'low': current_price * 0.99,
                'close': current_price,
                'volume': np.random.randint(1000000, 10000000)
            })
        
        return stock_data
    
    def simulate_options_data(self, stock_data: List[Dict], strategy_params: StrategyParams):
        """Simulate options data based on stock prices"""
        options_data = {}
        
        for stock_day in stock_data:
            date = stock_day['date']
            stock_price = stock_day['close']
            
            # Generate option chains for this day
            options_data[date] = self.generate_option_chain(stock_price, date, strategy_params)
        
        return options_data
    
    def generate_option_chain(self, stock_price: float, current_date: str, strategy_params: StrategyParams):
        """Generate realistic option chain for a given stock price and date"""
        options = []
        
        # Generate strikes around current price
        strikes = []
        for i in range(-10, 11):  # 20 strikes
            strike = round(stock_price * (1 + i * 0.05), 0)  # 5% intervals
            strikes.append(strike)
        
        # Generate different expiration dates
        current_dt = datetime.strptime(current_date, '%Y-%m-%d')
        
        expirations = []
        # Weekly options (Fridays)
        for week in range(1, 9):  # 8 weeks out
            exp_date = current_dt + timedelta(days=7*week)
            # Find next Friday
            days_to_friday = (4 - exp_date.weekday()) % 7
            if days_to_friday == 0 and exp_date.weekday() != 4:
                days_to_friday = 7
            exp_date += timedelta(days=days_to_friday)
            expirations.append(exp_date.strftime('%Y-%m-%d'))
        
        # Monthly options (3rd Friday)
        for month in range(1, 13):  # 12 months out
            exp_date = current_dt.replace(day=15) + timedelta(days=30*month)
            # Find 3rd Friday
            days_to_friday = (4 - exp_date.weekday()) % 7
            exp_date += timedelta(days=days_to_friday)
            if exp_date.day < 15:
                exp_date += timedelta(days=7)
            expirations.append(exp_date.strftime('%Y-%m-%d'))
        
        # Remove duplicates and sort
        expirations = sorted(list(set(expirations)))
        
        for expiration in expirations:
            dte = calculate_dte(expiration, current_date)
            if dte <= 0:
                continue
                
            for strike in strikes:
                if strike <= 0:
                    continue
                    
                # Calculate option metrics
                moneyness = strike / stock_price
                time_value = dte / 365.0
                
                # Simplified Black-Scholes approximation
                intrinsic_value = max(0, stock_price - strike)  # Call option
                
                # Estimate implied volatility based on moneyness and time
                iv = 0.20 + abs(moneyness - 1.0) * 0.1  # Base IV of 20%
                
                # Simplified option price
                option_price = intrinsic_value + (stock_price * iv * np.sqrt(time_value) * 0.4)
                option_price = max(0.01, option_price)  # Minimum $0.01
                
                # Calculate Greeks (simplified)
                delta = self.calculate_delta(stock_price, strike, dte, iv)
                theta = -option_price * 0.02 * (30 / dte) if dte > 0 else 0  # Simplified theta
                
                options.append({
                    'strike': strike,
                    'expiration': expiration,
                    'dte': dte,
                    'option_price': round(option_price, 2),
                    'delta': round(delta, 3),
                    'theta': round(theta, 3),
                    'iv': round(iv, 3),
                    'volume': np.random.randint(10, 1000)
                })
        
        return options
    
    def calculate_delta(self, stock_price: float, strike: float, dte: int, iv: float):
        """Simplified delta calculation"""
        if dte <= 0:
            return 1.0 if stock_price > strike else 0.0
        
        moneyness = stock_price / strike
        time_factor = np.sqrt(dte / 365.0)
        
        # Simplified delta approximation
        if moneyness >= 1.0:  # ITM
            delta = 0.5 + (moneyness - 1.0) * 0.3
        else:  # OTM
            delta = 0.5 * moneyness
        
        # Adjust for time
        delta *= (1.0 - np.exp(-time_factor))
        
        return min(0.99, max(0.01, delta))
    
    def should_open_position(self, current_date: str, strategy_params: StrategyParams) -> bool:
        """Determine if we should open a new position"""
        # Check if it's the right day of week
        date_obj = datetime.strptime(current_date, '%Y-%m-%d')
        day_name = date_obj.strftime('%A')
        
        if strategy_params.entry_day != "Any" and day_name != strategy_params.entry_day:
            return False
        
        # Check if we have enough capital and not too many positions
        open_positions = len([p for p in self.positions if p['status'] == 'open'])
        stock_cost = 100 * 100  # Assume $100 stock price and 100 shares for capital check
        return self.current_capital >= stock_cost and open_positions < 5
    
    def open_covered_call(self, current_date: str, stock_price: float, options_data: Dict, strategy_params: StrategyParams):
        """Open a new covered call position"""
        if current_date not in options_data:
            return
        
        suitable_options = self.find_suitable_options(
            options_data[current_date], stock_price, strategy_params
        )
        
        if not suitable_options:
            return
        
        # Select the best option (closest to target delta)
        best_option = min(suitable_options, 
                         key=lambda x: abs(x['delta'] - strategy_params.delta_target))
        
        # Calculate position size  
        shares_per_contract = 100  # Use 100 shares per contract
        stock_cost = stock_price * shares_per_contract
        option_premium = best_option['option_price'] * shares_per_contract
        
        if self.current_capital >= stock_cost:
            position = {
                'id': str(uuid.uuid4()),
                'open_date': current_date,
                'stock_price': stock_price,
                'shares': strategy_params.shares_per_contract,
                'strike': best_option['strike'],
                'expiration': best_option['expiration'],
                'premium_received': option_premium,
                'delta': best_option['delta'],
                'dte_at_open': best_option['dte'],
                'status': 'open'
            }
            
            self.positions.append(position)
            self.current_capital -= stock_cost
            self.current_capital += option_premium
    
    def find_suitable_options(self, options: List[Dict], stock_price: float, strategy_params: StrategyParams):
        """Find options matching strategy criteria"""
        suitable = []
        
        for option in options:
            # Filter by DTE range (more flexible)
            dte_diff = abs(option['dte'] - strategy_params.dte_target)
            if strategy_params.dte_target <= 7:  # Weekly options
                if dte_diff > 3:  # Within 3 days for weekly
                    continue
            else:  # Monthly options
                if dte_diff > 14:  # Within 2 weeks for monthly
                    continue
            
            # Filter by delta range (more flexible)
            delta_diff = abs(option['delta'] - strategy_params.delta_target)
            if delta_diff > 0.1:  # Within 10 delta points
                continue
            
            # Must be OTM call (but allow closer strikes)
            if option['strike'] <= stock_price * 1.01:  # Allow 1% OTM minimum
                continue
            
            # Must have reasonable option price
            if option['option_price'] < 0.50:  # Minimum $0.50 premium
                continue
            
            suitable.append(option)
        
        return suitable
    
    def manage_positions(self, current_date: str, stock_price: float, options_data: Dict):
        """Manage existing positions"""
        for position in self.positions:
            if position['status'] != 'open':
                continue
            
            # Check if expired
            if current_date >= position['expiration']:
                self.close_position_expiration(position, stock_price)
                continue
            
            # Check profit/loss targets
            if current_date in options_data:
                current_option_price = self.get_current_option_price(position, options_data[current_date])
                if current_option_price:
                    self.check_profit_loss_targets(position, current_option_price, stock_price)
    
    def close_position_expiration(self, position: Dict, stock_price: float):
        """Close position at expiration"""
        if stock_price > position['strike']:
            # Stock called away
            proceeds = position['strike'] * position['shares']
            called_away = True
        else:
            # Keep stock, option expires worthless
            proceeds = stock_price * position['shares']
            called_away = False
        
        total_return = proceeds - (position['stock_price'] * position['shares']) + position['premium_received']
        
        trade = {
            'id': position['id'],
            'open_date': position['open_date'],
            'close_date': position['expiration'],
            'ticker': 'TSLA',  # TODO: make dynamic
            'strategy': 'covered_call',
            'premium_received': position['premium_received'],
            'stock_entry': position['stock_price'],
            'stock_exit': position['strike'] if called_away else stock_price,
            'total_return': total_return,
            'return_pct': total_return / (position['stock_price'] * position['shares']),
            'called_away': called_away,
            'expired_worthless': not called_away,
            'dte_at_open': position['dte_at_open'],
            'delta_at_open': position['delta']
        }
        
        self.closed_trades.append(trade)
        self.current_capital += proceeds
        position['status'] = 'closed'
    
    def get_current_option_price(self, position: Dict, current_options: List[Dict]):
        """Get current option price"""
        for option in current_options:
            if (option['strike'] == position['strike'] and 
                option['expiration'] == position['expiration']):
                return option['option_price']
        return None
    
    def check_profit_loss_targets(self, position: Dict, current_option_price: float, stock_price: float):
        """Check if position hits profit/loss targets"""
        # Calculate current P&L on option
        option_pnl = position['premium_received'] - (current_option_price * position['shares'])
        profit_pct = option_pnl / position['premium_received']
        
        # Close if profit target hit (e.g., 50% of premium captured)
        if profit_pct >= 0.5:  # 50% profit target
            self.close_position_early(position, stock_price, current_option_price, 'profit_target')
        
        # Close if loss limit hit (e.g., 200% of premium lost)
        elif profit_pct <= -2.0:  # 200% loss limit
            self.close_position_early(position, stock_price, current_option_price, 'loss_limit')
    
    def close_position_early(self, position: Dict, stock_price: float, option_price: float, reason: str):
        """Close position before expiration"""
        # Sell stock and buy back option
        stock_proceeds = stock_price * position['shares']
        option_cost = option_price * position['shares']
        
        total_return = stock_proceeds - (position['stock_price'] * position['shares']) + position['premium_received'] - option_cost
        
        trade = {
            'id': position['id'],
            'open_date': position['open_date'],
            'close_date': datetime.now().strftime('%Y-%m-%d'),  # Current date
            'ticker': 'TSLA',  # TODO: make dynamic
            'strategy': 'covered_call',
            'premium_received': position['premium_received'],
            'stock_entry': position['stock_price'],
            'stock_exit': stock_price,
            'option_buyback': option_cost,
            'total_return': total_return,
            'return_pct': total_return / (position['stock_price'] * position['shares']),
            'close_reason': reason,
            'called_away': False,
            'expired_worthless': False,
            'dte_at_open': position['dte_at_open'],
            'delta_at_open': position['delta']
        }
        
        self.closed_trades.append(trade)
        self.current_capital += stock_proceeds - option_cost
        position['status'] = 'closed'
    
    def calculate_portfolio_value(self, current_date: str, stock_price: float, options_data: Dict):
        """Calculate current portfolio value"""
        total_value = self.current_capital
        
        # Add value of open positions
        for position in self.positions:
            if position['status'] == 'open':
                # Stock value
                stock_value = stock_price * position['shares']
                total_value += stock_value
                
                # Option liability
                if current_date in options_data:
                    current_option_price = self.get_current_option_price(position, options_data[current_date])
                    if current_option_price:
                        option_liability = current_option_price * position['shares']
                        total_value -= option_liability
        
        return total_value
    
    def calculate_performance_metrics(self, results: List[Dict]):
        """Calculate performance metrics"""
        if not results:
            return {}
        
        df = pd.DataFrame(results)
        
        initial_value = self.initial_capital
        final_value = df['portfolio_value'].iloc[-1]
        total_return = (final_value - initial_value) / initial_value
        
        # Calculate daily returns
        df['daily_return'] = df['portfolio_value'].pct_change().fillna(0)
        
        # Annualized return
        days = len(df)
        annualized_return = (1 + total_return) ** (252 / days) - 1
        
        # Volatility
        volatility = df['daily_return'].std() * np.sqrt(252)
        
        # Sharpe ratio (assuming 2% risk-free rate)
        risk_free_rate = 0.02
        sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0
        
        # Maximum drawdown
        df['peak'] = df['portfolio_value'].cummax()
        df['drawdown'] = (df['portfolio_value'] - df['peak']) / df['peak']
        max_drawdown = df['drawdown'].min()
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'final_value': final_value,
            'total_days': days
        }
    
    def calculate_covered_call_metrics(self):
        """Calculate covered call specific metrics"""
        if not self.closed_trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_return_per_trade': 0,
                'total_premium_collected': 0,
                'pct_expired_worthless': 0,
                'pct_called_away': 0,
                'avg_dte_at_open': 0,
                'avg_delta_at_open': 0
            }
        
        total_trades = len(self.closed_trades)
        winning_trades = len([t for t in self.closed_trades if t['total_return'] > 0])
        win_rate = winning_trades / total_trades
        
        avg_return = sum(t['total_return'] for t in self.closed_trades) / total_trades
        total_premium = sum(t['premium_received'] for t in self.closed_trades)
        
        expired_worthless = len([t for t in self.closed_trades if t.get('expired_worthless', False)])
        called_away = len([t for t in self.closed_trades if t.get('called_away', False)])
        
        avg_dte = sum(t['dte_at_open'] for t in self.closed_trades) / total_trades
        avg_delta = sum(t['delta_at_open'] for t in self.closed_trades) / total_trades
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_return_per_trade': avg_return,
            'total_premium_collected': total_premium,
            'pct_expired_worthless': expired_worthless / total_trades if total_trades > 0 else 0,
            'pct_called_away': called_away / total_trades if total_trades > 0 else 0,
            'avg_dte_at_open': avg_dte,
            'avg_delta_at_open': avg_delta
        }

# API Endpoints
@app.get("/")
async def root():
    return {"message": "Options Backtesting API", "status": "running"}

@app.post("/api/backtest")
async def run_backtest(request: BacktestRequest):
    """Run a covered call backtest"""
    try:
        backtester = CoveredCallBacktester(request.initial_capital)
        results = backtester.run_backtest(
            request.ticker,
            request.start_date,
            request.end_date,
            request.strategy_params
        )
        
        if "error" in results:
            raise HTTPException(status_code=400, detail=results["error"])
        
        # Save strategy if named
        if request.strategy_name:
            strategy = {
                "id": str(uuid.uuid4()),
                "name": request.strategy_name,
                "ticker": request.ticker,
                "strategy_params": request.strategy_params.dict(),
                "created_at": datetime.now(),
                "tags": []
            }
            strategies_collection.insert_one(strategy)
        
        # Save backtest results
        backtest_result = {
            "id": str(uuid.uuid4()),
            "ticker": request.ticker,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "strategy_params": request.strategy_params.dict(),
            "strategy_name": request.strategy_name,
            "results": results,
            "created_at": datetime.now()
        }
        backtest_results_collection.insert_one(backtest_result)
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")

@app.get("/api/strategies")
async def get_strategies():
    """Get all saved strategies"""
    try:
        strategies = list(strategies_collection.find({}, {"_id": 0}))
        return {"strategies": strategies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching strategies: {str(e)}")

@app.get("/api/backtest-results")
async def get_backtest_results():
    """Get all backtest results"""
    try:
        results = list(backtest_results_collection.find({}, {"_id": 0}).sort("created_at", -1).limit(50))
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching results: {str(e)}")

@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str):
    """Delete a strategy"""
    try:
        result = strategies_collection.delete_one({"id": strategy_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return {"message": "Strategy deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting strategy: {str(e)}")

@app.get("/api/polygon-test")
async def test_polygon_connection():
    """Test Polygon API connection"""
    try:
        client = get_polygon_client()
        # Test with a simple API call
        aggs = list(client.list_aggs(
            ticker="AAPL",
            multiplier=1,
            timespan="day",
            from_="2024-01-01",
            to="2024-01-02",
            limit=5
        ))
        return {
            "status": "success",
            "message": "Polygon API connection successful",
            "sample_data_points": len(aggs)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Polygon API connection failed: {str(e)}"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)