from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import yfinance as yf
import requests
import os
import json

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')

def ask_groq(system, user):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.7,
        "max_tokens": 2000
    }
    r = requests.post(url, json=body, headers=headers, timeout=60)
    data = r.json()
    if 'choices' not in data:
        raise Exception(f"Groq error: {data.get('error', {}).get('message', str(data))}")
    text = data['choices'][0]['message']['content']
    text = text.replace('```json','').replace('```','').strip()
    return text

@app.route('/')
def home():
    return jsonify({"status": "OMAHA Backend attivo", "version": "6.0"})

@app.route('/app')
def serve_app():
    return render_template('index.html')

@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&lang=it-IT&region=IT&quotesCount=20&newsCount=0&listsCount=0"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        results = []
        for item in data.get('quotes', []):
            if item.get('quoteType') in ['EQUITY', 'ETF']:
                results.append({
                    "ticker": item.get('symbol', ''),
                    "name": item.get('longname') or item.get('shortname', ''),
                    "exchange": item.get('exchange', ''),
                    "type": item.get('quoteType', ''),
                    "sector": item.get('sector', '—'),
                })
        return jsonify(results[:15])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
            prev = float(hist2['Close'].iloc[-2]) if len(hist2) >= 2 else float(hist2['Close'].iloc[-1])
            price = float(hist2['Close'].iloc[-1])
            change = price - prev
            quote = {
                "price": round(price, 2),
                "change": round(change, 2),
                "changePct": round((change/prev)*100, 2),
                "volume": int(hist2['Volume'].iloc[-1]),
                "high": round(float(hist2['High'].iloc[-1]), 2),
                "low": round(float(hist2['Low'].iloc[-1]), 2),
                "prevClose": round(prev, 2),
                "currency": getattr(t.fast_info, 'currency', 'USD'),
            }

        tech = None
        if not hist_daily.empty:
            close = hist_daily['Close']
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9).mean()
            sma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            tech = {
                "rsi": round(float(rsi.iloc[-1]), 1),
                "macd": round(float(macd.iloc[-1]), 3),
                "signal": round(float(signal.iloc[-1]), 3),
                "sma50": round(float(close.rolling(50).mean().iloc[-1]), 2),
                "sma200": round(float(close.rolling(200).mean().iloc[-1]), 2) if len(close) >= 200 else None,
                "bb_upper": round(float((sma20 + 2*std20).iloc[-1]), 2),
                "bb_lower": round(float((sma20 - 2*std20).iloc[-1]), 2),
                "high52w": round(float(close.rolling(252).max().iloc[-1]), 2),
                "low52w": round(float(close.rolling(252).min().iloc[-1]), 2),
            }

        income = t.financials
        inc_list = []
        if income is not None and not income.empty:
            for col in income.columns[:5]:
                rev = income.loc['Total Revenue', col] if 'Total Revenue' in income.index else None
                net = income.loc['Net Income', col] if 'Net Income' in income.index else None
                inc_list.append({
                    "year": str(col)[:4],
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

        history = []
        if not hist_monthly.empty:
            for date, row in hist_monthly.iterrows():
                history.append({"date": str(date)[:10], "price": round(float(row['Close']), 2)})

        fund = {
            "name": info.get('longName', ticker),
            "sector": info.get('sector', '—'),
            "industry": info.get('industry', '—'),
            "country": info.get('country', '—'),
            "pe": info.get('trailingPE', None),
            "pb": info.get('priceToBook', None),
            "eps": info.get('trailingEps', None),
            "dividendYield": info.get('dividendYield', None),
            "roe": info.get('returnOnEquity', None),
            "debtToEquity": info.get('debtToEquity', None),
            "profitMargins": info.get('profitMargins', None),
            "beta": info.get('beta', None),
            "marketCap": info.get('marketCap', None),
            "income": inc_list,
            "dividends": div_list,
            "description": (info.get('longBusinessSummary', '') or '')[:400],
        }

        fin_summary = "Dati non disponibili."
        if inc_list:
            fin_summary = "\n".join([f"{r['year']}: Ricavi {r['revenue']}, Utile {r['netIncome']}, Margine {r['margin']}%" for r in inc_list])
        if div_list:
            fin_summary += "\nDividendi: " + ", ".join([f"{d['date'][:7]} ${d['amount']}" for d in div_list[:4]])

        price_info = f"Prezzo=${quote['price'] if quote else 'N/D'}"
        tech_info = f"RSI={tech['rsi'] if tech else 'N/D'}, MACD={tech['macd'] if tech else 'N/D'}, SMA50={tech['sma50'] if tech else 'N/D'}, SMA200={tech['sma200'] if tech else 'N/D'}, BB_upper={tech['bb_upper'] if tech else 'N/D'}, BB_lower={tech['bb_lower'] if tech else 'N/D'}, Max52w={tech['high52w'] if tech else 'N/D'}, Min52w={tech['low52w'] if tech else 'N/D'}"
        fund_info = f"Settore={fund['sector']}, Paese={fund['country']}, PE={fund['pe']}, ROE={fund['roe']}, Margine={fund['profitMargins']}, D/E={fund['debtToEquity']}, Beta={fund['beta']}, DivYield={fund['dividendYield']}"
        temporal_schema = '"prev_1m":"outlook","prev_3m":"outlook","prev_6m":"outlook","prev_1a":"outlook","prev_3a":"outlook","prev_5a":"outlook"'

        # AGENTE 1: TECNICO
        tech_ai = json.loads(ask_groq(
            "Sei un analista tecnico senior. Rispondi SOLO JSON valido.",
            f"Analizza {ticker} ({fund['name']}). {price_info}, {tech_info}. Rispondi SOLO JSON: {{\"score\":7,\"trend\":\"RIALZISTA\",\"forza\":\"FORTE\",\"segnale\":\"COMPRA\",\"supporto\":\"livello\",\"resistenza\":\"livello\",\"analisi\":\"150 parole italiano\",\"punti_forza\":[\"p1\",\"p2\"],\"punti_debolezza\":[\"p1\",\"p2\"],{temporal_schema}}}"
        ))

        # AGENTE 2: FONDAMENTALE
        fund_ai = json.loads(ask_groq(
            "Sei un analista fondamentale senior. Rispondi SOLO JSON valido.",
            f"Analizza {ticker} ({fund['name']}). {fund_info}. Bilanci: {fin_summary}. Rispondi SOLO JSON: {{\"score\":7,\"valutazione\":\"SOTTOVALUTATA\",\"moat\":\"AMPIO\",\"qualita\":\"BUONA\",\"segnale\":\"COMPRA\",\"analisi\":\"150 parole italiano\",\"punti_forza\":[\"p1\",\"p2\"],\"punti_debolezza\":[\"p1\",\"p2\"],{temporal_schema}}}"
        ))

        # AGENTE 3: GEOPOLITICO
        geo_ai = json.loads(ask_groq(
            "Sei un analista geopolitico senior specializzato in impatti sui mercati finanziari. Rispondi SOLO JSON valido.",
            f"Analizza l impatto geopolitico su {ticker} ({fund['name']}, settore {fund['sector']}, paese {fund['country']}). Considera tensioni internazionali, sanzioni, guerre commerciali, rischi regionali, relazioni diplomatiche che impattano questo titolo. Rispondi SOLO JSON: {{\"score\":7,\"rischio_geopolitico\":\"ALTO|MEDIO|BASSO\",\"aree_rischio\":[\"area1\",\"area2\"],\"opportunita_geo\":[\"opp1\",\"opp2\"],\"segnale\":\"COMPRA|VENDI|NEUTRO|ATTENDI\",\"analisi\":\"150 parole italiano focalizzata su come la geopolitica influenzerà il prezzo\",{temporal_schema}}}"
        ))

        # AGENTE 4: ECONOMETRICO
        prices_str = ",".join([str(h['price']) for h in history[-24:]]) if history else "N/D"
        eco_ai = json.loads(ask_groq(
            "Sei un econometrista quantitativo senior specializzato in modelli predittivi dei mercati. Rispondi SOLO JSON valido.",
            f"Esegui analisi econometrica approfondita di {ticker} ({fund['name']}). Prezzi mensili ultimi 2 anni: [{prices_str}]. Beta={fund['beta']}, Volatilità implicita dai dati. Applica modelli ARIMA, regressione, analisi della volatilità, mean reversion, momentum per prevedere l andamento futuro del prezzo. Rispondi SOLO JSON: {{\"score\":7,\"volatilita\":\"ALTA|MEDIA|BASSA\",\"trend_statistico\":\"RIALZISTA|RIBASSISTA|LATERALE\",\"mean_reversion\":\"SI|NO\",\"momentum\":\"POSITIVO|NEGATIVO|NEUTRO\",\"segnale\":\"COMPRA|VENDI|NEUTRO|ATTENDI\",\"analisi\":\"150 parole italiano con focus su previsione quantitativa prezzo\",{temporal_schema}}}"
        ))

        # AGENTE 5: MACROECONOMICO
        macro_ai = json.loads(ask_groq(
            "Sei un analista macroeconomico senior specializzato in impatti macro sui mercati. Rispondi SOLO JSON valido.",
            f"Analizza l impatto macroeconomico su {ticker} ({fund['name']}, settore {fund['sector']}). Considera: tassi di interesse Fed/BCE, inflazione, PIL, disoccupazione, politiche monetarie, ciclo economico, credito, curva dei rendimenti. Come questi fattori macro influenzeranno il prezzo del titolo. Rispondi SOLO JSON: {{\"score\":7,\"ciclo_economico\":\"ESPANSIONE|PICCO|RECESSIONE|RIPRESA\",\"impatto_tassi\":\"POSITIVO|NEGATIVO|NEUTRO\",\"impatto_inflazione\":\"POSITIVO|NEGATIVO|NEUTRO\",\"segnale\":\"COMPRA|VENDI|NEUTRO|ATTENDI\",\"analisi\":\"150 parole italiano focalizzata su come il macro influenzerà il prezzo\",{temporal_schema}}}"
        ))

        # AGENTE 6: ARBITRO FINALE (tutti e 5 gli agenti)
        arb_ai = json.loads(ask_groq(
            "Sei il direttore di un sistema multi-agente di analisi finanziaria. Sintetizzi i report di 5 agenti specializzati. Rispondi SOLO JSON valido.",
            f"""Ticker: {ticker} ({fund['name']})
TECNICO (score {tech_ai['score']}/10): segnale={tech_ai['segnale']}, trend={tech_ai.get('trend','N/D')}
FONDAMENTALE (score {fund_ai['score']}/10): segnale={fund_ai['segnale']}, valutazione={fund_ai.get('valutazione','N/D')}
GEOPOLITICO (score {geo_ai['score']}/10): segnale={geo_ai['segnale']}, rischio={geo_ai.get('rischio_geopolitico','N/D')}
ECONOMETRICO (score {eco_ai['score']}/10): segnale={eco_ai['segnale']}, trend={eco_ai.get('trend_statistico','N/D')}
MACROECONOMICO (score {macro_ai['score']}/10): segnale={macro_ai['segnale']}, ciclo={macro_ai.get('ciclo_economico','N/D')}
Sintetizza tutto in un verdetto finale considerando tutti gli agenti. Rispondi SOLO JSON: {{"score_finale":7,"verdetto":"COMPRA","confidenza":"ALTA","rischio":"MEDIO","sintesi":"250 parole italiano che confronta tutti gli agenti e motiva il verdetto","catalyst_pos":["c1","c2","c3"],"catalyst_neg":["r1","r2","r3"],"prev_1m":"outlook dettagliato","prev_3m":"outlook dettagliato","prev_6m":"outlook dettagliato","prev_1a":"outlook dettagliato","prev_3a":"outlook dettagliato","prev_5a":"outlook dettagliato","accordo_agenti":"TOTALE|MAGGIORANZA|DIVISI","voti":{{"compra":3,"attendi":1,"vendi":1}}}}"""
        ))

        return jsonify({
            "ticker": ticker.upper(),
            "quote": quote,
            "tech": tech,
            "fund": fund,
            "tech_ai": tech_ai,
            "fund_ai": fund_ai,
            "geo_ai": geo_ai,
            "eco_ai": eco_ai,
            "macro_ai": macro_ai,
            "arb_ai": arb_ai,
            "history": history,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
