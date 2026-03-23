import sys
sys.path.insert(0, '.')

import os
os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-test'
os.environ['MT5_LOGIN'] = '12345'
os.environ['MT5_PASSWORD'] = 'test'
os.environ['MT5_SERVER'] = 'Demo'
os.environ['TRADING_MODE'] = 'demo'
os.environ['RISK_PER_TRADE'] = '0.01'

from config import Config
c = Config()
print(f"Config OK: mode={c.trading_mode}, risk={c.risk_per_trade}")

from data.yfinance_connector import YFinanceConnector
yf = YFinanceConnector()
df = yf.get_ohlcv("AAPL", "15m", 10)
print(f"yfinance OK: {len(df)} Zeilen geladen")

from agents.trend_agent import TrendAgent
agent = TrendAgent(config=c, data_connector=yf)
result = agent.analyze(symbol="AAPL")
print(f"TrendAgent OK: direction={result.get('direction')}, strength={result.get('strength_score')}")

from agents.volatility_agent import VolatilityAgent
va = VolatilityAgent(config=c, data_connector=yf)
result = va.analyze(symbol="AAPL")
print(f"VolatilityAgent OK: volatility_ok={result.get('volatility_ok')}, atr={result.get('atr_value')}")

from agents.risk_agent import RiskAgent
ra = RiskAgent(config=c)
result = ra.calculate(
    entry_price=150.0,
    direction='long',
    atr=2.5,
    account_balance=10000
)
print(f"RiskAgent OK: sl={result.get('stop_loss')}, tp={result.get('take_profit')}, crv={result.get('crv')}")

print("\n=== ALLE TESTS BESTANDEN ===")
