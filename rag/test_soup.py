import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

url = "https://react.dev"
base_url = "https://react.dev"
res = requests.get(url)
html_content = res.text

valid_links_to_process = []
soup = BeautifulSoup(html_content, "html.parser")
parsed_base = urlparse(base_url)
base_domain = parsed_base.netloc
base_path = parsed_base.path if parsed_base.path else "/"

print(f"Base Domain: {base_domain}, Base Path: {base_path}")

for a_tag in soup.find_all("a", href=True):
    href = a_tag["href"]
    absolute_link = urljoin(url, href)
    absolute_link = absolute_link.split("#")[0]
    absolute_link = absolute_link.rstrip("/")
    
    parsed_link = urlparse(absolute_link)
    link_domain = parsed_link.netloc
    link_path = parsed_link.path
    
    if link_domain == base_domain and absolute_link.startswith("http"):
        if link_path.startswith(base_path):
            if absolute_link not in valid_links_to_process and absolute_link != url:
                valid_links_to_process.append(absolute_link)

print("Found valid links:", len(valid_links_to_process))
if len(valid_links_to_process) > 0:
    print("Sample:", valid_links_to_process[:5])
