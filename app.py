from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import yfinance as yf
import requests
import os
import json

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')

def ask_groq(system, user, max_tokens=2500):
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
        "max_tokens": max_tokens
    }
    r = requests.post(url, json=body, headers=headers, timeout=90)
    data = r.json()
    if 'choices' not in data:
        raise Exception(f"Groq error: {data.get('error', {}).get('message', str(data))}")
    text = data['choices'][0]['message']['content']
    text = text.replace('```json','').replace('```','').strip()
    return text

@app.route('/')
def home():
    return jsonify({"status": "OMAHA Backend attivo", "version": "7.0"})

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

def get_market_data(ticker):
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
        "targetPrice": info.get('targetMeanPrice', None),
        "analystRating": info.get('recommendationMean', None),
        "income": inc_list,
        "dividends": div_list,
        "description": (info.get('longBusinessSummary', '') or '')[:600],
    }

    return quote, tech, fund, history

def run_all_agents(ticker, fund, quote, tech, history, extra_context=""):
    fin_summary = "Dati non disponibili."
    if fund['income']:
        fin_summary = "\n".join([f"{r['year']}: Ricavi {r['revenue']}, Utile {r['netIncome']}, Margine {r['margin']}%" for r in fund['income']])
    if fund['dividends']:
        fin_summary += "\nDividendi: " + ", ".join([f"{d['date'][:7]} ${d['amount']}" for d in fund['dividends'][:4]])

    price_info = f"Prezzo=${quote['price'] if quote else 'N/D'}, Var={quote['changePct'] if quote else 'N/D'}%"
    tech_info = f"RSI={tech['rsi'] if tech else 'N/D'}, MACD={tech['macd'] if tech else 'N/D'}, SMA50={tech['sma50'] if tech else 'N/D'}, SMA200={tech['sma200'] if tech else 'N/D'}, BB_upper={tech['bb_upper'] if tech else 'N/D'}, BB_lower={tech['bb_lower'] if tech else 'N/D'}, Max52w={tech['high52w'] if tech else 'N/D'}, Min52w={tech['low52w'] if tech else 'N/D'}"
    fund_info = f"Settore={fund['sector']}, Paese={fund['country']}, PE={fund['pe']}, ROE={fund['roe']}, Margine={fund['profitMargins']}, D/E={fund['debtToEquity']}, Beta={fund['beta']}, DivYield={fund['dividendYield']}, MarketCap={fund['marketCap']}"
    prices_str = ",".join([str(h['price']) for h in history[-24:]]) if history else "N/D"
    temporal_schema = '"prev_1m":"outlook","prev_3m":"outlook","prev_6m":"outlook","prev_1a":"outlook","prev_3a":"outlook","prev_5a":"outlook"'
    ctx = f"\nCONTESTO AGGIUNTIVO: {extra_context}" if extra_context else ""

    # AGENTE 1: TECNICO
    tech_ai = json.loads(ask_groq(
        "Sei un analista tecnico senior con 20 anni esperienza. Analisi approfondita e dettagliata. Rispondi SOLO JSON valido.",
        f"Analizza {ticker} ({fund['name']}). {price_info}, {tech_info}.{ctx} Rispondi SOLO JSON: {{\"score\":7,\"trend\":\"RIALZISTA\",\"forza\":\"FORTE\",\"segnale\":\"COMPRA\",\"supporto\":\"livello\",\"resistenza\":\"livello\",\"analisi\":\"250 parole italiano approfondite su trend pattern indicatori livelli chiave\",\"punti_forza\":[\"p1\",\"p2\",\"p3\"],\"punti_debolezza\":[\"p1\",\"p2\"],{temporal_schema}}}"
    ))

    # AGENTE 2: FONDAMENTALE
    fund_ai = json.loads(ask_groq(
        "Sei un analista fondamentale senior con 20 anni esperienza. Analisi approfondita. Rispondi SOLO JSON valido.",
        f"Analizza {ticker} ({fund['name']}). {fund_info}. Bilanci: {fin_summary}. Descrizione: {fund['description'][:300]}.{ctx} Rispondi SOLO JSON: {{\"score\":7,\"valutazione\":\"SOTTOVALUTATA\",\"moat\":\"AMPIO\",\"qualita\":\"BUONA\",\"segnale\":\"COMPRA\",\"analisi\":\"250 parole italiano approfondite su bilanci valutazione qualita business\",\"punti_forza\":[\"p1\",\"p2\",\"p3\"],\"punti_debolezza\":[\"p1\",\"p2\"],{temporal_schema}}}"
    ))

    # AGENTE 3: GEOPOLITICO
    geo_ai = json.loads(ask_groq(
        "Sei un analista geopolitico senior specializzato in impatti sui mercati. Rispondi SOLO JSON valido.",
        f"Analizza impatto geopolitico su {ticker} ({fund['name']}, settore {fund['sector']}, paese {fund['country']}).{ctx} Considera tensioni internazionali, sanzioni, guerre commerciali, rischi regionali. Rispondi SOLO JSON: {{\"score\":7,\"rischio_geopolitico\":\"MEDIO\",\"aree_rischio\":[\"area1\",\"area2\"],\"opportunita_geo\":[\"opp1\",\"opp2\"],\"segnale\":\"COMPRA\",\"analisi\":\"250 parole italiano su come geopolitica influenzerà il prezzo\",{temporal_schema}}}"
    ))

    # AGENTE 4: ECONOMETRICO
    eco_ai = json.loads(ask_groq(
        "Sei un econometrista quantitativo senior. Rispondi SOLO JSON valido.",
        f"Analisi econometrica {ticker} ({fund['name']}). Prezzi mensili: [{prices_str}]. Beta={fund['beta']}.{ctx} Applica ARIMA, regressione, volatilità, mean reversion, momentum. Rispondi SOLO JSON: {{\"score\":7,\"volatilita\":\"MEDIA\",\"trend_statistico\":\"RIALZISTA\",\"mean_reversion\":\"SI\",\"momentum\":\"POSITIVO\",\"segnale\":\"COMPRA\",\"analisi\":\"250 parole italiano con focus su previsione quantitativa prezzo\",{temporal_schema}}}"
    ))

    # AGENTE 5: MACROECONOMICO
    macro_ai = json.loads(ask_groq(
        "Sei un analista macroeconomico senior. Rispondi SOLO JSON valido.",
        f"Analizza impatto macroeconomico su {ticker} ({fund['name']}, settore {fund['sector']}).{ctx} Considera tassi Fed/BCE, inflazione, PIL, ciclo economico, curva rendimenti. Rispondi SOLO JSON: {{\"score\":7,\"ciclo_economico\":\"ESPANSIONE\",\"impatto_tassi\":\"POSITIVO\",\"impatto_inflazione\":\"NEUTRO\",\"segnale\":\"COMPRA\",\"analisi\":\"250 parole italiano su come macro influenzerà il prezzo\",{temporal_schema}}}"
    ))

    # AGENTE 6: ANALISI DI MERCATO E POSIZIONAMENTO
    market_ai = json.loads(ask_groq(
        "Sei un analista di mercato e strategia competitiva senior. Rispondi SOLO JSON valido.",
        f"Analizza posizionamento competitivo di {ticker} ({fund['name']}, settore {fund['sector']}, industria {fund['industry']}).{ctx} Analizza: quota di mercato, vantaggio competitivo, competitor principali, barriere entrata, trend settore, potenziale crescita mercato, minacce disruption, pricing power, brand strength. Rispondi SOLO JSON: {{\"score\":7,\"posizionamento\":\"LEADER|CHALLENGER|FOLLOWER|NICHE\",\"quota_mercato\":\"ALTA|MEDIA|BASSA\",\"competitor_principali\":[\"c1\",\"c2\",\"c3\"],\"trend_settore\":\"CRESCITA|STABILE|DECLINO\",\"disruption_risk\":\"ALTO|MEDIO|BASSO\",\"pricing_power\":\"FORTE|MEDIO|DEBOLE\",\"segnale\":\"COMPRA\",\"analisi\":\"250 parole italiano approfondite su mercato posizionamento e competitività\",{temporal_schema}}}"
    ))

    # AGENTE 7: TARGET PRICE E GRAFICO FUTURO
    target_ai = json.loads(ask_groq(
        "Sei il chief analyst di una primaria banca d investimento. Consulti tutti gli agenti e stimi target price e scenari futuri. Rispondi SOLO JSON valido.",
        f"""Ticker: {ticker} ({fund['name']}) - Prezzo attuale: ${quote['price'] if quote else 'N/D'}
TECNICO: score={tech_ai['score']}, segnale={tech_ai['segnale']}, trend={tech_ai.get('trend','N/D')}
FONDAMENTALE: score={fund_ai['score']}, segnale={fund_ai['segnale']}, PE={fund['pe']}, target_consensus=${fund.get('targetPrice','N/D')}
GEOPOLITICO: score={geo_ai['score']}, rischio={geo_ai.get('rischio_geopolitico','N/D')}
ECONOMETRICO: score={eco_ai['score']}, volatilita={eco_ai.get('volatilita','N/D')}, momentum={eco_ai.get('momentum','N/D')}
MACRO: score={macro_ai['score']}, ciclo={macro_ai.get('ciclo_economico','N/D')}
MERCATO: score={market_ai['score']}, posizionamento={market_ai.get('posizionamento','N/D')}, trend_settore={market_ai.get('trend_settore','N/D')}
{ctx}
Stima target price per ogni scenario e ogni orizzonte temporale. Rispondi SOLO JSON: {{"score":7,"target_base_1a":0.0,"target_bull_1a":0.0,"target_bear_1a":0.0,"target_base_3a":0.0,"target_bull_3a":0.0,"target_bear_3a":0.0,"upside_base":"percentuale","upside_bull":"percentuale","downside_bear":"percentuale","probabilita_bull":30,"probabilita_base":50,"probabilita_bear":20,"rating":"BUY|HOLD|SELL","analisi":"300 parole italiano: metodologia stima, ragionamento, confronto agenti, scenario base bull bear","catalizzatori_rialzo":["c1","c2","c3"],"catalizzatori_ribasso":["r1","r2","r3"],"prev_1m":"target e outlook","prev_3m":"target e outlook","prev_6m":"target e outlook","prev_1a":"target e outlook","prev_3a":"target e outlook","prev_5a":"target e outlook"}}"""
    ))

    # AGENTE 8: ARBITRO FINALE
    arb_ai = json.loads(ask_groq(
        "Sei il direttore di un sistema multi-agente di analisi finanziaria professionale. Sintetizzi 7 agenti specializzati. Rispondi SOLO JSON valido.",
        f"""Ticker: {ticker} - Prezzo: ${quote['price'] if quote else 'N/D'}
TECNICO (score {tech_ai['score']}/10): {tech_ai['segnale']}
FONDAMENTALE (score {fund_ai['score']}/10): {fund_ai['segnale']}
GEOPOLITICO (score {geo_ai['score']}/10): {geo_ai['segnale']}
ECONOMETRICO (score {eco_ai['score']}/10): {eco_ai['segnale']}
MACRO (score {macro_ai['score']}/10): {macro_ai['segnale']}
MERCATO (score {market_ai['score']}/10): {market_ai['segnale']}
TARGET PRICE (score {target_ai['score']}/10): rating={target_ai['rating']}, target_1a=${target_ai['target_base_1a']}
{ctx}
Rispondi SOLO JSON: {{"score_finale":7,"verdetto":"COMPRA","confidenza":"ALTA","rischio":"MEDIO","sintesi":"350 parole italiano: confronta tutti gli agenti, evidenzia accordi conflitti, motiva verdetto finale con logica professionale","catalyst_pos":["c1","c2","c3"],"catalyst_neg":["r1","r2","r3"],"prev_1m":"outlook","prev_3m":"outlook","prev_6m":"outlook","prev_1a":"outlook","prev_3a":"outlook","prev_5a":"outlook","accordo_agenti":"TOTALE|MAGGIORANZA|DIVISI","voti":{{"compra":4,"attendi":2,"vendi":1}}}}"""
    ))

    return tech_ai, fund_ai, geo_ai, eco_ai, macro_ai, market_ai, target_ai, arb_ai

