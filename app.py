from datetime import date, datetime
import pandas as pd
import sqlite3
import streamlit as st

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


# --- FUNCIONES CIERRES DE CAJA ---
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
        return 0
    else:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT saldo_final FROM cierres_caja WHERE fecha < ? ORDER BY"
            " fecha DESC LIMIT 1",
            (fecha_hoy_str,),
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0


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


# --- FUNCIONES CATEGORÍAS Y MARCAS ---
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
            return True
        except Exception as e:
            st.error(f"Error al registrar salida de caja: {e}")
            return False


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
st.sidebar.title("✨ Sistema Encanto")
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
                st.warning("⚠️ Todos los productos están sin stock.")
            else:
                st.subheader("1️⃣ Agregar productos al carrito")

                opciones_dict = {}
                for _, r in df_con_stock.iterrows():
                    cod_str = str(r.get("codigo_barras", "")).strip()
                    prefix_cod = (
                        f"[{cod_str}] "
                        if cod_str and cod_str != "nan" and cod_str != ""
                        else ""
                    )
                    label = (
                        f"{prefix_cod}{r['nombre']} ({r['marca']}) - Stock:"
                        f" {r['stock']}"
                    )
                    opciones_dict[label] = r["id"]

                col_a1, col_a2, col_a3 = st.columns([3, 1, 1])
                with col_a1:
                    p_sel_label = st.selectbox(
                        "🔍 Buscar o Escanear Código:",
                        options=list(opciones_dict.keys()),
                        index=None,
                        key="select_v",
                    )

                if p_sel_label:
                    id_p = str(opciones_dict[p_sel_label])
                    p_row = df_con_stock[
                        df_con_stock["id"].astype(str) == id_p
                    ].iloc[0]

                    cant_car = sum([
                        item["cantidad"]
                        for item in st.session_state.carrito
                        if str(item["id"]) == id_p
                    ])
                    stock_disp = int(p_row["stock"]) - cant_car

                    with col_a2:
                        cant = st.number_input(
                            "Cantidad:",
                            min_value=1,
                            max_value=max(1, stock_disp),
                            value=1,
                            key="cant_v",
                        )
                    with col_a3:
                        st.write("")
                        st.write("")
                        if st.button("➕ Agregar", type="primary"):
                            if cant <= stock_disp:
                                st.session_state.carrito.append({
                                    "id": id_p,
                                    "nombre": p_row["nombre"],
                                    "precio_unitario": int(
                                        p_row["precio_venta"]
                                    ),
                                    "cantidad": cant,
                                    "subtotal": int(p_row["precio_venta"])
                                    * cant,
                                })
                                st.success("¡Producto agregado al carrito!")
                                st.rerun()
                            else:
                                st.error("⚠️ Stock insuficiente disponible.")

        st.markdown("---")
        st.subheader("2️⃣ Carrito de Compras")

        if st.session_state.carrito:
            df_car = pd.DataFrame(st.session_state.carrito)
            df_car_show = df_car[
                ["nombre", "cantidad", "precio_unitario", "subtotal"]
            ].copy()
            df_car_show["precio_unitario"] = df_car_show[
                "precio_unitario"
            ].apply(formatear_gs)
            df_car_show["subtotal"] = df_car_show["subtotal"].apply(
                formatear_gs
            )

            st.dataframe(df_car_show, use_container_width=True)

            subtotal_venta = sum(
                item["subtotal"] for item in st.session_state.carrito
            )

            col_des1, col_des2 = st.columns([1, 2])
            with col_des1:
                descuento = st.number_input(
                    "🏷️ Descuento (Gs.):",
                    min_value=0,
                    max_value=subtotal_venta,
                    value=0,
                    step=1000,
                    key="descuento_v",
                )

            monto_total_venta = subtotal_venta - descuento

            if descuento > 0:
                st.markdown(
                    f"Subtotal: ~~{formatear_gs(subtotal_venta)}~~ | Descuento:"
                    f" -{formatear_gs(descuento)}"
                )

            st.markdown(
                f"### Total Final: **{formatear_gs(monto_total_venta)}**"
            )

            col_c1, col_c2, col_c3 = st.columns([2, 2, 1])
            with col_c1:
                tipo_venta = st.selectbox(
                    "Tipo de Venta:", ["Contado", "Crédito"]
                )

                lista_clientes = ["Cliente Ocasional"]
                if not df_clientes.empty:
                    lista_clientes += [
                        f"{r['nombre']} {r['apellido']} (CI: {r['ci']})"
                        for _, r in df_clientes.iterrows()
                    ]
                cliente_sel = st.selectbox("Cliente:", lista_clientes)

            with col_c2:
                metodo_pago = st.selectbox(
                    "Método de Pago:",
                    ["Efectivo", "Transferencia", "Tarjeta", "Giros / Otro"],
                )

            with col_c3:
                st.write("")
                st.write("")
                if st.button("✅ Finalizar Venta", type="primary"):
                    for item in st.session_state.carrito:
                        desc_item = (
                            int(descuento * (item["subtotal"] / subtotal_venta))
                            if subtotal_venta > 0
                            else 0
                        )
                        registrar_venta(
                            producto_id=item["id"],
                            producto_nombre=item["nombre"],
                            cantidad=item["cantidad"],
                            precio_unitario=item["precio_unitario"],
                            total=item["subtotal"] - desc_item,
                            tipo_venta=tipo_venta,
                            metodo_pago=metodo_pago,
                            cliente_nombre=cliente_sel,
                        )
                    st.session_state.carrito = []
                    st.success("🎉 ¡Venta registrada con éxito!")
                    st.rerun()

            if st.button("🗑️ Vaciar Carrito"):
                st.session_state.carrito = []
                st.rerun()
        else:
            st.info("El carrito está vacío.")

    with tab_salida:
        st.subheader("Registrar Salida / Gasto de Caja")
        with st.form("form_salida_caja"):
            motivo = st.text_input("Motivo de la salida:")
            monto = st.number_input("Monto (Gs.):", min_value=1, step=1000)
            metodo = st.selectbox(
                "Método de Pago:",
                ["Efectivo", "Transferencia", "Tarjeta", "Otro"],
            )
            if st.form_submit_button("Registrar Salida", type="primary"):
                if motivo.strip():
                    registrar_salida_caja(
                        motivo=motivo, monto=monto, metodo=metodo
                    )
                    st.success("Salida de caja registrada.")
                    st.rerun()
                else:
                    st.warning("Escribe el motivo de la salida.")

        st.markdown("---")
        st.subheader("Histórico de Salidas")
        df_salidas = obtener_salidas_caja()
        if not df_salidas.empty:
            df_salidas_show = df_salidas.copy()
            df_salidas_show["monto"] = df_salidas_show["monto"].apply(
                formatear_gs
            )
            st.dataframe(df_salidas_show, use_container_width=True)

            st.markdown("---")
            expander_salida_admin = st.expander(
                "🛠️ Opciones Avanzadas (Editar / Eliminar Salida)"
            )
            with expander_salida_admin:
                opcion_s_admin = st.radio(
                    "Selecciona una acción:",
                    ["Editar Salida", "Eliminar Salida"],
                    key="radio_salida_admin",
                )

                dict_salidas_edit = {}
                for _, r in df_salidas.iterrows():
                    label = (
                        f"ID: {r['id']} | {r.get('fecha_hora', '')} | "
                        f"{r.get('motivo', '')} - {formatear_gs(r.get('monto', 0))}"
                    )
                    dict_salidas_edit[label] = r["id"]

                salida_sel_admin = st.selectbox(
                    "Selecciona la salida a modificar:",
                    options=list(dict_salidas_edit.keys()),
                    key="select_salida_admin",
                )

                if salida_sel_admin:
                    id_s_sel = dict_salidas_edit[salida_sel_admin]
                    s_row = df_salidas[
                        df_salidas["id"].astype(str) == str(id_s_sel)
                    ].iloc[0]

                    if opcion_s_admin == "Editar Salida":
                        edit_s_motivo = st.text_input(
                            "Nuevo Motivo:",
                            value=str(s_row.get("motivo", "")),
                            key="edit_s_motivo",
                        )
                        edit_s_monto = st.number_input(
                            "Nuevo Monto (Gs.):",
                            min_value=1,
                            value=int(s_row.get("monto", 0)),
                            step=1000,
                            key="edit_s_monto",
                        )
                        metodos_pago_list = [
                            "Efectivo",
                            "Transferencia",
                            "Tarjeta",
                            "Otro",
                        ]
                        metodo_actual = str(
                            s_row.get("metodo_pago", "Efectivo")
                        )
                        idx_metodo = (
                            metodos_pago_list.index(metodo_actual)
                            if metodo_actual in metodos_pago_list
                            else 0
                        )
                        edit_s_metodo = st.selectbox(
                            "Nuevo Método de Pago:",
                            metodos_pago_list,
                            index=idx_metodo,
                            key="edit_s_metodo",
                        )

                        pwd_s_edit = st.text_input(
                            "Contraseña de confirmación:",
                            type="password",
                            key="pwd_s_edit",
                        )

                        if st.button("✏️ Guardar Cambios en Salida"):
                            if pwd_s_edit == CLAVE_ADMIN:
                                actualizar_salida_caja(
                                    id_s_sel,
                                    edit_s_motivo,
                                    edit_s_monto,
                                    edit_s_metodo,
                                )
                                st.success(
                                    "✅ Salida actualizada correctamente."
                                )
                                st.rerun()
                            else:
                                st.error("❌ Contraseña incorrecta.")

                    elif opcion_s_admin == "Eliminar Salida":
                        st.warning(
                            "⚠️ Esta acción eliminará permanentemente la"
                            " salida seleccionada."
                        )
                        pwd_s_del = st.text_input(
                            "Contraseña de confirmación para BORRAR:",
                            type="password",
                            key="pwd_s_del",
                        )

                        if st.button(
                            "🗑️ Eliminar Salida Definitivamente",
                            type="primary",
                        ):
                            if pwd_s_del == CLAVE_ADMIN:
                                eliminar_salida_caja(id_s_sel)
                                st.success(
                                    "✅ Registro de salida eliminado"
                                    " correctamente."
                                )
                                st.rerun()
                            else:
                                st.error("❌ Contraseña incorrecta.")

    # --- DATOS PARA CIERRE DE CAJA ---
    fecha_hoy = date.today().strftime("%Y-%m-%d")
    saldo_inicial = obtener_saldo_inicial_dia(fecha_hoy)

    df_v = obtener_ventas()
    if not df_v.empty and "fecha_hora" in df_v.columns:
        df_v_hoy = df_v[
            (df_v["fecha_hora"].str.startswith(fecha_hoy))
            & (df_v["estado_pago"] == "Pagado")
        ]
        ingresos_hoy = int(df_v_hoy["total"].sum()) if not df_v_hoy.empty else 0
    else:
        ingresos_hoy = 0

    df_s = obtener_salidas_caja()
    if not df_s.empty and "fecha_hora" in df_s.columns:
        df_s_hoy = df_s[df_s["fecha_hora"].str.startswith(fecha_hoy)]
        egresos_hoy = int(df_s_hoy["monto"].sum()) if not df_s_hoy.empty else 0
    else:
        egresos_hoy = 0

    saldo_final = saldo_inicial + ingresos_hoy - egresos_hoy

    # --- TAB 3: CIERRE DE CAJA (HOY) ---
    with tab_cierre:
        st.subheader(f"Cierre de Caja - Fecha: {fecha_hoy}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Saldo Inicial", formatear_gs(saldo_inicial))
        col2.metric("Ingresos (Hoy)", formatear_gs(ingresos_hoy))
        col3.metric("Egresos (Hoy)", formatear_gs(egresos_hoy))
        col4.metric("Saldo Final Calculado", formatear_gs(saldo_final))

        st.markdown("---")
        st.subheader("🔒 Confirmar Cierre")

        pwd_guardar = st.text_input(
            "Ingresa la contraseña para guardar el cierre:",
            type="password",
            key="pwd_cierre_hoy",
        )

        if st.button("🔒 Confirmar y Guardar Cierre de Hoy", type="primary"):
            if pwd_guardar == CLAVE_ADMIN:
                registrar_cierre_diario(
                    fecha_hoy,
                    saldo_inicial,
                    ingresos_hoy,
                    egresos_hoy,
                    saldo_final,
                )
                st.success("✅ ¡Cierre de caja guardado con éxito!")
                st.rerun()
            else:
                st.error(
                    "❌ Contraseña incorrecta. No se pudo guardar el cierre."
                )

    # --- TAB 4: HISTÓRICO DE CIERRES ---
    with tab_historico:
        st.subheader("🗓️ Histórico de Cierres de Caja")
        df_cierres = obtener_historico_cierres()

        if df_cierres.empty:
            st.info("No hay cierres guardados aún.")
        else:
            df_show = df_cierres.copy()
            for col in ["saldo_inicial", "ingresos", "egresos", "saldo_final"]:
                if col in df_show.columns:
                    df_show[col] = df_show[col].apply(formatear_gs)

            st.dataframe(df_show, use_container_width=True)

            st.markdown("---")

            expander_admin = st.expander(
                "🛠️ Opciones Avanzadas (Editar / Limpiar Histórico)"
            )
            with expander_admin:
                opcion_admin = st.radio(
                    "Selecciona una acción:",
                    ["Editar Cierre Existente", "Limpiar Todo el Histórico"],
                )

                if opcion_admin == "Editar Cierre Existente":
                    fecha_sel = st.selectbox(
                        "Selecciona la fecha a editar:",
                        df_cierres["fecha"].tolist(),
                    )
                    nuevo_saldo_final = st.number_input(
                        "Nuevo Saldo Final (Gs.):", min_value=0, step=1000
                    )
                    pwd_edit = st.text_input(
                        "Contraseña de confirmación:",
                        type="password",
                        key="pwd_edit",
                    )

                    if st.button("✏️ Actualizar Cierre"):
                        if pwd_edit == CLAVE_ADMIN:
                            actualizar_cierre_caja(
                                fecha_sel, nuevo_saldo_final
                            )
                            st.success(
                                f"✅ Cierre del {fecha_sel} actualizado"
                                " correctamente."
                            )
                            st.rerun()
                        else:
                            st.error("❌ Contraseña incorrecta.")

                elif opcion_admin == "Limpiar Todo el Histórico":
                    st.warning(
                        "⚠️ Esta acción borrará permanentemente todos los"
                        " cierres guardados."
                    )
                    pwd_del = st.text_input(
                        "Contraseña de confirmación para BORRAR:",
                        type="password",
                        key="pwd_del",
                    )

                    if st.button(
                        "🗑️ Limpiar Histórico Completo", type="primary"
                    ):
                        if pwd_del == CLAVE_ADMIN:
                            limpiar_historico_cierres()
                            st.success("✅ Histórico eliminado correctamente.")
                            st.rerun()
                        else:
                            st.error("❌ Contraseña incorrecta.")

