from datetime import date, datetime
import pandas as pd
import sqlite3
import streamlit as st
import base64


def aplicar_fundo_local(caminho_imagem):
    try:
        with open(caminho_imagem, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()

        st.markdown(
            f"""
            <style>
            /* Aplicar marca de agua suave sobre el fondo */
            [data-testid="stAppViewContainer"] {{
                background-image: linear-gradient(rgba(155, 255, 255, 0.92), rgba(255, 255, 255, 0.92)), 
                                  url("data:image/png;base64,{encoded}");
                background-size: contain;
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }}

            /* Quitar fondos blancos por defecto */
            [data-testid="stHeader"], [data-testid="stSidebar"] {{
                background-color: rgba(255, 255, 255, 0.10) !important;
            }}

            /* Contenedor principal con fondo limpio */
            .main .block-container {{
                background-color: rgba(255, 255, 255, 0.10) !important;
                padding: 2rem;
                border-radius: 12px;
                margin-top: 1rem;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            }}

            /* --- TAMAÑO Y GROSOR DE LAS PESTAÑAS (TABS) --- */
            button[data-baseweb="tab"] p, 
            div[data-baseweb="tab"] p,
            button[data-baseweb="tab"] div {{
                font-size: 10px !important;    /* Tamaño del texto de las pestañas */
                font-weight: 800 !important;   /* Grosor de la letra */
                color: #1e293b !important;
            }}

            button[data-baseweb="tab"] {{
                padding: 10px 16px !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        pass


# Llamada a la función con el nombre exacto de tu archivo de imagen
aplicar_fundo_local("LogoC.png")

# Importación segura de Firestore
try:
    from google.cloud import firestore

    FIRESTORE_DISPONIBLE = True
except ImportError:
    FIRESTORE_DISPONIBLE = False

# ==========================================
# CONSTANTES Y CONFIGURACIÓN GLOBAL
# ==========================================
CLAVE_ADMIN = "12345amor"  # Clave global para acciones sensibles


def obtener_conexion():
    """Conexión estándar a SQLite local."""
    return sqlite3.connect("inventario.db")


def obtener_conexion_db():
    """Conexión a Firestore en Cloud (si está configurado)."""
    if FIRESTORE_DISPONIBLE and "gcp_service_account" in st.secrets:
        try:
            return firestore.Client.from_service_account_info(
                dict(st.secrets["gcp_service_account"])
            )
        except Exception:
            return None
    return None


# ==========================================
# 1. CONTROL DE BASE DE DATOS Y PERSISTENCIA
# ==========================================
def init_db():
    conn = obtener_conexion()
    cursor = conn.cursor()

    # Productos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_barras TEXT,
            nombre TEXT NOT NULL,
            categoria TEXT,
            marca TEXT,
            precio_costo INTEGER NOT NULL,
            ganancia_porcentaje INTEGER NOT NULL,
            precio_venta INTEGER NOT NULL,
            stock INTEGER NOT NULL,
            descripcion TEXT
        )
    """)

    # Categorías y Marcas
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS categorias (id INTEGER PRIMARY KEY"
        " AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS marcas (id INTEGER PRIMARY KEY"
        " AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL)"
    )

    # Clientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            ci TEXT NOT NULL,
            telefono TEXT,
            ciudad TEXT
        )
    """)

    # Ventas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            producto_id TEXT NOT NULL,
            producto_nombre TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            precio_unitario INTEGER NOT NULL,
            total INTEGER NOT NULL,
            tipo_venta TEXT DEFAULT 'Contado',
            metodo_pago TEXT NOT NULL,
            cliente_nombre TEXT,
            estado_pago TEXT DEFAULT 'Pagado'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            cliente_nombre TEXT NOT NULL,
            monto INTEGER NOT NULL,
            metodo_pago TEXT NOT NULL
        )
    """)

    # Salidas Caja y Cierres Históricos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salidas_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            motivo TEXT NOT NULL,
            monto INTEGER NOT NULL,
            metodo_pago TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cierres_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT UNIQUE NOT NULL,
            saldo_inicial INTEGER NOT NULL,
            ingresos INTEGER NOT NULL,
            egresos INTEGER NOT NULL,
            saldo_final INTEGER NOT NULL
        )
    """)

    # Proveedores y Compras
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ruc_ci TEXT,
            telefono TEXT,
            ciudad TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            proveedor_nombre TEXT NOT NULL,
            concepto TEXT NOT NULL,
            monto_total INTEGER NOT NULL,
            monto_pagado INTEGER DEFAULT 0,
            tipo_compra TEXT NOT NULL,
            metodo_pago TEXT NOT NULL,
            estado_pago TEXT DEFAULT 'Pagado'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            compra_id INTEGER NOT NULL,
            proveedor_nombre TEXT NOT NULL,
            monto INTEGER NOT NULL,
            metodo_pago TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

def obtener_saldo_inicial_dia(fecha_hoy_str):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("cierres_caja").stream()
        registros = [
            doc.to_dict()
            for doc in docs
            if doc.to_dict().get("fecha", "") < fecha_hoy_str
        ]
        if registros:
            registros_ordenados = sorted(
                registros, key=lambda x: x["fecha"], reverse=True
            )
            return int(registros_ordenados[0].get("saldo_final", 0))
        
        cierre_hoy = db_cloud.collection("cierres_caja").document(fecha_hoy_str).get()
        if cierre_hoy.exists:
            return int(cierre_hoy.to_dict().get("saldo_inicial", 0))
            
        return 0
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT saldo_final FROM cierres_caja WHERE fecha < ? ORDER BY fecha DESC LIMIT 1",
            (fecha_hoy_str,),
        )
        row = cursor.fetchone()
        if row:
            conn.close()
            return row[0]
        
        cursor.execute(
            "SELECT saldo_inicial FROM cierres_caja WHERE fecha = ?",
            (fecha_hoy_str,),
        )
        row_hoy = cursor.fetchone()
        conn.close()
        return row_hoy[0] if row_hoy else 0

def registrar_cierre_diario(
    fecha_str, saldo_inicial, ingresos, egresos, saldo_final
):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("cierres_caja").document(fecha_str).set({
            "fecha": fecha_str,
            "saldo_inicial": int(saldo_inicial),
            "ingresos": int(ingresos),
            "egresos": int(egresos),
            "saldo_final": int(saldo_final),
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO cierres_caja (fecha, saldo_inicial, ingresos, egresos, saldo_final)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fecha) DO UPDATE SET
                saldo_inicial = excluded.saldo_inicial, ingresos = excluded.ingresos,
                egresos = excluded.egresos, saldo_final = excluded.saldo_final
        """,
            (
                fecha_str,
                int(saldo_inicial),
                int(ingresos),
                int(egresos),
                int(saldo_final),
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


@st.cache_data(ttl=30)
def obtener_historico_cierres():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("cierres_caja").stream()
        lista = [doc.to_dict() for doc in docs]
        if not lista:
            return pd.DataFrame(
                columns=[
                    "fecha",
                    "saldo_inicial",
                    "ingresos",
                    "egresos",
                    "saldo_final",
                ]
            )
        df = pd.DataFrame(lista)
        return df.sort_values(by="fecha", ascending=False)
    else:
        conn = obtener_conexion()
        df = pd.read_sql_query(
            "SELECT * FROM cierres_caja ORDER BY fecha DESC", conn
        )
        conn.close()
        return df


def actualizar_cierre_caja(fecha_str, nuevo_saldo_final):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("cierres_caja").document(fecha_str).update(
            {"saldo_final": int(nuevo_saldo_final)}
        )
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cierres_caja SET saldo_final = ? WHERE fecha = ?",
            (int(nuevo_saldo_final), fecha_str),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


def limpiar_historico_cierres():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("cierres_caja").stream()
        for doc in docs:
            db_cloud.collection("cierres_caja").document(doc.id).delete()
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cierres_caja")
        conn.commit()
        conn.close()
    st.cache_data.clear()


# --- FUNCIONES CATEGORÍAS Y MARCAS ---
@st.cache_data(ttl=30)
def obtener_categorias():
    db_cloud = obtener_conexion_db()
    cat_default = [
        "Perfumes",
        "Cosméticos",
        "Cuidado Personal",
        "Crochet",
        "Otros",
    ]
    if db_cloud is not None:
        docs = db_cloud.collection("categorias").stream()
        lista = [
            doc.to_dict().get("nombre")
            for doc in docs
            if doc.to_dict().get("nombre")
        ]
        return sorted(list(set(lista))) if lista else cat_default
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM categorias ORDER BY nombre ASC")
        filas = cursor.fetchall()
        conn.close()
        return [f[0] for f in filas] if filas else cat_default


def registrar_categoria(nombre_cat):
    db_cloud = obtener_conexion_db()
    nombre_cat = nombre_cat.strip()
    if db_cloud is not None:
        if nombre_cat not in obtener_categorias():
            db_cloud.collection("categorias").add({"nombre": nombre_cat})
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO categorias (nombre) VALUES (?)", (nombre_cat,)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()
    st.cache_data.clear()


def eliminar_categoria(nombre_cat):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = (
            db_cloud.collection("categorias")
            .where("nombre", "==", nombre_cat)
            .stream()
        )
        for doc in docs:
            db_cloud.collection("categorias").document(doc.id).delete()
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categorias WHERE nombre = ?", (nombre_cat,))
        conn.commit()
        conn.close()
    st.cache_data.clear()


@st.cache_data(ttl=30)
def obtener_marcas():
    db_cloud = obtener_conexion_db()
    marcas_default = ["Natura", "O Boticário", "Eudora", "Artesanal / Sin Marca"]
    if db_cloud is not None:
        docs = db_cloud.collection("marcas").stream()
        lista = [
            doc.to_dict().get("nombre")
            for doc in docs
            if doc.to_dict().get("nombre")
        ]
        return sorted(list(set(lista))) if lista else marcas_default
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM marcas ORDER BY nombre ASC")
        filas = cursor.fetchall()
        conn.close()
        return [f[0] for f in filas] if filas else marcas_default


def registrar_marca(nombre_marca):
    db_cloud = obtener_conexion_db()
    nombre_marca = nombre_marca.strip()
    if db_cloud is not None:
        if nombre_marca not in obtener_marcas():
            db_cloud.collection("marcas").add({"nombre": nombre_marca})
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO marcas (nombre) VALUES (?)", (nombre_marca,)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()
    st.cache_data.clear()


def eliminar_marca(nombre_marca):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = (
            db_cloud.collection("marcas")
            .where("nombre", "==", nombre_marca)
            .stream()
        )
        for doc in docs:
            db_cloud.collection("marcas").document(doc.id).delete()
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM marcas WHERE nombre = ?", (nombre_marca,))
        conn.commit()
        conn.close()
    st.cache_data.clear()

# --- FUNCIONES CLIENTES ---
def registrar_cliente(nombre, apellido, ci, telefono, ciudad):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("clientes").add({
            "nombre": nombre.strip(),
            "apellido": apellido.strip(),
            "ci": ci.strip(),
            "telefono": telefono.strip(),
            "ciudad": ciudad.strip(),
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO clientes (nombre, apellido, ci, telefono, ciudad)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                nombre.strip(),
                apellido.strip(),
                ci.strip(),
                telefono.strip(),
                ciudad.strip(),
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


def actualizar_cliente(id_cliente, nombre, apellido, ci, telefono, ciudad):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("clientes").document(str(id_cliente)).update({
            "nombre": nombre.strip(),
            "apellido": apellido.strip(),
            "ci": ci.strip(),
            "telefono": telefono.strip(),
            "ciudad": ciudad.strip(),
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE clientes
            SET nombre = ?, apellido = ?, ci = ?, telefono = ?, ciudad = ?
            WHERE id = ?
        """,
            (
                nombre.strip(),
                apellido.strip(),
                ci.strip(),
                telefono.strip(),
                ciudad.strip(),
                int(id_cliente) if str(id_cliente).isdigit() else id_cliente,
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


def eliminar_cliente(id_cliente):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("clientes").document(str(id_cliente)).delete()
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM clientes WHERE id = ?",
            (int(id_cliente) if str(id_cliente).isdigit() else id_cliente,),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


@st.cache_data(ttl=30)
def obtener_clientes():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("clientes").stream()
        lista = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            lista.append(d)
        return (
            pd.DataFrame(lista)
            if lista
            else pd.DataFrame(
                columns=["id", "nombre", "apellido", "ci", "telefono", "ciudad"]
            )
        )
    else:
        conn = obtener_conexion()
        df = pd.read_sql_query("SELECT * FROM clientes", conn)
        conn.close()
        return df

# --- FUNCIONES PROVEEDORES Y COMPRAS ---
def registrar_proveedor(nombre, ruc_ci, telefono, ciudad):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("proveedores").add({
            "nombre": nombre.strip(),
            "ruc_ci": ruc_ci.strip(),
            "telefono": telefono.strip(),
            "ciudad": ciudad.strip(),
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO proveedores (nombre, ruc_ci, telefono, ciudad) VALUES"
            " (?, ?, ?, ?)",
            (nombre.strip(), ruc_ci.strip(), telefono.strip(), ciudad.strip()),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


@st.cache_data(ttl=30)
def obtener_proveedores():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("proveedores").stream()
        lista = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            lista.append(d)
        return (
            pd.DataFrame(lista)
            if lista
            else pd.DataFrame(
                columns=["id", "nombre", "ruc_ci", "telefono", "ciudad"]
            )
        )
    else:
        conn = obtener_conexion()
        df = pd.read_sql_query("SELECT * FROM proveedores", conn)
        conn.close()
        return df


def actualizar_proveedor(id_prov, nombre, ruc_ci, telefono, ciudad):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("proveedores").document(str(id_prov)).update({
            "nombre": nombre.strip(),
            "ruc_ci": ruc_ci.strip(),
            "telefono": telefono.strip(),
            "ciudad": ciudad.strip(),
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE proveedores
            SET nombre = ?, ruc_ci = ?, telefono = ?, ciudad = ?
            WHERE id = ?
        """,
            (
                nombre.strip(),
                ruc_ci.strip(),
                telefono.strip(),
                ciudad.strip(),
                int(id_prov) if str(id_prov).isdigit() else id_prov,
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


def eliminar_proveedor(id_prov):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("proveedores").document(str(id_prov)).delete()
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM proveedores WHERE id = ?",
            (int(id_prov) if str(id_prov).isdigit() else id_prov,),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


def registrar_compra_proveedor(
    proveedor_nombre=None,
    concepto="",
    monto_total=0,
    tipo_compra="Contado",
    metodo_pago="Efectivo",
    estado_pago=None,
    proveedor=None,
):
    if proveedor_nombre is None and proveedor is not None:
        proveedor_nombre = proveedor

    proveedor_nombre = str(proveedor_nombre) if proveedor_nombre else ""
    concepto = str(concepto) if concepto else ""
    tipo_compra = str(tipo_compra) if tipo_compra else "Contado"
    metodo_pago = str(metodo_pago) if metodo_pago else "Efectivo"

    try:
        monto_total = int(float(monto_total))
    except (ValueError, TypeError):
        monto_total = 0

    if not estado_pago:
        estado_pago = "Pendiente" if tipo_compra == "Crédito" else "Pagado"

    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_cloud = obtener_conexion_db()

    if db_cloud is not None:
        db_cloud.collection("compras_proveedores").add({
            "fecha_hora": fecha_hora,
            "proveedor_nombre": proveedor_nombre,
            "concepto": concepto,
            "monto_total": monto_total,
            "monto_pagado": monto_total if estado_pago == "Pagado" else 0,
            "tipo_compra": tipo_compra,
            "metodo_pago": metodo_pago,
            "estado_pago": estado_pago,
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO compras_proveedores (
                fecha_hora, proveedor_nombre, concepto, monto_total, monto_pagado, tipo_compra, metodo_pago, estado_pago
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                fecha_hora,
                proveedor_nombre,
                concepto,
                monto_total,
                monto_total if estado_pago == "Pagado" else 0,
                tipo_compra,
                metodo_pago,
                estado_pago,
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


@st.cache_data(ttl=30)
def obtener_compras_proveedores():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("compras_proveedores").stream()
        lista = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            lista.append(d)
        return (
            pd.DataFrame(lista)
            if lista
            else pd.DataFrame(
                columns=[
                    "id",
                    "fecha_hora",
                    "proveedor_nombre",
                    "concepto",
                    "monto_total",
                    "monto_pagado",
                    "tipo_compra",
                    "metodo_pago",
                    "estado_pago",
                ]
            )
        )
    else:
        conn = obtener_conexion()
        df = pd.read_sql_query("SELECT * FROM compras_proveedores", conn)
        conn.close()
        return df


def actualizar_pago_compra_proveedor(
    id_compra, nuevo_monto_pagado, nuevo_estado, **kwargs
):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("compras_proveedores").document(
            str(id_compra)
        ).update({
            "monto_pagado": int(nuevo_monto_pagado),
            "estado_pago": str(nuevo_estado),
        })
        st.cache_data.clear()
        return True
    else:
        try:
            conn = obtener_conexion()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE compras_proveedores
                SET monto_pagado = ?, 
                    estado_pago = ?
                WHERE id = ?
            """,
                (
                    int(nuevo_monto_pagado),
                    str(nuevo_estado),
                    (
                        int(id_compra)
                        if str(id_compra).isdigit()
                        else id_compra
                    ),
                ),
            )
            conn.commit()
            conn.close()
            st.cache_data.clear()
            return True
        except Exception as e:
            st.error(f"Error al actualizar el pago: {e}")
            return False


def actualizar_compra_proveedor(
    id_compra, concepto, monto_total, monto_pagado, estado_pago
):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("compras_proveedores").document(
            str(id_compra)
        ).update({
            "concepto": concepto.strip(),
            "monto_total": int(monto_total),
            "monto_pagado": int(monto_pagado),
            "estado_pago": str(estado_pago),
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE compras_proveedores
            SET concepto = ?, monto_total = ?, monto_pagado = ?, estado_pago = ?
            WHERE id = ?
        """,
            (
                concepto.strip(),
                int(monto_total),
                int(monto_pagado),
                str(estado_pago),
                int(id_compra) if str(id_compra).isdigit() else id_compra,
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


def eliminar_compra_proveedor(id_compra):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("compras_proveedores").document(
            str(id_compra)
        ).delete()
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM compras_proveedores WHERE id = ?",
            (int(id_compra) if str(id_compra).isdigit() else id_compra,),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


# --- FUNCIONES PRODUCTOS ---
def registrar_producto(
    codigo_barras,
    nombre,
    categoria,
    marca,
    precio_costo,
    ganancia_porcentaje,
    precio_venta,
    stock,
    descripcion,
):
    db_cloud = obtener_conexion_db()
    cod_clean = str(codigo_barras).strip()
    if db_cloud is not None:
        db_cloud.collection("productos").add({
            "codigo_barras": cod_clean,
            "nombre": nombre,
            "categoria": categoria,
            "marca": marca,
            "precio_costo": int(precio_costo),
            "ganancia_porcentaje": int(ganancia_porcentaje),
            "precio_venta": int(precio_venta),
            "stock": int(stock),
            "descripcion": descripcion,
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO productos (codigo_barras, nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                cod_clean,
                nombre,
                categoria,
                marca,
                int(precio_costo),
                int(ganancia_porcentaje),
                int(precio_venta),
                int(stock),
                descripcion,
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


def actualizar_producto(
    id_prod,
    codigo_barras,
    nombre,
    categoria,
    marca,
    precio_costo,
    ganancia_porcentaje,
    precio_venta,
    stock,
    descripcion,
):
    db_cloud = obtener_conexion_db()
    cod_clean = str(codigo_barras).strip()
    if db_cloud is not None:
        db_cloud.collection("productos").document(str(id_prod)).update({
            "codigo_barras": cod_clean,
            "nombre": nombre,
            "categoria": categoria,
            "marca": marca,
            "precio_costo": int(precio_costo),
            "ganancia_porcentaje": int(ganancia_porcentaje),
            "precio_venta": int(precio_venta),
            "stock": int(stock),
            "descripcion": descripcion,
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE productos
            SET codigo_barras = ?, nombre = ?, categoria = ?, marca = ?, precio_costo = ?, ganancia_porcentaje = ?, precio_venta = ?, stock = ?, descripcion = ?
            WHERE id = ?
        """,
            (
                cod_clean,
                nombre,
                categoria,
                marca,
                int(precio_costo),
                int(ganancia_porcentaje),
                int(precio_venta),
                int(stock),
                descripcion,
                int(id_prod) if str(id_prod).isdigit() else id_prod,
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


def eliminar_producto(id_prod):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("productos").document(str(id_prod)).delete()
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM productos WHERE id = ?",
            (int(id_prod) if str(id_prod).isdigit() else id_prod,),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


@st.cache_data(ttl=30)
def obtener_productos():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("productos").stream()
        lista = []
        for doc in docs:
            datos = doc.to_dict()
            datos["id"] = doc.id
            lista.append(datos)
        if not lista:
            return pd.DataFrame(
                columns=[
                    "id",
                    "codigo_barras",
                    "nombre",
                    "marca",
                    "categoria",
                    "precio_costo",
                    "ganancia_porcentaje",
                    "precio_venta",
                    "stock",
                    "descripcion",
                ]
            )
        df = pd.DataFrame(lista)
    else:
        conn = obtener_conexion()
        df = pd.read_sql_query("SELECT * FROM productos", conn)
        conn.close()

    if "codigo_barras" not in df.columns:
        df["codigo_barras"] = ""
    if "marca" not in df.columns:
        df["marca"] = "Sin Marca"
    return df


# --- FUNCIONES VENTAS ---
def registrar_venta(
    producto_id,
    producto_nombre,
    cantidad,
    precio_unitario,
    total,
    tipo_venta,
    metodo_pago,
    cliente_nombre="Cliente Ocasional",
):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    estado_pago = "Pendiente" if tipo_venta == "Crédito" else "Pagado"

    if db_cloud is not None:
        db_cloud.collection("ventas").add({
            "fecha_hora": fecha_hora,
            "producto_id": str(producto_id),
            "producto_nombre": producto_nombre,
            "cantidad": int(cantidad),
            "precio_unitario": int(precio_unitario),
            "total": int(total),
            "tipo_venta": tipo_venta,
            "metodo_pago": metodo_pago,
            "cliente_nombre": cliente_nombre,
            "estado_pago": estado_pago,
        })
        doc_ref = db_cloud.collection("productos").document(str(producto_id))
        doc = doc_ref.get()
        if doc.exists:
            stock_actual = doc.to_dict().get("stock", 0)
            doc_ref.update({"stock": max(0, stock_actual - int(cantidad))})
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ventas (fecha_hora, producto_id, producto_nombre, cantidad, precio_unitario, total, tipo_venta, metodo_pago, cliente_nombre, estado_pago)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                fecha_hora,
                str(producto_id),
                producto_nombre,
                int(cantidad),
                int(precio_unitario),
                int(total),
                tipo_venta,
                metodo_pago,
                cliente_nombre,
                estado_pago,
            ),
        )
        cursor.execute(
            "UPDATE productos SET stock = stock - ? WHERE id = ?",
            (
                int(cantidad),
                (
                    int(producto_id)
                    if str(producto_id).isdigit()
                    else producto_id
                ),
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


@st.cache_data(ttl=30)
def obtener_ventas():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("ventas").stream()
        lista = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            lista.append(d)
        if not lista:
            return pd.DataFrame(
                columns=[
                    "id",
                    "fecha_hora",
                    "producto_id",
                    "producto_nombre",
                    "cantidad",
                    "precio_unitario",
                    "total",
                    "tipo_venta",
                    "metodo_pago",
                    "cliente_nombre",
                    "estado_pago",
                ]
            )
        df = pd.DataFrame(lista)
    else:
        conn = obtener_conexion()
        df = pd.read_sql_query("SELECT * FROM ventas", conn)
        conn.close()

    if "tipo_venta" not in df.columns:
        df["tipo_venta"] = "Contado"
    if "estado_pago" not in df.columns:
        df["estado_pago"] = "Pagado"
    if "cliente_nombre" not in df.columns:
        df["cliente_nombre"] = "Cliente Ocasional"
    return df


# --- FUNCIONES SALIDAS CAJA ---
def registrar_salida_caja(motivo="", monto=0, metodo="Efectivo", **kwargs):
    metodo_pago = kwargs.get("metodo_pago", metodo)
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if db_cloud is not None:
        db_cloud.collection("salidas_caja").add({
            "fecha_hora": fecha_hora,
            "motivo": motivo,
            "monto": int(monto),
            "metodo_pago": metodo_pago,
        })
        st.cache_data.clear()
        return True
    else:
        try:
            conn = obtener_conexion()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO salidas_caja (fecha_hora, motivo, monto,"
                " metodo_pago) VALUES (?, ?, ?, ?)",
                (fecha_hora, motivo, int(monto), metodo_pago),
            )
            conn.commit()
            conn.close()
            st.cache_data.clear()
            return True
        except Exception as e:
            st.error(f"Error al registrar salida de caja: {e}")
            return False


@st.cache_data(ttl=30)
def obtener_salidas_caja():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("salidas_caja").stream()
        lista = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            lista.append(d)
        if not lista:
            return pd.DataFrame(
                columns=["id", "fecha_hora", "motivo", "monto", "metodo_pago"]
            )
        df = pd.DataFrame(lista)
        return df.sort_values(by="fecha_hora", ascending=False)
    else:
        conn = obtener_conexion()
        df = pd.read_sql_query(
            "SELECT * FROM salidas_caja ORDER BY id DESC", conn
        )
        conn.close()
        return df


def actualizar_salida_caja(id_salida, motivo, monto, metodo_pago):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("salidas_caja").document(str(id_salida)).update({
            "motivo": motivo,
            "monto": int(monto),
            "metodo_pago": metodo_pago,
        })
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE salidas_caja
            SET motivo = ?, monto = ?, metodo_pago = ?
            WHERE id = ?
        """,
            (
                motivo,
                int(monto),
                metodo_pago,
                int(id_salida) if str(id_salida).isdigit() else id_salida,
            ),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


def eliminar_salida_caja(id_salida):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("salidas_caja").document(str(id_salida)).delete()
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM salidas_caja WHERE id = ?",
            (int(id_salida) if str(id_salida).isdigit() else id_salida,),
        )
        conn.commit()
        conn.close()
    st.cache_data.clear()


# Inicializar DB local
init_db()


def formatear_gs(valor):
    try:
        return f"Gs. {int(valor):,}".replace(",", ".")
    except Exception:
        return f"Gs. {valor}"


# ==========================================
# CONFIGURACIÓN STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Sistema Encanto - Stock & Ventas", layout="wide", page_icon="📦"
)

st.markdown(
    """
    <style>
    .stApp { background-color: #F8F9FA !important; }
    .main-title, h1, h2, h3 { color: #6B46C1 !important; font-weight: 800 !important; font-size: 30px !important; }
    p, span, label, div { color: #1A202C !important; }
    button[data-baseweb="tab"] p { color: #2D3748 !important; font-weight: 600 !important; }
    button[aria-selected="true"] p { color: #00A892 !important; font-weight: bold !important; }
    div.stButton > button[kind="primary"] {
        background-color: #00C2A8 !important; color: #0F172A !important; font-weight: bold !important; border-radius: 8px !important; border: none !important;
    }
    div.stButton > button[kind="primary"]:hover { background-color: #00A892 !important; color: #FFFFFF !important; }
    </style>
""",
    unsafe_allow_html=True,
)

# Menú Lateral
st.sidebar.image("LogoC.png", width=200)
st.sidebar.markdown("---")

opcion = st.sidebar.radio(
    "Selecciona una opción:",
    [
        "🛒 Ventas y Cierre de Caja",
        "📦 Ver Stock / Inventario",
        "➕ Registrar Producto",
        "👥 Gestor de Clientes",
        "💳 Deudas de Clientes",
        "🏬 Gestor de Proveedores",
        "🏷️ Gestor de Categorías",
        "📈 Flujo de Caja Mensual",
    ],
)

# ==========================================
# VENTAS Y CIERRE DE CAJA
# ==========================================
if opcion == "🛒 Ventas y Cierre de Caja":
    st.markdown(
        '<p class="main-title">🛒 Ventas y Cierre de Caja</p>',
        unsafe_allow_html=True,
    )
    tab_venta, tab_salida, tab_cierre, tab_historico = st.tabs([
        "🛍️ Nueva Venta",
        "💸 Salidas de Caja",
        "📊 Cierre de Caja (Hoy)",
        "📅 Histórico de Cierres",
    ])

    with tab_venta:
        if "carrito" not in st.session_state:
            st.session_state.carrito = []

        df_productos = obtener_productos()
        df_clientes = obtener_clientes()

        if df_productos.empty:
            st.info("No tienes productos registrados.")
        else:
            df_con_stock = df_productos[df_productos["stock"] > 0]
            if df_con_stock.empty:
                st.info("No hay productos con stock disponible.")
            else:
                opciones_dict = {}
                for _, r in df_con_stock.iterrows():
                    label = (
                        f"{r['nombre']} ({r['marca']}) - Stock: {r['stock']}"
                    )
                    opciones_dict[label] = r["id"]

                col_a1, col_a2, col_a3 = st.columns([3, 1, 1])

                with col_a1:
                    p_sel_label = st.selectbox(
                        "🔍 Buscar o Escanear Código:",
                        options=list(opciones_dict.keys()),
                        index=None,
                        key="select_v_unificado",
                    )

                p_row = None
                stock_disp = 1

                if p_sel_label:
                    id_p = str(opciones_dict[p_sel_label])
                    coincidencias = df_con_stock[
                        df_con_stock["id"].astype(str) == id_p
                    ]
                    if not coincidencias.empty:
                        p_row = coincidencias.iloc[0]

                        cant_car = sum([
                            item["cantidad"]
                            for item in st.session_state.carrito
                            if str(item["id"]) == id_p
                        ])
                        stock_disp = max(1, int(p_row["stock"]) - cant_car)

                with col_a2:
                    cant = st.number_input(
                        "Cantidad:",
                        min_value=1,
                        max_value=stock_disp,
                        value=1,
                        key="cant_v",
                    )

                with col_a3:
                    st.write("")
                    st.write("")
                    if st.button("➕ Agregar"):
                        if p_row is None:
                            st.warning(
                                "Por favor, selecciona un producto válido."
                            )
                        else:
                            id_p = p_row["id"]
                            encontrado = False

                            for item in st.session_state.carrito:
                                if item["id"] == id_p:
                                    cant_nueva = item["cantidad"] + cant
                                    if cant_nueva > p_row["stock"]:
                                        st.error(
                                            f"Stock insuficiente. Máximo disponible: {p_row['stock']}"
                                        )
                                    else:
                                        item["cantidad"] = cant_nueva
                                        item["subtotal"] = (
                                            item["cantidad"]
                                            * item["precio_unitario"]
                                        )
                                        st.success(
                                            "¡Cantidad actualizada en el carrito!"
                                        )
                                    encontrado = True
                                    break

                            if not encontrado:
                                if cant > p_row["stock"]:
                                    st.error(
                                        "Cantidad mayor al stock disponible."
                                    )
                                else:
                                    st.session_state.carrito.append({
                                        "id": p_row["id"],
                                        "nombre": p_row["nombre"],
                                        "cantidad": cant,
                                        "precio_unitario": p_row[
                                            "precio_venta"
                                        ],
                                        "subtotal": cant
                                        * p_row["precio_venta"],
                                        "stock_max": p_row["stock"],
                                    })
                                    st.success("¡Producto agregado!")
                            st.rerun()
