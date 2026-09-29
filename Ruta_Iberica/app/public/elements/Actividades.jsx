import { MapPin, Clock, Globe, CalendarPlus, Ticket, UtensilsCrossed } from "lucide-react"

const NOMBRE_DESTINO = { barcelona: "Barcelona", madrid: "Madrid", mallorca: "Mallorca" }

function horarioCorto(h) {
  if (!h) return null
  return h.length > 60 ? h.slice(0, 57) + "…" : h
}

export default function Actividades() {
  const lugares = props.lugares || []
  const destino = NOMBRE_DESTINO[props.destino] || props.destino
  return (
    <div className="ri-opciones">
      <div className="ri-sub">{lugares.length} lugares reales en {destino} · fuente: OpenStreetMap</div>
      <div className="ri-act-grilla">
        {lugares.map((l) => (
          <div key={l.osm_id || l.nombre} className="ri-act">
            <div className="ri-act-tipo">{l.tipo}</div>
            <div className="ri-nombre">{l.nombre}</div>
            {l.direccion && <div className="ri-sub"><MapPin size={11} /> {l.direccion}</div>}
            {l.dist_km != null && <div className="ri-sub"><MapPin size={11} /> a {l.dist_km} km</div>}
            {l.cocina && <div className="ri-sub"><UtensilsCrossed size={11} /> {l.cocina.replaceAll(";", ", ")}</div>}
            {l.horario && <div className="ri-sub" title={l.horario}><Clock size={11} /> {horarioCorto(l.horario)}</div>}
            <div className="ri-act-botones">
              <button className="ri-chip-btn" onClick={() => sendUserMessage(`Agregá "${l.nombre}" en ${destino} a mi itinerario como tentativa.`)}>
                <CalendarPlus size={13} /> Agregar
              </button>
              <button className="ri-chip-btn ri-chip-btn-fuerte" onClick={() => sendUserMessage(`Quiero reservar "${l.nombre}" en ${destino}.`)}>
                <Ticket size={13} /> Reservar
              </button>
              {(l.web || l.osm_url) && (
                <a className="ri-chip-btn" href={l.web || l.osm_url} target="_blank" rel="noreferrer" title="Sitio web / mapa">
                  <Globe size={13} />
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
