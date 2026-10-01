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
    r = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "supply.domain",
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
            clickUrl
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

@st.cache_data(ttl=1800, show_spinner=False)
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
        q = p.get("quantity")
        price = p.get("convertedPrice")
        if q is not None and price is not None and q <= qty:
            choices.append((q, float(price), p.get("convertedCurrency") or "EUR"))
    return max(choices, key=lambda x: x[0])[1:] if choices else (None, None)


def build_rows(part, qty):
    rows = []
    for seller in part.get("sellers") or []:
        company = seller.get("company") or {}
        for offer in seller.get("offers") or []:
            price, currency = price_for_qty(offer.get("prices"), qty)
            stock = offer.get("inventoryLevel")
            moq = offer.get("moq") or 1
            buy_qty = max(int(qty), int(moq))
            covers = isinstance(stock, (int, float)) and stock >= buy_qty
            total = round(price * buy_qty, 2) if price is not None else None
            rows.append({
                "Tarnija": company.get("name") or "—",
                "Telli": offer.get("clickUrl"),
                "Autoriseeritud": bool(seller.get("isAuthorized")),
                "Kontrollitud ettevõte": bool(company.get("isVerified")),
                "Laoseis": stock,
                "MOQ": moq,
                "Ostukogus": buy_qty,
                "Pakend": offer.get("packaging") or "—",
                "Lead time (päeva)": offer.get("factoryLeadDays"),
                "Ühiku hind EUR": price,
                "Kogukulu EUR": total,
                "Katab koguse": covers,
            })
    return rows

mpn = st.text_input("Tootja tootekood (MPN)", placeholder="STM32F407VGT6")
qty = st.number_input("Vajalik kogus", min_value=1, value=100, step=1)

c1, c2 = st.columns(2)
with c1:
    only_authorized = st.checkbox("Näita ainult autoriseeritud tarnijaid", value=True)
with c2:
    only_in_stock = st.checkbox("Näita ainult piisava laoseisuga pakkumisi", value=True)

if st.button("Otsi turuandmeid", type="primary"):
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

                rows = build_rows(part, qty)
                df = pd.DataFrame(rows)
                if not df.empty:
                    filtered = df.copy()
                    if only_authorized:
                        filtered = filtered[filtered["Autoriseeritud"]]
                    if only_in_stock:
                        filtered = filtered[filtered["Katab koguse"]]

                    priced = filtered.dropna(subset=["Kogukulu EUR"])
                    best = priced.sort_values("Kogukulu EUR").iloc[0] if not priced.empty else None

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Nexari kogusaadavus", f"{int(part.get('totalAvail') or 0):,}".replace(",", " "))
                    m2.metric("Sobivaid pakkumisi", len(filtered))
                    m3.metric("Parim ühikuhind", f"€{best['Ühiku hind EUR']:.4f}" if best is not None else "—")
                    m4.metric("Parim kogukulu", f"€{best['Kogukulu EUR']:.2f}" if best is not None else "—")

                    if best is not None:
                        st.success(
                            f"Odavaim kuvatud sobiv pakkumine: {best['Tarnija']} — "
                            f"{int(best['Ostukogus'])} tk × €{best['Ühiku hind EUR']:.4f} = €{best['Kogukulu EUR']:.2f}."
                        )
                        if pd.notna(best.get("Telli")) and str(best.get("Telli")).startswith(("http://", "https://")):
                            st.link_button(f"Ava parim pakkumine — {best['Tarnija']}", str(best["Telli"]), type="primary")

                    if filtered.empty:
                        st.warning("Valitud filtritega sobivaid pakkumisi ei ole. Eemalda mõni filter ja otsi uuesti; sama MPN-i tulemus on 30 minutit vahemälus.")
                    else:
                        filtered = filtered.sort_values(
                            ["Kogukulu EUR", "Laoseis"], ascending=[True, False], na_position="last"
                        )
                        st.dataframe(
                            filtered,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Telli": st.column_config.LinkColumn(
                                    "Telli", display_text="Ava pakkumine ↗"
                                ),
                                "Ühiku hind EUR": st.column_config.NumberColumn(format="€%.4f"),
                                "Kogukulu EUR": st.column_config.NumberColumn(format="€%.2f"),
                            },
                        )
                        st.download_button(
                            "Laadi tulemused CSV-na",
                            filtered.to_csv(index=False).encode("utf-8-sig"),
                            file_name=f"{part.get('mpn', mpn)}_{qty}tk_pakkumised.csv",
                            mime="text/csv",
                        )
                else:
                    st.info("Komponent leiti, kuid pakkumisi ei tagastatud.")

                st.caption("Andmeallikas: Nexar / Octopart. Hind ei pruugi sisaldada transporti, käibemaksu ega muid tasusid. Kontrolli enne ostu tarnija lõplik pakkumine.")
        except KeyError:
            st.error("Nexari võtmed puuduvad Streamlit Secrets alt.")
        except Exception as e:
            st.error(f"Otsing ebaõnnestus: {e}")

st.divider()
st.caption("V4 • Otselink tarnija pakkumisele • autoriseeritud tarnijad • laoseis • MOQ • kogukulu • CSV eksport")
