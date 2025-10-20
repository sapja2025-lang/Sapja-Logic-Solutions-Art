from flask import Flask, render_template,request,redirect, url_for,flash, session #importa de Flask
app =Flask(__name__) #inicializa o instancia
app.secret_key = "clave_secreta"
from flask_mysqldb import MySQL 
import MySQLdb.cursors
from werkzeug.security import generate_password_hash , check_password_hash#importa las funciones de seguridad para encriptar la contraseña

from werkzeug.utils import secure_filename
import os

import secrets
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import make_response
 
app.config['MYSQL_HOST']= 'localhost' #servidor de base de datos
app.config['MYSQL_USER']= 'root'#usuario por defecto
app.config['MYSQL_PASSWORD']= ''
app.config['MYSQL_DB']= 'sapjita'

mysql=MySQL(app) #inicializa la conexion a la base de datos

@app.context_processor
def contar_items_carrito():
    if 'id_usuario' in session:
        id_usuario = session['id_usuario']
        cursor = mysql.connection.cursor()
        cursor.execute("""
            SELECT SUM(dc.cantidad)
            FROM detalle_carrito dc
            JOIN carrito c ON dc.id_carrito = c.id_carrito
            WHERE c.id_usuario = %s
        """, (id_usuario,))
        cantidad = cursor.fetchone() [0]
        cursor.close()
        return dict(carrito_cantidad=cantidad if cantidad else 0)
    return dict(carrito_cantidad=0)

    

def generate_token(email):
    token = secrets.token_urlsafe(32) # Genera un token seguro
    expiry = datetime.now() + timedelta(hours=1) 
    cur = mysql.connection.cursor()
    cur.execute("UPDATE usuarios SET reset_token = %s, token_expiry = %s WHERE correo = %s", (token, expiry, email))
    mysql.connection.commit()
    cur.close()
    return token

def generar_factura_pdf(productos, total, direccion, fecha, id_factura, cliente):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"Factura #{id_factura}")

    # Encabezado
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(250, 750, "SAPJITA")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(240, 730, f"Factura #{id_factura}")
    
    # Datos del cliente y fecha
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, 700, f"Cliente: {cliente}")
    pdf.drawString(50, 685, f"Dirección de entrega: {direccion}")
    pdf.drawString(50, 670, f"Fecha: {fecha.strftime('%Y-%m-%d %H:%M')}")

    # Encabezados de tabla
    y = 630
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "Producto")
    pdf.drawString(250, y, "Cantidad")
    pdf.drawString(350, y, "Precio Unit.")
    pdf.drawString(450, y, "Subtotal")
    y -= 20

    # Línea separadora
    pdf.line(50, y+5, 500, y+5)
    
    # Productos
    pdf.setFont("Helvetica", 10)
    for producto in productos:
        subtotal = float(producto['precio']) * int(producto['cantidad'])
        
        pdf.drawString(50, y, producto['nombre_producto'][:30])
        pdf.drawString(250, y, str(producto['cantidad']))
        pdf.drawString(350, y, f"${producto['precio']:,.0f}")
        pdf.drawString(450, y, f"${subtotal:,.0f}")
        y -= 20

        if y < 100:  # Nueva página si no hay espacio
            pdf.showPage()
            y = 750
            pdf.setFont("Helvetica", 10)

    # Total
    pdf.line(50, y+5, 500, y+5)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(350, y-20, f"Total: ${total:,.0f}")

    pdf.save()
    buffer.seek(0)
    return buffer

def enviar_correo_resete(email, token):
    enlace = url_for('reset', token=token, _external=True)
    cuerpo=(f"""Para restablecer su contraseña, haga clic en el siguiente enlace:
            {enlace}
            Si no solicitó este cambio, ignore este correo electrónico.
            Este enlace es válido por 1 hora""")
    remitente = 'elotakuquelevalevergatodo@gmail.com'
    clave = 'vbpd adre bres hxcc'
    mensaje = MIMEText(cuerpo)
    mensaje['Subject'] = 'Restablecimiento de contraseña'
    mensaje['From'] = 'elotakuquelevalevergatodo@gmail.com'
    mensaje['To'] = email

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(remitente, clave)
    server.sendmail(remitente, email, mensaje.as_string())
    server.quit()

