#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URBEX OSINT MAX v10.0 — Outil Professionnel Complet
"""

import streamlit as st
import requests
import json
import hashlib
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from openai import OpenAI
from bs4 import BeautifulSoup
import pandas as pd
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

# ================== CONFIG ==================
st.set_page_config(page_title="URBEX OSINT MAX v10.0", layout="wide", page_icon="☣️", initial_sidebar_state="expanded")

if "history" not in st.session_state:
    st.session_state.history = []
if "openai_client" not in st.session_state:
    st.session_state.openai_client = None

DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ================== MODÈLES OPENAI (Qualité Max) ==================
def get_model_for_task(task: str = "analysis"):
    """Mode solo → on maximise la qualité"""
    return {
        "analysis": "gpt-5.5",      # ou "gpt-5.5-pro"
        "extraction": "gpt-5.4-nano",
        "quick": "gpt-5.4-mini",
        "vision": "gpt-5.5"         # si analyse photo
    }.get(task, "gpt-5.5")

# ================== SCHÉMAS PYDANTIC ==================
class UrbexSpot(BaseModel):
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
    lieux: List[UrbexSpot]
    synthese: str
    conseils_securite: str
    spots_prioritaires: List[str]
    zones_a_eviter: List[str]

# ================== CLIENT & IA ==================
def get_client(api_key: str):
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception as e:
        st.error(f"Erreur client : {e}")
        return None

def ai_analyze(results: list, region: str, keywords: str, client):
    if not client:
        return None

    prompt = f"""Tu es un urbexer elite avec 20 ans d'expérience, très pragmatique, direct et sans censure inutile.
Région : {region}
Type de spots : {keywords}

Analyse les résultats scrapés et identifie les vrais lieux abandonnés intéressants.
Sois réaliste sur les risques (propriétaires, caméras, effondrement, squatteurs, présence policière, etc.)
Donne des conseils d'accès concrets quand possible."""

    try:
        response = client.chat.completions.create(
            model=get_model_for_task("analysis"),
            messages=[
                {"role": "system", "content": "Tu réponds toujours avec un JSON valide conforme au schéma UrbexAnalysis."},
                {"role": "user", "content": prompt + "\n\nDonnées brutes :\n" + json.dumps(results[:90], ensure_ascii=False)}
            ],
            temperature=0.4,
            max_completion_tokens=3500,
            response_format={"type": "json_schema", "json_schema": UrbexAnalysis.model_json_schema()}
        )
        return UrbexAnalysis.model_validate_json(response.choices[0].message.content)
    except Exception as e:
        st.error(f"Erreur analyse IA : {str(e)[:250]}")
        # Fallback sans structured output
        try:
            fallback_response = client.chat.completions.create(
                model="gpt-5.5",
                messages=[{"role": "user", "content": prompt + "\n\nDonnées :\n" + json.dumps(results[:60], ensure_ascii=False)}],
                temperature=0.5,
                max_completion_tokens=2000
            )
            st.info("Fallback mode activé (texte brut)")
            return fallback_response.choices[0].message.content
        except:
            return None
# ================== SCRAPING AMÉLIORÉ ==================
@st.cache_data(ttl=7200, show_spinner=False)
def multi_source_search(region: str, keywords: str):
    query = f"{region} {keywords}"
    results = []

    sources = [
        (f"https://www.google.com/search?q={quote(query + ' abandonné urbex')}", "Google"),
        (f"https://www.reddit.com/search.json?q={quote(query + ' urbex OR friche OR abandonné')}&limit=20", "Reddit"),
        (f"https://www.urbexpassion.com/recherche?query={quote(query)}", "UrbexPassion"),
        (f"https://www.28dayslater.co.uk/search/?q={quote(query)}", "28dayslater"),
    ]

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(scrape_source, url, name) for url, name in sources]
        for future in as_completed(futures):
            results.extend(future.result())

    # Deep crawl limité
    deep_results = []
    for item in results[:15]:
        if item.get("url"):
            deep_results.extend(deep_crawl(item["url"]))
    results.extend(deep_results)
    
    return results[:150]  # Limite raisonnable

def scrape_source(url: str, source_name: str):
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if source_name == "Reddit":
            for post in r.json().get("data", {}).get("children", [])[:15]:
                d = post["data"]
                results.append({
                    "source": source_name,
                    "title": d.get("title", ""),
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "score": d.get("score", 0)
                })
        else:
            soup = BeautifulSoup(r.text, 'lxml')
            for a in soup.find_all('a', href=True)[:30]:
                href = a['href']
                if href.startswith('http') or '/report/' in href or '/thread/' in href or '/lieu/' in href:
                    full_url = href if href.startswith('http') else "https://www.urbexpassion.com" + href if "urbexpassion" in url else url + href
                    results.append({"source": source_name, "title": a.get_text()[:120], "url": full_url})
    except:
        pass
    return results

