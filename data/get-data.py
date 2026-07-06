import requests
import pandas as pd
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

# 🔥 TROQUE AQUI quando descobrir os endpoints reais
API_ENDPOINTS = {
    "voolt3d": "https://3dfilamentprofiles.com/api/filaments?vendor=voolt3d",
    "f3d": "https://3dfilamentprofiles.com/api/filaments?vendor=f3d",
    "gtmax": "https://3dfilamentprofiles.com/api/filaments?vendor=gtmax",
    "elegoo": "https://3dfilamentprofiles.com/api/filaments?vendor=elegoo",
    "sunlu": "https://3dfilamentprofiles.com/api/filaments?vendor=sunlu",
    "creality": "https://3dfilamentprofiles.com/api/filaments?vendor=creality",
    "masterprint": "https://3dfilamentprofiles.com/api/materials?material=pla&query=masterprint",
}


def fetch_json(url):
    r = requests.get(url, headers=HEADERS, timeout=30)

    if r.status_code != 200:
        print(f"❌ Erro {r.status_code} em {url}")
        return None

    try:
        return r.json()
    except Exception:
        print(f"⚠️ Resposta não é JSON: {url}")
        return None


def normalize_filament(item, source):
    """
    Ajusta estrutura independente do formato da API
    """
    return {
        "source": source,
        "name": item.get("name"),
        "brand": item.get("brand"),
        "material": item.get("material"),
        "color": item.get("color"),
        "nozzle_temp_min": item.get("nozzleTempMin"),
        "nozzle_temp_max": item.get("nozzleTempMax"),
        "bed_temp": item.get("bedTemp"),
        "density": item.get("density"),
        "url": item.get("url"),
    }


def scrape_all():
    all_data = []

    for source, url in API_ENDPOINTS.items():
        print(f"\n📦 Buscando: {source}")

        data = fetch_json(url)
        if not data:
            continue

        # pode vir como lista ou dict
        items = data if isinstance(data, list) else data.get("results", [])

        print(f"  → {len(items)} itens")

        for item in items:
            all_data.append(normalize_filament(item, source))

        time.sleep(0.3)

    return all_data


def export_csv(data, filename="filamentos_api.csv"):
    df = pd.DataFrame(data)
    df.to_csv(filename, index=False)
    print(f"\n✅ CSV gerado: {filename}")


if __name__ == "__main__":
    data = scrape_all()
    export_csv(data)
