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
    columnas = [col[1] for col in cursor.fetchall()]
    
    if columnas and "marca" not in columnas:
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
            metodo_pago TEXT NOT NULL
        )
    """)

    # Insertar categorías por defecto si está vacía
    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        cat_iniciales = [("Perfumes",), ("Cosméticos",), ("Cuidado Personal",), ("Otros",)]
        cursor.executemany("INSERT INTO categorias (nombre) VALUES (?)", cat_iniciales)

    # Insertar marcas por defecto si está vacía
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
        if not lista:
            return cat_default
        return sorted(list(set(lista)))
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM categorias ORDER BY nombre ASC")
        filas = cursor.fetchall()
        conn.close()
        if not filas:
            return cat_default
        return [f[0] for f in filas]

def registrar_categoria(nombre_cat):
    db_cloud = obtener_conexion_db()
    nombre_cat = nombre_cat.strip()
    
    if db_cloud is not None:
        existentes = obtener_categorias()
        if nombre_cat not in existentes:
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
        if not lista:
            return marcas_default
        return sorted(list(set(lista)))
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM marcas ORDER BY nombre ASC")
        filas = cursor.fetchall()
        conn.close()
        if not filas:
            return marcas_default
        return [f[0] for f in filas]

def registrar_marca(nombre_marca):
    db_cloud = obtener_conexion_db()
    nombre_marca = nombre_marca.strip()
    
    if db_cloud is not None:
        existentes = obtener_marcas()
        if nombre_marca not in existentes:
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

# --- FUNCIONES DE VENTAS ---
def registrar_venta(producto_id, producto_nombre, cantidad, precio_unitario, total, metodo_pago):
    """Registra la venta y descuenta el stock correspondientemente."""
    db_cloud = obtener_conexion_db()
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if db_cloud is not None:
        # Registrar venta en Firestore
        db_cloud.collection("ventas").add({
            "fecha_hora": fecha_hora,
            "producto_id": str(producto_id),
            "producto_nombre": producto_nombre,
            "cantidad": int(cantidad),
            "precio_unitario": int(precio_unitario),
            "total": int(total),
            "metodo_pago": metodo_pago
        })
        # Descontar stock
        doc_ref = db_cloud.collection("productos").document(str(producto_id))
        doc = doc_ref.get()
        if doc.exists:
            stock_actual = doc.to_dict().get("stock", 0)
            doc_ref.update({"stock": max(0, stock_actual - int(cantidad))})
    else:
        conn = sqlite3.connect("inventario.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ventas (fecha_hora, producto_id, producto_nombre, cantidad, precio_unitario, total, metodo_pago)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (fecha_hora, str(producto_id), producto_nombre, int(cantidad), int(precio_unitario), int(total), metodo_pago))
        
        # Descontar stock en SQLite
        cursor.execute("""
            UPDATE productos SET stock = stock - ? WHERE id = ?
        """, (int(cantidad), int(producto_id)))
        
        conn.commit()
        conn.close()

def obtener_ventas():
    """Obtiene el historial de ventas."""
    db_cloud = obtener_conexion_db()
    if db_cloud is not None:
        docs = db_cloud.collection("ventas").stream()
        lista = []
        for doc in docs:
            datos = doc.to_dict()
            lista.append(datos)
        if not lista:
            return pd.DataFrame(columns=["fecha_hora", "producto_id", "producto_nombre", "cantidad", "precio_unitario", "total", "metodo_pago"])
        return pd.DataFrame(lista)
    else:
        conn = sqlite3.connect("inventario.db")
        df = pd.read_sql_query("SELECT * FROM ventas", conn)
        conn.close()
        return df

# Inicializar almacenamiento
init_db()

def formatear_gs(valor):
    try:
        valor_entero = int(valor)
        cadena_formateada = "{:,}".format(valor_entero)
        cadena_paraguay = cadena_formateada.replace(",", ".")
        return f"Gs. {cadena_paraguay}"
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

nube_activa = obtener_conexion_db() is not None

if nube_activa:
    st.sidebar.success("☁️ Conectado a Almacenamiento Permanente")
else:
    st.sidebar.warning("💾 Almacenamiento Temporal (SQLite)")
    with st.sidebar.expander("🚀 Guardar datos para siempre"):
        st.markdown("""
        Los datos se borrarán si actualizas la app. Para activarlo de forma permanente:
        1. Crea un proyecto gratis en **Google Firebase**.
        2. Crea una base de datos **Cloud Firestore**.
        3. Ve a Configuración del proyecto > Cuentas de servicio > Generar nueva clave privada (JSON).
        4. Copia el contenido de ese archivo JSON y pégalo en la sección **Secrets** de Streamlit Cloud con el nombre `gcp_service_account`.
        """)

opcion = st.sidebar.radio(
    "Selecciona una opción:",
    ["🛒 Ventas y Cierre de Caja", "📦 Ver Stock / Inventario", "➕ Registrar Producto", "✏️ Editar / Modificar Producto", "🏷️ Gestor de Categorías", "🏢 Gestor de Marcas"],
    captions=["Registrar salidas y reporte del día", "Control de existencias", "Añadir nuevos artículos", "Actualizar o eliminar registros", "Organizar categorías", "Administrar marcas"]
)

# ------------------------------------------
# VISTA: VENTAS Y CIERRE DE CAJA
# ------------------------------------------
if opcion == "🛒 Ventas y Cierre de Caja":
    st.markdown('<p class="main-title">🛒 Ventas y Cierre de Caja</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Registra las ventas diarias y consulta el resumen de ingresos al final de la jornada.</p>', unsafe_allow_html=True)
    
    tab_venta, tab_cierre = st.tabs(["🛍️ Nueva Venta", "📊 Cierre de Caja del Día"])
    
    # TAB 1: NUEVA VENTA (CARRITO MULTI-PRODUCTO)
    with tab_venta:
        # Inicializar la variable del carrito en la sesión si no existe
        if "carrito" not in st.session_state:
            st.session_state.carrito = []

        df_productos = obtener_productos()
        
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
                    
                    # Descontar del stock disponible lo que ya esté metido en el carrito actual
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
                            # Si el producto ya está en el carrito, sumamos la cantidad
                            encontrado = False
                            for item in st.session_state.carrito:
                                if str(item['id']) == id_prod_sel:
                                    item['cantidad'] += cantidad_agregar
                                    item['subtotal'] = item['cantidad'] * item['precio_venta']
                                    encontrado = True
                                    break
                            
                            # Si no está, lo agregamos como un nuevo ítem
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
                    # Mostrar la lista del carrito ítem por ítem
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
                            if st.button("❌", key=f"del_cart_{idx}", help="Quitar ítem"):
                                st.session_state.carrito.pop(idx)
                                st.rerun()

                    total_general = sum(item['subtotal'] for item in st.session_state.carrito)

                    st.markdown("---")
                    col_fin1, col_fin2 = st.columns(2)

                    with col_fin1:
                        metodo_pago = st.selectbox("Método de Pago", ["Efectivo", "Transferencia / PIX", "Tarjeta de Débito/Crédito"], key="met_pago")
                        if st.button("🗑️ Vaciar Carrito", key="btn_vaciar"):
                            st.session_state.carrito = []
                            st.rerun()

                    with col_fin2:
                        st.markdown("### Total Final a Cobrar:")
                        st.success(f"💰 **{formatear_gs(total_general)}**")
                        
                        if st.button("💳 Finalizar Venta Completa", type="primary", use_container_width=True, key="btn_finalizar_venta"):
                            # Registrar cada ítem en la base de datos y descontar stock
                            for item in st.session_state.carrito:
                                registrar_venta(
                                    item['id'],
                                    item['nombre'],
                                    item['cantidad'],
                                    item['precio_venta'],
                                    item['subtotal'],
                                    metodo_pago
                                )
                            # Limpiar carrito tras completar la venta
                            st.session_state.carrito = []
                            st.success("✔️ ¡Venta realizada con éxito! Se registraron todos los productos y se actualizó el stock.")
                            st.rerun()

    # TAB 2: CIERRE DE CAJA
    with tab_cierre:
        st.subheader("📊 Cierre de Caja Diario")
        
        fecha_cierre = st.date_input("Selecciona la fecha para consultar el cierre:", value=date.today(), key="fecha_cierre")
        df_ventas = obtener_ventas()
        
        if df_ventas.empty:
            st.info("No hay ventas registradas aún en la base de datos.")
        else:
            # Filtrar por la fecha seleccionada
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
                    st.metric("Total Recaudado (Gs.)", formatear_gs(total_ingresos))
                with m2:
                    st.metric("Número de Transacciones", f"{num_ventas} ventas")
                with m3:
                    st.metric("Total Productos Vendidos", f"{unidades_vendidas} uds")
                
                st.markdown("---")
                st.write("### Desglose por Método de Pago")
                
                resumen_pago = df_ventas_dia.groupby("metodo_pago")["total"].sum().reset_index()
                resumen_pago.columns = ["Método de Pago", "Total (Gs.)"]
                resumen_pago["Total (Gs.)"] = resumen_pago["Total (Gs.)"].apply(formatear_gs)
                
                st.table(resumen_pago)
                
                st.markdown("---")
                st.write("### Detalle de Ventas del Día")
                
                df_cierre_visual = df_ventas_dia.copy()
                df_cierre_visual['precio_unitario'] = df_cierre_visual['precio_unitario'].apply(formatear_gs)
                df_cierre_visual['total'] = df_cierre_visual['total'].apply(formatear_gs)
                
                st.dataframe(
                    df_cierre_visual[['fecha_hora', 'producto_nombre', 'cantidad', 'precio_unitario', 'total', 'metodo_pago']],
                    column_config={
                        "fecha_hora": "Hora",
                        "producto_nombre": "Producto",
                        "cantidad": "Cantidad",
                        "precio_unitario": "Precio Unit.",
                        "total": "Total",
                        "metodo_pago": "Método de Pago"
                    },
                    hide_index=True,
                    use_container_width=True
                )

# ------------------------------------------
# VISTA: VER STOCK / INVENTARIO
# ------------------------------------------
elif opcion == "📦 Ver Stock / Inventario":
    st.markdown('<p class="main-title">📦 Control de Stock e Inventario</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Visualiza, busca y analiza el rendimiento financiero de tus productos en tiempo real.</p>', unsafe_allow_html=True)
    
    df_productos = obtener_productos()
    
    if df_productos.empty:
        st.info("Aún no tienes productos registrados en el inventario. Ve a la pestaña 'Registrar Producto' en el menú de la izquierda.")
    else:
        busqueda = st.text_input("🔍 Buscar producto por nombre", "", placeholder="Escribe el nombre del producto...")
        
        if busqueda:
            df_productos_filtrados = df_productos[df_productos['nombre'].str.contains(busqueda, case=False)]
        else:
            df_productos_filtrados = df_productos

        df_visual = df_productos_filtrados.copy()
        df_visual['precio_costo'] = df_visual['precio_costo'].apply(formatear_gs)
        df_visual['ganancia_porcentaje'] = df_visual['ganancia_porcentaje'].apply(lambda x: f"{x}%")
        df_visual['precio_venta'] = df_visual['precio_venta'].apply(formatear_gs)
        df_visual['stock'] = df_visual['stock'].apply(lambda x: f"{x} uds")

        st.dataframe(
            df_visual,
            column_config={
                "id": "ID",
                "nombre": "Producto",
                "categoria": "Categoría",
                "marca": "Marca",
                "precio_costo": "Precio Costo (Gs.)",
                "ganancia_porcentaje": "Ganancia (%)",
                "precio_venta": "Precio Venta (Gs.)",
                "stock": "Stock",
                "descripcion": "Descripción"
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("---")
        st.subheader("📊 Resumen Financiero del Inventario (Gs.)")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_productos = len(df_productos_filtrados)
        total_stock = int(df_productos_filtrados['stock'].sum())
        
        valor_costo = int((df_productos_filtrados['precio_costo'] * df_productos_filtrados['stock']).sum())
        valor_venta = int((df_productos_filtrados['precio_venta'] * df_productos_filtrados['stock']).sum())
        ganancia_estimada = valor_venta - valor_costo
        
        with col1:
            st.metric("Total de Productos", f"{total_productos} tipos")
        with col2:
            st.metric("Existencias en Stock", f"{total_stock} uds")
        with col3:
            st.metric("Inversión Total (Gs.)", formatear_gs(valor_costo))
        with col4:
            st.metric("Ganancia Estimada (Gs.)", formatear_gs(ganancia_estimada))

# ------------------------------------------
# VISTA: REGISTRAR PRODUCTO
# ------------------------------------------
elif opcion == "➕ Registrar Producto":
    st.markdown('<p class="main-title">➕ Registro de Nuevo Producto</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Añade nuevos artículos definiendo su costo de compra y margen de utilidad deseado.</p>', unsafe_allow_html=True)
    
    lista_categorias = obtener_categorias()
    lista_marcas = obtener_marcas()
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        nombre = st.text_input("Nombre del Producto *", placeholder="Ej. Encanto Imperial 100ml", key="reg_nombre")
        categoria = st.selectbox("Categoría", lista_categorias, key="reg_categoria")
        marca = st.selectbox("Marca", lista_marcas, key="reg_marca")
        stock = st.number_input("Cantidad inicial en stock *", min_value=1, step=1, value=1, key="reg_stock")
        
    with col_b:
        precio_costo = st.number_input("Precio de Costo (Gs.) *", min_value=0, step=500, value=0, key="reg_costo")
        ganancia_porcentaje = st.slider("Porcentaje de Ganancia (%)", min_value=20, max_value=100, step=5, value=20, key="reg_ganancia")
        
        precio_venta_calculado = int(precio_costo * (1 + (ganancia_porcentaje / 100.0)))
        
        st.markdown("**Precio de Venta Sugerido:**")
        st.info(f"💰 {formatear_gs(precio_venta_calculado)}  \n*(Costo + {ganancia_porcentaje}% de ganancia)*")

    descripcion = st.text_area("Descripción del Producto (Opcional)", placeholder="Fragancias, notas u observaciones...", key="reg_desc")
    
    st.markdown("---")
    guardar = st.button("💾 Guardar y Registrar", key="reg_guardar")
    
    if guardar:
        if nombre.strip() == "":
            st.error("El nombre del producto es requerido.")
        elif precio_costo <= 0:
            st.error("El precio de costo debe ser mayor a Gs. 0.")
        else:
            registrar_producto(nombre, categoria, marca, precio_costo, ganancia_porcentaje, precio_venta_calculado, stock, descripcion)
            st.success(f"✔️ ¡El producto '{nombre}' ha sido registrado con éxito a un precio de venta de {formatear_gs(precio_venta_calculado)}!")
            st.rerun()

# ------------------------------------------
# VISTA: EDITAR / MODIFICAR PRODUCTO
# ------------------------------------------
elif opcion == "✏️ Editar / Modificar Producto":
    st.markdown('<p class="main-title">✏️ Editar / Modificar Producto</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Selecciona un producto registrado para modificar sus precios, stock o eliminarlo del sistema.</p>', unsafe_allow_html=True)
    
    df_productos = obtener_productos()
    lista_categorias = obtener_categorias()
    lista_marcas = obtener_marcas()
    
    if df_productos.empty:
        st.info("No tienes productos registrados para modificar en este momento.")
    else:
        lista_productos = [f"{row['id']} - {row['nombre']}" for _, row in df_productos.iterrows()]
        seleccion = st.selectbox("Selecciona el producto que deseas editar:", lista_productos)
        
        id_seleccionado = str(seleccion.split(" - ")[0])
        df_filtrado = df_productos[df_productos['id'].astype(str) == id_seleccionado]
        
        if df_filtrado.empty:
            st.warning("⚠️ No se encontró el producto seleccionado.")
        else:
            prod_actual = df_filtrado.iloc[0]
            
            st.markdown("---")
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                nuevo_nombre = st.text_input("Nombre del Producto *", value=prod_actual['nombre'], key="edit_nombre")
                
                try:
                    cat_index = lista_categorias.index(prod_actual['categoria'])
                except (ValueError, KeyError):
                    cat_index = 0
                    
                nueva_categoria = st.selectbox("Categoría", lista_categorias, index=cat_index, key="edit_categoria")
                
                try:
                    marca_actual_val = prod_actual['marca'] if pd.notna(prod_actual['marca']) else ""
                    marca_index = lista_marcas.index(marca_actual_val)
                except (ValueError, KeyError):
                    marca_index = 0

                nueva_marca = st.selectbox("Marca", lista_marcas, index=marca_index, key="edit_marca")
                nuevo_stock = st.number_input("Cantidad en stock *", min_value=0, step=1, value=int(prod_actual['stock']), key="edit_stock")
                
            with col_b:
                nuevo_precio_costo = st.number_input("Precio de Costo (Gs.) *", min_value=0, step=500, value=int(prod_actual['precio_costo']), key="edit_costo")
                nueva_ganancia_porcentaje = st.slider("Porcentaje de Ganancia (%)", min_value=20, max_value=100, step=5, value=int(prod_actual['ganancia_porcentaje']), key="edit_ganancia")
                
                nuevo_precio_venta_calculado = int(nuevo_precio_costo * (1 + (nueva_ganancia_porcentaje / 100.0)))
                
                st.markdown("**Nuevo Precio de Venta Sugerido:**")
                st.info(f"💰 {formatear_gs(nuevo_precio_venta_calculado)}  \n*(Costo + {nueva_ganancia_porcentaje}% de ganancia)*")

            nueva_descripcion = st.text_area("Descripción del Producto (Opcional)", value=prod_actual['descripcion'] if pd.notna(prod_actual['descripcion']) else "", key="edit_desc")
            
            st.markdown("---")
            guardar_cambios = st.button("💾 Guardar Cambios", key="edit_guardar")
            
            if guardar_cambios:
                if nuevo_nombre.strip() == "":
                    st.error("El nombre del producto no puede quedar vacío.")
                elif nuevo_precio_costo <= 0:
                    st.error("El precio de costo debe ser mayor a Gs. 0.")
                else:
                    actualizar_producto(
                        id_seleccionado, 
                        nuevo_nombre, 
                        nueva_categoria, 
                        nueva_marca,
                        nuevo_precio_costo, 
                        nueva_ganancia_porcentaje, 
                        nuevo_precio_venta_calculado, 
                        nuevo_stock, 
                        nueva_descripcion
                    )
                    st.success(f"✔️ ¡El producto '{nuevo_nombre}' ha sido actualizado con éxito!")
                    st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader("⚠️ Zona de Eliminación")
            
            confirmar_borrado = st.checkbox(f"Confirmo que deseo borrar de forma permanente el producto: **{prod_actual['nombre']}**", key="confirm_del")
            
            if st.button("🗑️ Eliminar Producto Definitivamente", type="primary", disabled=not confirmar_borrado, key="btn_del"):
                eliminar_producto(id_seleccionado)
                st.success(f"✔️ ¡El producto '{prod_actual['nombre']}' ha sido eliminado con éxito!")
                st.rerun()

# ------------------------------------------
# VISTA: GESTOR DE CATEGORÍAS
# ------------------------------------------
elif opcion == "🏷️ Gestor de Categorías":
    st.markdown('<p class="main-title">🏷️ Gestor de Categorías</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Crea nuevas categorías o elimina aquellas que ya no necesites para organizar tu tienda.</p>', unsafe_allow_html=True)
    
    col_cat1, col_cat2 = st.columns(2)
    
    with col_cat1:
        st.subheader("➕ Añadir Nueva Categoría")
        nueva_cat_input = st.text_input("Nombre de la Categoría", placeholder="Ej. Maquillaje, Accesorios...", key="input_nueva_cat")
        
        if st.button("💾 Registrar Categoría", key="btn_add_cat"):
            if nueva_cat_input.strip() == "":
                st.error("Ingresa un nombre válido para la categoría.")
            else:
                registrar_categoria(nueva_cat_input)
                st.success(f"✔️ Categoría '{nueva_cat_input.strip()}' guardada con éxito.")
                st.rerun()
                
    with col_cat2:
        st.subheader("📋 Categorías Actuales")
        categorias_actuales = obtener_categorias()
        
        if categorias_actuales:
            for cat in categorias_actuales:
                st.markdown(f"- **{cat}**")
            
            st.markdown("---")
            st.subheader("🗑️ Eliminar Categoría")
            cat_a_eliminar = st.selectbox("Selecciona la categoría a eliminar", categorias_actuales, key="select_del_cat")
            
            if st.button("🗑️ Eliminar Categoría", type="secondary", key="btn_del_cat"):
                eliminar_categoria(cat_a_eliminar)
                st.success(f"✔️ Categoría '{cat_a_eliminar}' eliminada.")
                st.rerun()
        else:
            st.info("No hay categorías registradas.")

# ------------------------------------------
# VISTA: GESTOR DE MARCAS
# ------------------------------------------
elif opcion == "🏢 Gestor de Marcas":
    st.markdown('<p class="main-title">🏢 Gestor de Marcas</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Registra o elimina las marcas de los productos que comercializas.</p>', unsafe_allow_html=True)
    
    col_m1, col_m2 = st.columns(2)
    
    with col_m1:
        st.subheader("➕ Añadir Nueva Marca")
        nueva_marca_input = st.text_input("Nombre de la Marca", placeholder="Ej. Chanel, Victoria's Secret...", key="input_nueva_marca")
        
        if st.button("💾 Registrar Marca", key="btn_add_marca"):
            if nueva_marca_input.strip() == "":
                st.error("Ingresa un nombre válido para la marca.")
            else:
                registrar_marca(nueva_marca_input)
                st.success(f"✔️ Marca '{nueva_marca_input.strip()}' guardada con éxito.")
                st.rerun()
                
    with col_m2:
        st.subheader("📋 Marcas Actuales")
        marcas_actuales = obtener_marcas()
        
        if marcas_actuales:
            for m in marcas_actuales:
                st.markdown(f"- **{m}**")
            
            st.markdown("---")
            st.subheader("🗑️ Eliminar Marca")
            marca_a_eliminar = st.selectbox("Selecciona la marca a eliminar", marcas_actuales, key="select_del_marca")
            
            if st.button("🗑️ Eliminar Marca", type="secondary", key="btn_del_marca"):
                eliminar_marca(marca_a_eliminar)
                st.success(f"✔️ Marca '{marca_a_eliminar}' eliminada.")
                st.rerun()
        else:
            st.info("No hay marcas registradas.")
