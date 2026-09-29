import { CheckCircle2, Clock3, Car, AlertTriangle } from "lucide-react"

export default function Confirmacion() {
  const i = props.item || {}
  const reservada = i.estado === "reservada"
  const auto = i.categoria === "alquiler_auto"
  const cuando = [i.fecha, i.hora].filter(Boolean).join(" · ") || "sin fecha definida"
  return (
    <div className={`ri-confirma ${reservada ? "ri-confirma-ok" : ""}`}>
      <div className="ri-confirma-icono">{auto ? <Car size={22} /> : reservada ? <CheckCircle2 size={22} /> : <Clock3 size={22} />}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="ri-nombre">{i.nombre}</div>
        <div className="ri-sub">
          {auto ? `Retiro ${cuando} → devolución ${[i.fecha_devolucion, i.hora_devolucion].filter(Boolean).join(" · ")}` : `${i.tipo_texto || ""} · ${cuando}`}
        </div>
        {props.aviso && <div className="ri-sub" style={{ color: "#D48E1F" }}><AlertTriangle size={12} /> {props.aviso}</div>}
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="ri-confirma-estado">{reservada ? "RESERVADA" : "TENTATIVA"}</div>
        {i.codigo && <div className="ri-sub">código {i.codigo} (simulado)</div>}
      </div>
    </div>
  )
}
