"""
PDFScanner 진입점.

모든 오케스트레이션(인자 파싱 → 추출 → 저장 → 출력)은 이 파일에서만 수행합니다.
credit_scanner 패키지는 추출·분류·저장용 라이브러리입니다.

실행 예:
  python main.py report.pdf --target issuer
  python main.py ./pdfs -o result.xlsx --target coco_t1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from credit_scanner.constants import TARGET_INSTRUMENT_CHOICES
from credit_scanner.export.excel import (
    build_detail_rows,
    build_summary_row,
    write_results_workbook,
)
from credit_scanner.export.json_io import save_result_to_json
from credit_scanner.export.review import build_review_rows
from credit_scanner.pipeline import extract_credit_report


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "신용평가서 PDF에서 평가대상별 신용등급을 추출합니다."
        ),
    )
    parser.add_argument(
        "input",
        type=str,
        help="PDF 파일 또는 폴더 경로",
    )
    parser.add_argument("-o", "--output", type=str, default=None)
    parser.add_argument(
        "--target",
        type=str,
        default="coco_t1",
        choices=TARGET_INSTRUMENT_CHOICES,
    )
    parser.add_argument(
        "--taxonomy",
        type=str,
        default=None,
        help="instrument_taxonomy.yaml 경로",
    )
    parser.add_argument("--non-recursive", action="store_true")
    return parser


def run_single_pdf(
    pdf_path: Path,
    *,
    target_instrument: str,
    output_path: Path,
    taxonomy_path: Path | None,
) -> dict[str, Any]:
    result = extract_credit_report(
        pdf_path=pdf_path,
        target_instrument=target_instrument,
        taxonomy_path=taxonomy_path,
    )
    save_result_to_json(result=result, output_path=output_path)
    return result


def run_folder(
    input_folder: Path,
    *,
    output_excel: Path,
    target_instrument: str,
    recursive: bool,
    taxonomy_path: Path | None,
) -> Path:
    pdf_files = (
        sorted(input_folder.rglob("*.pdf"))
        if recursive
        else sorted(input_folder.glob("*.pdf"))
    )

    summary_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for pdf_path in pdf_files:
        try:
            result = extract_credit_report(
                pdf_path=pdf_path,
                target_instrument=target_instrument,
                taxonomy_path=taxonomy_path,
            )
            results.append(result)
            summary_rows.append(build_summary_row(result))
            detail_rows.extend(build_detail_rows(result))
        except Exception as error:
            summary_rows.append(
                {
                    "파일명": pdf_path.name,
                    "파일경로": str(pdf_path),
                    "처리상태": "error",
                    "오류내용": str(error),
                }
            )

    write_results_workbook(
        output_excel=output_excel,
        summary_rows=summary_rows,
        detail_rows=detail_rows,
        review_rows=build_review_rows(results),
    )
    return output_excel


def main(argv: list[str] | None = None) -> None:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    taxonomy_path = Path(args.taxonomy) if args.taxonomy else None

    if input_path.is_file():
        output_path = (
            Path(args.output)
            if args.output
            else input_path.with_suffix(".credit_rating.json")
        )
        result = run_single_pdf(
            input_path,
            target_instrument=args.target,
            output_path=output_path,
            taxonomy_path=taxonomy_path,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if input_path.is_dir():
        output_path = (
            Path(args.output)
            if args.output
            else input_path / "credit_rating_result.xlsx"
        )
        excel_path = run_folder(
            input_path,
            output_excel=output_path,
            target_instrument=args.target,
            recursive=not args.non_recursive,
            taxonomy_path=taxonomy_path,
        )
        print(excel_path)
        return

    raise FileNotFoundError(
        f"입력 경로를 찾을 수 없습니다: {input_path}"
    )


if __name__ == "__main__":
    main()
