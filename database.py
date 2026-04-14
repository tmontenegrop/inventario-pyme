import gspread


def conectar_sheet(credentials, sheet_id):
    gc = gspread.authorize(credentials)
    return gc.open_by_key(sheet_id)