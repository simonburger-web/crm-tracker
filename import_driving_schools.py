import os
import sys
import time
import django
import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crmtracker.settings')
django.setup()

from crm.models import Contact, Note

BASE_URL = "https://drivingschoolfinder.co.za"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

def get_school_urls_from_sitemap():
    print("Fetching sitemap...")
    resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = []
    for url_el in root.findall('sm:url', ns):
        loc = url_el.find('sm:loc', ns)
        if loc is not None and '/school/' in loc.text:
            urls.append(loc.text.strip())
    print(f"Found {len(urls)} school URLs in sitemap.")
    return urls

def parse_school_page(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ERROR fetching {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'lxml')

    # Name: h1
    name_el = soup.find('h1')
    name = name_el.get_text(strip=True) if name_el else None
    if not name:
        return None

    def find_text(label):
        """Find text next to an icon/label on the page."""
        for el in soup.find_all(string=lambda t: t and label.lower() in t.lower()):
            parent = el.parent
            if parent:
                text = parent.get_text(strip=True)
                if text and text != label:
                    return text
        return None

    # Try to extract structured data from JSON-LD first
    phone = email = website = address = city = None

    import json
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0]
            if data.get('@type') in ('LocalBusiness', 'DrivingSchool', 'EducationalOrganization', 'Organization'):
                name = data.get('name', name)
                phone = data.get('telephone', phone)
                email = data.get('email', email)
                raw_url = data.get('url', '')
                if raw_url and 'drivingschoolfinder.co.za' not in raw_url:
                    website = raw_url
                addr = data.get('address', {})
                if isinstance(addr, dict):
                    parts = [
                        addr.get('streetAddress', ''),
                        addr.get('addressLocality', ''),
                        addr.get('addressRegion', ''),
                        addr.get('postalCode', ''),
                    ]
                    address = ', '.join(p for p in parts if p)
                    city = addr.get('addressLocality', '')
        except Exception:
            pass

    # Fallback: scrape visible contact fields from the page
    if not phone:
        for el in soup.select('a[href^="tel:"]'):
            phone = el.get_text(strip=True) or el['href'].replace('tel:', '')
            break

    if not email:
        for el in soup.select('a[href^="mailto:"]'):
            email = el.get_text(strip=True) or el['href'].replace('mailto:', '')
            break

    if not website:
        for el in soup.select('a[href^="http"]'):
            href = el.get('href', '')
            if href and BASE_URL not in href and 'google' not in href and 'facebook' not in href:
                website = href
                break

    if not address:
        # Look for address-like text blocks
        for el in soup.select('.address, [itemprop="address"], [class*="address"]'):
            address = el.get_text(strip=True)
            break

    if not city:
        # Extract from URL slug: /school/name-city
        slug = url.rstrip('/').split('/')[-1]
        parts = slug.split('-')
        city = parts[-1].title() if parts else ''

    return {
        'name': name,
        'phone': phone or '',
        'email': email or '',
        'website': website or '',
        'address': address or '',
        'city': city or '',
        'url': url,
    }

def import_schools(urls, dry_run=False):
    created_count = 0
    skipped_count = 0
    error_count = 0

    for i, url in enumerate(urls, 1):
        slug = url.rstrip('/').split('/')[-1]
        print(f"[{i}/{len(urls)}] {slug}", end=' ... ', flush=True)

        data = parse_school_page(url)
        if not data:
            print("SKIP (no data)")
            error_count += 1
            time.sleep(0.3)
            continue

        if dry_run:
            print(f"DRY RUN: {data['name']} | {data['city']} | {data['phone']}")
            continue

        contact, created = Contact.objects.get_or_create(
            name=data['name'],
            defaults={
                'company': 'Driving School',
                'phone': data['phone'],
                'email': data['email'],
                'status': 'lead',
                'region': 'sa',
            }
        )

        if created:
            note_parts = []
            if data['address']:
                note_parts.append(f"Address: {data['address']}")
            if data['city']:
                note_parts.append(f"City: {data['city']}")
            if data['website']:
                note_parts.append(f"Website: {data['website']}")
            note_parts.append("Category: Driving School")
            note_parts.append(f"Source: {data['url']}")

            Note.objects.create(
                contact=contact,
                body='\n'.join(note_parts)
            )
            print(f"CREATED — {data['name']} ({data['city']})")
            created_count += 1
        else:
            print(f"EXISTS — {data['name']}")
            skipped_count += 1

        # Polite crawl delay
        time.sleep(0.4)

    print(f"\nDone. Created: {created_count}, Skipped (existing): {skipped_count}, Errors: {error_count}")

if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    urls = get_school_urls_from_sitemap()
    if not urls:
        print("No school URLs found. Exiting.")
        sys.exit(1)
    import_schools(urls, dry_run=dry_run)
