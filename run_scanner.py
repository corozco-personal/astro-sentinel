#!/usr/bin/env python3
"""
Punto de entrada para el Demonio / Servicio de Escaneo Continuo de TESS.
Permite ejecutar el escaneo autónomo en segundo plano o interactivo.
"""
import argparse
import sys
from pipeline.continuous_scanner import ContinuousScanner

def main():
    parser = argparse.ArgumentParser(
        description="Escaneo Continuo y Vigilancia Autónoma de Agujeros Negros en TESS"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Demora en segundos entre consultas a TESS/MAST para evitar rate limits (default: 0.5s)"
    )
    parser.add_argument(
        "--targets-file",
        type=str,
        default=None,
        help="Archivo opcional con lista de TICs o estrellas a escanear línea por línea"
    )
    parser.add_argument(
        "--max-targets",
        type=int,
        default=None,
        help="Máximo de objetivos a evaluar (omitir para escaneo infinito continuo)"
    )

    args = parser.parse_args()

    targets = None
    if args.targets_file:
        try:
            with open(args.targets_file, "r", encoding="utf-8") as f:
                targets = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except Exception as e:
            print(f"Error al leer {args.targets_file}: {e}")
            sys.exit(1)

    scanner = ContinuousScanner(delay_between_targets=args.delay)
    scanner.run_continuous_scan(custom_targets=targets, max_iterations=args.max_targets)

if __name__ == "__main__":
    main()
