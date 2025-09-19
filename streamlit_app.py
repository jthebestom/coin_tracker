"""
Run with:
streamlit run streamlit_app.py
"""

import streamlit as st
import time
import pandas as pd
import requests
from datetime import datetime

COINGECKO_SIMPLE_PRICE = "https://api.coingecko.com/api/v3/simple/price"
SYMBOL_TO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "ADA": "cardano",
    "SOL": "solana",
    "DOGE": "dogecoin",
}

def fetch(symbols, vs="usd"):
    ids = ",".join([SYMBOL_TO_ID.get(s.upper(), s.lower()) for s in symbols])
    params = {"ids": ids, "vs_currencies": vs}
    r = requests.get(COINGECKO_SIMPLE_PRICE, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    out = {}
    for s in symbols:
        idx = SYMBOL_TO_ID.get(s.upper(), s.lower())
        out[s] = data.get(idx, {}).get(vs)
    return out

st.title("Crypto Price Tracker — Dashboard")
with st.sidebar:
    symbols = st.multiselect("Symbols", options=list(SYMBOL_TO_ID.keys()), default=["BTC", "ETH"])
    interval = st.number_input("Refresh interval (s)", min_value=5, value=10)
    run = st.button("Start Live")

placeholder = st.empty()

# Initialize session state for history
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=["timestamp"] + symbols)

if run:
    for _ in range(1000):  # Arbitrary large number for live updates
        try:
            prices = fetch(symbols)
        except Exception as e:
            st.error(f"Fetch failed: {e}")
            break

        # Add new row to history
        row = {"timestamp": datetime.utcnow().isoformat()}
        row.update({k: prices.get(k) for k in symbols})
        st.session_state.history = pd.concat(
            [st.session_state.history, pd.DataFrame([row])], ignore_index=True
        )

        # Display updated data
        with placeholder.container():
            st.write(datetime.utcnow().isoformat())
            st.dataframe(pd.DataFrame([prices]).T.rename(columns={0: "price"}))
            for s in symbols:
                if s in st.session_state.history.columns:
                    st.line_chart(
                        st.session_state.history.set_index("timestamp")[s].astype(float)
                    )

        # Sleep for the specified interval
        time.sleep(interval)
else:
    st.write("Press Start Live in the sidebar to begin polling.")
