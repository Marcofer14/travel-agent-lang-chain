import { X, Car, FileDown, Moon, MapPin, Sparkles } from "lucide-react"

const euros = (n) => new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0)
const corta = (s) => (s ? new Date(s + "T12:00:00").toLocaleDateString("es-ES", { day: "numeric", month: "short" }) : "")
const NOMBRE = { barcelona: "Barcelona", madrid: "Madrid", mallorca: "Mallorca" }
const EMOJI = { barcelona: "🏛️", madrid: "🎨", mallorca: "🏖️" }

const accion = (name, payload) => callAction({ name, payload })

function Actividad({ a }) {
  const reservada = a.estado === "reservada"
  const auto = a.categoria === "alquiler_auto"
  return (
    <div className={`it-act ${reservada ? "it-act-ok" : ""}`}>
      <div className="it-act-fila">
        <span className="it-act-nombre">{auto ? <Car size={13} /> : null} {a.nombre}</span>
        <button className="it-x" title="Quitar" onClick={() => accion("it_quitar", { id: a.id })}><X size={13} /></button>
      </div>
      <div className="it-act-fila">
        <input className="it-input" type="date" defaultValue={a.fecha || ""} title={auto ? "Retiro" : "Fecha"}
          onChange={(e) => accion("it_editar", { id: a.id, campo: "fecha", valor: e.target.value })} />
        <input className="it-input it-hora" type="time" defaultValue={a.hora || ""} title="Hora"
          onChange={(e) => accion("it_editar", { id: a.id, campo: "hora", valor: e.target.value })} />
        <button className={`it-estado ${reservada ? "it-estado-ok" : ""}`}
          title="Cambiar entre tentativa y reservada"
          onClick={() => accion("it_editar", { id: a.id, campo: "estado", valor: reservada ? "tentativa" : "reservada" })}>
          {reservada ? "reservada" : "tentativa"}
        </button>
      </div>
      {auto && (
        <div className="it-act-fila">
          <span className="it-mini">devolución</span>
          <input className="it-input" type="date" defaultValue={a.fecha_devolucion || ""}
            onChange={(e) => accion("it_editar", { id: a.id, campo: "fecha_devolucion", valor: e.target.value })} />
        </div>
      )}
      {a.codigo && <div className="it-mini">código {a.codigo} · simulado</div>}
    </div>
  )
}

export default function Itinerario() {
  const hosp = props.hospedajes || []
  const acts = props.actividades || []
  const destinos = [...new Set([...hosp.map((h) => h.destino), ...acts.map((a) => a.destino)])]
  const vacio = destinos.length === 0
  return (
    <div className="it">
      <div className="it-cabecera">
        <div className="it-manuscrito">tu ruta</div>
        <div className="it-titulo">{vacio ? "Todavía en blanco" : destinos.map((d) => NOMBRE[d] || d).join(" · ")}</div>
        {!vacio && (
          <div className="it-kpis">
            <span><b>{euros(props.total)}</b> alojamiento</span>
            <span><b>{props.reservadas}</b> reservadas</span>
            <span><b>{props.tentativas}</b> tentativas</span>
          </div>
        )}
        {props.perfil && <div className="it-perfil"><Sparkles size={12} /> {props.perfil}</div>}
      </div>

      {vacio && (
        <div className="it-vacio">
          Acá se va armando tu viaje: alojamientos, actividades y auto. Podés cambiar fechas, horarios y estados
          directamente, sin escribir.
        </div>
      )}

      {destinos.map((d) => {
        const h = hosp.find((x) => x.destino === d)
        const lista = acts.filter((a) => a.destino === d)
        return (
          <div key={d} className="it-destino">
            <div className="it-destino-titulo">{EMOJI[d] || "📍"} {NOMBRE[d] || d}</div>
            {h ? (
              <div className="it-hosp">
                <img src={`${h.picture_url}?im_w=240`} onError={(e) => { e.currentTarget.style.visibility = "hidden" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="it-act-nombre">{h.name}</div>
                  <div className="it-mini"><Moon size={11} /> {corta(h.check_in)} → {corta(h.check_out)} · {h.noches} noches</div>
                  <div className="it-mini"><MapPin size={11} /> {h.barrio} · <b>{euros(h.total)}</b></div>
                </div>
                <button className="it-x" title="Quitar alojamiento" onClick={() => accion("it_quitar_hospedaje", { destino: d })}><X size={13} /></button>
              </div>
            ) : (
              <div className="it-mini it-pendiente">sin alojamiento elegido</div>
            )}
            {lista.map((a) => <Actividad key={a.id} a={a} />)}
          </div>
        )
      })}

      {!vacio && (
        <button className="it-pdf" onClick={() => accion("pdf", {})}>
          <FileDown size={16} /> Descargar itinerario en PDF
        </button>
      )}
    </div>
  )
}