def enviar_factura_email(email, productos, total, direccion, fecha, id_factura, cliente):
    remitente = 'elotakuquelevalevergatodo@gmail.com'
    clave = 'vbpd adre bres hxcc'
    
    mensaje = MIMEMultipart()
    mensaje['Subject'] = f'Tu factura de ROKA REAL.'
    mensaje['From'] = remitente
    mensaje['To'] = email
    
    # Cuerpo del correo
    cuerpo = f"""
    ¡Gracias por tu compra en ROKA REAL!

    Te adjuntamos la factura de tu compra.
    
    Resumen de la compra:
    - Total: ${total:,.0f}
    - Fecha: {fecha.strftime('%Y-%m-%d %H:%M')}
    - Dirección de entrega: {direccion}

    Si tienes alguna pregunta, no dudes en contactarnos.

    ¡Gracias por tu preferencia!
    """
    mensaje.attach(MIMEText(cuerpo))
    
    # Generar y adjuntar PDF
    pdf_buffer = generar_factura_pdf(productos, total, direccion, fecha, id_factura, cliente)
    pdf_attachment = MIMEApplication(pdf_buffer.read(), _subtype="pdf")
    pdf_attachment.add_header('Content-Disposition', 'attachment', filename=f'factura_{id_factura}.pdf')
    mensaje.attach(pdf_attachment)
    
    # Enviar correo
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(remitente, clave)
    server.sendmail(remitente, email, mensaje.as_string())
    server.quit()

@app.route("/")
def index():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT id_categoria, nombre FROM categorias")
    categorias = cursor.fetchall()
    cursor.close()
    return render_template("index.html", categorias=categorias)
 #usamos render_template para mostrar el archivo html(en este caso el index.html)

@app.route('/login', methods=['GET', 'POST']) #ruta para el login, acepta metodos GET y POST
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_ingresada = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("""
        SELECT u.id_usuario ,u.nombres,u.password,t.nombre_tipo_usuario
        FROM usuarios u
        JOIN usuario_tipo_usuario ut ON u.id_usuario= ut.id_usuario
        JOIN tipo_usuario t ON ut.id_tipo_usuario = t.id_tipo_usuario
        WHERE u.correo =%s  
        """, (username,))
        usuario = cur.fetchone()
        

        if usuario and check_password_hash(usuario[2], password_ingresada):
            session['id_usuario']= usuario[0]
            session['usuario'] = usuario[1]
            session['tipo_usuario'] = usuario[3]   # Guarda el nombre del usuario en la sesión
            flash(f"Bienvenido, {usuario[1]}!")

            cur.execute("""
            INSERT INTO registro_login (id_usuario, fecha_login)
            VALUES (%s, NOW())
            """,(usuario[0],))
            mysql.connection.commit()

            cur.close()


            if usuario[3] == 'admin':
                return redirect(url_for('crud'))
            elif usuario[3] == 'usuario':
                return redirect(url_for('index'))
            else:
                flash("Rol de usuario no reconocido")
                return redirect(url_for('login'))
            
        

        else:
            flash("Usuario o contraseña incorrectos")
    return render_template('login.html')

@app.route('/logout') #ruta para el logout
def logout():
    session.clear()  # Limpia la sesión
    flash("Has cerrado sesión exitosamente")
    return redirect(url_for('login'))

@app.route('/registro', methods=['GET', 'POST']) #ruta para el registro, acepta metodos GET y POST
def registro():
    if request.method == 'POST':
        nombres = request.form['nombres']
        apellidos = request.form['apellidos']
        correo = request.form['correo']
        password = request.form['password']
        hash = generate_password_hash(password)

        cur = mysql.connection.cursor() #crea un cursor para ejecutar consultas
        try:
            cur.execute("""INSERT INTO usuarios (nombres, apellidos, correo, password) VALUES (%s, %s, %s, %s)""", (nombres, apellidos, correo, hash))
            mysql.connection.commit() #confirma los cambios en la base de datos


            cur.execute("SELECT id_usuario FROM usuarios WHERE correo = %s", (correo,))
            nuevo_usuario = cur.fetchone()

            cur.execute("INSERT INTO usuario_tipo_usuario (id_usuario, id_tipo_usuario) VALUES (%s, %s)", (nuevo_usuario[0], 2)) # Asigna el rol de 'usuario' (id 2) al nuevo usuario
            mysql.connection.commit()

            flash ("su usuario ha sido registrado exitosamente")
            return redirect(url_for('login'))
        except:
            flash("este corrreo ya esta registrado")
        finally:
            cur.close()
            
            
    return render_template('registro.html')

@app.route ('/olvidarc', methods=['GET', 'POST']) #ruta para olvidar la contraseña, acepta metodos GET y POST
def olvidarc():
    if request.method == 'POST':
        email = request.form['email']
        cur = mysql.connection.cursor()
        cur.execute("SELECT id_usuario FROM usuarios WHERE correo= %s", (email,))
        existe = cur.fetchone()
        cur.close()
       

        if not existe:
            flash("El correo electrónico no está registrado")
            return redirect(url_for('olvidarc'))
        
        token = generate_token(email)
        enviar_correo_resete(email, token)
        flash("Se ha enviado un enlace de restablecimiento de contraseña a su correo electrónico")
        return redirect(url_for('login'))
    return render_template('olvidarc.html')


