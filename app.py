import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime, date
import io

# Intentar importar openpyxl para exportación a Excel
try:
    import openpyxl
    OPENPYXL_DISPONIBLE = True
except ImportError:
    OPENPYXL_DISPONIBLE = False

# Intentar importar la librería de Google Firestore para base de datos permanente
try:
    from google.cloud import firestore
    FIRESTORE_DISPONIBLE = True
except ImportError:
    FIRESTORE_DISPONIBLE = False

# ==========================================
# CONSTANTES Y CONFIGURACIÓN DE CONEXIÓN
# ==========================================
def obtener_conexion_db():
    """Detecta si están configuradas las credenciales de Firestore en la nube, de lo contrario usa SQLite."""
    if FIRESTORE_DISPONIBLE and "gcp_service_account" in st.secrets:
        try:
            return firestore.Client.from_service_account_info(dict(st.secrets["gcp_service_account"]))
        except Exception:
            return None
    return None

# ==========================================
# 1. CONTROL DE BASE DE DATOS (HÍBRIDO: SQLITE / CLOUD)
# ==========================================
def init_db():
    """Inicializa la base de datos local SQLite si no se usa almacenamiento en la nube."""
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        return
        
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    
    # Crear tabla de productos
    cursor.execute("PRAGMA table_info(productos)")
    columnas_prod = [col[1] for col in cursor.fetchall()]
    if columnas_prod and "marca" not in columnas_prod:
        try:
            cursor.execute("ALTER TABLE productos ADD COLUMN marca TEXT")
        except sqlite3.OperationalError:
            pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    # Crear tabla de categorías
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        )
    """)

    # Crear tabla de marcas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS marcas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL
        )
    """)

    # Crear tabla de clientes
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

    # Crear tabla de ventas
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
    
    # Crear tabla de historial de pagos de clientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            cliente_nombre TEXT NOT NULL,
            monto INTEGER NOT NULL,
            metodo_pago TEXT NOT NULL
        )
    """)

    # Crear tabla de salidas/gastos de caja
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salidas_caja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            motivo TEXT NOT NULL,
            monto INTEGER NOT NULL,
            metodo_pago TEXT NOT NULL
        )
    """)

    # Tabla: Cierres de caja para arrastre de saldo
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

    # NUEVA TABLA: Proveedores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ruc_ci TEXT,
            telefono TEXT,
            ciudad TEXT
        )
    """)

    # NUEVA TABLA: Compras a Proveedores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            proveedor_nombre TEXT NOT NULL,
            concepto TEXT NOT NULL,
            monto_total INTEGER NOT NULL,
            tipo_compra TEXT NOT NULL,
            metodo_pago TEXT NOT NULL,
            estado_pago TEXT DEFAULT 'Pagado'
        )
    """)

    # NUEVA TABLA: Pagos a Proveedores
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

    cursor.execute("PRAGMA table_info(ventas)")
    cols_ventas = [col[1] for col in cursor.fetchall()]
    if "tipo_venta" not in cols_ventas:
        try:
            cursor.execute("ALTER TABLE ventas ADD COLUMN tipo_venta TEXT DEFAULT 'Contado'")
        except sqlite3.OperationalError:
            pass
    if "estado_pago" not in cols_ventas:
        try:
            cursor.execute("ALTER TABLE ventas ADD COLUMN estado_pago TEXT DEFAULT 'Pagado'")
        except sqlite3.OperationalError:
            pass

    # Datos iniciales si está vacía la BD
    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        cat_iniciales = [("Perfumes",), ("Cosméticos",), ("Cuidado Personal",), ("Otros",)]
        cursor.executemany("INSERT INTO categorias (nombre) VALUES (?)", cat_iniciales)

    cursor.execute("SELECT COUNT(*) FROM marcas")
    if cursor.fetchone()[0] == 0:
        marcas_iniciales = [("Natura",), ("O Boticário",), ("Eudora",), ("Sin Marca / Genérico",)]
        cursor.executemany("INSERT INTO marcas (nombre) VALUES (?)", marcas_iniciales)

    conn.commit()
    conn.close()

