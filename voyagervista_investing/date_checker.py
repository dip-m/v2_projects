from dashboard_app.providers.finnhub_analyst import _yahoo_next_earnings
for s in ["AAPL", "MSFT", "NVDA", "SAP.DE", "IBE.MC", "SPY"]:
    print(s, "→", _yahoo_next_earnings(s))
