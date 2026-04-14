import streamlit as st
import pandas as pd
from datetime import datetime

from oauth import get_credentials
from googleapiclient.discovery import build
from saas import crear_entorno_cliente
from database import conectar_sheet


# ================================
# 🔧 CONFIG GLOBAL
# ================================
st.set_page_config(layout="wide")


# ================================
# 🔧 FUNCIONES
# ================================

_sheet_cache = {}

def get_cached_sheet(sheet_id):
    if sheet_id not in _sheet_cache:
        _sheet_cache[sheet_id] = get_sheet(sheet_id)
    return _sheet_cache[sheet_id]

def to_csv(df):
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig", decimal=",")


@st.cache_resource
def get_sheet(sheet_id):
    credentials = get_credentials()
    return conectar_sheet(credentials, sheet_id)


def asegurar_estructura(sheet):
    estructura = {
        "productos": ["nombre", "categoria", "unidad", "stock_min"],
        "movimientos": ["fecha", "producto", "acción", "cantidad", "monto total", "nota"],
        "categorias": ["nombre"],
        "unidades": ["nombre"]
    }

    for nombre_hoja, headers in estructura.items():
        ws = sheet.worksheet(nombre_hoja)
        try:
            ws.update('A1', [headers])
        except Exception:
            pass


@st.cache_data(ttl=600)
def load_all_data(sheet_id):
    sheet = get_sheet(sheet_id)

    data = {}
    hojas = ["productos", "movimientos", "categorias", "unidades"]

    for nombre in hojas:
        ws = sheet.worksheet(nombre)
        values = ws.get_all_values()

        if len(values) <= 1:
            df = pd.DataFrame()
        else:
            headers = [h.strip().lower() for h in values[0]]
            df = pd.DataFrame(values[1:], columns=headers)

        data[nombre] = df

    if not data["movimientos"].empty:
        df = data["movimientos"]
        df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce")
        df["monto total"] = pd.to_numeric(df["monto total"], errors="coerce")

    return data


def calcular_stock(df_mov, producto):
    if df_mov.empty or "producto" not in df_mov.columns:
        return 0

    df_p = df_mov[df_mov["producto"] == producto]

    ingresos = df_p[df_p["acción"] == "Ingreso"]["cantidad"].sum()
    salidas = df_p[df_p["acción"] == "Salida"]["cantidad"].sum()

    return ingresos - salidas


# ================================
# 🔐 LOGIN
# ================================

if "login" not in st.session_state:
    st.session_state["login"] = False


def mostrar_login():
    st.title("🔐 Login")

    modo = st.radio("Acción", ["Login", "Crear cuenta"])

    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Continuar"):

        credentials = get_credentials()
        MASTER_SHEET_ID = "1YoydFLwr_ohlRjk8Aaa8vRVti4sdj3QZ5yVNtAO3nis"
        sheet = conectar_sheet(credentials, MASTER_SHEET_ID)

        ws = sheet.worksheet("usuarios")
        df = pd.DataFrame(ws.get_all_records())

        if modo == "Login":
            user = df[
                (df["usuario"] == usuario) &
                (df["password"] == password)
            ]

            if not user.empty:
                st.session_state["login"] = True
                st.session_state["usuario"] = usuario
                st.session_state["sheet_id"] = user.iloc[0]["sheet_id"]
                st.rerun()
            else:
                st.error("Credenciales incorrectas")

        else:
            if not df[df["usuario"] == usuario].empty:
                st.error("El usuario ya existe")
            else:
                service = build('drive', 'v3', credentials=credentials)
                sheet_id = crear_entorno_cliente(service, credentials, usuario)

                ws.append_row([usuario, password, sheet_id])

                st.success("Cuenta creada")
                st.session_state["login"] = True
                st.session_state["sheet_id"] = sheet_id
                st.rerun()


# ================================
# 🚪 LOGIN FLOW
# ================================

if not st.session_state["login"]:
    mostrar_login()
    st.stop()


# ================================
# 🟢 APP PRINCIPAL
# ================================

st.title("📦 Inventario")

sheet = get_cached_sheet(st.session_state["sheet_id"])
st.session_state["sheet"] = sheet

if "init" not in st.session_state:
    asegurar_estructura(sheet)
    st.session_state["init"] = True

data = load_all_data(st.session_state["sheet_id"])

df_prod = data["productos"]
df_mov = data["movimientos"]
df_cat = data["categorias"]
df_uni = data["unidades"]


menu = st.radio(
    "Menú",  # <- SOLO esto se agrega
    ["📊 Inventario", "🔄 Movimientos", "⚙️ Configuración", "📜 Historial"],
    horizontal=True
)


# ================================
# 📊 INVENTARIO
# ================================

