import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime, date

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

# --- FUNCIONES DE CATEGORÍAS ---
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

# --- FUNCIONES DE MARCAS ---
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

# --- FUNCIONES DE VENTAS Y DEUDAS ---
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

def marcar_deuda_pagada(cliente_nombre):
    """Marca como Pagado todas las deudas pendientes de un cliente."""
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("ventas").where("cliente_nombre", "==", cliente_nombre).where("estado_pago", "==", "Pendiente").stream()
        for doc in docs:
            db_cloud.collection("ventas").document(doc.id).update({"estado_pago": "Pagado"})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ventas SET estado_pago = 'Pagado' WHERE cliente_nombre = ? AND estado_pago = 'Pendiente'
        """, (cliente_nombre,))
        conn.commit()
        conn.close()

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
        "💳 Deudas de Clientes",
        "👥 Gestor de Clientes", 
        "📦 Ver Stock / Inventario", 
        "➕ Registrar Producto", 
        "✏️ Editar / Modificar Producto", 
        "🏷️ Gestor de Categorías", 
        "🏢 Gestor de Marcas"
    ],
    captions=[
        "Registrar salidas y reporte del día", 
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
# VISTA: VENTAS Y CIERRE DE CAJA
# ------------------------------------------
if opcion == "🛒 Ventas y Cierre de Caja":
    st.markdown('<p class="main-title">🛒 Ventas y Cierre de Caja</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Registra ventas a Contado o Crédito y consulta el resumen del día.</p>', unsafe_allow_html=True)
    
    tab_venta, tab_cierre = st.tabs(["🛍️ Nueva Venta", "📊 Cierre de Caja del Día"])
    
    # TAB 1: NUEVA VENTA (CARRITO)
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
                        # Selección de Cliente
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
                            st.success(f"✔️ ¡Venta registrada ({tipo_venta}) con éxito!")
                            st.rerun()

    # TAB 2: CIERRE DE CAJA
    with tab_cierre:
        st.subheader("📊 Cierre de Caja Diario")
        fecha_cierre = st.date_input("Selecciona la fecha para consultar el cierre:", value=date.today(), key="fecha_cierre")
        df_ventas = obtener_ventas()
        
        if df_ventas.empty:
            st.info("No hay ventas registradas aún en la base de datos.")
        else:
            df_ventas['fecha_solo'] = df_ventas['fecha_hora'].apply(lambda x: str(x).split(" ")[0] if pd.notna(x) else "")
            df_ventas_dia = df_ventas[df_ventas['fecha_solo'] == str(fecha_cierre)]
            
            if df_ventas_dia.empty:
                st.warning(f"No se registraron ventas en la fecha {fecha_cierre.strftime('%d/%m/%Y')}.")
            else:
                total_ingresos = int(df_ventas_dia['total'].sum())
                num_ventas = len(df_ventas_dia)
                unidades_vendidas = int(df_ventas_dia['cantidad'].sum())
                
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric("Total General Generado", formatear_gs(total_ingresos))
                with m2:
                    st.metric("Número de Transacciones", f"{num_ventas} ventas")
                with m3:
                    st.metric("Total Productos Vendidos", f"{unidades_vendidas} uds")
                
                st.markdown("---")
                st.write("### Detalle de Ventas del Día")
                df_cierre_visual = df_ventas_dia.copy()
                df_cierre_visual['precio_unitario'] = df_cierre_visual['precio_unitario'].apply(formatear_gs)
                df_cierre_visual['total'] = df_cierre_visual['total'].apply(formatear_gs)
                
                st.dataframe(
                    df_cierre_visual[['fecha_hora', 'cliente_nombre', 'producto_nombre', 'cantidad', 'precio_unitario', 'total', 'tipo_venta', 'estado_pago']],
                    column_config={
                        "fecha_hora": "Hora",
                        "cliente_nombre": "Cliente",
                        "producto_nombre": "Producto",
                        "cantidad": "Cantidad",
                        "precio_unitario": "Precio Unit.",
                        "total": "Total",
                        "tipo_venta": "Condición",
                        "estado_pago": "Estado"
                    },
                    hide_index=True,
                    use_container_width=True
                )

# ------------------------------------------
# VISTA: DEUDAS DE CLIENTES
# ------------------------------------------
elif opcion == "💳 Deudas de Clientes":
    st.markdown('<p class="main-title">💳 Gestión de Deudas y Fiados</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Revisa las cuentas pendientes de tus clientes y registra sus pagos.</p>', unsafe_allow_html=True)
    
    df_ventas = obtener_ventas()
    
    if df_ventas.empty:
        st.info("No hay registros de ventas.")
    else:
        df_deudas = df_ventas[df_ventas['estado_pago'] == "Pendiente"]
        
        if df_deudas.empty:
            st.balloons()
            st.success("🎉 ¡Excelente! No hay clientes con deudas pendientes actualmente.")
        else:
            resumen_deudas = df_deudas.groupby("cliente_nombre")["total"].sum().reset_index()
            resumen_deudas.columns = ["Cliente", "Saldo Pendiente (Gs.)"]
            
            total_deuda_global = resumen_deudas["Saldo Pendiente (Gs.)"].sum()
            
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                st.metric("Deuda Total a Cobrar en la Tienda", formatear_gs(total_deuda_global))
            with c_m2:
                st.metric("Clientes con Deuda Activa", f"{len(resumen_deudas)} clientes")
                
            st.markdown("---")
            st.subheader("📋 Resumen por Cliente")
            
            resumen_visual = resumen_deudas.copy()
            resumen_visual["Saldo Pendiente (Gs.)"] = resumen_visual["Saldo Pendiente (Gs.)"].apply(formatear_gs)
            st.table(resumen_visual)
            
            st.markdown("---")
            st.subheader("🔍 Consultar y Saldar Deuda de un Cliente")
            
            cliente_con_deuda_sel = st.selectbox("Selecciona un cliente para ver su detalle de compras:", resumen_deudas["Cliente"].unique())
            
            df_detalle_cliente = df_deudas[df_deudas['cliente_nombre'] == cliente_con_deuda_sel].copy()
            deuda_total_cliente = df_detalle_cliente['total'].sum()
            
            st.warning(f"⚠️ **{cliente_con_deuda_sel}** debe un total de **{formatear_gs(deuda_total_cliente)}**")
            
            df_detalle_visual = df_detalle_cliente.copy()
            df_detalle_visual['precio_unitario'] = df_detalle_visual['precio_unitario'].apply(formatear_gs)
            df_detalle_visual['total'] = df_detalle_visual['total'].apply(formatear_gs)
            
            st.dataframe(
                df_detalle_visual[['fecha_hora', 'producto_nombre', 'cantidad', 'precio_unitario', 'total', 'metodo_pago']],
                column_config={
                    "fecha_hora": "Fecha/Hora",
                    "producto_nombre": "Producto",
                    "cantidad": "Cantidad",
                    "precio_unitario": "Precio Unit.",
                    "total": "Total",
                    "metodo_pago": "Método Pago"
                },
                hide_index=True,
                use_container_width=True
            )
            
            if st.button(f"✅ Marcar deudas de {cliente_con_deuda_sel} como PAGADAS", type="primary", use_container_width=True):
                marcar_deuda_pagada(cliente_con_deuda_sel)
                st.success(f"¡Se han cancelado todas las deudas de {cliente_con_deuda_sel}!")
                st.rerun()

# ------------------------------------------
# VISTA: GESTOR DE CLIENTES
# ------------------------------------------
elif opcion == "👥 Gestor de Clientes":
    st.markdown('<p class="main-title">👥 Gestor de Clientes</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Registra, edita o elimina la información de tus clientes.</p>', unsafe_allow_html=True)
    
    tab_list_cli, tab_reg_cli, tab_edit_cli = st.tabs(["📋 Lista de Clientes", "➕ Registrar Cliente", "✏️ Editar / Eliminar"])
    
    with tab_list_cli:
        df_cli = obtener_clientes()
        if df_cli.empty:
            st.info("No hay clientes registrados aún.")
        else:
            st.dataframe(
                df_cli[['id', 'nombre', 'apellido', 'ci', 'telefono', 'ciudad']],
                column_config={
                    "id": "ID",
                    "nombre": "Nombre",
                    "apellido": "Apellido",
                    "ci": "CI / RUC",
                    "telefono": "Teléfono",
                    "ciudad": "Ciudad"
                },
                hide_index=True,
                use_container_width=True
            )
            
    with tab_reg_cli:
        with st.form("form_reg_cliente", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                nom_cli = st.text_input("Nombre *")
                ci_cli = st.text_input("CI / Doc. *")
                ciudad_cli = st.text_input("Ciudad")
            with c2:
                ape_cli = st.text_input("Apellido *")
                tel_cli = st.text_input("Teléfono")
                
            btn_guardar_cli = st.form_submit_button("💾 Guardar Cliente", type="primary")
            if btn_guardar_cli:
                if nom_cli.strip() and ape_cli.strip() and ci_cli.strip():
                    registrar_cliente(nom_cli, ape_cli, ci_cli, tel_cli or "", ciudad_cli or "")
                    st.success("¡Cliente registrado exitosamente!")
                    st.rerun()
                else:
                    st.error("Por favor completa los campos obligatorios (*): Nombre, Apellido y CI.")

    with tab_edit_cli:
        df_cli = obtener_clientes()
        if df_cli.empty:
            st.info("No hay clientes disponibles para editar.")
        else:
            lista_cli_str = [f"{row['id']} - {row['nombre']} {row['apellido']} (CI: {row['ci']})" for _, row in df_cli.iterrows()]
            cli_sel_str = st.selectbox("Selecciona un cliente:", lista_cli_str, key="sel_cli_edit")
            if cli_sel_str:
                id_c = str(cli_sel_str.split(" - ")[0])
                datos_c = df_cli[df_cli['id'].astype(str) == id_c].iloc[0]
                
                with st.form("form_edit_cliente"):
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        e_nom = st.text_input("Nombre", value=str(datos_c['nombre']))
                        e_ci = st.text_input("CI / Doc.", value=str(datos_c['ci']))
                        e_ciudad = st.text_input("Ciudad", value=str(datos_c.get('ciudad', '')))
                    with ec2:
                        e_ape = st.text_input("Apellido", value=str(datos_c['apellido']))
                        e_tel = st.text_input("Teléfono", value=str(datos_c.get('telefono', '')))
                    
                    c_b1, c_b2 = st.columns(2)
                    with c_b1:
                        btn_act_c = st.form_submit_button("✏️ Actualizar Cliente", type="primary", use_container_width=True)
                    with c_b2:
                        btn_del_c = st.form_submit_button("❌ Eliminar Cliente", use_container_width=True)
                        
                    if btn_act_c:
                        actualizar_cliente(id_c, e_nom, e_ape, e_ci, e_tel, e_ciudad)
                        st.success("¡Cliente actualizado correctamente!")
                        st.rerun()
                    if btn_del_c:
                        eliminar_cliente(id_c)
                        st.warning("Cliente eliminado correctamente.")
                        st.rerun()

# ------------------------------------------
# VISTA: VER STOCK / INVENTARIO
# ------------------------------------------
elif opcion == "📦 Ver Stock / Inventario":
    st.markdown('<p class="main-title">📦 Ver Stock / Inventario</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Consulta el catálogo de productos y existencias en tiempo real.</p>', unsafe_allow_html=True)
    
    df_p = obtener_productos()
    if df_p.empty:
        st.info("No hay productos registrados en el inventario.")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            cat_filtro = st.selectbox("Filtrar por Categoría:", ["Todas"] + obtener_categorias(), key="filtro_cat")
        with col_f2:
            marca_filtro = st.selectbox("Filtrar por Marca:", ["Todas"] + obtener_marcas(), key="filtro_marca")
            
        df_filtrado = df_p.copy()
        if cat_filtro != "Todas":
            df_filtrado = df_filtrado[df_filtrado['categoria'] == cat_filtro]
        if marca_filtro != "Todas":
            df_filtrado = df_filtrado[df_filtrado['marca'] == marca_filtro]
            
        df_vis = df_filtrado.copy()
        df_vis['precio_costo'] = df_vis['precio_costo'].apply(formatear_gs)
        df_vis['precio_venta'] = df_vis['precio_venta'].apply(formatear_gs)
        
        st.dataframe(
            df_vis[['id', 'nombre', 'categoria', 'marca', 'precio_costo', 'ganancia_porcentaje', 'precio_venta', 'stock', 'descripcion']],
            column_config={
                "id": "ID",
                "nombre": "Producto",
                "categoria": "Categoría",
                "marca": "Marca",
                "precio_costo": "P. Costo",
                "ganancia_porcentaje": "Ganancia (%)",
                "precio_venta": "P. Venta",
                "stock": "Stock",
                "descripcion": "Descripción"
            },
            hide_index=True,
            use_container_width=True
        )

# ------------------------------------------
# VISTA: REGISTRAR PRODUCTO
# ------------------------------------------
elif opcion == "➕ Registrar Producto":
    st.markdown('<p class="main-title">➕ Registrar Nuevo Producto</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Añade nuevos artículos a tu catálogo.</p>', unsafe_allow_html=True)
    
    cats = obtener_categorias()
    marcas = obtener_marcas()
    
    with st.form("form_reg_prod", clear_on_submit=True):
        p_nom = st.text_input("Nombre del Producto *")
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            p_cat = st.selectbox("Categoría", cats)
            p_costo = st.number_input("Precio de Costo (Gs.) *", min_value=0, step=500)
            p_stock = st.number_input("Stock Inicial *", min_value=0, value=1, step=1)
        with col_p2:
            p_marca = st.selectbox("Marca", marcas)
            p_ganancia = st.number_input("Margen de Ganancia (%) *", min_value=0, value=30, step=5)
            precio_calc = int(p_costo * (1 + (p_ganancia / 100)))
            st.info(f"Precio Venta Calculado: **{formatear_gs(precio_calc)}**")
            
        p_desc = st.text_area("Descripción (Opcional)")
        
        btn_reg_prod = st.form_submit_button("💾 Guardar Producto", type="primary")
        
        if btn_reg_prod:
            if p_nom.strip() and p_costo >= 0:
                precio_final = int(p_costo * (1 + (p_ganancia / 100)))
                registrar_producto(p_nom.strip(), p_cat, p_marca, p_costo, p_ganancia, precio_final, p_stock, p_desc.strip())
                st.success(f"¡Producto '{p_nom}' registrado con éxito!")
                st.rerun()
            else:
                st.error("Por favor completa los campos obligatorios.")

# ------------------------------------------
# VISTA: EDITAR / MODIFICAR PRODUCTO
# ------------------------------------------
elif opcion == "✏️ Editar / Modificar Producto":
    st.markdown('<p class="main-title">✏️ Editar / Modificar Producto</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Actualiza la información o elimina productos existentes.</p>', unsafe_allow_html=True)
    
    df_p = obtener_productos()
    if df_p.empty:
        st.info("No hay productos registrados para modificar.")
    else:
        lista_prods_str = [f"{row['id']} - {row['nombre']} ({row['marca']})" for _, row in df_p.iterrows()]
        prod_edit_sel = st.selectbox("Selecciona un producto:", lista_prods_str, key="sel_prod_edit")
        
        if prod_edit_sel:
            id_p_edit = str(prod_edit_sel.split(" - ")[0])
            datos_p = df_p[df_p['id'].astype(str) == id_p_edit].iloc[0]
            
            cats = obtener_categorias()
            marcas = obtener_marcas()
            
            idx_cat = cats.index(datos_p['categoria']) if datos_p['categoria'] in cats else 0
            idx_marca = marcas.index(datos_p['marca']) if datos_p['marca'] in marcas else 0
            
            with st.form("form_edit_prod"):
                e_p_nom = st.text_input("Nombre", value=str(datos_p['nombre']))
                
                ep1, ep2 = st.columns(2)
                with ep1:
                    e_p_cat = st.selectbox("Categoría", cats, index=idx_cat)
                    e_p_costo = st.number_input("Precio Costo (Gs.)", min_value=0, value=int(datos_p['precio_costo']), step=500)
                    e_p_stock = st.number_input("Stock", min_value=0, value=int(datos_p['stock']), step=1)
                with ep2:
                    e_p_marca = st.selectbox("Marca", marcas, index=idx_marca)
                    e_p_ganancia = st.number_input("Ganancia (%)", min_value=0, value=int(datos_p['ganancia_porcentaje']), step=5)
                    e_precio_calc = int(e_p_costo * (1 + (e_p_ganancia / 100)))
                    st.info(f"Precio Venta Calculado: **{formatear_gs(e_precio_calc)}**")
                    
                e_p_desc = st.text_area("Descripción", value=str(datos_p.get('descripcion', '')))
                
                eb1, eb2 = st.columns(2)
                with eb1:
                    btn_act_p = st.form_submit_button("✏️ Actualizar Producto", type="primary", use_container_width=True)
                with eb2:
                    btn_del_p = st.form_submit_button("❌ Eliminar Producto", use_container_width=True)
                    
                if btn_act_p:
                    e_precio_final = int(e_p_costo * (1 + (e_p_ganancia / 100)))
                    actualizar_producto(id_p_edit, e_p_nom, e_p_cat, e_p_marca, e_p_costo, e_p_ganancia, e_precio_final, e_p_stock, e_p_desc)
                    st.success("¡Producto actualizado exitosamente!")
                    st.rerun()
                    
                if btn_del_p:
                    eliminar_producto(id_p_edit)
                    st.warning("Producto eliminado del inventario.")
                    st.rerun()

# ------------------------------------------
# VISTA: GESTOR DE CATEGORÍAS
# ------------------------------------------
elif opcion == "🏷️ Gestor de Categorías":
    st.markdown('<p class="main-title">🏷️ Gestor de Categorías</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Añade o elimina categorías para tus productos.</p>', unsafe_allow_html=True)
    
    col_cat1, col_cat2 = st.columns(2)
    
    with col_cat1:
        st.subheader("➕ Añadir Categoría")
        nueva_cat = st.text_input("Nombre de la Categoría:", key="input_nueva_cat")
        if st.button("Guardar Categoría", type="primary", key="btn_add_cat"):
            if nueva_cat.strip():
                registrar_categoria(nueva_cat)
                st.success(f"Categoría '{nueva_cat.strip()}' agregada.")
                st.rerun()
            else:
                st.error("Ingresa un nombre válido.")
                
    with col_cat2:
        st.subheader("🗑️ Eliminar Categoría")
        cats_existentes = obtener_categorias()
        cat_del_sel = st.selectbox("Selecciona categoría a eliminar:", cats_existentes, key="sel_del_cat")
        if st.button("Eliminar Categoría", key="btn_del_cat"):
            eliminar_categoria(cat_del_sel)
            st.warning(f"Categoría '{cat_del_sel}' eliminada.")
            st.rerun()

# ------------------------------------------
# VISTA: GESTOR DE MARCAS
# ------------------------------------------
elif opcion == "🏢 Gestor de Marcas":
    st.markdown('<p class="main-title">🏢 Gestor de Marcas</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Administra la lista de marcas de tu tienda.</p>', unsafe_allow_html=True)
    
    col_m1, col_m2 = st.columns(2)
    
    with col_m1:
        st.subheader("➕ Añadir Marca")
        nueva_marca = st.text_input("Nombre de la Marca:", key="input_nueva_marca")
        if st.button("Guardar Marca", type="primary", key="btn_add_marca"):
            if nueva_marca.strip():
                registrar_marca(nueva_marca)
                st.success(f"Marca '{nueva_marca.strip()}' agregada.")
                st.rerun()
            else:
                st.error("Ingresa un nombre válido.")
                
    with col_m2:
        st.subheader("🗑️ Eliminar Marca")
        marcas_existentes = obtener_marcas()
        marca_del_sel = st.selectbox("Selecciona marca a eliminar:", marcas_existentes, key="sel_del_marca")
        if st.button("Eliminar Marca", key="btn_del_marca"):
            eliminar_marca(marca_del_sel)
            st.warning(f"Marca '{marca_del_sel}' eliminada.")
            st.rerun()