@app.route('/analyze/<ticker>')
def analyze(ticker):
    try:
        quote, tech, fund, history = get_market_data(ticker)
        tech_ai, fund_ai, geo_ai, eco_ai, macro_ai, market_ai, target_ai, arb_ai = run_all_agents(ticker, fund, quote, tech, history)
        return jsonify({
            "ticker": ticker.upper(),
            "quote": quote, "tech": tech, "fund": fund, "history": history,
            "tech_ai": tech_ai, "fund_ai": fund_ai, "geo_ai": geo_ai,
            "eco_ai": eco_ai, "macro_ai": macro_ai, "market_ai": market_ai,
            "target_ai": target_ai, "arb_ai": arb_ai,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/clarify/<ticker>', methods=['POST'])
def clarify(ticker):
    try:
        body = request.json
        question = body.get('question', '')
        history_qa = body.get('history_qa', [])
        prev_analysis = body.get('prev_analysis', {})

        if not question.strip():
            return jsonify({"error": "Domanda vuota"}), 400

        # Verifica rilevanza domanda
        relevance = ask_groq(
            "Rispondi SOLO con 'SI' o 'NO'.",
            f"La seguente domanda è inerente all'analisi finanziaria del titolo {ticker}? Domanda: '{question}'"
        ).strip().upper()

        if 'NO' in relevance:
            return jsonify({"relevant": False, "message": "La domanda non è inerente all'analisi finanziaria. Poni domande sul titolo, sul settore, sui dati finanziari o sulle previsioni."})

        quote, tech, fund, hist = get_market_data(ticker)

        # Costruisci contesto con storico domande
        ctx = ""
        if history_qa:
            ctx += "DOMANDE E RISPOSTE PRECEDENTI:\n"
            for qa in history_qa[-3:]:
                ctx += f"D: {qa['q']}\nR: {qa['a']}\n"
        ctx += f"\nNUOVA DOMANDA DELL UTENTE: {question}"

        tech_ai, fund_ai, geo_ai, eco_ai, macro_ai, market_ai, target_ai, arb_ai = run_all_agents(ticker, fund, quote, tech, hist, extra_context=ctx)

        # Risposta specifica alla domanda
        answer = ask_groq(
            "Sei un analista finanziario senior. Rispondi in modo chiaro e professionale in italiano.",
            f"Basandoti sull'analisi completa di {ticker} ({fund['name']}), rispondi a questa domanda in modo approfondito (200-300 parole): {question}\n\nContesto analisi: Tech={tech_ai['segnale']} score={tech_ai['score']}, Fund={fund_ai['segnale']} score={fund_ai['score']}, Target_base_1a=${target_ai.get('target_base_1a','N/D')}, Verdetto finale={arb_ai['verdetto']}\n{ctx}",
            max_tokens=1000
        )

        return jsonify({
            "relevant": True,
            "answer": answer,
            "ticker": ticker.upper(),
            "quote": quote, "tech": tech, "fund": fund, "history": hist,
            "tech_ai": tech_ai, "fund_ai": fund_ai, "geo_ai": geo_ai,
            "eco_ai": eco_ai, "macro_ai": macro_ai, "market_ai": market_ai,
            "target_ai": target_ai, "arb_ai": arb_ai,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
