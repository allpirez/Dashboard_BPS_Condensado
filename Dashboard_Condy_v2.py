import pandas as pd
import streamlit as st
import gspread
import yfinance as yf
from datetime import date, datetime, timedelta
from google.oauth2.service_account import Credentials
from streamlit_echarts import st_echarts, JsCode

# =========================================================
# CONFIGURACIÓN
# =========================================================
st.set_page_config(
    page_title="Condensados BPS · Dashboard Ejecutivo",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

NOMBRE_PESTANA = "DASHBOARD_CONDY"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
COLS_NUM = [
    "Volumen_Compra_BLS", "Subtotal_Compra_MXN", "Volumen_Venta_BLS",
    "Subtotal_Venta_MXN", "TC", "Subtotal_Transporte_MXN",
    "Retencion_Transporte_MXN", "Comision_MXN",
]
INVALIDOS = {"", "N/A", "#N/A", "NAN", "NONE", "NULL", "NAT", "0"}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# Paleta con significado fijo: cada métrica conserva SIEMPRE el mismo color en todo el tablero.
C = dict(
    ventas="#2563eb", utilidad="#16a34a", volumen="#f59e0b", margen="#7c3aed",
    costo="#ef4444", neutro="#64748b", grid="#eef2f7",
    up="#16a34a", down="#dc2626", flat="#94a3b8",
)
PALETA = ["#2563eb", "#7c3aed", "#0ea5e9", "#f59e0b", "#14b8a6", "#ec4899", "#84cc16", "#94a3b8"]

CSS = """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem;}
.kpi-label {font-size: 11.5px; font-weight: 600; letter-spacing: .05em;
            text-transform: uppercase; color: #64748b;}
.kpi-value {font-size: 28px; font-weight: 700; line-height: 1.25; margin: 2px 0;}
.kpi-delta {font-size: 12.5px; font-weight: 600; margin-bottom: 2px;}
.insight {border-left: 3px solid #2563eb; padding: 8px 12px; font-size: 13.5px;
          background: rgba(37,99,235,.06); border-radius: 4px; height: 100%;}
.insight b {display:block; font-size: 11.5px; letter-spacing:.04em;
            text-transform: uppercase; color:#64748b; margin-bottom:2px;}
</style>
"""

# =========================================================
# FORMATOS (JS para ECharts y Python para tarjetas)
# =========================================================
def js(code):
    return JsCode(code).js_code

JS_MONEY = js("function(v){var a=Math.abs(v),s=v<0?'-':'';if(a>=1e6)return s+'$'+(a/1e6).toFixed(1)+'M';if(a>=1e3)return s+'$'+(a/1e3).toFixed(0)+'K';return s+'$'+a.toFixed(0);}")
JS_NUM = js("function(v){var a=Math.abs(v),s=v<0?'-':'';if(a>=1e6)return s+(a/1e6).toFixed(1)+'M';if(a>=1e3)return s+(a/1e3).toFixed(0)+'K';return s+a.toFixed(0);}")
JS_MONEY_FULL = js("function(v){return v==null?'–':'$'+Math.round(v).toLocaleString('en-US')+' MXN';}")
JS_BBL_FULL = js("function(v){return v==null?'–':Math.round(v).toLocaleString('en-US')+' BBL';}")
JS_PCT = js("function(v){return v==null?'–':v.toFixed(1)+'%';}")
JS_USD = js("function(v){return v==null?'–':'$'+v.toFixed(2)+' USD';}")
JS_WF_LBL = js("function(p){var a=Math.abs(p.value);return a>=1e6?(a/1e6).toFixed(1)+'M':a>=1e3?(a/1e3).toFixed(0)+'K':a;}")
JS_INT = js("function(v){return v==null?'–':Math.round(v).toLocaleString('en-US');}")


def fm(v, dec=1):
    """Formato monetario compacto para tarjetas."""
    a, s = abs(v), "-" if v < 0 else ""
    if a >= 1e6:
        return f"{s}${a / 1e6:,.{dec}f}M"
    if a >= 1e3:
        return f"{s}${a / 1e3:,.0f}K"
    return f"{s}${a:,.0f}"


def mes_label(ym):
    y, m = ym.split("-")
    return f"{MESES[int(m) - 1]}-{y[2:]}"


def L(serie, nd=0):
    """Serie -> lista JSON-safe (NaN -> None para que ECharts deje hueco, no un cero falso)."""
    return [None if pd.isna(v) else round(float(v), nd) for v in serie]


def sd(a, b):
    """División segura para escalares."""
    return float(a) / float(b) if b not in (0, None) and not pd.isna(b) else float("nan")


# =========================================================
# DATOS
# =========================================================
@st.cache_data(ttl=120)
def obtener_datos(nombre_pestana):
    secrets = dict(st.secrets["connections"]["gsheets"])
    if "private_key" in secrets:
        secrets["private_key"] = secrets["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(secrets, scopes=SCOPES)
    client = gspread.authorize(creds)
    ws = client.open_by_url(secrets["spreadsheet"]).worksheet(nombre_pestana)
    return pd.DataFrame(ws.get_all_records()), datetime.now()


@st.cache_data(ttl=3600)
def obtener_wti(fecha_inicio, fecha_fin):
    """OHLC diario del WTI (CL=F) desde Yahoo Finance."""
    try:
        d = yf.download("CL=F", start=fecha_inicio, end=fecha_fin, progress=False)
        if not d.empty:
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            d = d[["Open", "High", "Low", "Close"]].reset_index()
            d["Fecha"] = pd.to_datetime(d["Date"]).dt.tz_localize(None)
            d["AÑO_MES"] = d["Fecha"].dt.to_period("M").astype(str)
            return d.dropna(subset=["Open", "Close", "Low", "High"])
    except Exception:
        pass
    return pd.DataFrame(columns=["Fecha", "Open", "High", "Low", "Close", "AÑO_MES"])


def limpiar_texto(s):
    s = s.astype(str).str.strip()
    return s.where(~s.str.upper().isin(INVALIDOS), "Sin dato")


def preparar(df_raw):
    df = df_raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    if "Fecha" not in df.columns:
        st.error("No se encontró la columna 'Fecha' en la hoja de cálculo.")
        st.stop()

    df["FECHAS"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["FECHAS"])
    df["AÑO_MES"] = df["FECHAS"].dt.to_period("M").astype(str)

    faltantes = [c for c in COLS_NUM if c not in df.columns]
    if faltantes:
        st.warning(f"Columnas no encontradas en la hoja (se asumen en 0): {', '.join(faltantes)}")
        for c in faltantes:
            df[c] = 0.0
    for c in COLS_NUM:
        df[c] = pd.to_numeric(
            df[c].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        ).fillna(0)

    for c in ("Cliente", "Destino"):
        df[c] = limpiar_texto(df[c]) if c in df.columns else "Sin dato"

    df["Utilidad_Bruta"] = df["Subtotal_Venta_MXN"] - df["Subtotal_Compra_MXN"]
    df["Utilidad_Neta"] = df["Utilidad_Bruta"] - df["Subtotal_Transporte_MXN"] - df["Comision_MXN"]

    tc = df["TC"].where(df["TC"] > 0)  # TC=0 -> NaN (no inventa precios en USD)
    df["Venta_USD"] = df["Subtotal_Venta_MXN"] / tc
    df["Compra_USD"] = df["Subtotal_Compra_MXN"] / tc
    return df.sort_values("FECHAS", ascending=False)


def agregar(d, by):
    """Agregación única con todas las métricas derivadas (se reutiliza por mes, cliente y destino)."""
    g = d.groupby(by, as_index=False).agg(
        Ventas=("Subtotal_Venta_MXN", "sum"), Compras=("Subtotal_Compra_MXN", "sum"),
        Flete=("Subtotal_Transporte_MXN", "sum"), Comision=("Comision_MXN", "sum"),
        Utilidad=("Utilidad_Neta", "sum"), Vol_Venta=("Volumen_Venta_BLS", "sum"),
        Vol_Compra=("Volumen_Compra_BLS", "sum"), Pipas=("Subtotal_Venta_MXN", "count"),
    )
    nz = lambda s: s.where(s != 0)
    g["Margen"] = g["Utilidad"] / nz(g["Ventas"]) * 100
    g["Util_BBL"] = g["Utilidad"] / nz(g["Vol_Venta"])
    g["Merma"] = (g["Vol_Compra"] - g["Vol_Venta"]) / nz(g["Vol_Compra"]) * 100
    g["Flete_Pct"] = g["Flete"] / nz(g["Ventas"]) * 100
    g["BBL_Pipa"] = g["Vol_Venta"] / nz(g["Pipas"])
    return g


def precios_usd_mes(d):
    """Precio promedio ponderado por volumen (USD/BBL), solo con filas que tienen TC válido."""
    x = d[d["Venta_USD"].notna() & (d["Volumen_Venta_BLS"] > 0)]
    v = x.groupby("AÑO_MES").agg(vu=("Venta_USD", "sum"), vv=("Volumen_Venta_BLS", "sum"))
    y = d[d["Compra_USD"].notna() & (d["Volumen_Compra_BLS"] > 0)]
    c = y.groupby("AÑO_MES").agg(cu=("Compra_USD", "sum"), cv=("Volumen_Compra_BLS", "sum"))
    o = v.join(c, how="outer")
    o["Venta_USD_BBL"] = o["vu"] / o["vv"]
    o["Compra_USD_BBL"] = o["cu"] / o["cv"]
    return o[["Venta_USD_BBL", "Compra_USD_BBL"]].reset_index().sort_values("AÑO_MES")


def delta(serie, tipo="pct", inverso=False):
    """Variación último mes vs. anterior. inverso=True cuando 'bajar' es bueno (costos, merma)."""
    s = serie.dropna()
    if len(s) < 2:
        return "Sin mes previo", C["flat"]
    act, ant = float(s.iloc[-1]), float(s.iloc[-2])
    if tipo == "pp":
        d, txt = act - ant, f"{act - ant:+.1f} pp"
    else:
        if ant == 0:
            return "— N/A vs mes ant.", C["flat"]
        d = (act - ant) / abs(ant) * 100
        txt = f"{d:+.0f}%"
    if abs(d) < 0.05:
        return "— sin cambio vs mes ant.", C["flat"]
    bueno = (d > 0) != inverso
    return f"{'▲' if d > 0 else '▼'} {txt} vs mes ant.", (C["up"] if bueno else C["down"])


# =========================================================
# COMPONENTES DE UI
# =========================================================
def kpi(col, label, value, dtxt="", dcol=None, key="", ayuda="", sp=None):
    with col, st.container(border=True):
        st.markdown(
            f"<div class='kpi-label' title='{ayuda}'>{label}{' ⓘ' if ayuda else ''}</div>"
            f"<div class='kpi-value'>{value}</div>"
            f"<div class='kpi-delta' style='color:{dcol or C['flat']}'>{dtxt}</div>",
            unsafe_allow_html=True,
        )
        if sp:
            st_echarts(sp, height="52px", key=f"sp_{key}")


def spark(data, labels, color, barra=False):
    if barra:
        s = {"type": "bar", "barWidth": "60%", "itemStyle": {"color": color, "borderRadius": [2, 2, 0, 0]}}
    else:
        s = {"type": "line", "smooth": True, "symbol": "none", "lineStyle": {"color": color, "width": 2},
             "areaStyle": {"color": color, "opacity": 0.15}}
    s["data"] = data
    return {
        "grid": {"top": 4, "bottom": 2, "left": 2, "right": 2},
        "xAxis": {"type": "category", "data": labels, "show": False},
        "yAxis": {"type": "value", "show": False, "scale": True},
        "tooltip": {"trigger": "axis"},
        "series": [s],
    }


def base(**kw):
    o = {
        "color": PALETA,
        "textStyle": {"fontFamily": "inherit"},
        "grid": {"left": 8, "right": 16, "top": 44, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"top": 0, "icon": "roundRect", "itemWidth": 12, "itemHeight": 8,
                   "textStyle": {"color": C["neutro"]}},
    }
    o.update(kw)
    return o


def xax(data, **kw):
    a = {"type": "category", "data": data, "axisLine": {"lineStyle": {"color": "#cbd5e1"}},
         "axisLabel": {"color": C["neutro"]}}
    a.update(kw)
    return a


def yax(name=None, fmt=None, **kw):
    a = {"type": "value", "splitLine": {"lineStyle": {"color": C["grid"]}},
         "axisLabel": {"color": C["neutro"]}}
    if name:
        a["name"] = name
        a["nameTextStyle"] = {"color": C["neutro"], "align": "left"}
    if fmt:
        a["axisLabel"]["formatter"] = fmt
    a.update(kw)
    return a


def serie_tt(fmt):
    return {"tooltip": {"valueFormatter": fmt}}


def grafico(titulo, option, alto=340, key="", nota=None):
    st.markdown(f"##### {titulo}")
    if nota:
        st.caption(nota)
    st_echarts(option, height=f"{alto}px", key=key or titulo)


def mark_lines(prom, meta, eje="yAxis"):
    data = [{eje: round(prom, 1), "name": "Promedio",
             "lineStyle": {"color": C["neutro"], "type": "dashed"}, "label": {"formatter": "Prom. {c}%"}}]
    if meta > 0:
        data.append({eje: meta, "name": "Meta", "lineStyle": {"color": C["utilidad"], "type": "solid"},
                     "label": {"formatter": "Meta {c}%"}})
    return {"silent": True, "symbol": "none", "data": data}


def tabla_ranking(g, col):
    t = g.sort_values("Ventas", ascending=False).copy()
    t["% de ventas"] = t["Ventas"] / t["Ventas"].sum() * 100
    t = t[[col, "Pipas", "Vol_Venta", "Ventas", "Utilidad", "Margen", "Util_BBL", "% de ventas"]]
    t.columns = [col, "Pipas", "Volumen (BBL)", "Ventas (MXN)", "Utilidad (MXN)",
                 "Margen (%)", "Utilidad/BBL (MXN)", "% de ventas"]
    sty = t.style.format({
        "Pipas": "{:,.0f}", "Volumen (BBL)": "{:,.0f}", "Ventas (MXN)": "${:,.0f}",
        "Utilidad (MXN)": "${:,.0f}", "Margen (%)": "{:.1f}%", "Utilidad/BBL (MXN)": "${:,.2f}",
    }, na_rep="–")
    st.dataframe(
        sty, hide_index=True, use_container_width=True,
        column_config={"% de ventas": st.column_config.ProgressColumn(
            "% de ventas", format="%.1f%%", min_value=0, max_value=100)},
    )






def verificar_login():
    """Bloquea el acceso al dashboard hasta validar usuario y contraseña desde st.secrets."""
    if st.session_state.get("autenticado"):
        return

    st.markdown(CSS, unsafe_allow_html=True)
    _, col_centro, _ = st.columns([1, 1.2, 1])
    with col_centro:
        with st.container(border=True):
            st.subheader("🔒 Acceso Restringido")
            st.caption("Condensados BPS · Dashboard Ejecutivo")
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            if st.button("Iniciar sesión", use_container_width=True, type="primary"):
                auth_cfg = st.secrets.get("auth", {})
                if (
                    user_input == auth_cfg.get("usuario")
                    and pass_input == auth_cfg.get("password")
                ):
                    st.session_state["autenticado"] = True
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
    st.stop()





# =========================================================
# APLICACIÓN
# =========================================================
def main():
    verificar_login()
    st.markdown(CSS, unsafe_allow_html=True)

    df_raw, fetched_at = obtener_datos(NOMBRE_PESTANA)
    df = preparar(df_raw)

    # ---------------- Sidebar: filtros ----------------
    f_min, f_max = df["FECHAS"].min().date(), df["FECHAS"].max().date()

    def reset_filtros():
        st.session_state.f_preset = "Todo el histórico"
        st.session_state.f_cli = []
        st.session_state.f_dest = []

    with st.sidebar:
        st.markdown("### Filtros")
        preset = st.selectbox(
            "Periodo", ["Todo el histórico", "Últimos 30 días", "Últimos 3 meses", "Año en curso", "Personalizado"],
            key="f_preset", help="Los atajos se calculan a partir de la última fecha con datos.")
        if preset == "Personalizado":
            rango = st.date_input("Rango de fechas", value=(f_min, f_max), min_value=f_min, max_value=f_max)
            d_ini, d_fin = rango if isinstance(rango, (tuple, list)) and len(rango) == 2 else (f_min, f_max)
        else:
            d_fin = f_max
            d_ini = {
                "Todo el histórico": f_min,
                "Últimos 30 días": f_max - timedelta(days=30),
                "Últimos 3 meses": f_max - timedelta(days=90),
                "Año en curso": date(f_max.year, 1, 1),
            }[preset]

        clientes = st.multiselect("Cliente", sorted(df["Cliente"].unique()), key="f_cli", placeholder="Todos")
        destinos = st.multiselect("Destino", sorted(df["Destino"].unique()), key="f_dest", placeholder="Todos")

        st.markdown("### Metas")
        meta_margen = st.number_input("Meta de margen neto (%)", min_value=0.0, value=0.0, step=0.5,
                                      help="Opcional. Si es 0 no se muestra meta.")
        st.divider()
        st.button("Restablecer filtros", on_click=reset_filtros, use_container_width=True)
        if st.button("Actualizar datos", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"Datos de la hoja al {fetched_at:%d/%m/%Y %H:%M}")

    # ---------------- Aplicar filtros ----------------
    m = (df["FECHAS"] >= pd.Timestamp(d_ini)) & (df["FECHAS"] < pd.Timestamp(d_fin) + pd.Timedelta(days=1))
    if clientes:
        m &= df["Cliente"].isin(clientes)
    if destinos:
        m &= df["Destino"].isin(destinos)
    dff = df[m].copy()

    # ---------------- Encabezado ----------------
    st.title("Condensados BPS · Dashboard ejecutivo")
    if dff.empty:
        st.warning("No hay registros con los filtros actuales. Amplía el periodo o usa «Restablecer filtros».")
        st.stop()
    st.caption(
        f"{len(dff):,} pipas · {dff['FECHAS'].min():%d/%m/%Y} – {dff['FECHAS'].max():%d/%m/%Y} · "
        f"Clientes: {', '.join(clientes) if clientes else 'todos'} · "
        f"Destinos: {', '.join(destinos) if destinos else 'todos'}"
    )

    # ---------------- Agregados ----------------
    mes = agregar(dff, "AÑO_MES").sort_values("AÑO_MES").reset_index(drop=True)
    lbl = [mes_label(x) for x in mes["AÑO_MES"]]
    dff["_k"] = 1
    tot = agregar(dff, "_k").iloc[0]
    cli = agregar(dff, "Cliente")
    dst = agregar(dff, "Destino")

    # ---------------- KPIs ----------------
    r1 = st.columns(4)
    d_v, c_v = delta(mes["Ventas"])
    d_u, c_u = delta(mes["Utilidad"])
    d_b, c_b = delta(mes["Vol_Venta"])
    d_m, c_m = delta(mes["Margen"], tipo="pp")
    if meta_margen > 0 and not pd.isna(tot["Margen"]):
        d_m += f" · Meta {meta_margen:.1f}% {'✓' if tot['Margen'] >= meta_margen else '✗'}"

    kpi(r1[0], "Ventas totales", fm(tot["Ventas"]), d_v, c_v, "v", f"${tot['Ventas']:,.0f} MXN",
        spark(L(mes["Ventas"]), lbl, C["ventas"]))
    kpi(r1[1], "Utilidad neta", fm(tot["Utilidad"]), d_u, c_u, "u",
        f"Ventas − compra − flete − comisiones. ${tot['Utilidad']:,.0f} MXN",
        spark(L(mes["Utilidad"]), lbl, C["utilidad"]))
    kpi(r1[2], "Volumen vendido", f"{tot['Vol_Venta']:,.0f} BBL", d_b, c_b, "b", "Barriles vendidos en el periodo",
        spark(L(mes["Vol_Venta"]), lbl, C["volumen"]))
    kpi(r1[3], "Margen neto", f"{tot['Margen']:.1f}%", d_m, c_m, "m", "Utilidad neta / Ventas",
        spark(L(mes["Margen"], 1), lbl, C["margen"], barra=True))

    r2 = st.columns(4)
    d1, c1 = delta(mes["Util_BBL"])
    d2, c2 = delta(mes["Pipas"])
    d3, c3 = delta(mes["Merma"], tipo="pp", inverso=True)
    d4, c4 = delta(mes["Flete_Pct"], tipo="pp", inverso=True)
    kpi(r2[0], "Utilidad por barril", f"${tot['Util_BBL']:,.2f}", d1, c1, ayuda="Utilidad neta / BBL vendido (MXN)")
    kpi(r2[1], "Pipas despachadas", f"{tot['Pipas']:,.0f}", d2, c2,
        ayuda=f"Promedio de {tot['BBL_Pipa']:,.0f} BBL por pipa")
    kpi(r2[2], "Merma de volumen", f"{tot['Merma']:.2f}%", d3, c3,
        ayuda="(Vol. compra − Vol. venta) / Vol. compra. Menos es mejor")
    kpi(r2[3], "Costo logístico", f"{tot['Flete_Pct']:.1f}% de ventas", d4, c4,
        ayuda="Fletes / Ventas. Menos es mejor")

    ult = mes["AÑO_MES"].iloc[-1]
    parcial = " (mes en curso, parcial)" if ult == date.today().strftime("%Y-%m") else ""
    if len(mes) > 1:
        st.caption(f"Variaciones: {mes_label(ult)}{parcial} vs {mes_label(mes['AÑO_MES'].iloc[-2])}. "
                   "Verde = favorable, rojo = desfavorable.")

    # ---------------- Hallazgos automáticos ----------------
    hall = []
    mejor = mes.loc[mes["Utilidad"].idxmax()]
    hall.append(("Mejor mes", f"{mes_label(mejor['AÑO_MES'])}: {fm(mejor['Utilidad'])} de utilidad "
                              f"({mejor['Margen']:.1f}% de margen)"))
    if len(dst) > 1:
        bd = dst.loc[dst["Margen"].idxmax()]
        hall.append(("Destino más rentable", f"{bd['Destino']}: {bd['Margen']:.1f}% de margen, "
                                             f"${bd['Util_BBL']:,.2f} por barril"))
    if len(cli) > 1:
        tc_ = cli.loc[cli["Ventas"].idxmax()]
        share = tc_["Ventas"] / cli["Ventas"].sum() * 100
        hall.append(("Concentración de clientes", f"{tc_['Cliente']} aporta {share:.0f}% de las ventas"
                                                  + (" · riesgo alto" if share > 60 else "")))
    for col, (t, txt) in zip(st.columns(len(hall)), hall):
        col.markdown(f"<div class='insight'><b>{t}</b>{txt}</div>", unsafe_allow_html=True)

    st.write("")
    t_res, t_rent, t_op, t_mkt, t_det = st.tabs(["Resumen", "Rentabilidad", "Operación", "Mercado", "Detalle"])

    # =====================================================
    # TAB 1: RESUMEN
    # =====================================================
    with t_res:
        c_a, c_b_ = st.columns([1.6, 1])
        with c_a:
            grafico("Volumen vendido y utilidad neta por mes", base(
                tooltip={"trigger": "axis", "axisPointer": {"type": "cross"}},
                xAxis=[xax(lbl)],
                yAxis=[yax("Utilidad (MXN)", JS_MONEY),
                       yax("Volumen (BBL)", JS_NUM, splitLine={"show": False})],
                series=[
                    {"name": "Volumen (BBL)", "type": "bar", "yAxisIndex": 1, "barWidth": "45%",
                     "data": L(mes["Vol_Venta"]), "itemStyle": {"color": "rgba(245,158,11,.75)", "borderRadius": [4, 4, 0, 0]},
                     **serie_tt(JS_BBL_FULL)},
                    {"name": "Utilidad neta", "type": "line", "smooth": True, "yAxisIndex": 0,
                     "data": L(mes["Utilidad"]), "lineStyle": {"width": 3}, "itemStyle": {"color": C["utilidad"]},
                     **serie_tt(JS_MONEY_FULL)},
                ]), 360, "ev_mensual")

        with c_b_:
            v, co, f, cm, u = (float(tot[k]) for k in ("Ventas", "Compras", "Flete", "Comision", "Utilidad"))
            cats = ["Ventas", "Costo producto", "Flete", "Comisiones", "Utilidad neta"]
            vals = [v, co, f, cm, u]
            bases = [0, max(v - co, 0), max(v - co - f, 0), max(u, 0), 0]
            cols = [C["ventas"], C["costo"], C["costo"], C["costo"], C["utilidad"] if u >= 0 else C["costo"]]
            grafico("De ventas a utilidad neta", base(
                tooltip={"trigger": "item"},
                legend={"show": False},
                xAxis=[xax(cats, axisLabel={"color": C["neutro"], "interval": 0, "fontSize": 10, "rotate": 20})],
                yAxis=[yax(None, JS_MONEY)],
                series=[
                    {"type": "bar", "stack": "w", "silent": True, "data": bases,
                     "itemStyle": {"color": "transparent"}},
                    {"name": "Monto", "type": "bar", "stack": "w", "barWidth": "55%",
                     "data": [{"value": round(x), "itemStyle": {"color": c, "borderRadius": [4, 4, 0, 0]}}
                              for x, c in zip(vals, cols)],
                     "label": {"show": True, "position": "inside", "color": "#fff", "fontSize": 10,
                               "formatter": JS_WF_LBL},
                     **serie_tt(JS_MONEY_FULL)},
                ]), 360, "waterfall",
                nota=f"Cada peso vendido deja {tot['Margen']:.1f} centavos de utilidad.")

        c_c, c_d = st.columns(2)
        with c_c:
            grafico("Utilidad neta acumulada", base(
                xAxis=[xax(lbl, boundaryGap=False)], yAxis=[yax(None, JS_MONEY)], legend={"show": False},
                series=[{"name": "Utilidad acumulada", "type": "line", "smooth": True, "symbol": "none",
                         "data": L(mes["Utilidad"].cumsum()), "lineStyle": {"color": C["utilidad"], "width": 3},
                         "areaStyle": {"color": C["utilidad"], "opacity": 0.15}, **serie_tt(JS_MONEY_FULL)}],
            ), 300, "acum")
        with c_d:
            ml = mark_lines(float(tot["Margen"]), meta_margen)
            grafico("Margen neto mensual", base(
                xAxis=[xax(lbl)], yAxis=[yax(None, "{value}%")], legend={"show": False},
                series=[{"name": "Margen neto", "type": "bar", "barWidth": "50%", "data": L(mes["Margen"], 1),
                         "itemStyle": {"color": C["margen"], "borderRadius": [4, 4, 0, 0]},
                         "markLine": ml, **serie_tt(JS_PCT)}],
            ), 300, "margen_mes")

    # =====================================================
    # TAB 2: RENTABILIDAD
    # =====================================================
    with t_rent:
        c_l, c_r = st.columns(2)
        with c_l:
            t = cli.sort_values("Ventas", ascending=False)
            if len(t) > 7:
                otros = t.iloc[7:]["Ventas"].sum()
                t = pd.concat([t.iloc[:7][["Cliente", "Ventas"]],
                               pd.DataFrame({"Cliente": ["Otros"], "Ventas": [otros]})])
            grafico("Participación de cada cliente en las ventas", base(
                tooltip={"trigger": "item", "formatter": "{b}<br/>${c} MXN ({d}%)"},
                legend={"bottom": 0, "icon": "circle", "textStyle": {"color": C["neutro"]}},
                title={"text": fm(tot["Ventas"]), "subtext": "Ventas", "left": "center", "top": "38%",
                       "textAlign": "center", "textStyle": {"fontSize": 22}},
                series=[{"type": "pie", "radius": ["50%", "74%"], "center": ["50%", "46%"], "padAngle": 2,
                         "itemStyle": {"borderRadius": 8, "borderColor": "#fff", "borderWidth": 2},
                         "label": {"show": False},
                         "data": [{"value": round(r["Ventas"]), "name": r["Cliente"]} for _, r in t.iterrows()]}],
            ), 360, "dona_cli")
        with c_r:
            t = dst.sort_values("Margen", ascending=True)
            grafico("Margen neto por destino", base(
                legend={"show": False}, grid={"left": 8, "right": 40, "top": 24, "bottom": 8, "containLabel": True},
                xAxis=[yax(None, "{value}%")], yAxis=[xax(t["Destino"].tolist(), axisTick={"show": False})],
                series=[{"name": "Margen neto", "type": "bar", "barWidth": "55%", "data": L(t["Margen"], 1),
                         "itemStyle": {"color": C["margen"], "borderRadius": [0, 4, 4, 0]},
                         "label": {"show": True, "position": "right", "formatter": "{c}%", "fontWeight": "bold"},
                         "markLine": mark_lines(float(tot["Margen"]), meta_margen, "xAxis"),
                         **serie_tt(JS_PCT)}],
            ), 360, "margen_dest", nota="La línea punteada es el margen promedio del periodo.")

        st.markdown("##### Ranking detallado")
        vista = st.radio("Agrupar por", ["Cliente", "Destino"], horizontal=True, label_visibility="collapsed")
        tabla_ranking(cli if vista == "Cliente" else dst, vista)

    # =====================================================
    # TAB 3: OPERACIÓN
    # =====================================================
    with t_op:
        c_l, c_r = st.columns(2)
        with c_l:
            mx = int(mes["Pipas"].max())
            grafico("Pipas despachadas por mes", base(
                xAxis=[xax(lbl)], yAxis=[yax(None)], legend={"show": False},
                series=[{"name": "Pipas", "type": "bar", "barWidth": "50%",
                         "data": [{"value": int(n), "itemStyle": {
                             "color": C["volumen"] if n == mx else C["ventas"], "borderRadius": [5, 5, 0, 0]}}
                             for n in mes["Pipas"]],
                         "label": {"show": True, "position": "top", "fontWeight": "bold"}}],
            ), 320, "pipas", nota="En naranja el mes con más despachos.")
        with c_r:
            grafico("Barriles por pipa (carga promedio)", base(
                xAxis=[xax(lbl)], yAxis=[yax(None, scale=True)], legend={"show": False},
                series=[{"name": "BBL por pipa", "type": "line", "smooth": True, "data": L(mes["BBL_Pipa"], 1),
                         "lineStyle": {"color": C["volumen"], "width": 3}, "itemStyle": {"color": C["volumen"]},
                         **serie_tt(JS_BBL_FULL)}],
            ), 320, "bbl_pipa", nota="Una carga promedio más baja eleva el costo de flete por barril.")

        c_l, c_r = st.columns(2)
        with c_l:
            grafico("Merma de volumen (compra vs. venta)", base(
                xAxis=[xax(lbl)], yAxis=[yax(None, "{value}%")], legend={"show": False},
                series=[{"name": "Merma", "type": "bar", "barWidth": "50%", "data": L(mes["Merma"], 2),
                         "itemStyle": {"color": C["costo"], "borderRadius": [4, 4, 0, 0]}, **serie_tt(JS_PCT)}],
            ), 300, "merma", nota="Merma = (volumen comprado − vendido) / volumen comprado.")
        with c_r:
            grafico("Costo logístico como % de ventas", base(
                xAxis=[xax(lbl)], yAxis=[yax(None, "{value}%", scale=True)], legend={"show": False},
                series=[{"name": "Flete / Ventas", "type": "line", "smooth": True, "data": L(mes["Flete_Pct"], 1),
                         "lineStyle": {"color": C["costo"], "width": 3}, "itemStyle": {"color": C["costo"]},
                         **serie_tt(JS_PCT)}],
            ), 300, "flete_pct")

        fin = dff["FECHAS"].max()
        ini = max(dff["FECHAS"].min(), fin - pd.Timedelta(days=364))
        dias = dff[dff["FECHAS"] >= ini].groupby(dff["FECHAS"].dt.strftime("%Y-%m-%d")).size()
        grafico("Calendario de despachos (pipas por día)", {
            "textStyle": {"fontFamily": "inherit"},
            "tooltip": {"formatter": js("function(p){return p.value[0]+': <b>'+p.value[1]+'</b> pipas';}")},
            "visualMap": {"min": 1, "max": max(int(dias.max()), 2), "show": False,
                          "inRange": {"color": ["#bfdbfe", C["ventas"]]}},
            "calendar": {"top": 28, "left": 36, "right": 16, "cellSize": ["auto", 16], "range": [ini.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")],
                         "itemStyle": {"borderWidth": 2, "borderColor": "#fff", "color": "#f1f5f9"},
                         "splitLine": {"show": False}, "yearLabel": {"show": False},
                         "dayLabel": {"firstDay": 1, "nameMap": ["D", "L", "M", "M", "J", "V", "S"], "color": C["neutro"]},
                         "monthLabel": {"nameMap": MESES, "color": C["neutro"]}},
            "series": [{"type": "heatmap", "coordinateSystem": "calendar", "data": [[d, int(n)] for d, n in dias.items()]}],
        }, 200, "calendario", nota="Últimos 12 meses del periodo seleccionado. Útil para detectar días sin operación.")

    # =====================================================
    # TAB 4: MERCADO
    # =====================================================
    with t_mkt:
        wti = obtener_wti(min(df["FECHAS"].min() - pd.Timedelta(days=45), pd.Timestamp("2023-01-01")).strftime("%Y-%m-%d"),
                          (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
        if wti.empty:
            st.info("No se pudieron obtener cotizaciones del WTI desde Yahoo Finance. "
                    "Las gráficas de esta pestaña que dependen del WTI se omiten.")
        wti_mes = (wti.groupby("AÑO_MES", as_index=False)["Close"].mean().rename(columns={"Close": "WTI"})
                   if not wti.empty else pd.DataFrame(columns=["AÑO_MES", "WTI"]))

        pr = precios_usd_mes(dff).merge(wti_mes, on="AÑO_MES", how="left")
        pr = mes[["AÑO_MES"]].merge(pr, on="AÑO_MES", how="left")
        pr_lbl = [mes_label(x) for x in pr["AÑO_MES"]]
        tcm = dff[dff["TC"] > 0].groupby("AÑO_MES", as_index=False)["TC"].mean()
        mac = mes[["AÑO_MES"]].merge(tcm, on="AÑO_MES", how="left").merge(wti_mes, on="AÑO_MES", how="left")

        c_l, c_r = st.columns(2)
        with c_l:
            grafico("Precio de compra y venta vs. WTI (USD/BBL)", base(
                tooltip={"trigger": "axis", "axisPointer": {"type": "cross"}},
                grid={"left": 8, "right": 52, "top": 44, "bottom": 8, "containLabel": True},
                xAxis=[xax(pr_lbl)], yAxis=[yax("USD / BBL", "${value}", scale=True)],
                series=[
                    {"name": "Precio venta", "type": "line", "smooth": True, "data": L(pr["Venta_USD_BBL"], 2),
                     "itemStyle": {"color": C["utilidad"]}, "endLabel": {"show": True}, **serie_tt(JS_USD)},
                    {"name": "Precio compra", "type": "line", "smooth": True, "data": L(pr["Compra_USD_BBL"], 2),
                     "itemStyle": {"color": C["ventas"]}, "endLabel": {"show": True}, **serie_tt(JS_USD)},
                    {"name": "WTI (prom. mensual)", "type": "line", "smooth": True, "data": L(pr["WTI"], 2),
                     "lineStyle": {"type": "dashed", "width": 2}, "itemStyle": {"color": C["volumen"]},
                     "endLabel": {"show": True}, **serie_tt(JS_USD)},
                ]), 360, "precios")
        with c_r:
            grafico("Tipo de cambio vs. WTI", base(
                tooltip={"trigger": "axis", "axisPointer": {"type": "cross"}},
                xAxis=[xax([mes_label(x) for x in mac["AÑO_MES"]])],
                yAxis=[yax("WTI (USD)", "${value}", scale=True,
                           axisLine={"show": True, "lineStyle": {"color": C["volumen"]}}),
                       yax("TC (MXN/USD)", "{value}", scale=True, splitLine={"show": False},
                           axisLine={"show": True, "lineStyle": {"color": C["margen"]}})],
                series=[
                    {"name": "WTI", "type": "line", "smooth": True, "yAxisIndex": 0, "data": L(mac["WTI"], 2),
                     "itemStyle": {"color": C["volumen"]}, **serie_tt(JS_USD)},
                    {"name": "Tipo de cambio", "type": "bar", "barWidth": "40%", "yAxisIndex": 1,
                     "data": L(mac["TC"], 2), "itemStyle": {"color": "rgba(124,58,237,.7)", "borderRadius": [4, 4, 0, 0]}},
                ]), 360, "macro")

        c_l, c_r = st.columns(2)
        dif_v, dif_c = pr["Venta_USD_BBL"] - pr["WTI"], pr["Compra_USD_BBL"] - pr["WTI"]
        with c_l:
            grafico("Diferencial contra WTI (USD/BBL)", base(
                tooltip={"trigger": "axis", "axisPointer": {"type": "cross"}},
                xAxis=[xax(pr_lbl)], yAxis=[yax(None, "${value}")],
                series=[
                    {"name": "Venta − WTI", "type": "line", "smooth": True, "data": L(dif_v, 2),
                     "itemStyle": {"color": C["utilidad"]}, **serie_tt(JS_USD)},
                    {"name": "Compra − WTI", "type": "line", "smooth": True, "data": L(dif_c, 2),
                     "itemStyle": {"color": C["ventas"]}, **serie_tt(JS_USD)},
                ]), 300, "dif_wti", nota="Qué tan por debajo (o encima) del WTI se compra y se vende.")
        with c_r:
            grafico("Spread bruto venta − compra (USD/BBL)", base(
                xAxis=[xax(pr_lbl)], yAxis=[yax(None, "${value}")], legend={"show": False},
                series=[{"name": "Spread", "type": "bar", "barWidth": "50%",
                         "data": L(pr["Venta_USD_BBL"] - pr["Compra_USD_BBL"], 2),
                         "itemStyle": {"color": C["utilidad"], "borderRadius": [4, 4, 0, 0]}, **serie_tt(JS_USD)}],
            ), 300, "spread", nota="Antes de flete y comisiones.")

        if not wti.empty:
            h1, h2 = st.columns([0.7, 0.3])
            h1.markdown("##### WTI diario (velas) con media móvil de 20 días")
            ventana = h2.radio("Ventana", ["1M", "3M", "6M", "1A", "Todo"], index=2, horizontal=True,
                               label_visibility="collapsed")
            w = wti.sort_values("Fecha").copy()
            w["MA20"] = w["Close"].rolling(20).mean()
            dias_v = {"1M": 30, "3M": 90, "6M": 180, "1A": 365}.get(ventana)
            if dias_v:
                w = w[w["Fecha"] >= w["Fecha"].max() - pd.Timedelta(days=dias_v)]
            st_echarts(base(
                tooltip={"trigger": "axis", "axisPointer": {"type": "cross"}},
                grid={"left": 8, "right": 16, "top": 36, "bottom": 56, "containLabel": True},
                xAxis=[xax(w["Fecha"].dt.strftime("%Y-%m-%d").tolist(), boundaryGap=True)],
                yAxis=[yax("USD / BBL", "${value}", scale=True)],
                dataZoom=[{"type": "inside"}, {"type": "slider", "bottom": 8, "height": 18}],
                series=[
                    {"name": "WTI", "type": "candlestick",
                     "data": [[round(float(r.Open), 2), round(float(r.Close), 2), round(float(r.Low), 2),
                               round(float(r.High), 2)] for r in w.itertuples()],
                     "itemStyle": {"color": C["up"], "color0": C["down"], "borderColor": C["up"],
                                   "borderColor0": C["down"]}},
                    {"name": "Media móvil 20d", "type": "line", "symbol": "none", "smooth": True,
                     "data": L(w["MA20"], 2), "lineStyle": {"color": C["margen"], "width": 2}},
                ]), height="420px", key="candle")

    # =====================================================
    # TAB 5: DETALLE
    # =====================================================
    with t_det:
        cols_det = [c for c in ["ID_Op", "FECHAS", "Cliente", "Destino", "Volumen_Venta_BLS", "Subtotal_Venta_MXN",
                                "Subtotal_Compra_MXN", "Subtotal_Transporte_MXN", "Comision_MXN", "Utilidad_Neta"]
                    if c in dff.columns]
        det = dff.sort_values("FECHAS", ascending=False)[cols_det].copy()
        det["FECHAS"] = det["FECHAS"].dt.date
        b1, b2 = st.columns([0.8, 0.2])
        b1.caption(f"{len(det):,} registros. Usa el buscador de la tabla (esquina superior derecha) o haz clic en un encabezado para ordenar.")
        b2.download_button("Descargar CSV", det.to_csv(index=False).encode("utf-8-sig"),
                           "condensados_detalle.csv", "text/csv", use_container_width=True)
        fmt = {c: "${:,.0f}" for c in cols_det if c.endswith("_MXN") or c == "Utilidad_Neta"}
        fmt["Volumen_Venta_BLS"] = "{:,.0f}"
        st.dataframe(det.style.format(fmt, na_rep="–"), hide_index=True, use_container_width=True, height=480,
                     column_config={"FECHAS": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY")})


try:
    main()
except Exception as e:
    st.error(f"Error al cargar el dashboard de Condensados: {e}")
    with st.expander("Detalle técnico"):
        st.exception(e)
