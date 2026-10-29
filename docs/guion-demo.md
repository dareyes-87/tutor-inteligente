# Guion de preguntas verificadas para la demo

Preguntas sobre lecciones que **jgarcia** (9no) y **naldana** (4to) practicaron en el seed del piloto, ejecutadas
el 2026-10-29 por el pipeline real (`POST /chat/preguntar`, DeepSeek-V4.1-Flash, BD local tras el seed) con cuentas
de prueba del mismo grado (no con las cuentas demo, para no ensuciar su historial), una conversación nueva por pregunta.
Costo aproximado: 42 llamadas al LLM, ~$0.05 (estimado; no se midió por llamada).

- **Páginas citadas**: las que el modelo menciona en el texto. **Recuperadas**: las de los fragmentos (el pie «📖 Basado en tu libro…»).
- **Citas válidas**: todas las citadas están entre las recuperadas. En esta corrida no hubo ninguna cita inválida
  (0 avisos de grounding en el log; desde el commit 242786e una cita inválida se quitaría del texto).
- ⭐ = las 3 mejores de cada grupo para la demo. Las respuestas del LLM no son deterministas: al repetir la
  pregunta en vivo el texto cambia; el contenido y las páginas suelen mantenerse.
- **No usar en la demo** las que terminan en rechazo («No encuentro información…»), salvo para mostrar a propósito
  el rechazo fuera de los libros.

## 9no Básico (cuenta demo: jgarcia) · Ciencias Naturales

| # | ⭐ | Pregunta | Lección | Citadas | Recuperadas | Válidas | Latencia | Nota |
|---|---|---|---|---|---|---|---|---|
| 1 | ⭐ | ¿Por qué tiembla en Guatemala? | L22 Magnetismo, placas y suelos | 141 | 141, 225, 288, 304, 306 | sí | 4.3 s | Primera pregunta: 4.3 s (calentamiento) |
| 2 |  | ¿Qué son las placas tectónicas? | L22 | 135, 140, 301 | 135, 136, 140, 301, 302 | sí | 1.0 s | Texto del libro confuso («capas de piedra y otros metales, 100 km de ancho») |
| 3 |  | ¿Qué es la regla de Hund? | L28 Niveles de energía | 175 | 31, 84, 115, 175, 304 | sí | 0.6 s |  |
| 4 | ⭐ | ¿Qué representa la letra s en un subnivel de energía? | L28 | 174 | 174, 207, 213, 302 | sí | 0.6 s |  |
| 5 | ⭐ | ¿Qué es el sistema endocrino? | L7 Sistema endocrino | 13, 23 | 13, 23, 48 | sí | 0.5 s |  |
| 6 |  | ¿Con qué glándula se relaciona la diabetes? | L7 | 34, 48 | 23, 34, 48 | sí | 0.5 s | Errata del modelo («Te ánimo») |
| 7 |  | ¿Cuáles son los ecosistemas de Guatemala? | L17 Ecosistemas | — | — (rechazo) | — | 0.2 s | Rechazo determinístico (contexto no relevante) |
| 8 |  | ¿Para qué sirve la cera del oído? | L2 Los sentidos | — | — (rechazo) | — | 0.3 s | Rechazo determinístico |

## 9no Básico (jgarcia) · Matemáticas

| # | ⭐ | Pregunta | Lección | Citadas | Recuperadas | Válidas | Latencia | Nota |
|---|---|---|---|---|---|---|---|---|
| 9 |  | ¿Cómo se desarrolla (x + a)(x + b)? | L1 Productos notables | 17 | 17, 37, 185, 186, 189 | sí | 1.2 s |  |
| 10 |  | ¿Cómo desarrollo (x + 5)(x + 3)? | L1 | 180, 186 | — (rechazo) | sí* | 0.4 s | *Las pp. 180/186 sí estaban entre las recuperadas, pero al ser rechazo («No encuentro…») no se muestran referencias ni pie. El LLM rechaza y a la vez ofrece otros productos notables: no usar |
| 11 | ⭐ | ¿Cómo resuelvo la ecuación x² + 6x = 0? | L10 Funciones cuadráticas | 42, 43 | 38, 42, 43, 49 | sí | 0.5 s |  |
| 12 |  | ¿Cuál es la diferencia entre círculo y circunferencia? | L18 Círculos y sólidos | 94 | 29, 94, 197 | sí | 0.9 s |  |
| 13 | ⭐ | ¿Cómo se calcula el área superficial de una esfera? | L22 Volumen y área de sólidos | 113 | 104, 111, 113 | sí | 0.8 s |  |
| 14 | ⭐ | ¿Qué es una permutación? | L30 Probabilidades | 153 | 133, 138, 153, 155, 189 | sí | 0.6 s |  |
| 15 |  | Si tengo 5 tarjetas diferentes y quiero formar números de 3 dígitos sin repetir, ¿cuántos números puedo formar? | L30 | 153 | 153, 154, 155, 164 | sí | 0.7 s | Bien, pero deja el cálculo al estudiante |
| 16 |  | ¿Cómo se resuelve la inecuación x² - 6x + 8 < 0? | L38 Inecuaciones | 193 | 35, 42, 44, 52, 193 | sí | 1.2 s | Pone la solución del ejemplo del libro («x ≤ -2 o x ≥ 1») como modelo de respuesta: confuso |