if menu == "📊 Inventario":

    if df_prod.empty:
        st.info("👈 Ve a Configuración para crear productos")

    else:
        resultados = []

        if not df_mov.empty:
            df_mov["precio"] = df_mov["monto total"] / df_mov["cantidad"]

            df_mov_grouped = df_mov.groupby("producto") if not df_mov.empty else None

            for _, prod in df_prod.iterrows():

                nombre = prod["nombre"]

                df_p = df_mov_grouped.get_group(nombre) if df_mov_grouped is not None and nombre in df_mov_grouped.groups else pd.DataFrame()

                ingresos = df_p[df_p["acción"] == "Ingreso"]
                salidas = df_p[df_p["acción"] == "Salida"]

                stock = ingresos["cantidad"].sum() - salidas["cantidad"].sum()

                total_ing = ingresos["cantidad"].sum()

                if total_ing > 0:
                    costo = (ingresos["cantidad"] * ingresos["precio"]).sum() / total_ing
                else:
                    costo = 0

                stock_min = int(prod.get("stock_min", 0))

                if stock <= 0:
                    estado = "🔴 Sin stock"
                elif stock <= stock_min:
                    estado = "🟠 Bajo mínimo"
                else:
                    estado = "🟢 OK"

                resultados.append({
                    "producto": nombre,
                    "stock": stock,
                    "costo_promedio": round(costo, 2),
                    "total": round(stock * costo, 2),
                    "estado": estado
                })

        df_inv = pd.DataFrame(resultados)

        st.dataframe(df_inv, use_container_width=True)
        st.download_button("Descargar", to_csv(df_inv), "inventario.csv")


# ================================
# 🔄 MOVIMIENTOS
# ================================

elif menu == "🔄 Movimientos":

    if df_prod.empty:
        st.warning("Primero crea productos en ⚙️ Configuración")

    else:
        st.subheader("Entrada")

        producto = st.selectbox("Producto", df_prod["nombre"])
        cantidad = st.number_input("Cantidad", min_value=1)
        costo = st.number_input("Costo total", min_value=0.0)
        nota = st.text_input("Nota")

        if st.button("Guardar entrada"):
            ws = sheet.worksheet("movimientos")

            ws.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                producto,
                "Ingreso",
                float(cantidad),
                float(costo),
                nota
            ])

            st.cache_data.clear()
            st.rerun()

        st.subheader("Salida")

        producto_s = st.selectbox("Producto salida", df_prod["nombre"])

        stock = calcular_stock(df_mov, producto_s)
        st.info(f"Stock actual: {stock}")

        modo = st.radio("Tipo", ["Cantidad", "Stock final"])

        if modo == "Cantidad":
            cantidad_s = st.number_input("Cantidad salida", min_value=1)
        else:
            nuevo = st.number_input("Stock final", min_value=0)
            cantidad_s = stock - nuevo
            st.write(f"Salida: {cantidad_s}")

        if st.button("Registrar salida"):

            if cantidad_s <= 0 or cantidad_s > stock:
                st.error("Cantidad inválida")
            else:
                ws = sheet.worksheet("movimientos")

                df_temp = df_mov[df_mov["producto"] == producto_s]
                ing = df_temp[df_temp["acción"] == "Ingreso"]

                if not ing.empty and ing["cantidad"].sum() > 0:
                    costo_prom = ing["monto total"].sum() / ing["cantidad"].sum()
                else:
                    costo_prom = 0

                cantidad_s = int(cantidad_s)

                ws.append_row([
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    producto_s,
                    "Salida",
                    float(cantidad_s),
                    float(costo_prom),
                    ""
                ])

                st.cache_data.clear()
                st.rerun()


# ================================
# ⚙️ CONFIG
# ================================

elif menu == "⚙️ Configuración":

    ws_prod = sheet.worksheet("productos")
    ws_cat = sheet.worksheet("categorias")
    ws_uni = sheet.worksheet("unidades")

    st.subheader("📦 Crear producto")

    categorias = df_cat["nombre"].dropna().tolist() if ("nombre" in df_cat.columns and not df_cat.empty) else []
    unidades = df_uni["nombre"].dropna().tolist() if ("nombre" in df_uni.columns and not df_uni.empty) else []

    nombre = st.text_input("Nombre producto")
    categoria = st.selectbox("Categoría", categorias if categorias else [""])
    unidad = st.selectbox("Unidad", unidades if unidades else [""])
    stock_min = st.number_input("Stock mínimo", min_value=0)

    if st.button("Guardar producto", key="btn_producto"):
        ws_prod.append_row([nombre, categoria, unidad, stock_min])
        st.success("Producto guardado ✅")
        st.rerun()

    st.divider()

    st.subheader("🏷️ Categorías")

    nueva_cat = st.text_input("Nueva categoría")
    emoji = st.text_input("Emoji categoría (ej: 🥦, 🍺, 📦)")

    if st.button("Agregar categoría", key="btn_cat"):
        ws_cat.append_row([nueva_cat, emoji])
        st.success("Categoría creada")
        st.rerun()

    st.divider()

    st.subheader("📏 Unidades")

    nueva_uni = st.text_input("Nueva unidad")

    if st.button("Agregar unidad", key="btn_uni"):
        ws_uni.append_row([nueva_uni])
        st.success("Unidad creada")
        st.rerun()


# ================================
# 📜 HISTORIAL
# ================================

elif menu == "📜 Historial":

    if not df_mov.empty:
        df_mov["costo unitario"] = df_mov.apply(
            lambda x: x["monto total"] / x["cantidad"] if x["cantidad"] not in [0, None] else 0,
            axis=1
        )

        st.dataframe(df_mov)
        st.download_button("Descargar", to_csv(df_mov), "historial.csv")