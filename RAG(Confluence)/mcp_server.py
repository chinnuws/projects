# mcp_server.py
import os
from fastapi import FastAPI
import requests
from bs4 import BeautifulSoup

app = FastAPI()

CONFLUENCE_URL = os.getenv("CONFLUENCE_BASE_URL")
SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY")
AUTH = (os.getenv("CONFLUENCE_USERNAME"), os.getenv("CONFLUENCE_PASSWORD"))

@app.get("/crawl")
def crawl_confluence():
    url = f"{CONFLUENCE_URL}/spaces/{SPACE_KEY}/overview"
    resp = requests.get(url, auth=AUTH)
    soup = BeautifulSoup(resp.text, 'html.parser')
    pages = []
    for link in soup.select(".pagetitle a"):
        page_url = CONFLUENCE_URL + link['href']
        page_resp = requests.get(page_url, auth=AUTH)
        page_soup = BeautifulSoup(page_resp.text, 'html.parser')
        content = page_soup.find("div", {"id": "main-content"})
        pages.append({
            "title": link.text,
            "url": page_url,
            "content": content.text.strip() if content else ""
        })
    return pages