## 4to Primaria (cuenta demo: naldana) · Ciencias Naturales

| # | ⭐ | Pregunta | Lección | Citadas | Recuperadas | Válidas | Latencia | Nota |
|---|---|---|---|---|---|---|---|---|
| 17 |  | ¿Qué es la célula? | L1 La célula | 3 | 3, 4, 5, 6, 7 | sí | 0.7 s |  |
| 18 |  | ¿Qué es el ADN? | L1 | 4 | 4, 5, 6, 22 | sí | 1.1 s |  |
| 19 |  | ¿Qué hace el sistema circulatorio? | L2 El cuerpo humano | 20, 21 | 8, 20, 21, 26, 27 | sí | 0.6 s |  |
| 20 |  | ¿Para qué sirven los riñones? | L6 Nutrición y salud | 28 | 11, 17, 20, 28, 32 | sí | 0.8 s |  |
| 21 |  | ¿Qué hacen los descomponedores? | L18 Cadenas alimenticias | — | — (rechazo) | — | 0.3 s | Rechazo determinístico, aunque la lección se practicó: el umbral de relevancia no la encontró |
| 22 | ⭐ | ¿Por qué el aire tiene peso? | L21 La fuerza de la gravedad | 106 | 23, 106, 107, 154 | sí | 0.8 s |  |
| 23 | ⭐ | ¿Cuál es la diferencia entre energía renovable y no renovable? | L33 Fuentes de energía | 167, 173 | 167, 168, 169, 173, 174 | sí | 1.2 s |  |
| 24 | ⭐ | ¿Qué es un circuito eléctrico? | L37 Circuitos eléctricos | 187, 188 | 169, 187, 188, 193 | sí | 1.2 s |  |

## 4to Primaria (naldana) · Matemáticas

| # | ⭐ | Pregunta | Lección | Citadas | Recuperadas | Válidas | Latencia | Nota |
|---|---|---|---|---|---|---|---|---|
| 25 | ⭐ | ¿Por qué se dice que el sistema de numeración es posicional? | L2 Números naturales | 6 | 6, 12, 67, 68, 70 | sí | 0.7 s |  |
| 26 |  | ¿Qué es el valor posicional de una cifra? | L2 | 6 | 6, 12, 14, 40, 59 | sí | 0.9 s |  |
| 27 |  | ¿Qué es una muestra? | L4 Encuestas y estadísticas | — | — (rechazo) | — | 0.5 s | Rechazo determinístico |
| 28 |  | ¿Qué es una potencia? | L7 Números primos y compuestos | 31 | 19, 31, 73, 77, 78 | sí | 1.0 s |  |
| 29 |  | ¿Cómo se lee 4³? | L7 | — | — (rechazo) | — | 0.4 s | Rechazo determinístico |
| 30 |  | ¿Qué es un número primo? | L8 Búsqueda del tesoro | 35 | 7, 35, 36, 38 | sí | 0.9 s |  |
| 31 | ⭐ | ¿Cómo descompongo el 120 en factores primos? | L8 | 36, 37 | 33, 36, 37, 52 | sí | 0.8 s |  |
| 32 | ⭐ | ¿Cómo se ordenan 2.36, 2.06, 2.03, 2.3 y 2.6 de menor a mayor? | L14 Multiplicación con decimales | 66 | 8, 34, 35, 38, 66 | sí | 4.5 s | 4.5 s |

## Respuestas completas

### 1. ⭐ ¿Por qué tiembla en Guatemala?  (9no, Ciencias)

