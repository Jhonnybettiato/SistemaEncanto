import sqlite3
import pandas as pd
import streamlit as st

# ==========================================
# 1. CONFIGURACIÓN Y MIGRACIÓN DE LA BASE DE DATOS
# ==========================================
def init_db():
    """Inicializa la base de datos sqlite y migra la estructura si es necesario."""
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    
    # Comprobar si existe la tabla vieja para migrarla sin errores
    cursor.execute("PRAGMA table_info(productos)")
    columnas = [col[1] for col in cursor.fetchall()]
    
    # Si la tabla tiene el formato antiguo (precio simple), la borramos para reestructurar
    if columnas and "precio" in columnas:
        cursor.execute("DROP TABLE productos")
        conn.commit()

    # Creamos la tabla con los campos de costo, ganancia y venta adaptados a Guaraníes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            categoria TEXT,
            precio_costo INTEGER NOT NULL,
            ganancia_porcentaje INTEGER NOT NULL,
            precio_venta INTEGER NOT NULL,
            stock INTEGER NOT NULL,
            descripcion TEXT
        )
    """)
    conn.commit()
    conn.close()

def registrar_producto(nombre, categoria, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion):
    """Inserta un nuevo producto en la base de datos local."""
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO productos (nombre, categoria, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (nombre, categoria, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion))
    conn.commit()
    conn.close()

def obtener_productos():
    """Recupera todos los productos de la tabla en formato DataFrame de Pandas."""
    conn = sqlite3.connect("inventario.db")
    df = pd.read_sql_query("SELECT * FROM productos", conn)
    conn.close()
    return df

# Inicializar la base de datos al arrancar el hilo de ejecución
init_db()

# Helper para el formateo de los importes locales de Paraguay
def formatear_gs(valor):
    """Formatea un número entero al estilo de Guaraníes paraguayos: Gs. 15.000"""
    return f"Gs. {int(valor):,}".replace(",", ".")

# ==========================================
# 2. INTERFAZ DE USUARIO (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Sistema Encanto - Stock", layout="wide", page_icon="📦")

# Inyección de estilos CSS personalizados para mejorar el aspecto visual de la interfaz
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
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# Menú de navegación lateral intuitivo
st.sidebar.title("✨ Sistema Encanto")
st.sidebar.markdown("---")
opcion = st.sidebar.radio(
    "Selecciona una opción:",
    ["📦 Ver Stock / Inventario", "➕ Registrar Producto"],
    captions=["Control de existencias", "Añadir nuevos artículos"]
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
        # Buscador rápido por coincidencia de texto
        busqueda = st.text_input("🔍 Buscar producto por nombre", "", placeholder="Escribe el nombre del producto...")
        
        if busqueda:
            df_productos_filtrados = df_productos[df_productos['nombre'].str.contains(busqueda, case=False)]
        else:
            df_productos_filtrados = df_productos

        # Crear copias formateadas exclusivamente para la visualización (evitando alterar los números nativos)
        df_visual = df_productos_filtrados.copy()
        df_visual['precio_costo'] = df_visual['precio_costo'].apply(formatear_gs)
        df_visual['ganancia_porcentaje'] = df_visual['ganancia_porcentaje'].apply(lambda x: f"{x}%")
        df_visual['precio_venta'] = df_visual['precio_venta'].apply(formatear_gs)
        df_visual['stock'] = df_visual['stock'].apply(lambda x: f"{x} uds")

        # Configuración y visualización de la tabla
        st.dataframe(
            df_visual,
            column_config={
                "id": "ID",
                "nombre": "Producto",
                "categoria": "Categoría",
                "precio_costo": "Precio Costo",
                "ganancia_porcentaje": "Ganancia (%)",
                "precio_venta": "Precio Venta",
                "stock": "Stock",
                "descripcion": "Descripción"
            },
            hide_index=True,
            use_container_width=True
        )
        
        # Resumen financiero dinámico en base al inventario
        st.markdown("---")
        st.subheader("📊 Resumen Financiero (Gs.)")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_productos = len(df_productos_filtrados)
        total_stock = int(df_productos_filtrados['stock'].sum())
        
        # Cálculos de valorización financiera
        valor_costo = int((df_productos_filtrados['precio_costo'] * df_productos_filtrados['stock']).sum())
        valor_venta = int((df_productos_filtrados['precio_venta'] * df_productos_filtrados['stock']).sum())
        ganancia_estimada = valor_venta - valor_costo
        
        with col1:
            st.metric("Total de Productos", f"{total_productos} tipos")
        with col2:
            st.metric("Existencias en Stock", f"{total_stock} uds")
        with col3:
            st.metric("Inversión (Total Costo)", formatear_gs(valor_costo))
        with col4:
            st.metric("Ganancia Estimada", formatear_gs(ganancia_estimada), help="Diferencia entre el precio de venta y el precio de costo de tu stock disponible.")

# ------------------------------------------
# VISTA: REGISTRAR PRODUCTO
# ------------------------------------------
elif opcion == "➕ Registrar Producto":
    st.markdown('<p class="main-title">➕ Registro de Nuevo Producto</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Añade nuevos artículos definiendo su costo de compra y margen de utilidad deseado.</p>', unsafe_allow_html=True)
    
    # Formulario interactivo
    with st.form("registro_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        
        with col_a:
            nombre = st.text_input("Nombre del Producto *", placeholder="Ej. Encanto Imperial 100ml")
            categoria = st.selectbox("Categoría", ["Perfumes", "Cosméticos", "Cuidado Personal", "Otros"])
            stock = st.number_input("Cantidad inicial en stock *", min_value=1, step=1, value=1)
            
        with col_b:
            # Entrada en Guaraníes para el costo de adquisición
            precio_costo = st.number_input("Precio de Costo (Gs.) *", min_value=0, step=500, value=0, 
                                           help="¿Cuánto te costó adquirir este producto?")
            
            # Selección interactiva de ganancia del 30% al 100%
            ganancia_porcentaje = st.slider("Porcentaje de Ganancia (%)", min_value=30, max_value=100, step=5, value=30,
                                            help="Selecciona el margen que deseas ganar por encima del costo.")
            
            # Cálculo automático en tiempo real
            precio_venta_calculado = int(precio_costo * (1 + (ganancia_porcentaje / 100)))
            
            # Mostramos el precio de venta calculado de manera llamativa
            st.markdown(f"**Precio de Venta Sugerido:**")
            st.info(f"💰 {formatear_gs(precio_venta_calculado)}  \n*(Costo + {ganancia_porcentaje}% de ganancia)*")

        descripcion = st.text_area("Descripción del Producto (Opcional)", placeholder="Añade notas, especificaciones o fragancias...")
        
        st.markdown("---")
        guardar = st.form_submit_button("💾 Guardar y Registrar")
        
        if guardar:
            if nombre.strip() == "":
                st.error("El nombre del producto es requerido para el registro.")
            elif precio_costo <= 0:
                st.error("El precio de costo debe ser mayor a Gs. 0.")
            else:
                registrar_producto(nombre, categoria, precio_costo, ganancia_porcentaje, precio_venta_calculado, stock, descripcion)
                st.success(f"✔️ ¡El producto '{nombre}' ha sido registrado con éxito a un precio de venta de {formatear_gs(precio_venta_calculado)}!")
