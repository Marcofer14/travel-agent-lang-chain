import { MapPin, Moon, ExternalLink, Car } from "lucide-react"

const euros = (n) => new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n)
const fecha = (s) => new Date(s + "T12:00:00").toLocaleDateString("es-ES", { day: "numeric", month: "short" })
const EMOJI = { barcelona: "🏛️", madrid: "🎨", mallorca: "🏖️" }
const titulo = (d) => d.charAt(0).toUpperCase() + d.slice(1)

function Actividad({ a }) {
  const cuando = a.fecha ? `${fecha(a.fecha)}${a.hora ? " " + a.hora : ""}` : "sin fecha"
  return (
    <div className="ri-plan-actividad">
      <span className={`ri-estado ${a.estado === "reservada" ? "ri-estado-reservada" : ""}`}>
        {a.estado === "reservada" ? "RESERVADA" : "TENTATIVA"}
      </span>
      <span>{a.categoria === "alquiler_auto" ? <Car size={12} /> : null} <b>{a.nombre}</b> · {cuando}</span>
      {a.codigo && <span className="ri-sub">{a.codigo}</span>}
    </div>
  )
}

export default function PlanViaje() {
  const tramos = props.tramos || []
  const actividades = props.actividades || []
  const noches = tramos.reduce((a, t) => a + t.noches, 0)
  const destinos = [...new Set([...tramos.map((t) => t.destino), ...actividades.map((a) => a.destino)])]
  return (
    <div className="ri-plan">
      <div className="ri-plan-cabecera">
        <div>
          <small>TU RUTA</small>
          <h3>{destinos.map((d) => `${EMOJI[d] || "📍"} ${titulo(d)}`).join("  →  ")}</h3>
        </div>
        <div style={{ textAlign: "right" }}>
          <small>{noches} noches · {actividades.length} actividades</small>
          <h3>{euros(props.total || 0)}</h3>
        </div>
      </div>
      <div className="ri-plan-cuerpo">
        {destinos.map((d, i) => {
          const t = tramos.find((x) => x.destino === d)
          const acts = actividades.filter((a) => a.destino === d)
          return (
            <div key={d} style={{ display: "flex", flexDirection: "column", gap: ".35rem" }}>
              <div className="ri-tramo">
                <div className="ri-num">{i + 1}</div>
                {t ? (
                  <>
                    <img src={`${t.picture_url}?im_w=320`} onError={(e) => { e.currentTarget.style.visibility = "hidden" }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="ri-nombre">{t.name}</div>
                      <div className="ri-datos">
                        <span><MapPin size={12} /> {t.barrio}, {titulo(t.destino)}</span>
                        <span><Moon size={12} /> {fecha(t.check_in)} → {fecha(t.check_out)} ({t.noches} noches)</span>
                        <span>Puntaje {t.puntaje}/10</span>
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <b>{euros(t.total)}</b>
                      <a href={t.listing_url} target="_blank" rel="noreferrer" className="ri-reservar">
                        Ver en Airbnb <ExternalLink size={12} />
                      </a>
                    </div>
                  </>
                ) : (
                  <div className="ri-sub">{titulo(d)} · todavía sin alojamiento elegido</div>
                )}
              </div>
              {acts.map((a) => <Actividad key={a.id} a={a} />)}
            </div>
          )
        })}
      </div>
    </div>
  )
}
