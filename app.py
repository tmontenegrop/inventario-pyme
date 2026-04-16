import streamlit as st
import pandas as pd

from oauth import get_credentials
from googleapiclient.discovery import build
from saas import crear_entorno_cliente
from database import conectar_sheet

# 🔥 NUEVO
from data_layer import (
    get_all_data,
    crear_producto,
    crear_categoria,
    crear_unidad,
    crear_movimiento,
    calcular_estado_producto
)

# ================================
# CONFIG
# ================================
st.set_page_config(layout="wide")

# ================================
# CONEXIÓN
# ================================
@st.cache_resource
def get_sheet(sheet_id):
    credentials = get_credentials()
    return conectar_sheet(credentials, sheet_id)

# ================================
# LOGIN
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
            df["usuario"] = df["usuario"].astype(str).str.strip()
            df["password"] = df["password"].astype(str).str.strip()

            usuario_input = str(usuario).strip()
            password_input = str(password).strip()

            user = df[
                (df["usuario"] == usuario_input) &
                (df["password"] == password_input)
                ]

            if not user.empty:
                st.session_state["login"] = True
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

                st.session_state["login"] = True
                st.session_state["sheet_id"] = sheet_id
                st.rerun()


if not st.session_state["login"]:
    mostrar_login()
    st.stop()

# ================================
# APP
# ================================
st.title("📦 Inventario")

sheet = get_sheet(st.session_state["sheet_id"])

# 🔥 DATA CENTRALIZADA
@st.cache_data(ttl=30)
def load_data_cached(sheet_id):
    sheet = get_sheet(sheet_id)
    return get_all_data(sheet)

data = load_data_cached(st.session_state["sheet_id"])

df_prod = data["productos"]
df_mov = data["movimientos"]
df_cat = data["categorias"]
df_uni = data["unidades"]

menu = st.radio(
    "Menú",
    ["📊 Inventario", "🔄 Movimientos", "⚙️ Configuración", "📜 Historial"],
    horizontal=True
)

# ================================
# INVENTARIO
# ================================
if menu == "📊 Inventario":

    if df_prod.empty:
        st.info("👈 Ve a Configuración para crear productos")

    else:
        resultados = []

        for _, prod in df_prod.iterrows():
            nombre = prod["nombre"]

            stock, valor, cpp = calcular_estado_producto(df_mov, nombre)
            stock_min = pd.to_numeric(prod.get("stock_min"), errors="coerce")
            stock_min = int(stock_min) if pd.notna(stock_min) else 0

            if stock <= 0:
                estado = "🔴 Sin stock"
            elif stock <= stock_min:
                estado = "🟠 Bajo mínimo"
            else:
                estado = "🟢 OK"

            resultados.append({
                "producto": nombre,
                "stock": stock,
                "estado": estado
            })

        df_inv = pd.DataFrame(resultados)
        st.dataframe(df_inv, width="stretch")

# ================================
# MOVIMIENTOS
# ================================
elif menu == "🔄 Movimientos":

    if df_prod.empty:
        st.warning("Primero crea productos en ⚙️ Configuración")

    else:
        st.subheader("Entrada / Salida")

        # 🔥 ORDEN CORRECTO
        tipo = st.radio("Tipo", ["Ingreso", "Salida", "Ajuste"])

        producto = st.selectbox("Producto", df_prod["nombre"])

        cantidad = st.number_input("Cantidad", min_value=1)

        monto_total = 0
        if tipo == "Ingreso":
            monto_total = st.number_input(
                "Monto Total",
                min_value=0.0,
                value=None,
                placeholder="Ingrese monto total"
            )

        nota = st.text_input("Nota")

        # 🔘 BOTÓN
        if st.button("Guardar movimiento"):

            # 🔥 VALIDACIÓN (solo aquí)
            if tipo == "Ingreso" and (monto_total is None or monto_total <= 0):
                st.error("Debe ingresar un monto total válido")
                st.stop()

            if tipo == "Ajuste":
                stock_actual, _, _ = calcular_estado_producto(df_mov, producto)

                diferencia = stock_actual - cantidad

                if diferencia > 0:
                    tipo_real = "Salida"
                    cantidad_real = diferencia
                else:
                    tipo_real = "Ingreso"
                    cantidad_real = abs(diferencia)

                ok, msg = crear_movimiento(
                    sheet,
                    producto,
                    cantidad_real,
                    tipo_real,
                    f"Ajuste a {cantidad}. {nota}",
                    0
                )

            elif tipo == "Ingreso":

                ok, msg = crear_movimiento(
                    sheet,
                    producto,
                    cantidad,
                    "Ingreso",
                    nota,
                    monto_total
                )

            else:  # Salida

                stock_actual, valor_actual, cpp = calcular_estado_producto(df_mov, producto)

                if stock_actual <= 0:
                    st.error("No hay stock disponible")
                    st.stop()

                if cantidad > stock_actual:
                    st.error("Stock insuficiente")
                    st.stop()

                monto_salida = cantidad * cpp

                ok, msg = crear_movimiento(
                    sheet,
                    producto,
                    cantidad,
                    "Salida",
                    nota,
                    monto_salida
                )

            if ok:
                st.success(msg)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(msg)

# ================================
# CONFIGURACIÓN
# ================================
elif menu == "⚙️ Configuración":

    st.write("CATEGORIAS DF:")
    st.write(df_cat)

    st.write("COLUMNAS:")
    st.write(df_cat.columns)

    st.subheader("📦 Crear producto")

    categorias = df_cat["categoria"].tolist() if "categoria" in df_cat.columns else []
    unidades = df_uni["unidad"].tolist() if "unidad" in df_uni.columns else []

    nombre = st.text_input("Nombre producto")
    categoria = st.selectbox("Categoría", categorias if categorias else [""])
    unidad = st.selectbox("Unidad", unidades if unidades else [""])
    stock_min = st.number_input("Stock mínimo", min_value=0)

    if st.button("Guardar producto"):

        ok, msg = crear_producto(
            sheet,
            nombre,
            categoria,
            unidad,
            stock_min
        )

        if ok:
            st.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(msg)

    st.divider()

    # ====================
    # CATEGORÍAS
    # ====================
    st.subheader("🏷️ Categorías")

    nueva_cat = st.text_input("Nueva categoría")
    emoji = st.text_input("Emoji")

    if st.button("Agregar categoría"):

        ok, msg = crear_categoria(sheet, nueva_cat, emoji)

        if ok:
            st.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(msg)

    st.divider()

    # ====================
    # UNIDADES
    # ====================
    st.subheader("📏 Unidades")

    nueva_uni = st.text_input("Nueva unidad")

    if st.button("Agregar unidad"):

        ok, msg = crear_unidad(sheet, nueva_uni)

        if ok:
            st.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(msg)

# ================================
# HISTORIAL
# ================================
elif menu == "📜 Historial":

    if not df_mov.empty:
        st.dataframe(df_mov, width="stretch")