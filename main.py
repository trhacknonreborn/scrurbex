#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URBEX OSINT MAX v8.2 — Version Finale Optimisée
"""

import streamlit as st
import requests
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from openai import OpenAI
from bs4 import BeautifulSoup

st.set_page_config(page_title="URBEX OSINT by TRHACKNON", layout="wide", page_icon="☣️")

# ================== CLÉ OPENAI PAR DÉFAUT ==================
DEFAULT_API_KEY = ""

if "openai_client" not in st.session_state:
    try:
        st.session_state.openai_client = OpenAI(api_key=DEFAULT_API_KEY)
    except:
        st.session_state.openai_client = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ================== PROMPT IA AMÉLIORÉ ==================
def ai_analyze(results, region, keywords):
    if not st.session_state.openai_client:
        return "⚠️ OpenAI non configuré."

    prompt = f"""Tu es un expert très expérimenté en exploration urbaine (urbex).

**Mission :** Trouver des lieux abandonnés **concrets et intéressants** dans la région de {region} liés à {keywords}.

**Instructions strictes :**
- Ne garde que les lieux réels (usines, friches, hôpitaux, châteaux, bases, écoles, mines, etc.)
- Ignore les résultats trop généraux ou sans nom de lieu précis.
- Prefere les lieux d'exploration comme d'anciennes maisons dont les proprietaires ont disparu et qui ont été laissés à l'abandon
- Pour chaque lieu retenu, donne :
   • Nom du lieu + localisation approximative
   • Pourquoi il est intéressant (taille, état d'abandon, rareté, accessibilité, et distance par rapport au lieu indiqué dans la recherche)
   • Niveau de potentiel (Élevé / Moyen)
   • Lien principal

Liste maximum **10 à 12 lieux** les plus prometteurs.

Résultats bruts à analyser :
"""

    try:
        response = st.session_state.openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt + json.dumps(results[:90], ensure_ascii=False)}],
            temperature=0.6,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur OpenAI : {str(e)}"


# ================== SCRAPING ==================
def deep_crawl(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        links = [a.get('href') for a in soup.find_all('a', href=True)]
        return [link for link in links if link and link.startswith('http') and 
                any(x in link for x in ['report', 'thread', 'lieu', 'urbex', 'carte-urbex'])][:15]
    except:
        return []


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
        results.append({"source": "Google", "title": s, "url": f"https://www.google.com/search?q={quote(s)}"})
    return results


def scrape_reddit(query):
    results = []
    try:
        r = requests.get(f"https://www.reddit.com/search.json?q={quote(query + ' urbex OR abandonné OR friche')}&limit=20", 
                        headers=HEADERS, timeout=12)
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
        r = requests.get(f"https://www.urbexpassion.com/recherche?query={quote(query)}", headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.find_all('a', href=True):
            if '/report/' in a['href'] or '/lieu/' in a['href']:
                url = "https://www.urbexpassion.com" + a['href'] if not a['href'].startswith('http') else a['href']
                results.append({"source": "UrbexPassion", "title": a.get_text()[:100], "url": url})
    except:
        pass
    return results


def scrape_28dayslater(query):
    results = []
    try:
        r = requests.get(f"https://www.28dayslater.co.uk/search/?q={quote(query)}", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.find_all('a', href=True):
            if '/threads/' in a['href']:
                url = "https://www.28dayslater.co.uk" + a['href'] if not a['href'].startswith('http') else a['href']
                results.append({"source": "28dayslater", "title": a.get_text()[:80], "url": url})
    except:
        pass
    return results


def main():
    st.title("🌆 URBEX OSINT MAX v8.2")
    st.caption("**Scraping Amélioré + IA Optimisée**")

    with st.sidebar:
        st.header("Configuration")
        key = st.text_input("OpenAI API Key", type="password", value=DEFAULT_API_KEY)
        if st.button("Mettre à jour la clé"):
            try:
                st.session_state.openai_client = OpenAI(api_key=key)
                st.success("✅ Clé mise à jour")
            except Exception as e:
                st.error(f"Erreur : {e}")

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

            # Deep Crawl
            st.info("Deep Crawl en cours...")
            deep_links = []
            for item in all_results[:15]:
                if item.get("url"):
                    deep_links.extend(deep_crawl(item["url"]))
            all_results.extend([{"source": "Deep Crawl", "url": link} for link in deep_links])

            st.success(f"✅ {len(all_results)} résultats collectés")

            for i, res in enumerate(all_results[:50], 1):
                st.markdown(f"**{i}.** [{res.get('source')}] {res.get('title', res.get('url',''))[:130]}")
                if res.get("url"):
                    st.markdown(f"→ [{res['url']}]({res['url']})")
                st.divider()

            if use_ai and st.session_state.openai_client:
                with st.spinner("🤖 Analyse IA en cours..."):
                    ai_text = ai_analyze(all_results, region, keywords)
                    if ai_text:
                        st.subheader("🤖 Meilleurs lieux selon l'IA")
                        st.markdown(ai_text)

if __name__ == "__main__":
    main()
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        links = [a.get('href') for a in soup.find_all('a', href=True)]
        return [link for link in links if link and link.startswith('http') and 
                any(x in link for x in ['report', 'thread', 'lieu', 'urbex', 'carte-urbex'])][:15]
    except:
        return []


def search_concrete_places(query):
    results = []
    searches = [
        f"{query} usine abandonnÃ©e",
        f"{query} friche industrielle",
        f"{query} hÃ´pital abandonnÃ©",
        f"{query} base militaire abandonnÃ©e",
        f"{query} chÃ¢teau abandonnÃ©",
        f"{query} site urbex",
    ]
    for s in searches:
        results.append({"source": "Google", "title": s, "url": f"https://www.google.com/search?q={quote(s)}"})
    return results


def scrape_reddit(query):
    results = []
    try:
        r = requests.get(f"https://www.reddit.com/search.json?q={quote(query + ' urbex OR abandonnÃ© OR friche')}&limit=20", 
                        headers=HEADERS, timeout=12)
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
        r = requests.get(f"https://www.urbexpassion.com/recherche?query={quote(query)}", headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.find_all('a', href=True):
            if '/report/' in a['href'] or '/lieu/' in a['href']:
                url = "https://www.urbexpassion.com" + a['href'] if not a['href'].startswith('http') else a['href']
                results.append({"source": "UrbexPassion", "title": a.get_text()[:100], "url": url})
    except:
        pass
    return results


def scrape_28dayslater(query):
    results = []
    try:
        r = requests.get(f"https://www.28dayslater.co.uk/search/?q={quote(query)}", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, 'lxml')
        for a in soup.find_all('a', href=True):
            if '/threads/' in a['href']:
                url = "https://www.28dayslater.co.uk" + a['href'] if not a['href'].startswith('http') else a['href']
                results.append({"source": "28dayslater", "title": a.get_text()[:80], "url": url})
    except:
        pass
    return results


def main():
    st.title("ðŸŒ† URBEX OSINT MAX v8.2")
    st.caption("**Scraping AmÃ©liorÃ© + IA OptimisÃ©e**")

    with st.sidebar:
        st.header("Configuration")
        key = st.text_input("OpenAI API Key", type="password", value=DEFAULT_API_KEY)
        if st.button("Mettre Ã  jour la clÃ©"):
            try:
                st.session_state.openai_client = OpenAI(api_key=key)
                st.success("âœ… ClÃ© mise Ã  jour")
            except Exception as e:
                st.error(f"Erreur : {e}")

    col1, col2 = st.columns([3, 1])
    with col1:
        region = st.text_input("ðŸ“ RÃ©gion / Ville", "Ardennes")
        keywords = st.text_input("ðŸšï¸ Type de lieu / mots-clÃ©s", "usine sidÃ©rurgique")
    with col2:
        use_ai = st.checkbox("Activer Analyse IA", value=True)

    if st.button("ðŸš€ LANCER LA RECHERCHE MAX", type="primary", use_container_width=True):
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

            # Deep Crawl
            st.info("Deep Crawl en cours...")
            deep_links = []
            for item in all_results[:15]:
                if item.get("url"):
                    deep_links.extend(deep_crawl(item["url"]))
            all_results.extend([{"source": "Deep Crawl", "url": link} for link in deep_links])

            st.success(f"âœ… {len(all_results)} rÃ©sultats collectÃ©s")

            for i, res in enumerate(all_results[:50], 1):
                st.markdown(f"**{i}.** [{res.get('source')}] {res.get('title', res.get('url',''))[:130]}")
                if res.get("url"):
                    st.markdown(f"â†’ [{res['url']}]({res['url']})")
                st.divider()

            if use_ai and st.session_state.openai_client:
                with st.spinner("ðŸ¤– Analyse IA en cours..."):
                    ai_text = ai_analyze(all_results, region, keywords)
                    if ai_text:
                        st.subheader("ðŸ¤– Meilleurs lieux selon l'IA")
                        st.markdown(ai_text)

if __name__ == "__main__":
    main()    "flickr": "https://www.flickr.com/search/?text=",
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