> ¡Excelente pregunta! En tu libro encontramos información sobre esto.
>
> Guatemala es un caso atípico en cuanto a **placas tectónicas**, porque en su territorio **convergen tres de ellas** (página 141). Una de las que se menciona es la **Placa de Cocos**, que está debajo del Océano Pacífico (página 141).
>
> Además, el libro menciona que una **falla** es una fractura de la corteza terrestre a través de la cual el suelo experimenta movimiento (página 141).
>
> Eso es lo que tu libro explica sobre las placas tectónicas en Guatemala. Si quieres, podemos seguir repasando este tema de la Sesión 6 de la Unidad 6. ¿Te gustaría profundizar en algo más de lo que aparece en tu libro?
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 141, 225, 288, 304, 306.

### 2. ¿Qué son las placas tectónicas?  (9no, Ciencias)

> ¡Excelente pregunta! Vamos a ver qué dice tu libro sobre este tema.
>
> Según tu libro, las **placas tectónicas** de Guatemala son las **capas sólidas de piedra y de otros metales** que pasan por debajo del territorio guatemalteco, y su grosor es de aproximadamente **100 kilómetros de ancho** (página 140).
>
> También tu libro menciona que existen movimientos entre placas, como la **separación de placas** y el **choque de placas** (página 135). Por ejemplo, en el Atlántico se da una separación entre la placa Euroasiática y la Norteamericana, y en el Pacífico hay un choque entre la placa Nazca y la Sudamericana (página 135).
>
> Además, el libro menciona algunas placas por nombre, como la **Placa Africana**, la **Placa de Scotia**, la **Placa del Caribe** y la **Placa Sudamericana** (página 301).
>
> Es un tema muy interesante porque nos ayuda a entender por qué tiembla en nuestro país. ¿Quieres que sigamos explorando este tema?
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 135-136, 140, 301-302.

### 3. ¿Qué es la regla de Hund?  (9no, Ciencias)

> La **regla de Hund** se utiliza para el llenado de orbitales que posean igual energía (página 175).
>
> Fue propuesta por el físico alemán **Friedrich Hund**, y se basa en el llenado de **orbitales atómicos que tengan igual energía** (página 175).
>
> Fijate que en tu libro, junto a esta regla, aparece un ejemplo con los orbitales **s, px, py, pz** y los elementos **H, C, N** (página 175). Te recomiendo observar esa parte del texto y los diagramas para comprender mejor cómo se aplica el llenado.
>
> ¿Quieres que sigamos repasando este tema?
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 31, 84, 115, 175, 304.

### 4. ⭐ ¿Qué representa la letra s en un subnivel de energía?  (9no, Ciencias)

> La letra **s** representa el **subnivel de energía** que ocupa el electrón en ese átomo (página 174).
>
> Cuando escribimos la configuración electrónica de un átomo, por ejemplo **1s¹**, cada símbolo tiene un significado:
>
> 1. El primer número (**1**) representa el **nivel de energía** ocupado por el electrón.
> 2. La letra (**s**) representa el **subnivel de energía** ocupado por el electrón.
> 3. El número pequeño al final (**1**) representa la **cantidad de electrones** presentes en ese orbital y en ese nivel (página 174).
>
> Así que la **s** nos dice en qué subnivel se encuentra el electrón dentro de ese nivel de energía. ¡Muy bien por preguntar estos detalles, así se entiende mejor la configuración electrónica!
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 174, 207, 213, 302.

### 5. ⭐ ¿Qué es el sistema endocrino?  (9no, Ciencias)

> El **sistema endocrino** está formado por una serie de **glándulas** que segregan unas sustancias llamadas **hormonas**, que se incorporan directamente al torrente sanguíneo y actúan sobre órganos específicos (página 23).
>
> Las glándulas endocrinas más importantes producen hormonas, por ejemplo, la **hormona del crecimiento**, que estimula el crecimiento de los huesos y todos los tejidos del cuerpo (página 23).
>
> Además, el sistema endocrino trabaja junto con el **sistema nervioso** para coordinar las actividades del organismo. El sistema nervioso lo hace utilizando impulsos eléctricos y señales químicas, y el endocrino utiliza las hormonas, que son de secreción interna directa a la sangre, como la hormona del crecimiento o la hormona que reduce el azúcar en la sangre (página 13).
>
> ¡Muy buena pregunta! Sigue así, vas por buen camino.
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 13, 23, 48.

### 6. ¿Con qué glándula se relaciona la diabetes?  (9no, Ciencias)

