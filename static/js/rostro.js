/* =========================================================
   rostro.js — utilidades de reconocimiento facial con face-api.js
   (TensorFlow.js). Todo el análisis ocurre en el navegador:
   la imagen de la cámara NUNCA se envía al servidor, solo el
   descriptor facial (128 números).

   Modelos (carpeta /static/models):
     - tinyFaceDetector : encuentra el rostro en la imagen
     - faceLandmark68   : 68 puntos del rostro (alinea la cara antes de calcular el descriptor)
     - faceRecognition  : red ResNet-34 que produce el descriptor de 128 valores
   ========================================================= */
const Rostro = (() => {
    const RUTA_MODELOS = '/static/models';
    let modelosListos = false;
    let flujo = null;

    async function cargarModelos() {
        if (modelosListos) return;
        if (typeof faceapi === 'undefined') throw new Error('No se pudo cargar face-api.js.');
        await Promise.all([
            faceapi.nets.tinyFaceDetector.loadFromUri(RUTA_MODELOS),
            faceapi.nets.faceLandmark68Net.loadFromUri(RUTA_MODELOS),
            faceapi.nets.faceRecognitionNet.loadFromUri(RUTA_MODELOS),
        ]);
        modelosListos = true;
    }

    async function encenderCamara(video) {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('Este navegador no permite usar la cámara (se necesita HTTPS o localhost).');
        }
        try {
            flujo = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: false,
            });
        } catch (e) {
            throw new Error(e.name === 'NotAllowedError'
                ? 'Debes permitir el acceso a la cámara para usar el reconocimiento facial.'
                : 'No se encontró una cámara disponible.');
        }
        video.srcObject = flujo;
        await video.play();
    }

    function apagarCamara(video) {
        if (flujo) flujo.getTracks().forEach((t) => t.stop());
        flujo = null;
        if (video) video.srcObject = null;
    }

    const opciones = () => new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 });
    const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

    /* Analiza un cuadro: devuelve {ok, motivo, resultado} */
    async function analizar(video) {
        const caras = await faceapi.detectAllFaces(video, opciones()).withFaceLandmarks().withFaceDescriptors();
        if (caras.length === 0) return { ok: false, motivo: 'No se detecta un rostro. Mira de frente a la cámara.' };
        if (caras.length > 1) return { ok: false, motivo: 'Hay más de un rostro. Solo debe aparecer una persona.' };
        const cara = caras[0];
        const ancho = cara.detection.box.width / video.videoWidth;
        if (cara.detection.score < 0.7) return { ok: false, motivo: 'Mejora la iluminación y mira de frente.' };
        if (ancho < 0.2) return { ok: false, motivo: 'Acércate un poco más a la cámara.' };
        return { ok: true, resultado: cara };
    }

    /* Registro: toma N capturas válidas (un solo rostro, de frente y bien iluminado) */
    async function capturarMuestras(video, n, alAvanzar) {
        const muestras = [];
        const limite = Date.now() + 30000;
        while (muestras.length < n) {
            if (Date.now() > limite) throw new Error('No se pudo capturar el rostro. Revisa la luz e inténtalo otra vez.');
            const r = await analizar(video);
            if (!r.ok) { alAvanzar(muestras.length, r.motivo, false); await esperar(250); continue; }
            muestras.push(Array.from(r.resultado.descriptor));
            alAvanzar(muestras.length, `Captura ${muestras.length} de ${n} lista. Mueve un poco la cabeza.`, true);
            await esperar(900);
        }
        return muestras;
    }

    /* Login: espera un rostro válido (uno solo, de frente, bien iluminado) en 2 cuadros
       seguidos y devuelve el descriptor del de mejor calidad. La comparación la hace el servidor. */
    async function capturarRostro(video, alAvanzar, tiempoMax = 20000) {
        const limite = Date.now() + tiempoMax;
        let anterior = null;
        while (Date.now() < limite) {
            const r = await analizar(video);
            if (!r.ok) { anterior = null; alAvanzar(r.motivo, false); await esperar(150); continue; }
            if (anterior) {
                const mejor = r.resultado.detection.score >= anterior.detection.score ? r.resultado : anterior;
                return Array.from(mejor.descriptor);
            }
            anterior = r.resultado;
            alAvanzar('Rostro detectado. No te muevas…', true);
            await esperar(150);
        }
        throw new Error('No se pudo detectar tu rostro. Mira de frente a la cámara con buena luz.');
    }

    return { cargarModelos, encenderCamara, apagarCamara, capturarMuestras, capturarRostro };
})();
