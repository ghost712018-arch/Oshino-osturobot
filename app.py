import requests
import pandas as pd
import streamlit as st

TOKEN_URL = "https://identity.nexar.com/connect/token"
GRAPHQL_URL = "https://api.nexar.com/graphql"

st.set_page_config(page_title="Oshino OÜ Osturobot", page_icon="🔎", layout="wide")
st.title("Oshino OÜ Osturobot")
st.caption("Päris Nexar / Octopart turuandmed • Eesti • EUR")

@st.cache_data(ttl=82800, show_spinner=False)
def get_token(client_id, client_secret):
    r = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "supply.domain"
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

QUERY = """
query Search($mpn: String!, $country: String!, $currency: String!) {
  supSearchMpn(q: $mpn, country: $country, currency: $currency, limit: 1) {
    hits
    results {
      part {
        mpn
        name
        manufacturer { name }
        totalAvail
        sellers {
          company { name isVerified }
          isAuthorized
          offers {
            inventoryLevel
            moq
            factoryLeadDays
            packaging
            prices { quantity convertedPrice convertedCurrency }
          }
        }
      }
    }
  }
}
"""

def search(mpn):
    token = get_token(st.secrets["NEXAR_CLIENT_ID"], st.secrets["NEXAR_CLIENT_SECRET"])
    r = requests.post(
        GRAPHQL_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": QUERY, "variables": {"mpn": mpn, "country": "EE", "currency": "EUR"}},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(data["errors"][0].get("message", str(data["errors"])))
    return data["data"]["supSearchMpn"]

def price_for_qty(prices, qty):
    choices = []
    for p in prices or []:
        if p.get("quantity") is not None and p.get("convertedPrice") is not None and p["quantity"] <= qty:
            choices.append((p["quantity"], p["convertedPrice"], p.get("convertedCurrency") or "EUR"))
    return max(choices, key=lambda x: x[0])[1:] if choices else (None, None)

mpn = st.text_input("Tootja tootekood (MPN)", placeholder="STM32F407VGT6")
qty = st.number_input("Vajalik kogus", min_value=1, value=100, step=1)

if st.button("Otsi päris turuandmeid", type="primary"):
    if not mpn.strip():
        st.warning("Sisesta MPN.")
    else:
        try:
            with st.spinner("Küsin Nexar/Octopart andmeid..."):
                result = search(mpn.strip())
            results = result.get("results") or []
            if not results:
                st.warning("MPN-i kohta tulemust ei leitud.")
            else:
                part = results[0]["part"]
                maker = (part.get("manufacturer") or {}).get("name", "")
                st.subheader(f"{part.get('mpn', mpn)} — {maker}")
                st.metric("Nexari kogusaadavus", part.get("totalAvail", 0))

                rows = []
                for seller in part.get("sellers") or []:
                    company = seller.get("company") or {}
                    for offer in seller.get("offers") or []:
                        price, currency = price_for_qty(offer.get("prices"), qty)
                        stock = offer.get("inventoryLevel")
                        rows.append({
                            "Tarnija": company.get("name"),
                            "Autoriseeritud": seller.get("isAuthorized"),
                            "Laoseis": stock,
                            "MOQ": offer.get("moq"),
                            "Pakend": offer.get("packaging"),
                            "Lead time (päeva)": offer.get("factoryLeadDays"),
                            f"Hind @ {qty}": price,
                            "Valuuta": currency,
                            "Katab koguse": isinstance(stock, (int, float)) and stock >= qty,
                        })

                if rows:
                    df = pd.DataFrame(rows)
                    df = df.sort_values(["Katab koguse", f"Hind @ {qty}"], ascending=[False, True], na_position="last")
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("Komponent leiti, kuid pakkumisi ei tagastatud.")
                st.caption("Andmeallikas: Nexar / Octopart. Kontrolli enne ostu tarnija lõplik pakkumine.")
        except Exception as e:
            st.error(f"Otsing ebaõnnestus: {e}")

st.divider()
st.caption("V2 • BOM massotsingu lisame järgmises etapis, et Evaluation limiiti mitte asjatult kulutada.")
