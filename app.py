from datetime import date, datetime
import sqlite3
import pandas as pd
import streamlit as st

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
    conn = sqlite3.connect("inventario.db")
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


# --- FUNCIONES DE BASE DE DATOS ---
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
        conn = sqlite3.connect("inventario.db")
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
        conn = sqlite3.connect("inventario.db")
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


def obtener_cierre_por_fecha(fecha_str):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        doc = db_cloud.collection("cierres_caja").document(fecha_str).get()
        return doc.to_dict() if doc.exists else None
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT fecha, saldo_inicial, ingresos, egresos, saldo_final FROM"
            " cierres_caja WHERE fecha = ?",
            (fecha_str,),
        )
        row = cursor.fetchone()
        conn.close()
        return (
            {
                "fecha": row[0],
                "saldo_inicial": row[1],
                "ingresos": row[2],
                "egresos": row[3],
                "saldo_final": row[4],
            }
            if row
            else None
        )


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
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM categorias WHERE nombre = ?", (nombre_cat,)
        )
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
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM marcas WHERE nombre = ?", (nombre_marca,))
        conn.commit()
        conn.close()


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
        conn = sqlite3.connect("inventario.db")
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
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM clientes", conn)
        conn.close()
        return df


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
        conn = sqlite3.connect("inventario.db")
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
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM proveedores", conn)
        conn.close()
        return df


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
        conn = sqlite3.connect("inventario.db")
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
        conn = sqlite3.connect("inventario.db")
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
                int(id_prod),
            ),
        )
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
            return pd.DataFrame(
                columns=[
                    "id",
                    "codigo_barras",
                    "nombre",
                    "categoria",
                    "marca",
                    "precio_costo",
                    "ganancia_porcentaje",
                    "precio_venta",
                    "stock",
                    "descripcion",
                ]
            )
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
        conn = sqlite3.connect("inventario.db")
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
            (int(cantidad), int(producto_id)),
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


def registrar_compra_proveedor(
    proveedor_nombre, concepto, monto_total, tipo_compra, metodo_pago
):
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
            "estado_pago": estado_pago,
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO compras_proveedores (fecha_hora, proveedor_nombre, concepto, monto_total, tipo_compra, metodo_pago, estado_pago)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                fecha_hora,
                proveedor_nombre,
                concepto,
                int(monto_total),
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
                    "tipo_compra",
                    "metodo_pago",
                    "estado_pago",
                ]
            )
        )
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM compras_proveedores", conn)
        conn.close()
        return df