# ==========================================
# GESTOR DE PROVEEDORES
# ==========================================
elif opcion == "🏬 Gestor de Proveedores":
    st.markdown(
        '<p class="main-title">🏬 Gestor de Proveedores</p>',
        unsafe_allow_html=True,
    )

    tab_prov, tab_edit_p, tab_compras, tab_deudas = st.tabs([
        "👤 Registro / Proveedores",
        "✏️ Editar / Eliminar",
        "🚚 Registrar Compra",
        "📜 Deudas por Pagar",
    ])

    with tab_prov:
        st.subheader("Registrar Nuevo Proveedor")
        with st.form("form_proveedor"):
            col1, col2 = st.columns(2)
            nombre = col1.text_input("Nombre / Razón Social:")
            ruc_ci = col2.text_input("RUC o CI:")
            telefono = col1.text_input("Teléfono:")
            ciudad = col2.text_input("Ciudad:")

            if st.form_submit_button("💾 Guardar Proveedor", type="primary"):
                if nombre.strip():
                    registrar_proveedor(nombre, ruc_ci, telefono, ciudad)
                    st.success("¡Proveedor registrado correctamente!")
                    st.rerun()
                else:
                    st.warning("El Nombre / Razón Social es obligatorio.")

        st.markdown("---")
        st.subheader("📋 Lista de Proveedores")
        df_prov = obtener_proveedores()
        if not df_prov.empty:
            cols_deseadas = ["nombre", "ruc_ci", "telefono", "ciudad", "id"]
            cols_visibles = [c for c in cols_deseadas if c in df_prov.columns]
            st.dataframe(df_prov[cols_visibles], use_container_width=True)
        else:
            st.info("No hay proveedores registrados aún.")

    with tab_edit_p:
        st.subheader("Modificar o Eliminar Proveedor")
        df_prov = obtener_proveedores()

        if df_prov.empty:
            st.info("No hay proveedores registrados para modificar.")
        else:
            dict_prov = {}
            for _, r in df_prov.iterrows():
                ruc_text = (
                    f" (RUC/CI: {r['ruc_ci']})"
                    if r.get("ruc_ci") and str(r["ruc_ci"]) != "-"
                    else ""
                )
                label = f"{r['nombre']}{ruc_text}"
                dict_prov[label] = r["id"]

            prov_sel_label = st.selectbox(
                "🔍 Selecciona un proveedor para modificar:",
                options=list(dict_prov.keys()),
                index=None,
                key="select_edit_prov",
            )

            if prov_sel_label:
                id_prov = dict_prov[prov_sel_label]
                p_row = df_prov[
                    df_prov["id"].astype(str) == str(id_prov)
                ].iloc[0]

                with st.form("form_edit_prov"):
                    col1, col2 = st.columns(2)
                    edit_nombre = col1.text_input(
                        "Nombre / Razón Social:",
                        value=str(p_row.get("nombre", "")),
                    )
                    edit_ruc_ci = col2.text_input(
                        "RUC o CI:", value=str(p_row.get("ruc_ci", ""))
                    )
                    edit_telefono = col1.text_input(
                        "Teléfono:", value=str(p_row.get("telefono", ""))
                    )
                    edit_ciudad = col2.text_input(
                        "Ciudad:", value=str(p_row.get("ciudad", ""))
                    )

                    if st.form_submit_button(
                        "💾 Guardar Cambios", type="primary"
                    ):
                        if edit_nombre.strip():
                            actualizar_proveedor(
                                id_prov,
                                edit_nombre,
                                edit_ruc_ci,
                                edit_telefono,
                                edit_ciudad,
                            )
                            st.success(
                                "¡Datos del proveedor actualizados"
                                " correctamente!"
                            )
                            st.rerun()
                        else:
                            st.warning("El nombre es obligatorio.")

                st.markdown("---")
                st.subheader("⚠️ Zona de Peligro")
                if st.button("🗑️ Eliminar Proveedor", key="btn_del_prov"):
                    eliminar_proveedor(id_prov)
                    st.success("¡Proveedor eliminado correctamente!")
                    st.rerun()

    with tab_compras:
        st.subheader("Registrar Compra / Factura de Proveedor")
        df_prov = obtener_proveedores()

        if df_prov.empty:
            st.warning("⚠️ Primero debes registrar al menos un proveedor.")
        else:
            with st.form("form_compra_prov"):
                prov_sel = st.selectbox(
                    "Seleccionar Proveedor:", df_prov["nombre"].tolist()
                )
                concepto = st.text_input(
                    "Concepto / Descripción de la compra:"
                )
                monto = st.number_input(
                    "Monto Total (Gs.):", min_value=1, step=5000
                )
                metodo_pago = st.selectbox(
                    "Método de Pago Preferido / Cuenta:",
                    ["Efectivo", "Transferencia", "Tarjeta", "Giros / Otro"],
                )

                if st.form_submit_button(
                    "🚚 Registrar Compra (A Crédito)", type="primary"
                ):
                    if concepto.strip():
                        registrar_compra_proveedor(
                            proveedor=prov_sel,
                            concepto=concepto,
                            monto_total=monto,
                            tipo_compra="Crédito",
                            metodo_pago=metodo_pago,
                            estado_pago="Pendiente",
                        )
                        st.success("¡Compra registrada correctamente!")
                        st.rerun()
                    else:
                        st.warning("Por favor ingresa un concepto.")

            st.markdown("---")
            st.subheader("📋 Historial de Compras")
            df_compras = obtener_compras_proveedores()

            if not df_compras.empty:
                df_show = df_compras.copy()
                if "monto_total" in df_show.columns:
                    df_show["monto_total"] = df_show["monto_total"].apply(
                        formatear_gs
                    )
                if "monto_pagado" in df_show.columns:
                    df_show["monto_pagado"] = df_show["monto_pagado"].apply(
                        lambda x: (
                            formatear_gs(x) if pd.notnull(x) else "Gs. 0"
                        )
                    )

                st.dataframe(df_show, use_container_width=True)

                st.markdown("---")
                expander_compra_admin = st.expander(
                    "🛠️ Opciones Avanzadas (Editar / Eliminar Compra)"
                )

                with expander_compra_admin:
                    opcion_c_admin = st.radio(
                        "Selecciona una acción:",
                        ["Editar Compra", "Eliminar Compra"],
                        key="radio_compra_admin",
                    )

                    dict_compras_edit = {}
                    for _, r in df_compras.iterrows():
                        label = (
                            f"ID: {r['id']} |"
                            f" {r.get('proveedor_nombre', 'Proveedor')} |"
                            f" {r.get('concepto', '')} - Total:"
                            f" {formatear_gs(r.get('monto_total', 0))}"
                        )
                        dict_compras_edit[label] = r["id"]

                    compra_sel_admin = st.selectbox(
                        "Selecciona la compra a modificar:",
                        options=list(dict_compras_edit.keys()),
                        key="select_compra_admin",
                    )

                    if compra_sel_admin:
                        id_c_sel = dict_compras_edit[compra_sel_admin]
                        c_row = df_compras[
                            df_compras["id"].astype(str) == str(id_c_sel)
                        ].iloc[0]

                        if opcion_c_admin == "Editar Compra":
                            m_total_orig = int(c_row.get("monto_total", 0))
                            m_pagado_orig = int(
                                c_row.get("monto_pagado", 0)
                                if pd.notnull(c_row.get("monto_pagado"))
                                else 0
                            )

                            edit_concepto = st.text_input(
                                "Nuevo Concepto:",
                                value=str(c_row.get("concepto", "")),
                                key="edit_c_concepto",
                            )
                            edit_monto_total = st.number_input(
                                "Nuevo Monto Total (Gs.):",
                                min_value=0,
                                value=m_total_orig,
                                step=5000,
                                key="edit_c_monto_total",
                            )
                            edit_monto_pagado = st.number_input(
                                "Nuevo Monto Pagado (Gs.):",
                                min_value=0,
                                value=m_pagado_orig,
                                step=5000,
                                key="edit_c_monto_pagado",
                            )

                            pwd_c_edit = st.text_input(
                                "Contraseña de confirmación:",
                                type="password",
                                key="pwd_c_edit",
                            )

                            if st.button("✏️ Guardar Cambios en Compra"):
                                if pwd_c_edit == CLAVE_ADMIN:
                                    if edit_monto_pagado >= edit_monto_total:
                                        nuevo_est = "Pagado"
                                    elif edit_monto_pagado > 0:
                                        nuevo_est = "Parcial"
                                    else:
                                        nuevo_est = "Pendiente"

                                    actualizar_compra_proveedor(
                                        id_c_sel,
                                        edit_concepto,
                                        edit_monto_total,
                                        edit_monto_pagado,
                                        nuevo_est,
                                    )
                                    st.success(
                                        "✅ Compra actualizada correctamente."
                                    )
                                    st.rerun()
                                else:
                                    st.error("❌ Contraseña incorrecta.")

                        elif opcion_c_admin == "Eliminar Compra":
                            st.warning(
                                "⚠️ Esta acción eliminará permanentemente la"
                                " compra del historial."
                            )
                            pwd_c_del = st.text_input(
                                "Contraseña de confirmación para BORRAR:",
                                type="password",
                                key="pwd_c_del",
                            )

                            if st.button(
                                "🗑️ Eliminar Compra Definitivamente",
                                type="primary",
                            ):
                                if pwd_c_del == CLAVE_ADMIN:
                                    eliminar_compra_proveedor(id_c_sel)
                                    st.success(
                                        "✅ Registro de compra eliminado"
                                        " correctamente."
                                    )
                                    st.rerun()
                                else:
                                    st.error("❌ Contraseña incorrecta.")
            else:
                st.info("No hay registro de compras aún.")

    with tab_deudas:
        st.subheader("📜 Deudas Pendientes con Proveedores")
        df_compras = obtener_compras_proveedores()

        if not df_compras.empty:
            if "estado_pago" in df_compras.columns:
                deudas = df_compras[
                    df_compras["estado_pago"].isin(["Pendiente", "Parcial"])
                ].copy()
            else:
                deudas = pd.DataFrame()

            if not deudas.empty:
                deudas["monto_total"] = (
                    deudas["monto_total"].fillna(0).astype(int)
                )
                if "monto_pagado" not in deudas.columns:
                    deudas["monto_pagado"] = 0
                else:
                    deudas["monto_pagado"] = (
                        deudas["monto_pagado"].fillna(0).astype(int)
                    )

                deudas["saldo_pendiente"] = (
                    deudas["monto_total"] - deudas["monto_pagado"]
                )

                df_show_deudas = deudas.copy()
                df_show_deudas["monto_total"] = df_show_deudas[
                    "monto_total"
                ].apply(formatear_gs)
                df_show_deudas["monto_pagado"] = df_show_deudas[
                    "monto_pagado"
                ].apply(formatear_gs)
                df_show_deudas["saldo_pendiente"] = df_show_deudas[
                    "saldo_pendiente"
                ].apply(formatear_gs)

                columnas_deseadas = [
                    "fecha_hora",
                    "fecha",
                    "proveedor_nombre",
                    "proveedor",
                    "nombre_proveedor",
                    "concepto",
                    "monto_total",
                    "monto_pagado",
                    "saldo_pendiente",
                    "tipo_compra",
                    "metodo_pago",
                    "id",
                ]

                cols_existentes = [
                    c for c in columnas_deseadas if c in df_show_deudas.columns
                ]
                st.dataframe(
                    df_show_deudas[cols_existentes], use_container_width=True
                )

                st.markdown("---")
                st.subheader("💵 Registrar Pago / Entrega")

                dict_deudas = {}
                for _, r in deudas.iterrows():
                    nombre_prov = r.get(
                        "proveedor",
                        r.get(
                            "proveedor_nombre",
                            r.get("nombre_proveedor", "Proveedor"),
                        ),
                    )
                    label = (
                        f"ID: {r['id']} | {nombre_prov} | Saldo:"
                        f" {formatear_gs(r['saldo_pendiente'])}"
                    )
                    dict_deudas[label] = r["id"]

                compra_sel_label = st.selectbox(
                    "Selecciona la compra a pagar:",
                    options=list(dict_deudas.keys()),
                )

                if compra_sel_label:
                    id_compra_sel = dict_deudas[compra_sel_label]
                    compra_row = deudas[deudas["id"] == id_compra_sel].iloc[0]

                    saldo_actual = int(compra_row["saldo_pendiente"])
                    monto_pagado_actual = int(compra_row["monto_pagado"])
                    monto_total_original = int(compra_row["monto_total"])
                    prov_nombre_final = compra_row.get(
                        "proveedor",
                        compra_row.get("proveedor_nombre", "Proveedor"),
                    )

                    col_p1, col_p2 = st.columns(2)
                    col_p1.metric(
                        "Monto Total Compra",
                        formatear_gs(monto_total_original),
                    )
                    col_p2.metric(
                        "Saldo Pendiente Actual", formatear_gs(saldo_actual)
                    )

                    with st.form("form_pago_proveedor"):
                        monto_a_pagar = st.number_input(
                            "Monto a Abonar (Gs.):",
                            min_value=1,
                            max_value=max(1, saldo_actual),
                            value=saldo_actual,
                            step=5000,
                        )
                        metodo_pago_deuda = st.selectbox(
                            "Método de Pago:",
                            ["Efectivo", "Transferencia", "Tarjeta", "Otro"],
                        )

                        if st.form_submit_button(
                            "✅ Confirmar Pago", type="primary"
                        ):
                            nuevo_monto_pagado = (
                                monto_pagado_actual + monto_a_pagar
                            )
                            nuevo_estado = (
                                "Pagado"
                                if nuevo_monto_pagado >= monto_total_original
                                else "Parcial"
                            )

                            actualizar_pago_compra_proveedor(
                                id_compra=id_compra_sel,
                                nuevo_monto_pagado=nuevo_monto_pagado,
                                nuevo_estado=nuevo_estado,
                            )

                            registrar_salida_caja(
                                motivo=(
                                    f"Pago deuda proveedor {prov_nombre_final}"
                                    f" (ID Compra: {id_compra_sel})"
                                ),
                                monto=monto_a_pagar,
                                metodo=metodo_pago_deuda,
                            )

                            st.success(
                                f"¡Pago de {formatear_gs(monto_a_pagar)}"
                                " registrado con éxito!"
                            )
                            st.rerun()
            else:
                st.success("🎉 ¡No hay deudas pendientes con proveedores!")
        else:
            st.info("No hay registro de compras aún.")