> La **diabetes** se relaciona con los **Islotes de Langerhans** en el **páncreas** (página 48).
>
> En tu libro, la tabla de la página 48 te pide marcar con una X la relación de cada enfermedad con su glándula. Si revisas la lista de glándulas principales del sistema endocrino, ahí aparecen los **Islotes de Langerhans en el páncreas** (página 48).
>
> Además, en la página 34 se menciona que el **páncreas** produce **insulina**, que baja el nivel de azúcar en la sangre, y otra hormona que eleva el nivel de azúcar cuando el cuerpo necesita energía.
>
> Te ánimo a que completes tu cuadro con calma. ¡Vas muy bien!
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 23, 34, 48.

### 7. ¿Cuáles son los ecosistemas de Guatemala?  (9no, Ciencias)

> No encuentro información sobre eso en tus libros. ¿Quieres preguntarme sobre los temas que estamos viendo en clase?

### 8. ¿Para qué sirve la cera del oído?  (9no, Ciencias)

> No encuentro información sobre eso en tus libros. ¿Quieres preguntarme sobre los temas que estamos viendo en clase?

### 9. ¿Cómo se desarrolla (x + a)(x + b)?  (9no, Matemáticas)

> ¡Excelente pregunta! Ese producto notable sí aparece en tu libro.
>
> En la **página 17** se indica que una expresión de la forma **(x + a)(x + b)** puede desarrollarse así:
>
> **(x + a)(x + b) = x² + (a + b)x + ab**
>
> Fijate en la estructura del resultado:
> 1. **x²**: es el producto de los primeros términos (x · x).
> 2. **(a + b)x**: se suman los dos segundos términos y se multiplica por x.
> 3. **ab**: es el producto de los dos segundos términos.
>
> Un detalle importante: en el libro, el coeficiente de x se escribe como **(a + b)**, es decir, primero se suman a y b, y ese resultado multiplica a la x.
>
> Ahora te propongo practicar: si tuvieras **(x + 3)(x + 5)**, ¿cuánto valdría **a** y cuánto valdría **b**? Escribí esos valores y luego intentá reemplazarlos en la fórmula. ¡Vos podés!
>
> 📖 Basado en tu libro de Matemáticas, páginas 17, 37, 185-186, 189.

### 10. ¿Cómo desarrollo (x + 5)(x + 3)?  (9no, Matemáticas)

> No encuentro información sobre eso en tus libros de clase. ¿Quieres preguntarme sobre los temas que estamos viendo en clase?
>
> Lo que sí aparece en tu libro son productos como **el cubo de un binomio** (x + a)³ = x³ + 3ax² + 3a²x + a³ (página 180) y **la suma y diferencia de cubos**, por ejemplo (x + a)(x² − ax + a²) = x³ + a³ (página 186). Si quieres, podemos practicar con uno de esos.

### 11. ⭐ ¿Cómo resuelvo la ecuación x² + 6x = 0?  (9no, Matemáticas)

> ¡Excelente pregunta! Vamos a resolverla paso a paso, como lo indica tu libro (páginas 42 y 43).
>
> Para resolver una ecuación de la forma **x² + bx = 0**:
>
> 1. **Factoriza** extrayendo el factor común:
>    x² + 6x = 0  →  **x(x + 6) = 0**
>
> 2. **Aplica la propiedad**: si A × B = 0, entonces A = 0 o B = 0.
>    Entonces: **x = 0** o **x + 6 = 0**
>
> 3. **Resuelve la ecuación de primer grado** (la segunda parte):
>    x + 6 = 0
>    x = 0 − 6
>    x = **−6**
>
> Respuesta: **x = 0 o −6**
>
> Ahora te toca a ti. Intenta resolver **x² − 6x = 0** (ejercicio c de la página 42):
>
> ¿Cuál sería el factor común que extraes en el primer paso? Escríbeme lo que obtienes y lo revisamos juntos. ¡Vas muy bien!
>
> 📖 Basado en tu libro de Matemáticas, páginas 38, 42-43, 49.

### 12. ¿Cuál es la diferencia entre círculo y circunferencia?  (9no, Matemáticas)

> ¡Buena pregunta! Vamos a revisar lo que dice tu libro.
>
> En la página 94, tu libro presenta los principales elementos de un **círculo** y, al mismo tiempo, menciona la **circunferencia**. Fíjate en la imagen de esa página: aparece el punto **O** (el centro) y la línea curva que lo rodea.
>
> De acuerdo con lo que muestra el libro:
> - La **circunferencia** es la figura que se forma al conectar los puntos que están a la misma distancia de un punto fijo O (página 94). Es decir, es la línea curva.
> - El punto **O** se llama **centro de la circunferencia** (página 94).
>
> Ahora, un detalle importante: en tu libro, cuando se habla del **círculo**, se dice que sus **principales elementos** incluyen el arco, la cuerda, el ángulo central, el sector circular y el segmento circular (página 94). Varios de estos elementos se describen como partes de la **superficie** del círculo (por ejemplo, el sector circular y el segmento circular).
>
> Entonces, según lo que trae tu libro: la circunferencia es la línea curva, y el círculo es la figura que contiene esa línea junto con su superficie y sus elementos.
>
> ¿Puedes decirme, con tus palabras, cuál de los dos es solo la línea y cuál incluye la superficie?
>
> 📖 Basado en tu libro de Matemáticas, páginas 29, 94, 197.

