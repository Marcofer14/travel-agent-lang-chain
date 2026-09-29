import { Cpu, Timer, Coins, ArrowDownToLine, ArrowUpFromLine, Calculator } from "lucide-react"

const fmt = (n) => new Intl.NumberFormat("es-ES").format(n)

function Item({ icono, etiqueta, valor }) {
  return (
    <div className="ri-kpi">
      {icono}
      <div>
        <small>{etiqueta}</small>
        <b>{valor}</b>
      </div>
    </div>
  )
}

export default function Metricas() {
  const m = props
  return (
    <div className="ri-opciones">
      <div className="ri-sub">{m.titulo}</div>
      <div className="ri-kpis">
        <Item icono={<ArrowDownToLine size={18} />} etiqueta="Tokens de entrada" valor={fmt(m.tokens_entrada)} />
        <Item icono={<ArrowUpFromLine size={18} />} etiqueta="Tokens de salida" valor={fmt(m.tokens_salida)} />
        <Item icono={<Cpu size={18} />} etiqueta="Tokens totales" valor={fmt(m.tokens_totales)} />
        <Item icono={<Timer size={18} />} etiqueta="Tiempo de LLM" valor={`${m.segundos} s`} />
        <Item icono={<Coins size={18} />} etiqueta="Costo simulado total" valor={`US$ ${m.costo_total_usd.toFixed(4)}`} />
        <Item icono={<Calculator size={18} />} etiqueta="Promedio por consulta" valor={`US$ ${m.costo_promedio_usd.toFixed(5)}`} />
      </div>
      <div className="ri-sub">
        {m.consultas} consulta(s) · {m.llamadas} llamadas al LLM · costo real US$ 0 (free tier de Groq) ·
        con Claude Sonnet 5 costaría US$ {m.costo_si_fuera_claude_sonnet_usd}
      </div>
    </div>
  )
}
