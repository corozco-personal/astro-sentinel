"""
Script de pruebas unitarias y de simulación para validar los algoritmos de detección:
1. Simulación de curva sintética de Microlente Gravitatoria de un agujero negro estelar (M ~ 10 M_sun, tE ~ 40 días).
2. Simulación de curva con modulación elipsoidal generada por un objeto compacto.
3. Validación contra el módulo de descarte oficial SIMBAD.
"""
import numpy as np
import lightkurve as lk
from astropy.time import Time
from pipeline.detectors.microlensing import MicrolensingDetector, paczynski_model
from pipeline.detectors.ellipsoidal import EllipsoidalDetector
from pipeline.cross_match import CatalogCrossMatcher

def test_microlensing_synthetic():
    print("\n--- Test 1: Simulación de Evento de Microlente (Agujero Negro Aislado) ---")
    time_arr = np.linspace(1500, 1580, 1500)
    # Parámetros astrofísicos típicos de lente masiva
    true_t0 = 1540.0
    true_u0 = 0.25
    true_tE = 35.0 # Cruce de radio de Einstein característico de BH
    true_fbase = 1.0

    clean_flux = paczynski_model(time_arr, true_t0, true_u0, true_tE, true_fbase)
    # Ruido fotométrico realista de TESS (~200 ppm)
    noise = np.random.normal(0, 0.005, size=len(time_arr))
    flux_with_noise = clean_flux + noise

    lc = lk.LightCurve(time=Time(time_arr, format='btjd'), flux=flux_with_noise, flux_err=np.full_like(flux_with_noise, 0.005))
    detector = MicrolensingDetector()
    res = detector.evaluate(lc)

    print("Resultado Microlente:", res)
    assert res["is_candidate"] is True, "El detector debería identificar el evento de microlente de BH"
    print(f"-> Detectado exitosamente: t0={res['t0']:.2f}, u0={res['u0']:.3f}, tE={res['tE_days']:.1f} días, Δchi2={res['delta_chi2']:.1f}")

def test_ellipsoidal_synthetic():
    print("\n--- Test 2: Simulación de Modulación Elipsoidal (Binaria con Compañero Oscuro) ---")
    time_arr = np.linspace(1500, 1550, 1000)
    orbital_period = 4.2 # días
    omega = 2 * np.pi / orbital_period
    
    # Modulación armónica con componente principal en 2*f_orb (efecto de marea / marea elipsoidal)
    flux_clean = 1.0 + 0.015 * np.cos(2 * omega * time_arr) + 0.004 * np.cos(omega * time_arr)
    noise = np.random.normal(0, 0.001, size=len(time_arr))
    flux_noisy = flux_clean + noise

    lc = lk.LightCurve(time=Time(time_arr, format='btjd'), flux=flux_noisy)
    detector = EllipsoidalDetector()
    # Parámetros de estrella gigante roja realista (compañero masivo induce marea fuerte)
    res = detector.evaluate(lc, star_mass=1.5, star_rad=3.0)

    print("Resultado Elipsoidal:", res)
    assert res["is_candidate"] is True, "El detector debería identificar la modulación de marea elipsoidal"
    print(f"-> Detectado exitosamente: Período={res['detected_period_days']:.2f} d, SNR={res['snr']:.1f}")

def test_cross_match_mock():
    print("\n--- Test 3: Verificación con fuentes oficiales ---")
    matcher = CatalogCrossMatcher()
    
    # Objeto conocido en literatura como agujero negro (Cygnus X-1)
    res_bh = matcher.check_simbad_and_mast("Cyg X-1")
    print("Cross-match Cyg X-1:", res_bh)
    assert res_bh["is_documented_black_hole"] is True, "Cyg X-1 debe ser detectado como agujero negro conocido"

    # Evaluación de novedad
    mock_detection = {"is_candidate": True, "type": "Microlensing (Paczynski)"}
    assessment_known = matcher.assess_undocumented_bh_potential(res_bh, mock_detection)
    print("Evaluación objeto documentado:", assessment_known)
    assert assessment_known["undocumented_candidate"] is False, "No debe marcarse como candidato no documentado si ya existe en catálogo"

    # Objeto no catalogado como agujero negro (TIC estándar)
    res_star = {"is_known_object": True, "object_type": "TIC STAR", "is_documented_black_hole": False, "is_eclipsing_binary": False}
    assessment_new = matcher.assess_undocumented_bh_potential(res_star, mock_detection)
    print("Evaluación estrella común con firma anómala:", assessment_new)
    assert assessment_new["undocumented_candidate"] is True, "Debe ser catalogado como candidato potencial a agujero negro sin documentar"

if __name__ == "__main__":
    test_microlensing_synthetic()
    test_ellipsoidal_synthetic()
    test_cross_match_mock()
    print("\n[OK] Todas las pruebas pasaron satisfactoriamente.")