# ==========================================
# DEUDAS DE CLIENTES
# ==========================================
elif opcion == "💳 Deudas de Clientes":
    st.markdown(
        '<p class="main-title">💳 Deudas de Clientes</p>',
        unsafe_allow_html=True,
    )
    df_ventas = obtener_ventas()
    if not df_ventas.empty:
        deudas = df_ventas[df_ventas["estado_pago"] == "Pendiente"]
        if not deudas.empty:
            df_show = deudas.copy()
            df_show["total"] = df_show["total"].apply(formatear_gs)
            st.dataframe(df_show, use_container_width=True)
        else:
            st.success("🎉 ¡No hay deudas pendientes de clientes!")

# ==========================================
# GESTOR DE CLIENTES
# ==========================================
elif opcion == "👥 Gestor de Clientes":
    st.markdown(
        '<p class="main-title">👥 Gestor de Clientes</p>',
        unsafe_allow_html=True,
    )

    tab_nuevo_c, tab_editar_c, tab_lista_c = st.tabs([
        "➕ Registrar Cliente",
        "✏️ Editar / Modificar Cliente",
        "📋 Ver Lista de Clientes",
    ])

    df_clientes = obtener_clientes()

    with tab_nuevo_c:
        st.subheader("Registrar Nuevo Cliente")
        with st.form("form_cliente"):
            col1, col2 = st.columns(2)
            nombre = col1.text_input("Nombre:")
            apellido = col2.text_input("Apellido:")
            ci = col1.text_input("N° Documento / CI:")
            telefono = col2.text_input("Teléfono:")
            ciudad = st.text_input("Ciudad:")

            if st.form_submit_button("Guardar Cliente", type="primary"):
                if nombre.strip() and apellido.strip():
                    registrar_cliente(nombre, apellido, ci, telefono, ciudad)
                    st.success("¡Cliente guardado con éxito!")
                    st.rerun()
                else:
                    st.warning("El Nombre y Apellido son obligatorios.")

    with tab_editar_c:
        st.subheader("Modificar Datos de un Cliente")
        if df_clientes.empty:
            st.info("No hay clientes registrados para editar.")
        else:
            dict_clientes = {}
            for _, r in df_clientes.iterrows():
                label = f"{r['nombre']} {r['apellido']} (CI: {r['ci']})"
                dict_clientes[label] = r["id"]

            cliente_sel_label = st.selectbox(
                "🔍 Selecciona un cliente para modificar:",
                options=list(dict_clientes.keys()),
                index=None,
                key="select_edit_cliente",
            )

            if cliente_sel_label:
                id_cliente = dict_clientes[cliente_sel_label]
                c_row = df_clientes[
                    df_clientes["id"].astype(str) == str(id_cliente)
                ].iloc[0]

                with st.form("form_edit_cliente"):
                    col1, col2 = st.columns(2)
                    edit_nombre = col1.text_input(
                        "Nombre:", value=str(c_row.get("nombre", ""))
                    )
                    edit_apellido = col2.text_input(
                        "Apellido:", value=str(c_row.get("apellido", ""))
                    )
                    edit_ci = col1.text_input(
                        "N° Documento / CI:", value=str(c_row.get("ci", ""))
                    )
                    edit_telefono = col2.text_input(
                        "Teléfono:", value=str(c_row.get("telefono", ""))
                    )
                    edit_ciudad = st.text_input(
                        "Ciudad:", value=str(c_row.get("ciudad", ""))
                    )

                    col_btn1, col_btn2 = st.columns([1, 1])
                    if col_btn1.form_submit_button(
                        "💾 Guardar Cambios", type="primary"
                    ):
                        if edit_nombre.strip() and edit_apellido.strip():
                            actualizar_cliente(
                                id_cliente,
                                edit_nombre,
                                edit_apellido,
                                edit_ci,
                                edit_telefono,
                                edit_ciudad,
                            )
                            st.success(
                                "¡Datos del cliente actualizados correctamente!"
                            )
                            st.rerun()
                        else:
                            st.warning(
                                "El Nombre y Apellido no pueden quedar vacíos."
                            )

    with tab_lista_c:
        st.subheader("📋 Listado General de Clientes")

        if not df_clientes.empty:
            columnas_ordenadas = [
                "nombre",
                "apellido",
                "ci",
                "cedula",
                "telefono",
                "ciudad",
                "direccion",
                "deuda",
                "deuda_pendiente",
                "id",
            ]

            cols_existentes = [
                col for col in columnas_ordenadas if col in df_clientes.columns
            ]
            st.dataframe(
                df_clientes[cols_existentes], use_container_width=True
            )
        else:
            st.info("No hay clientes registrados en el sistema.")