### 13. ⭐ ¿Cómo se calcula el área superficial de una esfera?  (9no, Matemáticas)

> ¡Excelente pregunta! Vamos a verlo con lo que dice tu libro.
>
> Según tu libro (página 113), el **área superficial de una esfera** es igual al área de la cara lateral del cilindro en donde cabe completamente esa esfera.
>
> El procedimiento que muestra el libro es este:
>
> 1. Imagina el cilindro que contiene la esfera. Su cara lateral forma un rectángulo con **base 2πr** y **altura 2r**.
> 2. Entonces, el área de esa cara lateral es: **(2πr × 2r)**.
> 3. Al multiplicar, queda: **4πr²**.
>
> Por eso, la **fórmula** que usa el libro es:
>
> **Área superficial de la esfera = 4πr²**
>
> En el ejemplo del libro (página 113), con radio r = 3 cm:
> Área = 4 × π × 3² = 36π, y el área superficial es **36π cm²**.
>
> Ahora te toca a ti: si tuvieras una esfera con radio de 5 cm, ¿qué valor usarías en lugar de la r en la fórmula **4πr²**? Intenta plantearlo y me cuentas.
>
> 📖 Basado en tu libro de Matemáticas, páginas 104, 111, 113.

### 14. ⭐ ¿Qué es una permutación?  (9no, Matemáticas)

> ¡Excelente pregunta! Vamos a verlo con lo que dice tu libro.
>
> Una **permutación** es un arreglo de objetos para el cual **importa el orden** de los objetos (página 153).
>
> Además, tu libro te da la expresión para calcular el número total de permutaciones de **r** objetos a partir de **n** objetos diferentes, que se denota como **P** (página 153):
>
> P = n (n - 1)(n - 2) … (n - r + 1)
>
> donde se multiplican **r factores**.
>
> Fíjate en la idea clave: en una permutación el orden sí cambia el arreglo. Por ejemplo, si tienes los objetos A y B, el arreglo AB no es lo mismo que BA.
>
> ¿Quieres que veamos juntos cómo se aplica esa expresión en un ejercicio? Escríbeme los valores de **n** y de **r** y lo resolvemos paso a paso.
>
> 📖 Basado en tu libro de Matemáticas, páginas 133, 138, 153, 155, 189.

### 15. Si tengo 5 tarjetas diferentes y quiero formar números de 3 dígitos sin repetir, ¿cuántos números puedo formar?  (9no, Matemáticas)

> ¡Excelente pregunta! Vamos a resolverlo paso a paso usando lo que dice tu libro.
>
> El libro explica que para una **permutación** se usa la expresión (página 153):
>
> **P = n (n − 1)(n − 2) … (n − r + 1)**, con **r factores**.
>
> Aquí identificamos:
> - **n** = cantidad total de tarjetas = 5
> - **r** = cantidad de dígitos que quieres formar = 3
>
> Entonces debes multiplicar **3 factores** empezando desde 5 (página 153):
>
> **P = 5 × 4 × 3**
>
> Ahora te toca a ti: ¿cuánto da esa multiplicación? Intenta resolverla y me dices tu resultado para verificarlo juntos.
>
> 📖 Basado en tu libro de Matemáticas, páginas 153-155, 164.

### 16. ¿Cómo se resuelve la inecuación x² - 6x + 8 < 0?  (9no, Matemáticas)

> ¡Excelente pregunta! Vamos a resolverla paso a paso, siguiendo el procedimiento que aparece en tu libro (página 193).
>
> Observa que tu inecuación es **x² - 6x + 8 < 0**, muy parecida a la del ejemplo del libro (página 193), donde se resuelve x² + x - 2 ≥ 0.
>
> 1. **Factoriza** el lado izquierdo. Busca dos números que multiplicados den 8 y sumados den -6. ¿Cuáles crees que son?
>
> 2. Una vez factorizada, **iguala cada factor a cero** para encontrar los valores donde la expresión cambia de signo. Esos son los puntos que dividen la recta numérica en intervalos.
>
> 3. **Analiza los intervalos**: el libro (página 193) revisa en qué intervalo la expresión cumple la condición. En tu caso, como el signo es **< 0**, buscas dónde la expresión es **negativa**.
>
> 4. **Escribe la solución** como un intervalo o con desigualdades, igual que en el ejemplo: "x ≤ -2 o x ≥ 1" (página 193).
>
> Empieza con el paso 1: ¿qué dos números multiplican 8 y suman -6? Inténtalo y me dices tu resultado. 💪
>
> 📖 Basado en tu libro de Matemáticas, páginas 35, 42, 44, 52, 193.

