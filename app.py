from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import json

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return jsonify({"status": "OMAHA Backend attivo", "version": "2.0"})

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    # yfinance non ha search nativa, restituiamo suggerimenti basati su input
    # Usiamo yf.Ticker per validare
    try:
        t = yf.Ticker(q.upper())
        info = t.fast_info
        price = getattr(info, 'last_price', None)
        name = getattr(info, 'quote_type', q.upper())
        return jsonify([{"ticker": q.upper(), "name": name, "price": price}])
    except:
        return jsonify([])

@app.route('/quote/<ticker>')
def quote(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        hist = t.history(period="2d")
        if hist.empty:
            return jsonify({"error": "Ticker non trovato"}), 404
        
        prev_close = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else float(hist['Close'].iloc[-1])
        price = float(hist['Close'].iloc[-1])
        change = price - prev_close
        change_pct = (change / prev_close) * 100

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

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_val = round(float(rsi.iloc[-1]), 1)

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_val = round(float(macd.iloc[-1]), 3)
        signal_val = round(float(signal.iloc[-1]), 3)

        # SMA
        sma50 = round(float(close.rolling(50).mean().iloc[-1]), 2)
        sma200 = round(float(close.rolling(200).mean().iloc[-1]), 2) if len(close) >= 200 else None

        # Bollinger
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = round(float((sma20 + 2*std20).iloc[-1]), 2)
        bb_lower = round(float((sma20 - 2*std20).iloc[-1]), 2)

        # Support / Resistance (52-week)
        high52 = round(float(close.rolling(252).max().iloc[-1]), 2)
        low52  = round(float(close.rolling(252).min().iloc[-1]), 2)

        return jsonify({
            "rsi": rsi_val,
            "macd": macd_val,
            "signal": signal_val,
            "sma50": sma50,
            "sma200": sma200,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "high52w": high52,
            "low52w": low52,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/fundamentals/<ticker>')
def fundamentals(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info

        # Income statement (annual)
        income = t.financials
        balance = t.balance_sheet
        cashflow = t.cashflow

        inc_list = []
        if income is not None and not income.empty:
            for col in income.columns[:5]:
                year = str(col)[:4]
                rev = income.loc['Total Revenue', col] if 'Total Revenue' in income.index else None
                net = income.loc['Net Income', col] if 'Net Income' in income.index else None
                ebit = income.loc['EBIT', col] if 'EBIT' in income.index else None
                eps_val = info.get('trailingEps', None)
                inc_list.append({
                    "year": year,
                    "revenue": int(rev) if rev and not isinstance(rev, float) or rev == rev else None,
                    "netIncome": int(net) if net and net == net else None,
                    "ebit": int(ebit) if ebit and ebit == ebit else None,
                    "margin": round((net/rev*100), 1) if rev and net and rev != 0 and rev == rev and net == net else None,
                })

        # Dividends
        divs = t.dividends
        div_list = []
        if divs is not None and not divs.empty:
            for date, amount in divs.tail(12).items():
                div_list.append({
                    "date": str(date)[:10],
                    "amount": round(float(amount), 4)
                })
            div_list.reverse()

        return jsonify({
            "name": info.get('longName', ticker),
            "sector": info.get('sector', '—'),
            "industry": info.get('industry', '—'),
            "marketCap": info.get('marketCap', None),
            "pe": info.get('trailingPE', None),
            "forwardPE": info.get('forwardPE', None),
            "pb": info.get('priceToBook', None),
            "ps": info.get('priceToSalesTrailing12Months', None),
            "eps": info.get('trailingEps', None),
            "dividendYield": info.get('dividendYield', None),
            "payoutRatio": info.get('payoutRatio', None),
            "roe": info.get('returnOnEquity', None),
            "roa": info.get('returnOnAssets', None),
            "debtToEquity": info.get('debtToEquity', None),
            "currentRatio": info.get('currentRatio', None),
            "revenueGrowth": info.get('revenueGrowth', None),
            "earningsGrowth": info.get('earningsGrowth', None),
            "grossMargins": info.get('grossMargins', None),
            "operatingMargins": info.get('operatingMargins', None),
            "profitMargins": info.get('profitMargins', None),
            "freeCashflow": info.get('freeCashflow', None),
            "beta": info.get('beta', None),
            "52wHigh": info.get('fiftyTwoWeekHigh', None),
            "52wLow": info.get('fiftyTwoWeekLow', None),
            "targetPrice": info.get('targetMeanPrice', None),
            "analystRating": info.get('recommendationMean', None),
            "income": inc_list,
            "dividends": div_list,
            "description": info.get('longBusinessSummary', '')[:500] if info.get('longBusinessSummary') else '',
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history/<ticker>')
def price_history(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5y", interval="1mo")
        if hist.empty:
            return jsonify([])
        result = []
        for date, row in hist.iterrows():
            result.append({
                "date": str(date)[:10],
                "price": round(float(row['Close']), 2),
                "volume": int(row['Volume'])
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/screener')
def screener():
    """Returns a curated list of popular stocks for the search page"""
    stocks = [
        # USA Tech
        {"ticker":"AAPL","name":"Apple Inc.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"MSFT","name":"Microsoft Corp.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"GOOGL","name":"Alphabet Inc.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"AMZN","name":"Amazon.com Inc.","sector":"Consumer","market":"NASDAQ"},
        {"ticker":"NVDA","name":"NVIDIA Corp.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"META","name":"Meta Platforms","sector":"Technology","market":"NASDAQ"},
        {"ticker":"TSLA","name":"Tesla Inc.","sector":"Auto","market":"NASDAQ"},
        {"ticker":"AMD","name":"Advanced Micro Devices","sector":"Technology","market":"NASDAQ"},
        {"ticker":"INTC","name":"Intel Corp.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"NFLX","name":"Netflix Inc.","sector":"Media","market":"NASDAQ"},
        {"ticker":"ORCL","name":"Oracle Corp.","sector":"Technology","market":"NYSE"},
        {"ticker":"CRM","name":"Salesforce Inc.","sector":"Technology","market":"NYSE"},
        {"ticker":"ADBE","name":"Adobe Inc.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"QCOM","name":"Qualcomm Inc.","sector":"Technology","market":"NASDAQ"},
        {"ticker":"AVGO","name":"Broadcom Inc.","sector":"Technology","market":"NASDAQ"},
        # USA Finance
        {"ticker":"JPM","name":"JPMorgan Chase","sector":"Finance","market":"NYSE"},
        {"ticker":"GS","name":"Goldman Sachs","sector":"Finance","market":"NYSE"},
        {"ticker":"BAC","name":"Bank of America","sector":"Finance","market":"NYSE"},
        {"ticker":"MS","name":"Morgan Stanley","sector":"Finance","market":"NYSE"},
        {"ticker":"V","name":"Visa Inc.","sector":"Finance","market":"NYSE"},
        {"ticker":"MA","name":"Mastercard Inc.","sector":"Finance","market":"NYSE"},
        {"ticker":"BRK-B","name":"Berkshire Hathaway","sector":"Finance","market":"NYSE"},
        # USA Consumer
        {"ticker":"KO","name":"Coca-Cola Co.","sector":"Consumer","market":"NYSE"},
        {"ticker":"PEP","name":"PepsiCo Inc.","sector":"Consumer","market":"NASDAQ"},
        {"ticker":"MCD","name":"McDonald's Corp.","sector":"Consumer","market":"NYSE"},
        {"ticker":"NKE","name":"Nike Inc.","sector":"Consumer","market":"NYSE"},
        {"ticker":"WMT","name":"Walmart Inc.","sector":"Consumer","market":"NYSE"},
        {"ticker":"COST","name":"Costco Wholesale","sector":"Consumer","market":"NASDAQ"},
        {"ticker":"SBUX","name":"Starbucks Corp.","sector":"Consumer","market":"NASDAQ"},
        # USA Healthcare
        {"ticker":"JNJ","name":"Johnson & Johnson","sector":"Healthcare","market":"NYSE"},
        {"ticker":"PFE","name":"Pfizer Inc.","sector":"Healthcare","market":"NYSE"},
        {"ticker":"MRK","name":"Merck & Co.","sector":"Healthcare","market":"NYSE"},
        {"ticker":"ABBV","name":"AbbVie Inc.","sector":"Healthcare","market":"NYSE"},
        {"ticker":"UNH","name":"UnitedHealth Group","sector":"Healthcare","market":"NYSE"},
        # USA Energy
        {"ticker":"XOM","name":"ExxonMobil Corp.","sector":"Energy","market":"NYSE"},
        {"ticker":"CVX","name":"Chevron Corp.","sector":"Energy","market":"NYSE"},
        # Italia - Borsa Milano
        {"ticker":"ENI.MI","name":"ENI SpA","sector":"Energy","market":"MIL"},
        {"ticker":"ENEL.MI","name":"Enel SpA","sector":"Utilities","market":"MIL"},
        {"ticker":"ISP.MI","name":"Intesa Sanpaolo","sector":"Finance","market":"MIL"},
        {"ticker":"UCG.MI","name":"UniCredit SpA","sector":"Finance","market":"MIL"},
        {"ticker":"RACE.MI","name":"Ferrari NV","sector":"Auto","market":"MIL"},
        {"ticker":"STM.MI","name":"STMicroelectronics","sector":"Technology","market":"MIL"},
        {"ticker":"MB.MI","name":"Mediobanca","sector":"Finance","market":"MIL"},
        {"ticker":"G.MI","name":"Generali Assicurazioni","sector":"Finance","market":"MIL"},
        {"ticker":"TIT.MI","name":"Telecom Italia","sector":"Telecom","market":"MIL"},
        {"ticker":"PRY.MI","name":"Prysmian SpA","sector":"Industrial","market":"MIL"},
        {"ticker":"LDO.MI","name":"Leonardo SpA","sector":"Defense","market":"MIL"},
        {"ticker":"MONC.MI","name":"Moncler SpA","sector":"Luxury","market":"MIL"},
        {"ticker":"CPR.MI","name":"Amplifon SpA","sector":"Healthcare","market":"MIL"},
        {"ticker":"FCA.MI","name":"Stellantis NV","sector":"Auto","market":"MIL"},
        {"ticker":"BAMI.MI","name":"Banco BPM","sector":"Finance","market":"MIL"},
        {"ticker":"AZM.MI","name":"Azimut Holding","sector":"Finance","market":"MIL"},
        {"ticker":"INWT.MI","name":"Inwit SpA","sector":"Telecom","market":"MIL"},
        {"ticker":"TRN.MI","name":"Terna SpA","sector":"Utilities","market":"MIL"},
        {"ticker":"SRG.MI","name":"Snam SpA","sector":"Energy","market":"MIL"},
        {"ticker":"CNHI.MI","name":"CNH Industrial","sector":"Industrial","market":"MIL"},
    ]
    return jsonify(stocks)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
