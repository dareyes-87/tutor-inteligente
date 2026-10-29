# Prueba de la app móvil en Expo Go (cuenta jgarcia, backend local)

## 0. Antes de empezar

1. **Expo Go para SDK 56 no está en Play Store** (la app usa `expo ~56.0.12`). Si el teléfono ya tiene
   Expo Go de Play Store, ábrela → *Settings* y mira "Supported SDK": si no dice 56, desinstálala e instala
   a mano **Expo Go 56.0.4** desde <https://expo.dev/go> (Android → dispositivo), APK directo:
   `https://github.com/expo/expo-go-releases/releases/download/Expo-Go-56.0.4/Expo-Go-56.0.4.apk`
   (permitir "instalar apps desconocidas" para el navegador). No uses la 56.0.1: rechaza los proyectos SDK 56.
2. Teléfono y laptop en la **misma red Wi-Fi**. La IP del laptop en el Wi-Fi (interfaz `wlp2s0`) era
   `192.168.31.50` el 2026-10-29; puede cambiar, por eso el comando la calcula.
3. Backend local levantado (`docker compose up -d`) y `curl http://localhost:8000/health` → `ok`.
4. La sesión dura lo que diga `ACCESS_TOKEN_EXPIRE_MINUTES` del `.env` local (hoy **60**). Para no ser
   expulsado a mitad de la prueba, cámbialo a `720` y `docker compose restart backend`.
5. Contraseña de jgarcia: en `datos/estudiantes/9no Basico/` (credenciales; no está en el repo).

### Puertos (firewalld)

La zona activa `FedoraWorkstation` ya permite 1025–65535/tcp, así que 8000 (backend) y 8081 (Metro)
suelen estar abiertos. Si la zona fuera otra o los cerraste:

```bash
sudo firewall-cmd --add-port=8000/tcp --add-port=8081/tcp          # abrir (solo hasta reiniciar firewalld)
sudo firewall-cmd --remove-port=8000/tcp --remove-port=8081/tcp    # cerrar al terminar
firewall-cmd --list-ports                                          # comprobar
```

(Sin `--permanent` el cambio se pierde al reiniciar firewalld o el equipo, que es lo que se quiere.)

### Arrancar

```bash
cd mobile
IP=$(ip -4 -o addr show wlp2s0 | awk '{print $4}' | cut -d/ -f1)
EXPO_PUBLIC_API_URL=http://$IP:8000 npx expo start --lan --clear
```

`--clear` evita que Metro reutilice un bundle con otra URL (la variable se incrusta al empaquetar).
Escanear el QR con Expo Go. Comprobar desde el navegador del teléfono: `http://<IP>:8000/health`.

## 1. Recorrido (marcar cada punto)

- [ ] **Login** con jgarcia → entra al Inicio.
- [ ] **Cerrar y reabrir**: cerrar Expo Go por completo (multitarea → deslizar) y volver a abrir el proyecto → sigue la sesión, sin pasar por el login.
- [ ] **Inicio**: racha **0 días** con "Practica hoy para empezar una nueva racha" y **🏆 Mejor racha: 3**; asignaturas con "% dominio" (Matemáticas ~86 %, Ciencias ~73 %) y "0 de N lecciones completadas".
- [ ] **Mi Ruta**: se ve la ruta; el selector cambia entre Ciencias Naturales y Matemáticas.
- [ ] **Estudiar** una lección disponible → tarjetas de la micro-lección (y lectura en voz alta).
- [ ] **Practicar** → se generan **5 actividades** del nivel.
- [ ] **Retroalimentación**: tras responder, el panel incluye "📖 Esto está en tu libro de … página(s) X" (acierto) o "Repasa tu libro…" (error).
- [ ] **Mi progreso**: bloques **por asignatura**, cada uno con su "% dominio"; temas con mayúscula inicial.
- [ ] **Ranking**: lista de 9no, jgarcia marcado con "Tú"; 🔥 0 para quien no practicó ayer u hoy.
- [ ] **Chat en Ciencias**: chip "Ciencias Naturales" → "¿Qué es el sistema endocrino?" → respuesta con chips de página (entre ellos **📖 Página 23**).
- [ ] **Chat en Matemáticas**: chip "Matemáticas" (empieza conversación nueva) → "¿Cómo se calcula el área superficial de una esfera?" → chips de página (entre ellos **📖 Página 113**).
- [ ] **Perfil** (pestaña 👤): nombre completo, @jgarcia, 9no Básico, mejor racha y puntos (tras practicar pueden haber subido).
- [ ] **Cerrar sesión** → confirmación → vuelve al login. Reabrir la app → pide login.
- [ ] (Opcional) **Sesión expirada**: con la app abierta en jgarcia, desactivarlo desde el panel admin web
  (Estudiantes → desactivar) y tocar cualquier pestaña → vuelve al login con "👋 Tu sesión expiró, vuelve a
  ingresar." **Reactivarlo** después.

## 2. Después de la prueba: dejar a jgarcia como estaba

La prueba le añade a jgarcia actividades, progreso, chat y racha de octubre, que entrarían en el
traslado a producción (el mapa de calor y Mi progreso no filtran por fecha). Para restaurarlo:

```bash
# 1. Conversaciones de la prueba (fuera de la ventana del piloto)
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "delete from conversacion where estudiante_id = (select id from usuario where username = '"'"'jgarcia'"'"') and fecha_creacion >= '"'"'2026-10-01 06:00+00'"'"';"'
# 2. Rehacer las actividades del piloto de 9no (conserva su chat de septiembre; recalcula racha y puntos)
docker compose exec -T backend sh -c "cd /app && python scripts/seed_piloto.py --csv /tmp/datos_simulados_cap5.csv --mapeo /tmp/mapeo.csv --rehacer-actividades --todas --grado 7 --max-usd 0.2"
docker compose exec -T backend sh -c "cd /app && python scripts/verificar_seed.py --csv /tmp/datos_simulados_cap5.csv --mapeo /tmp/mapeo.csv"
```

(Si el contenedor se recreó, copiar antes `datos/datos_simulados_cap5.csv` y `datos/mapeo_estudiantes_csv.csv`
a `/tmp/` del backend, como en `docs/despliegue-produccion.md`.)
