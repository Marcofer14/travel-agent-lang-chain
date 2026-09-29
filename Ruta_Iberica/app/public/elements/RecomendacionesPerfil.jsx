import { Sunrise, Sun, Moon, Sparkles, CalendarPlus, Lightbulb, Home } from "lucide-react"

const NOMBRE_DESTINO = { barcelona: "Barcelona", madrid: "Madrid", mallorca: "Mallorca" }
const MOMENTO = {
  "mañana": <Sunrise size={13} />, "tarde": <Sun size={13} />, "noche": <Moon size={13} />, "cualquier momento": <Sparkles size={13} />,
}

export default function RecomendacionesPerfil() {
  const destino = NOMBRE_DESTINO[props.destino] || props.destino
  return (
    <div className="ri-guia">
      <div className="ri-guia-cabecera">
        <small>{props.perfil} · {destino}</small>
        <h3>{props.titular}</h3>
        {(props.barrios_sugeridos || []).length > 0 && (
          <div className="ri-guia-barrios"><Home size={13} /> Dónde alojarte: {props.barrios_sugeridos.join(" · ")}</div>
        )}
      </div>
      <div className="ri-guia-cuerpo">
        {(props.imperdibles || []).map((i) => (
          <div key={i.nombre} className="ri-imperdible">
            <div className="ri-imperdible-momento" title={i.momento}>{MOMENTO[i.momento] || <Sparkles size={13} />}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div><b>{i.nombre}</b> <span className="ri-sub" style={{ display: "inline" }}>{i.tipo || ""}</span></div>
              <div className="ri-sub" style={{ display: "block" }}>{i.por_que}</div>
            </div>
            <button className="ri-chip-btn" onClick={() => sendUserMessage(`Agregá "${i.nombre}" en ${destino} a mi itinerario como tentativa.`)}>
              <CalendarPlus size={13} />
            </button>
          </div>
        ))}
        {props.plan_dia_tipo && <div className="ri-cita"><Sun size={13} /> <span><b>Un día ideal:</b> {props.plan_dia_tipo}</span></div>}
        {(props.consejos || []).map((c, n) => (
          <div key={n} className="ri-sub" style={{ display: "flex" }}><Lightbulb size={12} /> {c}</div>
        ))}
      </div>
    </div>
  )
}
