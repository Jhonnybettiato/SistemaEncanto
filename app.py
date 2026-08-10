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
        "CREATE TABLE IF NOT EXISTS categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS marcas (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE NOT NULL)"
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
            "SELECT saldo_final FROM cierres_caja WHERE fecha < ? ORDER BY fecha DESC LIMIT 1",
            (fecha_hoy_str,),
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0


def registrar_cierre_diario(fecha_str, saldo_inicial, ingresos, egresos, saldo_final):
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
            "SELECT fecha, saldo_inicial, ingresos, egresos, saldo_final FROM cierres_caja WHERE fecha = ?",
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
            "INSERT INTO clientes (nombre, apellido, ci, telefono, ciudad) VALUES (?, ?, ?, ?, ?)",
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
            "INSERT INTO proveedores (nombre, ruc_ci, telefono, ciudad) VALUES (?, ?, ?, ?)",
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


def registrar_pago_proveedor(compra_id, proveedor_nombre, monto, metodo_pago):
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
            "INSERT INTO pagos_proveedores (fecha_hora, compra_id, proveedor_nombre, monto, metodo_pago) VALUES (?, ?, ?, ?, ?)",
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
            "INSERT INTO salidas_caja (fecha_hora, motivo, monto, metodo_pago) VALUES (?, ?, ?, ?)",
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
# Menú Lateral
st.sidebar.title("✨ Sistema Encanto")
st.sidebar.markdown("---")

