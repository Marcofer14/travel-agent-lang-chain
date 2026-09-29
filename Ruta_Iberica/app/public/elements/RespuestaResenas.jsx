import { MessageSquareQuote, Search } from "lucide-react"

const COLORES = { "positivo": "#6E7D4F", "negativo": "#B85C38", "mixto": "#D9A441", "sin información": "#6B7280" }
const ICONOS = { "positivo": "👍", "negativo": "👎", "mixto": "⚖️", "sin información": "❔" }

export default function RespuestaResenas() {
  const color = COLORES[props.veredicto] || "#6B7280"
  return (
    <div className="ri-qa" style={{ borderLeftColor: color }}>
      <div className="ri-qa-cabecera">
        <span className="ri-qa-veredicto" style={{ background: color }}>{ICONOS[props.veredicto] || ""} {props.veredicto.toUpperCase()}</span>
        <span className="ri-sub"><Search size={12} /> “{props.pregunta}” · {props.nombre}</span>
      </div>
      <p className="ri-resumen">{props.respuesta}</p>
      {(props.evidencia || []).map((c, i) => (
        <div key={i} className="ri-cita"><MessageSquareQuote size={13} /> “{c.texto}” <small>— reseña del {c.fecha}</small></div>
      ))}
      <div className="ri-sub">
        {props.n_relevantes} de {props.n_total} reseñas mencionan el tema · búsqueda multilingüe:{" "}
        {(props.palabras || []).slice(0, 8).join(", ")}
      </div>
    </div>
  )
}
