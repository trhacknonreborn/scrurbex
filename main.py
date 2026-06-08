#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URBEX OSINT MAX v10.5 — Schema OpenAI Corrigé Définitivement
"""

import streamlit as st
import requests
import json
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from openai import OpenAI
from bs4 import BeautifulSoup
import pandas as pd
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any

st.set_page_config(
    page_title="URBEX OSINT MAX v10.5",
    layout="wide",
    page_icon="☣️",
    initial_sidebar_state="expanded"
)

if "history" not in st.session_state:
    st.session_state.history = []
if "openai_client" not in st.session_state:
    st.session_state.openai_client = None

DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
}

# ================== MODÈLE ==================
def get_model_for_task():
    return "gpt-5.5"

# ================== SCHÉMAS SIMPLIFIÉS & CORRIGÉS ==================
class UrbexSpot(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    
    nom: str
    localisation: str
    interet: str
    niveau: str
    risques: List[str]
    score_potentiel: int = Field(..., ge=0, le=100)
    coordonnees: Optional[str] = None
    conseils_acces: Optional[str] = None
    historique: Optional[str] = None
    lien: Optional[str] = None

class UrbexAnalysis(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    
    lieux: List[UrbexSpot]
    synthese: str
    conseils_securite: str
    spots_prioritaires: List[str] = Field(default_factory=list)
    zones_a_eviter: List[str] = Field(default_factory=list)

# Préparation du schéma OpenAI
def prepare_schema_for_openai(model_class):
    schema = model_class.model_json_schema()
    
    # Force additionalProperties: false
    def enforce_strict(obj):
        if isinstance(obj, dict):
            if obj.get("type") == "object":
                obj["additionalProperties"] = False
            for v in obj.values():
                if isinstance(v, dict):
                    enforce_strict(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            enforce_strict(item)
        return obj
    
    schema = enforce_strict(schema)
    return schema

# ================== CLIENT ==================
def get_client(api_key: str):
    if not api_key or not api_key.strip():
        return None
    try:
        return OpenAI(api_key=api_key.strip())
    except Exception as e:
        st.error(f"Erreur client OpenAI: {e}")
        return None

# ================== ANALYSE IA ==================
def ai_analyze(results: list, region: str, keywords: str, client):
    if not client:
        return None

    prompt = f"""Tu es un expert urbex réaliste.
Région : {region}
Mots-clés : {keywords}