opcion = st.sidebar.radio(
    "Selecciona una opción:",
    [
        "🛒 Ventas y Cierre de Caja",
        "🏬 Gestor de Proveedores",  # <-- Ahora reúne todo lo de proveedores
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
                
                # Diccionario para ocultar el ID de Firestore en el texto
                opciones_dict = {}
                for _, r in df_con_stock.iterrows():
                    cod_str = str(r.get("codigo_barras", "")).strip()
                    prefix_cod = (
                        f"[{cod_str}] " if cod_str and cod_str != "nan" and cod_str != "" else ""
                    )
                    # Texto limpio para mostrar en pantalla
                    label = f"{prefix_cod}{r['nombre']} ({r['marca']}) - Stock: {r['stock']}"
                    opciones_dict[label] = r['id']

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
                                    "precio_unitario": int(p_row["precio_venta"]),
                                    "cantidad": cant,
                                    "subtotal": int(p_row["precio_venta"]) * cant,
                                })
                                st.success("¡Producto agregado al carrito!")
                                st.rerun()
                            else:
                                st.error("⚠️ Stock insuficiente disponible.")

        st.markdown("---")
        st.subheader("2️⃣ Carrito de Compras")

        if st.session_state.carrito:
            df_car = pd.DataFrame(st.session_state.carrito)
            df_car_show = df_car[["nombre", "cantidad", "precio_unitario", "subtotal"]].copy()
            df_car_show["precio_unitario"] = df_car_show["precio_unitario"].apply(formatear_gs)
            df_car_show["subtotal"] = df_car_show["subtotal"].apply(formatear_gs)

            st.dataframe(df_car_show, use_container_width=True)

            subtotal_venta = sum(item["subtotal"] for item in st.session_state.carrito)

            # --- SECCIÓN DE DESCUENTO EN GUARANÍES ---
            col_des1, col_des2 = st.columns([1, 2])
            with col_des1:
                descuento = st.number_input(
                    "🏷️ Descuento (Gs.):",
                    min_value=0,
                    max_value=subtotal_venta,
                    value=0,
                    step=1000,
                    key="descuento_v"
                )

            monto_total_venta = subtotal_venta - descuento

            # Muestra de Totales
            if descuento > 0:
                st.markdown(f"Subtotal: ~~{formatear_gs(subtotal_venta)}~~ | Descuento: -{formatear_gs(descuento)}")
            
            st.markdown(f"### Total Final: **{formatear_gs(monto_total_venta)}**")

            col_c1, col_c2, col_c3 = st.columns([2, 2, 1])
            with col_c1:
                tipo_venta = st.selectbox("Tipo de Venta:", ["Contado", "Crédito"])
                
                lista_clientes = ["Cliente Ocasional"]
                if not df_clientes.empty:
                    lista_clientes += [
                        f"{r['nombre']} {r['apellido']} (CI: {r['ci']})"
                        for _, r in df_clientes.iterrows()
                    ]
                cliente_sel = st.selectbox("Cliente:", lista_clientes)

            with col_c2:
                metodo_pago = st.selectbox("Método de Pago:", ["Efectivo", "Transferencia", "Tarjeta", "Giros / Otro"])

            with col_c3:
                st.write("")
                st.write("")
                if st.button("✅ Finalizar Venta", type="primary"):
                    # Calcular proporcionadamente el precio con descuento o pasarlo directamente
                    for item in st.session_state.carrito:
                        # Si deseas registrar el total global con descuento aplicado
                        registrar_venta(
                            producto_id=item["id"],
                            producto_nombre=item["nombre"],
                            cantidad=item["cantidad"],
                            precio_unitario=item["precio_unitario"],
                            total=item["subtotal"] - int(descuento * (item["subtotal"] / subtotal_venta)),
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
            metodo = st.selectbox("Método de Pago:", ["Efectivo", "Transferencia", "Tarjeta", "Otro"])
            if st.form_submit_button("Registrar Salida", type="primary"):
                if motivo.strip():
                    registrar_salida_caja(motivo, monto, metodo)
                    st.success("Salida de caja registrada.")
                    st.rerun()
                else:
                    st.warning("Escribe el motivo de la salida.")

        st.markdown("---")
        st.subheader("Histórico de Salidas")
        df_salidas = obtener_salidas_caja()
        if not df_salidas.empty:
            df_salidas_show = df_salidas.copy()
            df_salidas_show["monto"] = df_salidas_show["monto"].apply(formatear_gs)
            st.dataframe(df_salidas_show, use_container_width=True)

    with tab_cierre:
        hoy_str = datetime.now().strftime("%Y-%m-%d")
        st.subheader(f"Cierre de Caja - Fecha: {hoy_str}")

        saldo_ini = obtener_saldo_inicial_dia(hoy_str)
        df_ventas = obtener_ventas()
        
        # Filtrar ventas de hoy
        if not df_ventas.empty and "fecha_hora" in df_ventas.columns:
            df_ventas_hoy = df_ventas[
                (df_ventas["fecha_hora"].str.startswith(hoy_str)) & 
                (df_ventas["estado_pago"] == "Pagado")
            ]
            total_ingresos = df_ventas_hoy["total"].sum() if not df_ventas_hoy.empty else 0
        else:
            total_ingresos = 0

        df_salidas = obtener_salidas_caja()
        if not df_salidas.empty and "fecha_hora" in df_salidas.columns:
            df_salidas_hoy = df_salidas[df_salidas["fecha_hora"].str.startswith(hoy_str)]
            total_egresos = df_salidas_hoy["monto"].sum() if not df_salidas_hoy.empty else 0
        else:
            total_egresos = 0

        saldo_final = saldo_ini + total_ingresos - total_egresos

        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        col_k1.metric("Saldo Inicial", formatear_gs(saldo_ini))
        col_k2.metric("Ingresos (Hoy)", formatear_gs(total_ingresos))
        col_k3.metric("Egresos (Hoy)", formatear_gs(total_egresos))
        col_k4.metric("Saldo Final Calculado", formatear_gs(saldo_final))

        if st.button("🔒 Confirmar y Guardar Cierre de Hoy", type="primary"):
            registrar_cierre_diario(hoy_str, saldo_ini, total_ingresos, total_egresos, saldo_final)
            st.success("¡Cierre guardado correctamente!")

    with tab_historico:
        st.subheader("Cierres de Caja Guardados")
        db_cloud = obtener_conexion_db()
        if db_cloud is not None:
            docs = db_cloud.collection("cierres_caja").stream()
            cierres = [d.to_dict() for d in docs]
            df_cierres = pd.DataFrame(cierres)
        else:
            conn = sqlite3.connect("inventario.db")
            df_cierres = pd.read_sql_query("SELECT * FROM cierres_caja ORDER BY fecha DESC", conn)
            conn.close()

        if not df_cierres.empty:
            df_cierres_show = df_cierres.copy()
            for c in ["saldo_inicial", "ingresos", "egresos", "saldo_final"]:
                if c in df_cierres_show.columns:
                    df_cierres_show[c] = df_cierres_show[c].apply(formatear_gs)
            st.dataframe(df_cierres_show, use_container_width=True)
        else:
            st.info("No hay cierres de caja registrados aún.")

# ==========================================
# GESTOR DE PROVEEDORES
# ==========================================
# ==========================================
# GESTOR DE PROVEEDORES (COMPLETO)
# ==========================================
elif opcion == "🏬 Gestor de Proveedores":
    st.markdown('<p class="main-title">🏬 Gestor de Proveedores</p>', unsafe_allow_html=True)
    
    tab_prov, tab_compras, tab_deudas = st.tabs([
        "👤 Registro / Proveedores", 
        "🚚 Registrar Compra", 
        "📜 Deudas por Pagar"
    ])

    # ---------------------------------------------------------
    # TAB 1: REGISTRO Y LISTA DE PROVEEDORES
    # ---------------------------------------------------------
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
            st.dataframe(df_prov, use_container_width=True)
        else:
            st.info("No hay proveedores registrados aún.")

    # ---------------------------------------------------------
    # TAB 2: REGISTRAR COMPRA A PROVEEDOR
    # ---------------------------------------------------------
    with tab_compras:
        st.subheader("Registrar Compra a Proveedor")
        df_prov = obtener_proveedores()
        
        if df_prov.empty:
            st.warning("⚠️ Primero debes registrar al menos un proveedor en la pestaña anterior.")
        else:
            with st.form("form_compra_prov"):
                prov_sel = st.selectbox("Seleccionar Proveedor:", df_prov["nombre"].tolist())
                concepto = st.text_input("Concepto / Descripción de la compra:")
                monto = st.number_input("Monto Total (Gs.):", min_value=1, step=5000)
                tipo_compra = st.selectbox("Tipo de Compra:", ["Contado", "Crédito"])
                metodo_pago = st.selectbox("Método de Pago:", ["Efectivo", "Transferencia", "Tarjeta", "Giros / Otro"])
                
                if st.form_submit_button("🚚 Registrar Compra", type="primary"):
                    if concepto.strip():
                        # Si es Contado se guarda pagado, si es Crédito queda Pendiente
                        estado_pago = "Pagado" if tipo_compra == "Contado" else "Pendiente"
                        
                        registrar_compra_proveedor(
                            proveedor=prov_sel, 
                            concepto=concepto, 
                            monto=monto, 
                            tipo_compra=tipo_compra, 
                            metodo_pago=metodo_pago,
                            estado_pago=estado_pago
                        )
                        st.success("¡Compra a proveedor registrada exitosamente!")
                        st.rerun()
                    else:
                        st.warning("Por favor ingresa un concepto o descripción para la compra.")

            st.markdown("---")
            st.subheader("📋 Historial de Compras")
            df_compras = obtener_compras_proveedores()
            if not df_compras.empty:
                df_show = df_compras.copy()
                if "monto_total" in df_show.columns:
                    df_show["monto_total"] = df_show["monto_total"].apply(formatear_gs)
                st.dataframe(df_show, use_container_width=True)

    # ---------------------------------------------------------
    # TAB 3: DEUDAS Y PAGOS (PARCIALES Y TOTALES)
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # TAB 3: DEUDAS Y PAGOS (PARCIALES Y TOTALES)
    # ---------------------------------------------------------
    with tab_deudas:
        st.subheader("📜 Deudas Pendientes con Proveedores")
        df_compras = obtener_compras_proveedores()
        
        if not df_compras.empty:
            # Filtrar las compras que no están 100% pagadas
            if "estado_pago" in df_compras.columns:
                deudas = df_compras[df_compras["estado_pago"].isin(["Pendiente", "Parcial"])].copy()
            else:
                deudas = pd.DataFrame()

            if not deudas.empty:
                # Asegurar columnas numéricas para el saldo
                deudas["monto_total"] = deudas["monto_total"].fillna(0).astype(int)
                if "monto_pagado" not in deudas.columns:
                    deudas["monto_pagado"] = 0
                else:
                    deudas["monto_pagado"] = deudas["monto_pagado"].fillna(0).astype(int)

                deudas["saldo_pendiente"] = deudas["monto_total"] - deudas["monto_pagado"]

                # Mostrar tabla con formato visual
                df_show_deudas = deudas.copy()
                df_show_deudas["monto_total"] = df_show_deudas["monto_total"].apply(formatear_gs)
                df_show_deudas["monto_pagado"] = df_show_deudas["monto_pagado"].apply(formatear_gs)
                df_show_deudas["saldo_pendiente"] = df_show_deudas["saldo_pendiente"].apply(formatear_gs)

                st.dataframe(df_show_deudas, use_container_width=True)

                st.markdown("---")
                st.subheader("💵 Registrar Pago / Entrega")

                # Diccionario seguro (evita KeyError si no encuentra la columna 'proveedor')
                dict_deudas = {}
                for _, r in deudas.iterrows():
                    nombre_prov = r.get('proveedor', r.get('proveedor_nombre', r.get('nombre_proveedor', 'Proveedor')))
                    label = f"ID: {r['id']} | {nombre_prov} | Saldo: {formatear_gs(r['saldo_pendiente'])}"
                    dict_deudas[label] = r['id']

                compra_sel_label = st.selectbox("Selecciona la compra a pagar:", options=list(dict_deudas.keys()))
                
                if compra_sel_label:
                    id_compra_sel = dict_deudas[compra_sel_label]
                    compra_row = deudas[deudas["id"] == id_compra_sel].iloc[0]

                    saldo_actual = int(compra_row["saldo_pendiente"])
                    monto_pagado_actual = int(compra_row["monto_pagado"])
                    monto_total_original = int(compra_row["monto_total"])
                    prov_nombre_final = compra_row.get('proveedor', compra_row.get('proveedor_nombre', 'Proveedor'))

                    col_p1, col_p2 = st.columns(2)
                    col_p1.metric("Monto Total Compra", formatear_gs(monto_total_original))
                    col_p2.metric("Saldo Pendiente Actual", formatear_gs(saldo_actual))

                    with st.form("form_pago_proveedor"):
                        monto_a_pagar = st.number_input(
                            "Monto a Abonar (Gs.):", 
                            min_value=1, 
                            max_value=max(1, saldo_actual), 
                            value=saldo_actual, 
                            step=5000,
                            help="Puedes ingresar el monto total para cancelar la deuda o un monto menor para un pago parcial."
                        )
                        metodo_pago_deuda = st.selectbox("Método de Pago:", ["Efectivo", "Transferencia", "Tarjeta", "Otro"])

                        if st.form_submit_button("✅ Confirmar Pago", type="primary"):
                            nuevo_monto_pagado = monto_pagado_actual + monto_a_pagar
                            
                            if nuevo_monto_pagado >= monto_total_original:
                                nuevo_estado = "Pagado"
                            else:
                                nuevo_estado = "Parcial"

                            # Actualizar registro en BD
                            actualizar_pago_compra_proveedor(
                                id_compra=id_compra_sel, 
                                nuevo_monto_pagado=nuevo_monto_pagado, 
                                nuevo_estado=nuevo_estado
                            )

                            # Registrar la salida de caja
                            registrar_salida_caja(
                                motivo=f"Pago deuda proveedor {prov_nombre_final} (ID Compra: {id_compra_sel})",
                                monto=monto_a_pagar,
                                metodo=metodo_pago_deuda
                            )

                            st.success(f"¡Pago de {formatear_gs(monto_a_pagar)} registrado con éxito! Estado: {nuevo_estado}")
                            st.rerun()
            else:
                st.success("🎉 ¡No hay deudas pendientes con proveedores!")
        else:
            st.info("No hay registro de compras aún.")

# ==========================================
# DEUDAS DE CLIENTES
# ==========================================
elif opcion == "💳 Deudas de Clientes":
    st.markdown('<p class="main-title">💳 Deudas de Clientes</p>', unsafe_allow_html=True)
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
# ==========================================
# GESTOR DE CLIENTES (REGISTRO Y EDICIÓN)
# ==========================================
elif opcion == "👥 Gestor de Clientes":
    st.markdown('<p class="main-title">👥 Gestor de Clientes</p>', unsafe_allow_html=True)
    
    tab_nuevo_c, tab_editar_c, tab_lista_c = st.tabs([
        "➕ Registrar Cliente", 
        "✏️ Editar / Modificar Cliente", 
        "📋 Ver Lista de Clientes"
    ])

    df_clientes = obtener_clientes()

    # --- Pestaña 1: Registrar Cliente ---
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

    # --- Pestaña 2: Editar / Modificar Cliente ---
    with tab_editar_c:
        st.subheader("Modificar Datos de un Cliente")
        if df_clientes.empty:
            st.info("No hay clientes registrados para editar.")
        else:
            # Creamos la lista para el desplegable
            dict_clientes = {}
            for _, r in df_clientes.iterrows():
                label = f"{r['nombre']} {r['apellido']} (CI: {r['ci']})"
                dict_clientes[label] = r['id']

            cliente_sel_label = st.selectbox(
                "🔍 Selecciona un cliente para modificar:",
                options=list(dict_clientes.keys()),
                index=None,
                key="select_edit_cliente"
            )

            if cliente_sel_label:
                id_cliente = dict_clientes[cliente_sel_label]
                c_row = df_clientes[df_clientes["id"].astype(str) == str(id_cliente)].iloc[0]

                with st.form("form_edit_cliente"):
                    col1, col2 = st.columns(2)
                    edit_nombre = col1.text_input("Nombre:", value=str(c_row.get("nombre", "")))
                    edit_apellido = col2.text_input("Apellido:", value=str(c_row.get("apellido", "")))
                    edit_ci = col1.text_input("N° Documento / CI:", value=str(c_row.get("ci", "")))
                    edit_telefono = col2.text_input("Teléfono:", value=str(c_row.get("telefono", "")))
                    edit_ciudad = st.text_input("Ciudad:", value=str(c_row.get("ciudad", "")))

                    col_btn1, col_btn2 = st.columns([1, 1])
                    if col_btn1.form_submit_button("💾 Guardar Cambios", type="primary"):
                        if edit_nombre.strip() and edit_apellido.strip():
                            # Llamada a la función de actualización
                            actualizar_cliente(id_cliente, edit_nombre, edit_apellido, edit_ci, edit_telefono, edit_ciudad)
                            st.success("¡Datos del cliente actualizados correctamente!")
                            st.rerun()
                        else:
                            st.warning("El Nombre y Apellido no pueden quedar vacíos.")

    # --- Pestaña 3: Lista de Clientes ---
    with tab_lista_c:
        st.subheader("Listado General de Clientes")
        if not df_clientes.empty:
            st.dataframe(df_clientes, use_container_width=True)
        else:
            st.info("No hay clientes registrados.")

# ==========================================
# FLUJO DE CAJA MENSUAL
# ==========================================
elif opcion == "📈 Flujo de Caja Mensual":
    st.markdown('<p class="main-title">📈 Flujo de Caja Mensual</p>', unsafe_allow_html=True)
    df_ventas = obtener_ventas()
    df_salidas = obtener_salidas_caja()
    
    col1, col2 = st.columns(2)
    ingresos_totales = df_ventas[df_ventas["estado_pago"] == "Pagado"]["total"].sum() if not df_ventas.empty else 0
    egresos_totales = df_salidas["monto"].sum() if not df_salidas.empty else 0
    
    col1.metric("Ingresos Históricos Totales", formatear_gs(ingresos_totales))
    col2.metric("Egresos Históricos Totales", formatear_gs(egresos_totales))

# ==========================================
# VER STOCK / INVENTARIO
# ==========================================
elif opcion == "📦 Ver Stock / Inventario":
    st.markdown('<p class="main-title">📦 Ver Stock / Inventario</p>', unsafe_allow_html=True)
    
    # Cargamos los productos actualizados
    df_stock = obtener_productos()
    
    if not df_stock.empty:
        columnas_ordenadas = [
            'codigo_barras', 
            'nombre', 
            'precio_venta', 
            'categoria', 
            'marca', 
            'ganancia_porcentaje', 
            'precio_costo', 
            'descripcion', 
            'id'
        ]
        cols_existentes = [col for col in columnas_ordenadas if col in df_stock.columns]
        st.dataframe(df_stock[cols_existentes], use_container_width=True)
    else:
        st.info("No hay productos en el inventario.")

# ==========================================
# REGISTRAR PRODUCTO
# ==========================================
elif opcion == "➕ Registrar Producto":
    st.markdown('<p class="main-title">➕ Registrar Producto</p>', unsafe_allow_html=True)
    cats = obtener_categorias()
    marcas = obtener_marcas()

    with st.form("form_reg_prod"):
        col1, col2 = st.columns(2)
        cod_barras = col1.text_input("Código de Barras:")
        nombre = col2.text_input("Nombre del Producto:")
        cat = col1.selectbox("Categoría:", cats)
        marca = col2.selectbox("Marca:", marcas)
        costo = col1.number_input("Precio Costo (Gs.):", min_value=0, step=1000)
        ganancia = col2.number_input("% Ganancia:", min_value=0, value=30)
        
        precio_sugerido = int(costo + (costo * (ganancia / 100)))
        precio_venta = col1.number_input("Precio Venta (Gs.):", min_value=0, value=precio_sugerido, step=1000)
        stock = col2.number_input("Stock Inicial:", min_value=0, value=1)
        desc = st.text_area("Descripción:")

        if st.form_submit_button("Guardar Producto", type="primary"):
            if nombre.strip():
                registrar_producto(cod_barras, nombre, cat, marca, costo, ganancia, precio_venta, stock, desc)
                st.success("¡Producto registrado exitosamente!")
                st.rerun()
            else:
                st.warning("El nombre del producto es obligatorio.")

# ==========================================
# EDITAR / MODIFICAR PRODUCTO
# ==========================================
elif opcion == "✏️ Editar / Modificar Producto":
    st.markdown('<p class="main-title">✏️ Editar / Modificar Producto</p>', unsafe_allow_html=True)
    df_p = obtener_productos()
    if not df_p.empty:
        prod_sel = st.selectbox("Selecciona un producto a modificar:", [f"{r['id']} - {r['nombre']}" for _, r in df_p.iterrows()])
        if prod_sel:
            id_p = str(prod_sel.split(" - ")[0])
            p_row = df_p[df_p["id"].astype(str) == id_p].iloc[0]

            cats = obtener_categorias()
            marcas = obtener_marcas()

            with st.form("form_edit_prod"):
                col1, col2 = st.columns(2)
                cod_barras = col1.text_input("Código de Barras:", value=str(p_row.get("codigo_barras", "")))
                nombre = col2.text_input("Nombre del Producto:", value=p_row["nombre"])
                cat = col1.selectbox("Categoría:", cats, index=cats.index(p_row["categoria"]) if p_row["categoria"] in cats else 0)
                marca = col2.selectbox("Marca:", marcas, index=marcas.index(p_row["marca"]) if p_row["marca"] in marcas else 0)
                costo = col1.number_input("Precio Costo (Gs.):", min_value=0, value=int(p_row["precio_costo"]))
                ganancia = col2.number_input("% Ganancia:", min_value=0, value=int(p_row["ganancia_porcentaje"]))
                precio_venta = col1.number_input("Precio Venta (Gs.):", min_value=0, value=int(p_row["precio_venta"]))
                stock = col2.number_input("Stock:", min_value=0, value=int(p_row["stock"]))
                desc = st.text_area("Descripción:", value=str(p_row.get("descripcion", "")))

                c_save, c_del = st.columns([1, 1])
                if c_save.form_submit_button("Guardar Cambios", type="primary"):
                    actualizar_producto(id_p, cod_barras, nombre, cat, marca, costo, ganancia, precio_venta, stock, desc)
                    st.success("Producto actualizado correctamente.")
                    st.rerun()

            if st.button("🗑️ Eliminar Producto"):
                eliminar_producto(id_p)
                st.success("Producto eliminado.")
                st.rerun()

# ==========================================
# GESTOR DE CATEGORÍAS
# ==========================================
elif opcion == "🏷️ Gestor de Categorías":
    st.markdown('<p class="main-title">🏷️ Gestor de Categorías</p>', unsafe_allow_html=True)
    cats = obtener_categorias()
    
    col1, col2 = st.columns(2)
    with col1:
        nueva_cat = st.text_input("Nueva Categoría:")
        if st.button("Agregar Categoría", type="primary"):
            if nueva_cat.strip():
                registrar_categoria(nueva_cat)
                st.success("Categoría agregada.")
                st.rerun()
    with col2:
        cat_del = st.selectbox("Eliminar Categoría:", cats)
        if st.button("Eliminar"):
            eliminar_categoria(cat_del)
            st.success("Categoría eliminada.")
            st.rerun()

    st.markdown("---")
    st.write("Categorías actuales:", cats)

# ==========================================
# GESTOR DE MARCAS
# ==========================================
elif opcion == "🏢 Gestor de Marcas":
    st.markdown('<p class="main-title">🏢 Gestor de Marcas</p>', unsafe_allow_html=True)
    marcas = obtener_marcas()
    
    col1, col2 = st.columns(2)
    with col1:
        nueva_marca = st.text_input("Nueva Marca:")
        if st.button("Agregar Marca", type="primary"):
            if nueva_marca.strip():
                registrar_marca(nueva_marca)
                st.success("Marca agregada.")
                st.rerun()
    with col2:
        marca_del = st.selectbox("Eliminar Marca:", marcas)
        if st.button("Eliminar"):
            eliminar_marca(marca_del)
            st.success("Marca eliminada.")
            st.rerun()

    st.markdown("---")
    st.write("Marcas actuales:", marcas)