# --- FUNCIONES DE ARRASTRE DE SALDO ---
def obtener_saldo_inicial_dia(fecha_hoy_str):
    """Obtiene el saldo final del cierre anterior para arrastrarlo como saldo inicial."""
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("cierres_caja").stream()
        registros = [doc.to_dict() for doc in docs if doc.to_dict().get("fecha", "") < fecha_hoy_str]
        if registros:
            registros_ordenados = sorted(registros, key=lambda x: x["fecha"], reverse=True)
            return int(registros_ordenados[0].get("saldo_final", 0))
        return 0
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("SELECT saldo_final FROM cierres_caja WHERE fecha < ? ORDER BY fecha DESC LIMIT 1", (fecha_hoy_str,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0

def registrar_cierre_diario(fecha_str, saldo_inicial, ingresos, egresos, saldo_final):
    """Guarda o actualiza el cierre oficial del día con arrastre."""
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("cierres_caja").document(fecha_str).set({
            "fecha": fecha_str,
            "saldo_inicial": int(saldo_inicial),
            "ingresos": int(ingresos),
            "egresos": int(egresos),
            "saldo_final": int(saldo_final)
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cierres_caja (fecha, saldo_inicial, ingresos, egresos, saldo_final)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fecha) DO UPDATE SET
                saldo_inicial = excluded.saldo_inicial,
                ingresos = excluded.ingresos,
                egresos = excluded.egresos,
                saldo_final = excluded.saldo_final
        """, (fecha_str, int(saldo_inicial), int(ingresos), int(egresos), int(saldo_final)))
        conn.commit()
        conn.close()

# --- FUNCIONES DE CATEGORÍAS Y MARCAS ---
def obtener_categorias():
    db_cloud = obtener_conexion_db()
    cat_default = ["Perfumes", "Cosméticos", "Cuidado Personal", "Otros"]
    if db_cloud is not None:
        docs = db_cloud.collection("categorias").stream()
        lista = [doc.to_dict().get("nombre") for doc in docs if doc.to_dict().get("nombre")]
        return sorted(list(set(lista))) if lista else cat_default
    else:
        conn = sqlite3.connect("inventario.db")
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
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO categorias (nombre) VALUES (?)", (nombre_cat,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()

def eliminar_categoria(nombre_cat):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("categorias").where("nombre", "==", nombre_cat).stream()
        for doc in docs:
            db_cloud.collection("categorias").document(doc.id).delete()
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categorias WHERE nombre = ?", (nombre_cat,))
        conn.commit()
        conn.close()

def obtener_marcas():
    db_cloud = obtener_conexion_db()
    marcas_default = ["Natura", "O Boticário", "Eudora", "Sin Marca / Genérico"]
    if db_cloud is not None:
        docs = db_cloud.collection("marcas").stream()
        lista = [doc.to_dict().get("nombre") for doc in docs if doc.to_dict().get("nombre")]
        return sorted(list(set(lista))) if lista else marcas_default
    else:
        conn = sqlite3.connect("inventario.db")
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
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO marcas (nombre) VALUES (?)", (nombre_marca,))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()

def eliminar_marca(nombre_marca):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("marcas").where("nombre", "==", nombre_marca).stream()
        for doc in docs:
            db_cloud.collection("marcas").document(doc.id).delete()
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM marcas WHERE nombre = ?", (nombre_marca,))
        conn.commit()
        conn.close()

# --- FUNCIONES DE CLIENTES ---
def registrar_cliente(nombre, apellido, ci, telefono, ciudad):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("clientes").add({
            "nombre": nombre.strip(),
            "apellido": apellido.strip(),
            "ci": ci.strip(),
            "telefono": telefono.strip(),
            "ciudad": ciudad.strip()
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clientes (nombre, apellido, ci, telefono, ciudad)
            VALUES (?, ?, ?, ?, ?)
        """, (nombre.strip(), apellido.strip(), ci.strip(), telefono.strip(), ciudad.strip()))
        conn.commit()
        conn.close()

def actualizar_cliente(id_cli, nombre, apellido, ci, telefono, ciudad):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("clientes").document(str(id_cli)).update({
            "nombre": nombre.strip(),
            "apellido": apellido.strip(),
            "ci": ci.strip(),
            "telefono": telefono.strip(),
            "ciudad": ciudad.strip()
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE clientes
            SET nombre = ?, apellido = ?, ci = ?, telefono = ?, ciudad = ?
            WHERE id = ?
        """, (nombre.strip(), apellido.strip(), ci.strip(), telefono.strip(), ciudad.strip(), int(id_cli)))
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
        if not lista:
            return pd.DataFrame(columns=["id", "nombre", "apellido", "ci", "telefono", "ciudad"])
        return pd.DataFrame(lista)
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM clientes", conn)
        conn.close()
        return df

def eliminar_cliente(id_cli):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("clientes").document(str(id_cli)).delete()
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM clientes WHERE id = ?", (int(id_cli),))
        conn.commit()
        conn.close()

# --- FUNCIONES DE PRODUCTOS ---
def registrar_producto(nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("productos").add({
            "nombre": nombre,
            "categoria": categoria,
            "marca": marca,
            "precio_costo": int(precio_costo),
            "ganancia_porcentaje": int(ganancia_porcentaje),
            "precio_venta": int(precio_venta),
            "stock": int(stock),
            "descripcion": descripcion
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO productos (nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion))
        conn.commit()
        conn.close()

def actualizar_producto(id_prod, nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("productos").document(str(id_prod)).update({
            "nombre": nombre,
            "categoria": categoria,
            "marca": marca,
            "precio_costo": int(precio_costo),
            "ganancia_porcentaje": int(ganancia_porcentaje),
            "precio_venta": int(precio_venta),
            "stock": int(stock),
            "descripcion": descripcion
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE productos
            SET nombre = ?, categoria = ?, marca = ?, precio_costo = ?, ganancia_porcentaje = ?, precio_venta = ?, stock = ?, descripcion = ?
            WHERE id = ?
        """, (nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion, int(id_prod)))
        conn.commit()
        conn.close()

def eliminar_producto(id_prod):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("productos").document(str(id_prod)).delete()
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM productos WHERE id = ?", (int(id_prod),))
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
            return pd.DataFrame(columns=["id", "nombre", "categoria", "marca", "precio_costo", "ganancia_porcentaje", "precio_venta", "stock", "descripcion"])
        df = pd.DataFrame(lista)
        if "marca" not in df.columns:
            df["marca"] = "Sin Marca"
        return df
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM productos", conn)
        conn.close()
        if "marca" not in df.columns:
            df["marca"] = "Sin Marca"
        return df

# --- FUNCIONES DE VENTAS Y DEUDAS CLIENTES ---
def registrar_venta(producto_id, producto_nombre, cantidad, precio_unitario, total, tipo_venta, metodo_pago, cliente_nombre="Cliente Ocasional"):
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
            "estado_pago": estado_pago
        })
        doc_ref = db_cloud.collection("productos").document(str(producto_id))
        doc = doc_ref.get()
        if doc.exists:
            stock_actual = doc.to_dict().get("stock", 0)
            doc_ref.update({"stock": max(0, stock_actual - int(cantidad))})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ventas (fecha_hora, producto_id, producto_nombre, cantidad, precio_unitario, total, tipo_venta, metodo_pago, cliente_nombre, estado_pago)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fecha_hora, str(producto_id), producto_nombre, int(cantidad), int(precio_unitario), int(total), tipo_venta, metodo_pago, cliente_nombre, estado_pago))
        
        cursor.execute("""
            UPDATE productos SET stock = stock - ? WHERE id = ?
        """, (int(cantidad), int(producto_id)))
        
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
            return pd.DataFrame(columns=["id", "fecha_hora", "producto_id", "producto_nombre", "cantidad", "precio_unitario", "total", "tipo_venta", "metodo_pago", "cliente_nombre", "estado_pago"])
        df = pd.DataFrame(lista)
        if "tipo_venta" not in df.columns:
            df["tipo_venta"] = "Contado"
        if "estado_pago" not in df.columns:
            df["estado_pago"] = "Pagado"
        if "cliente_nombre" not in df.columns:
            df["cliente_nombre"] = "Cliente Ocasional"
        return df
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM ventas", conn)
        conn.close()
        if "tipo_venta" not in df.columns:
            df["tipo_venta"] = "Contado"
        if "estado_pago" not in df.columns:
            df["estado_pago"] = "Pagado"
        if "cliente_nombre" not in df.columns:
            df["cliente_nombre"] = "Cliente Ocasional"
        return df

