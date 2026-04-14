import gspread
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ---------------------------
# CONEXIÓN GSPREAD DESDE OAUTH
# ---------------------------
def get_gspread_client(credentials):
    return gspread.authorize(credentials)


# ---------------------------
# CREAR GOOGLE SHEET
# ---------------------------
def crear_google_sheet(service, nombre_cliente):
    try:
        file_metadata = {
            'name': f"{nombre_cliente} - Inventario",
            'mimeType': 'application/vnd.google-apps.spreadsheet'
        }

        file = service.files().create(
            body=file_metadata,
            fields='id'
        ).execute()

        return file.get('id')

    except HttpError as error:
        print(f"Error creando Google Sheet: {error}")
        return None


# ---------------------------
# CREAR HOJA SI NO EXISTE
# ---------------------------
def crear_hoja_si_no_existe(spreadsheet, nombre_hoja):
    hojas = [ws.title for ws in spreadsheet.worksheets()]

    if nombre_hoja not in hojas:
        spreadsheet.add_worksheet(title=nombre_hoja, rows="1000", cols="20")
        return True

    return False


# ---------------------------
# AGREGAR HEADERS
# ---------------------------
def agregar_headers(worksheet, headers):
    existing = worksheet.get_all_values()

    if not existing:  # solo si está vacía
        worksheet.append_row(headers)


# ---------------------------
# DATOS INICIALES
# ---------------------------
def insertar_datos_iniciales(spreadsheet):
    try:
        categorias = spreadsheet.worksheet("categorias")
        unidades = spreadsheet.worksheet("unidades")

        if len(categorias.get_all_values()) <= 1:
            categorias.append_rows([
                ["Insumos", "📦"],
                ["Bebidas", "🥤"],
                ["Limpieza", "🧼"]
            ])

        if len(unidades.get_all_values()) <= 1:
            unidades.append_rows([
                ["kg"],
                ["lt"],
                ["un"]
            ])

    except Exception as e:
        print("Error insertando datos iniciales:", e)


# ---------------------------
# INICIALIZAR ESTRUCTURA
# ---------------------------
def inicializar_estructura(sheet_id, credentials):
    import time

    gc = get_gspread_client(credentials)
    spreadsheet = gc.open_by_key(sheet_id)

    estructura = {
        "productos": ["Nombre", "Categoría", "Unidad", "Stock Min"],
        "movimientos": ["Fecha", "Producto", "Acción", "Cantidad", "Monto Total", "Nota"],
        "categorias": ["Nombre", "Emoji"],
        "unidades": ["Nombre"]
    }

    # ⏳ Esperar a que Google cree bien el archivo
    time.sleep(2)

    hojas = spreadsheet.worksheets()

    # 🔍 BUSCAR hoja default REAL
    hoja_default = None

    for ws in hojas:
        if ws.title.strip().lower() in ["hoja1", "hoja 1", "sheet1", "sheet 1","Hoja 1", "Hoja1"]:
            hoja_default = ws
            break

    # 🔥 SI EXISTE → USARLA COMO PRODUCTOS
    if hoja_default:
        try:
            hoja_default.update_title("productos")
        except Exception as e:
            print("Error renombrando:", e)

        agregar_headers(hoja_default, estructura["productos"])

    # 🔄 refrescar estado
    time.sleep(1)
    hojas_existentes = [ws.title for ws in spreadsheet.worksheets()]

    # 🧱 crear resto de hojas
    for nombre_hoja, headers in estructura.items():

        if nombre_hoja == "productos":
            continue

        if nombre_hoja not in hojas_existentes:
            spreadsheet.add_worksheet(
                title=nombre_hoja,
                rows="1000",
                cols="20"
            )

        ws = spreadsheet.worksheet(nombre_hoja)
        agregar_headers(ws, headers)

    insertar_datos_iniciales(spreadsheet)

    return True
# ---------------------------
# FUNCIÓN PRINCIPAL (ORQUESTADOR)
# ---------------------------
PARENT_FOLDER_ID = "1azW6BUDY7OVn4sn4c6DPUxtBI1GASn2n"


def crear_entorno_cliente(service, credentials, nombre_cliente):
    # 📁 Crear carpeta del cliente
    folder_id = crear_carpeta_cliente(
        service,
        nombre_cliente,
        PARENT_FOLDER_ID
    )

    # 📄 Crear Sheet dentro de la carpeta
    sheet_id = crear_google_sheet(
        service,
        nombre_cliente,
        folder_id
    )

    if not sheet_id:
        return None

    # 🧱 Inicializar estructura
    inicializar_estructura(sheet_id, credentials)

    return sheet_id
def crear_carpeta_cliente(service, nombre_cliente, parent_folder_id):
    file_metadata = {
        'name': nombre_cliente,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id]
    }

    folder = service.files().create(
        body=file_metadata,
        fields='id'
    ).execute()

    return folder.get('id')

def crear_google_sheet(service, nombre_cliente, folder_id):
    file_metadata = {
        'name': f"{nombre_cliente} - Inventario",
        'mimeType': 'application/vnd.google-apps.spreadsheet',
        'parents': [folder_id]  # 🔥 AQUÍ
    }

    file = service.files().create(
        body=file_metadata,
        fields='id'
    ).execute()

    return file.get('id')