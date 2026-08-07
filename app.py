import sqlite3
import pandas as pd
import streamlit as st

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
            # Conexión permanente a la nube
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
        # Si la tabla vieja no tiene la columna marca, agregarla
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

    # Insertar categorías por defecto si la tabla está vacía
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
    """Obtiene la lista de categorías registradas."""
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
    """Guarda una nueva categoría en la nube o localmente."""
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
    """Elimina una categoría seleccionada."""
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
    """Obtiene la lista de marcas registradas."""
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
    """Guarda una nueva marca en la nube o localmente."""
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
    """Elimina una marca seleccionada."""
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
    """Guarda un producto en la base de datos activa (Nube o SQLite)."""
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
    """Modifica los datos de un producto en la nube o local."""
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
    """Elimina permanentemente un producto de la base de datos activa."""
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
    """Obtiene los datos desde SQLite o Firestore en formato DataFrame."""
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

# Inicializar almacenamiento
init_db()

def formatear_gs(valor):
    """Formatea un número entero al estilo de Guaraníes paraguayos: Gs. 15.000"""
    try:
        valor_entero = int(valor)
        cadena_formateada = "{:,}".format(valor_entero)
        cadena_paraguay = cadena_formateada.replace(",", ".")
        return f"Gs. {cadena_paraguay}"
    except Exception:
        return f"Gs. {valor}"

st.set_page_config(page_title="Sistema Encanto - Stock", layout="wide", page_icon="📦")

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
    ["📦 Ver Stock / Inventario", "➕ Registrar Producto", "✏️ Editar / Modificar Producto", "🏷️ Gestor de Categorías", "🏢 Gestor de Marcas"],
    captions=["Control de existencias", "Añadir nuevos artículos", "Actualizar o eliminar registros", "Crear y organizar categorías", "Administrar marcas de productos"]
)

# ------------------------------------------
# VISTA: VER STOCK / INVENTARIO
# ------------------------------------------
if opcion == "📦 Ver Stock / Inventario":
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
        st.subheader("📊 Resumen Financiero (Gs.)")
        
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
        
        id_seleccionado = seleccion.split(" - ")[0]
        prod_actual = df_productos[df_productos['id'] == id_seleccionado].iloc[0]
        
        st.markdown("---")
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            nuevo_nombre = st.text_input("Nombre del Producto *", value=prod_actual['nombre'], key="edit_nombre")
            
            # Buscar índice de categoría actual
            try:
                cat_index = lista_categorias.index(prod_actual['categoria'])
            except ValueError:
                cat_index = 0
                
            nueva_categoria = st.selectbox("Categoría", lista_categorias, index=cat_index, key="edit_categoria")
            
            # Buscar índice de marca actual
            try:
                marca_actual_val = prod_actual['marca'] if pd.notna(prod_actual['marca']) else ""
                marca_index = lista_marcas.index(marca_actual_val)
            except ValueError:
                marca_index = 0

            nueva_marca = st.selectbox("Marca", lista_marcas, index=marca_index, key="edit_marca")
            nuevo_stock = st.number_input("Cantidad en stock *", min_value=0, step=1, value=int(prod_actual['stock']), key="edit_stock")
            
        with col_b:
            nuevo_precio_costo = st.number_input("Precio de Costo (Gs.) *", min_value=0, step=500, value=int(prod_actual['precio_costo']), key="edit_costo")
            nueva_ganancia_porcentaje = st.slider("Porcentaje de Ganancia (%)", min_value=20, max_value=100, step=5, value=int(prod_actual['ganancia_porcentaje']), key="edit_ganancia")
            
            nuevo_precio_venta_calculado = int(nuevo_precio_costo * (1 + (nueva_ganancia_porcentaje / 100.0)))
            
            st.markdown("**Nuevo Precio de Venta Sugerido:**")
            st.info(f"💰 {formatear_gs(nuevo_precio_venta_calculado)}  \n*(Costo + {nueva_ganancia_porcentaje}% de ganancia)*")

        nueva_descripcion = st.text_area("Descripción del Producto (Opcional)", value=prod_actual['descripcion'] if prod_actual['descripcion'] else "", key="edit_desc")
        
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
