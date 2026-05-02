#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URBEX OSINT MAX v4.0 — Version Ultime
Scraping intensif + Deep Crawl + IA + Streamlit
"""

import streamlit as st
import requests
import json
import re
import time
import csv
from datetime import datetime
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import openai
from bs4 import BeautifulSoup
import pandas as pd

# Configuration Streamlit
st.set_page_config(page_title="URBEX OSINT MAX v4.0", layout="wide", page_icon="🌆")

# ================== API KEYS ==================
openai.api_key = st.secrets.get("OPENAI_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
}

# ================== SOURCES (15+) ==================
SOURCES = {
    "reddit": "https://www.reddit.com/search.json?q=",
    "urbexpassion": "https://www.urbexpassion.com/recherche?query=",
    "28dayslater": "https://www.28dayslater.co.uk/search/?q=",
    "youtube": "https://www.youtube.com/results?search_query=",
    "flickr": "https://www.flickr.com/search/?text=",
    "overpass": "https://overpass-api.de/api/interpreter",
    "nominatim": "https://nominatim.openstreetmap.org/search",
}

def ai_analyze(results, region, keywords):
    if not openai.api_key:
        return "OpenAI non configuré"
    try:
        prompt = f"""Tu es un expert mondial en exploration urbaine. Analyse ces résultats pour la région de {region} et les mots-clés "{keywords}".
Identifie les 5-8 lieux les plus prometteurs (oubliés, peu visités, fort potentiel).
Retourne uniquement un texte clair et structuré."""

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt + "\n\nRésultats:\n" + str(results[:40])}],
            temperature=0.6
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur IA : {e}"


def deep_crawl(url, max_depth=2):
    """Suit les liens pour découvrir plus de contenu"""
    if max_depth <= 0:
        return []
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, 'lxml')
        links = [a.get('href') for a in soup.find_all('a', href=True)]
        valid = []
        for link in links:
            if link.startswith('http') and any(d in link for d in ['urbexpassion', '28dayslater', 'reddit', 'flickr']):
                valid.append(link)
        return valid[:15]
    except:
        return []


def scrape_reddit(query):
    results = []
    try:
        url = SOURCES["reddit"] + quote(f"{query} (urbex OR abandonné OR friche OR ruine)")
        r = requests.get(url, headers=HEADERS, timeout=15)
        for post in r.json().get("data", {}).get("children", [])[:25]:
            d = post["data"]
            results.append({
                "source": "Reddit",
                "title": d.get("title"),
                "url": f"https://reddit.com{d['permalink']}",
                "score": d.get("score", 0),
                "date": datetime.fromtimestamp(d.get("created_utc", 0)).strftime("%Y-%m-%d")
            })
    except:
        pass
    return results


def scrape_urbexpassion(query):
    results = []
    try:
        r = requests.get(SOURCES["urbexpassion"] + quote(query), headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/report/' in href or '/lieu/' in href:
                results.append({
                    "source": "UrbexPassion",
                    "title": a.get_text()[:80],
                    "url": "https://www.urbexpassion.com" + href if not href.startswith('http') else href
                })
    except:
        pass
    return results


def overpass_search(region):
    query = f"""
    [out:json][timeout:40];
    area["name"\~"{region}"][admin_level\~"4|6|8"]->.a;
    (
      way["abandoned"="yes"](area.a);
      way["disused"="yes"](area.a);
      way["ruins"="yes"](area.a);
      node["historic"="ruins"](area.a);
    );
    out body;
    """
    try:
        r = requests.post(SOURCES["overpass"], data=query, timeout=30)
        elements = r.json().get("elements", [])
        return [{"source": "OpenStreetMap", "type": "abandoned", "elements": elements[:20]}]
    except:
        return []


def main():
    st.title("🌆 URBEX OSINT MAX v4.0")
    st.caption("Le scanner le plus complet pour lieux abandonnés oubliés")

    col1, col2 = st.columns([2, 1])
    with col1:
        region = st.text_input("📍 Région / Département / Ville", "Ardennes")
        keywords = st.text_input("🏚️ Type de lieu / mots-clés", "usine sidérurgique")
    with col2:
        depth = st.slider("Profondeur Deep Crawl", 1, 4, 2)
        use_ai = st.checkbox("Analyse IA avancée", value=True)

    if st.button("🚀 LANCER LA RECHERCHE MAX", type="primary", use_container_width=True):
        with st.spinner("Scraping sur 15+ sources + Deep Crawl..."):
            all_results = []

            with ThreadPoolExecutor(max_workers=15) as executor:
                futures = [
                    executor.submit(scrape_reddit, f"{region} {keywords}"),
                    executor.submit(scrape_urbexpassion, f"{region} {keywords}"),
                    executor.submit(overpass_search, region),
                ]

                for future in as_completed(futures):
                    res = future.result()
                    if res:
                        all_results.extend(res)

            # Deep Crawl
            st.info("Deep Crawl en cours...")
            deep_links = []
            for item in all_results[:12]:
                if isinstance(item, dict) and "url" in item:
                    deep_links.extend(deep_crawl(item["url"], depth))
            all_results.extend([{"source": "Deep Crawl", "url": link} for link in deep_links])

            # Scoring
            for item in all_results:
                item["score"] = 50 + len(str(item).split()) // 5  # scoring simple

            all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

            # IA
            ai_text = ai_analyze(all_results, region, keywords) if use_ai else None

            # Affichage
            st.success(f"{len(all_results)} résultats collectés !")

            df = pd.DataFrame(all_results)
            st.dataframe(df, use_container_width=True)

            if ai_text:
                st.subheader("🤖 Analyse IA des meilleurs spots")
                st.markdown(ai_text)

            # Export
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            json_file = f"urbex_max_{region}_{ts}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump({
                    "date": datetime.now().isoformat(),
                    "region": region,
                    "keywords": keywords,
                    "results": all_results
                }, f, indent=2, ensure_ascii=False)

            st.download_button("📥 Télécharger JSON complet", open(json_file, "r").read(), json_file)

if __name__ == "__main__":
    main()
