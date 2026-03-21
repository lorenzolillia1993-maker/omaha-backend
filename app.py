from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import requests
import os

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

@app.route('/')
def home():
    return jsonify({"status": "OMAHA
              @app.route('/claude', methods=['POST'])
def claude_proxy():
    try:
        data = request.json
        headers = {
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        }
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            json=data,
            headers=headers,
            timeout=60
        )
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
      @app.route('/quote/<ticker>')
def quote(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        if hist.empty:
            return jsonify({"error": "Ticker non trovato"}), 404
        prev_close = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else float(hist['Close'].iloc[-1])
        price = float(hist['Close'].iloc[-1])
        change = price - prev_close
        change_pct = (change / prev_close) * 100
        info = t.fast_info
        return jsonify({
            "ticker": ticker.upper(),
            "price": round(price, 2),
            "change": round(change, 2),
            "changePct": round(change_pct, 2),
            "volume": int(hist['Volume'].iloc[-1]),
            "high": round(float(hist['High'].iloc[-1]), 2),
            "low": round(float(hist['Low'].iloc[-1]), 2),
            "prevClose": round(prev_close, 2),
            "currency": getattr(info, 'currency', 'USD'),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/technicals/<ticker>')
def technicals(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", interval="1d")
        if hist.empty:
            return jsonify({"error": "Nessun dato"}), 404
        close = hist['Close']
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        return jsonify({
            "rsi": round(float(rsi.iloc[-1]), 1),
            "macd": round(float(macd.iloc[-1]), 3),
            "signal": round(float(signal.iloc[-1]), 3),
            "sma50": round(float(sma50.iloc[-1]), 2),
            "sma200": round(float(sma200.iloc[-1]), 2) if len(close) >= 200 else None,
            "bb_upper": round(float((sma20 + 2*std20).iloc[-1]), 2),
            "bb_lower": round(float((sma20 - 2*std20).iloc[-1]), 2),
            "high52w": round(float(close.rolling(252).max().iloc[-1]), 2),
            "low52w": round(float(close.rolling(252).min().iloc[-1]), 2),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/fundamentals/<ticker>')
def fundamentals(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        income = t.financials
        inc_list = []
        if income is not None and not income.empty:
            for col in income.columns[:5]:
                year = str(col)[:4]
                rev = income.loc['Total Revenue', col] if 'Total Revenue' in income.index else None
                net = income.loc['Net Income', col] if 'Net Income' in income.index else None
                inc_list.append({
                    "year": year,
                    "revenue": int(rev) if rev and rev == rev else None,
                    "netIncome": int(net) if net and net == net else None,
                    "margin": round((net/rev*100), 1) if rev and net and rev != 0 and rev == rev and net == net else None,
                })
        divs = t.dividends
        div_list = []
        if divs is not None and not divs.empty:
            for date, amount in divs.tail(12).items():
                div_list.append({"date": str(date)[:10], "amount": round(float(amount), 4)})
            div_list.reverse()
        return jsonify({
            "name": info.get('longName', ticker),
            "sector": info.get('sector', '—'),
            "industry": info.get('industry', '—'),
            "pe": info.get('trailingPE', None),
            "pb": info.get('priceToBook', None),
            "eps": info.get('trailingEps', None),
            "dividendYield": info.get('dividendYield', None),
            "roe": info.get('returnOnEquity', None),
            "debtToEquity": info.get('debtToEquity', None),
            "profitMargins": info.get('profitMargins', None),
            "revenueGrowth": info.get('revenueGrowth', None),
            "income": inc_list,
            "dividends": div_list,
            "description": (info.get('longBusinessSummary', '') or '')[:400],
        })
    except Exception as e:
       @app.route('/history/<ticker>')
def price_history(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5y", interval="1mo")
        if hist.empty:
            return jsonify([])
        result = []
        for date, row in hist.iterrows():
            result.append({"date": str(date)[:10], "price": round(float(row['Close']), 2)})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/screener')
def screener():
    stocks = [
        {"ticker":"AAPL","name":"Apple Inc.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"MSFT","name":"Microsoft Corp.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"GOOGL","name":"Alphabet Inc.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"AMZN","name":"Amazon.com Inc.","sector":"Consumer","market":"NASDAQ"},
        {"ticker":"NVDA","name":"NVIDIA Corp.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"META","name":"Meta Platforms","sector":"Technology","market":"NASDAQ"},
        {"ticker":"TSLA","name":"Tesla Inc.","sector":"Auto","market":"NASDAQ"},
        {"ticker":"AMD","name":"Advanced Micro Devices","sector":"Technology","market":"NASDAQ"},
        {"ticker":"INTC","name":"Intel Corp.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"NFLX","name":"Netflix Inc.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"JPM","name":"JPMorgan Chase","sector":"Finance","market":"NYSE"},
        {"ticker":"GS","name":"Goldman Sachs","sector":"Finance","market":"NYSE"},
        {"ticker":"BAC","name":"Bank of America","sector":"Finance","market":"NYSE"},
        {"ticker":"V","name":"Visa Inc.","sector":"Finance","market":"NYSE"},
        {"ticker":"MA","name":"Mastercard Inc.","sector":"Finance","market":"NYSE"},
        {"ticker":"KO","name":"Coca-Cola Co.","sector":"Consumer","market":"NYSE"},
        {"ticker":"PEP","name":"PepsiCo Inc.","sector":"Consumer","market":"NASDAQ"},
        {"ticker":"MCD","name":"McDonald's Corp.","sector":"Consumer","market":"NYSE"},
        {"ticker":"NKE","name":"Nike Inc.","sector":"Consumer","market":"NYSE"},
        {"ticker":"WMT","name":"Walmart Inc.","sector":"Consumer","market":"NYSE"},
        {"ticker":"JNJ","name":"Johnson & Johnson","sector":"Healthcare","market":"NYSE"},
        {"ticker":"PFE","name":"Pfizer Inc.","sector":"Healthcare","market":"NYSE"},
        {"ticker":"XOM","name":"ExxonMobil Corp.","sector":"Energy","market":"NYSE"},
        {"ticker":"CVX","name":"Chevron Corp.","sector":"Energy","market":"NYSE"},
        {"ticker":"ENI.MI","name":"ENI SpA","sector":"Energy","market":"MIL"},
        {"ticker":"ENEL.MI","name":"Enel SpA","sector":"Utilities","market":"MIL"},
        {"ticker":"ISP.MI","name":"Intesa Sanpaolo","sector":"Finance","market":"MIL"},
        {"ticker":"UCG.MI","name":"UniCredit SpA","sector":"Finance","market":"MIL"},
        {"ticker":"RACE.MI","name":"Ferrari NV","sector":"Auto","market":"MIL"},
        {"ticker":"STM.MI","name":"STMicroelectronics","sector":"Technology","market":"MIL"},
        {"ticker":"G.MI","name":"Generali Assicurazioni","sector":"Finance","market":"MIL"},
        {"ticker":"TIT.MI","name":"Telecom Italia","sector":"Telecom","market":"MIL"},
        {"ticker":"LDO.MI","name":"Leonardo SpA","sector":"Defense","market":"MIL"},
        {"ticker":"MONC.MI","name":"Moncler SpA","sector":"Luxury","market":"MIL"},
        {"ticker":"TRN.MI","name":"Terna SpA","sector":"Utilities","market":"MIL"},
        {"ticker":"SRG.MI","name":"Snam SpA","sector":"Energy","market":"MIL"},
        {"ticker":"BAMI.MI","name":"Banco BPM","sector":"Finance","market":"MIL"},
    ]
    return jsonify(stocks)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
