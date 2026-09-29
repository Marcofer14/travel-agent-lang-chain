"""Descarga los datos de Inside Airbnb (https://insideairbnb.com/get-the-data/) para los tres destinos."""
import urllib.request

from _rutas import RAW

BASE = "https://data.insideairbnb.com/spain"
CIUDADES = {
    "barcelona": "catalonia/barcelona/2026-06-24",
    "madrid": "comunidad-de-madrid/madrid/2026-06-20",
    "mallorca": "islas-baleares/mallorca/2026-06-23",
}
ARCHIVOS = ["listings", "calendar", "reviews"]


def descargar(forzar: bool = False) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for ciudad, ruta in CIUDADES.items():
        for archivo in ARCHIVOS:
            destino = RAW / f"{ciudad}_{archivo}.csv.gz"
            if destino.exists() and not forzar:
                continue
            url = f"{BASE}/{ruta}/data/{archivo}.csv.gz"
            print(f"Descargando {url}")
            urllib.request.urlretrieve(url, destino)
    print("Listo:", sorted(p.name for p in RAW.glob("*.csv.gz")))


if __name__ == "__main__":
    descargar()
