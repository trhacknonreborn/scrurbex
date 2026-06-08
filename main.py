#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URBEX OSINT MAX v9.0 — Ultra Optimisé & Fiable
Auteur : Optimisé par Grok
"""

import streamlit as st
import requests
import json
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from openai import OpenAI
from bs4 import BeautifulSoup
import hashlib
from functools import lru_cache
import os

# ================== CONFIGURATION ==================
st.set_page_config(page_title="URBEX OSINT MAX v9.0", layout="wide", page_icon="☣️")

# Gestion sécurisée de la clé API
if "openai_client" not in st.session_state:
    st.session_state.openai_client = None

DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY", "")  # Préférer variables d'environnement

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
}

# ================== ROUTING MODÈLES OPENAI ==================
def get_openai_client(api_key: str):
    try:
        return OpenAI(api_key=api_key)
    except Exception as e:
        st.error(f"Erreur client OpenAI: {e}")
        return None

def get_model_for_task(task: str = "analysis"):
    """Routing intelligent selon la tâche pour optimiser coût/performance"""
    models = {
        "quick": "gpt-5.4-mini",      # Interactions rapides, chat
        "extraction": "gpt-5.4-nano", # Summarization & structuration massive
        "analysis": "gpt-5.4",        # Raisonnement principal (recommandé)
        "pro": "gpt-5.4-pro" if "pro" in ["gpt-5.4-pro"] else "gpt-5.4"  # Pour tâches très complexes
    }
    return models.get(task, "gpt-5.4")

# ================== PROMPT + STRUCTURED OUTPUT ==================
from pydantic import BaseModel, Field
from typing import List, Optional

class UrbexSpot(BaseModel):
    nom: str = Field(..., description="Nom précis du lieu")
    localisation: str = Field(..., description="Localisation approximative (ville, coordonnées ou description)")
    interet: str = Field(..., description="Pourquoi ce spot est intéressant (taille, histoire, rareté, état)")
    niveau: str = Field(..., description="Élevé | Moyen | Faible")
    risques: List[str] = Field(..., description="Risques principaux (légal, structurel, sécurité, etc.)")
    lien: Optional[str] = Field(None, description="Lien principal ou source")
    distance_estimee: Optional[str] = Field(None, description="Distance estimée depuis le point de recherche")

class UrbexAnalysis(BaseModel):
    lieux: List[UrbexSpot] = Field(..., description="Liste de 8 à 12 meilleurs spots")
    synthese: str = Field(..., description="Synthèse générale des opportunités dans la région")
    conseils_securite: str = Field(..., description="Conseils généraux de sécurité pour cette recherche")

def ai_analyze_structured(results, region: str, keywords: str, client):
    if not client:
        return {"error": "OpenAI non configuré"}

    prompt = f"""Tu es un expert urbex chevronné, prudent et réaliste.
Région : {region}
Type de lieux recherchés : {keywords}

Analyse uniquement les résultats fournis et identifie les lieux **réels et concrets** (usines, châteaux, hôpitaux, friches, etc.).
Ignore les résultats trop vagues ou sans nom précis.
Priorise les spots intéressants, peu documentés publiquement et potentiellement accessibles.

