from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import requests
import os
from flask import render_template

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

def ask_gemini(system, user):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1500}
    }
    r = requests.post(url, json=body, timeout=60)
    data = r.json()
    text = data['candidates'][0]['content']['parts'][0]['text']
    text = text.replace('```json','').replace('```','').strip()
    return text

@app.route('/')
def home():
    return jsonify({"status": "OMAHA Backend attivo", "version": "4.0"})

@app.route('/app')
def serve_app():
    return render_template('index.html')

@app.route('/analyze/<ticker>')
def analyze(ticker):
    try:
        t = yf.Ticker(ticker)
        hist_daily = t.history(period="1y", interval="1d")
        hist_monthly = t.history(period="5y", interval="1mo")
        info = t.info
        hist2 = t.history(period="2d")
        quote = None
        if not hist2.empty:
            prev = float(hist2['Close'].iloc[-2]) if len(hist2)>=2 else float(hist2['Close'].iloc[-1])
            price = float(hist2['Close'].iloc[-1])
            change = price - prev
            quote = {
                "price": round(price,2), "change": round(change,2),
                "changePct": round((change/prev)*100,2),
                "volume": int(hist2['Volume'].iloc[-1]),
                "high": round(float(hist2['High'].iloc[-1]),2),
                "low": round(float(hist2['Low'].iloc[-1]),2),
                "prevClose": round(prev,2),
                "currency": getattr(t.fast_info,'currency','USD'),
            }
        tech = None
        if not hist_daily.empty:
            close = hist_daily['Close']
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain/loss
            rsi = 100-(100/(1+rs))
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd = ema12-ema26
            signal = macd.ewm(span=9).mean()
            sma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            tech = {
                "rsi": round(float(rsi.iloc[-1]),1),
                "macd": round(float(macd.iloc[-1]),3),
                "signal": round(float(signal.iloc[-1]),3),
                "sma50": round(float(close.rolling(50).mean().iloc[-1]),2),
                "sma200": round(float(close.rolling(200).mean().iloc[-1]),2) if len(close)>=200 else None,
                "bb_upper": round(float((sma20+2*std20).iloc[-1]),2),
                "bb_lower": round(float((sma20-2*std20).iloc[-1]),2),
                "high52w": round(float(close.rolling(252).max().iloc[-1]),2),
                "low52w": round(float(close.rolling(252).min().iloc[-1]),2),
            }
        income = t.financials
        inc_list = []
        if income is not None and not income.empty:
            for col in income.columns[:5]:
                rev = income.loc['Total Revenue',col] if 'Total Revenue' in income.index else None
                net = income.loc['Net Income',col] if 'Net Income' in income.index else None
                inc_list.append({
                    "year": str(col)[:4],
                    "revenue": int(rev) if rev and rev==rev else None,
                    "netIncome": int(net) if net and net==net else None,
                    "margin": round((net/rev*100),1) if rev and net and rev!=0 and rev==rev and net==net else None,
                })
        divs = t.dividends
        div_list = []
        if divs is not None and not divs.empty:
            for date,amount in divs.tail(12).items():
                div_list.append({"date":str(date)[:10],"amount":round(float(amount),4)})
            div_list.reverse()
        history = []
        if not hist_monthly.empty:
            for date,row in hist_monthly.iterrows():
                history.append({"date":str(date)[:10],"price":round(float(row['Close']),2)})
        fund = {
            "name": info.get('longName',ticker),
            "sector": info.get('sector','—'),
            "industry": info.get('industry','—'),
            "pe": info.get('trailingPE',None),
            "pb": info.get('priceToBook',None),
            "eps": info.get('trailingEps',None),
            "dividendYield": info.get('dividendYield',None),
            "roe": info.get('returnOnEquity',None),
            "debtToEquity": info.get('debtToEquity',None),
            "profitMargins": info.get('profitMargins',None),
            "income": inc_list,
            "dividends": div_list,
            "description": (info.get('longBusinessSummary','') or '')[:300],
        }
        fin_summary = "Dati non disponibili."
        if inc_list:
            fin_summary = "\n".join([f"{r['year']}: Ricavi {r['revenue']}, Utile {r['netIncome']}, Margine {r['margin']}%" for r in inc_list])
        if div_list:
            fin_summary += f"\nDividendi recenti: {', '.join([f\"{d['date'][:7]} ${d['amount']}\" for d in div_list[:4]])}"

        tech_prompt = f"""Sei un analista tecnico senior. Analizza {ticker} ({fund['name']}).
Dati reali: Prezzo ${quote['price'] if quote else 'N/D'}, RSI={tech['rsi'] if tech else 'N/D'}, MACD={tech['macd'] if tech else 'N/D'}, SMA50={tech['sma50'] if tech else 'N/D'}, SMA200={tech['sma200'] if tech else 'N/D'}, BB_upper={tech['bb_upper'] if tech else 'N/D'}, BB_lower={tech['bb_lower'] if tech else 'N/D'}, Max52w={tech['high52w'] if tech else 'N/D'}, Min52w={tech['low52w'] if tech else 'N/D'}
Rispondi SOLO JSON valido: {{"score":7,"trend":"RIALZISTA","forza":"FORTE","segnale":"COMPRA","supporto":"livello","resistenza":"livello","analisi":"180 parole italiano","punti_forza":["p1","p2","p3"],"punti_debolezza":["p1","p2"]}}"""

        fund_prompt = f"""Sei un analista fondamentale senior. Analizza {ticker} ({fund['name']}).
Settore: {fund['sector']}. PE={fund['pe']}, ROE={fund['roe']}, Margine={fund['profitMargins']}, D/E={fund['debtToEquity']}, DivYield={fund['dividendYield']}
Bilanci 5 anni: {fin_summary}
Rispondi SOLO JSON valido: {{"score":7,"valutazione":"SOTTOVALUTATA","moat":"AMPIO","qualita":"BUONA","segnale":"COMPRA","analisi":"180 parole italiano","punti_forza":["p1","p2","p3"],"punti_debolezza":["p1","p2"],"prev_breve":"testo","prev_medio":"testo","prev_lungo":"testo"}}"""

        import json
        tech_ai = json.loads(ask_gemini("Sei un analista tecnico. Rispondi SOLO JSON.", tech_prompt))
        fund_ai = json.loads(ask_gemini("Sei un analista fondamentale. Rispondi SOLO JSON.", fund_prompt))

        arb_prompt = f"""Sei l arbitro di un sistema multi-agente. Analizza {ticker}.
TECNICO score={tech_ai['score']}, segnale={tech_ai['segnale']}, analisi={tech_ai['analisi']}
FONDAMENTALE score={fund_ai['score']}, segnale={fund_ai['segnale']}, analisi={fund_ai['analisi']}
Rispondi SOLO JSON valido: {{"score_finale":7,"verdetto":"COMPRA","confidenza":"ALTA","rischio":"MEDIO","orizzonte":"MEDIO (6-12 mesi)","target_upside":"+15%","accordo":"CONCORDANO","sintesi":"220 parole italiano","previsione":"100 parole italiano","catalyst_pos":["c1","c2"],"catalyst_neg":["r1","r2"]}}"""

        arb_ai = json.loads(ask_gemini("Sei un arbitro finanziario. Rispondi SOLO JSON.", arb_prompt))

        return jsonify({
            "ticker": ticker.upper(),
            "quote": quote,
            "tech": tech,
            "fund": fund,
            "tech_ai": tech_ai,
            "fund_ai": fund_ai,
            "arb_ai": arb_ai,
            "history": history,
        })
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
