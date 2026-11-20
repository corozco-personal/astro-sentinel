"""
Generador de Cartas de Búsqueda Astronómicas (Astronomical Finder Charts) para telescopios terrestres.
Produce mapas de orientación científica (5x5 arcmin) en alta definición con estrellas de referencia para seguimiento ToO.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
from astroquery.mast import Catalogs

class FinderChartGenerator:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir / "finder_charts"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_finder_chart(self, target_id: str, ra: float, dec: float, fov_arcmin: float = 6.0) -> str:
        """
        Genera un Finder Chart formal de 6x6 arcmin centrado en el candidato
        con retícula Norte-Este y marcas de estrellas de calibración de campo.
        """
        chart_path = self.output_dir / f"{target_id.replace(' ', '_')}_finder_chart.png"
        
        fig, ax = plt.subplots(figsize=(6, 6), dpi=150, facecolor='#090c12')
        ax.set_facecolor('#07090e')

        # Consultar estrellas de campo en TIC (radio de 3 arcmin)
        try:
            coord = SkyCoord(ra=ra, dec=dec, unit=(u.deg, u.deg))
            res = Catalogs.query_region(coord, radius=fov_arcmin/2.0 * u.arcmin, catalog="TIC")
            
            if res is not None and len(res) > 0:
                ras = np.array(res["ra"])
                decs = np.array(res["dec"])
                tmags = np.array(res["Tmag"])

                # Desplazamientos en segundos de arco relativos al centro
                delta_ra_arcsec = (ras - ra) * 3600.0 * np.cos(np.radians(dec))
                delta_dec_arcsec = (decs - dec) * 3600.0

                # Tamaño de marcador inversamente proporcional a la magnitud
                valid_m = np.isfinite(tmags)
                sizes = np.clip(120.0 - 6.0 * tmags, 6.0, 150.0)

                # Estrellas de campo (fondo)
                ax.scatter(delta_ra_arcsec, delta_dec_arcsec, s=sizes, color='#e2e8f0', alpha=0.85, edgecolors='none', label='Field Stars')
        except Exception:
            pass

        # Marcar objetivo central (Candidato a Agujero Negro)
        ax.scatter([0], [0], s=180, facecolors='none', edgecolors='#ff3366', linewidths=2.5, label='Target (0,0)')
        ax.scatter([0], [0], s=35, color='#ff3366', marker='+')

        # Retícula y límites de visión
        lim = (fov_arcmin / 2.0) * 60.0
        ax.set_xlim(lim, -lim) # Este hacia la izquierda (convención astronómica estándar)
        ax.set_ylim(-lim, lim)

        ax.set_title(f"ASTRONOMICAL FINDER CHART: {target_id}\nRA: {ra:.4f}° | DEC: {dec:.4f}° (FOV: {fov_arcmin}' x {fov_arcmin}')", color='#00f2fe', fontsize=10, family='monospace', pad=12)
        ax.set_xlabel("Relative ΔRA (arcsec) [East ←]", color='#94a3b8', fontsize=8.5)
        ax.set_ylabel("Relative ΔDEC (arcsec) [→ North]", color='#94a3b8', fontsize=8.5)

        ax.tick_params(colors='#7987a1', labelsize=8)
        ax.grid(color='#1f2737', linestyle='--', linewidth=0.6, alpha=0.7)

        # Rosa de orientación astronómica (North & East arrows)
        ax.annotate('N', xy=(0.08, 0.92), xycoords='axes fraction', color='#00e676', fontweight='bold', fontsize=10)
        ax.annotate('E', xy=(0.02, 0.84), xycoords='axes fraction', color='#00e676', fontweight='bold', fontsize=10)
        ax.annotate('', xy=(0.06, 0.96), xytext=(0.06, 0.86), xycoords='axes fraction', arrowprops=dict(arrowstyle="->", color="#00e676", lw=1.5))
        ax.annotate('', xy=(0.00, 0.86), xytext=(0.06, 0.86), xycoords='axes fraction', arrowprops=dict(arrowstyle="->", color="#00e676", lw=1.5))

        plt.tight_layout()
        plt.savefig(chart_path, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)

        return str(chart_path)