def registrar_pago_proveedor(
    compra_id, proveedor_nombre, monto, metodo_pago
):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if db_cloud is not None:
        db_cloud.collection("pagos_proveedores").add({
            "fecha_hora": fecha_hora,
            "compra_id": str(compra_id),
            "proveedor_nombre": proveedor_nombre,
            "monto": int(monto),
            "metodo_pago": metodo_pago,
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pagos_proveedores (fecha_hora, compra_id,"
            " proveedor_nombre, monto, metodo_pago) VALUES (?, ?, ?, ?, ?)",
            (
                fecha_hora,
                int(compra_id),
                proveedor_nombre,
                int(monto),
                metodo_pago,
            ),
        )
        conn.commit()
        conn.close()


def actualizar_estado_compra(compra_id, estado_pago):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("compras_proveedores").document(
            str(compra_id)
        ).update({"estado_pago": estado_pago})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE compras_proveedores SET estado_pago = ? WHERE id = ?",
            (estado_pago, int(compra_id)),
        )
        conn.commit()
        conn.close()


def registrar_salida_caja(motivo, monto, metodo_pago):
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if db_cloud is not None:
        db_cloud.collection("salidas_caja").add({
            "fecha_hora": fecha_hora,
            "motivo": motivo,
            "monto": int(monto),
            "metodo_pago": metodo_pago,
        })
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO salidas_caja (fecha_hora, motivo, monto, metodo_pago)"
            " VALUES (?, ?, ?, ?)",
            (fecha_hora, motivo, int(monto), metodo_pago),
        )
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
            return pd.DataFrame(
                columns=["id", "fecha_hora", "motivo", "monto", "metodo_pago"]
            )
        df = pd.DataFrame(lista)
        return df.sort_values(by="fecha_hora", ascending=False)
    else:
        conn = sqlite3.connect("inventario.db")
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
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE salidas_caja
            SET motivo = ?, monto = ?, metodo_pago = ?
            WHERE id = ?
        """,
            (motivo, int(monto), metodo_pago, int(id_salida)),
        )
        conn.commit()
        conn.close()


def eliminar_salida_caja(id_salida):
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        db_cloud.collection("salidas_caja").document(str(id_salida)).delete()
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM salidas_caja WHERE id = ?", (int(id_salida),)
        )
        conn.commit()
        conn.close()


# Inicialización
init_db()


def formatear_gs(valor):
    try:
        return f"Gs. {int(valor):,}".replace(",", ".")
    except Exception:
        return f"Gs. {valor}"


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
        "🏬 Gestor de Proveedores",
        "🚚 Compras a Proveedores",
        "📜 Deudas con Proveedores",
        "💳 Deudas de Clientes",
        "👥 Gestor de Clientes",
        "📈 Flujo de Caja Mensual",
        "📦 Ver Stock / Inventario",
        "➕ Registrar Producto",
        "✏️ Editar / Modificar Producto",
        "🏷️ Gestor de Categorías",
        "🏢 Gestor de Marcas",
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
                lista_prods = []
                for _, r in df_con_stock.iterrows():
                    cod_str = str(r.get("codigo_barras", "")).strip()
                    prefix_cod = (
                        f"[{cod_str}] " if cod_str and cod_str != "nan" else ""
                    )
                    lista_prods.append(
                        f"{r['id']} - {prefix_cod}{r['nombre']}"
                        f" ({r['marca']}) - Stock: {r['stock']}"
                    )

                col_a1, col_a2, col_a3 = st.columns([3, 1, 1])
                with col_a1:
                    p_sel = st.selectbox(
                        "🔍 Buscar o Escanear Código:",
                        lista_prods,
                        index=None,
                        key="select_v",
                    )
                
                        if p_sel:
                    id_p = str(p_sel.split(" - ")[0])
                    p_row = df_con_stock[
                        df_con_stock["id"].astype(str) == id_p
                    ].iloc[0]

                    # Calcular cuánto de este producto ya está en el carrito
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
                        st.write("")  # Espaciador para alinear el botón
                        st.write("")
                        if st.button("➕ Agregar", type="primary"):
                            if cant <= stock_disp:
                                st.session_state.carrito.append({
                                    "id": id_p,
                                    "nombre": p_row["nombre"],
                                    "precio_unitario": p_row["precio_venta"],
                                    "cantidad": cant,
                                    "subtotal": p_row["precio_venta"] * cant,
                                })
                                st.success("¡Producto agregado al carrito!")
                                st.rerun()
                            else:
                                st.error("⚠️ Stock insuficiente disponible.")
                                
                            st.session_state.carrito.append({
                                "id": id_p,
                                "nombre": p_row["nombre"],
                                "precio_venta": int(p_row["precio_venta"]),
                                "cantidad": cant_add,
                                "subtotal": cant_add
                                * int(p_row["precio_venta"]),
                            })
                            st.rerun()

                st.markdown("---")
                st.subheader("2️⃣ Carrito de Compras")
                if st.session_state.carrito:
                    total_carrito = 0
                    for idx, item in enumerate(st.session_state.carrito):
                        c1, c2, c3, c4, c5 = st.columns([3, 1, 2, 2, 1])
                        c1.write(f"**{item['nombre']}**")
                        c2.write(f"Cant: {item['cantidad']}")
                        c3.write(formatear_gs(item["precio_venta"]))
                        c4.write(f"Subtotal: {formatear_gs(item['subtotal'])}")
                        total_carrito += item["subtotal"]
                        if c5.button("❌", key=f"del_{idx}"):
                            st.session_state.carrito.pop(idx)
                            st.rerun()

                    st.markdown("---")
                    st.markdown(
                        f"### Total a Cobrar: **{formatear_gs(total_carrito)}**"
                    )

                    col_c1, col_c2, col_c3 = st.columns(3)
                    with col_c1:
                        tipo_v = st.selectbox(
                            "Tipo de Venta:", ["Contado", "Crédito"]
                        )
                    with col_c2:
                        metodo_p = st.selectbox(
                            "Método de Pago:",
                            ["Efectivo", "Transferencia / QR", "Tarjeta"],
                        )
                    with col_c3:
                        cli_opts = ["Cliente Ocasional"]
                        if not df_clientes.empty:
                            cli_opts += [
                                f"{r['nombre']} {r['apellido']}"
                                for _, r in df_clientes.iterrows()
                            ]
                        cliente_v = st.selectbox("Cliente:", cli_opts)

                    if st.button("✅ Finalizar Venta", type="primary"):
                        for item in st.session_state.carrito:
                            registrar_venta(
                                item["id"],
                                item["nombre"],
                                item["cantidad"],
                                item["precio_venta"],
                                item["subtotal"],
                                tipo_v,
                                metodo_p,
                                cliente_v,
                            )
                        st.session_state.carrito = []
                        st.success("🎉 Venta registrada con éxito.")
                        st.rerun()

    # ==========================================
    # SALIDAS DE CAJA (REGISTRO + EDICIÓN Y ELIMINACIÓN)
    # ==========================================
    with tab_salida:
        st.subheader("💸 Registrar Salida de Caja")
        with st.form("form_salida"):
            motivo_s = st.text_input("Motivo:")
            monto_s = st.number_input("Monto (Gs.):", min_value=1, step=1000)
            metodo_s = st.selectbox(
                "Método:", ["Efectivo", "Transferencia / QR", "Tarjeta"]
            )
            if (
                st.form_submit_button("Registrar Salida", type="primary")
                and motivo_s
            ):
                registrar_salida_caja(motivo_s, monto_s, metodo_s)
                st.success("Salida registrada correctamente.")
                st.rerun()

        st.markdown("---")
        st.subheader("✏️ Historial y Edición de Salidas")
        df_salidas = obtener_salidas_caja()

        if df_salidas.empty:
            st.info("No hay salidas de caja registradas.")
        else:
            st.dataframe(df_salidas, use_container_width=True)

            opts_salidas = [
                f"{r['id']} - {r['motivo']} | {formatear_gs(r['monto'])} |"
                f" {r['fecha_hora']}"
                for _, r in df_salidas.iterrows()
            ]
            salida_sel = st.selectbox(
                "Selecciona una salida para Modificar o Eliminar:", opts_salidas
            )

            if salida_sel:
                id_sal = salida_sel.split(" - ")[0]
                row_sal = df_salidas[
                    df_salidas["id"].astype(str) == str(id_sal)
                ].iloc[0]

                col_es1, col_es2, col_es3 = st.columns(3)
                with col_es1:
                    edit_motivo = st.text_input(
                        "Motivo:",
                        value=row_sal["motivo"],
                        key=f"edit_m_{id_sal}",
                    )
                with col_es2:
                    edit_monto = st.number_input(
                        "Monto (Gs.):",
                        min_value=1,
                        value=int(row_sal["monto"]),
                        key=f"edit_mo_{id_sal}",
                    )
                with col_es3:
                    metodos_lista = ["Efectivo", "Transferencia / QR", "Tarjeta"]
                    idx_m = (
                        metodos_lista.index(row_sal["metodo_pago"])
                        if row_sal["metodo_pago"] in metodos_lista
                        else 0
                    )
                    edit_metodo = st.selectbox(
                        "Método:",
                        metodos_lista,
                        index=idx_m,
                        key=f"edit_me_{id_sal}",
                    )

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Guardar Cambios", type="primary"):
                        actualizar_salida_caja(
                            id_sal, edit_motivo, edit_monto, edit_metodo
                        )
                        st.success("Salida actualizada con éxito.")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Eliminar Salida"):
                        eliminar_salida_caja(id_sal)
                        st.warning("Salida de caja eliminada.")
                        st.rerun()

    with tab_cierre:
        fecha_hoy_str = date.today().strftime("%Y-%m-%d")
        st.subheader(f"📊 Resumen de Caja ({fecha_hoy_str})")
        saldo_ini = obtener_saldo_inicial_dia(fecha_hoy_str)
        df_ventas = obtener_ventas()
        df_salidas = obtener_salidas_caja()

        ingresos_hoy = (
            df_ventas[
                (df_ventas["fecha_hora"].str.startswith(fecha_hoy_str))
                & (df_ventas["estado_pago"] == "Pagado")
            ]["total"].sum()
            if not df_ventas.empty
            else 0
        )
        egresos_hoy = (
            df_salidas[df_salidas["fecha_hora"].str.startswith(fecha_hoy_str)][
                "monto"
            ].sum()
            if not df_salidas.empty
            else 0
        )
        saldo_final_calc = saldo_ini + ingresos_hoy - egresos_hoy

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Saldo Inicial", formatear_gs(saldo_ini))
        k2.metric("Ingresos Hoy", formatear_gs(ingresos_hoy))
        k3.metric("Egresos Hoy", formatear_gs(egresos_hoy))
        k4.metric("Saldo Final", formatear_gs(saldo_final_calc))

        if st.button("🔒 Confirmar y Cerrar Caja", type="primary"):
            registrar_cierre_diario(
                fecha_hoy_str,
                saldo_ini,
                ingresos_hoy,
                egresos_hoy,
                saldo_final_calc,
            )
            st.success("Cierre del día guardado.")

    with tab_historico:
        st.subheader("📅 Histórico de Cierres")
        fecha_h = st.date_input("Selecciona una fecha:", date.today())
        cierre = obtener_cierre_por_fecha(fecha_h.strftime("%Y-%m-%d"))
        if cierre:
            st.success(f"Cierre de fecha {fecha_h}:")
            h1, h2, h3, h4 = st.columns(4)
            h1.metric("Inicial", formatear_gs(cierre["saldo_inicial"]))
            h2.metric("Ingresos", formatear_gs(cierre["ingresos"]))
            h3.metric("Egresos", formatear_gs(cierre["egresos"]))
            h4.metric("Final", formatear_gs(cierre["saldo_final"]))
        else:
            st.info("Sin registros de cierre para la fecha elegida.")

# ==========================================
# GESTOR DE PROVEEDORES
# ==========================================
elif opcion == "🏬 Gestor de Proveedores":
    st.markdown(
        '<p class="main-title">🏬 Gestor de Proveedores</p>',
        unsafe_allow_html=True,
    )
    st.subheader("➕ Registrar Nuevo Proveedor")
    with st.form("form_prov"):
        nom = st.text_input("Nombre / Razón Social:")
        ruc = st.text_input("RUC / CI:")
        tel = st.text_input("Teléfono:")
        ciu = st.text_input("Ciudad:")
        if st.form_submit_button("Guardar Proveedor", type="primary"):
            if nom:
                registrar_proveedor(nom, ruc, tel, ciu)
                st.success(
                    f"Proveedor '{nom}' registrado. ¡Ya puedes seleccionarlo"
                    " en Compras!"
                )
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Lista de Proveedores Registrados")
    df_p = obtener_proveedores()
    if df_p.empty:
        st.info("Aún no tienes proveedores registrados.")
    else:
        st.dataframe(df_p, use_container_width=True)

# ==========================================
# DEUDAS CON PROVEEDORES / CUENTAS POR PAGAR
# ==========================================
elif opcion == "📜 Deudas con Proveedores":
    st.markdown(
        '<p class="main-title">📜 Deudas por Pagar a Proveedores</p>',
        unsafe_allow_html=True,
    )
    df_compras = obtener_compras_proveedores()

    if df_compras.empty:
        st.info("No hay registros de compras.")
    else:
        df_pendientes = df_compras[df_compras["estado_pago"] == "Pendiente"]
        if df_pendientes.empty:
            st.success("🎉 ¡Felicidades! No tienes deudas pendientes con ningún proveedor.")
        else:
            st.warning(
                f"⚠️ Tienes {len(df_pendientes)} compras pendientes de pago."
            )
            st.dataframe(df_pendientes, use_container_width=True)

            st.markdown("---")
            st.subheader("💵 Registrar Pago / Saldar Deuda a Proveedor")
            opts = [
                f"{r['id']} | {r['proveedor_nombre']} | Concepto: {r['concepto']}"
                f" | Total: {formatear_gs(r['monto_total'])}"
                for _, r in df_pendientes.iterrows()
            ]
            c_sel = st.selectbox("Selecciona la compra a saldar:", opts)

            if c_sel:
                compra_id = c_sel.split(" | ")[0]
                row_c = df_pendientes[
                    df_pendientes["id"].astype(str) == str(compra_id)
                ].iloc[0]

                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    monto_pago = st.number_input(
                        "Monto a Pagar (Gs.):",
                        min_value=1,
                        max_value=int(row_c["monto_total"]),
                        value=int(row_c["monto_total"]),
                    )
                with col_p2:
                    metodo_pago = st.selectbox(
                        "Método de Pago:", ["Efectivo", "Transferencia / QR"]
                    )

                if st.button("✅ Registrar Pago y Saldar", type="primary"):
                    registrar_pago_proveedor(
                        compra_id,
                        row_c["proveedor_nombre"],
                        monto_pago,
                        metodo_pago,
                    )
                    registrar_salida_caja(
                        f"Pago Proveedor {row_c['proveedor_nombre']} (Compra #{compra_id})",
                        monto_pago,
                        metodo_pago,
                    )
                    actualizar_estado_compra(compra_id, "Pagado")
                    st.success("Pago registrado y cargado a salidas de caja.")
                    st.rerun()

# ==========================================
# RESTO DEL CÓDIGO (COMPRAS, PRODUCCIÓN, ETC.)
# ==========================================
elif opcion == "🚚 Compras a Proveedores":
    st.markdown(
        '<p class="main-title">🚚 Registrar Compras a Proveedores</p>',
        unsafe_allow_html=True,
    )
    df_prov = obtener_proveedores()
    if df_prov.empty:
        st.warning(
            "⚠️ Primero debes registrar al menos un proveedor en la opción"
            " '🏬 Gestor de Proveedores'."
        )
    else:
        with st.form("form_compra"):
            prov = st.selectbox("Proveedor:", df_prov["nombre"].tolist())
            conc = st.text_input("Concepto / Mercadería:")
            monto = st.number_input("Monto Total (Gs.):", min_value=1)
            tipo_c = st.selectbox(
                "Tipo de Compra:",
                ["Contado", "Crédito"],
                help=(
                    "Si eliges Crédito, irá automáticamente al módulo 'Deudas"
                    " con Proveedores'"
                ),
            )
            metodo = st.selectbox(
                "Método Pago:", ["Efectivo", "Transferencia / QR"]
            )
            if (
                st.form_submit_button("Registrar Compra", type="primary")
                and conc
            ):
                registrar_compra_proveedor(prov, conc, monto, tipo_c, metodo)
                if tipo_c == "Contado":
                    registrar_salida_caja(
                        f"Compra Contado: {conc} ({prov})", monto, metodo
                    )
                st.success("Compra registrada correctamente.")
                st.rerun()

elif opcion == "📦 Ver Stock / Inventario":
    st.markdown(
        '<p class="main-title">📦 Ver Stock / Inventario</p>',
        unsafe_allow_html=True,
    )
    df = obtener_productos()
    st.dataframe(df, use_container_width=True)

elif opcion == "➕ Registrar Producto":
    st.markdown(
        '<p class="main-title">➕ Registrar Producto</p>', unsafe_allow_html=True
    )
    cats = obtener_categorias()
    marcas = obtener_marcas()
    with st.form("form_prod"):
        cod_b = st.text_input("Código de Barras:")
        nom = st.text_input("Nombre:")
        cat = st.selectbox("Categoría:", cats)
        mar = st.selectbox("Marca:", marcas)
        p_costo = st.number_input("Precio Costo (Gs.):", min_value=0, step=1000)
        p_gan = st.number_input("Ganancia (%)", min_value=0, value=30)
        p_venta = p_costo * (1 + p_gan / 100)
        st.write(f"**Precio Venta Calculado:** {formatear_gs(p_venta)}")
        stk = st.number_input("Stock Inicial:", min_value=0, value=1)
        desc = st.text_area("Descripción:")
        if st.form_submit_button("Guardar Producto", type="primary") and nom:
            registrar_producto(
                cod_b, nom, cat, mar, p_costo, p_gan, p_venta, stk, desc
            )
            st.success("Producto registrado.")
            st.rerun()

elif opcion == "✏️ Editar / Modificar Producto":
    st.markdown(
        '<p class="main-title">✏️ Editar Producto</p>', unsafe_allow_html=True
    )
    df_p = obtener_productos()
    if not df_p.empty:
        opts = [f"{r['id']} - {r['nombre']}" for _, r in df_p.iterrows()]
        p_sel = st.selectbox("Selecciona un producto:", opts)
        if p_sel:
            id_p = p_sel.split(" - ")[0]
            row = df_p[df_p["id"].astype(str) == id_p].iloc[0]
            cats = obtener_categorias()
            marcas = obtener_marcas()

            cod_b = st.text_input("Código:", value=str(row["codigo_barras"]))
            nom = st.text_input("Nombre:", value=row["nombre"])
            cat = st.selectbox(
                "Categoría:",
                cats,
                index=cats.index(row["categoria"])
                if row["categoria"] in cats
                else 0,
            )
            mar = st.selectbox(
                "Marca:",
                marcas,
                index=marcas.index(row["marca"])
                if row["marca"] in marcas
                else 0,
            )
            p_costo = st.number_input(
                "Precio Costo:", min_value=0, value=int(row["precio_costo"])
            )
            p_gan = st.number_input(
                "Ganancia (%):",
                min_value=0,
                value=int(row["ganancia_porcentaje"]),
            )
            p_venta = p_costo * (1 + p_gan / 100)
            st.write(f"**Precio Venta:** {formatear_gs(p_venta)}")
            stk = st.number_input(
                "Stock:", min_value=0, value=int(row["stock"])
            )
            desc = st.text_area("Descripción:", value=str(row["descripcion"]))

            col_e1, col_e2 = st.columns(2)
            with col_e1:
                if st.button("💾 Actualizar", type="primary"):
                    actualizar_producto(
                        id_p,
                        cod_b,
                        nom,
                        cat,
                        mar,
                        p_costo,
                        p_gan,
                        p_venta,
                        stk,
                        desc,
                    )
                    st.success("Producto actualizado.")
                    st.rerun()
            with col_e2:
                if st.button("🗑️ Eliminar"):
                    eliminar_producto(id_p)
                    st.warning("Producto eliminado.")
                    st.rerun()

elif opcion == "🏷️ Gestor de Categorías":
    st.markdown(
        '<p class="main-title">🏷️ Gestor de Categorías</p>',
        unsafe_allow_html=True,
    )
    nova_c = st.text_input("Nueva Categoría:")
    if st.button("Agregar Categoría", type="primary") and nova_c:
        registrar_categoria(nova_c)
        st.success("Categoría agregada.")
        st.rerun()
    cats = obtener_categorias()
    cat_del = st.selectbox("Eliminar Categoría:", cats)
    if st.button("Eliminar Categoría") and cat_del:
        eliminar_categoria(cat_del)
        st.warning("Categoría eliminada.")
        st.rerun()

elif opcion == "🏢 Gestor de Marcas":
    st.markdown(
        '<p class="main-title">🏢 Gestor de Marcas</p>', unsafe_allow_html=True
    )
    nova_m = st.text_input("Nueva Marca:")
    if st.button("Agregar Marca", type="primary") and nova_m:
        registrar_marca(nova_m)
        st.success("Marca agregada.")
        st.rerun()
    marcas = obtener_marcas()
    mar_del = st.selectbox("Eliminar Marca:", marcas)
    if st.button("Eliminar Marca") and mar_del:
        eliminar_marca(mar_del)
        st.warning("Marca eliminada.")
        st.rerun()

elif opcion == "👥 Gestor de Clientes":
    st.markdown(
        '<p class="main-title">👥 Gestor de Clientes</p>', unsafe_allow_html=True
    )
    with st.form("form_cli"):
        nom = st.text_input("Nombre:")
        ape = st.text_input("Apellido:")
        ci = st.text_input("RUC / CI:")
        tel = st.text_input("Teléfono:")
        ciu = st.text_input("Ciudad:")
        if st.form_submit_button("Guardar Cliente", type="primary") and nom:
            registrar_cliente(nom, ape, ci, tel, ciu)
            st.success("Cliente guardado.")
            st.rerun()
    st.dataframe(obtener_clientes(), use_container_width=True)

elif opcion == "💳 Deudas de Clientes":
    st.markdown(
        '<p class="main-title">💳 Deudas de Clientes (Cuentas por Cobrar)</p>',
        unsafe_allow_html=True,
    )
    df_ventas = obtener_ventas()
    if not df_ventas.empty:
        df_credito = df_ventas[df_ventas["tipo_venta"] == "Crédito"]
        st.dataframe(df_credito, use_container_width=True)
    else:
        st.info("No hay ventas a crédito registradas.")

elif opcion == "📈 Flujo de Caja Mensual":
    st.markdown(
        '<p class="main-title">📈 Flujo de Caja Mensual</p>',
        unsafe_allow_html=True,
    )
    df_v = obtener_ventas()
    df_s = obtener_salidas_caja()
    tot_v = df_v["total"].sum() if not df_v.empty else 0
    tot_s = df_s["monto"].sum() if not df_s.empty else 0

    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Total Ingresos Ventas", formatear_gs(tot_v))
    col_m2.metric("Total Egresos / Gastos", formatear_gs(tot_s))