@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset(token):
    cur = mysql.connection.cursor()
    cur.execute("SELECT id_usuario, token_expiry FROM usuarios WHERE reset_token = %s", (token,))
    usuario = cur.fetchone()
    cur.close()

    # Verificar token
    if not usuario or datetime.now() > usuario[1]:
        flash("❌ El enlace de restablecimiento de contraseña es inválido o ha expirado.")
        return redirect(url_for('olvidarc'))

    if request.method == 'POST':
        nueva_password = request.form.get('nueva_password')
        confirmar_password = request.form.get('confirma')  # 👈 nombre correcto según tu HTML

        # Validar campos vacíos
        if not nueva_password or not confirmar_password:
            flash("⚠️ Debes llenar ambos campos de contraseña.")
            return render_template('reiniciar.html', token=token)

        # Validar coincidencia
        if nueva_password != confirmar_password:
            flash("❌ Las contraseñas no coinciden. Inténtalo de nuevo.")
            return render_template('reiniciar.html', token=token)

        # Si todo está bien, actualiza la contraseña
        hash_nueva_password = generate_password_hash(nueva_password)
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE usuarios 
            SET password = %s, reset_token = NULL, token_expiry = NULL 
            WHERE id_usuario = %s
        """, (hash_nueva_password, usuario[0]))
        mysql.connection.commit()
        cur.close()

        flash("✅ Su contraseña ha sido restablecida exitosamente.")
        return redirect(url_for('login'))

    return render_template('reiniciar.html', token=token)


# CRUD de usuarios
@app.route('/crud')
def crud():
    if 'usuario' not in session:
        flash("Por favor, inicia sesión para acceder a esta página.")
        return redirect(url_for('login'))
    
    elif session.get('tipo_usuario') != 'admin':
        flash("No tienes permiso para acceder a esta página.")
        return redirect(url_for('index'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor) #para que los resultados se devuelvan como diccionarios o columnas
    cursor.execute("""
        SELECT u.id_usuario, u.nombres, u.apellidos, u.correo, t.nombre_tipo_usuario,ut.id_tipo_usuario
        FROM usuarios u 
        LEFT JOIN usuario_tipo_usuario ut ON u.id_usuario = ut.id_usuario
        LEFT JOIN tipo_usuario t ON ut.id_tipo_usuario = t.id_tipo_usuario
                   
                   """)
    usuarios = cursor.fetchall() #obtiene todos los registros de la tabla usuarios en duplas
    cursor.close()
    return render_template('crud.html', usuarios=usuarios)

#funcion para editar usuarios
@app.route('/actualizar/<int:id>', methods=['POST'])
def actualizar (id):
    nombre=request.form['nombres']
    apellidos=request.form['apellidos']
    correo=request.form['correo']
    rol=request.form['rol']
    

    cursor=mysql.connection.cursor()
    cursor.execute("""UPDATE usuarios SET nombres=%s, apellidos=%s, correo=%s WHERE id_usuario=%s""", (nombre, apellidos, correo, id))
    cursor.execute("SELECT * FROM usuario_tipo_usuario WHERE id_usuario=%s", (id,))
    existe=cursor.fetchone()

    if existe:
        cursor.execute("UPDATE usuario_tipo_usuario SET id_tipo_usuario=%s WHERE id_usuario=%s", (rol, id))
    else:
        cursor.execute("INSERT INTO usuario_tipo_usuario (id_usuario, id_tipo_usuario) VALUES (%s, %s)", (id, rol))
    mysql.connection.commit()
    cursor.close()
    return redirect(url_for('crud'))

#funcion para eliminar usuarios
@app.route('/eliminar/<int:id>')
def eliminar (id):
    cursor=mysql.connection.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id_usuario=%s", (id,))
    mysql.connection.commit()
    cursor.close()
    flash("Usuario eliminado exitosamente")
    return redirect(url_for('crud'))



@app.route('/inventario')
def inventario():
    if 'tipo_usuario' not in session or session['tipo_usuario'] != 'admin':
        flash("No tienes permiso para acceder a esta página.")
        return redirect(url_for('login'))
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM productos")
    productos= cursor.fetchall()
    for p in productos:
        p['precio_formateado'] = "{:,.0f}".format(p['precio'])
    cursor.execute("SELECT id_categoria, nombre FROM categorias")
    categorias = cursor.fetchall()
    cursor.close()

    return render_template('inventario.html', productos=productos, categorias=categorias)

@app.route('/agregar_producto', methods=['GET','POST'])
def agregar_producto():

    if 'tipo_usuario' not in session or session['tipo_usuario'] != 'admin':
        flash("No tienes permiso para acceder a esta página.")
        return redirect(url_for('login'))


    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form['descripcion']
        cantidad = request.form['cantidad']
        precio = request.form['precio']
        imagen = request.files['imagen']
        id_categoria = request.form['id_categoria']

        
        filename = secure_filename(imagen.filename)
        imagen.save(os.path.join('static/uploads', filename))
        

        cursor = mysql.connection.cursor()
        cursor.execute("""INSERT INTO productos (nombre_producto, descripcion, cantidad, precio, imagen, id_categoria) 
                       VALUES (%s, %s, %s, %s, %s, %s)
                       """,(nombre, descripcion, cantidad, precio, filename, id_categoria))
        mysql.connection.commit()
        cursor.close()

        flash("Producto agregado exitosamente")
        return redirect(url_for('inventario'))
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT id_categoria, nombre FROM categorias")
    categorias = cursor.fetchall()
    cursor.close()
    return render_template('agregar_producto.html', categorias=categorias)

#funcion para eliminar productos
@app.route('/eliminarproducto/<int:id>')
def eliminarproducto (id):
    cursor=mysql.connection.cursor()
    cursor.execute("DELETE FROM productos WHERE id_producto=%s", (id,))
    mysql.connection.commit()
    cursor.close()
    flash("producto eliminado exitosamente")
    return redirect(url_for('inventario'))


@app.route('/actualizarproducto/<int:id>', methods=['POST'])
def actualizarproducto(id):
    nombre=request.form['nombre']
    precio=request.form['precio']
    descripcion=request.form['descripcion']
    cantidad=request.form['cantidad']
    id_categoria = request.form['id_categoria']
    imagen=request.files['imagen']

    cursor=mysql.connection.cursor()

    if imagen and imagen.filename != '':
        filename= secure_filename(imagen.filename)
        imagen.save(os.path.join('static/uploads', filename))

        cursor.execute("""UPDATE productos SET nombre_producto=%s, 
                       precio=%s, 
                       descripcion=%s, 
                       cantidad=%s,
                        imagen=%s,
                        id_categoria=%s 
                        WHERE id_producto=%s"""
                       , (nombre, precio, descripcion, cantidad, filename, id_categoria, id))

    else:
        cursor.execute("""UPDATE productos SET nombre_producto=%s, 
                       precio=%s, 
                       descripcion=%s, 
                       cantidad=%s,
                       id_categoria=%s 
                       WHERE id_producto=%s""", 
                       (nombre, precio, descripcion, cantidad, id_categoria, id))

    mysql.connection.commit()
    cursor.close()
    flash("Producto actualizado exitosamente")
    return redirect(url_for('inventario'))

#ruta para el catalogo de productos
@app.route('/catalogo', methods=['GET'])
def catalogo():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    query = request.args.get('buscar', '')
    categoria_id = request.args.get('categoria')  # 👈 nuevo parámetro opcional

    if query:
        sql = """SELECT * FROM productos 
                 WHERE nombre_producto LIKE %s OR descripcion LIKE %s"""
        cursor.execute(sql, ('%' + query + '%', '%' + query + '%'))
    elif categoria_id:
        sql = """SELECT p.*, c.nombre AS categoria_nombre
                 FROM productos p
                 JOIN categorias c ON p.id_categoria = c.id_categoria
                 WHERE p.id_categoria = %s"""
        cursor.execute(sql, (categoria_id,))
    else:
        sql = """SELECT p.*, c.nombre AS categoria_nombre
                 FROM productos p
                 LEFT JOIN categorias c ON p.id_categoria = c.id_categoria"""
        cursor.execute(sql)

    productos = cursor.fetchall()
    cursor.close()

    return render_template('catalogo.html', productos=productos, buscar=query)




@app.route('/agregarcarrito/<int:id>', methods=['POST'])
def agregarcarrito(id):
    if 'usuario' not in session:
        flash("Por favor, inicia sesión para agregar productos al carrito.")
        return redirect(url_for('login'))

    cantidad = int(request.form['cantidad'])
    id_usuario = session['id_usuario']

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT cantidad FROM productos WHERE id_producto = %s", (id,))
    stock = cursor.fetchone()[0]
    cursor.execute("SELECT id_carrito FROM carrito WHERE id_usuario = %s", (id_usuario,))
    carrito= cursor.fetchone()

    if not carrito:
        cursor.execute("INSERT INTO carrito (id_usuario) VALUES (%s)", (id_usuario,))
        mysql.connection.commit()
        cursor.execute("SELECT LAST_INSERT_ID()")
        carrito = cursor.fetchone()

    id_carrito = carrito[0]

    cursor.execute("""SELECT cantidad FROM detalle_carrito
                    WHERE id_carrito=%s AND id_producto=%s""", (id_carrito, id))
        
    existente= cursor.fetchone()
    cantidad_total = cantidad 

    if existente:
        cantidad_total += existente[0] if existente[0] else 0
    if cantidad_total > stock:
        flash("No puedes agregar mas unidades de las disponibles en el inventario","warning")
        cursor.close
        return redirect(url_for('catalogo'))
        
    if existente:
        # existente could be a tuple like (cantidad,)
        existente_cantidad = existente[0] if isinstance(existente, (list, tuple)) else existente
        nueva_cantidad = (existente_cantidad or 0) + cantidad
        cursor.execute("""UPDATE detalle_carrito SET cantidad=%s
                       WHERE id_carrito=%s AND id_producto=%s""",
                       (nueva_cantidad, id_carrito, id))
    else:
        cursor.execute("""INSERT INTO detalle_carrito (id_carrito, id_producto, cantidad) 
                   VALUES (%s, %s, %s)
                   """, (id_carrito, id, cantidad))

    mysql.connection.commit()
    cursor.close()

    flash("Producto agregado al carrito")
    return redirect(url_for('catalogo'))


@app.route('/carrito')
def carrito():
    if 'usuario' not in session:
        flash("Por favor, inicia sesión para ver el carrito.")
        return redirect(url_for('login'))
    id_usuario = session.get('id_usuario')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        SELECT p.id_producto, p.nombre_producto, p.precio, p.imagen, dc.cantidad
        FROM detalle_carrito dc
        JOIN carrito c ON dc.id_carrito = c.id_carrito
        JOIN productos p ON dc.id_producto = p.id_producto
        WHERE c.id_usuario = %s""", (id_usuario,))
    productos_carrito = cursor.fetchall()
    cursor.close()
    if not productos_carrito:
        total = 0
    else:
        total = sum(item['precio'] * item['cantidad'] for item in productos_carrito)
    return render_template('carrito.html', productos=productos_carrito, total=total)

