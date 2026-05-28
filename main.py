#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URBEX OSINT MAX v8.3 — .env + Export CSV
"""

import streamlit as st
import requests
import json
import csv
import io
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from openai import OpenAI
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

# Charger .env
load_dotenv()

st.set_page_config(page_title="URBEX OSINT by TRHACKNON", layout="wide", page_icon="☣️")

# ================== OPENAI ==================
DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY")

if not DEFAULT_API_KEY:
    st.error("⚠️ Clé OpenAI non trouvée dans le fichier .env")
    st.info("Ajoute OPENAI_API_KEY=sk-... dans le fichier .env")

if "openai_client" not in st.session_state:
    if DEFAULT_API_KEY:
        st.session_state.openai_client = OpenAI(api_key=DEFAULT_API_KEY)
    else:
        st.session_state.openai_client = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ================== FONCTIONS DE SCRAPING ==================
def search_concrete_places(query):
    results = []
    searches = [
        f"{query} usine abandonnée",
        f"{query} friche industrielle",
        f"{query} hôpital abandonné",
        f"{query} base militaire abandonnée",
        f"{query} château abandonné",
        f"{query} site urbex",
    ]
    for s in searches:
        results.append({
            "source": "Google", 
            "title": s, 
            "url": f"https://www.google.com/search?q={quote(s)}"
        })
    return results


def scrape_reddit(query):
    results = []
    try:
        r = requests.get(
            f"https://www.reddit.com/search.json?q={quote(query + ' urbex OR abandonné OR friche')}&limit=15",
            headers=HEADERS, 
            timeout=12
        )
        for post in r.json().get("data", {}).get("children", []):
            d = post["data"]
            results.append({
                "source": "Reddit",
                "title": d.get("title", ""),
                "url": f"https://reddit.com{d.get('permalink', '')}"
            })
    except:
        pass
    return results


def scrape_urbexpassion(query):
    results = []
    try:
        r = requests.get(f"https://www.urbexpassion.com/recherche?query={quote(query)}", 
                        headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.find_all('a', href=True):
            if '/report/' in a['href'] or '/lieu/' in a['href']:
                url = "https://www.urbexpassion.com" + a['href'] if not a['href'].startswith('http') else a['href']
                results.append({
                    "source": "UrbexPassion", 
                    "title": a.get_text()[:100], 
                    "url": url
                })
    except:
        pass
    return results


def scrape_28dayslater(query):
    results = []
    try:
        r = requests.get(f"https://www.28dayslater.co.uk/search/?q={quote(query)}", 
                        headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.find_all('a', href=True):
            if '/threads/' in a['href']:
                url = "https://www.28dayslater.co.uk" + a['href'] if not a['href'].startswith('http') else a['href']
                results.append({
                    "source": "28dayslater", 
                    "title": a.get_text()[:80], 
                    "url": url
                })
    except:
        pass
    return results


def deep_crawl(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        links = [a.get('href') for a in soup.find_all('a', href=True)]
        return [link for link in links if link and link.startswith('http') and 
                any(x in link.lower() for x in ['report', 'thread', 'lieu', 'urbex', 'abandon'])]
    except:
        return []


# ================== ANALYSE IA ==================
def ai_analyze(results, region, keywords):
    if not st.session_state.openai_client:
        return "⚠️ OpenAI non configuré."

    prompt = f"""Tu es un expert en exploration urbaine (urbex).

**Mission :** Trouver des lieux abandonnés concrets dans la région de {region} liés à {keywords}.

**Instructions :**
- Garde uniquement les lieux réels et intéressants.
- Pour chaque lieu : Nom + localisation + pourquoi intéressant + niveau de potentiel.

Liste maximum 10-12 lieux."""

    try:
        response = st.session_state.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt + "\n\nRésultats :\n" + json.dumps(results[:80], ensure_ascii=False)}],
            temperature=0.65,
            max_tokens=1800
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur OpenAI : {str(e)}"


# ================== MAIN ==================
def main():
    st.title("🌆 URBEX OSINT MAX v8.3")
    st.caption("**Multi-sources + IA + Export CSV**")

    with st.sidebar:
        st.header("Configuration")
        key_input = st.text_input("OpenAI API Key", type="password", value=DEFAULT_API_KEY)
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
        with st.spinner("Recherche en cours..."):
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

            # Deep crawl (optionnel)
            st.info("Deep crawl en cours...")
            deep_links = []
            for item in all_results[:12]:
                if item.get("url"):
                    deep_links.extend(deep_crawl(item["url"]))
            all_results.extend([{"source": "Deep Crawl", "title": "", "url": link} for link in deep_links[:30]])

            st.success(f"✅ {len(all_results)} résultats trouvés")

            # Affichage
            for i, res in enumerate(all_results[:50], 1):
                st.markdown(f"**{i}.** [{res.get('source')}] {res.get('title', res.get('url',''))[:140]}")
                if res.get("url"):
                    st.markdown(f"🔗 [{res['url']}]({res['url']})")
                st.divider()

            # Analyse IA
            ai_text = None
            if use_ai and st.session_state.openai_client:
                with st.spinner("🤖 Analyse IA..."):
                    ai_text = ai_analyze(all_results, region, keywords)
                    st.subheader("🤖 Meilleurs lieux selon l'IA")
                    st.markdown(ai_text)

            # ================== EXPORT ==================
            if all_results:
                st.subheader("📥 Export des résultats")

                col_exp1, col_exp2 = st.columns(2)

                # TXT
                txt_content = f"URBEX OSINT MAX\nRégion: {region}\nMots-clés: {keywords}\nDate: {datetime.now()}\n\n{ai_text or ''}"
                with col_exp1:
                    st.download_button(
                        "📄 Télécharger TXT",
                        data=txt_content,
                        file_name=f"urbex_{region}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                        mime="text/plain"
                    )

                # CSV
                with col_exp2:
                    csv_data = []
                    for res in all_results:
                        csv_data.append({
                            "Source": res.get("source", ""),
                            "Titre": res.get("title", ""),
                            "URL": res.get("url", ""),
                        })
                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=["Source", "Titre", "URL"])
                    writer.writeheader()
                    writer.writerows(csv_data)
                    csv_str = output.getvalue()

                    st.download_button(
                        "📊 Télécharger CSV",
                        data=csv_str,
                        file_name=f"urbex_{region}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv"
                    )

if __name__ == "__main__":
    main()
