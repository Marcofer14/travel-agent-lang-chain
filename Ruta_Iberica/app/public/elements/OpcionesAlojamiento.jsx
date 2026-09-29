import { Star, Users, MapPin, ExternalLink, Check, AlertTriangle, BedDouble, Quote, Award, Navigation, Info } from "lucide-react"
import { useState } from "react"

const NOMBRES_PUNTAJE = {
  calidad: "Calidad (rating)",
  resenas_nlp: "Reseñas (IA)",
  precio_calidad: "Precio/calidad",
  ubicacion: "Ubicación",
  ajuste_capacidad: "Ajuste capacidad",
}

const euros = (n) => new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n)

function Anillo({ valor }) {
  const r = 22, c = 2 * Math.PI * r, pct = Math.max(0, Math.min(1, (valor - 1) / 9))
  const color = valor >= 8.5 ? "#6E7D4F" : valor >= 7 ? "#D9A441" : "#B85C38"
  return (
    <div className="ri-anillo" title="Puntaje Ruta Ibérica (1 a 10)">
      <svg viewBox="0 0 56 56">
        <circle cx="28" cy="28" r={r} className="ri-anillo-fondo" strokeWidth="5" fill="none" />
        <circle cx="28" cy="28" r={r} stroke={color} strokeWidth="5" fill="none" strokeLinecap="round"
          strokeDasharray={`${c * pct} ${c}`} transform="rotate(-90 28 28)" />
      </svg>
      <span>{valor?.toFixed(1)}</span>
    </div>
  )
}

function Tarjeta({ t }) {
  const [abierto, setAbierto] = useState(false)
  const foto = t.picture_url ? `${t.picture_url}?im_w=720` : null
  return (
    <div className={`ri-card ri-${t.etiqueta}`}>
      <div className="ri-foto">
        {foto && <img src={foto} alt={t.name} onError={(e) => { e.currentTarget.style.display = "none" }} />}
        <span className="ri-chip" title={t.titulo_etiqueta}>{t.etiqueta_corta || t.titulo_etiqueta}</span>
        {t.host_is_superhost === "t" && <span className="ri-superhost"><Award size={12} /> Superhost</span>}
      </div>

      <div className="ri-cuerpo">
        <div className="ri-fila-titulo">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="ri-nombre">{t.name}</div>
            <div className="ri-sub"><MapPin size={12} /> {t.barrio}</div>
          </div>
          <Anillo valor={t.puntaje} />
        </div>

        <div className="ri-datos">
          <span><Users size={12} /> hasta {t.accommodates}</span>
          {t.bedrooms ? <span><BedDouble size={12} /> {t.bedrooms} dorm.</span> : null}
          <span><Star size={12} /> {t.rating_airbnb_10}/10 · {t.number_of_reviews} reseñas</span>
        </div>

        {(t.cercanias || []).length > 0 && (
          <div className="ri-cerca">
            {t.cercanias.map((c) => (
              <span key={c.lugar} title={`${c.lugar}: ${c.texto}`}><Navigation size={11} /><em>{c.lugar}</em><b>{c.texto}</b></span>
            ))}
          </div>
        )}

        <div className="ri-precio">
          <div><b>{euros(t.price)}</b><small> / noche</small></div>
          <small>{t.noches} noches · <b>{euros(t.total)}</b></small>
        </div>

        {t.resumen && <p className="ri-resumen">{t.resumen}</p>}
        {!t.tiene_nlp && <p className="ri-sub">Análisis de reseñas pendiente: puntaje calculado con los ratings de Airbnb.</p>}

        {t.alerta && <div className="ri-alerta"><AlertTriangle size={14} /> {t.alerta}</div>}

        <button className="ri-link" onClick={() => setAbierto(!abierto)}>
          {abierto ? "Ocultar detalle" : "Pros, contras y por qué este puntaje"}
        </button>

        {abierto && (
          <div className="ri-detalle">
            {(t.pros || []).map((p, i) => <div key={"p" + i}>✅ {p}</div>)}
            {(t.contras || []).map((p, i) => <div key={"c" + i}>⚠️ {p}</div>)}
            {t.cita_textual && <div className="ri-cita"><Quote size={12} /> “{t.cita_textual}”</div>}
            {Object.entries(t.detalle_puntaje || {}).map(([k, v]) => (
              <div key={k} className="ri-barra">
                <span>{NOMBRES_PUNTAJE[k] || k}</span>
                <div><i style={{ width: `${v * 10}%` }} /></div>
                <b>{v}</b>
              </div>
            ))}
            {(t.ideal_para || []).length > 0 && (
              <div className="ri-tags">{t.ideal_para.map((p) => <span key={p}>{p}</span>)}</div>
            )}
          </div>
        )}

        <div className="ri-botones">
          <button className="ri-btn-primario"
            onClick={() => sendUserMessage(`Elijo "${t.name}" (id ${t.id}) para ${t.destino}.`)}>
            <Check size={16} /> Elegir esta
          </button>
          <a className="ri-btn-secundario" href={t.listing_url} target="_blank" rel="noreferrer" title="Ver en Airbnb">
            <ExternalLink size={16} />
          </a>
        </div>
      </div>
    </div>
  )
}

export default function OpcionesAlojamiento() {
  const tarjetas = props.tarjetas || []
  return (
    <div className="ri-opciones">
      <div className="ri-sub">
        {props.candidatos} alojamientos disponibles evaluados para {props.huespedes} huésped{props.huespedes > 1 ? "es" : ""}
        {props.cerca_de ? ` · cerca de ${props.cerca_de}` : ""}
      </div>
      <div className="ri-grilla">
        {tarjetas.map((t) => <Tarjeta key={t.id} t={t} />)}
      </div>
      <div className="ri-aviso">
        <Info size={13} /> Disponibilidad y precios según el relevamiento de Inside Airbnb del {props.relevamiento}.
        Confirmá en Airbnb antes de reservar.
      </div>
    </div>
  )
}
