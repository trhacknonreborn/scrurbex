#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URBEX OSINT MAX v8.3 — Version avec .env + Export CSV
"""

import streamlit as st
import requests
import json
import csv
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from openai import OpenAI
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

# Charger les variables d'environnement
load_dotenv()

st.set_page_config(page_title="URBEX OSINT by TRHACKNON", layout="wide", page_icon="☣️")

# ================== CLÉ OPENAI DEPUIS .env ==================
DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY")

if not DEFAULT_API_KEY:
    st.error("⚠️ Clé OpenAI non trouvée dans le fichier .env")
    st.info("Crée un fichier `.env` avec : OPENAI_API_KEY=sk-...")

if "openai_client" not in st.session_state:
    if DEFAULT_API_KEY:
        st.session_state.openai_client = OpenAI(api_key=DEFAULT_API_KEY)
    else:
        st.session_state.openai_client = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ================== PROMPT IA ==================
def ai_analyze(results, region, keywords):
    if not st.session_state.openai_client:
        return "⚠️ OpenAI non configuré."

    prompt = f"""Tu es un expert très expérimenté en exploration urbaine (urbex).

**Mission :** Trouver des lieux abandonnés concrets et intéressants dans la région de {region} liés à {keywords}.

**Instructions strictes :**
- Ne garde que les lieux réels (usines, friches, hôpitaux, châteaux, bases, écoles, mines, etc.)
- Pour chaque lieu retenu, donne :
   • Nom du lieu + localisation approximative
   • Pourquoi il est intéressant
   • Niveau de potentiel (Élevé / Moyen)
   • Lien principal

Liste maximum 10 à 12 lieux les plus prometteurs."""

    try:
        response = st.session_state.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt + "\n\nRésultats bruts :\n" + json.dumps(results[:90], ensure_ascii=False)}],
            temperature=0.6,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur OpenAI : {str(e)}"


# ================== FONCTIONS DE SCRAPING (inchangées) ==================
def search_concrete_places(query):
    results = []
    searches = [f"{query} usine abandonnée", f"{query} friche industrielle", f"{query} hôpital abandonné",
                f"{query} base militaire abandonnée", f"{query} château abandonné", f"{query} site urbex"]
    for s in searches:
        results.append({"source": "Google", "title": s, "url": f"https://www.google.com/search?q={quote(s)}"})
    return results

# ... (les autres fonctions scrape_reddit, scrape_urbexpassion, scrape_28dayslater, deep_crawl restent identiques)


def main():
    st.title("🌆 URBEX OSINT MAX v8.3")
    st.caption("**Scraping Amélioré + IA + Export CSV**")

    with st.sidebar:
        st.header("Configuration")
        key_input = st.text_input("OpenAI API Key (optionnel)", type="password", value=DEFAULT_API_KEY)
        if st.button("Mettre à jour la clé"):
            st.session_state.openai_client = OpenAI(api_key=key_input)
            st.success("✅ Clé mise à jour")

    col1, col2 = st.columns([3, 1])
    with col1:
        region = st.text_input("📍 Région / Ville", "Ardennes")
        keywords = st.text_input("🏚️ Type de lieu / mots-clés", "usine sidérurgique")
    with col2:
        use_ai = st.checkbox("Activer Analyse IA", value=True)

    if st.button("🚀 LANCER LA RECHERCHE MAX", type="primary", use_container_width=True):
        with st.spinner("Recherche multi-sources en cours..."):
            all_results = []
            with ThreadPoolExecutor(max_workers=10) as ex:
                futures = [
                    ex.submit(search_concrete_places, f"{region} {keywords}"),
                    ex.submit(scrape_reddit, f"{region} {keywords}"),
                    ex.submit(scrape_urbexpassion, f"{region} {keywords}"),
                    ex.submit(scrape_28dayslater, f"{region} {keywords}"),
                ]
                for f in as_completed(futures):
                    all_results.extend(f.result() or [])

            st.success(f"✅ {len(all_results)} résultats collectés")

            # Affichage des résultats
            for i, res in enumerate(all_results[:50], 1):
                st.markdown(f"**{i}.** [{res.get('source')}] {res.get('title', res.get('url',''))[:130]}")
                if res.get("url"):
                    st.markdown(f"→ [{res['url']}]({res['url']})")
                st.divider()

            # Analyse IA
            ai_text = None
            if use_ai and st.session_state.openai_client:
                with st.spinner("🤖 Analyse IA en cours..."):
                    ai_text = ai_analyze(all_results, region, keywords)
                    st.subheader("🤖 Analyse IA - Meilleurs lieux")
                    st.markdown(ai_text)

            # ================== EXPORT ==================
            if ai_text or all_results:
                st.subheader("📥 Export des résultats")
                col_exp1, col_exp2 = st.columns(2)

                # Export TXT
                txt_data = f"URBEX OSINT - {region} - {keywords}\nDate: {datetime.now()}\n\n" + \
                          (ai_text if ai_text else "Pas d'analyse IA")
                with col_exp1:
                    st.download_button(
                        label="📄 Télécharger en TXT",
                        data=txt_data,
                        file_name=f"urbex_{region}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                        mime="text/plain"
                    )

                # Export CSV
                with col_exp2:
                    csv_data = []
                    # Résultats bruts
                    for res in all_results[:100]:
                        csv_data.append({
                            "Source": res.get("source", ""),
                            "Titre": res.get("title", ""),
                            "URL": res.get("url", ""),
                            "Type": "Résultat brut"
                        })

                    # Si analyse IA, on peut ajouter une ligne synthétique
                    if ai_text:
                        csv_data.append({
                            "Source": "IA Analysis",
                            "Titre": "Synthèse IA",
                            "URL": "",
                            "Type": "Analyse"
                        })

                    csv_str = ""
                    if csv_data:
                        import io
                        output = io.StringIO()
                        writer = csv.DictWriter(output, fieldnames=["Source", "Titre", "URL", "Type"])
                        writer.writeheader()
                        writer.writerows(csv_data)
                        csv_str = output.getvalue()

                    st.download_button(
                        label="📊 Télécharger en CSV",
                        data=csv_str,
                        file_name=f"urbex_{region}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv"
                    )

if __name__ == "__main__":
    main()