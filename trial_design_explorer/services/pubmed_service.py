"""
PubMed / PubMed Central evidence service.

Uses NCBI E-utilities (free, no API key required for low-volume access).
Searches PubMed for peer-reviewed evidence relevant to a trial's condition,
design choices, or endpoints, and returns structured, auditable citations.

Rate limit: NCBI allows up to 3 requests/second without an API key.
All requests include a user-agent identifying this tool.
"""

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

_HEADERS = {
    "User-Agent": "TrialDesignExplorer/1.0 (clinical-trial-planning-tool; contact: opensource)",
    "Accept": "application/xml",
}
_RATE_LIMIT_SLEEP = 0.4  # seconds between requests


@dataclass
class PubMedArticle:
    pmid: str
    title: str
    abstract: str
    authors: str
    journal: str
    year: str
    doi: str
    url: str
    query_used: str
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence_type: str = "PubMed/MEDLINE"

    def to_dict(self) -> dict:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "journal": self.journal,
            "year": self.year,
            "doi": self.doi,
            "url": self.url,
            "query_used": self.query_used,
            "retrieved_at": self.retrieved_at,
            "evidence_type": self.evidence_type,
        }

    def short_citation(self) -> str:
        """APA-style short citation for display."""
        author_part = self.authors.split(",")[0] if self.authors else "Unknown"
        return f"{author_part} et al. ({self.year}). {self.title}. {self.journal}. PMID:{self.pmid}"


def _get_xml(url: str, params: dict) -> Optional[ET.Element]:
    """Fetch XML from NCBI E-utilities with error handling."""
    try:
        time.sleep(_RATE_LIMIT_SLEEP)
        response = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        return ET.fromstring(response.content)
    except Exception:
        return None


def _search_pmids(query: str, max_results: int = 8) -> list[str]:
    """Return PMIDs matching a PubMed query."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "xml",
        "sort": "relevance",
    }
    root = _get_xml(ESEARCH_URL, params)
    if root is None:
        return []
    return [id_elem.text for id_elem in root.findall(".//Id") if id_elem.text]


def _fetch_article_details(pmids: list[str], query: str) -> list[PubMedArticle]:
    """Fetch full article details for a list of PMIDs."""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
    }
    root = _get_xml(EFETCH_URL, params)
    if root is None:
        return []

    articles = []
    for article_elem in root.findall(".//PubmedArticle"):
        try:
            pmid = (article_elem.findtext(".//PMID") or "").strip()
            title = (article_elem.findtext(".//ArticleTitle") or "").strip()
            title = re.sub(r"<[^>]+>", "", title)

            abstract_parts = [
                (text_elem.text or "").strip()
                for text_elem in article_elem.findall(".//AbstractText")
                if text_elem.text
            ]
            abstract = " ".join(abstract_parts)[:600]
            if len(abstract) == 600:
                abstract += "..."

            author_elems = article_elem.findall(".//Author")
            author_names = []
            for author in author_elems[:3]:
                last = author.findtext("LastName") or ""
                initials = author.findtext("Initials") or ""
                if last:
                    author_names.append(f"{last} {initials}".strip())
            authors = ", ".join(author_names)

            journal = (article_elem.findtext(".//Journal/Title") or
                       article_elem.findtext(".//MedlineTA") or "").strip()

            year_elem = (
                article_elem.findtext(".//PubDate/Year") or
                article_elem.findtext(".//PubDate/MedlineDate") or ""
            )
            year = re.search(r"\d{4}", year_elem).group() if re.search(r"\d{4}", year_elem) else ""

            doi = ""
            for id_elem in article_elem.findall(".//ArticleId"):
                if id_elem.get("IdType") == "doi":
                    doi = (id_elem.text or "").strip()
                    break

            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

            if title and pmid:
                articles.append(PubMedArticle(
                    pmid=pmid, title=title, abstract=abstract,
                    authors=authors, journal=journal, year=year,
                    doi=doi, url=url, query_used=query,
                ))
        except Exception:
            continue

    return articles


def _build_query(condition: str, design_context: Optional[str] = None,
                 endpoint_focus: Optional[str] = None) -> str:
    """Build a focused PubMed query for clinical trial evidence."""
    parts = [f'"{condition}"[MeSH Terms] OR "{condition}"[Title/Abstract]']
    parts.append('("clinical trial"[Publication Type] OR "randomized controlled trial"[Publication Type] '
                 'OR "systematic review"[Publication Type] OR "meta-analysis"[Publication Type])')
    if design_context:
        parts.append(f'("{design_context}"[Title/Abstract])')
    if endpoint_focus and endpoint_focus not in ("Unspecified", "Other"):
        ep_map = {
            "Efficacy": "efficacy OR treatment outcome",
            "Safety": "safety OR adverse events OR tolerability",
            "Patient Reported": "quality of life OR patient reported outcome",
            "Biomarker": "biomarker OR molecular marker",
            "Utilization": "hospital utilization OR resource use",
            "Operational": "trial feasibility OR recruitment",
        }
        if endpoint_focus in ep_map:
            parts.append(f"({ep_map[endpoint_focus]}[Title/Abstract])")
    return " AND ".join(parts)


def search_pubmed_evidence(
    condition: str,
    design_context: Optional[str] = None,
    endpoint_focus: Optional[str] = None,
    max_results: int = 8,
) -> list[PubMedArticle]:
    """
    Search PubMed for peer-reviewed evidence relevant to a trial design.

    Args:
        condition: Clinical condition (e.g. 'Sepsis', 'Heart Failure')
        design_context: Optional design element (e.g. 'randomized double-blind')
        endpoint_focus: Optional endpoint category (e.g. 'Efficacy', 'Safety')
        max_results: Maximum number of articles to return

    Returns:
        List of PubMedArticle objects with full provenance metadata.
    """
    if not condition:
        return []
    query = _build_query(condition, design_context, endpoint_focus)
    pmids = _search_pmids(query, max_results=max_results)
    if not pmids:
        # Fallback to broader query
        fallback_query = f'"{condition}" AND (clinical trial[pt] OR randomized controlled trial[pt])'
        pmids = _search_pmids(fallback_query, max_results=max_results)
        if not pmids:
            return []
        query = fallback_query
    return _fetch_article_details(pmids, query)


def articles_to_evidence_rows(articles: list[PubMedArticle]) -> list[dict]:
    """Convert articles to compact rows for display in tables/reports."""
    rows = []
    for article in articles:
        rows.append({
            "PMID": article.pmid,
            "Title": article.title[:90] + "..." if len(article.title) > 90 else article.title,
            "Authors": article.authors,
            "Journal": article.journal,
            "Year": article.year,
            "Endpoint Focus": _classify_endpoint_from_abstract(article.abstract),
            "URL": article.url,
            "Retrieved": article.retrieved_at[:10],
        })
    return rows


def _classify_endpoint_from_abstract(abstract: str) -> str:
    """Infer endpoint focus from abstract text."""
    text = (abstract or "").lower()
    if any(w in text for w in ["mortality", "survival", "response", "remission", "efficacy"]):
        return "Efficacy"
    if any(w in text for w in ["adverse", "safety", "tolerability", "toxicity"]):
        return "Safety"
    if any(w in text for w in ["quality of life", "pain", "fatigue", "patient reported"]):
        return "Patient Reported"
    if any(w in text for w in ["biomarker", "cytokine", "protein", "gene"]):
        return "Biomarker"
    return "General"
