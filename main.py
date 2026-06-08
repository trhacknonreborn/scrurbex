#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URBEX OSINT MAX v10.1 — Version Propre & Puissante
Optimisé pour GPT-5.5 • Usage solo
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
from typing import List, Optional

# ================== CONFIGURATION STREAMLIT ==================
st.set_page_config(
    page_title="URBEX OSINT MAX v10.1",
    layout="wide",
    page_icon="☣️",
    initial_sidebar_state="expanded"
)

# Session state
if "history" not in st.session_state:
    st.session_state.history = []
if "openai_client" not in st.session_state:
    st.session_state.openai_client = None

DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
}

# ================== MODÈLES OPENAI ==================
def get_model_for_task(task: str = "analysis"):
    """Modèle principal : GPT-5.5 (le plus adapté pour l'urbex)"""
    models = {
        "analysis": "gpt-5.5",      # Meilleur équilibre qualité/raisonnement
        "extraction": "gpt-5.4-nano",
        "quick": "gpt-5.4-mini",
    }
    return models.get(task, "gpt-5.5")

# ================== SCHÉMAS PYDANTIC ==================
class UrbexSpot(BaseModel):
    nom: str = Field(..., description="Nom du lieu")
    localisation: str = Field(..., description="Localisation précise ou approximative")
    coordonnees: Optional[str] = None
    interet: str = Field(..., description="Pourquoi ce spot est intéressant")
    niveau: str = Field(..., description="Élevé | Moyen | Faible")
    risques: List[str] = Field(..., description="Liste des risques")
    conseils_acces: Optional[str] = None
    historique: Optional[str] = None
    lien: Optional[str] = None
    score_potentiel: int = Field(..., ge=0, le=100)

class UrbexAnalysis(BaseModel):
    lieux: List[UrbexSpot]
    synthese: str
    conseils_securite: str
    spots_prioritaires: List[str] = Field(default_factory=list)
    zones_a_eviter: List[str] = Field(default_factory=list)

# ================== CLIENT OPENAI ==================
def get_client(api_key: str):
    if not api_key or api_key.strip() == "":
        return None
    try:
        return OpenAI(api_key=api_key.strip())
    except Exception as e:
        st.error(f"Impossible de créer le client OpenAI : {e}")
        return None

# ================== ANALYSE IA (CORRIGÉE) ==================
def ai_analyze(results: list, region: str, keywords: str, client):
    if not client:
        return None

    prompt = f"""Tu es un urbexer expérimenté, discret, pragmatique et direct.
Région cible : {region}
Type de lieux : {keywords}

Analyse les résultats de scraping. Identifie uniquement les lieux réels et intéressants.
Sois honnête sur les risques (légal, structurel, humain, etc.) et propose des conseils d'accès réalistes."""

    try:
        schema = UrbexAnalysis.model_json_schema()

        response = client.chat.completions.create(
            model=get_model_for_task("analysis"),
            messages=[
                {"role": "system", "content": "Tu réponds exclusivement avec un JSON valide selon le schéma fourni."},
                {"role": "user", "content": prompt + "\n\nDonnées brutes :\n" + json.dumps(results[:90], ensure_ascii=False)}
            ],
            temperature=0.4,
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
        st.error(f"Erreur analyse IA : {str(e)[:280]}")
        
        # Fallback propre
        try:
            st.info("🔄 Mode fallback activé (texte libre)")
            fallback = client.chat.completions.create(
                model=get_model_for_task("analysis"),
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Analyse ces résultats et structure ta réponse clairement :\n" + 
                                             json.dumps(results[:60], ensure_ascii=False)}
                ],
                temperature=0.5,
                max_completion_tokens=2800
            )
            return fallback.choices[0].message.content
        except Exception as fb_err:
            st.error(f"Fallback échoué : {fb_err}")
            return None

# ================== SCRAPING ==================
@st.cache_data(ttl=7200, show_spinner=False)
def multi_source_search(region: str, keywords: str):
    query = f"{region} {keywords}"
    results = []

    sources = [
        (f"https://www.google.com/search?q={quote(query + ' urbex abandonné')}", "Google"),
        (f"https://www.reddit.com/search.json?q={quote(query + ' urbex OR friche OR abandonné')}&limit=20", "Reddit"),
        (f"https://www.urbexpassion.com/recherche?query={quote(query)}", "UrbexPassion"),
        (f"https://www.28dayslater.co.uk/search/?q={quote(query)}", "28dayslater"),
    ]

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(scrape_source, url, name) for url, name in sources]
        for future in as_completed(futures):
            results.extend(future.result() or [])

    # Deep crawl léger
    for item in results[:12]:
        if item.get("url"):
            results.extend(deep_crawl(item["url"]))

    return results[:160]

