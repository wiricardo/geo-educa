# Convenciones del proyecto

Decisiones tomadas durante la construcción de GEO_EDUCA. Están aquí para que no haya
que volver a discutirlas y para que quien retome el proyecto sepa por qué las cosas son
como son.

---

## 1. Cómo se escribe

**Nada de rayas largas.** Ni en el código, ni en la interfaz, ni en la documentación, ni
en los mensajes de commit. Se usan dos puntos, coma, paréntesis o punto seguido. En
nombres compuestos, guion simple. La raya larga es un recurso del inglés y delata texto
generado.

**Nada de punto medio como separador.** Nada de "Matemática · 4.° de primaria": se
escribe "Matemática en 4.° de primaria". Repetido se vuelve un tic tan reconocible como
la raya larga.

**Los títulos nombran, no narran.** "Fuente", no "La fuente". "Ponderación", no "Es una
muestra, no un censo". "Alcance del análisis", no "Lo que estos datos no dicen".

**Los textos de la interfaz se escriben para quien la usa**, no para quien la construyó.
Nada de explicar que un filtro no recorta una página, ni de hablar del almacén, ni de
decir que con un punto no hay pendiente que dibujar. Los avisos de error nombran lo que
el lector puede cambiar, no dicen "esta combinación".

**Sin sobreinterpretar.** Se describe lo que miden los datos. No se infieren causas, no
se adorna un hallazgo con lenguaje dramático, no se llama trayectoria a lo que no lo es.

**Las advertencias metodológicas viven en una sola página**, no repartidas por las
pantallas de análisis. Cada página enlaza ahí desde su pie.

**Se escribe para quien no conoce la evaluación.** No para quien ya leyó el informe
técnico. Esa persona existe y es la que más necesita la plataforma.

**El rótulo explica, no nombra.** "Rindieron la prueba" y "Representan a", no "Evaluados"
y "Estimados". Cuando el rótulo dice lo que es, sobra la línea de ayuda debajo. Los
términos oficiales se quedan en el glosario, que es donde los busca quien los necesita.

**Una definición no puede apoyarse en el vocabulario que hay que explicar.** "Estudiantes
en Previo al inicio o En inicio" define un nivel nombrando otros dos, que es justo lo que
no sabe quien lee. Cada nivel de logro lleva su glosa de una línea al lado del nombre.

**Un número y un gráfico juntos tienen que decir qué relación guardan.** Si la cifra
grande es la suma de dos tramos de la barra de al lado, eso se escribe o se dibuja. Nadie
lo deduce.

**Explicar con una comparación antes que con el término correcto.** "305 escuelas frente
a 4 816" se entiende solo; "la muestra no tiene representatividad regional" no le dice
nada a quien no conoce la palabra.

**El método no es información para la portada, es una credencial.** "Calculado sobre el
microdato con el diseño muestral completo" no ayuda a leer la cifra: dice lo bien que
está hecho el trabajo. Eso va en Notas sobre los datos.

---

## 2. Cómo se ve

El estilo se llama **Bosque**: oscuro, verdes profundos, acentos terracota y ámbar,
tipografía Plus Jakarta Sans, formas muy redondeadas con píldoras en los controles.

**Toda la identidad vive en dos archivos**: `app/core/theme.py` y
`.streamlit/config.toml`. Las páginas no escriben colores literales. Gracias a eso se
pasó de un tema claro azul a este sin tocar ninguna página.

**Solo hay dos fondos**: el de la página y el verde de la navegación, que se apoya
encima. Un tercer tono por detrás del panel delata su caja.

**Sin tropos visuales de IA**: nada de franjas de color a la izquierda de los avisos,
nada de degradados de adorno, nada de emoji. Los iconos son los Material Symbols de
Streamlit.

**Las escalas de datos no son decoración:**

- Los cuatro niveles de logro usan una escala divergente, cálida de un lado y fría del
  otro, porque tienen un umbral claro en medio entre quienes no llegan y quienes al
  menos avanzan. Ese corte es lo que el ojo debe encontrar primero.
