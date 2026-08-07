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

# Intentar importar Google Firestore
try:
    from google.cloud import firestore
    FIRESTORE_DISPONIBLE = True
except ImportError:
    FIRESTORE_DISPONIBLE = False

# ==========================================
# CONSTANTES Y CONFIGURACIÓN DE CONEXIÓN
# ==========================================
def obtener_conexion_db():
    if FIRESTORE_DISPONIBLE and "gcp_service_account" in st.secrets:
        try:
            return firestore.Client.from_service_account_info(dict(st.secrets["gcp_service_account"]))
        except Exception:
            return None
    return None

# ==========================================
# 1. CONTROL DE BASE DE DATOS
# ==========================================
def init_db():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        return
        
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    
    # Productos con Código de Barras
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
    cursor.execute("CREATE TABLE IF NOT EXISTS categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS marcas (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL)")

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

    # Ventas y Pagos Clientes
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

    # Salidas Caja y Cierres
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

    # Datos iniciales
    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT INTO categorias (nombre) VALUES (?)", [("Perfumes",), ("Cosméticos",), ("Cuidado Personal",), ("Crochet",), ("Otros",)])

    cursor.execute("SELECT COUNT(*) FROM marcas")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT INTO marcas (nombre) VALUES (?)", [("Natura",), ("O Boticário",), ("Eudora",), ("Artesanal / Sin Marca",)])

    conn.commit()
    conn.close()

