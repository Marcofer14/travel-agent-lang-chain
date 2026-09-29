// Ruta Ibérica · panel izquierdo con la guía de uso (se inyecta una sola vez sobre la interfaz de Chainlit)
(function () {
  const EJEMPLOS = [
    "Somos 2, Barcelona del 10 al 13 de octubre y Madrid del 13 al 16",
    "¿La recomendada es ruidosa de noche?",
    "Compará la recomendada con la mejor rateada",
    "Soy fan de los museos, ¿qué me recomendás?",
    "Buscame restaurantes de tapas cerca de la Sagrada Familia",
    "Reservá el Museo del Prado el 14 a las 10:00",
    "Reservame un auto en Mallorca del 16 al 20",
    "Generame el PDF del itinerario",
  ];

  const HTML = `
    <div class="gu-cabecera">
      <span class="gu-manuscrito">cómo usarme</span>
      <button class="gu-toggle" title="Mostrar u ocultar la guía">ocultar</button>
    </div>
    <div class="gu-contenido">
      <div class="gu-seccion">
        <h4>En 4 pasos</h4>
        <div class="gu-paso"><span class="gu-num">1</span><span>Contame <b>destinos, fechas y cuántos viajan</b> (el presupuesto es opcional).</span></div>
        <div class="gu-paso"><span class="gu-num">2</span><span>Elegí entre las <b>4 opciones</b> de cada destino con <b>Elegir esta</b>.</span></div>
        <div class="gu-paso"><span class="gu-num">3</span><span>Sumá <b>actividades</b>: reservadas o tentativas, con o sin horario.</span></div>
        <div class="gu-paso"><span class="gu-num">4</span><span>Ajustá todo en <b>Tu itinerario</b> (derecha) y descargá el <b>PDF</b>.</span></div>
      </div>
      <div class="gu-seccion">
        <h4>Probá escribir</h4>
        ${EJEMPLOS.map((e) => `<button class="gu-ejemplo">“${e}”</button>`).join("")}
      </div>
      <div class="gu-seccion">
        <h4>Qué significa cada cosa</h4>
        <div class="gu-glosario">
          <span>🧭</span><span>Recomendada por nuestro modelo (puntaje 1-10)</span>
          <span>⭐</span><span>Mejor rateada por los huéspedes</span>
          <span>💸 💎</span><span>La más barata y la más cara</span>
          <span>👍 👎</span><span>Qué dicen las reseñas sobre lo que preguntaste</span>
          <span>🟢</span><span>Reservada (simulada, con código)</span>
          <span>🟡</span><span>Tentativa: todavía sin confirmar</span>
          <span>⚙️</span><span>Ajustá qué pesa más en el puntaje</span>
        </div>
      </div>
      <div class="gu-pie">Datos: Inside Airbnb (jun 2026) · OpenStreetMap · Open-Meteo. Las reservas son simuladas: confirmalas con cada proveedor.</div>
    </div>`;

  function escribirEnChat(texto) {
    const campo = document.querySelector("#chat-input") || document.querySelector("textarea");
    if (!campo) return;
    if (campo.tagName === "TEXTAREA" || campo.tagName === "INPUT") {
      const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(campo), "value").set;
      setter.call(campo, texto);
    } else {
      campo.textContent = texto;
    }
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.focus();
  }

  function guardar(clave, valor) { try { localStorage.setItem(clave, valor); } catch (e) { /* sin storage */ } }
  function leer(clave) { try { return localStorage.getItem(clave); } catch (e) { return null; } }

  function montar() {
    if (document.getElementById("ri-guia-uso") || !document.getElementById("root")) return;
    const panel = document.createElement("aside");
    panel.id = "ri-guia-uso";
    panel.innerHTML = HTML;
    document.body.appendChild(panel);
    document.body.classList.add("ri-con-guia");

    const boton = panel.querySelector(".gu-toggle");
    const aplicar = (cerrado) => {
      panel.classList.toggle("gu-cerrado", cerrado);
      document.body.classList.toggle("ri-con-guia", !cerrado);
      boton.textContent = cerrado ? "📖 guía" : "ocultar";
      guardar("ri-guia-cerrada", cerrado ? "1" : "0");
    };
    const preferencia = leer("ri-guia-cerrada");
    aplicar(preferencia === null ? window.innerWidth < 1180 : preferencia === "1");
    boton.addEventListener("click", () => aplicar(!panel.classList.contains("gu-cerrado")));
    panel.querySelectorAll(".gu-ejemplo").forEach((b, i) => b.addEventListener("click", () => escribirEnChat(EJEMPLOS[i])));
  }

  const observador = new MutationObserver(montar);
  observador.observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("DOMContentLoaded", montar);
  montar();
})();