- El mapa usa una escala secuencial de un tono. Sobre fondo oscuro, la intensidad crece
  hacia el claro.
- Las categorías de conglomerado son cualitativas, no una escala: azul contra terracota,
  que sigue funcionando con daltonismo.
- Las unidades sin dato suficiente van en negro con trama, nunca con el color más claro
  de la escala: tienen que leerse como ausencia, no como un valor bajo. El negro, y no
  un gris: el gris que había caía a un paso del lienzo del mapa y se perdía contra él.
- El negro cubre dos casos, no tener dato y tenerlo sobre muy pocos estudiantes, así
  que el tooltip dice cuál de los dos es. Sin eso, una unidad con cifra pintada en negro
  parece un fallo del mapa.

**El color tiene dirección.** Una cifra toma el color de lo que significa que suba: cálido
cuando más es peor, frío cuando más es mejor. Es la misma regla de la escala del mapa.
Un 30,9 % de estudiantes que no llegan a lo esperado, pintado en el verde de la
plataforma, se lee como una buena noticia.

**Una diferencia no se cuenta con un signo.** El signo de la resta entre dos grupos
cambia de sentido con el indicador y con el área evaluada: en Matemática de 4.° de
primaria, Hombre menos Mujer sale negativa, y en Lectura positiva. Quién queda por detrás
se decide comparando los dos valores con `mas_es_peor` y se dice con el nombre del grupo,
en una frase. Y la brecha no se pinta del color de lo bueno: una distancia confirmada
entre dos grupos no es una buena noticia.

**Las clases del tema no se reutilizan para otra cosa.** `theme.py` define `.tarjeta`,
`.rotulo`, `.nota` y `.aviso`, y una clase nueva que repita uno de esos nombres hereda su
fondo y su relleno: `.tarjeta` ya trae `padding: 18px 20px`, así que una tarjeta propia
con ese nombre aparecía metida dentro de otra caja. Antes de nombrar una clase, mirar esa
lista.

**Los bloques de una página se separan con una línea fina**, la misma que separa la barra
de filtros del contenido. Solo con aire de por medio, varios bloques seguidos se leen
como una página larga.

**Los globos de texto de los mapas se componen a mano.** La tabla de dos columnas que
arma folium se estrangula dentro de un ancho máximo y acaba partiendo las palabras letra
a letra.

**Cifras en formato peruano**: coma decimal, espacio como separador de miles. Números
tabulares en tablas. Se redondea solo al mostrar, nunca al calcular: sumar valores ya
redondeados produjo dos errores en este proyecto.

---

## 3. Cómo está organizada la aplicación

- **Navegación a la izquierda**, con el nombre del proyecto por encima de las secciones.
- **Barra superior** con los filtros de grado y área, en las páginas donde recortan algo.
- **Asistente anclado a la derecha**, presente en las páginas de datos.
- **Panorama no lleva filtros**: resume los tres grados a la vez.
- **Las páginas de Ajustes** no llevan filtros ni asistente, y aprovechan todo el ancho.

Son dos reglas distintas y no coinciden: hay páginas sin filtros que sí llevan asistente.

**Explorar y Analizar se escriben en dos registros distintos.** Panorama, Mapa y Brechas
son para quien solo está mirando: la conclusión en lenguaje corriente y nada del
vocabulario del muestreo. Análisis espacial y Focalización son donde caben el índice de
Moran, los conglomerados y los p-valores. Toda la precisión formal que se saca de
Explorar aterriza en Notas sobre los datos, que existe para eso. Una frase de Explorar
que haya que releer ya falló: «el orden fino de esta lista no se sostiene» y «parejas de
regiones vecinas» se cambiaron por «la mayoría de estas regiones están demasiado cerca
entre sí para ordenarlas».