### 17. ¿Qué es la célula?  (4to, Ciencias)

> ¡Hola! Qué buena pregunta. 😊
>
> La **célula** es la unidad más pequeña de los seres vivos (página 3). Se dice que es la base de la estructura de la vida porque, en conjunto, forma los organismos (página 3).
>
> Además, una célula puede considerarse como un organismo vivo porque es capaz de **nutrirse**, **relacionarse** y **reproducirse** (página 3).
>
> En la naturaleza hay seres formados por una sola célula: los **protozoos** y las **bacterias**. Todos los demás seres vivos son celulares, entre ellos el ser humano (página 3).
>
> ¿Te gustaría saber cómo funcionan las células? ¡Sigue preguntando! 🌿
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 3-7.

### 18. ¿Qué es el ADN?  (4to, Ciencias)

> ¡Excelente pregunta! El **ADN** es la información genética que está dentro de la célula (página 4).
>
> En el ADN está la **herencia**, que permite que las características se transmitan de generación en generación. Por eso todos los miembros de una especie se parecen entre sí (página 4).
>
> También el libro explica que los organismos no son siempre iguales: evolucionan, cambian poco a poco, y esos cambios también se heredan a los hijos (página 4).
>
> Además, existe la **mutación**, que es un cambio genético brusco que sucede en algún organismo, y lo increíble es que las mutaciones también se pueden heredar (página 4).
>
> ¡Sigue así, vas muy bien! ¿Quieres que hablemos de la célula?
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 4-6, 22.

### 19. ¿Qué hace el sistema circulatorio?  (4to, Ciencias)

> ¡Excelente pregunta! El **sistema circulatorio** hace que la sangre se mueva por todo el cuerpo. Gracias a él, la sangre lleva los **nutrientes** y el **oxígeno** a todas las células del cuerpo. Además, **defiende al cuerpo de infecciones** y **recoge los desechos** (página 20).
>
> También está formado por el **corazón**, las **arterias**, las **venas**, los **vasos capilares** y la **sangre** (página 21).
>
> ¿Te gustaría que hablemos de alguna de sus partes?
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 8, 20-21, 26-27.

### 20. ¿Para qué sirven los riñones?  (4to, Ciencias)

> ¡Muy bien! Los **riñones** son parte del aparato urinario y sirven para:
>
> 1. **Filtrar la sangre**: cuando la sangre pasa por ellos, dejan allí las sustancias que el cuerpo ya no va a utilizar (página 28).
> 2. **Regular la presión sanguínea** (página 28).
>
> Son dos, están a los lados de la columna vertebral, a nivel de la espalda baja, y son una especie de **filtros** (página 28).
>
> Además, el aparato urinario expulsa del cuerpo todo lo que ya no se va a utilizar, y lo hace por medio de la **orina** (página 28). ¡Sigue así, vas muy bien!
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 11, 17, 20, 28, 32.

### 21. ¿Qué hacen los descomponedores?  (4to, Ciencias)

> No encuentro información sobre eso en tus libros. ¿Quieres preguntarme sobre los temas que estamos viendo en clase?

### 22. ⭐ ¿Por qué el aire tiene peso?  (4to, Ciencias)

> ¡Qué buena pregunta! El aire sí tiene peso.
>
> Todas las partículas tienen peso, y el espacio también está compuesto de partículas, aunque sean tan pequeñas que no puedas verlas. Por eso, el aire tiene peso. Y ese peso es lo que se conoce como **presión atmosférica** (página 106).
>
> Tu cuerpo está tan acostumbrado a recibir esa presión invisible durante cada minuto de tu vida, que no te das cuenta de la fuerza y el peso que ejerce (página 106).
>
> ¿Y por qué tanto peso no te aplasta? Porque en tu interior existen muchos espacios que contienen aire. Es ese aire el responsable de contrarrestar el peso exterior y evitar que te comprima demasiado (página 106).
>
> ¡Sigue preguntando, vas muy bien!
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 23, 106-107, 154.

