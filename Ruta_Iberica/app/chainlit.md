# 🧭 Ruta Ibérica

**Asesor de viajes con IA para Barcelona, Madrid y Mallorca.**

## ¿Qué hace?
1. Interpreta tu pedido de viaje (destinos, fechas, huéspedes y presupuesto).
2. Busca alojamientos **disponibles en todas tus noches** y con **capacidad para todo el grupo**.
3. Te presenta **4 opciones por destino**:
   - 🧭 **Recomendada por nuestro modelo**, la de mayor puntaje Ruta Ibérica
   - ⭐ **Mejor rateada**, ajustada por cantidad de reseñas
   - 💸 **Más barata**
   - 💎 **Más cara**
4. Guarda tus elecciones y arma el resumen de la ruta con el costo total.
5. Te recomienda qué hacer según tu **perfil de viajero** (playero, museos, foodie, cultural, caminador, familiar,
   noctámbulo o generalista) con lugares reales de OpenStreetMap.
6. Agenda actividades como **reservadas (simuladas)** o **tentativas**, con o sin día y hora, y reserva **auto**.
7. Al final te da el **itinerario completo en PDF**.

## ¿Cómo se calcula el puntaje (1 a 10)?
| Componente | Peso |
|---|---|
| Calidad percibida (rating de Airbnb con ajuste bayesiano) | 30 % |
| Análisis de reseñas con IA (limpieza, tranquilidad, anfitrión, fidelidad al anuncio, sentimiento) | 30 % |
| Relación precio/calidad frente a la mediana de su barrio | 20 % |
| Ubicación | 10 % |
| Ajuste de capacidad al tamaño del grupo | 10 % |

## Datos
- **Fuente:** [Inside Airbnb](https://insideairbnb.com/get-the-data/), relevamientos de junio de 2026 (Barcelona 24/06, Madrid 20/06, Mallorca 23/06).
- Catálogo curado de **1.500 alojamientos activos** (500 por destino) con reseñas recientes.
- **Actividades:** [OpenStreetMap](https://www.openstreetmap.org/) (© colaboradores de OSM, ODbL) y popularidad de Wikidata.
- **Clima:** [Open-Meteo](https://open-meteo.com/).
- Las reservas de actividades y autos son **simuladas**: confirmalas con cada proveedor.
- Los precios son en euros por noche. La disponibilidad corresponde al último relevamiento y **puede haber cambiado**: confirmá siempre en Airbnb.

## Tecnología
LangChain (LCEL, Pydantic, RunnableParallel, batch, agente con tools y memoria) · Groq (modelos gpt-oss, free tier) · Chainlit.