**Las perillas metodológicas no se ofrecen en la página de entrada.** El umbral de muestra
está fijo en el mapa y se puede mover en Análisis espacial y en Focalización, donde forma
parte del análisis. Ofrecerlo en la portada es ofrecer desactivarlo: con el umbral en
cero, una UGEL de tres estudiantes con 100 % se pinta igual que Lima con 3 061.

**Cada control lleva su propia clave y no recibe `index` ni `value`.** Un widget de
Streamlit sin clave toma su identidad de sus parámetros, y pasarle un índice calculado
desde el mismo filtro que él escribe lo convierte en otro widget en cuanto el filtro
cambia: se pierde el primer clic y durante un instante se dibujan los dos a la vez.
`estado.sembrar` se encarga de que el control siga al filtro cuando lo mueve el asistente.

**Lo que se añade al mapa tiene que colgar del mapa.** `st_folium` no publica el script
de la raíz de la figura: recorre el objeto `Map` y sus hijos, así que todo lo que se
cuelgue de `get_root().script` se pierde al renderizar dentro de Streamlit. Un control
propio se escribe como `MacroElement` con su plantilla y entra con `mapa.add_child`.

El directorio de páginas se llama `paginas` y no `pages` porque Streamlit activa su
navegación automática al encontrar esa carpeta y anula la declarada con `st.navigation`.

---

## 4. Cómo se tratan los datos

**Siempre ponderar.** La ENLA es muestral. Sin los pesos, las cifras no coinciden con las
oficiales: el porcentaje satisfactorio de 4.° de primaria en Lectura da 30,6 % en lugar
de 32,7 %. Hay un peso por área evaluada y no son intercambiables.

**Las medidas no se comparan entre grados.** Cada grado tiene su propia escala calibrada.
Entre grados solo se compara la distribución por niveles de logro.

**Los tres grados no son una cohorte.** Se evaluaron el mismo año con muestras distintas.

**5.° de secundaria no tiene diseño regional.** Sus cifras por región se pueden calcular
pero no tienen el mismo respaldo, y la aplicación lo advierte.

**Los errores estándar necesitan el diseño muestral completo**, no salen con SQL. El
módulo `muestreo.py` está validado contra el paquete `survey` de R.

**La llave geográfica es el ubigeo**, nunca el nombre: los nombres de distrito se
repiten. Y `cod_DRE`, `cod_UGEL` y `codgeo` vienen como enteros y pierden el cero
inicial.

**Mazamari y Pangoa comparten polígono** en la cartografía oficial. Para pintarlos hay
que sumar sus cifras y atribuirlas a la unidad 120699.

---

## 5. Cómo se trabaja

**Por partes, confirmando cada una.** No se reorganiza la estructura ni se adelanta
andamiaje porque vaya a hacer falta.

**Avisar antes de eliminar o mover algo que ya estaba**, y esperar respuesta. En macOS el
sistema de archivos no distingue mayúsculas: `DATA` y `data` son la misma carpeta, y un
`rm -rf` sobre una de ellas borra la otra.

**Verificar contra los datos reales** antes de dar por buena una regla de negocio o el
resultado que reporta otra parte del trabajo. Presentar los números concretos, no un
"confirmado".

**Los datos no se versionan.** Las bases de la ENLA, el PDF y la cartografía cruda quedan
fuera del repositorio; `FUENTES.md` documenta de dónde se descargan. Las capas
simplificadas sí se versionan, porque pesan 4 MB y permiten clonar y ejecutar.

**Entorno propio.** Se usa siempre `.venv/bin/python`, nunca el Python global de
anaconda, que tiene `pyproj` roto.

**Streamlit no recarga los módulos de `src/`.** Hay que reiniciar el servidor antes de
comprobar un cambio ahí, o se verifica sobre código viejo. Pasó dos veces en una sesión.

**Verificar midiendo, no mirando.** Para la interfaz, leer el DOM desde el navegador en
lugar de juzgar una captura: así se vio que un contenedor medía menos que su contenido y
que un globo de texto no tenía el estilo que parecía tener.

