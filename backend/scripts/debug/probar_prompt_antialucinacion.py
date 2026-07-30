"""
Prueba antes/después del prompt anti-alucinación (Prioridad 2, fix/pre-piloto).
Reproduce los 3 casos reales detectados en producción usando el texto EXACTO
de las páginas del libro (extraído vía /chat/debug/fragmentos/3 en prod, solo
lectura, sin re-indexar nada). Compara el prompt viejo (git show HEAD) vs el
nuevo (app/modules/chat/prompts.py actual) llamando directo a Together AI,
sin pasar por RAG/Modal — aísla el efecto del prompt.

Uso (dentro del contenedor backend): python3 scripts/debug/probar_prompt_antialucinacion.py
"""
import sys

sys.path.insert(0, "/app")

from app.llm.client import llm_client  # noqa: E402
from app.modules.chat.prompts import build_system_prompt  # noqa: E402

# --- Contenido real de producción (libro_id=3, Ciencias Naturales 6to) ---
PAGINA_83 = """--- Página 83 ---
o
¿Te recuerdas de la dermis en el cuerpo humano? Ahora lo vere-
mos en las plantas.
Este tejido vegetal, al que en los animales, proporciona protec-
ción al cuerpo de las plantas (tallos, hojas y raíces), regula la respi-
ración vegetal y reconoce organismos que producen enfermedades.
Tiene epidermis y peridermis.
e Epidermis. Este tejido cubre la planta en las primeras etapas
de su crecimiento.

íz durante el crecimiento secundario y sustituye a la.
epidermis. Es el que permite la transformación de un tallo
Suave a corteza.
epidermis superior
e inferior

nutrientes producidos gracias a la fotosíntesis y que importante en este
forman la savia elaborada. Dichos nutrientes son transportados por contexto.
el floema desde el lugar donde se produce (hojas y tallos verdes), E
hasta todas las partes de la planta, principalmente raíces y tallo.
Uno de los Objetivos
de Desarrollo
Sostenible está
relacionado con
"Hambre cero". Una
parte de este objeti-
vo.in

¿Cuáles son los sistemas de las plantas?
Sistema vascular
Similar al cuerpo humano, las plantas tienen sistemas y células
especializadas en realizar diferentes funciones. Veremos dos de estos
Sistema vascular
Este sistema tiene como función transportar el agua, minerales y
nutrientes de la planta. Para realizar este trabajo, los tejidos del siste-
ma tienen forma cilíndrica, tal como las venas y l
"""

PAGINA_161 = """--- Página 161 ---
161
Las nubes
¿De qué están nubes? ¿Sabías que cada nube está formada por agua que hay en la atmós-
fera? Las nubes se forman a partir del enfriamiento del vapor de aire. Están compuestas de pequeñas
gotitas de agua. Esas gotas son tan livianas que las corrientes de aire las mantienen suspendidas en
el cielo. Cuando la temperatura del aire es fría, las nubes estarán formadas por pequeñitos crista-
les de hielo. Las que se forman en climas más cálidos están formadas por pequeñas gotas de
agua en estado líquido.
Las nubes están clasificadas en tres tipos:
Nubes
altas medias bajas
cirros cirrocúmulos cirrostratos altocúmulos altostratos 'nimbostratos estratocúmulos estratos
| |
Blancas y
transparentes. Forma de
Filamentos copos de Apariencia de Nubes Bancos de
finos algodón. Indi- lo. denubes. de color gris neblina. Pre-
lor gris. ian buen
delgados. ' con sombras. Anuncian sagian
Avisan temperatura frente y frío. gian
descenso de lluvias.
temperatura.
CIrros
cirrostratos
"""

PAGINA_SISTEMA_EXCRETOR = """--- Página 36 ---
ncarga de
sistema circulatorio quien, a
recoger los desechos de las células: sa
do de carbono y urea. Todos
os por el sistema ex
el oxígeno a las de
las células para que puedan producir energía con
la glucosa que viene de los nutrientes.
¿Te gustaría conocer más acerca de cómo.
trabaja el sistema excretor para sacar todos esos
desechos de tu cuerpo?
Ahora descubre lo que hace cada una de las
partes del sistema excretor:
En tu cuerpo tienes dos riñones,
Uno a cada lado de la columna
vertebral, cerca de la cintura. Los
| riñones son los encargados de
| filtrar la Sangre que viene de todo
el cuerpo. Al filtrarla los
hutrientes que todavía se pueden A
utilizar y los desechos que se
deben eliminar Por la orina.

--- Página 36 (continuación) ---
humano
Digestivo. Circulatorio.
ransforma Transporta
los alimentos oxígeno,
nutrientes y
sustancias
de desecho,
Excretor.
Obtiene Elimina
oxígeno sustancias
y expulsa de desecho,
dióxido de producto de
carbono la actividad
celular,
Para comenzar, debes conocer las partes
principales de este sistema. Observa la siguien-
te imagen para que las ubiques.
Partes del sistema urina
arteria
renal
riñon
vena Cava
arteria
Inferior
aorta
— Uréter
vejiga —
urinaria
Uretra
toda
Amigos inseparables
El sistema excretor

--- Página 37 ---
¿Se debe cuidar el sistema excretor?
Consejos para cuidar tu sistema
¿Notas la importancia de cada órgano del sistema excretor? Con
uno que falle...¡todo tu organismo se
Es muy importante que cuides
tu sistema excretor o urinario. Aplica los consejos que se indican a
continuación.
e Esimportante que orines cuando tengas deseos. Orinar cada tres
o cuatro horas evita infecciones a nivel de la vejiga.
e Definitivamente debes consumir de cinco a ocho vasos de agua
al día.
e Las medidas de higiene son muy importantes para evitar enferme-
dades a nivel de genitales externos, uretra y vejiga urinaria.
"""

CASOS = [
    ("A — página 83 (sistemas de la planta)", PAGINA_83, "Explícame la página 83"),
    ("B — página 161 (las nubes)", PAGINA_161, "¿Qué tipos de nubes hay y qué significan?"),
    ("C — sistema excretor", PAGINA_SISTEMA_EXCRETOR, "Explícame las partes del sistema excretor y urinario"),
]

GRADO = "6to Primaria"
ASIGNATURA = "Ciencias Naturales"


def probar() -> None:
    for nombre_caso, pagina_texto, pregunta in CASOS:
        system_prompt = build_system_prompt(GRADO, ASIGNATURA)
        context = f"CONTENIDO DEL LIBRO (usa SOLO esta información para responder):\n\n{pagina_texto}"
        messages = [
            {"role": "system", "content": f"{system_prompt}\n\n{context}"},
            {"role": "user", "content": f"{pregunta}\n\n[Recuerda: responde únicamente en español]"},
        ]
        respuesta = llm_client.chat(messages, max_tokens=400, temperature=0.7)
        print(f"\n--- Caso {nombre_caso} ---")
        print(f"Pregunta: {pregunta}")
        print(f"Respuesta:\n{respuesta}\n")


if __name__ == "__main__":
    probar()