# ==========================================
# FLUJO DE CAJA MENSUAL
# ==========================================
elif opcion == "📈 Flujo de Caja Mensual":
    st.markdown(
        '<p class="main-title">📈 Flujo de Caja Mensual</p>',
        unsafe_allow_html=True,
    )
    df_ventas = obtener_ventas()
    df_salidas = obtener_salidas_caja()

    col1, col2 = st.columns(2)
    ingresos_totales = (
        df_ventas[df_ventas["estado_pago"] == "Pagado"]["total"].sum()
        if not df_ventas.empty
        else 0
    )
    egresos_totales = (
        df_salidas["monto"].sum() if not df_salidas.empty else 0
    )

    col1.metric("Ingresos Históricos Totales", formatear_gs(ingresos_totales))
    col2.metric("Egresos Históricos Totales", formatear_gs(egresos_totales))

# ==========================================
# VER STOCK / INVENTARIO
# ==========================================
elif opcion in ["📦 Ver Stock / Inventario", "Ver Stock / Inventario"]:
    st.markdown(
        '<p class="main-title">📦 Ver Stock / Inventario</p>',
        unsafe_allow_html=True,
    )

    df_p = obtener_productos()

    if not df_p.empty:
        # Ordenar el DataFrame alfabéticamente por nombre
        df_p = df_p.sort_values(by="nombre", ascending=True)

        # Creamos la lista de opciones para el buscador
        opciones_filtro = ["-- Mostrar Todos --"]

        for _, r in df_p.iterrows():
            cod = str(r.get("codigo_barras", "")).strip()
            label = f"{r['nombre']} | Marca: {r.get('marca', '')} | Cat: {r.get('categoria', '')}"
            if cod and cod not in ["nan", "None", ""]:
                label = f"[{cod}] " + label
            opciones_filtro.append(label)

        seleccion = st.selectbox(
            "🔍 Empieza a escribir el Nombre, Código, Marca o Categoría:",
            options=opciones_filtro,
            index=0,
            key="buscar_instantaneo",
        )

        # Filtrado según la opción seleccionada
        if seleccion != "-- Mostrar Todos --":
            if "]" in seleccion:
                cod_extraido = seleccion.split("]")[0].replace("[", "").strip()
                df_p = df_p[df_p["codigo_barras"].astype(str) == cod_extraido]
            else:
                nombre_extraido = seleccion.split(" | ")[0].strip()
                df_p = df_p[df_p["nombre"] == nombre_extraido]

        # Orden de columnas con 'stock' en tercer lugar
        orden_columnas = [
            "codigo_barras",
            "nombre",
            "stock",
            "marca",
            "categoria",
            "precio_costo",
            "ganancia_porcentaje",
            "precio_venta",
        ]

        resto_columnas = [
            col for col in df_p.columns if col not in orden_columnas
        ]
        columnas_finales = [
            col for col in orden_columnas if col in df_p.columns
        ] + resto_columnas

        df_mostrar = df_p[columnas_finales]

        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
    else:
        st.info("No hay productos registrados en el inventario.")

