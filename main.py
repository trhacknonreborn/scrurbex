#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URBEX OSINT MAX v10.4 — Version Stable Finale
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
    page_title="URBEX OSINT MAX v10.4",
    layout="wide",
    page_icon="☣️",
    initial_sidebar_state="expanded"
)

# Session State
if "history" not in st.session_state:
    st.session_state.history = []
if "openai_client" not in st.session_state:
    st.session_state.openai_client = None

DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
}

# ================== MODÈLES ==================
def get_model_for_task(task: str = "analysis"):
    return "gpt-5.5"  # Modèle principal recommandé

# ================== SCHÉMAS ==================
class UrbexSpot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nom: str
    localisation: str
    coordonnees: Optional[str] = None
    interet: str
    niveau: str
    risques: List[str]
    conseils_acces: Optional[str] = None
    historique: Optional[str] = None
    lien: Optional[str] = None
    score_potentiel: int = Field(..., ge=0, le=100)

class UrbexAnalysis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lieux: List[UrbexSpot]
    synthese: str
    conseils_securite: str
    spots_prioritaires: List[str] = Field(default_factory=list)
    zones_a_eviter: List[str] = Field(default_factory=list)

# Fonction pour corriger le schéma OpenAI
def prepare_schema_for_openai(model_class):
    schema = model_class.model_json_schema()
    # Force additionalProperties: false partout
    def add_additional_properties_false(obj: Dict[str, Any]):
        if isinstance(obj, dict):
            if obj.get("type") == "object":
                obj["additionalProperties"] = False
            for value in obj.values():
                if isinstance(value, dict):
                    add_additional_properties_false(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            add_additional_properties_false(item)
        return obj
    
    schema = add_additional_properties_false(schema)
    return schema

# ================== CLIENT ==================
def get_client(api_key: str):
    if not api_key or not api_key.strip():
        return None
    try:
        return OpenAI(api_key=api_key.strip())
    except Exception as e:
        st.error(f"Erreur client : {e}")
        return None

# ================== ANALYSE IA ==================
def ai_analyze(results: list, region: str, keywords: str, client):
    if not client:
        return None

    prompt = f"""Tu es un urbexer expérimenté et réaliste.
Région : {region}
Recherche : {keywords}

Analyse les résultats et identifie les meilleurs spots concrets."""

    try:
        schema = prepare_schema_for_openai(UrbexAnalysis)

        response = client.chat.completions.create(
            model=get_model_for_task(),
            messages=[
                {"role": "system", "content": "Réponds uniquement avec un JSON valide selon le schéma fourni."},
                {"role": "user", "content": prompt + "\n\nDonnées brutes :\n" + json.dumps(results[:120], ensure_ascii=False)}
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
        st.error(f"Erreur analyse IA : {str(e)[:300]}")
        # Fallback
        try:
            st.info("🔄 Fallback activé")
            fallback = client.chat.completions.create(
                model=get_model_for_task(),
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Analyse ces résultats et structure ta réponse clairement :\n" + json.dumps(results[:80], ensure_ascii=False)}
                ],
                max_completion_tokens=2800
            )
            return fallback.choices[0].message.content
        except Exception as fb:
            st.error(f"Fallback échoué : {fb}")
            return None

# ================== SCRAPING (renforcé) ==================
@st.cache_data(ttl=7200, show_spinner=False)
def multi_source_search(region: str, keywords: str):
    query = f"{region} {keywords}"
    results = []

    sources = [
        (f"https://www.google.com/search?q={quote(query + ' urbex OR friche OR usine abandonnée OR bâtiment désaffecté')}", "Google"),
        (f"https://www.reddit.com/search.json?q={quote(query + ' urbex OR abandonné OR friche')}&limit=30", "Reddit"),
        (f"https://www.urbexpassion.com/recherche?query={quote(query)}", "UrbexPassion"),
        (f"https://www.28dayslater.co.uk/search/?q={quote(query)}", "28dayslater"),
    ]

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(scrape_source, url, name) for url, name in sources]
        for future in as_completed(futures):
            results.extend(future.result() or [])

    # Deep crawl
    for item in results[:18]:
        if item.get("url"):
            results.extend(deep_crawl(item["url"]))

    return results[:220]

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
                    "title": d.get("title", "")[:200],
                    "url": f"https://reddit.com{d.get('permalink', '')}"
                })
        else:
            soup = BeautifulSoup(r.text, 'lxml')
            for a in soup.find_all('a', href=True)[:50]:
                href = a['href']
                title = a.get_text(strip=True)[:200]
                if href and title and len(title) > 5:
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
            if href.startswith('http') and any(k in href.lower() for k in ['urbex', 'report', 'thread', 'abandon', 'friche', 'lieu']):
                links.append({"source": "Deep Crawl", "title": a.get_text(strip=True)[:150] or "Lien", "url": href})
                if len(links) >= 12:
                    break
        return links
    except:
        return []

# ================== MAIN ==================
def main():
    st.title("🌆 URBEX OSINT MAX v10.4")
    st.caption("**Stable • GPT-5.5 • Schema corrigé**")

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
                st.error("Ajoute ta clé OpenAI dans la sidebar.")
                st.stop()

            with st.spinner("Scraping multi-sources en cours..."):
                all_results = multi_source_search(region, keywords)

            st.success(f"✅ {len(all_results)} résultats collectés")

            with st.expander("📋 Résultats bruts"):
                st.dataframe(pd.DataFrame(all_results).head(70), width='stretch')

            if use_ai and client:
                with st.spinner("Analyse GPT-5.5 en cours..."):
                    analysis = ai_analyze(all_results, region, keywords, client)

                if analysis:
                    if isinstance(analysis, UrbexAnalysis):
                        st.subheader("🏆 Analyse Experte")
                        st.markdown(analysis.synthese)

                        spots_data = []
                        for spot in analysis.lieux[:max_spots]:
                            with st.expander(f"**{spot.nom}** — {spot.niveau} — Score {spot.score_potentiel}/100"):
                                st.markdown(f"**Localisation** : {spot.localisation}")
                                st.markdown(f"**Intérêt** : {spot.interet}")
                                st.markdown(f"**Risques** : {', '.join(spot.risques)}")
                                if spot.conseils_acces:
                                    st.markdown(f"**Conseils accès** : {spot.conseils_acces}")
                                if spot.lien:
                                    st.markdown(f"[🔗 Lien]({spot.lien})")
                            spots_data.append(spot.model_dump())

                        if spots_data:
                            df = pd.DataFrame(spots_data)
                            c1, c2 = st.columns(2)
                            with c1:
                                st.download_button("📥 CSV", df.to_csv(index=False), f"urbex_{region}.csv")
                            with c2:
                                st.download_button("📥 JSON", json.dumps(spots_data, indent=2, ensure_ascii=False), f"urbex_{region}.json")
                    else:
                        st.subheader("Analyse (texte)")
                        st.markdown(str(analysis))

            st.session_state.history.append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "region": region, "keywords": keywords})

    if st.session_state.history:
        with st.expander("Historique"):
            st.dataframe(pd.DataFrame(st.session_state.history))

if __name__ == "__main__":
    main()