Analyse les résultats et retourne **uniquement** les spots concrets intéressants."""

    try:
        schema = prepare_schema_for_openai(UrbexAnalysis)

        response = client.chat.completions.create(
            model=get_model_for_task(),
            messages=[
                {"role": "system", "content": "Tu dois répondre EXCLUSIVEMENT avec un JSON valide selon le schéma fourni."},
                {"role": "user", "content": prompt + "\n\nDonnées brutes :\n" + json.dumps(results[:130], ensure_ascii=False)}
            ],
            max_completion_tokens=3500,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "urbex_analysis",
                    "schema": schema,
                    "strict": True
                }
            }
        )
        return UrbexAnalysis.model_validate_json(response.choices[0].message.content)

    except Exception as e:
        st.error(f"Erreur analyse IA : {str(e)[:350]}")
        try:
            st.info("🔄 Fallback activé")
            fallback = client.chat.completions.create(
                model=get_model_for_task(),
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Analyse ces résultats et structure ta réponse de façon claire et organisée."}
                ],
                max_completion_tokens=2800
            )
            return fallback.choices[0].message.content
        except Exception as fb:
            st.error(f"Fallback échoué : {fb}")
            return None

# ================== SCRAPING (très renforcé) ==================
@st.cache_data(ttl=7200)
def multi_source_search(region: str, keywords: str):
    query = f"{region} {keywords}"
    results = []

    search_terms = ["urbex", "friche", "usine abandonnée", "bâtiment désaffecté", "site abandonné"]

    sources = []
    for term in search_terms:
        sources.append((f"https://www.google.com/search?q={quote(query + ' ' + term)}", "Google"))
    
    sources.extend([
        (f"https://www.reddit.com/search.json?q={quote(query + ' urbex OR friche OR abandonné')}&limit=30", "Reddit"),
        (f"https://www.urbexpassion.com/recherche?query={quote(query)}", "UrbexPassion"),
    ])

    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = [ex.submit(scrape_source, url, name) for url, name in sources]
        for future in as_completed(futures):
            results.extend(future.result() or [])

    # Deep crawl
    for item in results[:20]:
        if item.get("url"):
            results.extend(deep_crawl(item["url"]))

    return results[:250]

def scrape_source(url: str, source_name: str):
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        
        if source_name == "Reddit":
            for post in r.json().get("data", {}).get("children", [])[:25]:
                d = post["data"]
                results.append({
                    "source": source_name,
                    "title": d.get("title", "")[:220],
                    "url": f"https://reddit.com{d.get('permalink', '')}"
                })
        else:
            soup = BeautifulSoup(r.text, 'lxml')
            for a in soup.find_all('a', href=True)[:60]:
                href = a['href']
                title = a.get_text(strip=True)[:220]
                if href and title and len(title) > 8:
                    full_url = href if href.startswith('http') else f"https://www.urbexpassion.com{href}" if "urbexpassion" in url else url + href
                    results.append({"source": source_name, "title": title, "url": full_url})
    except:
        pass
    return results

def deep_crawl(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('http') and any(k in href.lower() for k in ['urbex','report','thread','abandon','friche','lieu']):
                links.append({"source": "Deep Crawl", "title": a.get_text(strip=True)[:160] or "Lien", "url": href})
                if len(links) >= 15:
                    break
        return links
    except:
        return []

# ================== INTERFACE ==================
def main():
    st.title("🌆 URBEX OSINT MAX v10.5")
    st.caption("**Schema OpenAI fixé • Scraping renforcé**")

    with st.sidebar:
        st.header("🔑 Configuration")
        api_key = st.text_input("OpenAI API Key", type="password", value=DEFAULT_API_KEY)
        if st.button("Mettre à jour clé"):
            st.session_state.openai_client = get_client(api_key)
            st.success("✅ Client mis à jour")

        st.divider()
        use_ai = st.checkbox("Analyse IA GPT-5.5", value=True)
        max_spots = st.slider("Nombre max de spots", 6, 20, 12)

    col1, col2 = st.columns([3, 1])
    with col1:
        region = st.text_input("📍 Région / Ville", "Belfort")
        keywords = st.text_input("🏚️ Type de spot / Mots-clés", "usine abandonnée friche")
    with col2:
        if st.button("🚀 LANCER RECHERCHE COMPLÈTE", type="primary", width='stretch'):
            client = st.session_state.openai_client
            if use_ai and not client:
                st.error("Ajoute ta clé OpenAI.")
                st.stop()

            with st.spinner("Scraping en cours..."):
                all_results = multi_source_search(region, keywords)

            st.success(f"✅ {len(all_results)} résultats collectés")

            with st.expander("📋 Résultats bruts"):
                st.dataframe(pd.DataFrame(all_results).head(80), width='stretch')

            if use_ai and client:
                with st.spinner("Analyse GPT-5.5..."):
                    analysis = ai_analyze(all_results, region, keywords, client)

                if analysis:
                    if isinstance(analysis, UrbexAnalysis):
                        st.subheader("🏆 Analyse Experte")
                        st.markdown(analysis.synthese)

                        for spot in analysis.lieux[:max_spots]:
                            with st.expander(f"**{spot.nom}** — {spot.niveau} — {spot.score_potentiel}/100"):
                                st.markdown(f"**Localisation** : {spot.localisation}")
                                st.markdown(f"**Intérêt** : {spot.interet}")
                                st.markdown(f"**Risques** : {', '.join(spot.risques)}")
                                if spot.conseils_acces:
                                    st.markdown(f"**Conseils accès** : {spot.conseils_acces}")
                                if spot.lien:
                                    st.markdown(f"[🔗 Lien]({spot.lien})")
                    else:
                        st.subheader("Analyse")
                        st.markdown(str(analysis))

            st.session_state.history.append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "region": region, "keywords": keywords})

    if st.session_state.history:
        with st.expander("Historique"):
            st.dataframe(pd.DataFrame(st.session_state.history))

if __name__ == "__main__":
    main()