**Una operación, una implementación.** Cuando dos sitios resuelven lo mismo, uno de los
dos está mal y nadie lo nota. En este proyecto pasó con la recomposición de unidades
cartográficas, con el estilo de los mapas, con la separación de bloques y con el
reencuadre: las cuatro acabaron unificadas después de que la duplicada fallara.

**El repositorio guarda el producto, no el proceso.** Ni documentos de trabajo, ni notas
de seguimiento, ni rastro en los mensajes de commit de cómo se llegó hasta aquí. Lo que
sí queda es la explicación técnica de por qué algo está como está: un mensaje de commit
debe decir qué estaba mal y por qué se cambió.

**Git**: repositorio privado bajo la cuenta del autor, sin colaboradores.

---

## 6. Sobre el asistente

**No tiene que acertar, tiene que no mentir.** De ahí salen sus dos reglas:

1. Casi nunca escribe SQL. Para lo que se pregunta a menudo hay herramientas que ya
   calculan ponderando, y `consultar_sql` es el último recurso, además validado.
2. Toda cifra de una respuesta sale de una herramienta recién ejecutada, nunca de lo que
   el modelo recuerde. Cada respuesta muestra de dónde salió cada número.

**El validador analiza el árbol sintáctico**, no el texto de la consulta, y rechaza las
agregaciones sobre microdatos que no usan el peso. El riesgo no es la consulta que falla,
es la que funciona y devuelve 486,3 en lugar de 490,1 sin que nada lo delate.

**El peso va dentro de la agregación, no en cualquier parte de la consulta.** Buscarlo en
todo el árbol dejaba pasar `SELECT AVG(medida500), SUM(peso)`, que devuelve 486,3.

**Las agregaciones se le preguntan a DuckDB**, no se enumeran a mano. Por una lista
escrita a mano entraban `favg`, `fsum`, `mad`, `reservoir_quantile` y una docena más. Y
se miran las dos clases del árbol, `FUNCTION` y `WINDOW`: una agregación con OVER se
serializa como la segunda y era invisible.

**Agregar el microdato exige fijar grado y área.** El hecho trae una fila por estudiante
y área, cada una con el peso de la suya. `SUM(peso)` sin `cod_area` da 1 721 256 donde la
población de 2.° de secundaria es 573 752: el error de partición es mayor que el de
ponderación.

**Las tablas agregadas vienen ponderadas fila a fila, no entre filas.** Promediar
`pct_satisfactorio` entre departamentos da 30,4 % donde el nacional es 32,7 %.

**Una herramienta que vuelve vacía, rechazada o rota no es una fuente.** Su salida se
marca en origen y no entra en el desplegable de procedencia: listar como fuente una
consulta rechazada convierte la trazabilidad en un sello sin respaldo. Y cuando una
respuesta trae cifras sin ninguna herramienta detrás, la interfaz lo dice.

**Una herramienta no confirma lo que la vista va a deshacer.** Pedir Ciencia y Tecnología
en 4.° de primaria se rechaza con su motivo, en lugar de responder "vista actualizada"
mientras la pantalla se queda en Matemática.

**Los argumentos se validan, no se interpretan.** `orden` admite `desc` y `asc`: con
cualquier otra palabra la herramienta falla en vez de ordenar al revés en silencio. Los
nombres de unidad se buscan como texto, no como expresión regular, y el nombre exacto
gana al parcial.

**Lo que el modelo lee viene con decimales fijos.** Con el formato general, las columnas
de población salían como `5.407e+05`, y desde ahí la cifra exacta ya no se recupera.

**La clave es del visitante.** Vive solo en la sesión: no se escribe en disco, ni en el
navegador, ni en registros, y no se muestra de vuelta. La aplicación trae una clave
compartida con tope por sesión para que cualquiera pueda probarla, pero la protección
real es el límite de gasto en el panel del proveedor, no el contador de la aplicación.
