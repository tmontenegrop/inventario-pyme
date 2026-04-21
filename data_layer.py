import pandas as pd
from datetime import datetime


# ================================
# 🔧 HELPERS
# ================================
_sheet_ws_cache = {}

def _get_ws(sheet, name):
    key = f"{sheet.id}_{name}"

    if key not in _sheet_ws_cache:
        _sheet_ws_cache[key] = sheet.worksheet(name)

    return _sheet_ws_cache[key]

def _safe_get_df(sheet, nombre_hoja):
    try:
        ws = _get_ws(sheet, nombre_hoja)
        values = ws.get_all_values()

        if len(values) <= 1:
            return pd.DataFrame()

        df = pd.DataFrame(values[1:], columns=values[0])

        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
            .str.replace(" ", "_")
        )

        return df

    except Exception:
        return pd.DataFrame()


def _to_numeric(df, cols):
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ================================
# 📊 LECTURA
# ================================

def get_all_data(sheet):
    productos = _safe_get_df(sheet, "productos")
    movimientos = _safe_get_df(sheet, "movimientos")
    categorias = _safe_get_df(sheet, "categorias")
    unidades = _safe_get_df(sheet, "unidades")

    return {
        "productos": productos,
        "movimientos": movimientos,
        "categorias": categorias,
        "unidades": unidades
    }

def get_productos(sheet):
    return get_all_data(sheet)["productos"]


def get_movimientos(sheet):
    return get_all_data(sheet)["movimientos"]


def get_categorias(sheet):
    return get_all_data(sheet)["categorias"]


def get_unidades(sheet):
    return get_all_data(sheet)["unidades"]


# ================================
# 📦 PRODUCTOS
# ================================

def crear_producto(sheet, nombre, categoria, unidad, stock_minimo):
    if not nombre:
        return False, "Nombre requerido"

    df = _safe_get_df(sheet, "productos")

    nombre_clean = str(nombre).strip().lower()

    # 🔥 VALIDAR SOLO SI EXISTE LA COLUMNA
    if not df.empty and "nombre" in df.columns:
        df["nombre"] = df["nombre"].astype(str).str.strip().str.lower()

        if nombre_clean in df["nombre"].values:
            return False, "El producto ya existe"

    ws = _get_ws(sheet, "productos")

    # ID simple incremental seguro
    nuevo_id = len(df) + 1 if not df.empty else 1

    ws.append_row([
        nuevo_id,
        nombre,
        categoria,
        unidad,
        stock_minimo,
        "OK"
    ])

    return True, "Producto creado"


# ================================
# 🏷️ CATEGORÍAS
# ================================

def crear_categoria(sheet, nombre, emoji):
    if not nombre:
        return False, "Nombre requerido"

    ws = _get_ws(sheet, "categorias")

    ws.append_row([
        nombre,
        emoji,
        "OK"
    ])

    return True, "Categoría creada"


# ================================
# 📏 UNIDADES
# ================================

def crear_unidad(sheet, nombre):
    if not nombre:
        return False, "Nombre requerido"

    ws = _get_ws(sheet, "unidades")

    ws.append_row([
        nombre,
        "OK"
    ])

    return True, "Unidad creada"


# ================================
# 🔄 MOVIMIENTOS
# ================================

def crear_movimiento(sheet, producto, cantidad, tipo, nota, monto_total=0):
    if not producto:
        return False, "Producto requerido"

    if cantidad <= 0:
        return False, "Cantidad inválida"

    ws = _get_ws(sheet, "movimientos")

    df_prod = _safe_get_df(sheet, "productos")
    row = df_prod[df_prod["nombre"] == producto]

    if row.empty:
        return False, "Producto no encontrado"

    id_producto = row.iloc[0]["id"]

    # 🔥 ORDEN EXACTO DE LA PLANTILLA
    ws.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M"),  # Fecha
        id_producto,                                # ID_Producto
        producto,                                   # Producto
        float(cantidad),                            # Cantidad
        tipo,                                       # Accion
        nota,                                       # Nota
        float(monto_total),                          # Monto Total
        "OK"                                        # Estado
    ])

    return True, "Movimiento registrado"


# ================================
# 📈 STOCK
# ================================

def calcular_estado_producto(df_mov, producto):
    if df_mov.empty:
        return 0, 0, 0

    df = df_mov.copy()

    # 🔥 ignorar eliminados
    if "estado" in df.columns:
        df = df[df["estado"] != "ELIMINADO"]

    # 🔥 normalizar
    df["producto"] = df["producto"].astype(str).str.strip().str.lower()
    producto = str(producto).strip().lower()

    df = df[df["producto"] == producto]

    if df.empty:
        return 0, 0, 0

    # 🔥 ordenar por fecha
    df = df.sort_values("fecha")

    stock = 0
    valor = 0
    cpp = 0

    for _, row in df.iterrows():

        cantidad = float(pd.to_numeric(row["cantidad"], errors="coerce") or 0)
        monto = float(pd.to_numeric(row["monto_total"], errors="coerce") or 0)
        accion = str(row["accion"]).strip().lower()

        if accion == "ingreso":
            stock += cantidad
            valor += monto

            cpp = valor / stock if stock > 0 else 0

        elif accion == "salida":
            if stock <= 0:
                continue

            costo = cantidad * cpp

            stock -= cantidad
            valor -= costo

            cpp = valor / stock if stock > 0 else 0

    return stock, valor, cpp