def registrar_pago_historial(cliente_nombre, monto, metodo_pago):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if db_cloud is not None:
        db_cloud.collection("pagos_clientes").add({
            "fecha_hora": fecha_hora,
            "cliente_nombre": cliente_nombre,
            "monto": int(monto),
            "metodo_pago": metodo_pago
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pagos_clientes (fecha_hora, cliente_nombre, monto, metodo_pago)
            VALUES (?, ?, ?, ?)
        """, (fecha_hora, cliente_nombre, int(monto), metodo_pago))
        conn.commit()
        conn.close()

def obtener_historial_pagos():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("pagos_clientes").stream()
        lista = [doc.to_dict() for doc in docs]
        if not lista:
            return pd.DataFrame(columns=["fecha_hora", "cliente_nombre", "monto", "metodo_pago"])
        return pd.DataFrame(lista)
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM pagos_clientes ORDER BY id DESC", conn)
        conn.close()
        return df

# --- FUNCIONES DE PROVEEDORES Y COMPRAS ---
def registrar_proveedor(nombre, ruc_ci, telefono, ciudad):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("proveedores").add({
            "nombre": nombre.strip(),
            "ruc_ci": ruc_ci.strip(),
            "telefono": telefono.strip(),
            "ciudad": ciudad.strip()
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO proveedores (nombre, ruc_ci, telefono, ciudad)
            VALUES (?, ?, ?, ?)
        """, (nombre.strip(), ruc_ci.strip(), telefono.strip(), ciudad.strip()))
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
        if not lista:
            return pd.DataFrame(columns=["id", "nombre", "ruc_ci", "telefono", "ciudad"])
        return pd.DataFrame(lista)
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM proveedores", conn)
        conn.close()
        return df

def registrar_compra_proveedor(proveedor_nombre, concepto, monto_total, tipo_compra, metodo_pago):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    estado_pago = "Pendiente" if tipo_compra == "Crédito" else "Pagado"

    if db_cloud is not None:
        db_cloud.collection("compras_proveedores").add({
            "fecha_hora": fecha_hora,
            "proveedor_nombre": proveedor_nombre,
            "concepto": concepto,
            "monto_total": int(monto_total),
            "tipo_compra": tipo_compra,
            "metodo_pago": metodo_pago,
            "estado_pago": estado_pago
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO compras_proveedores (fecha_hora, proveedor_nombre, concepto, monto_total, tipo_compra, metodo_pago, estado_pago)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (fecha_hora, proveedor_nombre, concepto, int(monto_total), tipo_compra, metodo_pago, estado_pago))
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
        if not lista:
            return pd.DataFrame(columns=["id", "fecha_hora", "proveedor_nombre", "concepto", "monto_total", "tipo_compra", "metodo_pago", "estado_pago"])
        return pd.DataFrame(lista)
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM compras_proveedores", conn)
        conn.close()
        return df

def registrar_pago_proveedor(compra_id, proveedor_nombre, monto, metodo_pago):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if db_cloud is not None:
        db_cloud.collection("pagos_proveedores").add({
            "fecha_hora": fecha_hora,
            "compra_id": int(compra_id),
            "proveedor_nombre": proveedor_nombre,
            "monto": int(monto),
            "metodo_pago": metodo_pago
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pagos_proveedores (fecha_hora, compra_id, proveedor_nombre, monto, metodo_pago)
            VALUES (?, ?, ?, ?, ?)
        """, (fecha_hora, int(compra_id), proveedor_nombre, int(monto), metodo_pago))
        conn.commit()
        conn.close()

def obtener_pagos_proveedores():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("pagos_proveedores").stream()
        lista = [doc.to_dict() for doc in docs]
        if not lista:
            return pd.DataFrame(columns=["fecha_hora", "compra_id", "proveedor_nombre", "monto", "metodo_pago"])
        return pd.DataFrame(lista)
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM pagos_proveedores ORDER BY id DESC", conn)
        conn.close()
        return df

def actualizar_estado_compra(compra_id, estado_pago):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("compras_proveedores").document(str(compra_id)).update({"estado_pago": estado_pago})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE compras_proveedores SET estado_pago = ? WHERE id = ?", (estado_pago, int(compra_id)))
        conn.commit()
        conn.close()

# --- FUNCIONES SALIDAS / GASTOS DE CAJA ---
def registrar_salida_caja(motivo, monto, metodo_pago):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if db_cloud is not None:
        db_cloud.collection("salidas_caja").add({
            "fecha_hora": fecha_hora,
            "motivo": motivo,
            "monto": int(monto),
            "metodo_pago": metodo_pago
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO salidas_caja (fecha_hora, motivo, monto, metodo_pago)
            VALUES (?, ?, ?, ?)
        """, (fecha_hora, motivo, int(monto), metodo_pago))
        conn.commit()
        conn.close()

def obtener_salidas_caja():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("salidas_caja").stream()
        lista = [doc.to_dict() for doc in docs]
        if not lista:
            return pd.DataFrame(columns=["fecha_hora", "motivo", "monto", "metodo_pago"])
        return pd.DataFrame(lista)
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM salidas_caja ORDER BY id DESC", conn)
        conn.close()
        return df

# Inicializar almacenamiento
init_db()

def formatear_gs(valor):
    try:
        valor_entero = int(valor)
        cadena_formateada = "{:,}".format(valor_entero)
        return f"Gs. {cadena_formateada.replace(',', '.')}"
    except Exception:
        return f"Gs. {valor}"

st.set_page_config(page_title="Sistema Encanto - Stock & Ventas", layout="wide", page_icon="📦")

st.markdown("""
    <style>
    .main-title {
        font-size: 38px;
        font-weight: bold;
        color: #1E293B;
        margin-bottom: 5px;
    }
    .sub-title {
        font-size: 16px;
        color: #64748B;
        margin-bottom: 25px;
    }
    </style>
""", unsafe_allow_html=True)

# Menú lateral
st.sidebar.title("✨ Sistema Encanto")
st.sidebar.markdown("---")

if obtener_conexion_db() is not None:
    st.sidebar.success("☁️ Conectado a Almacenamiento Permanente")
else:
    st.sidebar.warning("💾 Almacenamiento Temporal (SQLite)")

opcion = st.sidebar.radio(
    "Selecciona una opción:",
    [
        "🛒 Ventas y Cierre de Caja", 
        "🚚 Compras a Proveedores",
        "📈 Flujo de Caja Mensual",
        "💳 Deudas de Clientes",
        "👥 Gestor de Clientes", 
        "📦 Ver Stock / Inventario", 
        "➕ Registrar Producto", 
        "✏️ Editar / Modificar Producto", 
        "🏷️ Gestor de Categorías", 
        "🏢 Gestor de Marcas"
    ],
    captions=[
        "Registrar salidas, gastos y reporte del día", 
        "Registro de facturas, deudas y pagos a proveedores",
        "Reporte completo mensual de ingresos y egresos",
        "Control de fiados y cobro de cuentas",
        "Administrar la lista de clientes", 
        "Control de existencias", 
        "Añadir nuevos artículos", 
        "Actualizar o eliminar registros", 
        "Organizar categorías", 
        "Administrar marcas"
    ]
)

# ------------------------------------------
# VISTA: COMPRAS A PROVEEDORES (NUEVO)
# ------------------------------------------
if opcion == "🚚 Compras a Proveedores":
    st.markdown('<p class="main-title">🚚 Compras a Proveedores y Deudas</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Registra facturas de compra, controla deudas pendientes con proveedores y abonos parciales o totales.</p>', unsafe_allow_html=True)

    tab_compra, tab_deudas, tab_prov = st.tabs(["🛍️ Registrar Compra", "💳 Cuentas por Pagar (Deudas)", "🏢 Directoria de Proveedores"])

    # TAB 1: REGISTRAR COMPRA
    with tab_compra:
        df_prov = obtener_proveedores()
        
        if df_prov.empty:
            st.info("Primero debes registrar al menos un proveedor en la pestaña '🏢 Directoria de Proveedores'.")
        else:
            lista_prov = [f"{r['id']} - {r['nombre']}" for _, r in df_prov.iterrows()]
            
            with st.form("form_registro_compra"):
                st.subheader("Datos de la Compra / Factura")
                prov_sel = st.selectbox("Seleccionar Proveedor:", lista_prov)
                concepto = st.text_input("Concepto / Descripción:", placeholder="Ej: Compra de lote de perfumes Natura o Factura N° 001-002")
                monto_total = st.number_input("Monto Total de la Compra (Gs.):", min_value=1, step=10000, value=100000)
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    tipo_compra = st.radio("Condición de Compra:", ["Contado", "Crédito"], horizontal=True)
                with col_c2:
                    metodo_pago = st.selectbox("Forma de Pago Registrada:", ["Efectivo", "Transferencia / PIX", "A Cuenta / Deuda Pendiente"])

                submitted_compra = st.form_submit_button("💾 Registrar Compra", type="primary")

                if submitted_compra:
                    if not concepto.strip():
                        st.error("Por favor ingresa un concepto para la compra.")
                    else:
                        nombre_prov = prov_sel.split(" - ")[1]
                        registrar_compra_proveedor(nombre_prov, concepto, monto_total, tipo_compra, metodo_pago)
                        st.success(f"✅ Compra registrada correctamente. Condición: {tipo_compra}.")
                        st.rerun()

    # TAB 2: CUENTAS POR PAGAR Y PAGOS PARCIALES/TOTALES
    with tab_deudas:
        st.subheader("💳 Cuentas por Pagar a Proveedores")
        
        df_compras = obtener_compras_proveedores()
        df_pagos = obtener_pagos_proveedores()

        if df_compras.empty:
            st.info("No hay registros de compras.")
        else:
            compras_credito = df_compras[df_compras['tipo_compra'] == 'Crédito']
            
            if compras_credito.empty:
                st.success("🎉 ¡No tienes deudas pendientes con proveedores!")
            else:
                # Calcular saldo por cada compra a crédito
                lista_deudas = []
                for _, row in compras_credito.iterrows():
                    c_id = int(row['id'])
                    monto_factura = int(row['monto_total'])
                    
                    pagos_asoc = df_pagos[df_pagos['compra_id'] == c_id] if not df_pagos.empty else pd.DataFrame()
                    total_pagado = pagos_asoc['monto'].sum() if not pagos_asoc.empty else 0
                    
                    saldo_pendiente = monto_factura - total_pagado
                    
                    if saldo_pendiente > 0:
                        lista_deudas.append({
                            "ID Compra": c_id,
                            "Fecha": row['fecha_hora'],
                            "Proveedor": row['proveedor_nombre'],
                            "Concepto": row['concepto'],
                            "Monto Total": monto_factura,
                            "Total Pagado": total_pagado,
                            "Saldo Pendiente": saldo_pendiente,
                            "Estado": row['estado_pago']
                        })

                df_deudas = pd.DataFrame(lista_deudas)
                
                if df_deudas.empty:
                    st.success("🎉 ¡Todas las compras a crédito han sido completamente saldadas!")
                else:
                    st.write("📋 **Lista de Facturas Pendientes de Pago:**")
                    
                    df_display = df_deudas.copy()
                    df_display['Monto Total'] = df_display['Monto Total'].apply(formatear_gs)
                    df_display['Total Pagado'] = df_display['Total Pagado'].apply(formatear_gs)
                    df_display['Saldo Pendiente'] = df_display['Saldo Pendiente'].apply(formatear_gs)
                    
                    st.dataframe(df_display, use_container_width=True)

                    st.markdown("---")
                    st.subheader("💵 Registrar Pago / Abono (Parcial o Total)")

                    opciones_deuda = [f"ID: {r['ID Compra']} | Prov: {r['Proveedor']} | Conc: {r['Concepto']} | Saldo: {formatear_gs(r['Saldo Pendiente'])}" for _, r in df_deudas.iterrows()]
                    
                    deuda_sel_str = st.selectbox("Selecciona la Factura a Pagado:", opciones_deuda)
                    
                    if deuda_sel_str:
                        id_compra_sel = int(deuda_sel_str.split(" | ")[0].replace("ID: ", ""))
                        info_deuda = df_deudas[df_deudas['ID Compra'] == id_compra_sel].iloc[0]

                        col_p1, col_p2, col_p3 = st.columns(3)
                        with col_p1:
                            monto_abono = st.number_input(
                                "Monto a Abonar (Gs.):", 
                                min_value=1, 
                                max_value=int(info_deuda['Saldo Pendiente']), 
                                value=int(info_deuda['Saldo Pendiente']), 
                                step=5000
                            )
                        with col_p2:
                            metodo_pago_abono = st.selectbox("Método de Pago del Abono:", ["Efectivo", "Transferencia / PIX"])
                        with col_p3:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("💳 Registrar Pago", type="primary", use_container_width=True):
                                registrar_pago_proveedor(id_compra_sel, info_deuda['Proveedor'], monto_abono, metodo_pago_abono)
                                
                                # Verificar si se saldó completamente la deuda
                                nuevo_saldo = info_deuda['Saldo Pendiente'] - monto_abono
                                if nuevo_saldo <= 0:
                                    actualizar_estado_compra(id_compra_sel, "Pagado")
                                    st.success(f"🎉 ¡Factura ID {id_compra_sel} saldada en su totalidad!")
                                else:
                                    st.info(f"✅ Abono registrado. Queda un saldo restante de {formatear_gs(nuevo_saldo)}.")
                                st.rerun()

    # TAB 3: GESTOR DE PROVEEDORES
    with tab_prov:
        st.subheader("🏢 Agregar Nuevo Proveedor")
        with st.form("form_prov"):
            c1, c2 = st.columns(2)
            with c1:
                nom_p = st.text_input("Nombre de la Empresa / Proveedor:")
                ruc_p = st.text_input("RUC o C.I.:")
            with c2:
                tel_p = st.text_input("Teléfono:")
                ciu_p = st.text_input("Ciudad:")

            btn_prov = st.form_submit_button("💾 Guardar Proveedor", type="primary")
            if btn_prov:
                if not nom_p.strip():
                    st.error("El nombre del proveedor es obligatorio.")
                else:
                    registrar_proveedor(nom_p, ruc_p, tel_p, ciu_p)
                    st.success("✅ Proveedor guardado con éxito.")
                    st.rerun()

        st.markdown("---")
        st.subheader("📋 Lista de Proveedores Registrados")
        df_prov_list = obtener_proveedores()
        if not df_prov_list.empty:
            st.dataframe(df_prov_list, use_container_width=True)
        else:
            st.info("No hay proveedores registrados aún.")

# ------------------------------------------
# VISTA: VENTAS Y CIERRE DE CAJA
# ------------------------------------------
if opcion == "🛒 Ventas y Cierre de Caja":
    st.markdown('<p class="main-title">🛒 Ventas y Cierre de Caja</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Registra ventas, gastos de caja y consulta el balance acumulado (con arrastre de saldo).</p>', unsafe_allow_html=True)
    
    tab_venta, tab_salida, tab_cierre = st.tabs(["🛍️ Nueva Venta", "💸 Registrar Salida de Caja", "📊 Cierre de Caja (Arrastre de Saldo)"])
    
    # --- TAB 1: NUEVA VENTA ---
    with tab_venta:
        if "carrito" not in st.session_state:
            st.session_state.carrito = []

        df_productos = obtener_productos()
        df_clientes = obtener_clientes()
        
        if df_productos.empty:
            st.info("No tienes productos registrados en el inventario para vender.")
        else:
            df_con_stock = df_productos[df_productos['stock'] > 0]
            
            if df_con_stock.empty:
                st.warning("⚠️ Todos los productos actualmente se encuentran sin stock disponible.")
            else:
                st.subheader("1️⃣ Agregar productos al carrito")
                
                lista_productos = [f"{row['id']} - {row['nombre']} ({row['marca']}) - Stock: {row['stock']} uds" for _, row in df_con_stock.iterrows()]
                
                col_add1, col_add2, col_add3 = st.columns([3, 1, 1])
                
                with col_add1:
                    prod_seleccionado_str = st.selectbox(
                        "🔍 Busca o selecciona un producto:",
                        options=lista_productos,
                        index=None,
                        placeholder="Haz clic y empieza a escribir...",
                        key="select_venta_prod"
                    )
                
                if prod_seleccionado_str is not None:
                    id_prod_sel = str(prod_seleccionado_str.split(" - ")[0])
                    prod_sel = df_con_stock[df_con_stock['id'].astype(str) == id_prod_sel].iloc[0]
                    
                    cant_en_carrito = sum([item['cantidad'] for item in st.session_state.carrito if str(item['id']) == id_prod_sel])
                    stock_disponible_real = int(prod_sel['stock']) - cant_en_carrito

                    with col_add2:
                        if stock_disponible_real > 0:
                            cantidad_agregar = st.number_input("Cantidad", min_value=1, max_value=stock_disponible_real, value=1, step=1, key="cant_agregar")
                        else:
                            st.warning("Agotado en carrito")
                            cantidad_agregar = 0

                    with col_add3:
                        st.markdown("<br>", unsafe_allow_html=True)
                        btn_deshabilitado = stock_disponible_real <= 0
                        if st.button("➕ Agregar", type="primary", disabled=btn_deshabilitado, use_container_width=True, key="btn_agregar_carrito"):
                            encontrado = False
                            for item in st.session_state.carrito:
                                if str(item['id']) == id_prod_sel:
                                    item['cantidad'] += cantidad_agregar
                                    item['subtotal'] = item['cantidad'] * item['precio_venta']
                                    encontrado = True
                                    break
                            
                            if not encontrado:
                                st.session_state.carrito.append({
                                    "id": id_prod_sel,
                                    "nombre": prod_sel['nombre'],
                                    "precio_venta": int(prod_sel['precio_venta']),
                                    "cantidad": cantidad_agregar,
                                    "subtotal": cantidad_agregar * int(prod_sel['precio_venta'])
                                })
                            st.rerun()

                st.markdown("---")
                st.subheader("2️⃣ Carrito de Compras Actual")

                if not st.session_state.carrito:
                    st.info("🛒 El carrito está vacío. Busca un producto arriba y haz clic en '➕ Agregar'.")
                else:
                    for idx, item in enumerate(st.session_state.carrito):
                        c1, c2, c3, c4, c5 = st.columns([3, 1, 2, 2, 1])
                        with c1:
                            st.markdown(f"**{item['nombre']}**")
                        with c2:
                            st.write(f"Cant: **{item['cantidad']}**")
                        with c3:
                            st.write(f"P.U.: {formatear_gs(item['precio_venta'])}")
                        with c4:
                            st.write(f"Subtotal: **{formatear_gs(item['subtotal'])}**")
                        with c5:
                            if st.button("❌", key=f"del_cart_{idx}"):
                                st.session_state.carrito.pop(idx)
                                st.rerun()

                    total_general = sum(item['subtotal'] for item in st.session_state.carrito)

                    st.markdown("---")
                    col_fin1, col_fin2 = st.columns(2)

                    with col_fin1:
                        lista_opciones_clientes = ["Cliente Ocasional / Anónimo"]
                        if not df_clientes.empty:
                            for _, r_cli in df_clientes.iterrows():
                                lista_opciones_clientes.append(f"{r_cli['nombre']} {r_cli['apellido']} (CI: {r_cli['ci']})")
                        
                        cliente_seleccionado = st.selectbox("👤 Asignar Cliente:", lista_opciones_clientes, key="venta_cliente_sel")
                        tipo_venta = st.radio("📋 Condición de Venta:", ["Contado", "Crédito"], horizontal=True, key="tipo_venta_radio")
                        metodo_pago = st.selectbox("Método de Pago / Registro", ["Efectivo", "Transferencia / PIX", "Tarjeta de Débito/Crédito", "A Cuenta / Fiado"], key="met_pago")
                        
                        if st.button("🗑️ Vaciar Carrito", key="btn_vaciar"):
                            st.session_state.carrito = []
                            st.rerun()

                    with col_fin2:
                        st.markdown("### Total Final a Cobrar:")
                        st.success(f"💰 **{formatear_gs(total_general)}**")
                        
                        if tipo_venta == "Crédito" and cliente_seleccionado == "Cliente Ocasional / Anónimo":
                            st.warning("⚠️ Para ventas a crédito debes seleccionar un cliente registrado.")
                            btn_bloqueado = True
                        else:
                            btn_bloqueado = False

                        if st.button("💳 Finalizar Venta Completa", type="primary", disabled=btn_bloqueado, use_container_width=True, key="btn_finalizar_venta"):
                            for item in st.session_state.carrito:
                                registrar_venta(
                                    item['id'],
                                    item['nombre'],
                                    item['cantidad'],
                                    item['precio_venta'],
                                    item['subtotal'],
                                    tipo_venta,
                                    metodo_pago,
                                    cliente_seleccionado
                                )
                            st.session_state.carrito = []
                            st.success("✅ ¡Venta registrada con éxito!")
                            st.rerun()

    # --- TAB 2: REGISTRAR SALIDA DE CAJA ---
    with tab_salida:
        st.subheader("💸 Registrar Gasto / Salida de Efectivo")
        with st.form("form_salida_caja"):
            motivo_salida = st.text_input("Motivo / Concepto del gasto:", placeholder="Ej: Pago de flete, Compra de insumos, Retiro personal")
            monto_salida = st.number_input("Monto en Gs.:", min_value=1, step=5000, value=10000)
            metodo_salida = st.selectbox("Forma de Pago:", ["Efectivo", "Transferencia / PIX"])
            
            submitted_salida = st.form_submit_button("🔻 Registrar Salida", type="primary")
            if submitted_salida:
                if not motivo_salida.strip():
                    st.error("Debes ingresar un motivo para el gasto.")
                else:
                    registrar_salida_caja(motivo_salida, monto_salida, metodo_salida)
                    st.success(f"✅ Salida de {formatear_gs(monto_salida)} registrada correctamente.")
                    st.rerun()

    # --- TAB 3: CIERRE DE CAJA CON ARRASTRE DE SALDO ---
    with tab_cierre:
        st.subheader("📊 Cierre y Balance de Caja Diario (Opción 1: Arrastre de Saldo)")
        
        fecha_consulta = st.date_input("Selecciona Fecha para la Caja:", date.today())
        fecha_str = fecha_consulta.strftime("%Y-%m-%d")

        # 1. Obtenemos el saldo inicial que viene arrastrado de días anteriores
        saldo_inicial_arrastrado = obtener_saldo_inicial_dia(fecha_str)

        # 2. Obtenemos ventas de la fecha seleccionada
        df_ventas = obtener_ventas()
        ingresos_efectivo = 0
        if not df_ventas.empty and "fecha_hora" in df_ventas.columns:
            ventas_hoy = df_ventas[df_ventas['fecha_hora'].str.startswith(fecha_str)]
            ventas_efectivo = ventas_hoy[(ventas_hoy['tipo_venta'] == 'Contado') & (ventas_hoy['metodo_pago'] == 'Efectivo')]
            ingresos_efectivo += ventas_efectivo['total'].sum()

        # 3. Obtenemos cobros de fiados realizados en efectivo
        df_pagos = obtener_historial_pagos()
        if not df_pagos.empty and "fecha_hora" in df_pagos.columns:
            pagos_hoy = df_pagos[df_pagos['fecha_hora'].str.startswith(fecha_str)]
            pagos_efectivo = pagos_hoy[pagos_hoy['metodo_pago'] == 'Efectivo']
            ingresos_efectivo += pagos_efectivo['monto'].sum()

        # 4. Obtenemos gastos/salidas en efectivo de hoy
        df_salidas = obtener_salidas_caja()
        egresos_efectivo = 0
        if not df_salidas.empty and "fecha_hora" in df_salidas.columns:
            salidas_hoy = df_salidas[df_salidas['fecha_hora'].str.startswith(fecha_str)]
            salidas_efectivo = salidas_hoy[salidas_hoy['metodo_pago'] == 'Efectivo']
            egresos_efectivo += salidas_efectivo['monto'].sum()

        # 5. Cálculo del Saldo Final
        saldo_final_calculado = saldo_inicial_arrastrado + ingresos_efectivo - egresos_efectivo

        # Visualización de los indicadores clave
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📦 Saldo Inicial (Arrastrado)", formatear_gs(saldo_inicial_arrastrado))
        col2.metric("🟢 Ingresos Efectivo Hoy", formatear_gs(ingresos_efectivo))
        col3.metric("🔴 Salidas Efectivo Hoy", formatear_gs(egresos_efectivo))
        col4.metric("💰 Saldo Final para Mañana", formatear_gs(saldo_final_calculado))

        st.markdown("---")
        
        if st.button("🔒 Confirmar y Guardar Cierre de Caja del Día", type="primary"):
            registrar_cierre_diario(fecha_str, saldo_inicial_arrastrado, ingresos_efectivo, egresos_efectivo, saldo_final_calculado)
            st.success(f"✅ Caja del día {fecha_str} cerrada correctamente. Mañana la caja abrirá automáticamente con {formatear_gs(saldo_final_calculado)}.")
