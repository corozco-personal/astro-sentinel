#!/usr/bin/env python3
"""
CLI Principal de Búsqueda de Agujeros Negros en Datos de TESS.
"""
import argparse
import sys
from pipeline.pipeline import BlackHolePipeline

def main():
    parser = argparse.ArgumentParser(
        description="Buscador de Candidatos a Agujeros Negros No Documentados en TESS"
    )
    parser.add_argument(
        "--target",
        type=str,
        default="TIC 261136679",
        help="Identificador del objetivo en TESS (ej. 'TIC 261136679', 'TIC 25155310', etc.)"
    )
    parser.add_argument(
        "--sector",
        type=int,
        default=None,
        help="Sector de observación de TESS específico (opcional)"
    )

    args = parser.parse_args()

    pipeline = BlackHolePipeline()
    result = pipeline.analyze_target(args.target, sector=args.sector)

    if result.get("status") == "SUCCESS":
        print("\n[Resultados Finales]")
        print(f"Target: {result['target_id']}")
        print(f"Veredicto: {result['assessment']['verdict']}")
        print(f"Informe guardado en: {result['report_path']}")
    else:
        print(f"\n[Error] {result.get('reason')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
