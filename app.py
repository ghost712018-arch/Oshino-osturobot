import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Oshino OÜ Osturobot", page_icon="🔎", layout="wide")

st.title("Oshino OÜ Osturobot")
st.caption("Elektroonikakomponentide ostu ja saadavuse piloot")

st.info("DEMO-režiim: praegu ei kasutata veel reaalajas TrustedPartsi/Octoparti API andmeid.")

tab1, tab2 = st.tabs(["Komponendi otsing", "BOM analüüs"])

with tab1:
    mpn = st.text_input("Tootja tootekood (MPN)", placeholder="Näiteks STM32F407VGT6")
    qty = st.number_input("Vajalik kogus", min_value=1, value=100, step=1)
    if st.button("Otsi komponenti", type="primary"):
        if not mpn.strip():
            st.warning("Sisesta MPN.")
        else:
            demo = pd.DataFrame([
                {"Allikas":"TrustedParts (DEMO)", "MPN":mpn.upper(), "Laoseis":1250, "Hind €/tk":4.82, "MOQ":1, "Tarneaeg":"Laos"},
                {"Allikas":"DigiKey (DEMO)", "MPN":mpn.upper(), "Laoseis":480, "Hind €/tk":5.10, "MOQ":1, "Tarneaeg":"Laos"},
                {"Allikas":"Mouser (DEMO)", "MPN":mpn.upper(), "Laoseis":0, "Hind €/tk":4.95, "MOQ":1, "Tarneaeg":"12 nädalat"},
            ])
            demo["Piisab koguseks"] = demo["Laoseis"] >= qty
            st.dataframe(demo, use_container_width=True, hide_index=True)
            available = demo[demo["Piisab koguseks"]]
            if len(available):
                best = available.sort_values("Hind €/tk").iloc[0]
                st.success(f"DEMO soovitus: {best['Allikas']} — {best['Hind €/tk']:.2f} €/tk, laos {int(best['Laoseis'])} tk.")
            else:
                st.error("DEMO: ükski kuvatud allikas ei kata kogu kogust.")

with tab2:
    uploaded = st.file_uploader("Laadi BOM CSV või XLSX", type=["csv","xlsx"])
    if uploaded:
        try:
            df = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded)
            st.dataframe(df, use_container_width=True)
            st.caption("Järgmises versioonis otsib robot iga MPN-i kohta päris laoseisu, hinda ja tarneaega.")
        except Exception as e:
            st.error(f"Faili lugemine ebaõnnestus: {e}")

st.divider()
st.caption("V1 piloot • päris turuandmed lisame API võtmetega järgmises etapis.")
