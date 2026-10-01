import urllib.parse
import requests
import pandas as pd
import streamlit as st

TOKEN_URL = "https://identity.nexar.com/connect/token"
GRAPHQL_URL = "https://api.nexar.com/graphql"

st.set_page_config(page_title="Oshino OÜ Osturobot", page_icon="🔎", layout="wide")
st.title("Oshino OÜ Osturobot")
st.caption("Nexar / Octopart turuandmed • Eesti • EUR")

@st.cache_data(ttl=82800, show_spinner=False)
def get_token(client_id, client_secret):
    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "supply.domain",
        },
        timeout=30,
    )
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
            clickUrl
            prices {
              quantity
              convertedPrice
              convertedCurrency
            }
          }
        }
      }
    }
  }
}
"""

def vendor_search_url(vendor, mpn):
    q = urllib.parse.quote_plus(mpn)
    v = (vendor or "").lower()

    if "verical" in v:
        return f"https://www.verical.com/pd/search?query={q}"
    if "arrow" in v:
        return f"https://www.arrow.com/en/products/search?q={q}"
    if "digikey" in v or "digi-key" in v:
        return f"https://www.digikey.com/en/products/result?keywords={q}"
    if "farnell" in v:
        return f"https://ee.farnell.com/w/search?st={q}"
    if "newark" in v:
        return f"https://www.newark.com/search?st={q}"
    if "tme" in v:
        return f"https://www.tme.eu/ee/en/katalog/?search={q}"
    if "mouser" in v:
        return f"https://www.mouser.ee/c/?q={q}"
    if "rs" in v and "components" in v:
        return f"https://ee.rs-online.com/web/c/?searchTerm={q}"

    # Generic fallback: Google search restricted to vendor name + MPN
    return f"https://www.google.com/search?q={urllib.parse.quote_plus((vendor or '') + ' ' + mpn)}"

@st.cache_data(ttl=1800, show_spinner=False)
def search_nexar(mpn):
    token = get_token(st.secrets["NEXAR_CLIENT_ID"], st.secrets["NEXAR_CLIENT_SECRET"])
    r = requests.post(
        GRAPHQL_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "query": QUERY,
            "variables": {"mpn": mpn, "country": "EE", "currency": "EUR"},
        },
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
        if p.get("quantity") is None or p.get("convertedPrice") is None:
            continue
        if p["quantity"] <= qty:
            choices.append((p["quantity"], p["convertedPrice"], p.get("convertedCurrency") or "EUR"))
    if not choices:
        return None, None
    _, price, currency = max(choices, key=lambda x: x[0])
    return price, currency

def normalize_url(url):
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url.lstrip("/")

mpn = st.text_input("Tootja tootekood (MPN)", value="STM32F407VGT6")
qty = st.number_input("Vajalik kogus", min_value=1, value=100, step=1)

c1, c2 = st.columns(2)
with c1:
    only_authorized = st.checkbox("Näita ainult autoriseeritud tarnijaid", value=True)
with c2:
    only_stock = st.checkbox("Näita ainult piisava laoseisuga pakkumisi", value=True)

if st.button("Otsi turuandmeid", type="primary"):
    try:
        with st.spinner("Küsin Nexar/Octopart andmeid..."):
            result = search_nexar(mpn.strip())

        results = result.get("results") or []
        if not results:
            st.warning("MPN-i kohta tulemust ei leitud.")
            st.stop()

        part = results[0]["part"]
        manufacturer = (part.get("manufacturer") or {}).get("name", "")
        st.subheader(f"{part.get('mpn', mpn)} — {manufacturer}")

        rows = []
        for seller in part.get("sellers") or []:
            company = seller.get("company") or {}
            vendor = company.get("name") or "Tundmatu"
            for offer in seller.get("offers") or []:
                stock = offer.get("inventoryLevel")
                moq = offer.get("moq") or 1
                buy_qty = max(qty, moq)
                price, currency = price_for_qty(offer.get("prices"), buy_qty)
                total = (price * buy_qty) if price is not None else None
                enough = isinstance(stock, (int, float)) and stock >= buy_qty

                direct = normalize_url(offer.get("clickUrl"))
                order_url = direct or vendor_search_url(vendor, part.get("mpn", mpn))

                rows.append({
                    "Tarnija": vendor,
                    "Telli": order_url,
                    "Autoriseeritud": bool(seller.get("isAuthorized")),
                    "Kontrollitud ettevõte": bool(company.get("isVerified")),
                    "Laoseis": stock,
                    "MOQ": moq,
                    "Ostukogus": buy_qty,
                    "Pakend": offer.get("packaging") or "—",
                    "Lead time (päeva)": offer.get("factoryLeadDays"),
                    "Ühiku hind EUR": price,
                    "Kogukulu EUR": total,
                    "Katab koguse": enough,
                })

        df = pd.DataFrame(rows)

        if only_authorized:
            df = df[df["Autoriseeritud"] == True]
        if only_stock:
            df = df[df["Katab koguse"] == True]

        if df.empty:
            st.warning("Valitud filtritega sobivaid pakkumisi ei leitud.")
            st.stop()

        df = df.sort_values(
            by=["Kogukulu EUR", "Ühiku hind EUR"],
            ascending=[True, True],
            na_position="last",
        )

        best = df[df["Kogukulu EUR"].notna()].head(1)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Nexari kogusaadavus", f"{part.get('totalAvail', 0):,}".replace(",", " "))
        m2.metric("Sobivaid pakkumisi", len(df))
        if not best.empty:
            b = best.iloc[0]
            m3.metric("Parim ühikuhind", f"€{b['Ühiku hind EUR']:.4f}")
            m4.metric("Parim kogukulu", f"€{b['Kogukulu EUR']:.2f}")

            st.success(
                f"Odavaim kuvatud sobiv pakkumine: {b['Tarnija']} — "
                f"{int(b['Ostukogus'])} tk × €{b['Ühiku hind EUR']:.4f} = €{b['Kogukulu EUR']:.2f}."
            )
            st.link_button(f"Ava parim pakkumine — {b['Tarnija']} ↗", b["Telli"])

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Telli": st.column_config.LinkColumn(
                    "Telli",
                    display_text="Ava pakkumine ↗"
                ),
                "Ühiku hind EUR": st.column_config.NumberColumn(format="€%.4f"),
                "Kogukulu EUR": st.column_config.NumberColumn(format="€%.2f"),
            },
        )

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Laadi tulemused CSV-na",
            data=csv,
            file_name=f"{part.get('mpn', mpn)}_pakkumised.csv",
            mime="text/csv",
        )

        st.caption(
            "Kui Nexar ei tagasta otselinki, avab 'Telli' tarnija enda MPN-otsingu. "
            "Hind ja laoseis võivad tarnija lehel erineda; kontrolli lõplik pakkumine enne tellimust."
        )

    except Exception as e:
        st.error(f"Otsing ebaõnnestus: {e}")

st.divider()
st.caption("V5.1 • otselink või tarnija MPN-otsing • autoriseeritud tarnijad • laoseis • MOQ • kogukulu")