@app.route('/actualizar_carrito/<int:id>', methods=['POST'])
def actualizar_carrito(id):
    accion = request.form.get('accion')
    # read the field sent by the form (carrito template uses 'cantidad_actual')
    try:
        cantidad_actual = int(request.form.get('cantidad_actual') or request.form.get('cantidad') or 1)
    except ValueError:
        cantidad_actual = 1
    id_usuario = session.get('id_usuario')

    # Fetch current quantity from detalle_carrito to avoid desync
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT dc.cantidad, c.id_carrito FROM detalle_carrito dc JOIN carrito c ON dc.id_carrito = c.id_carrito WHERE c.id_usuario = %s AND dc.id_producto = %s", (id_usuario, id))
    fila = cursor.fetchone()
    current_qty = fila[0] if fila else 0
    id_carrito = fila[1] if fila else None

    if accion == "sumar":
        nueva_cantidad = current_qty + 1
    elif accion == "restar":
        nueva_cantidad = max(1, current_qty - 1)
    else:
        # manual input
        try:
            nueva_cantidad = int(request.form.get('cantidad_manual', current_qty))
        except ValueError:
            nueva_cantidad = current_qty

    # ensure we have a cursor (we already opened one above)
    cursor.execute("SELECT cantidad FROM productos WHERE id_producto = %s", (id,))
    stock_row = cursor.fetchone()
    stock = stock_row[0] if stock_row else 0

    if nueva_cantidad > stock:
        flash("No puedes agregar más unidades de las disponibles en el inventario", "warning")
        cursor.close()
        return redirect(url_for('carrito'))
    if nueva_cantidad > 0:
        cursor.execute("""
                       UPDATE detalle_carrito dc
                       JOIN carrito c ON dc.id_carrito = c.id_carrito
                          SET dc.cantidad = %s
                          WHERE c.id_usuario = %s AND dc.id_producto = %s""",
                          (nueva_cantidad, id_usuario, id))
        
    else:   
        cursor.execute("""
                       DELETE dc FROM detalle_carrito dc
                       JOIN carrito c ON dc.id_carrito = c.id_carrito
                       WHERE c.id_usuario = %s AND dc.id_producto = %s""",
                       (id_usuario, id)) 
    mysql.connection.commit()
    cursor.close()
    flash("Carrito actualizado","info")
    return redirect(url_for('carrito'))


