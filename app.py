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
if st.button("🔄 Reautenticar"):
    st.cache_resource.clear()
    st.rerun()
# ================================
# CONFIG
# ================================
st.set_page_config(layout="wide")

# ================================
# CONEXIÓN
# ================================
@st.cache_resource
def get_sheet(sheet_id):
    try:
        credentials = get_credentials()
        return conectar_sheet(credentials, sheet_id)
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

# ================================
# LOGIN
# ================================
# 🔥 intentar recuperar sesión desde URL
if "login" not in st.session_state:
    st.session_state["login"] = False

    # 🔥 recuperar sesión desde URL
    params = st.query_params

    if "sheet_id" in params and not st.session_state["login"]:
        st.session_state["login"] = True
        st.session_state["sheet_id"] = params["sheet_id"]


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

                # 🔥 NUEVO (guardar en URL)
                st.query_params["sheet_id"] = user.iloc[0]["sheet_id"]

                st.success("Login exitoso")  # 👈 opcional pero recomendado
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

                # 🔥 NUEVO
                st.query_params["sheet_id"] = sheet_id

                st.success("Cuenta creada correctamente")  # opcional
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

# 🔥 FILTRAR ELIMINADOS (SOFT DELETE)
if "estado" in df_prod.columns:
    df_prod = df_prod[df_prod["estado"] != "ELIMINADO"]

if "estado" in df_cat.columns:
    df_cat = df_cat[df_cat["estado"] != "ELIMINADO"]