# ==========================================
# GESTOR DE PRODUCTOS
# ==========================================
elif opcion in [
    "📦 Gestor de Productos",
    "➕ Registrar Producto",
    "✏️ Editar / Modificar Producto",
]:
    st.markdown(
        '<p class="main-title">📦 Gestor de Productos</p>',
        unsafe_allow_html=True,
    )

    tab_reg_p, tab_edit_p = st.tabs(
        ["➕ Registrar Producto", "✏️ Editar / Modificar Producto"]
    )

    with tab_reg_p:
        st.subheader("Registrar Nuevo Producto")
        cats = obtener_categorias()
        marcas = obtener_marcas()

        # Inicialización de estado para el registro interactivo
        if "reg_costo" not in st.session_state:
            st.session_state.reg_costo = 0
        if "reg_ganancia" not in st.session_state:
            st.session_state.reg_ganancia = 30
        if "reg_precio_venta" not in st.session_state:
            st.session_state.reg_precio_venta = 0

        # Funciones callback para cálculo dinámico
        def recalcular_por_ganancia():
            costo = st.session_state.reg_costo
            ganancia = st.session_state.reg_ganancia
            st.session_state.reg_precio_venta = int(
                costo + (costo * (ganancia / 100))
            )

        def recalcular_por_precio():
            costo = st.session_state.reg_costo
            precio_v = st.session_state.reg_precio_venta
            if costo > 0:
                st.session_state.reg_ganancia = int(
                    ((precio_v - costo) / costo) * 100
                )
            else:
                st.session_state.reg_ganancia = 0

        col1, col2 = st.columns(2)
        cod_barras = col1.text_input("Código de Barras:")
        nombre = col2.text_input("Nombre del Producto:")
        cat = col1.selectbox("Categoría:", cats)
        marca = col2.selectbox("Marca:", marcas)

        costo = col1.number_input(
            "Precio Costo (Gs.):",
            min_value=0,
            step=1000,
            key="reg_costo",
            on_change=recalcular_por_ganancia,
        )

        ganancia = col2.number_input(
            "% Ganancia:",
            min_value=0,
            key="reg_ganancia",
            on_change=recalcular_por_ganancia,
        )

        precio_venta = col1.number_input(
            "Precio Venta (Gs.):",
            min_value=0,
            step=1000,
            key="reg_precio_venta",
            on_change=recalcular_por_precio,
        )

        stock = col2.number_input("Stock Inicial:", min_value=0, value=1)
        desc = st.text_area("Descripción:")

        if st.button("💾 Guardar Producto", type="primary"):
            if nombre.strip():
                registrar_producto(
                    cod_barras,
                    nombre,
                    cat,
                    marca,
                    costo,
                    ganancia,
                    precio_venta,
                    stock,
                    desc,
                )
                st.success("¡Producto registrado exitosamente!")
                # Limpiar variables de sesión tras guardar
                st.session_state.reg_costo = 0
                st.session_state.reg_ganancia = 30
                st.session_state.reg_precio_venta = 0
                st.rerun()
            else:
                st.warning("El nombre del producto es obligatorio.")

    with tab_edit_p:
        st.subheader("Modificar / Eliminar Producto")
        df_p = obtener_productos()

        if not df_p.empty:
            # Filtros superiores opcionales
            col_f1, col_f2 = st.columns(2)
            cats_filtro = ["Todas"] + list(obtener_categorias())
            marcas_filtro = ["Todas"] + list(obtener_marcas())

            cat_sel = col_f1.selectbox(
                "Filtrar por Categoría:", cats_filtro, key="filtro_cat_edit"
            )
            marca_sel = col_f2.selectbox(
                "Filtrar por Marca:", marcas_filtro, key="filtro_marca_edit"
            )

            # Filtrar datos si se selecciona una categoría o marca específica
            df_filtrado = df_p.copy()
            if cat_sel != "Todas":
                df_filtrado = df_filtrado[df_filtrado["categoria"] == cat_sel]
            if marca_sel != "Todas":
                df_filtrado = df_filtrado[df_filtrado["marca"] == marca_sel]

            dict_productos = {}
            for _, r in df_filtrado.iterrows():
                cod_str = str(r.get("codigo_barras", "")).strip()
                prefix_cod = (
                    f"[{cod_str}] "
                    if cod_str and cod_str not in ["nan", "None", ""]
                    else ""
                )
                cat_str = str(r.get("categoria", "")).strip()
                marca_str = str(r.get("marca", "")).strip()

                # Etiqueta completa para que el buscador encuentre todo al escribir
                label = f"{prefix_cod}{r['nombre']} | Cat: {cat_str} | Marca: {marca_str}"
                dict_productos[label] = str(r["id"])

            prod_sel_label = st.selectbox(
                "🔍 Busca por Nombre, Código de Barras, Categoría o Marca:",
                options=list(dict_productos.keys()),
                index=None,
                placeholder="Escribe cualquier dato del producto...",
                key="select_edit_prod",
            )

            if prod_sel_label:
                id_p = dict_productos[prod_sel_label]
                p_row = df_p[df_p["id"].astype(str) == id_p].iloc[0]

                cats = obtener_categorias()
                marcas = obtener_marcas()

                with st.form("form_edit_prod"):
                    col1, col2 = st.columns(2)
                    cod_barras = col1.text_input(
                        "Código de Barras:",
                        value=str(p_row.get("codigo_barras", "")),
                    )
                    nombre = col2.text_input(
                        "Nombre del Producto:", value=p_row["nombre"]
                    )
                    cat = col1.selectbox(
                        "Categoría:",
                        cats,
                        index=(
                            cats.index(p_row["categoria"])
                            if p_row["categoria"] in cats
                            else 0
                        ),
                    )
                    marca = col2.selectbox(
                        "Marca:",
                        marcas,
                        index=(
                            marcas.index(p_row["marca"])
                            if p_row["marca"] in marcas
                            else 0
                        ),
                    )
                    costo = col1.number_input(
                        "Precio Costo (Gs.):",
                        min_value=0,
                        value=int(p_row["precio_costo"]),
                    )
                    ganancia = col2.number_input(
                        "% Ganancia:",
                        min_value=0,
                        value=int(p_row["ganancia_porcentaje"]),
                    )
                    precio_venta = col1.number_input(
                        "Precio Venta (Gs.):",
                        min_value=0,
                        value=int(p_row["precio_venta"]),
                    )
                    stock = col2.number_input(
                        "Stock:", min_value=0, value=int(p_row["stock"])
                    )
                    desc = st.text_area(
                        "Descripción:",
                        value=str(p_row.get("descripcion", "")),
                    )

                    c_save, _ = st.columns([1, 1])
                    if c_save.form_submit_button(
                        "Guardar Cambios", type="primary"
                    ):
                        actualizar_producto(
                            id_p,
                            cod_barras,
                            nombre,
                            cat,
                            marca,
                            costo,
                            ganancia,
                            precio_venta,
                            stock,
                            desc,
                        )
                        st.success("Producto actualizado correctamente.")
                        st.rerun()

                if st.button("🗑️ Eliminar Producto", key="btn_del_prod"):
                    eliminar_producto(id_p)
                    st.success("Producto eliminado.")
                    st.rerun()
        else:
            st.info("No hay productos registrados para modificar.")