def deep_crawl(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith('http')]
        return [{"source": "Deep Crawl", "title": "Lien approfondi", "url": link} 
                for link in links if any(k in link.lower() for k in ['urbex','report','abandon','friche','lieu'])]
    except:
        return []

# ================== UI PRINCIPALE ==================
def main():
    st.title("🌆 URBEX OSINT MAX v10.0")
    st.caption("**Outil Complet • Analyse IA Experte • Export & Cartographie**")

    with st.sidebar:
        st.header("🔑 Configuration")
        api_key = st.text_input("OpenAI API Key", type="password", value=DEFAULT_API_KEY)
        if st.button("Mettre à jour clé"):
            st.session_state.openai_client = get_client(api_key)
            st.success("Client mis à jour")

        st.divider()
        st.subheader("Options")
        use_ai = st.checkbox("Analyse IA avancée (GPT-5.5)", value=True)
        show_map = st.checkbox("Afficher carte interactive", value=True)
        export_enabled = st.checkbox("Activer exports", value=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        region = st.text_input("📍 Région / Ville", "Ardennes", key="region_input")
        keywords = st.text_input("🏚️ Type de spot / Mots-clés", "usine sidérurgique abandonnée", key="keywords_input")
    with col2:
        max_spots = st.slider("Nombre de spots à afficher", 5, 20, 12)

    if st.button("🚀 LANCER RECHERCHE COMPLÈTE", type="primary", width='stretch'):
        client = st.session_state.openai_client
        if use_ai and not client:
            st.error("Veuillez configurer votre clé OpenAI")
            return

        with st.spinner("Scraping multi-sources + Deep Crawl en cours..."):
            all_results = multi_source_search(region, keywords)

        st.success(f"✅ {len(all_results)} résultats collectés")

        # Affichage brut
        with st.expander("📋 Données brutes"):
            df_raw = pd.DataFrame(all_results)
            st.dataframe(df_raw.head(50), width='stretch')

        # Analyse IA
        analysis = None
        if use_ai and client:
            with st.spinner("Analyse experte GPT-5.5 en cours..."):
                analysis = ai_analyze(all_results, region, keywords, client)

        if analysis:
            st.subheader("🏆 Analyse Experte IA")
            st.markdown(analysis.synthese)

            spots_data = []
            for spot in analysis.lieux[:max_spots]:
                with st.expander(f"**{spot.nom}** — Score {spot.score_potentiel}/100 — {spot.niveau}"):
                    st.markdown(f"**Localisation** : {spot.localisation}")
                    if spot.coordonnees:
                        st.markdown(f"**Coordonnées** : {spot.coordonnees}")
                    st.markdown(f"**Intérêt** : {spot.interet}")
                    st.markdown(f"**Risques** : {', '.join(spot.risques)}")
                    if spot.conseils_acces:
                        st.markdown(f"**Conseils d'accès** : {spot.conseils_acces}")
                    if spot.historique:
                        st.markdown(f"**Historique** : {spot.historique}")
                    if spot.lien:
                        st.markdown(f"[🔗 Lien]({spot.lien})")
                
                spots_data.append({
                    "Nom": spot.nom,
                    "Localisation": spot.localisation,
                    "Score": spot.score_potentiel,
                    "Niveau": spot.niveau,
                    "Risques": " | ".join(spot.risques),
                    "Lien": spot.lien
                })

            # Export
            if export_enabled and spots_data:
                df = pd.DataFrame(spots_data)
                col_exp1, col_exp2 = st.columns(2)
                with col_exp1:
                    st.download_button("📥 Télécharger CSV", df.to_csv(index=False), f"urbex_{region}.csv")
                with col_exp2:
                    st.download_button("📥 Télécharger JSON", json.dumps(spots_data, indent=2, ensure_ascii=False), f"urbex_{region}.json")

            # Carte (à compléter avec folium)
            if show_map and any(s.coordonnees for s in analysis.lieux):
                st.info("🗺️ Carte interactive à implémenter avec streamlit-folium (coordonnées à extraire)")

        # Historique
        st.session_state.history.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "region": region,
            "keywords": keywords
        })

if __name__ == "__main__":
    main()