if "estado" in df_uni.columns:
    df_uni = df_uni[df_uni["estado"] != "ELIMINADO"]

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
            stock_min = pd.to_numeric(prod.get("stock_minimo"), errors="coerce")
            stock_min = int(stock_min) if pd.notna(stock_min) else 0

            if stock <= 0:
                estado = "🔴 Sin stock"
            elif stock <= stock_min:
                estado = "⚠️ Stock Crítico"
            else:
                estado = "🟢 OK"

            resultados.append({
                "producto": nombre,
                "stock": round(stock, 2),
                "cpp": round(cpp, 2),
                "valor_inventario": round(stock * cpp, 2),
                "estado": estado
            })

        df_inv = pd.DataFrame(resultados)
        df_inv = df_inv.sort_values("producto")
        df_view = df_inv.copy()

        for col in ["cpp", "valor_inventario"]:
            if col in df_view.columns:
                df_view[col] = df_view[col].apply(
                    lambda x: f"${x:,.0f}".replace(",", ".") if pd.notna(x) else ""
                )

        st.dataframe(df_view, width="stretch")

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

                stock_actual, valor_actual, cpp = calcular_estado_producto(df_mov, producto)

                diferencia = stock_actual - cantidad

                if diferencia > 0:
                    # 🔻 BAJA STOCK → SALIDA
                    tipo_real = "Salida"
                    cantidad_real = diferencia
                    monto_total = cantidad_real * cpp

                else:
                    # 🔺 SUBE STOCK → INGRESO
                    tipo_real = "Ingreso"
                    cantidad_real = abs(diferencia)
                    monto_total = cantidad_real * cpp  # 🔥 usamos CPP actual

                ok, msg = crear_movimiento(
                    sheet,
                    producto,
                    cantidad_real,
                    tipo_real,
                    f"Ajuste a {cantidad}. {nota}",
                    monto_total
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

    # st.subheader("🗑️ Eliminar producto")
    #
    # df_sel = data["productos"].copy()
    #
    # if "estado" in df_sel.columns:
    #     df_sel = df_sel[df_sel["estado"] != "ELIMINADO"]
    #
    # if not df_sel.empty:
    #
    #     df_sel["row_number"] = df_sel.index + 2
    #     df_sel["id"] = df_sel.index.astype(str)
    #
    #     tipo = "producto"
    #
    #     prod = st.selectbox(
    #         "Producto",
    #         df_sel["id"],
    #         format_func=lambda x: df_sel.loc[int(x), "nombre"],
    #         key=f"select_{tipo}_eliminar"
    #     )
    #
    #     if st.button("Eliminar producto"):
    #         fila = int(df_sel.loc[int(prod), "row_number"])
    #         ws = sheet.worksheet("productos")
    #         ws.update_cell(fila, 6, "ELIMINADO")  # 👈 col Estado
    #
    #         st.success("Producto eliminado")
    #         st.cache_data.clear()
    #         st.rerun()

    # ====================
    # 🗑️ ELIMINAR PRODUCTO
    # ====================

    st.subheader("🗑️ Eliminar producto")

    df_sel = data["productos"].copy()

    if "estado" in df_sel.columns:
        df_sel = df_sel[df_sel["estado"] != "ELIMINADO"]

    if not df_sel.empty:

        df_sel["row_number"] = df_sel.index + 2
        df_sel["id"] = df_sel.index.astype(str)

        if "confirmar_eliminar_producto" not in st.session_state:
            st.session_state["confirmar_eliminar_producto"] = False

        prod = st.selectbox(
            "Producto",
            df_sel["id"],
            format_func=lambda x: df_sel.loc[int(x), "nombre"],
            key="select_producto_eliminar"
        )

        if st.button("🗑️ Eliminar producto", type="primary"):
            st.session_state["confirmar_eliminar_producto"] = True

        if st.session_state["confirmar_eliminar_producto"]:

            st.error("⚠️ Esta acción no se puede deshacer")
            st.warning("¿Seguro que quieres eliminar este producto?")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("✅ Sí, eliminar"):
                    fila = int(df_sel.loc[int(prod), "row_number"])
                    ws = sheet.worksheet("productos")
                    ws.update_cell(fila, 6, "ELIMINADO")

                    st.success("Producto eliminado")
                    st.session_state["confirmar_eliminar_producto"] = False
                    st.cache_data.clear()
                    st.rerun()

            with col2:
                if st.button("❌ Cancelar"):
                    st.session_state["confirmar_eliminar_producto"] = False



    # ====================
    # CATEGORÍAS
    # ====================
    st.subheader("🏷️ Categorías")

    nueva_cat = st.text_input("Nueva categoría")
    emoji = st.selectbox(
        "Emoji",
        ["📦", "🍎", "🥤", "🧂", "🍞", "🥩", "🧀", "🍺", "📊", "🔧"],
        key="emoji_select"
    )

    if st.button("Agregar categoría"):

        ok, msg = crear_categoria(sheet, nueva_cat, emoji)

        if ok:
            st.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(msg)

    st.divider()

    st.subheader("🗑️ Eliminar categoría")

    df_sel = data["categorias"].copy()

    if "estado" in df_sel.columns:
        df_sel = df_sel[df_sel["estado"] != "ELIMINADO"]

    if not df_sel.empty:

        df_sel["row_number"] = df_sel.index + 2
        df_sel["id"] = df_sel.index.astype(str)

        tipo = "catergoria"

        cat = st.selectbox(
            "Categoría",
            df_sel["id"],
            format_func=lambda x: df_sel.loc[int(x), "categoria"],
        key=f"select_{tipo}_eliminar"
        )

        if st.button("Eliminar categoría"):
            fila = int(df_sel.loc[int(cat), "row_number"])
            ws = sheet.worksheet("categorias")
            ws.update_cell(fila, 3, "ELIMINADO")

            st.success("Categoría eliminada")
            st.cache_data.clear()
            st.rerun()

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

    st.subheader("🗑️ Eliminar unidad")

    df_sel = data["unidades"].copy()

    if "estado" in df_sel.columns:
        df_sel = df_sel[df_sel["estado"] != "ELIMINADO"]

    if not df_sel.empty:

        df_sel["row_number"] = df_sel.index + 2
        df_sel["id"] = df_sel.index.astype(str)

        tipo = "unidad"

        uni = st.selectbox(
            "Unidad",
            df_sel["id"],
            format_func=lambda x: df_sel.loc[int(x), "unidad"],
            key=f"select_{tipo}_eliminar"
        )

        if st.button("Eliminar unidad"):
            fila = int(df_sel.loc[int(uni), "row_number"])
            ws = sheet.worksheet("unidades")
            ws.update_cell(fila, 2, "ELIMINADO")

            st.success("Unidad eliminada")
            st.cache_data.clear()
            st.rerun()

# ================================
# HISTORIAL
# ================================
elif menu == "📜 Historial":

    if not df_mov.empty:

        # 🔘 Mostrar eliminados
        mostrar_eliminados = st.checkbox("Mostrar movimientos eliminados", value=False)

        df = df_mov.copy()

        # 🔥 FILTRO ESTADO (solo visual)
        if "estado" in df.columns and not mostrar_eliminados:
            df = df[df["estado"] != "ELIMINADO"]

        # 🔥 NORMALIZAR
        df["producto"] = df["producto"].astype(str).str.strip().str.lower()

        # 🔥 ORDEN
        df = df.sort_values("fecha")

        resultados = []

        productos = df["producto"].unique()

        for prod in productos:

            df_p = df[df["producto"] == prod]

            stock = 0
            valor = 0
            cpp = 0

            for _, row in df_p.iterrows():

                cantidad = float(pd.to_numeric(row["cantidad"], errors="coerce") or 0)
                monto = float(pd.to_numeric(row["monto_total"], errors="coerce") or 0)
                accion = str(row["accion"]).strip().lower()
                estado = row.get("estado", "OK")

                # 🔥 ignorar eliminados en cálculo
                if estado == "ELIMINADO":
                    continue

                if accion == "ingreso":
                    stock += cantidad
                    valor += monto
                    cpp = valor / stock if stock > 0 else 0

                elif accion == "salida":
                    costo = cantidad * cpp

                    stock -= cantidad
                    valor -= costo

                    monto = costo  # 🔥 FIX CLAVE

                    cpp = valor / stock if stock > 0 else 0

                resultados.append({
                    "fecha": row["fecha"],
                    "producto": row["producto"],
                    "accion": row["accion"],
                    "cantidad": cantidad,
                    "monto_total": monto,
                    "cpp": cpp,
                    "nota": row["nota"],
                    "estado": estado
                })

        df_final = pd.DataFrame(resultados)

        # 💰 FORMATO MONEDA
        for col in ["monto_total", "cpp"]:
            df_final[col] = df_final[col].apply(
                lambda x: f"${x:,.0f}".replace(",", ".") if pd.notna(x) else ""
            )

        # 📊 TABLA
        st.dataframe(df_final, width="stretch")

        # ========================
        # 🗑️ GESTIÓN DE ELIMINACIÓN
        # ========================

        if "modo_eliminar" not in st.session_state:
            st.session_state["modo_eliminar"] = False

        if st.button("🗑️ Gestionar movimientos"):
            st.session_state["modo_eliminar"] = not st.session_state["modo_eliminar"]

        if st.session_state["modo_eliminar"]:

            st.divider()
            st.subheader("Eliminar movimiento")

            df_sel = df_mov.copy()

            if "estado" in df_sel.columns and not mostrar_eliminados:
                df_sel = df_sel[df_sel["estado"] != "ELIMINADO"]

            # 🔥 NO resetear índice
            df_sel["row_number"] = df_sel.index + 2
            df_sel["id_mov"] = df_sel.index.astype(str)

            # 🔥 mantener índice original para borrar bien
            df_sel["original_index"] = df_sel.index

            if not mostrar_eliminados:
                df_sel = df_sel[df_sel["estado"] != "ELIMINADO"]

            df_sel = df_sel.reset_index(drop=True)
            df_sel["id_mov"] = df_sel.index.astype(str)

            if "estado" in df_sel.columns:
                df_sel = df_sel[df_sel["estado"] != "ELIMINADO"]

            if df_sel.empty:
                st.info("No hay movimientos disponibles para eliminar")
                st.stop()

            df_sel["id_mov"] = df_sel.index.astype(str)


            def format_movimiento(row):
                monto = pd.to_numeric(row["monto_total"], errors="coerce")

                if pd.notna(monto):
                    monto_fmt = f"${monto:,.0f}".replace(",", ".")
                else:
                    monto_fmt = "$0"

                return (
                    f"{row['fecha']} | "
                    f"{row['producto']} | "
                    f"{row['accion']} | "
                    f"{row['cantidad']} | "
                    f"{monto_fmt} | "
                    f"{row['nota']} | "
                    f"{row['estado'] if 'estado' in row else 'OK'}"
                )


            def format_movimiento(row):
                monto = pd.to_numeric(row["monto_total"], errors="coerce")

                if pd.notna(monto):
                    monto_fmt = f"${monto:,.0f}".replace(",", ".")
                else:
                    monto_fmt = "$0"

                return (
                    f"{row['fecha']} | "
                    f"{row['producto']} | "
                    f"{row['accion']} | "
                    f"{row['cantidad']} | "
                    f"{monto_fmt} | "
                    f"{row['nota']} | "
                    f"{row['estado'] if 'estado' in row else 'OK'}"
                )

            mov = st.selectbox(
                "Movimiento",
                df_sel["id_mov"],
                format_func=lambda x: format_movimiento(df_sel.loc[int(x)])
            )

            st.warning("¿Seguro que quieres eliminar este movimiento?")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("✅ Sí, eliminar"):
                    row_number = int(df_sel.loc[int(mov), "row_number"])

                    ws = sheet.worksheet("movimientos")

                    ws.update_cell(row_number, 8, "ELIMINADO")

                    st.success("Movimiento eliminado")
                    st.cache_data.clear()
                    st.rerun()

            with col2:
                if st.button("❌ Cancelar"):
                    st.info("Operación cancelada")