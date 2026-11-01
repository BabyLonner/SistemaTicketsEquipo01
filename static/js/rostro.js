
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


    async function capturarRostro(video, alAvanzar, tiempoMax = 20000) {
        const limite = Date.now() + tiempoMax;
        const descriptores = [];
        while (descriptores.length < 3) {
            if (Date.now() > limite) throw new Error('No se pudo detectar tu rostro. Mira de frente a la cámara con buena luz.');
            const r = await analizar(video);
            if (!r.ok) { alAvanzar(r.motivo, false); await esperar(150); continue; }
            descriptores.push(Array.from(r.resultado.descriptor));
            alAvanzar(`Rostro detectado (${descriptores.length}/3). No te muevas…`, true);
            await esperar(200);
        }
        return descriptores[0].map((_, i) => descriptores.reduce((s, d) => s + d[i], 0) / descriptores.length);
    }

    return { cargarModelos, encenderCamara, apagarCamara, capturarMuestras, capturarRostro };
})();