### 23. ⭐ ¿Cuál es la diferencia entre energía renovable y no renovable?  (4to, Ciencias)

> ¡Excelente pregunta! Vamos a verlo con lo que dice tu libro.
>
> Las **fuentes de energía** se conocen como **renovable** o **no renovable** según sus características (página 167).
>
> **Energía renovable:** son recursos naturales que **no se agotan** o que tienen un **ciclo que permite su regeneración**. Ejemplos: la **luz del Sol**, el **viento** y el **agua** (página 167).
>
> **Energía no renovable:** se extrae de recursos que **sí se agotan** a medida que se usan, o que **no pueden reponerse** a la misma velocidad con que son explotados. Existe en cantidades **limitadas** y algún día se acabará. Ejemplos: el **petróleo**, el **carbón mineral** y el **gas natural** (página 167).
>
> Puedes pensarlo así: el Sol sale todos los días, como los árboles que vuelven a crecer. En cambio, el petróleo es como el agua de un tinaco: si la usas mucho, se acaba.
>
> ¿Te gustaría saber cómo se usa la energía en Guatemala? (página 173)
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 167-169, 173-174.

### 24. ⭐ ¿Qué es un circuito eléctrico?  (4to, Ciencias)

> ¡Excelente pregunta! Te la contesto con gusto.
>
> Un **circuito eléctrico** es un **conjunto de componentes que permiten el paso de energía** (página 187).
>
> Además, tu libro explica que los circuitos eléctricos simples pueden ser de dos tipos (página 188):
>
> 1. **Abiertos:** no dejan que la electricidad pase.
> 2. **Cerrados:** sí dejan pasar la electricidad, porque todos sus componentes están unidos. Así la corriente sigue su camino desde el generador hasta el receptor, y de regreso al generador.
>
> Las partes básicas de un circuito simple son (página 188):
>
> 1. **Generador:** puede ser una batería o el tomacorriente de la casa.
> 2. **Receptor de la corriente:** absorbe la electricidad y la transforma, por ejemplo en luz, movimiento o sonido.
> 3. **Controlador o interruptor:** permite cortar o dejar pasar la corriente.
> 4. **Conductor:** transporta la energía desde la fuente hasta cada receptor.
>
> ¿Quieres que te explique cómo viaja la energía dentro del circuito?
>
> 📖 Basado en tu libro de Ciencias Naturales, páginas 169, 187-188, 193.

### 25. ⭐ ¿Por qué se dice que el sistema de numeración es posicional?  (4to, Matemáticas)

> ¡Muy buena pregunta! Vamos a verlo con calma.
>
> Según tu libro, nuestro sistema de numeración se llama **decimal** porque cada valor posicional equivale a **10 unidades** del valor inmediatamente menor (página 6).
>
> También se considera un sistema de numeración **posicional** porque **el valor de cada cifra depende de la posición en la que se encuentra** (página 6).
>
> Por ejemplo, en el número 5 746 252, la cifra 5 vale como **5Um** (unidades de millón) porque está en esa posición (página 6).
>
> Entonces, la misma cifra puede valer cosas distintas según dónde esté colocada.
>
> ¿Te animas a decirme cuánto vale la cifra 7 en el número 5 746 252?
>
> 📖 Basado en tu libro de Matemáticas, páginas 6, 12, 67-68, 70.

### 26. ¿Qué es el valor posicional de una cifra?  (4to, Matemáticas)

> ¡Hola! Qué buena pregunta. Vamos a verlo con calma.
>
> El **valor posicional** es el valor que tiene cada cifra según el lugar donde se encuentra dentro del número (página 6).
>
> Tu libro explica dos cosas importantes de nuestro sistema de numeración (página 6):
>
> 1. Se llama **decimal** porque cada valor posicional equivale a **10 unidades** del inmediatamente menor.
> 2. Se llama **posicional** porque el valor de cada cifra **depende de la posición** en la que se encuentra.
>
> Por ejemplo, en el número **5 746 252** se descompone según la posición de sus cifras (página 6):
>
> **5 746 252 = 5Um + 7CM + 4DM + 6UM + 2C + 5D + 2U**
>
> Fijate que el **5** que está al inicio vale **5 unidades de millón**, pero el **5** que está más adelante vale solo **5 decenas**. ¡La misma cifra vale distinto según su posición!
>
> ¿Te animás a decirme cuánto vale la cifra **7** en ese número?
>
> 📖 Basado en tu libro de Matemáticas, páginas 6, 12, 14, 40, 59.

### 27. ¿Qué es una muestra?  (4to, Matemáticas)

