import sqlite3
import pandas as pd
import streamlit as st

def init_db():
    """Inicializa la base de datos y migra la estructura si es necesario."""
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    
    # Comprobar si existe la tabla vieja para migrarla sin errores
    cursor.execute("PRAGMA table_info(productos)")
    columnas = [col[1] for col in cursor.fetchall()]
    
    # Si la tabla tiene el formato antiguo, la reestructuramos
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

def actualizar_producto(id_prod, nombre, categoria, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion):
    """Actualiza los datos de un producto existente en la base de datos."""
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE productos
        SET nombre = ?, categoria = ?, precio_costo = ?, ganancia_porcentaje = ?, precio_venta = ?, stock = ?, descripcion = ?
        WHERE id = ?
    """, (nombre, categoria, precio_costo, ganancia_porcentaje, precio_venta, stock, descripcion, id_prod))
    conn.commit()
    conn.close()

def eliminar_producto(id_prod):
    """Elimina permanentemente un producto de la base de datos."""
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM productos WHERE id = ?", (id_prod,))
    conn.commit()
    conn.close()

def obtener_productos():
    """Recupera todos los productos de la tabla en formato DataFrame de Pandas."""
    conn = sqlite3.connect("inventario.db")
    df = pd.read_sql_query("SELECT * FROM productos", conn)
    conn.close()
    return df

# Inicializar la base de datos al arrancar
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
opcion = st.sidebar.radio(
    "Selecciona una opción:",
    ["📦 Ver Stock / Inventario", "➕ Registrar Producto", "✏️ Editar / Modificar Producto"],
    captions=["Control de existencias", "Añadir nuevos artículos", "Actualizar o eliminar registros"]
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
        # Buscador rápido
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
    
    with st.form("registro_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        
        with col_a:
            nombre = st.text_input("Nombre del Producto *", placeholder="Ej. Encanto Imperial 100ml")
            categoria = st.selectbox("Categoría", ["Perfumes", "Cosméticos", "Cuidado Personal", "Otros"])
            stock = st.number_input("Cantidad inicial en stock *", min_value=1, step=1, value=1)
            
        with col_b:
            precio_costo = st.number_input("Precio de Costo (Gs.) *", min_value=0, step=500, value=0)
            ganancia_porcentaje = st.slider("Porcentaje de Ganancia (%)", min_value=30, max_value=100, step=5, value=30)
            
            precio_venta_calculado = int(precio_costo * (1 + (ganancia_porcentaje / 100.0)))
            
            st.markdown("**Precio de Venta Sugerido:**")
            st.info(f"💰 {formatear_gs(precio_venta_calculado)}  \n*(Costo + {ganancia_porcentaje}% de ganancia)*")

        descripcion = st.text_area("Descripción del Producto (Opcional)", placeholder="Fragancias, notas u observaciones...")
        
        st.markdown("---")
        guardar = st.form_submit_button("💾 Guardar y Registrar")
        
        if guardar:
            if nombre.strip() == "":
                st.error("El nombre del producto es requerido.")
            elif precio_costo <= 0:
                st.error("El precio de costo debe ser mayor a Gs. 0.")
            else:
                registrar_producto(nombre, categoria, precio_costo, ganancia_porcentaje, precio_venta_calculado, stock, descripcion)
                st.success(f"✔️ ¡El producto '{nombre}' ha sido registrado con éxito a un precio de venta de {formatear_gs(precio_venta_calculado)}!")

# ------------------------------------------
# VISTA: EDITAR / MODIFICAR PRODUCTO
# ------------------------------------------
elif opcion == "✏️ Editar / Modificar Producto":
    st.markdown('<p class="main-title">✏️ Editar / Modificar Producto</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Selecciona un producto registrado para modificar sus precios, stock o eliminarlo del sistema.</p>', unsafe_allow_html=True)
    
    df_productos = obtener_productos()
    
    if df_productos.empty:
        st.info("No tienes productos registrados para modificar en este momento.")
    else:
        # Menú desplegable para buscar y seleccionar el producto
        lista_productos = [f"{row['id']} - {row['nombre']}" for _, row in df_productos.iterrows()]
        seleccion = st.selectbox("Selecciona el producto que deseas editar:", lista_productos)
        
        # Extraer el ID correspondiente
        id_seleccionado = int(seleccion.split(" - ")[0])
        prod_actual = df_productos[df_productos['id'] == id_seleccionado].iloc[0]
        
        st.markdown("---")
        
        # Formulario de modificación pre-cargado con los datos actuales
        with st.form("edicion_form", clear_on_submit=False):
            col_a, col_b = st.columns(2)
            
            with col_a:
                nuevo_nombre = st.text_input("Nombre del Producto *", value=prod_actual['nombre'])
                
                categorias = ["Perfumes", "Cosméticos", "Cuidado Personal", "Otros"]
                try:
                    cat_index = categorias.index(prod_actual['categoria'])
                except ValueError:
                    cat_index = 0
                    
                nueva_categoria = st.selectbox("Categoría", categorias, index=cat_index)
                nuevo_stock = st.number_input("Cantidad en stock *", min_value=0, step=1, value=int(prod_actual['stock']))
                
            with col_b:
                nuevo_precio_costo = st.number_input("Precio de Costo (Gs.) *", min_value=0, step=500, value=int(prod_actual['precio_costo']))
                nueva_ganancia_porcentaje = st.slider("Porcentaje de Ganancia (%)", min_value=30, max_value=100, step=5, value=int(prod_actual['ganancia_porcentaje']))
                
                nuevo_precio_venta_calculado = int(nuevo_precio_costo * (1 + (nueva_ganancia_porcentaje / 100.0)))
                
                st.markdown("**Nuevo Precio de Venta Sugerido:**")
                st.info(f"💰 {formatear_gs(nuevo_precio_venta_calculado)}  \n*(Costo + {nueva_ganancia_porcentaje}% de ganancia)*")

            nueva_descripcion = st.text_area("Descripción del Producto (Opcional)", value=prod_actual['descripcion'] if prod_actual['descripcion'] else "")
            
            st.markdown("---")
            guardar_cambios = st.form_submit_button("💾 Guardar Cambios")
            
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
                        nuevo_precio_costo, 
                        nueva_ganancia_porcentaje, 
                        nuevo_precio_venta_calculado, 
                        nuevo_stock, 
                        nueva_descripcion
                    )
                    st.success(f"✔️ ¡El producto '{nuevo_nombre}' ha sido actualizado con éxito!")
                    st.rerun()

        # Sección para eliminar producto de forma segura
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("⚠️ Zona de Eliminación")
        
        confirmar_borrado = st.checkbox(f"Confirmo que deseo borrar de forma permanente el producto: **{prod_actual['nombre']}**")
        
        if st.button("🗑️ Eliminar Producto Definitivamente", type="primary", disabled=not confirmar_borrado):
            eliminar_producto(id_seleccionado)
            st.success(f"✔️ ¡El producto '{prod_actual['nombre']}' ha sido eliminado con éxito!")
            st.rerun()
```
eof

---

### 🚀 Pasos sencillos para actualizarlo ahora:

1. Ve a la pantalla del Canvas de la derecha y haz clic en la opción **"Copiar contenido"** (ahora copiará **únicamente** las líneas de código correctas).
2. Abre tu archivo local `app.py`, borra todo su contenido y pega el nuevo.
3. Guarda el archivo (`Ctrl + S`).
4. Ejecuta tus comandos de siempre en la terminal:
   ```bash
   git add app.py
   git commit -m "Corregido: Archivo python limpio sin textos explicativos de chat"
   git push origin main
