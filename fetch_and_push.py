import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
import yfinance as yf
import pandas as pd

# 1. Firebase 初始化
if os.path.exists("serviceAccountKey.json"):
    cred = credentials.Certificate("serviceAccountKey.json")
else:
    firebase_config = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(firebase_config)

firebase_admin.initialize_app(cred)
db = firestore.client()

def calculate_indicators(df):
    df['MA20'] = df['Close'].rolling(20).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['STD20'] = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    return df

def main():
    # 預設追蹤熱門股
    all_tickers = set(["2330.TW", "2454.TW", "NVDA", "AAPL", "TSLA"])

    # 撈取使用者自由新增的所有股票代碼
    user_stocks = db.collection("user_stocks").stream()
    for doc in user_stocks:
        data = doc.to_dict()
        if "ticker" in data:
            all_tickers.add(data["ticker"])

    print(f"📊 本次掃描股票清單: {all_tickers}")

    for ticker in all_tickers:
        try:
            df = yf.download(ticker, period="1y")
            if df.empty:
                continue

            df = calculate_indicators(df)
            latest = df.iloc[-1]

            history = []
            for date, row in df.tail(60).iterrows():
                history.append({
                    "date": date.strftime('%Y-%m-%d'),
                    "close": round(float(row['Close']), 2),
                })

            # 更新 Google Firestore
            doc_ref = db.collection("stocks").document(ticker)
            doc_ref.set({
                "ticker": ticker,
                "latest_price": round(float(latest['Close']), 2),
                "rsi": round(float(latest['RSI']), 2),
                "bb_upper": round(float(latest['BB_Upper']), 2) if pd.notnull(latest['BB_Upper']) else None,
                "bb_lower": round(float(latest['BB_Lower']), 2) if pd.notnull(latest['BB_Lower']) else None,
                "history": history,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            print(f"✅ {ticker} 數據更新成功！")
        except Exception as e:
            print(f"❌ {ticker} 抓取失敗: {e}")

if __name__ == "__main__":
    main()
