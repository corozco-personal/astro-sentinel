# Black Hole Candidate Search Pipeline (TESS / MAST)

Sistema modular para la búsqueda e identificación de candidatos a agujeros negros (de masa estelar, aislados o en sistemas binarios no interactuantes) a partir de fotometría de TESS (Transiting Exoplanet Survey Satellite) y verificación cruzada contra catálogos astrométricos (Gaia) y bases de datos astronómicas (SIMBAD / VizieR / NASA Exoplanet Archive).

## Fundamento Astrofísico

Los agujeros negros no emiten luz directamente, pero pueden detectarse fotométricamente mediante tres firmas principales:

1. **Microlente Gravitatoria Aislada o Binaria (Gravitational Microlensing)**:
   - Simetría o asimetrías de curva de luz características según el modelo Paczyński:
     $$A(u) = \frac{u^2 + 2}{u \sqrt{u^2 + 4}}, \quad u(t) = \sqrt{u_0^2 + \left(\frac{t - t_0}{t_{\rm E}}\right)^2}$$
   - Larga duración del evento Einstein ($t_{\rm E} > 50-100$ días para agujeros negros estelares).
   - Ausencia de variación cromática en el pico y ausencia de eclipse secundario.
   - Modelo de "self-lensing" en sistemas binarios compactos: magnificación focal periódica cuando el agujero negro pasa frente a la estrella compañera.

2. **Modulación Elipsoidal Pura y Beaming Doppler (Binarias durmientes / Dormant BH Companions)**:
   - Variaciones periódicas por distorsión de marea de una estrella gigante o de secuencia principal debida a un objeto compacto no luminoso de alta masa (función de masa $f(M) > 3 M_\odot$).
   - Deformación armónica característica (amplitudes en $2f$ y $1f$).

3. **Eventos Transitorios Cataclísmicos Inusuales (TDE / Fast Blue Optical Transients)**:
   - Disrupciones de marea o acreción esporádica en agujeros negros de masa intermedia (IMBH).

## Arquitectura del Sistema de Vigilancia Autónoma

```text
black-hole-search/
├── config.py                     # Parámetros astrofísicos y umbrales de detección
├── run_scanner.py                # Servicio / Demonio de escaneo continuo autónomo
├── main.py                       # CLI interactivo para analizar TICs individuales
├── test_pipeline.py              # Suite de validación con eventos sintéticos de BH
├── pipeline/
│   ├── tess_client.py            # Descarga, limpieza y normalización TESS/MAST
│   ├── continuous_scanner.py     # Gestor de cola continua e indexación SQLite
│   ├── notifier.py               # Sistema multicanal de alertas (macOS, JSONL, Terminal)
│   ├── cross_match.py            # Filtro contra fuentes oficiales (MAST, Exoplanetas, BHs)
│   ├── report_generator.py       # Gráficos de diagnóstico e informes JSON
│   └── detectors/
│       ├── microlensing.py       # Ajuste no lineal Paczyński para BHs aislados
│       └── ellipsoidal.py        # Periodogramas Lomb-Scargle para BHs en binarias
└── outputs/
    ├── scan_progress.db          # Base de datos SQLite de auditoría de estrellas
    ├── alerts.jsonl              # Bitácora histórica de candidatos detectados
    ├── candidates/               # Reportes detallados por TIC
    └── plots/                    # Curvas de luz y ajustes gráficos (.png)
```

## Modos de Uso

### 1. Iniciar el demonio de análisis continuo:
```bash
.venv/bin/python run_scanner.py --delay 0.5
```
*El sistema iterará sector por sector de TESS descargando series temporales reales, evaluando anomalías y guardando el progreso para nunca repetir una estrella ya analizada.*

### 2. Ejecutar con una lista personalizada de estrellas:
```bash
.venv/bin/python run_scanner.py --targets-file mis_estrellas.txt
```

### 3. Consultar la bitácora de alertas de nuevos candidatos:
```bash
cat outputs/alerts.jsonl
```

