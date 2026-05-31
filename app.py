import sqlite3
import pandas as pd
import streamlit as st


# ==========================================
# 1. CONFIGURACIÓN DE LA BASE DE DATOS
# ==========================================
def init_db():
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    # Creamos la tabla si no existe
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            categoria TEXT,
            precio REAL NOT NULL,
            stock INTEGER NOT NULL,
            descripcion TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def registrar_producto(nombre, categoria, precio, stock, descripcion):
    conn = sqlite3.connect("inventario.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO productos (nombre, categoria, precio, stock, descripcion)
        VALUES (?, ?, ?, ?, ?)
    """,
        (nombre, categoria, precio, stock, descripcion),
    )
    conn.commit()
    conn.close()


def obtener_productos():
    conn = sqlite3.connect("inventario.db")
    df = pd.read_sql_query("SELECT * FROM productos", conn)
    conn.close()
    return df


# Inicializar la base de datos al arrancar
init_db()

# ==========================================
# 2. INTERFAZ DE USUARIO (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Registro de Inventario", layout="wide")

st.title("📦 Sistema de Registro de Productos")
st.markdown("---")

# Creamos dos columnas: una para el formulario y otra para ver el inventario
col_form, col_vista = st.columns([1, 2])

with col_form:
    st.subheader("📝 Registrar Nuevo Producto")

    # Formulario de entrada
    with st.form("form_producto", clear_on_submit=True):
        nombre = st.text_input("Nombre del Producto *", placeholder="Ej. Resina Epoxi")
        categoria = st.selectbox(
            "Categoría",
            ["Electrónica", "Herramientas", "Materiales", "Otros"],
        )

        # Usamos columnas pequeñas dentro del formulario para los números
        col_p, col_s = st.columns(2)
        with col_p:
            precio = st.number_input("Precio ($) *", min_value=0.0, format="%.2f")
        with col_s:
            stock = st.number_input("Stock Inicial *", min_value=0, step=1)

        descripcion = st.text_area(
            "Descripción", placeholder="Detalles opcionales del producto..."
        )

        boton_guardar = st.form_submit_button("Guardar Producto")

    # Lógica al enviar el formulario
    if boton_guardar:
        if nombre.strip() == "":
            st.error("El nombre del producto es obligatorio.")
        elif precio <= 0:
            st.error("El precio debe ser mayor a 0.")
        else:
            registrar_producto(nombre, categoria, precio, stock, descripcion)
            st.success(f"¡'{nombre}' registrado con éxito!")
            # Recargar la página para actualizar la tabla visual
            st.rerun()

with col_vista:
    st.subheader("📊 Productos en Inventario")

    # Leer datos actuales
    df_productos = obtener_productos()

    if df_productos.empty:
        st.info("Aún no hay productos registrados. ¡Usa el formulario para añadir el primero!")
    else:
        # Buscador rápido
        busqueda = st.text_input("🔍 Buscar producto por nombre", "")
        if busqueda:
            df_productos = df_productos[
                df_productos["nombre"].str.contains(busqueda, case=False)
            ]

        # Mostrar tabla formateada de manera interactiva
        st.dataframe(
            df_productos,
            column_config={
                "id": "ID",
                "nombre": "Producto",
                "categoria": "Categoría",
                "precio": st.column_config.NumberColumn("Precio", format="$ %.2f"),
                "stock": st.column_config.NumberColumn("Stock", format="%d uds"),
                "descripcion": "Descripción",
            },
            hide_index=True,
            use_container_width=True,
        )

        # Métricas rápidas en la parte inferior
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Productos Únicos", len(df_productos))
        m2.metric("Total Unidades en Stock", int(df_productos["stock"].sum()))
        m3.metric(
            "Valor Total del Inventario",
            f"$ {(df_productos['precio'] * df_productos['stock']).sum():,.2f}",
        )
