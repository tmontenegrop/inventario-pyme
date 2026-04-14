def preparar_credenciales(df_maestro):
    import streamlit_authenticator as stauth
    credentials = {"usernames": {}}

    for _, row in df_maestro.iterrows():
        credentials["usernames"][str(row['usuario'])] = {
            "name": str(row['nombre']),
            "password": str(row['password'])  # Ya debe venir hasheada de la base
        }
    return credentials