Retourne uniquement le JSON conforme au schéma demandé."""

    try:
        response = client.chat.completions.create(
            model=get_model_for_task("analysis"),
            messages=[
                {"role": "system", "content": "Tu es un analyste urbex précis. Réponds toujours en JSON valide selon le schéma fourni."},
                {"role": "user", "content": prompt + "\n\nRésultats bruts:\n" + json.dumps(results[:80], ensure_ascii=False)}
            ],
            temperature=0.5,
            max_tokens=2500,
            response_format={
                "type": "json_schema",
                "json_schema": UrbexAnalysis.model_json_schema()
            }
        )
        
        content = response.choices[0].message.content
        analysis = UrbexAnalysis.model_validate_json(content)
        return analysis
        
    except Exception as e:
        st.error(f"Erreur Structured Output: {str(e)[:200]}")
        # Fallback simple
        return {"error": str(e)}

# ================== CACHING & SCRAPING OPTIMISÉ ==================
@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(query: str):
    return search_concrete_places(query)

@lru_cache(maxsize=50)
def get_cache_key(region: str, keywords: str):
    return hashlib.md5(f"{region}|{keywords}".encode()).hexdigest()

def deep_crawl(url: str, max_links: int = 8):
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'lxml')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('http') and any(k in href.lower() for k in ['urbex', 'report', 'thread', 'lieu', 'abandon']):
                links.append(href)
                if len(links) >= max_links:
                    break
        return links[:max_links]
    except:
        return []

def search_concrete_places(query: str):
    results = []
    searches = [
        f"{query} usine abandonnée", f"{query} friche industrielle",
        f"{query} hôpital abandonné", f"{query} château abandonné",
        f"{query} site urbex", f"{query} base militaire abandonnée"
    ]
    for s in searches:
        results.append({
            "source": "Google-like",
            "title": s,
            "url": f"https://www.google.com/search?q={quote(s)}"
        })
    return results

def scrape_reddit(query: str):
    # ... (garde ta fonction originale avec améliorations mineures)
    results = []
    try:
        r = requests.get(
            f"https://www.reddit.com/search.json?q={quote(query + ' urbex OR abandonné OR friche')}&limit=15",
            headers=HEADERS, timeout=10
        )
        for post in r.json().get("data", {}).get("children", [])[:12]:
            d = post["data"]
            results.append({
                "source": "Reddit",
                "title": d.get("title", "")[:120],
                "url": f"https://reddit.com{d.get('permalink', '')}"
            })
    except:
        pass
    return results

# (Garde tes autres scrapers : urbexpassion, 28dayslater)

def main():
    st.title("🌆 URBEX OSINT MAX v9.0")
    st.caption("**Scraping + IA Structurée • Ultra Optimisé**")

    # Sidebar
    with st.sidebar:
        st.header("🔑 Configuration")
        api_key = st.text_input("OpenAI API Key", type="password", value=DEFAULT_API_KEY)
        if st.button("🔄 Mettre à jour clé"):
            st.session_state.openai_client = get_openai_client(api_key)
            st.success("Client mis à jour")

        st.divider()
        st.info("**Conseils** : Utilise `gpt-5.4` pour meilleure qualité.")

    # Main UI
    col1, col2 = st.columns([3, 1])
    with col1:
        region = st.text_input("📍 Région / Ville", "Ardennes", key="region")
        keywords = st.text_input("🏚️ Type de lieu / mots-clés", "usine sidérurgique", key="keywords")
    with col2:
        use_ai = st.checkbox("🤖 Analyse IA Structurée", value=True)
        max_spots = st.slider("Nombre max de spots", 6, 15, 10)

    if st.button("🚀 LANCER RECHERCHE MAX", type="primary", use_container_width=True):
        client = st.session_state.openai_client
        if not client and use_ai:
            st.error("Configure ta clé OpenAI dans la sidebar !")
            return

        with st.spinner("Recherche multi-sources + Deep Crawl..."):
            all_results = []
            
            with ThreadPoolExecutor(max_workers=8) as ex:
                futures = [
                    ex.submit(search_concrete_places, f"{region} {keywords}"),
                    ex.submit(scrape_reddit, f"{region} {keywords}"),
                    # Ajoute tes autres scrapers ici
                ]
                for future in as_completed(futures):
                    all_results.extend(future.result() or [])

            # Deep crawl limité
            st.info("Deep Crawl sur les meilleurs liens...")
            deep_links = []
            for item in all_results[:12]:
                if item.get("url"):
                    deep_links.extend(deep_crawl(item["url"]))
            
            all_results.extend([{"source": "Deep Crawl", "url": link} for link in deep_links[:30]])

            st.success(f"✅ {len(all_results)} résultats collectés")

            # Affichage brut
            with st.expander("📋 Résultats bruts (premiers 30)"):
                for i, res in enumerate(all_results[:30], 1):
                    st.markdown(f"**{i}.** {res.get('source')} — [{res.get('title', res.get('url',''))[:100]}]({res.get('url', '#')})")

            # Analyse IA
            if use_ai and client:
                with st.spinner("🤖 Analyse IA structurée en cours (GPT-5.4)..."):
                    analysis = ai_analyze_structured(all_results, region, keywords, client)
                    
                    if isinstance(analysis, dict) and "error" in analysis:
                        st.error(analysis["error"])
                    else:
                        st.subheader("🏆 Meilleurs Spots selon l'IA")
                        st.markdown(analysis.synthese)
                        
                        for spot in analysis.lieux[:max_spots]:
                            with st.expander(f"**{spot.nom}** — {spot.niveau}"):
                                st.markdown(f"**Localisation** : {spot.localisation}")
                                st.markdown(f"**Intérêt** : {spot.interet}")
                                st.markdown(f"**Risques** : {', '.join(spot.risques)}")
                                if spot.lien:
                                    st.markdown(f"[🔗 Lien]({spot.lien})")
                        
                        st.info("**Conseils Sécurité** :\n" + analysis.conseils_securite)

if __name__ == "__main__":
    main()