# --- FUNCIONES DE BASE DE DATOS ---
def obtener_saldo_inicial_dia(fecha_hoy_str):
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
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("cierres_caja").document(fecha_str).set({
            "fecha": fecha_str, "saldo_inicial": int(saldo_inicial),
            "ingresos": int(ingresos), "egresos": int(egresos), "saldo_final": int(saldo_final)
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cierres_caja (fecha, saldo_inicial, ingresos, egresos, saldo_final)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(fecha) DO UPDATE SET
                saldo_inicial = excluded.saldo_inicial, ingresos = excluded.ingresos,
                egresos = excluded.egresos, saldo_final = excluded.saldo_final
        """, (fecha_str, int(saldo_inicial), int(ingresos), int(egresos), int(saldo_final)))
        conn.commit()
        conn.close()

def obtener_categorias():
    db_cloud = obtener_conexion_db()
    cat_default = ["Perfumes", "Cosméticos", "Cuidado Personal", "Crochet", "Otros"]
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
    marcas_default = ["Natura", "O Boticário", "Eudora", "Artesanal / Sin Marca"]
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

def registrar_cliente(nombre, apellido, ci, telefono, ciudad):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("clientes").add({"nombre": nombre.strip(), "apellido": apellido.strip(), "ci": ci.strip(), "telefono": telefono.strip(), "ciudad": ciudad.strip()})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO clientes (nombre, apellido, ci, telefono, ciudad) VALUES (?, ?, ?, ?, ?)", (nombre.strip(), apellido.strip(), ci.strip(), telefono.strip(), ciudad.strip()))
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
        return pd.DataFrame(lista) if lista else pd.DataFrame(columns=["id", "nombre", "apellido", "ci", "telefono", "ciudad"])
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM clientes", conn)
        conn.close()
        return df

def registrar_producto(codigo_barras, nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion):
    db_cloud = obtener_conexion_db()
    cod_clean = str(codigo_barras).strip()
    if db_cloud is not None:
        db_cloud.collection("productos").add({
            "codigo_barras": cod_clean, "nombre": nombre, "categoria": categoria, "marca": marca, 
            "precio_costo": int(precio_costo), "ganancia_porcentaje": int(ganancia_porcentaje), 
            "precio_venta": int(precio_venta), "stock": int(stock), "descripcion": descripcion
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO productos (codigo_barras, nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cod_clean, nombre, categoria, marca, int(precio_costo), int(ganancia_porcentaje), int(precio_venta), int(stock), descripcion))
        conn.commit()
        conn.close()

def actualizar_producto(id_prod, codigo_barras, nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion):
    db_cloud = obtener_conexion_db()
    cod_clean = str(codigo_barras).strip()
    if db_cloud is not None:
        db_cloud.collection("productos").document(str(id_prod)).update({
            "codigo_barras": cod_clean, "nombre": nombre, "categoria": categoria, "marca": marca, 
            "precio_costo": int(precio_costo), "ganancia_porcentaje": int(ganancia_porcentaje), 
            "precio_venta": int(precio_venta), "stock": int(stock), "descripcion": descripcion
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE productos
            SET codigo_barras = ?, nombre = ?, categoria = ?, marca = ?, precio_costo = ?, ganancia_porcentaje = ?, precio_venta = ?, stock = ?, descripcion = ?
            WHERE id = ?
        """, (cod_clean, nombre, categoria, marca, int(precio_costo), int(ganancia_porcentaje), int(precio_venta), int(stock), descripcion, int(id_prod)))
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
            return pd.DataFrame(columns=["id", "codigo_barras", "nombre", "categoria", "marca", "precio_costo", "ganancia_porcentaje", "precio_venta", "stock", "descripcion"])
        df = pd.DataFrame(lista)
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM productos", conn)
        conn.close()
        
    if "codigo_barras" not in df.columns: 
        df["codigo_barras"] = ""
    if "marca" not in df.columns: 
        df["marca"] = "Sin Marca"
    return df

def registrar_venta(producto_id, producto_nombre, cantidad, precio_unitario, total, tipo_venta, metodo_pago, cliente_nombre="Cliente Ocasional"):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    estado_pago = "Pendiente" if tipo_venta == "Crédito" else "Pagado"
    
    if db_cloud is not None:
        db_cloud.collection("ventas").add({
            "fecha_hora": fecha_hora, "producto_id": str(producto_id), "producto_nombre": producto_nombre,
            "cantidad": int(cantidad), "precio_unitario": int(precio_unitario), "total": int(total),
            "tipo_venta": tipo_venta, "metodo_pago": metodo_pago, "cliente_nombre": cliente_nombre, "estado_pago": estado_pago
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
        cursor.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (int(cantidad), int(producto_id)))
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
        if "tipo_venta" not in df.columns: df["tipo_venta"] = "Contado"
        if "estado_pago" not in df.columns: df["estado_pago"] = "Pagado"
        if "cliente_nombre" not in df.columns: df["cliente_nombre"] = "Cliente Ocasional"
        return df
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM ventas", conn)
        conn.close()
        if "tipo_venta" not in df.columns: df["tipo_venta"] = "Contado"
        if "estado_pago" not in df.columns: df["estado_pago"] = "Pagado"
        if "cliente_nombre" not in df.columns: df["cliente_nombre"] = "Cliente Ocasional"
        return df

def registrar_pago_historial(cliente_nombre, monto, metodo_pago):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if db_cloud is not None:
        db_cloud.collection("pagos_clientes").add({"fecha_hora": fecha_hora, "cliente_nombre": cliente_nombre, "monto": int(monto), "metodo_pago": metodo_pago})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pagos_clientes (fecha_hora, cliente_nombre, monto, metodo_pago) VALUES (?, ?, ?, ?)", (fecha_hora, cliente_nombre, int(monto), metodo_pago))
        conn.commit()
        conn.close()

def obtener_historial_pagos():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("pagos_clientes").stream()
        lista = [doc.to_dict() for doc in docs]
        return pd.DataFrame(lista) if lista else pd.DataFrame(columns=["fecha_hora", "cliente_nombre", "monto", "metodo_pago"])
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM pagos_clientes ORDER BY id DESC", conn)
        conn.close()
        return df

def registrar_proveedor(nombre, ruc_ci, telefono, ciudad):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("proveedores").add({"nombre": nombre.strip(), "ruc_ci": ruc_ci.strip(), "telefono": telefono.strip(), "ciudad": ciudad.strip()})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO proveedores (nombre, ruc_ci, telefono, ciudad) VALUES (?, ?, ?, ?)", (nombre.strip(), ruc_ci.strip(), telefono.strip(), ciudad.strip()))
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
        return pd.DataFrame(lista) if lista else pd.DataFrame(columns=["id", "nombre", "ruc_ci", "telefono", "ciudad"])
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
            "fecha_hora": fecha_hora, "proveedor_nombre": proveedor_nombre, "concepto": concepto,
            "monto_total": int(monto_total), "tipo_compra": tipo_compra, "metodo_pago": metodo_pago, "estado_pago": estado_pago
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
        return pd.DataFrame(lista) if lista else pd.DataFrame(columns=["id", "fecha_hora", "proveedor_nombre", "concepto", "monto_total", "tipo_compra", "metodo_pago", "estado_pago"])
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM compras_proveedores", conn)
        conn.close()
        return df

def registrar_pago_proveedor(compra_id, proveedor_nombre, monto, metodo_pago):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if db_cloud is not None:
        db_cloud.collection("pagos_proveedores").add({"fecha_hora": fecha_hora, "compra_id": int(compra_id), "proveedor_nombre": proveedor_nombre, "monto": int(monto), "metodo_pago": metodo_pago})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pagos_proveedores (fecha_hora, compra_id, proveedor_nombre, monto, metodo_pago) VALUES (?, ?, ?, ?, ?)", (fecha_hora, int(compra_id), proveedor_nombre, int(monto), metodo_pago))
        conn.commit()
        conn.close()

def obtener_pagos_proveedores():
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("pagos_proveedores").stream()
        lista = [doc.to_dict() for doc in docs]
        return pd.DataFrame(lista) if lista else pd.DataFrame(columns=["fecha_hora", "compra_id", "proveedor_nombre", "monto", "metodo_pago"])
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

# --- FUNCIONES DE SALIDAS DE CAJA (NUEVAS) ---
def registrar_salida_caja(motivo, monto, metodo_pago):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if db_cloud is not None:
        db_cloud.collection("salidas_caja").add({"fecha_hora": fecha_hora, "motivo": motivo, "monto": int(monto), "metodo_pago": metodo_pago})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO salidas_caja (fecha_hora, motivo, monto, metodo_pago) VALUES (?, ?, ?, ?)", (fecha_hora, motivo, int(monto), metodo_pago))
        conn.commit()
        conn.close()

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
            return pd.DataFrame(columns=["id", "fecha_hora", "motivo", "monto", "metodo_pago"])
        df = pd.DataFrame(lista)
        df = df.sort_values(by="fecha_hora", ascending=False)
        return df
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM salidas_caja ORDER BY id DESC", conn)
        conn.close()
        return df

def actualizar_salida_caja(id_salida, motivo, monto, metodo_pago):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("salidas_caja").document(str(id_salida)).update({
            "motivo": motivo, "monto": int(monto), "metodo_pago": metodo_pago
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE salidas_caja
            SET motivo = ?, monto = ?, metodo_pago = ?
            WHERE id = ?
        """, (motivo, int(monto), metodo_pago, int(id_salida)))
        conn.commit()
        conn.close()

def eliminar_salida_caja(id_salida):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("salidas_caja").document(str(id_salida)).delete()
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM salidas_caja WHERE id = ?", (int(id_salida),))
        conn.commit()
        conn.close()

init_db()

def formatear_gs(valor):
    try:
        return f"Gs. {int(valor):,}".replace(",", ".")
    except Exception:
        return f"Gs. {valor}"

st.set_page_config(page_title="Sistema Encanto - Stock & Ventas", layout="wide", page_icon="📦")

st.markdown("""
    <style>
    /* Título principal brillante en Lila */
    .main-title { 
        font-size: 36px !important; 
        font-weight: 800 !important; 
        color: #B19FFB !important; 
        margin-bottom: 10px !important; 
    }
    
    /* Subtítulos en gris claro brillante */
    .sub-title { 
        font-size: 16px !important; 
        color: #E2E8F0 !important; 
        margin-bottom: 25px !important; 
    }

    /* Asegurar que todos los títulos H1, H2, H3 sean Lila */
    h1, h2, h3 {
        color: #B19FFB !important;
    }

    /* Texto general y etiquetas de formulario en blanco radiante */
    label, p, span, div[data-widget-label="true"] {
        color: #FFFFFF !important;
    }
    </style>
""", unsafe_allow_html=True)

# Menú Lateral
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
    ]
)

# ------------------------------------------
# 1. VENTAS Y CIERRE DE CAJA (Con Edición de Salidas)
# ------------------------------------------
if opcion == "🛒 Ventas y Cierre de Caja":
    st.markdown('<p class="main-title">🛒 Ventas y Cierre de Caja</p>', unsafe_allow_html=True)
    tab_venta, tab_salida, tab_edit_salida, tab_cierre = st.tabs([
        "🛍️ Nueva Venta", 
        "💸 Registrar Salida", 
        "✏️ Modificar / Eliminar Salida", 
        "📊 Cierre de Caja"
    ])
    
    with tab_venta:
        if "carrito" not in st.session_state: 
            st.session_state.carrito = []
            
        df_productos = obtener_productos()
        df_clientes = obtener_clientes()
        
        if df_productos.empty:
            st.info("No tienes productos registrados.")
        else:
            df_con_stock = df_productos[df_productos['stock'] > 0]
            if df_con_stock.empty:
                st.warning("⚠️ Todos los productos están sin stock.")
            else:
                st.subheader("1️⃣ Agregar productos al carrito")
                lista_prods = []
                for _, r in df_con_stock.iterrows():
                    cod_str = str(r.get('codigo_barras', '')).strip()
                    prefix_cod = f"[{cod_str}] " if cod_str and cod_str != "nan" else ""
                    lista_prods.append(f"{r['id']} - {prefix_cod}{r['nombre']} ({r['marca']}) - Stock: {r['stock']}")

                col_a1, col_a2, col_a3 = st.columns([3, 1, 1])
                with col_a1:
                    p_sel = st.selectbox("🔍 Buscar por Nombre o Escanear Código de Barras:", lista_prods, index=None, key="select_venta")
                if p_sel:
                    id_p = str(p_sel.split(" - ")[0])
                    p_row = df_con_stock[df_con_stock['id'].astype(str) == id_p].iloc[0]
                    cant_car = sum([item['cantidad'] for item in st.session_state.carrito if str(item['id']) == id_p])
                    stk_disp = int(p_row['stock']) - cant_car
                    with col_a2:
                        cant_add = st.number_input("Cantidad", min_value=1, max_value=max(1, stk_disp), value=1)
                    with col_a3:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("➕ Agregar", type="primary", disabled=stk_disp<=0):
                            st.session_state.carrito.append({
                                "id": id_p, 
                                "nombre": p_row['nombre'], 
                                "precio_venta": int(p_row['precio_venta']), 
                                "cantidad": cant_add, 
                                "subtotal": cant_add * int(p_row['precio_venta'])
                            })
                            st.rerun()

                st.markdown("---")
                st.subheader("2️⃣ Carrito de Compras")
                for idx, item in enumerate(st.session_state.carrito):
                    c1, c2, c3, c4, c5 = st.columns([3, 1, 2, 2, 1])
                    c1.write(f"**{item['nombre']}**")
                    c2.write(f"Cant: {item['cantidad']}")
                    c3.write(formatear_gs(item['precio_venta']))
                    c4.write(formatear_gs(item['subtotal']))
                    if c5.button("❌", key=f"del_{idx}"):
                        st.session_state.carrito.pop(idx)
                        st.rerun()

                if st.session_state.carrito:
                    tot_gen = sum(i['subtotal'] for i in st.session_state.carrito)
                    
                    st.markdown("---")
                    st.subheader("3️⃣ Descuento y Finalización")
                    
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        tipo_desc = st.radio("Tipo de Descuento:", ["Sin Descuento", "Monto en Gs.", "Porcentaje (%)"], horizontal=True)
                    
                    monto_descuento = 0
                    with col_d2:
                        if tipo_desc == "Monto en Gs.":
                            monto_descuento = st.number_input("Monto de Descuento (Gs.):", min_value=0, max_value=tot_gen, value=0, step=1000)
                        elif tipo_desc == "Porcentaje (%)":
                            porc_desc = st.number_input("Porcentaje de Descuento (%):", min_value=0, max_value=100, value=0)
                            monto_descuento = int(tot_gen * (porc_desc / 100))

                    tot_final = max(0, tot_gen - monto_descuento)

                    st.markdown("<br>", unsafe_allow_html=True)
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Subtotal", formatear_gs(tot_gen))
                    m2.metric("Descuento Aplicado", f"- {formatear_gs(monto_descuento)}")
                    m3.metric("Total Final a Cobrar", formatear_gs(tot_final))

                    st.markdown("---")
                    c_opts = ["Cliente Ocasional"] + [f"{r['nombre']} {r['apellido']}" for _, r in df_clientes.iterrows()] if not df_clientes.empty else ["Cliente Ocasional"]
                    cli_s = st.selectbox("Cliente:", c_opts)
                    tipo_v = st.radio("Tipo Venta:", ["Contado", "Crédito"], horizontal=True)
                    met_p = st.selectbox("Método Pago:", ["Efectivo", "Transferencia / PIX", "Tarjeta"])
                    
                    if st.button("💳 Finalizar Venta", type="primary"):
                        factor_desc = tot_final / tot_gen if tot_gen > 0 else 1.0
                        
                        for i in st.session_state.carrito:
                            subtotal_ajustado = int(i['subtotal'] * factor_desc)
                            precio_unit_ajustado = int(subtotal_ajustado / i['cantidad']) if i['cantidad'] > 0 else i['precio_venta']
                            
                            registrar_venta(
                                i['id'], 
                                i['nombre'], 
                                i['cantidad'], 
                                precio_unit_ajustado, 
                                subtotal_ajustado, 
                                tipo_v, 
                                met_p, 
                                cli_s
                            )
                        
                        st.session_state.carrito = []
                        st.success(f"✅ ¡Venta registrada exitosamente por {formatear_gs(tot_final)}!")
                        st.rerun()

    with tab_salida:
        st.subheader("💸 Registrar Nueva Salida de Caja")
        with st.form("form_salida"):
            mot = st.text_input("Motivo de Salida:")
            monto = st.number_input("Monto en Gs.:", min_value=1, value=10000)
            met = st.selectbox("Forma de Pago:", ["Efectivo", "Transferencia / PIX"])
            if st.form_submit_button("Guardar Salida", type="primary") and mot:
                registrar_salida_caja(mot, monto, met)
                st.success("✅ Salida de caja registrada con éxito.")
                st.rerun()

    with tab_edit_salida:
        st.subheader("✏️ Modificar o Eliminar Salida Registrada")
        df_salidas = obtener_salidas_caja()
        
        if df_salidas.empty:
            st.info("No hay salidas de caja registradas para modificar.")
        else:
            opciones_salida = [
                f"{r['id']} - {r['fecha_hora']} | {r['motivo']} | {formatear_gs(r['monto'])}" 
                for _, r in df_salidas.iterrows()
            ]
            
            salida_sel = st.selectbox("Selecciona la Salida a Editar:", opciones_salida)
            
            if salida_sel:
                id_sal_sel = str(salida_sel.split(" - ")[0])
                salida_row = df_salidas[df_salidas['id'].astype(str) == id_sal_sel].iloc[0]
                
                with st.form("form_editar_salida"):
                    nuevo_mot = st.text_input("Motivo:", value=salida_row['motivo'])
                    nuevo_monto = st.number_input("Monto (Gs.):", min_value=1, value=int(salida_row['monto']))
                    
                    metodos = ["Efectivo", "Transferencia / PIX"]
                    idx_met = metodos.index(salida_row['metodo_pago']) if salida_row['metodo_pago'] in metodos else 0
                    nuevo_met = st.selectbox("Forma de Pago:", metodos, index=idx_met)
                    
                    col_b1, col_b2 = st.columns(2)
                    with col_b1:
                        btn_guardar_salida = st.form_submit_button("💾 Guardar Cambios", type="primary")
                    with col_b2:
                        btn_eliminar_salida = st.form_submit_button("🗑️ Eliminar Salida")

                    if btn_guardar_salida:
                        actualizar_salida_caja(id_sal_sel, nuevo_mot, nuevo_monto, nuevo_met)
                        st.success("✅ Salida corregida correctamente.")
                        st.rerun()
                        
                    if btn_eliminar_salida:
                        eliminar_salida_caja(id_sal_sel)
                        st.warning("⚠️ Salida eliminada correctamente.")
                        st.rerun()

    with tab_cierre:
        st.subheader("📊 Balance Diario")
        f_caja = st.date_input("Fecha:", date.today()).strftime("%Y-%m-%d")
        s_ini = obtener_saldo_inicial_dia(f_caja)
        
        df_v = obtener_ventas()
        ing_ef = 0
        if not df_v.empty and "fecha_hora" in df_v.columns:
            v_hoy = df_v[df_v['fecha_hora'].str.startswith(f_caja)]
            ing_ef += v_hoy[(v_hoy['tipo_venta']=='Contado') & (v_hoy['metodo_pago']=='Efectivo')]['total'].sum()

        df_sal = obtener_salidas_caja()
        egr_ef = 0
        if not df_sal.empty and "fecha_hora" in df_sal.columns:
            egr_ef += df_sal[df_sal['fecha_hora'].str.startswith(f_caja) & (df_sal['metodo_pago']=='Efectivo')]['monto'].sum()

        s_fin = s_ini + ing_ef - egr_ef
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Inicial Arrastrado", formatear_gs(s_ini))
        c2.metric("Ingresos Efectivo", formatear_gs(ing_ef))
        c3.metric("Egresos Efectivo", formatear_gs(egr_ef))
        c4.metric("Saldo Final", formatear_gs(s_fin))

        if st.button("🔒 Guardar Cierre Diario", type="primary"):
            registrar_cierre_diario(f_caja, s_ini, ing_ef, egr_ef, s_fin)
            st.success("Cierre guardado exitosamente!")

# ------------------------------------------
# 2. COMPRAS A PROVEEDORES
# ------------------------------------------
elif opcion == "🚚 Compras a Proveedores":
    st.markdown('<p class="main-title">🚚 Compras a Proveedores</p>', unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["🛍️ Registrar Compra", "💳 Cuentas por Pagar", "🏢 Proveedores"])
    
    with tab1:
        df_p = obtener_proveedores()
        if df_p.empty: st.info("Registra proveedores primero.")
        else:
            with st.form("form_compra_p"):
                prov = st.selectbox("Proveedor:", df_p['nombre'].tolist())
                con = st.text_input("Concepto / Factura:")
                tot = st.number_input("Monto Total Gs.:", min_value=1, value=100000)
                tipo = st.radio("Tipo:", ["Contado", "Crédito"], horizontal=True)
                met = st.selectbox("Método:", ["Efectivo", "Transferencia / PIX"])
                if st.form_submit_button("Guardar Compra") and con:
                    registrar_compra_proveedor(prov, con, tot, tipo, met)
                    st.success("Compra Registrada.")
                    st.rerun()

    with tab2:
        st.subheader("Deudas a Proveedores")
        df_cp = obtener_compras_proveedores()
        df_pp = obtener_pagos_proveedores()
        if not df_cp.empty:
            cred = df_cp[df_cp['tipo_compra'] == 'Crédito']
            if cred.empty: st.success("🎉 No tienes deudas con proveedores.")
            else:
                deudas = []
                for _, r in cred.iterrows():
                    c_id = int(r['id'])
                    pagado = df_pp[df_pp['compra_id']==c_id]['monto'].sum() if not df_pp.empty else 0
                    saldo = int(r['monto_total']) - pagado
                    if saldo > 0:
                        deudas.append({"ID": c_id, "Proveedor": r['proveedor_nombre'], "Concepto": r['concepto'], "Monto": r['monto_total'], "Saldo": saldo})
                
                df_d = pd.DataFrame(deudas)
                if not df_d.empty:
                    st.dataframe(df_d, use_container_width=True)
                    sel_d = st.selectbox("Abonar a Compra ID:", df_d['ID'].tolist())
                    monto_ab = st.number_input("Monto Abono:", min_value=1, value=int(df_d[df_d['ID']==sel_d]['Saldo'].iloc[0]))
                    met_ab = st.selectbox("Forma de Pago:", ["Efectivo", "Transferencia / PIX"])
                    if st.button("Pagar Abono", type="primary"):
                        prov_n = df_d[df_d['ID']==sel_d]['Proveedor'].iloc[0]
                        registrar_pago_proveedor(sel_d, prov_n, monto_ab, met_ab)
                        if (df_d[df_d['ID']==sel_d]['Saldo'].iloc[0] - monto_ab) <= 0:
                            actualizar_estado_compra(sel_d, "Pagado")
                        st.success("Abono registrado.")
                        st.rerun()
                else: st.success("🎉 Todas las deudas saldadas.")

    with tab3:
        with st.form("f_prov"):
            n = st.text_input("Nombre Proveedor:")
            r = st.text_input("RUC:")
            t = st.text_input("Teléfono:")
            c = st.text_input("Ciudad:")
            if st.form_submit_button("Guardar Proveedor") and n:
                registrar_proveedor(n, r, t, c)
                st.success("Proveedor agregado.")
                st.rerun()
        st.dataframe(obtener_proveedores(), use_container_width=True)

# ------------------------------------------
# 3. FLUJO DE CAJA MENSUAL
# ------------------------------------------
elif opcion == "📈 Flujo de Caja Mensual":
    st.markdown('<p class="main-title">📈 Flujo de Caja Mensual</p>', unsafe_allow_html=True)
    mes_sel = st.date_input("Selecciona un día del mes a consultar:", date.today())
    prefix_mes = mes_sel.strftime("%Y-%m")
    
    df_v = obtener_ventas()
    ing_mes = df_v[df_v['fecha_hora'].str.startswith(prefix_mes)]['total'].sum() if not df_v.empty else 0
    
    df_s = obtener_salidas_caja()
    egr_mes = df_s[df_s['fecha_hora'].str.startswith(prefix_mes)]['monto'].sum() if not df_s.empty else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("🟢 Total Ingresos Ventas", formatear_gs(ing_mes))
    c2.metric("🔴 Total Gastos / Salidas", formatear_gs(egr_mes))
    c3.metric("💰 Balance Neto", formatear_gs(ing_mes - egr_mes))

# ------------------------------------------
# 4. DEUDAS DE CLIENTES
# ------------------------------------------
elif opcion == "💳 Deudas de Clientes":
    st.markdown('<p class="main-title">💳 Deudas de Clientes (Fiados)</p>', unsafe_allow_html=True)
    df_v = obtener_ventas()
    df_p = obtener_historial_pagos()
    
    if not df_v.empty:
        cred = df_v[df_v['tipo_venta'] == 'Crédito']
        if cred.empty:
            st.success("🎉 No hay ventas a crédito registradas.")
        else:
            deudores = cred['cliente_nombre'].unique()
            resumen = []
            for d in deudores:
                tot_fiado = cred[cred['cliente_nombre']==d]['total'].sum()
                tot_pago = df_p[df_p['cliente_nombre']==d]['monto'].sum() if not df_p.empty else 0
                s_pen = tot_fiado - tot_pago
                if s_pen > 0:
                    resumen.append({"Cliente": d, "Total Fiado": tot_fiado, "Total Pagado": tot_pago, "Saldo Pendiente": s_pen})
            
            df_res = pd.DataFrame(resumen)
            if not df_res.empty:
                st.dataframe(df_res, use_container_width=True)
                st.subheader("Cobrar Deuda")
                cli_cobro = st.selectbox("Cliente:", df_res['Cliente'].tolist())
                monto_cob = st.number_input("Monto a Cobrar:", min_value=1, value=int(df_res[df_res['Cliente']==cli_cobro]['Saldo Pendiente'].iloc[0]))
                met_cob = st.selectbox("Forma de Cobro:", ["Efectivo", "Transferencia / PIX"])
                if st.button("Registrar Cobro", type="primary"):
                    registrar_pago_historial(cli_cobro, monto_cob, met_cob)
                    st.success("Cobro guardado!")
                    st.rerun()
            else: st.success("🎉 Todas las cuentas de clientes están al día.")

# ------------------------------------------
# 5. GESTOR DE CLIENTES
# ------------------------------------------
elif opcion == "👥 Gestor de Clientes":
    st.markdown('<p class="main-title">👥 Gestor de Clientes</p>', unsafe_allow_html=True)
    with st.form("form_cli"):
        n = st.text_input("Nombre:")
        a = st.text_input("Apellido:")
        c = st.text_input("CI / Doc:")
        t = st.text_input("Teléfono:")
        ciu = st.text_input("Ciudad:")
        if st.form_submit_button("Guardar Cliente") and n:
            registrar_cliente(n, a, c, t, ciu)
            st.success("Cliente guardado!")
            st.rerun()
    st.dataframe(obtener_clientes(), use_container_width=True)

# ------------------------------------------
# 6. VER STOCK / INVENTARIO
# ------------------------------------------
elif opcion == "📦 Ver Stock / Inventario":
    st.markdown('<p class="main-title">📦 Inventario de Productos</p>', unsafe_allow_html=True)
    df_p = obtener_productos()
    if not df_p.empty:
        st.dataframe(df_p, use_container_width=True)
    else:
        st.info("No hay productos registrados.")

# ------------------------------------------
# 7. REGISTRAR PRODUCTO (Con Código de Barras)
# ------------------------------------------
elif opcion == "➕ Registrar Producto":
    st.markdown('<p class="main-title">➕ Registrar Nuevo Producto</p>', unsafe_allow_html=True)
    cats = obtener_categorias()
    marcas = obtener_marcas()
    
    with st.form("form_p_new"):
        cod_barras = st.text_input("📦 Código de Barras (Escanear o escribir manualmente):")
        nom = st.text_input("Nombre Producto:")
        cat = st.selectbox("Categoría:", cats)
        mar = st.selectbox("Marca:", marcas)
        costo = st.number_input("Precio Costo Gs.:", min_value=0, value=10000)
        gan = st.number_input("% Ganancia:", min_value=0, value=30)
        p_venta = int(costo * (1 + gan/100))
        st.info(f"Precio Venta Calculado: {formatear_gs(p_venta)}")
        stk = st.number_input("Stock Inicial:", min_value=0, value=1)
        desc = st.text_area("Descripción:")
        
        if st.form_submit_button("Guardar Producto") and nom:
            registrar_producto(cod_barras, nom, cat, mar, costo, gan, p_venta, stk, desc)
            st.success("¡Producto guardado con éxito!")
            st.rerun()

# ------------------------------------------
# 8. EDITAR / MODIFICAR PRODUCTO
# ------------------------------------------
elif opcion == "✏️ Editar / Modificar Producto":
    st.markdown('<p class="main-title">✏️ Editar Producto</p>', unsafe_allow_html=True)
    df_p = obtener_productos()
    if not df_p.empty:
        p_list = [f"{r['id']} - {r['nombre']}" for _, r in df_p.iterrows()]
        p_sel = st.selectbox("Selecciona Producto a Modificar:", p_list)
        id_p = p_sel.split(" - ")[0]
        p_row = df_p[df_p['id'].astype(str) == str(id_p)].iloc[0]
        
        with st.form("form_e_prod"):
            cod_barras = st.text_input("📦 Código de Barras:", value=str(p_row.get('codigo_barras', '')))
            nom = st.text_input("Nombre:", value=p_row['nombre'])
            cat = st.selectbox("Categoría:", obtener_categorias(), index=0)
            mar = st.selectbox("Marca:", obtener_marcas(), index=0)
            costo = st.number_input("Precio Costo Gs.:", value=int(p_row['precio_costo']))
            gan = st.number_input("% Ganancia:", value=int(p_row['ganancia_porcentaje']))
            p_v = int(costo * (1 + gan/100))
            st.info(f"Precio Venta: {formatear_gs(p_v)}")
            stk = st.number_input("Stock:", value=int(p_row['stock']))
            desc = st.text_area("Descripción:", value=str(p_row['descripcion']))
            
            c1, c2 = st.columns(2)
            if c1.form_submit_button("💾 Actualizar"):
                actualizar_producto(id_p, cod_barras, nom, cat, mar, costo, gan, p_v, stk, desc)
                st.success("Producto actualizado!")
                st.rerun()
            if c2.form_submit_button("🗑️ Eliminar Producto"):
                eliminar_producto(id_p)
                st.warning("Producto eliminado.")
                st.rerun()

# ------------------------------------------
# 9. GESTOR DE CATEGORÍAS
# ------------------------------------------
elif opcion == "🏷️ Gestor de Categorías":
    st.markdown('<p class="main-title">🏷️ Gestor de Categorías</p>', unsafe_allow_html=True)
    new_cat = st.text_input("Nueva Categoría:")
    if st.button("Agregar Categoría") and new_cat:
        registrar_categoria(new_cat)
        st.success("Categoría agregada.")
        st.rerun()
    st.markdown("---")
    for c in obtener_categorias():
        col_c1, col_c2 = st.columns([4, 1])
        col_c1.write(f"• **{c}**")
        if col_c2.button("Eliminar", key=f"cat_{c}"):
            eliminar_categoria(c)
            st.rerun()

# ------------------------------------------
# 10. GESTOR DE MARCAS
# ------------------------------------------
elif opcion == "🏢 Gestor de Marcas":
    st.markdown('<p class="main-title">🏢 Gestor de Marcas</p>', unsafe_allow_html=True)
    new_m = st.text_input("Nueva Marca:")
    if st.button("Agregar Marca") and new_m:
        registrar_marca(new_m)
        st.success("Marca agregada.")
        st.rerun()
    st.markdown("---")
    for m in obtener_marcas():
        col_m1, col_m2 = st.columns([4, 1])
        col_m1.write(f"• **{m}**")
        if col_m2.button("Eliminar", key=f"mar_{m}"):
            eliminar_marca(m)
            st.rerun()