# ==========================================
# GESTOR DE CATEGORÍAS Y MARCAS
# ==========================================
elif opcion in [
    "🏷️ Gestor de Categorías",
    "🏢 Gestor de Marcas",
    "Gestor de Categorías",
    "Gestor de Marcas",
]:
    st.markdown(
        '<p class="main-title">🏷️ Gestor de Categorías y Marcas</p>',
        unsafe_allow_html=True,
    )

    tab_cat, tab_mar = st.tabs(["🏷️ Categorías", "🏢 Marcas"])

    with tab_cat:
        st.subheader("Gestión de Categorías")
        cats = obtener_categorias()

        col1, col2 = st.columns(2)
        with col1:
            nueva_cat = st.text_input("Nueva Categoría:", key="input_nueva_cat")
            if st.button("Agregar Categoría", type="primary", key="btn_add_cat"):
                if nueva_cat.strip():
                    registrar_categoria(nueva_cat)
                    st.success("Categoría agregada.")
                    st.rerun()
        with col2:
            cat_del = st.selectbox(
                "Eliminar Categoría:", cats, key="select_del_cat"
            )
            if st.button("Eliminar Categoría", key="btn_del_cat"):
                eliminar_categoria(cat_del)
                st.success("Categoría eliminada.")
                st.rerun()

        st.markdown("---")
        st.write("Categorías actuales:", cats)

    with tab_mar:
        st.subheader("Gestión de Marcas")
        marcas = obtener_marcas()

        col1, col2 = st.columns(2)
        with col1:
            nueva_marca = st.text_input("Nueva Marca:", key="input_nueva_marca")
            if st.button(
                "Agregar Marca", type="primary", key="btn_add_marca"
            ):
                if nueva_marca.strip():
                    registrar_marca(nueva_marca)
                    st.success("Marca agregada.")
                    st.rerun()
        with col2:
            marca_del = st.selectbox(
                "Eliminar Marca:", marcas, key="select_del_marca"
            )
            if st.button("Eliminar Marca", key="btn_del_marca"):
                eliminar_marca(marca_del)
                st.success("Marca eliminada.")
                st.rerun()

        st.markdown("---")
        st.write("Marcas actuales:", marcas)