def scrape_source(url: str, source_name: str):
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        
        if source_name == "Reddit":
            data = r.json().get("data", {}).get("children", [])[:15]
            for post in data:
                d = post["data"]
                results.append({
                    "source": source_name,
                    "title": d.get("title", "")[:150],
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "score": d.get("score", 0)
                })
        else:
            soup = BeautifulSoup(r.text, 'lxml')
            for a in soup.find_all('a', href=True)[:35]:
                href = a['href']
                if href.startswith(('http', '/')) and any(k in href.lower() for k in ['urbex', 'report', 'thread', 'lieu', 'abandon']):
                    full_url = href if href.startswith('http') else f"https://www.urbexpassion.com{href}" if "urbexpassion" in url else url + href
                    results.append({
                        "source": source_name,
                        "title": a.get_text(strip=True)[:150] or "Sans titre",
                        "url": full_url
                    })
    except Exception:
        pass
    return results

def deep_crawl(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=9)
        soup = BeautifulSoup(r.text, 'lxml')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('http') and any(k in href.lower() for k in ['urbex', 'report', 'thread', 'abandon', 'friche']):
                links.append({"source": "Deep Crawl", "title": a.get_text(strip=True)[:100] or "Lien", "url": href})
                if len(links) >= 8:
                    break
        return links
    except:
        return []

# ================== INTERFACE ==================
def main():
    st.title("🌆 URBEX OSINT MAX v10.1")
    st.caption("**Outil puissant • GPT-5.5 • Analyse experte**")

    with st.sidebar:
        st.header("🔑 Configuration")
        api_key = st.text_input("OpenAI API Key", type="password", value=DEFAULT_API_KEY)
        if st.button("Mettre à jour la clé"):
            st.session_state.openai_client = get_client(api_key)
            st.success("✅ Client OpenAI mis à jour")

        st.divider()
        st.subheader("Paramètres")
        use_ai = st.checkbox("Analyse IA avancée (GPT-5.5)", value=True)
        max_spots = st.slider("Nombre maximum de spots", 6, 20, 12)

    col1, col2 = st.columns([3, 1])
    with col1:
        region = st.text_input("📍 Région / Ville", "Ardennes")
        keywords = st.text_input("🏚️ Type de spot / Mots-clés", "usine sidérurgique abandonnée")
    with col2:
        if st.button("🚀 LANCER RECHERCHE COMPLÈTE", type="primary", use_container_width=True):
            client = st.session_state.openai_client
            if use_ai and not client:
                st.error("Configure ta clé OpenAI dans la barre latérale.")
                st.stop()

            with st.spinner("Scraping multi-sources + Deep Crawl..."):
                all_results = multi_source_search(region, keywords)

            st.success(f"✅ {len(all_results)} résultats collectés")

            # Affichage brut
            with st.expander("📋 Résultats bruts"):
                df_raw = pd.DataFrame(all_results)
                st.dataframe(df_raw.head(40), use_container_width=True)

            # Analyse IA
            if use_ai and client:
                with st.spinner("🤖 Analyse experte GPT-5.5 en cours..."):
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
                                    st.markdown(f"**Conseils d'accès** : {spot.conseils_acces}")
                                if spot.historique:
                                    st.markdown(f"**Historique** : {spot.historique}")
                                if spot.lien:
                                    st.markdown(f"[🔗 Lien]({spot.lien})")
                            
                            spots_data.append(spot.model_dump())

                        # Export
                        if spots_data:
                            df = pd.DataFrame(spots_data)
                            col1_exp, col2_exp = st.columns(2)
                            with col1_exp:
                                st.download_button("📥 CSV", df.to_csv(index=False), f"urbex_{region}_{datetime.now().strftime('%Y%m%d')}.csv")
                            with col2_exp:
                                st.download_button("📥 JSON", json.dumps(spots_data, indent=2, ensure_ascii=False), f"urbex_{region}.json")
                    else:
                        # Fallback texte
                        st.subheader("Analyse (mode texte)")
                        st.markdown(analysis)

            # Historique
            st.session_state.history.append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "region": region,
                "keywords": keywords
            })

    # Historique rapide
    if st.session_state.history:
        with st.expander("Historique des recherches"):
            st.dataframe(pd.DataFrame(st.session_state.history))

if __name__ == "__main__":
    main()
