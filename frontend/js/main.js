$(document).ready(function() {
    const API_URL = 'http://191.91.240.39';
    let controlWs = null;
    let selectedCells = new Set();
    const barcosColocados = {
        submarino: false,
        acorazado: false,
        destructor: false
    };

    // Clase para manejar los sonidos
    class SoundManager {
        constructor() {
            this.sounds = {
                splash: new Audio('sounds/splash.mp3'),
                hit: new Audio('sounds/hit.mp3'),
                fail: new Audio('sounds/fail.mp3')
            };

            // Inicializar todos los sonidos con volumen bajo
            Object.values(this.sounds).forEach(sound => {
                sound.volume = 0.3;
                // Precargar los sonidos
                sound.load();
            });

            // Manejar la interacción inicial del usuario
            document.addEventListener('click', () => this.initializeSounds(), { once: true });
        }

        initializeSounds() {
            // Intentar reproducir y pausar inmediatamente cada sonido
            Object.values(this.sounds).forEach(sound => {
                sound.play().then(() => {
                    sound.pause();
                    sound.currentTime = 0;
                }).catch(err => console.log('Error precargando sonido:', err));
            });
        }

        async play(type) {
            try {
                if (this.sounds[type]) {
                    await this.sounds[type].play();
                }
            } catch (error) {
                if (error.name === 'NotAllowedError') {
                    // Si el error es por falta de interacción, intentar inicializar
                    this.initializeSounds();
                }
                console.log('Error reproduciendo sonido:', error);
            }
        }
    }

    // Instanciar el manejador de sonidos
    const soundManager = new SoundManager();

    // Crear tablero inicial
    function crearTablero() {
        const tablero = $('#tableroControl');
        for (let i = 0; i < 5; i++) {
            for (let j = 0; j < 5; j++) {
                const coordenada = `${String.fromCharCode(65 + i)}${j + 1}`;
                const celda = $('<div>', {
                    class: 'celda',
                    text: coordenada,
                    'data-coord': coordenada
                });
                celda.on('click', () => seleccionarCelda(celda, coordenada));
                tablero.append(celda);
            }
        }
    }

    function seleccionarCelda(celda, coordenada) {
        const tipoBarco = $('#tipoBarco').val();
        const tamañoBarco = {
            'submarino': 2,
            'acorazado': 3,
            'destructor': 1
        }[tipoBarco];

        if (celda.hasClass('ocupado')) {
            return;
        }

        if (celda.hasClass('selected')) {
            celda.removeClass('selected');
            selectedCells.delete(coordenada);
        } else if (selectedCells.size < tamañoBarco && validarSeleccionContinua(coordenada)) {
            celda.addClass('selected');
            selectedCells.add(coordenada);
        }
    }

    function validarSeleccionContinua(nuevaCoordenada) {
        if (selectedCells.size === 0) return true;
        
        const coordsActuales = Array.from(selectedCells);
        const nuevaFila = nuevaCoordenada.charCodeAt(0) - 65;
        const nuevaCol = parseInt(nuevaCoordenada[1]) - 1;
        
        const primeraCoord = coordsActuales[0];
        const primeraFila = primeraCoord.charCodeAt(0) - 65;
        const primeraCol = parseInt(primeraCoord[1]) - 1;
        
        const mismaFila = nuevaFila === primeraFila;
        const mismaColumna = nuevaCol === primeraCol;
        
        if (!mismaFila && !mismaColumna) {
            mostrarError('Las casillas deben estar en la misma fila o columna');
            return false;
        }
        
        for (const coord of coordsActuales) {
            const fila = coord.charCodeAt(0) - 65;
            const col = parseInt(coord[1]) - 1;
            
            const esAdyacente = (Math.abs(fila - nuevaFila) === 1 && col === nuevaCol) ||
                               (Math.abs(col - nuevaCol) === 1 && fila === nuevaFila);
                               
            if (esAdyacente) return true;
        }
        
        mostrarError('Las casillas deben ser continuas');
        return false;
    }

    async function colocarFlota() {
        const tipoBarco = $('#tipoBarco').val();
        const tamañoBarco = {
            'submarino': 2,
            'acorazado': 3,
            'destructor': 1
        }[tipoBarco];

        if (barcosColocados[tipoBarco]) {
            mostrarError('Este tipo de barco ya ha sido colocado');
            return;
        }

        if (selectedCells.size !== tamañoBarco) {
            mostrarError(`Selecciona exactamente ${tamañoBarco} casillas para el ${tipoBarco}`);
            return;
        }

        try {
            const response = await fetch(`${API_URL}/colocar-flota`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    tipo: tipoBarco,
                    posiciones: Array.from(selectedCells)
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Error al colocar la flota');
            }

            const data = await response.json();
            barcosColocados[tipoBarco] = true;
            
            selectedCells.forEach(coord => {
                const celda = $(`.celda[data-coord="${coord}"]`);
                celda.removeClass('selected')
                    .addClass('ocupado')
                    .attr('data-tipo', tipoBarco)
                    .text(tipoBarco[0].toUpperCase());
            });
            
            selectedCells.clear();
            actualizarEstado(`${tipoBarco} colocado correctamente`);
            
            // Si todos los barcos están colocados, conectar al WebSocket
            if (data.flota_completa) {
                $('#tipoBarco').prop('disabled', true);
                $('#btnColocar').prop('disabled', true);
                actualizarEstado('Flota completa. Conectando al servidor de control...');
                conectarWebSocket();
            }
        } catch (error) {
            actualizarEstado(error.message, true);
        }
    }

    function actualizarEstado(mensaje, isError = false) {
        const statusDiv = $('#status');
        statusDiv.text(mensaje);
        statusDiv.removeClass('alert-info alert-danger')
                .addClass(isError ? 'alert-danger' : 'alert-info');
    }

    function mostrarError(mensaje) {
        actualizarEstado(mensaje, true);
    }

    async function cargarEstadoInicial() {
        try {
            const response = await fetch(`${API_URL}/estado`);
            if (!response.ok) {
                throw new Error('Error al obtener el estado del servidor');
            }

            const estado = await response.json();
            actualizarTableroDesdeEstado(estado);

            if (estado.estado_actual !== 'q0') {
                conectarWebSocket();
                actualizarEstado('Servidor activo - Conectado');
            } else {
                actualizarEstado('Servidor listo para colocar barcos');
            }
        } catch (error) {
            actualizarEstado('Error al conectar con el servidor: ' + error.message, true);
        }
    }

    function actualizarTableroDesdeEstado(estado) {
        selectedCells.clear();
        
        $('.celda').each(function() {
            const celda = $(this);
            celda.removeClass('selected ocupado impacto agua')
                 .text(celda.data('coord'))
                 .css('background-color', '');
        });

        // Actualizar barcos colocados
        Object.entries(estado.barcos_colocados).forEach(([tipo, colocado]) => {
            barcosColocados[tipo] = colocado;
        });

        // Mostrar barcos en el tablero
        Object.entries(estado.tablero).forEach(([coord, contenido]) => {
            if (contenido) {
                const celda = $(`.celda[data-coord="${coord}"]`);
                celda.addClass('ocupado').text(contenido);
            }
        });

        // Mostrar impactos
        Object.entries(estado.impactos).forEach(([coord, impacto]) => {
            if (impacto !== '~') {
                const celda = $(`.celda[data-coord="${coord}"]`);
                if (impacto === 'X') {
                    celda.css('background-color', '#ff4444').text('💥');
                } else if (impacto === 'O') {
                    celda.css('background-color', '#44aaff').text('💧');
                }
            }
        });

        // Actualizar estado de los controles
        const todosLosBarcos = Object.values(barcosColocados).every(v => v);
        $('#tipoBarco, #btnColocar').prop('disabled', todosLosBarcos);
    }

    function conectarWebSocket() {
        if (controlWs) {
            controlWs.close();
        }

        const wsUrl = API_URL.replace('http', 'ws');
        controlWs = new WebSocket(`${wsUrl}/ws/control`);
        
        controlWs.onopen = function() {
            actualizarEstado('Conectado al servidor de control. Esperando ataques...');
        };

        controlWs.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (data.tipo === "impacto") {
                mostrarImpacto(data.coordenada, data.resultado);
            } else if (data.tipo === "estado_inicial") {
                actualizarTableroDesdeEstado(data.estado);
            } else if (data.tipo === "error") {
                actualizarEstado(data.mensaje, true);
                // Reconectar después de un tiempo si la flota no está lista
                setTimeout(conectarWebSocket, 5000);
            }
        };

        controlWs.onclose = function() {
            controlWs = null;
            actualizarEstado('Desconectado del servidor de control');
        };

        controlWs.onerror = function(error) {
            controlWs = null;
            actualizarEstado('Error en la conexión WebSocket: ' + error.message, true);
        };
    }

    function mostrarImpacto(coordenada, resultado) {
        const celda = $(`.celda[data-coord="${coordenada}"]`);
        if (celda.length) {
            celda.removeClass('agua-temporal impacto-permanente agua-animation explosion-animation');
            
            switch(resultado) {
                case "Impactado":
                    celda.addClass('impacto-permanente explosion-animation')
                         .text('💥');
                    soundManager.play('hit');
                    setTimeout(() => {
                        celda.removeClass('explosion-animation');
                    }, 800);
                    break;
                case "Hundido":
                    // Encontrar todas las celdas del mismo tipo de barco
                    const tipoBarco = celda.attr('data-tipo');
                    $(`.celda[data-tipo="${tipoBarco}"]`).each(function() {
                        const celdaBarco = $(this);
                        celdaBarco.addClass('impacto-permanente explosion-animation')
                                 .text('💀');
                        // Hacer una animación más intensa para el hundimiento
                        celdaBarco.css('animation-iteration-count', '2');
                    });
                    
                    soundManager.play('fail');
                    
                    // Remover las animaciones después de que terminen
                    setTimeout(() => {
                        $(`.celda[data-tipo="${tipoBarco}"]`).each(function() {
                            $(this).removeClass('explosion-animation')
                                   .css('animation-iteration-count', '');
                        });
                    }, 1600);
                    break;
                case "Fallido":
                    celda.addClass('agua-temporal agua-animation')
                         .text('💧');
                    soundManager.play('splash');
                    setTimeout(() => {
                        celda.removeClass('agua-animation')
                             .text(coordenada)
                             .removeClass('agua-temporal');
                    }, 1000);
                    break;
            }
        }
        actualizarEstado(`Ataque recibido en ${coordenada}: ${resultado}`);
    }

    async function reiniciarServicio() {
        try {
            if (controlWs) {
                controlWs.close();
                controlWs = null;
            }

            const response = await fetch(`${API_URL}/reiniciar`, {
                method: 'POST'
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || 'Error al reiniciar el servicio');
            }

            // Resetear estado local
            selectedCells.clear();
            Object.keys(barcosColocados).forEach(key => barcosColocados[key] = false);

            // Habilitar controles
            $('#tipoBarco, #btnColocar').prop('disabled', false);

            // Limpiar tablero
            $('.celda').each(function() {
                const celda = $(this);
                celda.removeClass('selected ocupado agua-temporal impacto-permanente')
                     .text(celda.data('coord'))
                     .css('background-color', '');
            });

            actualizarEstado('Servicio reiniciado. Puede colocar los barcos nuevamente.');

            // Reconectar después de un momento
            setTimeout(async () => {
                await cargarEstadoInicial();
            }, 2000);

        } catch (error) {
            actualizarEstado('Error: ' + error.message, true);
        }
    }

    // Event Listeners
    $('#btnColocar').on('click', colocarFlota);
    $('#btnReiniciar').on('click', reiniciarServicio);

    // Inicialización
    crearTablero();
    cargarEstadoInicial();
}); 