> No encuentro información sobre eso en tus libros. ¿Quieres preguntarme sobre los temas que estamos viendo en clase?

### 28. ¿Qué es una potencia?  (4to, Matemáticas)

> ¡Hola! Qué buena pregunta. Vamos a verlo juntos.
>
> Una **potencia** es el resultado de la **potenciación**. En la potenciación, la **base** se repite como **factor** varias veces, y el **exponente** te dice cuántas veces se repite (página 31).
>
> Las partes de una potencia son:
>
> 1. **Base**: el número que se repite.
> 2. **Exponente**: indica cuántas veces se repite la base como factor.
> 3. **Potencia**: el resultado.
>
> Por ejemplo, en tu libro aparece:
>
> 4 × 4 = 4² = 16
>
> Se lee: **cuatro al cuadrado** (página 31).
>
> Ahí la base es 4, el exponente es 2 y la potencia es 16.
>
> Un dato importante del libro: si la **base es 1**, la potencia **siempre será 1**. Por ejemplo: 1 × 1 = 1² = 1 (página 31).
>
> ¿Quieres intentar tú? ¿Cuál sería la base y el exponente en 2³?
>
> 📖 Basado en tu libro de Matemáticas, páginas 19, 31, 73, 77-78.

### 29. ¿Cómo se lee 4³?  (4to, Matemáticas)

> No encuentro información sobre eso en tus libros. ¿Quieres preguntarme sobre los temas que estamos viendo en clase?

### 30. ¿Qué es un número primo?  (4to, Matemáticas)

> ¡Excelente pregunta! Vamos a verlo con lo que dice tu libro.
>
> Un **número primo** es aquel que **solo tiene dos divisores** (página 35).
>
> En tu libro aparece un ejemplo claro (página 35):
>
> - El **23** solo tiene dos divisores, por eso es **primo**.
> - El **31** solo tiene dos divisores, por eso es **primo**.
>
> Y también te dice que el **único número primo par es el 2** (página 35).
>
> Ahora te toca a ti: si el **9** tiene más de dos divisores, ¿será primo o compuesto? ¡Cuéntame qué piensas!
>
> 📖 Basado en tu libro de Matemáticas, páginas 7, 35-36, 38.

### 31. ⭐ ¿Cómo descompongo el 120 en factores primos?  (4to, Matemáticas)

> ¡Hola! Qué bueno que quieras practicar la descomposición en factores primos. Vamos paso a paso, como lo explica tu libro (páginas 36 y 37).
>
> 1. Como 120 es par, lo divides entre 2: 120 ÷ 2 = 60. Escribes 60 debajo.
> 2. 60 también es par, divides entre 2: 60 ÷ 2 = 30.
> 3. 30 es par, divides entre 2: 30 ÷ 2 = 15.
> 4. 15 ya no es par, pero es divisible entre 3: 15 ÷ 3 = 5.
> 5. 5 es primo, lo divides entre él mismo: 5 ÷ 5 = 1. La descomposición termina cuando llegas a 1 (página 36).
>
> Ahora multiplica los números que quedaron a la derecha de la línea. ¿Puedes escribir esa multiplicación tú mismo y decirme cuánto te da?
>
> 📖 Basado en tu libro de Matemáticas, páginas 33, 36-37, 52.

### 32. ⭐ ¿Cómo se ordenan 2.36, 2.06, 2.03, 2.3 y 2.6 de menor a mayor?  (4to, Matemáticas)

> ¡Hola! Vamos a ordenarlos paso a paso. 😊
>
> El libro nos enseña que, cuando los números decimales tienen diferente cantidad de cifras, completamos con ceros para compararlos mejor (página 66). Fíjate que todos empiezan con 2, así que comparamos la parte decimal:
>
> 1. Escribe todos con la misma cantidad de cifras decimales:
> - 2.36 → 2.36
> - 2.06 → 2.06
> - 2.03 → 2.03
> - 2.3 → 2.30
> - 2.6 → 2.60
>
> 2. Ahora compara solo los decimales: 03, 06, 30, 36 y 60.
>
> 3. Ordena de menor a mayor esos decimales: 03 < 06 < 30 < 36 < 60.
>
> Entonces el orden queda así: **2.03, 2.06, 2.3, 2.36, 2.6**.
>
> El libro también menciona que podemos apoyarnos en la recta numérica: se ubican las cantidades de menor a mayor (página 66). ¿Te animas a ubicarlos tú en una recta numérica?
>
> 📖 Basado en tu libro de Matemáticas, páginas 8, 34-35, 38, 66.