@app.route('/eliminar_del_carrito/<int:id>')
def eliminar_del_carrito(id):
    id_usuario = session.get('id_usuario')
    cursor = mysql.connection.cursor()

    cursor.execute("""
                       DELETE dc FROM detalle_carrito dc
                       JOIN carrito c ON dc.id_carrito = c.id_carrito
                       WHERE c.id_usuario = %s AND dc.id_producto = %s""",
                       (id_usuario, id)) 
    mysql.connection.commit()
    cursor.close()
    flash("Producto eliminado del carrito","danger")
    return redirect(url_for('carrito'))

@app.route('/vaciar_carrito')
def vaciar_carrito():
    id_usuario = session.get('id_usuario')
    cursor = mysql.connection.cursor()

    cursor.execute("""
                       DELETE dc FROM detalle_carrito dc
                       JOIN carrito c ON dc.id_carrito = c.id_carrito
                       WHERE c.id_usuario = %s""",
                       (id_usuario,)) 
    mysql.connection.commit()
    cursor.close()
    flash("Carrito vaciado","warning")
    return redirect(url_for('carrito'))


@app.route('/pago', methods=['GET', 'POST'])
def pago():
    # Verificar si el usuario ha iniciado sesión
    if 'usuario' not in session:
        flash("Por favor, inicia sesión para continuar con el pago.")
        return redirect(url_for('login'))
    
    id_usuario = session.get('id_usuario')
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Obtener los productos del carrito
    cursor.execute("""
        SELECT p.id_producto, p.nombre_producto, p.precio, dc.cantidad, p.cantidad AS stock
        FROM detalle_carrito dc
        JOIN carrito c ON dc.id_carrito = c.id_carrito
        JOIN productos p ON dc.id_producto = p.id_producto
        WHERE c.id_usuario = %s
    """, (id_usuario,))
    productos = cursor.fetchall()

    # Calcular el total y la cantidad total de productos
    total = sum(p['precio'] * p['cantidad'] for p in productos)
    cantidad_total = sum(p['cantidad'] for p in productos)  # ✅ cantidad real comprada

    # Si el usuario envía el formulario (POST)
    if request.method == 'POST':
        # Capturar campos del formulario
        direccion = request.form.get('direccion')
        confirmar = request.form.get('confirmar_direccion')
        metodo_pago = request.form.get('metodo_pago')

        # Validaciones básicas
        if not direccion or not confirmar:
            flash("Debes ingresar y confirmar la dirección de entrega.", "warning")
            return redirect(url_for('pago'))

        if direccion.strip() != confirmar.strip():
            flash("Las direcciones no coinciden. Por favor, revisa.", "danger")
            return redirect(url_for('pago'))

        if not metodo_pago:
            flash("Debes seleccionar un método de pago.", "warning")
            return redirect(url_for('pago'))

        # Guardar dirección en sesión (para mostrar en factura)
        session['direccion_entrega'] = direccion.strip()
        # Guardar método de pago en sesión (para mostrar en factura)
        session['metodo_pago'] = metodo_pago

        # 🔹 Actualizar dirección del usuario en la base de datos
        cursor.execute("""
            UPDATE usuarios 
            SET direccion = %s 
            WHERE id_usuario = %s
        """, (direccion.strip(), id_usuario))
        mysql.connection.commit()

        # Verificar stock de los productos
        errores = []
        for p in productos:
            if p['cantidad'] > p['stock']:
                errores.append(f"{p['nombre_producto']} excede el stock disponible.")
        if errores:
            flash("Error en el pago: " + ", ".join(errores), "danger")
            cursor.close()
            return redirect(url_for('carrito'))

        # 🔹 Crear factura con cantidad total y método de pago incluido
        cursor.execute("""
            INSERT INTO facturas (fecha, total, cantidad_productos, descripcion, metodo_pago, id_usuario)
            VALUES (NOW(), %s, %s, %s, %s, %s)
        """, (total, cantidad_total, 'Compra realizada desde la web', metodo_pago, id_usuario))
        mysql.connection.commit()

        # Obtener ID de la factura creada
        cursor.execute("SELECT LAST_INSERT_ID() AS id_factura")
        id_factura = cursor.fetchone()['id_factura']

        # 🔹 Insertar registro en compras_ventas con cantidad real
        cursor.execute("""
            INSERT INTO compras_ventas (fecha, cantidad, total, estado, id_factura)
            VALUES (NOW(), %s, %s, %s, %s)
        """, (cantidad_total, total, 'Pagado', id_factura))
        mysql.connection.commit()

        # Relacionar usuario con la compra
        cursor.execute("""
            INSERT INTO usuarios_compras (id_usuario, id_compra_venta)
            VALUES (%s, LAST_INSERT_ID())
        """, (id_usuario,))
        mysql.connection.commit()

        # 🔹 Actualizar inventario (restar cantidad comprada)
        for p in productos:
            cursor.execute(
                "UPDATE productos SET cantidad = cantidad - %s WHERE id_producto = %s",
                (p['cantidad'], p['id_producto'])
            )
        mysql.connection.commit()

        # 🔹 Vaciar el carrito del usuario
        cursor.execute("""
            DELETE dc FROM detalle_carrito dc
            JOIN carrito c ON dc.id_carrito = c.id_carrito
            WHERE c.id_usuario = %s
        """, (id_usuario,))
        mysql.connection.commit()

        # Obtener el correo del usuario
        cursor.execute("SELECT correo, nombres FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        usuario_info = cursor.fetchone()
        email = usuario_info['correo']
        nombre_cliente = usuario_info['nombres']

        # Enviar factura por correo
        try:
            enviar_factura_email(
                email=email,
                productos=productos,
                total=total,
                direccion=direccion,
                fecha=datetime.now(),
                id_factura=id_factura,
                cliente=nombre_cliente
            )
            flash("✅ Pago realizado con éxito. La factura ha sido enviada a tu correo electrónico.", "success")
        except Exception as e:
            flash("✅ Pago realizado con éxito. Se ha generado tu factura, pero hubo un error al enviarla por correo.", "warning")

        # Guardar datos en sesión para mostrar en factura
        session['factura_productos'] = productos
        session['factura_total'] = total
        session['factura_id'] = id_factura

        cursor.close()
        return redirect(url_for('factura'))

    # Si entra por GET (mostrar la página de pago)
    cursor.close()
    return render_template('pago.html', productos=productos, total=total)


@app.route('/factura')
def factura():
    productos = session.get('factura_productos', [])
    total = session.get('factura_total', 0)
    direccion = session.get('direccion_entrega', 'No registrada')

    # Asegurarse de que todos los tipos sean numéricos
    try:
        total = float(total)
    except (ValueError, TypeError):
        total = 0

    for p in productos:
        try:
            p['precio'] = float(p['precio'])
            p['cantidad'] = int(p['cantidad'])
        except (ValueError, TypeError):
            p['precio'] = 0.0
            p['cantidad'] = 0

    return render_template('factura.html', productos=productos, total=total, direccion=direccion)


@app.route('/historial')
def historial():
    if 'id_usuario' not in session:
        flash("Por favor, inicia sesión para ver tu historial.")
        return redirect(url_for('login'))

    tipo_usuario = session.get('tipo_usuario')
    id_usuario = session.get('id_usuario')
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Si es un usuario normal → historial de compras
    if tipo_usuario == 'usuario':
        cursor.execute("""
            SELECT f.id_factura, f.fecha, f.total, f.cantidad_productos, f.descripcion
            FROM facturas f
            WHERE f.id_usuario = %s
            ORDER BY f.fecha DESC
        """, (id_usuario,))
        historial = cursor.fetchall()
        cursor.close()
        return render_template('historial_compras.html', historial=historial)

    # Si es admin → historial de ventas
    elif tipo_usuario == 'admin':
        cursor.execute("""
            SELECT f.id_factura, f.fecha, f.total, f.cantidad_productos, f.descripcion,
                   u.nombres AS cliente
            FROM facturas f
            JOIN usuarios u ON f.id_usuario = u.id_usuario
            ORDER BY f.fecha DESC
        """)
        historial = cursor.fetchall()
        cursor.close()
        return render_template('historial_ventas.html', historial=historial)

    flash("Tipo de usuario no reconocido.")
    return redirect(url_for('index'))

@app.route('/historial/pdf')
def historial_pdf():
    if 'id_usuario' not in session:
        flash("Por favor, inicia sesión para generar tu historial.")
        return redirect(url_for('login'))

    id_usuario = session.get('id_usuario')
    tipo_usuario = session.get('tipo_usuario')

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Historial de Compras")

    # Encabezado
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(200, 750, "Historial de Compras")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, 735, f"Usuario: {session.get('usuario', 'Desconocido')}")
    pdf.drawString(50, 720, f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Espacio inicial para las filas
    y = 690

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if tipo_usuario == 'usuario':
        cursor.execute("""
            SELECT f.id_factura, f.fecha, f.total, f.cantidad_productos, f.descripcion, f.metodo_pago
            FROM facturas f
            WHERE f.id_usuario = %s
            ORDER BY f.fecha DESC
        """, (id_usuario,))
    else:  # Si es admin, muestra todas
        cursor.execute("""
            SELECT f.id_factura, f.fecha, f.total, f.cantidad_productos, f.descripcion, 
                   u.nombres AS cliente, f.metodo_pago
            FROM facturas f
            JOIN usuarios u ON f.id_usuario = u.id_usuario
            ORDER BY f.fecha DESC
        """)

    compras = cursor.fetchall()
    cursor.close()

    # Si no hay registros
    if not compras:
        pdf.setFont("Helvetica-Oblique", 12)
        pdf.drawString(200, y, "No hay compras registradas.")
    else:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(50, y, "ID")
        pdf.drawString(90, y, "Fecha")
        pdf.drawString(180, y, "Total")
        pdf.drawString(250, y, "Productos")
        pdf.drawString(330, y, "Método")
        pdf.drawString(420, y, "Descripción")
        y -= 15
        pdf.line(50, y, 550, y)
        y -= 15

        pdf.setFont("Helvetica", 9)
        for compra in compras:
            if y < 80:  # Salto de página automático
                pdf.showPage()
                pdf.setFont("Helvetica-Bold", 10)
                pdf.drawString(50, 750, "Historial de Compras (continuación)")
                pdf.setFont("Helvetica", 9)
                y = 730

            pdf.drawString(50, y, str(compra['id_factura']))
            pdf.drawString(90, y, compra['fecha'].strftime('%Y-%m-%d'))
            pdf.drawString(180, y, f"${compra['total']:,.0f}")
            pdf.drawString(250, y, str(compra['cantidad_productos']))
            pdf.drawString(330, y, compra.get('metodo_pago', 'N/A')[:15])
            pdf.drawString(420, y, compra['descripcion'][:40])
            y -= 15

    pdf.save()
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=historial_compras.pdf'
    return response


@app.route('/historial_ventas/pdf')
def historial_ventas_pdf():
    if 'tipo_usuario' not in session or session.get('tipo_usuario') != 'admin':
        flash("Solo los administradores pueden generar el historial de ventas.")
        return redirect(url_for('login'))

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Historial de Ventas")

    # 🔹 Encabezado
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(200, 750, "Historial de Ventas (Administrador)")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, 735, f"Administrador: {session.get('usuario', 'Desconocido')}")
    pdf.drawString(50, 720, f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    y = 690

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        SELECT f.id_factura, f.fecha, f.total, f.cantidad_productos, f.descripcion, 
               u.nombres AS cliente, f.metodo_pago
        FROM facturas f
        JOIN usuarios u ON f.id_usuario = u.id_usuario
        ORDER BY f.fecha DESC
    """)
    ventas = cursor.fetchall()
    cursor.close()

    # 🔹 Si no hay ventas
    if not ventas:
        pdf.setFont("Helvetica-Oblique", 12)
        pdf.drawString(200, y, "No hay ventas registradas.")
    else:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(50, y, "ID")
        pdf.drawString(90, y, "Fecha")
        pdf.drawString(160, y, "Cliente")
        pdf.drawString(300, y, "Total")
        pdf.drawString(380, y, "Método")
        pdf.drawString(460, y, "Descripción")
        y -= 15
        pdf.line(50, y, 550, y)
        y -= 15

        total_general = 0  # 🔹 acumulador del total vendido

        pdf.setFont("Helvetica", 9)
        for venta in ventas:
            if y < 80:
                pdf.showPage()
                pdf.setFont("Helvetica-Bold", 10)
                pdf.drawString(200, 750, "Historial de Ventas (continuación)")
                pdf.setFont("Helvetica", 9)
                y = 730

            metodo = venta.get('metodo_pago') or 'N/A'
            descripcion = venta.get('descripcion') or 'Sin descripción'

            pdf.drawString(50, y, str(venta['id_factura']))
            pdf.drawString(90, y, venta['fecha'].strftime('%Y-%m-%d'))
            pdf.drawString(160, y, venta['cliente'][:18])
            pdf.drawString(300, y, f"${venta['total']:,.0f}")
            pdf.drawString(380, y, metodo[:15])
            pdf.drawString(460, y, descripcion[:35])

            total_general += venta['total']
            y -= 15

        # 🔹 Total general al final
        if y < 100:
            pdf.showPage()
            y = 730

        pdf.setFont("Helvetica-Bold", 12)
        pdf.line(50, y - 5, 550, y - 5)
        pdf.drawString(300, y - 20, f"TOTAL GENERAL VENDIDO: ${total_general:,.0f}")

    pdf.save()
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=historial_ventas.pdf'
    return response



                       
if __name__ =="__main__": #verifica si el archivo se ejecuta directamente
    app.run(port=5000,debug=True) #permite ver errores detalladamente y recarga e servidor automaticamente cunado se hacen cambios